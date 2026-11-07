from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import api, documents
from backend.documents import measurement_lines, read_document

SAMPLES = Path("data/samples/designs")
REGULATIONS = Path("data/regulations")


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    return tmp_path


def test_text_file_values_keep_their_element_line(tmp_path):
    document = read_document("deck5.txt", (SAMPLES / "deck5_accessibility.txt").read_bytes(), tmp_path)
    lines = [line for line, _ in measurement_lines(document)]

    assert document.kind == "text"
    assert "Passenger corridor, frame 40 to 80 | Clear width: 800 mm" in lines
    assert any("1:10" in line for line in lines)


def test_word_file_is_read(tmp_path):
    document = read_document("notes.docx", (SAMPLES / "open_deck_notes.docx").read_bytes(), tmp_path)

    assert document.kind == "word"
    assert any("sill height 300 mm" in line for line, _ in measurement_lines(document))


def test_pdf_text_pages_are_read_with_page_numbers(tmp_path):
    pdf = REGULATIONS / "QF520E_supplement_January2026.pdf"
    document = read_document(pdf.name, pdf.read_bytes(), tmp_path)

    assert document.kind == "pdf"
    assert document.pages and document.pages[0].number == 1
    assert not document.pictures


def test_pictures_are_read_with_ocr_and_values_can_be_marked(tmp_path, monkeypatch):
    import io

    from PIL import Image

    from backend import lovable, ocr

    lines = [ocr.Line("Corridor 5-12", (0.1, 0.1, 0.5, 0.2)), ocr.Line("Clear width: 800 mm", (0.1, 0.3, 0.6, 0.4))]
    monkeypatch.setattr(ocr, "read_lines", lambda image: lines)
    picture = io.BytesIO()
    Image.new("RGB", (1000, 500), "white").save(picture, format="PNG")

    document = read_document("deck plan.png", picture.getvalue(), tmp_path)

    assert document.kind == "picture" and document.pictures[0].status == "read with OCR"
    assert document.pages[0].text == "Corridor 5-12\nClear width: 800 mm"
    assert measurement_lines(document) == [("Corridor 5-12 | Clear width: 800 mm", 1)]
    # The red mark goes where OCR found the line: pixels from the bottom left, with a small margin.
    x0, y0, x1, y1 = lovable._locate(tmp_path, "deck_plan.png", 1, ["Clear width: 800 mm"])
    assert (round(x0), round(y0), round(x1), round(y1)) == (94, 294, 606, 356)


def test_a_file_that_is_not_a_picture_is_reported(tmp_path):
    document = read_document("deck plan.png", b"\x89PNG fake picture", tmp_path)

    assert document.kind == "picture" and not document.pages
    assert "could not open this picture" in document.warnings[0]


def test_unsupported_and_unsafe_names_are_handled(tmp_path):
    document = read_document("../../evil.exe", b"MZ", tmp_path)

    assert document.kind == "unsupported"
    assert document.filename == "evil.exe"
    assert not any(tmp_path.iterdir())


class FakeLLM:
    def chat_json(self, system, user, schema, max_tokens=400):
        if "Clear width: 800 mm" in user:
            return {"items": [{
                "element": "Passenger corridor", "property": "clear width",
                "attribute": "walking_route_clear_width", "value_text": "800 mm", "search_query": "",
            }, {
                "element": "Passenger corridor", "property": "clear width",
                "attribute": "walking_route_clear_width", "value_text": "750 mm", "search_query": "",
            }]}
        return {"items": []}


def test_upload_returns_items_with_their_source(upload_dir, monkeypatch):
    monkeypatch.setattr(api, "llm", FakeLLM())
    client = TestClient(api.app)
    files = [
        ("files", ("deck5.txt", (SAMPLES / "deck5_accessibility.txt").read_bytes(), "text/plain")),
        ("files", ("plan.png", b"\x89PNG fake picture", "image/png")),
    ]
    response = client.post("/upload", files=files)
    body = response.json()

    assert response.status_code == 200
    assert body["items"][0]["value_text"] == "800 mm"
    assert body["items"][0]["source"] == "deck5.txt"
    # Mistral invented 750 mm: it is not in the document, so the value is dropped.
    assert all(item["value_text"] != "750 mm" for item in body["items"])
    # Not a real picture: it is reported, and the text file is still read.
    assert any("could not open this picture" in warning for warning in body["warnings"])


def test_upload_rejects_too_many_files(upload_dir):
    client = TestClient(api.app)
    files = [("files", (f"f{number}.txt", b"x", "text/plain")) for number in range(11)]

    assert client.post("/upload", files=files).status_code == 422


def test_lines_that_name_their_element_stay_on_their_own(tmp_path):
    document = read_document("notes.docx", (SAMPLES / "open_deck_notes.docx").read_bytes(), tmp_path)
    lines = [line for line, _ in measurement_lines(document)]

    assert "Superstructure end bulkhead door, frame 120: sill height 300 mm" in lines
    assert "Ballast water exchange system: volumetric efficiency 92 %" in lines


def test_drawing_areas_and_scales_are_not_read_as_lengths_or_slopes(tmp_path):
    text = "GALLEY\n30 m\n2\nLIBRARY 48 m2\nMPS TRA 1:150 1 1\nRamp slope 1:12\nBREADTH MLD : 16,00 m\n"
    document = read_document("ga.txt", text.encode(), tmp_path)
    lines = [line for line, _ in measurement_lines(document)]

    # Only the slope and the breadth are measurements; the areas and the scale are not.
    assert len(lines) == 2
    assert lines[0].endswith("Ramp slope 1:12")
    assert lines[1] == "BREADTH MLD : 16,00 m"


def test_cut_off_answers_are_read_again_in_halves():
    from backend.intake import _read_part
    from backend.llm import LLMBadOutputError
    from backend.rules import load_library

    class CutOffLLM:
        def chat_json(self, system, user, schema, max_tokens=400):
            lines = [line for line in user.splitlines()[1:] if line.strip()]
            if len(lines) > 1:
                raise LLMBadOutputError("Unterminated string")
            value = lines[0].split(": ")[-1]
            return {"items": [{"element": "x", "property": "y", "attribute": "unknown",
                               "value_text": value, "search_query": ""}]}

    warnings: list[str] = []
    text = "Corridor: 800 mm\nDoor: 850 mm\nRamp: 1:10\n"
    parts = _read_part(CutOffLLM(), text, load_library()[0], warnings)

    assert [found[0]["value_text"] for _, found in parts] == ["800 mm", "850 mm", "1:10"]
    assert not warnings


def test_ocr_keeps_each_label_with_the_line_below_it():
    from backend.ocr import Line, reading_order

    # Two labels side by side, as on a deck plan: top-to-bottom order would mix them.
    lines = [
        Line("Cabin 10045 door threshold", (0.05, 0.641, 0.21, 0.660)),
        Line("Cabin 10038 light switch", (0.64, 0.637, 0.79, 0.665)),
        Line("Raised threshold 8 mm", (0.05, 0.666, 0.18, 0.687)),
        Line("Mounting height: 1275 mm", (0.65, 0.666, 0.80, 0.690)),
    ]

    assert [line.text for line in reading_order(lines)] == [
        "Cabin 10038 light switch", "Mounting height: 1275 mm", "Cabin 10045 door threshold", "Raised threshold 8 mm",
    ]


def test_a_value_is_found_only_as_a_whole_number():
    from backend.intake import _has_value

    assert not _has_value("8 mm", "clear opening: 918 mm")
    assert _has_value("8 mm", "raised threshold 8 mm")
    assert _has_value("1:12", "running slope 1:12")
