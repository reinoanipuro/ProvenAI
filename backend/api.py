import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import lovable
from .checker import accept_items, approve_rule, check_design
from .documents import MAX_FILE_BYTES, MAX_FILES, new_upload_folder
from .intake import describe, find_items, read_files
from .llm import LLMUnavailableError, OllamaClient, parse_design
from .pages import render_highlighted_page
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


def _optional_retriever() -> RegulatoryRetriever | None:
    try:
        return _get_retriever()
    except ValueError:
        return None


# The Lovable web app in web/app talks to this API under /lovable.
def _warm_up() -> None:
    """Load the index and models before the first request, so it does not wait for them."""
    try:
        _get_retriever().search("warm up", top_k=1)
    except ValueError:
        pass  # Index not built yet; requests report it with instructions.


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=_warm_up, daemon=True).start()
    # Rule quotes confirmed and OCR loaded before the first upload, so it is not slower.
    lovable.warm_up(_optional_retriever)
    if hasattr(llm, "load"):
        threading.Thread(target=llm.load, daemon=True).start()
    yield


app = FastAPI(title="ProvenAI", lifespan=lifespan)
# Lets a browser page, such as the Lovable app in web/, call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get("PROVENAI_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://[a-z0-9-]+\.(lovable\.app|lovableproject\.com|lovable\.dev)",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(lovable.create_router(lambda: llm, _optional_retriever), prefix="/lovable")


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
    property: str = Field(default="", max_length=200)
    source: str = Field(default="", max_length=300)
    attribute: str = Field(default="unknown", max_length=100)
    value_text: str = Field(min_length=1, max_length=100)


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class CheckRequest(BaseModel):
    text: str | None = Field(default=None, max_length=20_000)
    items: list[DesignItem] | None = Field(default=None, max_length=50)
    summarize: bool = True
    # False checks everything with Mistral and the regulations, ignoring approved rules.
    use_rule_library: bool = True


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


@app.post("/upload")
def upload(files: list[UploadFile] = File(...)) -> dict:
    """Read dropped design documents and return the design items for the engineer to confirm.

    Text is read from text files, Word files and PDF pages with text. Pictures
    and drawing pages without text are stored for 2D reading, a later step.
    """
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=422, detail=f"Drop at most {MAX_FILES} files at a time.")
    upload_id, folder = new_upload_folder()
    received: list[tuple[str, bytes]] = []
    warnings: list[str] = []
    for file in files:
        data = file.file.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            warnings.append(f"{file.filename}: larger than {MAX_FILE_BYTES // (1024 * 1024)} MB, skipped.")
            continue
        received.append((file.filename or "file", data))
    documents, read_warnings = read_files(received, folder)
    warnings.extend(read_warnings)
    attributes, _ = load_library()
    try:
        items, item_warnings = find_items(documents, llm, attributes)
    except LLMUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "upload_id": upload_id,
        "documents": [describe(document) for document in documents],
        "items": items,
        "warnings": warnings + item_warnings,
    }


@app.post("/check")
def check(request: CheckRequest) -> dict:
    """Check design values or regulation questions, with citations and a summary.

    Send confirmed items to skip reading the text again; send only text to let
    Mistral read it in the same call. Items with an approved rule use it; the
    rest are checked against the regulations by Mistral and reviewed by Python.
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
            use_rule_library=request.use_rule_library,
        )
    except LLMUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if search_warning:
        result["warnings"].append(search_warning)
    return result


@app.get("/rules")
def rules() -> dict:
    """The approved rule library, so engineers can see what is checked automatically."""
    attributes, library = load_library()
    return {
        "attributes": attributes,
        "rules": [
            {
                "id": rule.id,
                "title": rule.title,
                "attribute": rule.attribute,
                "requirement": rule.required_text,
                "filename": rule.source.filename,
                "page": rule.source.page,
                "section": rule.source.section,
                "quote": rule.source.quote,
            }
            for rule in library
        ],
    }


@app.get("/source/page")
def source_page(
    filename: str = Query(min_length=1, max_length=300),
    page: int = Query(ge=1, le=5000),
    quote: str = Query(default="", max_length=2000),
) -> Response:
    """The cited regulation page as an image, with the quote highlighted."""
    try:
        image, _ = render_highlighted_page(filename, page, quote)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(content=image, media_type="image/png")


class ApprovalRequest(BaseModel):
    proposal: dict


@app.post("/rules/approve")
def approve(request: ApprovalRequest) -> dict:
    """Save an AI-read requirement as a checked rule, once an engineer has confirmed it."""
    try:
        rule_id = approve_rule(request.proposal)
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"approved": rule_id}


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
