import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .checker import accept_items, check_design
from .llm import LLMUnavailableError, OllamaClient, parse_design
from .pipeline import inspect_document
from .rag import RegulatoryRetriever
from .rules import load_library

retriever: RegulatoryRetriever | None = None
_retriever_lock = threading.Lock()
llm = OllamaClient()


def _get_retriever() -> RegulatoryRetriever:
    global retriever
    with _retriever_lock:
        if retriever is None:
            retriever = RegulatoryRetriever()
    return retriever


def _warm_up() -> None:
    """Load the index and models before the first request, so it does not wait for them."""
    try:
        _get_retriever().search("warm up", top_k=1)
    except ValueError:
        pass  # Index not built yet; requests report it with instructions.


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=_warm_up, daemon=True).start()
    yield


app = FastAPI(title="ProvenAI", lifespan=lifespan)


class InspectionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1_000_000)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "rag": "ready" if retriever is not None else "loading"}


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=5, ge=1, le=50)


@app.post("/rag/search")
def search_regulations(request: SearchRequest) -> dict:
    try:
        search = _get_retriever()
    except ValueError as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "The regulatory index is not ready. Put PDFs in "
                "data/regulations and run 'python rebuild_rag.py'."
            ),
        ) from error
    return {"query": request.query, "results": search.search(request.query, request.top_k)}


class DesignItem(BaseModel):
    element: str = Field(default="design item", max_length=200)
    attribute: str = Field(min_length=1, max_length=100)
    value_text: str = Field(min_length=1, max_length=100)


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class CheckRequest(BaseModel):
    text: str | None = Field(default=None, max_length=20_000)
    items: list[DesignItem] | None = Field(default=None, max_length=50)
    summarize: bool = True


@app.post("/parse")
def parse(request: ParseRequest) -> dict:
    """Read design items from text, so the engineer can confirm them before checking."""
    attributes, _ = load_library()
    try:
        items = parse_design(llm, request.text, attributes)
    except LLMUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    accepted, warnings = accept_items(items, request.text, attributes)
    return {"items": accepted, "warnings": warnings}


@app.post("/check")
def check(request: CheckRequest) -> dict:
    """Check design items against the rule library, with citations and a summary.

    Send confirmed items to skip reading the text again; send only text to let
    Mistral read it in the same call.
    """
    if not request.items and not request.text:
        raise HTTPException(status_code=422, detail="Send design text or design items.")
    try:
        search = _get_retriever()
        search_warning = None
    except ValueError:
        search = None
        search_warning = "Regulation search is not ready, so citations were not checked."
    items = [item.model_dump() for item in request.items] if request.items else None
    try:
        result = check_design(
            text=request.text,
            items=items,
            llm=llm,
            retriever=search,
            summarize=request.summarize,
        )
    except LLMUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if search_warning:
        result["warnings"].append(search_warning)
    return result


@app.post("/inspect")
def inspect(request: InspectionRequest) -> dict:
    findings = inspect_document(request.text)
    statuses = [finding.status for finding in findings]
    overall = (
        "FAIL" if "FAIL" in statuses
        else "UNKNOWN" if "UNKNOWN" in statuses
        else "PASS"
    )
    return {
        "overall": overall,
        "findings": [
            {
                "rule_id": finding.rule_id,
                "status": finding.status,
                "reason": finding.reason,
                "evidence": (
                    {
                        "attribute": finding.evidence.attribute,
                        "value": finding.evidence.value,
                        "unit": finding.evidence.unit,
                        "confidence": finding.evidence.confidence,
                        "quote": finding.evidence.quote,
                        "source": finding.evidence.source,
                    }
                    if finding.evidence
                    else None
                ),
            }
            for finding in findings
        ],
    }
