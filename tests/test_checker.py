import pytest

from backend.checker import accept_items, approve_rule, check_design, unsupported_numbers
from backend.rules import RULE_LIBRARY_PATH, load_library, parse_measurement

WALKWAY = {"element": "deck 5 corridor", "attribute": "walking_route_clear_width"}


class FakeRetriever:
    """Returns the cited passage for a rule quote, and set passages for anything else."""

    def __init__(self, passages=None):
        self.passages = passages or []

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not any(rule.source.quote == query for rule in load_library()[1]):
            return self.passages[:top_k]
        # ADA and PVAG share some sentences, so every matching passage is returned.

    def find_passage(self, filename: str, page: int, quote: str) -> dict | None:
        _, rules = load_library()
        for rule in rules:
            source = rule.source
            if (source.filename, source.page, source.quote) == (filename, page, quote):
                return {
                    "filename": filename,
                    "page": page,
                    "page_end": page,
                    "chunk_id": "test-chunk",
                    "text": f"Intro text. {quote} More text.",
                }
        return None


class FakeLLM:
    def __init__(self, items=None, summary="Summary.", requirement=None):
        self.items = items or []
        self.summary = summary
        self.requirement = requirement or {"found": False}

    def chat_json(self, system, user, schema, max_tokens=400):
        if "items" in schema["properties"]:
            return {"items": self.items}
        if "found" in schema["properties"]:
            return self.requirement
        return {"summary": self.summary}


SILL_PASSAGE = {
    "chunk_id": "load-line:p20:c1",
    "filename": "MSIS41_International_Load_Line_R05.23.pdf",
    "page": 20,
    "page_end": 20,
    "section": "Regulation 12 Doors",
    "regulation": "Load Line",
    "status": "guidance",
    "text": "The height of the sills of the doorways shall be at least 380 mm above the deck.",
}
SILL_ITEM = {"element": "superstructure door", "property": "sill height", "value_text": "300 mm"}
SILL_ANSWER = {
    "found": True,
    "chunk_id": "load-line:p20:c1",
    "quote": "The height of the sills of the doorways shall be at least 380 mm above the deck.",
    "requirement_type": "numeric",
    "min_text": "380 mm",
    "max_text": "",
    "applies_to": "doorways in superstructures",
    "answer": "Door sills must be at least 380 mm above the deck.",
    "conditions": "",
}


def results_by_rule(result: dict) -> dict[str, str]:
    return {item["rule_id"]: item["status"] for item in result["results"] if "rule_id" in item}


def test_narrow_walkway_fails_with_margin():
    result = check_design(
        items=[{**WALKWAY, "value_text": "800 mm"}], retriever=FakeRetriever(), summarize=False
    )

    assert result["overall"] == "FAIL"
    assert results_by_rule(result) == {"ADA-403.5.1": "FAIL", "PVAG-V403.5.1": "FAIL"}
    assert result["results"][0]["margin"] == "115 mm"
    assert result["results"][0]["citation"]["verified"] is True


def test_wide_walkway_passes():
    result = check_design(
        items=[{**WALKWAY, "value_text": "1000 mm"}], retriever=FakeRetriever(), summarize=False
    )

    assert result["overall"] == "PASS"


def test_inches_are_judged_against_the_inch_value():
    # 36 inches is 914.4 mm, below the rounded 915 mm, but it meets the rule as written.
    result = check_design(
        items=[{**WALKWAY, "value_text": "36 inches"}], retriever=FakeRetriever(), summarize=False
    )

    assert set(results_by_rule(result).values()) == {"PASS"}


def test_ramp_slope_and_handrail_range():
    items = [
        {"element": "ramp", "attribute": "ramp_running_slope", "value_text": "1:10"},
        {"element": "handrail", "attribute": "handrail_height", "value_text": "1000 mm"},
    ]
    result = check_design(items=items, retriever=FakeRetriever(), summarize=False)

    assert set(results_by_rule(result).values()) == {"FAIL"}
    assert parse_measurement("1:12", "slope").value == 1 / 12


def test_item_without_a_rule_needs_review():
    item = {"element": "hull plate", "attribute": "unknown", "value_text": "12 mm"}
    result = check_design(items=[item], retriever=FakeRetriever(), summarize=False)

    assert result["overall"] == "NEEDS_REVIEW"
    assert result["results"][0]["status"] == "NO_RULE"


def test_unverified_citation_needs_review():
    result = check_design(items=[{**WALKWAY, "value_text": "1000 mm"}], summarize=False)

    assert result["overall"] == "NEEDS_REVIEW"
    assert result["results"][0]["citation"]["verified"] is False


def test_values_not_in_the_input_are_rejected():
    attributes, _ = load_library()
    items = [{**WALKWAY, "value_text": "1200 mm"}]

    accepted, warnings = accept_items(items, "Corridor clear width 800 mm", attributes)

    # The invented value is dropped, and the requirement is still looked up.
    assert accepted[0]["value_text"] == ""
    assert "not in the input" in warnings[0]


