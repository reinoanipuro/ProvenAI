from backend.checker import accept_items, check_design, unsupported_numbers
from backend.rules import load_library, parse_measurement

WALKWAY = {"element": "deck 5 corridor", "attribute": "walking_route_clear_width"}


class FakeRetriever:
    """Returns the cited passage, as the real index would."""

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
    def __init__(self, items=None, summary="Summary."):
        self.items = items or []
        self.summary = summary

    def chat_json(self, system, user, schema, max_tokens=400):
        if "items" in schema["properties"]:
            return {"items": self.items}
        return {"summary": self.summary}


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

    assert accepted == []
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
