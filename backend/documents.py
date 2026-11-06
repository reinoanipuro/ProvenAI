"""Parse text documents into lines that know their page and section.

Page breaks are marked with `<!-- page: N -->`; sections are Markdown headings.
"""

import hashlib
import re
from dataclasses import dataclass

_PAGE = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")


@dataclass(frozen=True)
class Line:
    number: int
    page: int
    section: str
    text: str


@dataclass(frozen=True)
class ParsedDocument:
    filename: str
    sha256: str
    lines: list[Line]


def parse_document(filename: str, text: str) -> ParsedDocument:
    page, section = 1, "(no section)"
    lines: list[Line] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if match := _PAGE.fullmatch(stripped):
            page = int(match.group(1))
        elif match := _HEADING.match(stripped):
            section = match.group(1)
        elif stripped:
            lines.append(Line(number, page, section, stripped))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ParsedDocument(filename, digest, lines)
