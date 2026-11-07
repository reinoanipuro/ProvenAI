"""Read dropped design documents: text files, PDFs, Word files and 2D pictures.

Text is extracted here. Pictures, and PDF pages without a text layer such as
scanned drawings, are read with local OCR (backend/ocr.py). The position of
every OCR line is saved next to the file as "<file>.ocr.json", so a finding
can be marked where its value is printed.
"""

import io
import json
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
# Scanned PDF pages are rendered at this scale for OCR (2 = 144 dpi).
OCR_RENDER_SCALE = 2
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
    read_by: str = "text"


@dataclass
class Picture:
    page: int | None
    stored_as: str
    status: str = "read with OCR"


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
        stored = _store(folder, name, data)
        try:
            from PIL import Image

            image = Image.open(io.BytesIO(data))
            image.load()
        except Exception:  # noqa: BLE001 - any unreadable picture gets the same warning
            document.warnings.append(f"{name}: could not open this picture.")
            return document
        picture = Picture(1, stored)
        document.pictures.append(picture)
        _ocr_pages(document, folder, name, [(1, image)])
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
        scanned = []
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
                scanned.append((index + 1, pdf[index].render(scale=OCR_RENDER_SCALE).to_pil()))
    finally:
        pdf.close()
    if scanned:
        _ocr_pages(document, folder, name, scanned)
    return document


def _ocr_pages(document: Document, folder: Path, name: str, images: list[tuple[int, object]]) -> None:
    """Read pictures with OCR, and save where each line is for marking findings."""
    from .ocr import OCRUnavailableError, read_lines

    positions: dict[str, list] = {}
    for number, image in images:
        try:
            lines = read_lines(image)
        except OCRUnavailableError as error:
            document.warnings.append(f"{name}: page {number} is a picture and could not be read: {error}")
            for picture in document.pictures:
                picture.status = "not read: OCR unavailable"
            return
        positions[str(number)] = [[line.text, *line.box] for line in lines]
        document.pages.append(Page(number, "\n".join(line.text for line in lines), read_by="ocr"))
        if not lines:
            document.warnings.append(f"{name}: no text was found on page {number}.")
    document.pages.sort(key=lambda page: page.number or 0)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.ocr.json").write_text(json.dumps(positions), encoding="utf-8")


def ocr_positions(folder: Path, name: str) -> dict[str, list]:
    """OCR lines per page saved by _ocr_pages: {page: [[text, x0, y0, x1, y1], ...]}, or {}."""
    path = folder / f"{name}.ocr.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


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
