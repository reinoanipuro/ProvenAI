"""Rebuild the local regulatory vector index from data/regulations/*.pdf."""

from backend.rag import rebuild_index


if __name__ == "__main__":
    count = rebuild_index()
    print(f"Indexed {count} chunks.")
