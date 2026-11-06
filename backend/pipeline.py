import json
import re
from pathlib import Path

from .models import Evidence, Finding, Rule

ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = ROOT / "data" / "rules.json"
NUMBER_PATTERN = re.compile(r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>[A-Za-z]+)?")


def load_rules(path: Path = RULES_PATH) -> list[Rule]:
    items = json.loads(path.read_text(encoding="utf-8"))
    return [
        Rule(
            id=item["id"],
            title=item["title"],
            attribute=item["attribute"],
            operator=item["operator"],
            threshold=item["threshold"],
            unit=item["unit"],
            labels=tuple(item["labels"]),
        )
        for item in items
    ]


def extract_evidence(text: str, rule: Rule) -> Evidence | None:
    for line in text.splitlines():
        lowered = line.lower()
        label = next((item for item in rule.labels if item.lower() in lowered), None)
        if label is None:
            continue
        match = NUMBER_PATTERN.search(line[line.lower().find(label.lower()) + len(label):])
        if match is None:
            return Evidence(rule.attribute, None, "", 0.0, line.strip(), "document")
        value = match.group("value").replace(",", ".")
        unit = match.group("unit") or rule.unit
        return Evidence(rule.attribute, value, unit, 0.95, line.strip(), "document")
    return None


def evaluate(rule: Rule, evidence: Evidence | None) -> Finding:
    if evidence is None or evidence.value is None:
        return Finding(rule.id, "UNKNOWN", "No usable value was found.", evidence)
    if evidence.unit.lower() != rule.unit.lower():
        return Finding(rule.id, "UNKNOWN", f"Expected unit {rule.unit}.", evidence)

    value = float(evidence.value)
    if rule.operator == ">=":
        passed = value >= rule.threshold
    elif rule.operator == "<=":
        passed = value <= rule.threshold
    else:
        return Finding(rule.id, "UNKNOWN", f"Unsupported operator {rule.operator}.", evidence)

    status = "PASS" if passed else "FAIL"
    reason = f"Found {value:g} {rule.unit}; required {rule.operator} {rule.threshold:g} {rule.unit}."
    return Finding(rule.id, status, reason, evidence)


def inspect_document(text: str, rules: list[Rule] | None = None) -> list[Finding]:
    active_rules = rules if rules is not None else load_rules()
    return [evaluate(rule, extract_evidence(text, rule)) for rule in active_rules]
