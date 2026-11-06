from backend.pipeline import inspect_document, load_rules


def statuses(text: str) -> dict[str, str]:
    return {finding.rule_id: finding.status for finding in inspect_document(text)}


def test_compliant_document_passes():
    result = statuses("Escape route clear width: 1400 mm\nGuardrail height: 1100 mm")
    assert result == {"ER-1": "PASS", "DS-1": "PASS"}


def test_violation_fails_only_the_invalid_rule():
    result = statuses("Escape route clear width: 900 mm\nGuardrail height: 1100 mm")
    assert result == {"ER-1": "FAIL", "DS-1": "PASS"}


def test_missing_value_is_unknown():
    result = statuses("Escape route clear width: to be confirmed")
    assert result == {"ER-1": "UNKNOWN", "DS-1": "UNKNOWN"}


def test_rules_are_loaded_from_data():
    assert {rule.id for rule in load_rules()} == {"ER-1", "DS-1"}
