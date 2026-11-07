"""Turn dropped design documents into design items, shared by every front end.

Text is read from the documents, only lines that state a value go to Mistral,
and every value Mistral returns must be in those lines. Each item names the
file and page it came from.
"""

import re
from pathlib import Path

from .checker import accept_items
from .documents import Document, measurement_lines, read_document
from .llm import LLMBadOutputError, parse_design

# Each Mistral call reads at most this much document text, and an upload is read
# in at most this many calls, so one upload takes a few minutes at most. Small
# parts keep Mistral's answer short enough not to be cut off.
CHUNK_CHARACTERS = 900
MAX_CHUNKS = 8


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _has_value(value: str, line: str) -> bool:
    """The value as a whole number in the line: "8 mm" is not in "918 mm"."""
    return re.search(rf"(?<![\d.,]){re.escape(value)}(?!\d)", line) is not None


def read_files(files: list[tuple[str, bytes]], folder: Path) -> tuple[list[Document], list[str]]:
    documents: list[Document] = []
    warnings: list[str] = []
    for filename, data in files:
        document = read_document(filename, data, folder)
        documents.append(document)
        warnings.extend(document.warnings)
    return documents, warnings


def _read_part(llm, text: str, attributes: dict, warnings: list[str], depth: int = 0) -> list[tuple[str, list[dict]]]:
    """Read one part; if Mistral's answer is cut off, read each half separately.

    A part that still fails is skipped with a warning, so one bad answer never
    stops the rest of the documents from being read.
    """
    try:
        return [(text, parse_design(llm, text, attributes))]
    except LLMBadOutputError:
        lines = text.splitlines()
        if len(lines) < 2 or depth >= 2:
            warnings.append(f"Mistral could not read these lines, so they were skipped: {text[:150]}")
            return []
        middle = len(lines) // 2
        halves = ["\n".join(lines[:middle]) + "\n", "\n".join(lines[middle:]) + "\n"]
        return [result for half in halves for result in _read_part(llm, half, attributes, warnings, depth + 1)]


def find_items(documents: list[Document], llm, attributes: dict) -> tuple[list[dict], list[str]]:
    """Ask Mistral for the design items in the documents' value lines.

    Each item gets "source" (file and page) and "source_file" and "source_page",
    so a front end can point to where the value was found.
    """
    lines: list[tuple[str, str, int | None]] = []
    for document in documents:
        for line, page in measurement_lines(document):
            lines.append((line, document.filename, page))

    warnings: list[str] = []
    chunks: list[str] = []
    current = ""
    for line, _, _ in lines:
        if current and len(current) + len(line) + 1 > CHUNK_CHARACTERS:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current:
        chunks.append(current)
    if len(chunks) > MAX_CHUNKS:
        warnings.append(
            f"Only the first {MAX_CHUNKS * CHUNK_CHARACTERS} characters of values were read, to keep "
            "the time reasonable. Split large documents or add items by hand."
        )
        chunks = chunks[:MAX_CHUNKS]
    if not lines and documents:
        warnings.append("No values with units were found in the text of these files.")

    items: list[dict] = []
    for chunk in chunks:
        for part, found in _read_part(llm, chunk, attributes, warnings):
            accepted, part_warnings = accept_items(found, part, attributes)
            items.extend(accepted)
            warnings.extend(part_warnings)

    for item in items:
        value = _normalize(item["value_text"])
        found = next(
            ((line, filename, page) for line, filename, page in lines if value and _has_value(value, _normalize(line))),
            None,
        )
        item["source_line"] = found[0] if found else ""
        match = found[1:] if found else None
        item["source_file"], item["source_page"] = match if match else ("", None)
        item["source"] = (
            f"{match[0]}, page {match[1]}" if match and match[1] else (match[0] if match else "")
        )
    return items, warnings
