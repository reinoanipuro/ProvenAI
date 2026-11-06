"""FastAPI service. Start with: uvicorn backend.main:app"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .audit import AuditStore
from .config import CHROMA_DIR, DATABASE, REGULATIONS_DIR, RULES_DIR, SAMPLES_DIR
from .pipeline import Pipeline, load_rules
from .rag import RegulatoryIndex
from .schemas import Inspection, InspectionRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pipeline = Pipeline(
        rules=load_rules(RULES_DIR),
        index=RegulatoryIndex(CHROMA_DIR, REGULATIONS_DIR),
        audit=AuditStore(DATABASE),
    )
    yield


app = FastAPI(title="ProvenAI Compliance Checker", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/samples")
def samples() -> list[str]:
    return sorted(path.name for path in SAMPLES_DIR.glob("*.md"))


@app.get("/samples/{name}")
def sample(name: str) -> dict:
    # Compare against the listing so the name can never escape the samples folder.
    if name not in samples():
        raise HTTPException(404, "Sample not found.")
    return {"filename": name, "text": (SAMPLES_DIR / name).read_text(encoding="utf-8")}


@app.post("/inspections")
def create_inspection(request: InspectionRequest) -> Inspection:
    return app.state.pipeline.run(request.filename, request.text)


@app.get("/inspections/{inspection_id}/audit")
def inspection_audit(inspection_id: str) -> list[dict]:
    return app.state.pipeline.audit.events(inspection_id)
