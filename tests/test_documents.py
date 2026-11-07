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


def test_pictures_are_stored_for_later_2d_reading(tmp_path):
    document = read_document("deck plan.png", b"\x89PNG fake picture", tmp_path)

    assert document.kind == "picture"
    assert "2D reading" in document.pictures[0].status
    assert (tmp_path / "deck_plan.png").exists()


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
    assert body["documents"][1]["pictures"][0]["status"].startswith("waiting for 2D reading")


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
