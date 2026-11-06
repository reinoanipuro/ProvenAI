import ast
from pathlib import Path

import pytest

from backend import engine
from backend.engine import evaluate, overall_status
from backend.schemas import Extraction, RuleEvidence, SourceRef

VERIFIED = RuleEvidence(verified=True, note="ok")
SOURCE = SourceRef(file="plan.md", section="2", page=1, line=1, quote="quote")


def extraction(value, unit="mm", confidence=0.95, sources=(SOURCE,)):
    return Extraction(
        attribute="x", status="FOUND", value=value, unit=unit,
        confidence=confidence, sources=list(sources),
    )


@pytest.mark.parametrize("value, unit, expected", [
    ("1200", "mm", "PASS"),      # exactly on the limit
    ("1199.9", "mm", "FAIL"),
    ("1.2", "m", "PASS"),        # exact conversion
    ("120", "cm", "PASS"),
    ("1.1", "m", "FAIL"),
])
def test_minimum_limit(rule_by_id, value, unit, expected):
    decision = evaluate(rule_by_id["ER-1"], VERIFIED, extraction(value, unit), 0.8)
    assert decision.status == expected


@pytest.mark.parametrize("value, expected", [("30", "PASS"), ("30.01", "FAIL")])
def test_maximum_limit(rule_by_id, value, expected):
    decision = evaluate(rule_by_id["ER-2"], VERIFIED, extraction(value, "m"), 0.8)
    assert decision.status == expected


def test_conversion_has_no_float_error(rule_by_id):
    # With binary floats 1.1 * 1000 = 1100.0000000000002.
    decision = evaluate(rule_by_id["DS-1"], VERIFIED, extraction("1.1", "m"), 0.8)
    assert decision.status == "PASS"
    assert decision.computation.startswith("1100.0 >= 1100")


@pytest.mark.parametrize("value, expected", [
    ("A-30", "PASS"), ("A-60", "PASS"), ("A-15", "FAIL"),
])
def test_classification_uses_scale_order(rule_by_id, value, expected):
    decision = evaluate(rule_by_id["FS-1"], VERIFIED, extraction(value, ""), 0.8)
    assert decision.status == expected


@pytest.mark.parametrize("bad", [
    extraction(None),
    extraction("1500", confidence=0.79),
    extraction("1500", sources=()),
    extraction("abc"),
    extraction("NaN"),
    extraction("Infinity"),
    extraction("-5"),
    extraction("0"),
    extraction("1e999999"),
    extraction("1199.99999999999999999999999999999"),
    extraction("1500", unit="kg"),
    extraction("1500", unit=""),
])
def test_doubtful_input_is_unknown(rule_by_id, bad):
    assert evaluate(rule_by_id["ER-1"], VERIFIED, bad, 0.8).status == "UNKNOWN"


def test_value_off_the_scale_is_unknown(rule_by_id):
    decision = evaluate(rule_by_id["FS-1"], VERIFIED, extraction("A-61", ""), 0.8)
    assert decision.status == "UNKNOWN"


def test_unverified_rule_source_is_unknown_even_with_good_value(rule_by_id):
    evidence = RuleEvidence(verified=False, note="clause changed")
    decision = evaluate(rule_by_id["ER-1"], evidence, extraction("1500"), 0.8)
    assert decision.status == "UNKNOWN"


@pytest.mark.parametrize("statuses, expected", [
    (["PASS", "PASS"], "PASS"),
    (["PASS", "UNKNOWN"], "UNKNOWN"),
    (["UNKNOWN", "FAIL", "PASS"], "FAIL"),
    ([], "UNKNOWN"),
])
def test_overall_status(statuses, expected):
    assert overall_status(statuses) == expected


def test_engine_imports_stay_pure():
    """Fails the build if anyone connects the decision code to an LLM, network, or database."""
    tree = ast.parse(Path(engine.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add("." * node.level + (node.module or ""))
    assert imported == {"operator", "re", "decimal", ".schemas", ".units"}
