"""PDF ingestion and hybrid retrieval for the compliance document knowledge base."""

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REGULATIONS_DIR = ROOT / "data" / "regulations"
CATALOG_NAME = "catalog.json"
VECTOR_DB_DIR = Path(os.environ.get("PROVENAI_INDEX_DIR", ROOT / ".runtime" / "chroma"))
COLLECTION_NAME = "ship_compliance_documents"
# Both models run through ONNX Runtime (see onnx_models.py). Changing the
# embedding model requires 'python rebuild_rag.py'.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_ONNX_FILE = "onnx/model_O3.onnx"
EMBEDDING_MAX_TOKENS = 256
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
RERANKER_ONNX_FILE = "onnx/model_O3.onnx"
RERANKER_MAX_TOKENS = 512
# all-MiniLM-L6-v2 reads about 256 tokens, so longer chunks would be cut off silently.
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
MIN_CHUNK_BEFORE_SECTION_BREAK = 120
CANDIDATES_PER_METHOD = 30
# Reranking is most of the query time. In tests/eval_rag.py, 20 candidates rank
# exactly as well as 30.
RERANK_POOL = 20
RRF_K = 60
SEARCH_CACHE_SIZE = 256

_ROMAN_OR_ID = r"(?:\d+[A-Za-z]?(?:[.\-/]\d+)*|[IVXLC]+(?:-\d+)?|[A-Z](?:-\d+)?)"
# Case-sensitive on purpose: running text such as "section 4 of the" is not a heading.
_HEADING_KINDS = "Regulation|Rule|Article|Section|Chapter|Part|Annex|Appendix"
_NAMED_HEADING = re.compile(
    rf"^(?P<kind>{_HEADING_KINDS}|{_HEADING_KINDS.upper()})\s+"
    rf"(?P<id>{_ROMAN_OR_ID})\s*(?:[:.\-–—]\s*)?(?P<title>[A-Z][^.]{{0,70}})?$"
)
_RESOLUTION_HEADING = re.compile(
    r"^(?:Resolution|RESOLUTION)\s+(?P<id>(?:MSC|MEPC|A)\.\d+\(\d+\))\s*$"
)
# Bare four-digit numbers are allowed for sections like 1003, but not years like 2010.
_NUMBERED_HEADING = re.compile(
    r"^(?P<id>[VT]?(?:\d{3}(?:\.\d+)*|\d{4}\.\d+(?:\.\d+)*|(?!19|20)\d{4}))\s+"
    r"(?P<title>[A-Z][^.]{2,70})(?:\.|$)"
)
_LEVELS = {
    "resolution": 0,
    "annex": 1,
    "appendix": 1,
    "chapter": 1,
    "part": 2,
    "regulation": 3,
    "rule": 3,
    "article": 3,
    "section": 3,
    "numbered": 3,
}
_STAMP_LINE = re.compile(r"^Delivered by Base to:", re.IGNORECASE)
_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-/()]+[a-z0-9]+)*\)?")


class IndexNotReadyError(ValueError):
    """The vector index has not been built, so search cannot run."""


@dataclass(frozen=True)
class DocumentChunk:
    """A searchable piece of a PDF with enough information to cite it."""

    chunk_id: str
    text: str
    filename: str
    page: int
    page_end: int
    section: str
    regulation: str
    document: str
    edition: str
    status: str

    @property
    def search_text(self) -> str:
        """Text plus its source, so a passage can match on what it belongs to."""
        return search_text(self.regulation, self.document, self.section, self.text)


def search_text(regulation: str, document: str, section: str, text: str) -> str:
    return f"{regulation} | {document} | {section}\n{text}"


def load_catalog(regulations_dir: Path = REGULATIONS_DIR) -> dict[str, dict]:
    path = regulations_dir / CATALOG_NAME
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.replace(" ", " ")).strip()


def _is_contents_page(lines: list[str]) -> bool:
    """Contents pages repeat every heading and would mislabel the real sections."""
    if sum(1 for line in lines if re.search(r"\.{4,}", line)) >= 5:
        return True
    entries = sum(
        1
        for line in lines
        if re.search(r"[A-Za-z]{3,}.*\s\d{1,3}$", line) or _heading_of(line) is not None
    )
    return len(lines) >= 8 and entries / len(lines) >= 0.5


