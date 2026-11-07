from pathlib import Path

from backend.documents import measurement_lines, read_document

SAMPLES = Path("data/samples/designs")
REGULATIONS = Path("data/regulations")


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
    assert not document.pages_without_text


def test_pictures_are_not_supported(tmp_path):
    document = read_document("deck plan.png", b"PNG picture", tmp_path)

    assert document.kind == "unsupported" and not document.pages
    assert "not supported" in document.warnings[0]


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


def test_dropped_files_give_items_with_their_source(tmp_path):
    from backend.intake import find_items, read_files
    from backend.rules import load_library

    files = [("deck5.txt", (SAMPLES / "deck5_accessibility.txt").read_bytes()), ("plan.png", b"PNG picture")]
    documents, warnings = read_files(files, tmp_path)
    items, _ = find_items(documents, FakeLLM(), load_library()[0])

    assert items[0]["value_text"] == "800 mm" and items[0]["source_file"] == "deck5.txt"
    # Mistral invented 750 mm: it is not in the document, so the value is dropped.
    assert all(item["value_text"] != "750 mm" for item in items)
    # A picture is not supported: it is reported, and the text file is still read.
    assert any("plan.png: this file type is not supported" in warning for warning in warnings)


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


def test_a_value_is_found_only_as_a_whole_number():
    from backend.intake import _has_value

    assert not _has_value("8 mm", "clear opening: 918 mm")
    assert _has_value("8 mm", "raised threshold 8 mm")
    assert _has_value("1:12", "running slope 1:12")


def test_pdf_pages_without_text_are_reported(tmp_path):
    import io

    import pypdfium2

    pdf = pypdfium2.PdfDocument.new()
    pdf.new_page(595, 842)  # A blank page, like a scan: no text layer.
    data = io.BytesIO()
    pdf.save(data)

    document = read_document("scan.pdf", data.getvalue(), tmp_path)

    assert document.pages == [] and document.pages_without_text == [1]
    assert "page 1 has no text" in document.warnings[0]
