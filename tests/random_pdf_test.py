"""Search for random passages from the PDFs and check the source page comes back.

Run from the project root after building the index:
    python tests/random_pdf_test.py            30 random passages
    python tests/random_pdf_test.py 50         50 random passages
    python tests/random_pdf_test.py 50 7       50 passages, repeatable with seed 7

The query is copied from the PDF, so this is easier than a real question. It
shows whether text was indexed and can be found, not whether paraphrases work.
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from backend.rag import RegulatoryRetriever, all_pdf_chunks  # noqa: E402

QUERY_LENGTH = 150
TOP_K = 5


def random_passage(text: str, rng: random.Random) -> str:
    """Take a stretch of whole words from somewhere inside the chunk."""
    words = text.split()
    start = rng.randrange(max(1, len(words) - 25))
    return " ".join(words[start:])[:QUERY_LENGTH].rsplit(" ", 1)[0]


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else random.randrange(100_000)
    rng = random.Random(seed)

    chunks = [chunk for chunk in all_pdf_chunks() if len(chunk.text) >= QUERY_LENGTH]
    retriever = RegulatoryRetriever()
    print(f"Seed {seed}. Searching for {count} random passages.\n")

    ranks: list[int | None] = []
    for chunk in rng.sample(chunks, min(count, len(chunks))):
        query = random_passage(chunk.text, rng)
        results = retriever.search(query, top_k=TOP_K)
        rank = next(
            (
                position
                for position, result in enumerate(results, start=1)
                if result["filename"] == chunk.filename
                and result["page"] <= chunk.page_end
                and result["page_end"] >= chunk.page
            ),
            None,
        )
        ranks.append(rank)
        label = f"#{rank}" if rank else "MISS"
        print(f"{label:>5}  {chunk.filename[:30]:<30} p{chunk.page:<4} {query[:60]!r}")
        if rank is None:
            top = results[0]
            print(f"       top result: {top['filename'][:30]} p{top['page']}: {top['text'][:60]!r}")

    total = len(ranks)
    first = sum(1 for rank in ranks if rank == 1)
    found = sum(1 for rank in ranks if rank is not None)
    print(f"\nFirst result: {first}/{total} = {first / total:.0%}")
    print(f"Top {TOP_K}:        {found}/{total} = {found / total:.0%}")


if __name__ == "__main__":
    main()
