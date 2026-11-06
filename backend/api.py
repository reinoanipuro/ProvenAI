from fastapi import FastAPI
from pydantic import BaseModel, Field

from .pipeline import inspect_document

app = FastAPI(title="ProvenAI")


class InspectionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1_000_000)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
