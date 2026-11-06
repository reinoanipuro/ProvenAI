import pytest

from backend.documents import parse_document
from backend.extraction import extract


def run(text, rule):
    return extract(parse_document("plan.md", text), rule)


@pytest.mark.parametrize("line, value, unit", [
    ("Escape route clear width: 1200 mm", "1200", "mm"),
    ("Escape route clear width: 1.2 m", "1.2", "m"),
    ("Escape route clear width: 1,2 m", "1.2", "m"),  # Finnish decimal comma
    ("| Escape route clear width | 140 cm |", "140", "cm"),
    ("ESCAPE ROUTE CLEAR WIDTH = 1500MM", "1500", "mm"),
])
def test_clear_values_are_found(rule_by_id, line, value, unit):
    result = run(line, rule_by_id["ER-1"])
    assert (result.status, result.value, result.unit) == ("FOUND", value, unit)
    assert result.confidence >= 0.8


@pytest.mark.parametrize("line", [
    "Escape route clear width: approx. 1.2 m",
    "Escape route clear width: about 1200 mm",
    "Escape route clear width: ~1200 mm",
    "Escape route clear width: 1200 mm (assumed)",
    "Escape route clear width: 1100-1200 mm",
    "Escape route clear width: 1100 to 1200 mm",
    "Escape route clear width: 1200 ± 50 mm",
    "Escape route clear width: 1,200 mm",   # 1.2 mm or 1200 mm?
    "Escape route clear width: 1 200 mm",   # 1200 mm, or a stray 1 before 200 mm?
])
def test_uncertain_values_never_reach_required_confidence(rule_by_id, line):
    result = run(line, rule_by_id["ER-1"])
    assert result.confidence < 0.8


def test_range_is_not_read_as_its_upper_bound(rule_by_id):
    result = run("Escape route clear width: 1100-1200 mm", rule_by_id["ER-1"])
    assert result.value is None


def test_conflicting_values_have_no_value(rule_by_id):
    text = "Guardrail height: 1100 mm\nGuardrail height: 950 mm"
    result = run(text, rule_by_id["DS-1"])
    assert result.status == "AMBIGUOUS"
    assert result.value is None
    assert len(result.sources) == 2


def test_two_values_on_one_line_conflict(rule_by_id):
    result = run("Escape route clear width: 1200 mm, 900 mm at stairs", rule_by_id["ER-1"])
    assert result.status == "AMBIGUOUS"


def test_same_value_in_different_units_is_not_a_conflict(rule_by_id):
    result = run("Guardrail height: 1100 mm\nGuardrail height: 1.1 m", rule_by_id["DS-1"])
    assert result.status == "FOUND"
    assert len(result.sources) == 2


def test_hedged_mention_lowers_agreeing_clear_mention(rule_by_id):
    result = run("Guardrail height: 1100 mm\nGuardrail height: approx. 1100 mm", rule_by_id["DS-1"])
    assert result.status == "LOW_CONFIDENCE"


def test_missing_and_value_less_mentions(rule_by_id):
    assert run("Nothing relevant.", rule_by_id["FS-2"]).status == "MISSING"
    assert run("Fire door class: TBD", rule_by_id["FS-1"]).status == "NO_VALUE"
    assert run("Guardrail height: see drawing", rule_by_id["DS-1"]).status == "NO_VALUE"


def test_wrong_unit_type_is_not_a_value(rule_by_id):
    assert run("Emergency lighting duration: 60 lx", rule_by_id["FS-2"]).status == "NO_VALUE"


def test_class_is_normalised(rule_by_id):
    assert run("Fire door class: A60", rule_by_id["FS-1"]).value == "A-60"
    assert run("Fire door class: A 30", rule_by_id["FS-1"]).value == "A-30"


def test_source_reference_has_file_section_page_and_quote(rule_by_id):
    text = "<!-- page: 7 -->\n## 3 Doors\nFire door class: A-60."
    source = run(text, rule_by_id["FS-1"]).sources[0]
    assert (source.file, source.section, source.page) == ("plan.md", "3 Doors", 7)
    assert source.quote == "Fire door class: A-60."
