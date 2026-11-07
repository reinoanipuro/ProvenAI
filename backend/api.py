"""The ProvenAI checker: the web app's API under /lovable, regulation search and regulation pages."""

import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import lovable
from .llm import OllamaClient
from .pages import render_highlighted_page
from .rag import RegulatoryRetriever

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


def _warm_up() -> None:
    """Load the index and models before the first request, so it does not wait for them."""
    try:
        _get_retriever().search("warm up", top_k=1)
    except ValueError:
        pass  # Index not built yet; requests report it with instructions.


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=_warm_up, daemon=True).start()
    # Rule quotes confirmed and Mistral loaded before the first upload, so it is not slower.
    lovable.warm_up(_optional_retriever)
    if hasattr(llm, "load"):
        threading.Thread(target=llm.load, daemon=True).start()
    yield


app = FastAPI(title="ProvenAI", lifespan=lifespan)
# Lets the web app in web/app call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get("PROVENAI_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(lovable.create_router(lambda: llm, _optional_retriever), prefix="/lovable")


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