def test_mistral_reads_text_and_summary_is_used():
    llm = FakeLLM(
        items=[{**WALKWAY, "value_text": "800 mm"}],
        summary="The corridor fails ADA-403.5.1: 800 mm < 915 mm minimum, short by 115 mm.",
    )
    result = check_design(text="Deck 5 corridor width 800 mm.", llm=llm, retriever=FakeRetriever())

    assert result["parsed_by"] == "mistral"
    assert result["summary_source"] == "mistral"
    assert result["overall"] == "FAIL"


def test_summary_with_invented_numbers_is_replaced():
    llm = FakeLLM(summary="The corridor is 750 mm wide and fails.")
    result = check_design(
        items=[{**WALKWAY, "value_text": "800 mm"}], llm=llm, retriever=FakeRetriever()
    )

    assert result["summary_source"] == "template"
    assert result["overall"] == "FAIL"
    assert unsupported_numbers("750 mm", [{"design": "800 mm"}]) == ["750"]


def test_rule_quotes_contain_their_required_values():
    _, rules = load_library()
    for rule in rules:
        assert rule.required_text.lower() in rule.source.quote.lower(), rule.id


def test_level_two_reads_a_limit_from_a_passage():
    llm = FakeLLM(requirement=SILL_ANSWER)
    retriever = FakeRetriever([SILL_PASSAGE])
    result = check_design(items=[SILL_ITEM], llm=llm, retriever=retriever, summarize=False)

    found = result["results"][0]
    assert found["level"] == "ai_read"
    assert found["status"] == "FAIL"
    assert found["margin"] == "80 mm"
    # An AI-read limit reports an issue, but never fails the design outright.
    assert result["overall"] == "ISSUES_FOUND"
    # The source is guidance, so one soft check fails and confidence drops.
    assert found["confidence"] == "medium"
    assert found["proposed_rule"]["rule"]["min"] == [{"value": 380.0, "unit": "mm"}]


def test_level_two_rejects_an_invented_quote():
    answer = {**SILL_ANSWER, "quote": "Sills shall be at least 250 mm high.", "min_text": "250 mm"}
    llm = FakeLLM(requirement=answer)
    result = check_design(
        items=[SILL_ITEM], llm=llm, retriever=FakeRetriever([SILL_PASSAGE]), summarize=False
    )

    found = result["results"][0]
    assert found["level"] == "manual_review"
    assert "failed Python's review" in found["reason"]
    assert found["passages"][0]["page"] == 20


def test_level_two_rejects_a_limit_missing_from_the_quote():
    llm = FakeLLM(requirement={**SILL_ANSWER, "min_text": "450 mm"})
    result = check_design(
        items=[SILL_ITEM], llm=llm, retriever=FakeRetriever([SILL_PASSAGE]), summarize=False
    )

    assert result["results"][0]["level"] == "manual_review"


def test_level_three_lists_passages_when_nothing_is_found():
    result = check_design(
        items=[SILL_ITEM], llm=FakeLLM(), retriever=FakeRetriever([SILL_PASSAGE]), summarize=False
    )

    found = result["results"][0]
    assert found["level"] == "manual_review"
    assert found["status"] == "NO_RULE"
    assert found["passages"][0]["filename"] == SILL_PASSAGE["filename"]


