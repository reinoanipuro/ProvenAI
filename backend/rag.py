"""PDF ingestion and retrieval for the compliance document knowledge base."""

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent.parent
REGULATIONS_DIR = ROOT / "data" / "regulations"
VECTOR_DB_DIR = ROOT / ".runtime" / "chroma"
COLLECTION_NAME = "ship_compliance_documents"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 180


@dataclass(frozen=True)
class DocumentChunk:
    """A searchable piece of a PDF with enough information to cite it."""

    chunk_id: str
    text: str
    filename: str
    page: int
    section: str


def _section_for(text: str, current_section: str) -> str:
    """Use Markdown-like headings as sections when a PDF preserves them."""
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned.startswith(("#", "ARTICLE ", "CHAPTER ", "SECTION ")):
            return cleaned
    return current_section


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


def extract_pdf_chunks(pdf_path: Path) -> list[DocumentChunk]:
    """Extract text from a PDF and turn each page into citeable chunks.

    OCR is intentionally not included. A PDF with no extractable text raises a
    clear error so a scanned document cannot enter the index as empty evidence.
    """
    reader = PdfReader(str(pdf_path))
    chunks: list[DocumentChunk] = []
    section = "Unsectioned"

    for page_number, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if not page_text:
            continue
        section = _section_for(page_text, section)
        for chunk_number, text in enumerate(_split_text(page_text), start=1):
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{pdf_path.name}:p{page_number}:c{chunk_number}",
                    text=text,
                    filename=pdf_path.name,
                    page=page_number,
                    section=section,
                )
            )

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

    chunks: list[DocumentChunk] = []
    for pdf_path in pdf_paths:
        chunks.extend(extract_pdf_chunks(pdf_path))
    return chunks


class RegulatoryRetriever:
    """Chroma vector search followed by optional local CrossEncoder reranking."""

    def __init__(
        self,
        vector_db_dir: Path = VECTOR_DB_DIR,
        embedding_model: str = EMBEDDING_MODEL,
        reranker_model: str = RERANKER_MODEL,
    ):
        import chromadb
        from sentence_transformers import CrossEncoder, SentenceTransformer

        self._embedding_model = SentenceTransformer(embedding_model)
        self._reranker = CrossEncoder(reranker_model)
        client = chromadb.PersistentClient(path=str(vector_db_dir))
        self._collection = client.get_collection(COLLECTION_NAME)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Return the most relevant chunks with source metadata and scores."""
        if not query.strip():
            raise ValueError("Search query cannot be empty.")
        if top_k < 1 or top_k > 50:
            raise ValueError("top_k must be between 1 and 50.")

        candidate_count = min(max(top_k * 4, 10), 50)
        query_embedding = self._embedding_model.encode(query).tolist()
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=candidate_count,
            include=["documents", "metadatas", "distances"],
        )
        candidates = [
            {
                "text": text,
                "filename": metadata["filename"],
                "page": metadata["page"],
                "section": metadata["section"],
                "vector_score": round(1 - distance, 4),
            }
            for text, metadata, distance in zip(
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
            )
        ]

        rerank_scores = self._reranker.predict(
            [(query, candidate["text"]) for candidate in candidates]
        )
        for candidate, score in zip(candidates, rerank_scores):
            candidate["rerank_score"] = round(float(score), 4)
        return sorted(
            candidates, key=lambda candidate: candidate["rerank_score"], reverse=True
        )[:top_k]


def rebuild_index(
    regulations_dir: Path = REGULATIONS_DIR,
    vector_db_dir: Path = VECTOR_DB_DIR,
) -> int:
    """Delete and rebuild the Chroma collection from the current PDF files."""
    import chromadb
    from sentence_transformers import SentenceTransformer

    chunks = all_pdf_chunks(regulations_dir)
    embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    vector_db_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(vector_db_dir))
    collection_names = {
        collection.name if hasattr(collection, "name") else collection
        for collection in client.list_collections()
    }
    if COLLECTION_NAME in collection_names:
        client.delete_collection(COLLECTION_NAME)
    collection = client.create_collection(COLLECTION_NAME)
    texts = [chunk.text for chunk in chunks]
    embeddings = embedding_model.encode(texts).tolist()
    collection.add(
        ids=[chunk.chunk_id for chunk in chunks],
        documents=texts,
        embeddings=embeddings,
        metadatas=[
            {
                "filename": chunk.filename,
                "page": chunk.page,
                "section": chunk.section,
            }
            for chunk in chunks
        ],
    )
    return len(chunks)