def _heading_of(line: str) -> tuple[str, str] | None:
    """Return (kind, label) when a line is a section heading."""
    if len(line) > 110:
        return None
    if match := _RESOLUTION_HEADING.match(line):
        return "resolution", f"Resolution {match['id']}"
    if match := _NAMED_HEADING.match(line):
        title = (match["title"] or "").strip()
        if title and re.search(r"\d$", title):
            return None
        kind = match["kind"].lower()
        label = f"{kind.capitalize()} {match['id']}"
        return kind, f"{label} {title}".strip()
    if match := _NUMBERED_HEADING.match(line):
        return "numbered", f"{match['id']} {match['title'].strip()}"
    return None


def _boilerplate_lines(pages: list[list[str]]) -> set[str]:
    """Find running headers and footers: edge lines repeated across many pages."""
    if len(pages) < 5:
        return set()
    counts: Counter[str] = Counter()
    for lines in pages:
        edges = set(lines[:3] + lines[-2:])
        counts.update(re.sub(r"\d+", "#", line) for line in edges)
    threshold = max(3, int(len(pages) * 0.03))
    return {line for line, count in counts.items() if count >= threshold}


def _split_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text on word boundaries while preserving a small context overlap."""
    if size <= overlap:
        raise ValueError("Chunk size must be greater than chunk overlap.")

    words = text.split()
    chunks: list[str] = []
    start = 0
    while start < len(words):
        current: list[str] = []
        length = 0
        index = start
        while index < len(words):
            word = words[index]
            added_length = len(word) + (1 if current else 0)
            if current and length + added_length > size:
                break
            current.append(word)
            length += added_length
            index += 1
        chunks.append(" ".join(current))
        if index >= len(words):
            break

        overlap_length = 0
        next_start = index
        while next_start > start and overlap_length < overlap:
            next_start -= 1
            overlap_length += len(words[next_start]) + 1
        start = next_start
    return chunks


def _read_pdf_lines(pdf_path: Path) -> list[list[str]]:
    import pypdfium2

    document = pypdfium2.PdfDocument(str(pdf_path))
    try:
        pages: list[list[str]] = []
        for index in range(len(document)):
            page = document[index]
            textpage = page.get_textpage()
            cleaned = (_clean_line(line) for line in textpage.get_text_bounded().splitlines())
            pages.append([line for line in cleaned if line and not _STAMP_LINE.match(line)])
            textpage.close()
            page.close()
        return pages
    finally:
        document.close()


def chunks_from_pages(
    pages: list[list[str]], filename: str, source: dict | None = None
) -> list[DocumentChunk]:
    """Turn page lines into citeable chunks that follow the document's structure.

    Chunks may cross a page boundary, so a requirement split over two pages stays
    together, and they break at section headings so each one has one correct label.
    """
    source = source or {}
    metadata = {
        "regulation": source.get("regulation", Path(filename).stem),
        "document": source.get("document", Path(filename).stem),
        "edition": source.get("edition", "unknown"),
        "status": source.get("status", "unclassified"),
    }
    boilerplate = _boilerplate_lines(pages)
    active: dict[int, str] = {}
    chunks: list[DocumentChunk] = []
    buffer: list[tuple[str, int]] = []
    buffer_section = ""
    has_body = False

    def current_section() -> str:
        return " > ".join(active[level] for level in sorted(active)) or "Unsectioned"

    def flush(keep_overlap: bool) -> None:
        nonlocal buffer, has_body
        if not buffer:
            return
        text = "\n".join(line for line, _ in buffer)
        pieces = _split_text(text) if len(text) > CHUNK_SIZE else [text]
        for piece in pieces:
            first_page, last_page = buffer[0][1], buffer[-1][1]
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{filename}:p{first_page}:c{len(chunks) + 1}",
                    text=piece,
                    filename=filename,
                    page=first_page,
                    page_end=last_page,
                    section=buffer_section,
                    **metadata,
                )
            )
        kept: list[tuple[str, int]] = []
        if keep_overlap:
            length = 0
            for line, page in reversed(buffer):
                if length + len(line) > CHUNK_OVERLAP:
                    break
                kept.insert(0, (line, page))
                length += len(line) + 1
        buffer = kept
        has_body = False

    for page_number, lines in enumerate(pages, start=1):
        if _is_contents_page(lines):
            continue
        previous = ""
        for line in lines:
            # A long line with no closing punctuation wraps onto this one, so
            # "see\nChapter 4" is a sentence and not a new section.
            wrapped = len(previous) >= 60 and previous[-1] not in ".:;!?)"
            heading = None if wrapped else _heading_of(line)
            previous = line
            is_boilerplate = re.sub(r"\d+", "#", line) in boilerplate
            if heading is not None:
                kind, label = heading
                level = _LEVELS[kind]
                # A running header repeats its heading, which must not reset the
                # lower levels: the section really continues on this page.
                if active.get(level) != label:
                    buffered = sum(len(item) + 1 for item, _ in buffer)
                    if has_body and buffered >= MIN_CHUNK_BEFORE_SECTION_BREAK:
                        flush(keep_overlap=False)
                    for lower in [item for item in active if item > level]:
                        del active[lower]
                    active[level] = label
                    # Too little text to stand alone, so it joins the new section.
                    if buffer:
                        buffer_section = current_section()
            if is_boilerplate or (line.isdigit() and len(line) <= 4):
                continue
            if not buffer:
                buffer_section = current_section()
            if sum(len(item) + 1 for item, _ in buffer) + len(line) > CHUNK_SIZE and has_body:
                flush(keep_overlap=True)
                if not buffer:
                    buffer_section = current_section()
            buffer.append((line, page_number))
            if heading is None:
                has_body = True
    flush(keep_overlap=False)
    return chunks


def extract_pdf_chunks(pdf_path: Path, source: dict | None = None) -> list[DocumentChunk]:
    """Extract citeable chunks from a PDF.

    OCR is intentionally not included. A PDF with no extractable text raises a
    clear error so a scanned document cannot enter the index as empty evidence.
    """
    chunks = chunks_from_pages(_read_pdf_lines(pdf_path), pdf_path.name, source)
    if not chunks:
        raise ValueError(
            f"{pdf_path.name} contains no selectable text. "
            "Scanned PDFs require OCR before ingestion."
        )
    return chunks


def all_pdf_chunks(regulations_dir: Path = REGULATIONS_DIR) -> list[DocumentChunk]:
    """Extract chunks from every PDF in the regulations directory."""
    pdf_paths = sorted(regulations_dir.glob("*.pdf"))
    if not pdf_paths:
        raise FileNotFoundError(f"No PDF files found in {regulations_dir}.")

    catalog = load_catalog(regulations_dir)
    chunks: list[DocumentChunk] = []
    for pdf_path in pdf_paths:
        chunks.extend(extract_pdf_chunks(pdf_path, catalog.get(pdf_path.name)))
    return chunks


def tokenize(text: str) -> list[str]:
    """Keep identifiers like 403.5.1 or msc.532(107) whole, and also their parts."""
    tokens: list[str] = []
    for token in _TOKEN.findall(text.lower()):
        tokens.append(token)
        parts = re.findall(r"[a-z0-9]+", token)
        if len(parts) > 1:
            tokens.extend(parts)
    return tokens


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = RRF_K) -> list[str]:
    """Merge rankings by position, since vector and keyword scores are not comparable."""
    scores: Counter[str] = Counter()
    for ranking in rankings:
        for position, item in enumerate(ranking):
            scores[item] += 1 / (k + position + 1)
    return [item for item, _ in sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))]


def load_embedder():
    from .onnx_models import OnnxEmbedder

    return OnnxEmbedder(EMBEDDING_MODEL, EMBEDDING_ONNX_FILE, EMBEDDING_MAX_TOKENS)


def load_reranker():
    from .onnx_models import OnnxCrossEncoder

    return OnnxCrossEncoder(RERANKER_MODEL, RERANKER_ONNX_FILE, RERANKER_MAX_TOKENS)


def normalize_quote(text: str) -> str:
    """Compare quotes regardless of line breaks, spacing, case, dashes and curly quotes."""
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


class RegulatoryRetriever:
    """Vector and keyword search merged together, then reranked by a CrossEncoder."""

    def __init__(self, vector_db_dir: Path = VECTOR_DB_DIR):
        import chromadb
        from rank_bm25 import BM25Okapi

        client = chromadb.PersistentClient(path=str(vector_db_dir))
        try:
            self._collection = client.get_collection(COLLECTION_NAME)
        except Exception as error:
            raise IndexNotReadyError(
                "The regulatory index is not ready. Run 'python rebuild_rag.py'."
            ) from error

        stored = self._collection.get(include=["documents", "metadatas"])
        if not stored["ids"]:
            raise IndexNotReadyError(
                "The regulatory index is empty. Run 'python rebuild_rag.py'."
            )
        self._ids: list[str] = stored["ids"]
        self._records = {
            chunk_id: {"text": text, **metadata}
            for chunk_id, text, metadata in zip(
                stored["ids"], stored["documents"], stored["metadatas"]
            )
        }
        self._by_file: dict[str, list[str]] = {}
        for chunk_id in self._ids:
            self._by_file.setdefault(self._records[chunk_id]["filename"], []).append(chunk_id)
        self._bm25 = BM25Okapi([tokenize(self._search_text(item)) for item in self._ids])
        self._embedding_model = load_embedder()
        self._reranker = load_reranker()
        self._cache: dict[tuple[str, int], list[dict]] = {}

    def _search_text(self, chunk_id: str) -> str:
        record = self._records[chunk_id]
        return search_text(
            record["regulation"], record["document"], record["section"], record["text"]
        )

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Return the most relevant chunks with source metadata and scores."""
        if not query.strip():
            raise ValueError("Search query cannot be empty.")
        if top_k < 1 or top_k > 50:
            raise ValueError("top_k must be between 1 and 50.")

        key = (query.strip(), top_k)
        if key not in self._cache:
            if len(self._cache) >= SEARCH_CACHE_SIZE:
                del self._cache[next(iter(self._cache))]
            self._cache[key] = self._search(query, top_k)
        return [dict(result) for result in self._cache[key]]

    def find_passage(self, filename: str, page: int, quote: str) -> dict | None:
        """Return the indexed chunk of `filename` covering `page` that contains `quote`.

        Citation checks need an exact lookup, not a relevance ranking: the right
        chunk must not be missed because other passages scored higher.
        """
        wanted = normalize_quote(quote)
        if not wanted:
            return None
        on_page = [
            chunk_id
            for chunk_id in self._by_file.get(filename, [])
            if self._records[chunk_id]["page"]
            <= page
            <= self._records[chunk_id].get("page_end", self._records[chunk_id]["page"])
        ]
        for chunk_id in on_page:
            if wanted in normalize_quote(self._records[chunk_id]["text"]):
                return {**self._records[chunk_id], "chunk_id": chunk_id}
        return None

    def _search(self, query: str, top_k: int) -> list[dict]:
        pool = min(CANDIDATES_PER_METHOD, len(self._ids))
        query_embedding = self._embedding_model.encode([query])[0].tolist()
        vector = self._collection.query(
            query_embeddings=[query_embedding], n_results=pool, include=["distances"]
        )
        vector_ids = vector["ids"][0]
        vector_scores = {
            chunk_id: round(1 - distance, 4)
            for chunk_id, distance in zip(vector_ids, vector["distances"][0])
        }

        bm25_scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(range(len(self._ids)), key=lambda index: -bm25_scores[index])
        keyword_ids = [self._ids[index] for index in ranked[:pool] if bm25_scores[index] > 0]

        merged = reciprocal_rank_fusion([vector_ids, keyword_ids])
        candidate_ids = merged[: max(RERANK_POOL, top_k)]
        rerank_scores = self._reranker.predict(
            [(query, self._search_text(chunk_id)) for chunk_id in candidate_ids]
        )
        results = [
            {
                **self._records[chunk_id],
                "chunk_id": chunk_id,
                "vector_score": vector_scores.get(chunk_id),
                "rerank_score": round(score, 4),
            }
            for chunk_id, score in zip(candidate_ids, rerank_scores)
        ]
        results.sort(key=lambda result: result["rerank_score"], reverse=True)
        return results[:top_k]


def rebuild_index(
    regulations_dir: Path = REGULATIONS_DIR,
    vector_db_dir: Path = VECTOR_DB_DIR,
) -> int:
    """Delete and rebuild the Chroma collection from the current PDF files."""
    import chromadb

    chunks = all_pdf_chunks(regulations_dir)
    embedding_model = load_embedder()
    vector_db_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(vector_db_dir))
    collection_names = {
        collection.name if hasattr(collection, "name") else collection
        for collection in client.list_collections()
    }
    if COLLECTION_NAME in collection_names:
        client.delete_collection(COLLECTION_NAME)
    collection = client.create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )
    batch_size = 1000
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        embeddings = embedding_model.encode([chunk.search_text for chunk in batch]).tolist()
        collection.add(
            ids=[chunk.chunk_id for chunk in batch],
            documents=[chunk.text for chunk in batch],
            embeddings=embeddings,
            metadatas=[
                {
                    "filename": chunk.filename,
                    "page": chunk.page,
                    "page_end": chunk.page_end,
                    "section": chunk.section,
                    "regulation": chunk.regulation,
                    "document": chunk.document,
                    "edition": chunk.edition,
                    "status": chunk.status,
                }
                for chunk in batch
            ],
        )
    return len(chunks)
