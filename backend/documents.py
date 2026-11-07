"""Read dropped design documents: text files, PDFs, Word files and 2D pictures.

Text is extracted here. Pictures, and PDF pages without a text layer such as
scanned drawings, are stored and listed as waiting for 2D reading, which is a
later step: read_picture() is the place to add it. The local model
(ministral-3:8b) supports images, so that step needs no new model.
"""

import io
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DIR = ROOT / ".runtime" / "uploads"
TEXT_TYPES = {".txt", ".md", ".csv"}
PICTURE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
SUPPORTED_TYPES = TEXT_TYPES | PICTURE_TYPES | {".pdf", ".docx"}
MAX_FILES = 10
MAX_FILE_BYTES = 25 * 1024 * 1024
# Fewer characters than this on a PDF page means it is a picture, such as a drawing.
MIN_PAGE_TEXT = 40
# A label this short before a value, like "Clear width:", needs the line above for its element.
SHORT_LABEL = 30
# A ratio like 1:50 or steeper denominators is a drawing scale, not a slope (slopes are about 1:8 to 1:20).
MIN_SCALE_DENOMINATOR = 50
_SPLIT_SQUARE_METRE = re.compile(r"(\d)\s*m\s*\n\s*2(?!\d)")
# A value with a unit or a ratio, such as "800 mm", "1:12" or "92 %".
# "%" and "°" are not word characters, so they must not be followed by \b.
_MEASUREMENT = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:(?:mm|cm|m|in|inch|inches|ft|feet|percent|deg|degrees)\b|%|°)"
    r"|\b\d+\s*:\s*\d+\b",
    re.IGNORECASE,
)
_WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass
class Page:
    number: int | None
    text: str


@dataclass
class Picture:
    page: int | None
    stored_as: str
    status: str = "waiting for 2D reading (not available yet)"


@dataclass
class Document:
    filename: str
    kind: str
    pages: list[Page] = field(default_factory=list)
    pictures: list[Picture] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def text_characters(self) -> int:
        return sum(len(page.text) for page in self.pages)


def safe_name(filename: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename or "file").name).strip("._")
    return name[:120] or "file"


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _docx_text(data: bytes) -> str:
    """Paragraph and table text from a .docx file, without extra libraries."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    paragraphs = []
    for paragraph in root.iter(f"{_WORD_NAMESPACE}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{_WORD_NAMESPACE}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def _store(folder: Path, name: str, data: bytes) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)
    # Stored as "<upload id>/<file name>" inside UPLOAD_DIR.
    return f"{folder.name}/{name}"


def read_document(filename: str, data: bytes, folder: Path) -> Document:
    """Extract text from one file, and store pictures for later 2D reading."""
    name = safe_name(filename)
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_TYPES:
        document = Document(name, "unsupported")
        document.warnings.append(
            f"{name}: this file type is not supported. Use {', '.join(sorted(SUPPORTED_TYPES))}."
        )
        return document

    if suffix in TEXT_TYPES:
        return Document(name, "text", pages=[Page(None, _decode(data))])

    if suffix == ".docx":
        try:
            return Document(name, "word", pages=[Page(None, _docx_text(data))])
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
            document = Document(name, "word")
            document.warnings.append(f"{name}: could not read this Word file.")
            return document

    if suffix in PICTURE_TYPES:
        document = Document(name, "picture")
        document.pictures.append(Picture(None, _store(folder, name, data)))
        return document

    return _read_pdf(name, data, folder)


def _read_pdf(name: str, data: bytes, folder: Path) -> Document:
    import pypdfium2

    document = Document(name, "pdf")
    try:
        pdf = pypdfium2.PdfDocument(data)
    except pypdfium2.PdfiumError:
        document.warnings.append(f"{name}: could not open this PDF.")
        return document
    try:
        stored = None
        for index in range(len(pdf)):
            page = pdf[index]
            textpage = page.get_textpage()
            text = re.sub(r"[\x02­]\s*", "", textpage.get_text_bounded())
            textpage.close()
            page.close()
            if len(text.strip()) >= MIN_PAGE_TEXT:
                document.pages.append(Page(index + 1, text))
            else:
                stored = stored or _store(folder, name, data)
                document.pictures.append(Picture(index + 1, stored))
    finally:
        pdf.close()
    if document.pictures:
        document.warnings.append(
            f"{name}: {len(document.pictures)} page(s) have no text, such as drawings or scans. "
            "They are stored for 2D reading, which is not available yet."
        )
    return document


def read_picture(picture: Picture) -> str:
    """The place for 2D reading of drawings and pictures. Not available yet."""
    raise NotImplementedError("2D picture reading is a later step.")


def measurement_lines(document: Document) -> list[tuple[str, int | None]]:
    """Lines that state a value with a unit, each with the line before it.

    Only these go to Mistral: a long document would not fit its context or
    would take many minutes. The line before usually names the element, as in
    a heading followed by "Clear width: 800 mm".
    """
    lines: list[tuple[str, int | None]] = []
    for page in document.pages:
        # Drawings often put the "2" of "m²" on the next line: "GALLEY 30 m" / "2".
        # Joined into "m²", an area is no longer mistaken for a length.
        text = _SPLIT_SQUARE_METRE.sub(r"\1 m²", page.text)
        page_lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index, line in enumerate(page_lines):
            value = _first_measurement(line)
            if value or line.endswith("?"):
                previous = page_lines[index - 1] if index else ""
                # Only a short label such as "Clear width: 800 mm" needs the line
                # before it; a line that names its element stays on its own.
                label = line[: value.start()] if value else line
                needs_context = len(label.strip(" :-|")) <= SHORT_LABEL
                if needs_context and previous and not _first_measurement(previous):
                    line = f"{previous} | {line}"
                lines.append((line[:400], page.number))
    return lines


def _first_measurement(line: str) -> re.Match | None:
    """The first real measurement in a line, skipping drawing scales such as 1:150."""
    for match in _MEASUREMENT.finditer(line):
        ratio = re.fullmatch(r"\s*\d+\s*:\s*(\d+)\s*", match.group(0))
        if ratio and int(ratio.group(1)) >= MIN_SCALE_DENOMINATOR:
            continue
        return match
    return None


def new_upload_folder() -> tuple[str, Path]:
    upload_id = uuid.uuid4().hex[:12]
    return upload_id, UPLOAD_DIR / upload_id
