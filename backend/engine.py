"""Deterministic rule engine: the only code allowed to decide PASS or FAIL.

This module is pure. It uses no LLM, network, randomness, clock, or database, so the
same inputs always give the same decision. tests/test_engine.py enforces its imports.

Any doubt about the rule's source or the input value gives UNKNOWN, never a guess.
"""

import operator
import re
from decimal import Decimal

from .schemas import Decision, Extraction, Rule, RuleEvidence, Status
from .units import UnitError, to_base

_OPERATORS = {">=": operator.ge, "<=": operator.le}
# Rejects NaN, Infinity, signs, and exponents. The digit limits keep every value within
# Decimal's 28-digit precision, so conversion cannot round a value across a limit.
_PLAIN_NUMBER = re.compile(r"\d{1,12}(\.\d{1,6})?")


def _unknown(reason: str) -> Decision:
    return Decision(status="UNKNOWN", reason=reason)


def _evaluate_numeric(rule: Rule, extraction: Extraction, compare) -> Decision:
    if not _PLAIN_NUMBER.fullmatch(extraction.value):
        return _unknown(f"'{extraction.value}' is not a plain decimal number.")
    measured = Decimal(extraction.value)
    if measured <= 0:
        return _unknown(f"'{extraction.value}' is not a valid physical measurement.")
    try:
        measured_base = to_base(measured, extraction.unit, rule.dimension)
        limit_base = to_base(Decimal(rule.threshold), rule.unit, rule.dimension)
    except UnitError as error:
        return _unknown(f"Cannot compare values: {error}.")

    passed = compare(measured_base, limit_base)
    return Decision(
        status="PASS" if passed else "FAIL",
        reason=(
            f"Found {extraction.value} {extraction.unit}; "
            f"required {rule.operator} {rule.threshold} {rule.unit}."
        ),
        computation=f"{measured_base} {rule.operator} {limit_base} (base units) = {passed}",
    )


def _evaluate_classification(rule: Rule, extraction: Extraction, compare) -> Decision:
    if extraction.value not in rule.scale:
        return _unknown(f"'{extraction.value}' is not on the rule's scale: {rule.scale}.")
    if rule.threshold not in rule.scale:
        return _unknown(f"Threshold '{rule.threshold}' is not on the rule's scale.")
    found_rank = rule.scale.index(extraction.value)
    limit_rank = rule.scale.index(rule.threshold)
    passed = compare(found_rank, limit_rank)
    return Decision(
        status="PASS" if passed else "FAIL",
        reason=f"Found {extraction.value}; required {rule.operator} {rule.threshold}.",
        computation=f"scale rank {found_rank} {rule.operator} {limit_rank} = {passed}",
    )


def evaluate(
    rule: Rule,
    rule_evidence: RuleEvidence,
    extraction: Extraction,
    min_confidence: float,
) -> Decision:
    if not rule_evidence.verified:
        return _unknown(f"The rule's source could not be verified: {rule_evidence.note}")
    if extraction.value is None:
        return _unknown(extraction.note or "No value was extracted.")
    if extraction.confidence < min_confidence:
        return _unknown(
            f"Extraction confidence {extraction.confidence:.2f} is below the required "
            f"{min_confidence:.2f}. {extraction.note}".strip()
        )
    if not extraction.sources:
        return _unknown("The extracted value has no source reference.")

    compare = _OPERATORS.get(rule.operator)
    if compare is None:
        return _unknown(f"Unsupported operator '{rule.operator}'.")
    if rule.kind == "numeric":
        return _evaluate_numeric(rule, extraction, compare)
    return _evaluate_classification(rule, extraction, compare)


def overall_status(statuses: list[Status]) -> Status:
    """FAIL outranks UNKNOWN, and PASS requires every check to pass."""
    if not statuses:
        return "UNKNOWN"
    if "FAIL" in statuses:
        return "FAIL"
    if "UNKNOWN" in statuses:
        return "UNKNOWN"
    return "PASS"
