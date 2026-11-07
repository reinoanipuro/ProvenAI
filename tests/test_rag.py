from backend.rag import (
    RegulatoryRetriever,
    _heading_of,
    _split_text,
    chunks_from_pages,
    reciprocal_rank_fusion,
    tokenize,
)


def test_split_text_keeps_all_content():
    text = " ".join(f"word{i}" for i in range(500))
    chunks = _split_text(text, size=100, overlap=20)

    assert len(chunks) > 1
    assert chunks[0].startswith("word0")
    assert chunks[-1].endswith("word499")


def test_split_text_rejects_invalid_overlap():
    try:
        _split_text("text", size=10, overlap=10)
    except ValueError as error:
        assert "greater than" in str(error)
    else:
        raise AssertionError("Expected invalid chunk configuration to fail.")


def test_heading_detection_ignores_running_text():
    assert _heading_of("Regulation D-2") == ("regulation", "Regulation D-2")
    assert _heading_of("403.5.1 Clear Width. Except as provided")[0] == "numbered"
    assert _heading_of("V1004.2.5.3.2 Handrail Height. Top of")[0] == "numbered"
    assert _heading_of("section 4 of the Convention") is None
    assert _heading_of("2010 Standards for State and Local") is None
    assert _heading_of("resolution MSC.338(91) and regulations") is None


def test_chunks_follow_sections_across_pages():
    pages = [
        ["Rule 1", "First requirement that continues on the next page and"],
        ["ends here with enough wording to be useful.", "Rule 2", "Second requirement."],
    ]
    chunks = chunks_from_pages(pages, "doc.pdf", {"regulation": "COLREG"})

    assert chunks[0].regulation == "COLREG"
    assert (chunks[0].page, chunks[0].page_end) == (1, 2)
    assert chunks[0].section.startswith("Rule")
    assert chunks[-1].section == "Rule 2"


def test_running_header_does_not_reset_the_section():
    long_line = "Requirement text that is long enough to count as a body line here."
    pages = [
        ["Chapter 4", "401 General", long_line],
        ["Chapter 4", long_line],
    ]
    chunks = chunks_from_pages(pages, "doc.pdf")

    assert all(chunk.section == "Chapter 4 > 401 General" for chunk in chunks)


def test_contents_pages_are_not_indexed():
    contents = [f"Rule {number} Conduct of vessels {number}" for number in range(10, 20)]
    body = ["Rule 1", "The real requirement text."]

    chunks = chunks_from_pages([contents, body], "doc.pdf")

    assert [chunk.page for chunk in chunks] == [2]


def test_tokenize_keeps_identifiers_and_their_parts():
    tokens = tokenize("See MSC.532(107) and 403.5.1")

    assert "msc.532(107)" in tokens
    assert "403.5.1" in tokens
    assert "532" in tokens


def test_rank_fusion_prefers_items_found_by_both_methods():
    assert reciprocal_rank_fusion([["a", "b"], ["c", "b"]])[0] == "b"


def _retriever_with(records: dict[str, dict]) -> RegulatoryRetriever:
    retriever = object.__new__(RegulatoryRetriever)
    retriever._records = records
    retriever._by_file = {}
    for chunk_id, record in records.items():
        retriever._by_file.setdefault(record["filename"], []).append(chunk_id)
    return retriever


def test_find_passage_matches_quote_on_the_cited_page_only():
    text = "The clear width of walking\nsurfaces shall be 36 inches (915 mm) minimum."
    retriever = _retriever_with({
        "a": {"filename": "ada.pdf", "page": 120, "page_end": 121, "text": text},
        "b": {"filename": "pvag.pdf", "page": 121, "page_end": 121, "text": text},
    })
    quote = "the clear width of walking surfaces shall be 36 inches (915 mm) minimum."

    assert retriever.find_passage("ada.pdf", 121, quote)["chunk_id"] == "a"
    assert retriever.find_passage("ada.pdf", 119, quote) is None
    assert retriever.find_passage("ada.pdf", 121, "48 inches minimum") is None