def test_approved_rule_becomes_a_checked_rule(tmp_path):
    library_path = tmp_path / "rule_library.json"
    library_path.write_text(RULE_LIBRARY_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    regulations = tmp_path / "regulations"
    regulations.mkdir()
    (regulations / SILL_PASSAGE["filename"]).write_bytes(b"%PDF")

    first = check_design(
        items=[SILL_ITEM], llm=FakeLLM(requirement=SILL_ANSWER),
        retriever=FakeRetriever([SILL_PASSAGE]), summarize=False,
    )
    rule_id = approve_rule(first["results"][0]["proposed_rule"], library_path, regulations)
    library = load_library(library_path)
    second = check_design(
        items=[{**SILL_ITEM, "attribute": "sill_height"}], summarize=False, library=library
    )

    assert rule_id == "APPROVED-sill_height"
    assert second["results"][0]["level"] == "verified"
    assert second["results"][0]["status"] == "FAIL"


def test_approval_rejects_a_value_not_in_the_quote(tmp_path):
    proposal = check_design(
        items=[SILL_ITEM], llm=FakeLLM(requirement=SILL_ANSWER),
        retriever=FakeRetriever([SILL_PASSAGE]), summarize=False,
    )["results"][0]["proposed_rule"]
    proposal["rule"]["required_text"] = "450 mm minimum"

    with pytest.raises(ValueError):
        approve_rule(proposal, tmp_path / "unused.json", tmp_path)


def test_level_two_warns_when_the_quote_has_several_limits():
    text = "In position 1 sills shall be at least 600 mm. In position 2 it shall be at least 380 mm."
    passage = {**SILL_PASSAGE, "text": text}
    answer = {**SILL_ANSWER, "quote": text, "min_text": "600 mm"}
    result = check_design(
        items=[SILL_ITEM], llm=FakeLLM(requirement=answer),
        retriever=FakeRetriever([passage]), summarize=False,
    )

    steps = " ".join(result["results"][0]["verification_steps"])
    assert "also states 380 mm" in steps


def test_questions_without_a_value_get_a_quoted_answer():
    question = {"element": "superstructure door", "property": "sill height", "value_text": ""}
    result = check_design(
        items=[question], llm=FakeLLM(requirement=SILL_ANSWER),
        retriever=FakeRetriever([SILL_PASSAGE]), summarize=False,
    )

    found = result["results"][0]
    assert found["status"] == "REQUIREMENT_FOUND"
    assert found["answer"] == SILL_ANSWER["answer"]
    assert found["citation"]["page"] == 20
    assert result["overall"] == "ANSWERED"


def test_rule_library_can_be_switched_off():
    passage = {**SILL_PASSAGE, "text": "The clear width of walking surfaces shall be 915 mm minimum."}
    answer = {
        **SILL_ANSWER, "quote": passage["text"], "min_text": "915 mm",
        "applies_to": "walking surfaces in corridors",
    }
    item = {**WALKWAY, "property": "clear width", "value_text": "800 mm"}
    result = check_design(
        items=[item], llm=FakeLLM(requirement=answer), retriever=FakeRetriever([passage]),
        summarize=False, use_rule_library=False,
    )

    assert result["results"][0]["level"] == "ai_read"
    assert result["overall"] == "ISSUES_FOUND"


def test_invented_numbers_in_the_answer_are_replaced_by_the_quote():
    answer = {**SILL_ANSWER, "answer": "Door sills must be at least 450 mm high."}
    result = check_design(
        items=[SILL_ITEM], llm=FakeLLM(requirement=answer),
        retriever=FakeRetriever([SILL_PASSAGE]), summarize=False,
    )

    assert "450" not in result["results"][0]["answer"]
    assert result["results"][0]["answer"].startswith("The passage states:")


def test_rule_for_another_element_lowers_confidence():
    answer = {**SILL_ANSWER, "applies_to": "companionways"}
    result = check_design(
        items=[SILL_ITEM], llm=FakeLLM(requirement=answer),
        retriever=FakeRetriever([SILL_PASSAGE]), summarize=False,
    )

    found = result["results"][0]
    failed = [check["check"] for check in found["review"] if not check["passed"]]
    assert "Requirement covers the same kind of element" in failed
    # Guidance source plus another element: two soft failures make it low confidence.
    assert found["confidence"] == "low"


def test_quotes_survive_hidden_hyphens_and_small_rewording():
    from backend.checker import _match_quote

    passage = "Ships which are stationary ex\x02cept for relocation voyages need not be provided with oil filtering equipment."
    exact, _ = _match_quote("Ships which are stationary except for relocation voyages need not be provided", passage)
    close, how = _match_quote(
        "Ships which are stationary except for relocation voyages need not have oil filtering equipment.", passage
    )
    invented, _ = _match_quote("Hotel ships must always carry oil filtering equipment.", passage)

    assert exact is not None
    assert close is not None and "except" in close and "differed slightly" in how
    assert invented is None


def test_rule_for_a_similar_element_is_low_confidence():
    # The real door sill case: a deckhouse rule shares "freeboard deck" with the design item.
    text = "Where access is not provided from above, the height of the sills to doorways in deckhouses on the freeboard deck shall be 600 mm."
    passage = {**SILL_PASSAGE, "text": text}
    answer = {
        **SILL_ANSWER, "quote": text, "min_text": "600 mm",
        "applies_to": "doorways in deckhouses on the freeboard deck",
    }
    item = {**SILL_ITEM, "element": "Superstructure door on the freeboard deck"}
    result = check_design(
        items=[item], llm=FakeLLM(requirement=answer), retriever=FakeRetriever([passage]), summarize=False,
    )

    found = result["results"][0]
    assert found["confidence"] == "low"
    assert result["overall"] == "ISSUES_FOUND"
    assert any("superstructure" in check["detail"] for check in found["review"])


def test_values_match_the_input_regardless_of_spaces():
    attributes, _ = load_library()
    items = [{"element": "ramp", "attribute": "ramp_running_slope", "value_text": "6%"}]

    accepted, warnings = accept_items(items, "Gangway ramp: running slope 6 %.", attributes)
    changed, _ = accept_items([{**items[0], "value_text": "8%"}], "Gangway ramp: running slope 6 %.", attributes)

    assert accepted[0]["value_text"] == "6%" and not warnings
    assert changed[0]["value_text"] == ""
