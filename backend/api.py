from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .pipeline import inspect_document
from .rag import RegulatoryRetriever

app = FastAPI(title="ProvenAI")
retriever: RegulatoryRetriever | None = None


class InspectionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1_000_000)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=5, ge=1, le=50)


@app.post("/rag/search")
def search_regulations(request: SearchRequest) -> dict:
    global retriever
    if retriever is None:
        try:
            retriever = RegulatoryRetriever()
        except ValueError as error:
            raise HTTPException(
                status_code=503,
                detail=(
                    "The regulatory index is not ready. Put PDFs in "
                    "data/regulations and run 'python rebuild_rag.py'."
                ),
            ) from error
    return {"query": request.query, "results": retriever.search(request.query, request.top_k)}


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
