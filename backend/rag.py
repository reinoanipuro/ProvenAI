"""Regulatory RAG: index regulation clauses in ChromaDB and verify rules against them.

Retrieval returns verbatim text. Nothing here generates or paraphrases regulations.
"""

from pathlib import Path

import chromadb
from chromadb.config import Settings

from .config import MIN_RELEVANCE, RETRIEVAL_TOP_K
from .documents import parse_document
from .schemas import Passage, Rule, RuleEvidence

_COLLECTION = "regulations"


def _clauses(path: Path) -> list[dict]:
    """Split a regulation into one chunk per numbered section."""
    document = parse_document(path.name, path.read_text(encoding="utf-8"))
    chunks: dict[str, dict] = {}
    for line in document.lines:
        chunk = chunks.setdefault(
            line.section, {"section": line.section, "page": line.page, "lines": []}
        )
        chunk["lines"].append(line.text)
    return [
        {
            "file": path.name,
            "clause": chunk["section"].split(" ", 1)[0],
            "title": chunk["section"],
            "page": chunk["page"],
            "text": " ".join(chunk["lines"]),
        }
        for chunk in chunks.values()
    ]


class RegulatoryIndex:
    def __init__(self, chroma_dir: Path, regulations_dir: Path):
        client = chromadb.PersistentClient(
            path=str(chroma_dir), settings=Settings(anonymized_telemetry=False)
        )
        # Rebuild on start so the index can never drift from the source files.
        if any(c.name == _COLLECTION for c in client.list_collections()):
            client.delete_collection(_COLLECTION)
        self._collection = client.create_collection(
            _COLLECTION, metadata={"hnsw:space": "cosine"}
        )
        clauses = [c for path in sorted(regulations_dir.glob("*.md")) for c in _clauses(path)]
        self._collection.add(
            ids=[f"{c['file']}::{c['clause']}" for c in clauses],
            documents=[f"{c['title']}. {c['text']}" for c in clauses],
            metadatas=clauses,
        )

    def search(self, query: str, top_k: int = RETRIEVAL_TOP_K) -> list[Passage]:
        result = self._collection.query(query_texts=[query], n_results=top_k)
        return [
            Passage(
                file=meta["file"],
                clause=meta["clause"],
                title=meta["title"],
                page=meta["page"],
                text=meta["text"],
                relevance=round(1 - distance, 3),
            )
            for meta, distance in zip(result["metadatas"][0], result["distances"][0])
        ]

    def verify_rule(self, rule: Rule) -> RuleEvidence:
        """Confirm that the current regulation text still supports the rule."""
        passages = self.search(rule.query)
        match = next(
            (p for p in passages if p.file == rule.regulation_file and p.clause == rule.clause),
            None,
        )
        if match is None:
            return RuleEvidence(
                verified=False,
                note=f"Clause {rule.clause} was not among the top retrieved passages.",
            )
        if match.relevance < MIN_RELEVANCE:
            return RuleEvidence(
                verified=False,
                passage=match,
                note=f"Retrieval relevance {match.relevance:.2f} is below {MIN_RELEVANCE:.2f}.",
            )
        if rule.threshold_quote not in match.text:
            return RuleEvidence(
                verified=False,
                passage=match,
                note=(
                    f"Clause {rule.clause} no longer contains the approved wording "
                    f"'{rule.threshold_quote}'. The rule needs human review."
                ),
            )
        return RuleEvidence(
            verified=True,
            passage=match,
            note=f"Clause {rule.clause} retrieved and contains '{rule.threshold_quote}'.",
        )
