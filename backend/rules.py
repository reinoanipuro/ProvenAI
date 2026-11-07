"""Checked rule library and the deterministic calculation against design values.

Required values come from data/rule_library.json, where each rule was checked by
a person against its source page. Nothing here is read from regulation text at
run time, so the calculation cannot pick up a wrong number.
"""

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULE_LIBRARY_PATH = ROOT / "data" / "rule_library.json"

LENGTH_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}
IMPERIAL = {"in", "ft"}
_UNIT_ALIASES = {
    "mm": "mm", "millimetre": "mm", "millimetres": "mm", "millimeter": "mm", "millimeters": "mm",
    "cm": "cm", "centimetre": "cm", "centimetres": "cm", "centimeter": "cm", "centimeters": "cm",
    "m": "m", "metre": "m", "metres": "m", "meter": "m", "meters": "m",
    "in": "in", "inch": "in", "inches": "in", '"': "in",
    "ft": "ft", "foot": "ft", "feet": "ft", "'": "ft",
    "%": "percent", "percent": "percent", "per cent": "percent",
    "°": "degrees", "deg": "degrees", "degree": "degrees", "degrees": "degrees",
}
_RATIO = re.compile(r"(?P<rise>\d+(?:[.,]\d+)?)\s*:\s*(?P<run>\d+(?:[.,]\d+)?)")
_NUMBER_WITH_UNIT = re.compile(
    r"(?P<value>-?\d+(?:[.,]\d+)?)\s*(?P<unit>per cent|percent|millimet(?:re|er)s?|centimet(?:re|er)s?|"
    r"met(?:re|er)s?|inch(?:es)?|feet|foot|degrees?|deg|mm|cm|in|ft|m|%|°|\"|')?",
    re.IGNORECASE,
)
_RELATIVE_TOLERANCE = 1e-9


@dataclass(frozen=True)
class Limit:
    value: float
    unit: str


@dataclass(frozen=True)
class Source:
    filename: str
    page: int
    section: str
    quote: str


@dataclass(frozen=True)
class LibraryRule:
    id: str
    title: str
    attribute: str
    quantity: str
    minimum: tuple[Limit, ...]
    maximum: tuple[Limit, ...]
    required_text: str
    exceptions: str
    source: Source


@dataclass(frozen=True)
class Measurement:
    """A design value in a canonical unit: mm, a rise/run fraction, or percent."""

    value: float
    unit: str
    original_unit: str
    text: str


@dataclass(frozen=True)
class Calculation:
    status: str  # PASS, FAIL or UNKNOWN
    design: str
    required: str
    comparison: str
    margin: str
    reason: str


def load_library(path: Path = RULE_LIBRARY_PATH) -> tuple[dict[str, dict], list[LibraryRule]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    attributes = data["attributes"]
    rules = [
        LibraryRule(
            id=item["id"],
            title=item["title"],
            attribute=item["attribute"],
            quantity=attributes[item["attribute"]]["quantity"],
            minimum=tuple(Limit(limit["value"], limit["unit"]) for limit in item.get("min", [])),
            maximum=tuple(Limit(limit["value"], limit["unit"]) for limit in item.get("max", [])),
            required_text=item["required_text"],
            exceptions=item.get("exceptions", ""),
            source=Source(**item["source"]),
        )
        for item in data["rules"]
    ]
    return attributes, rules


def parse_measurement(text: str, quantity: str) -> Measurement | None:
    """Read a value such as '800 mm', '36 in', '1:14', '7 %' or '96 percent'."""
    if quantity == "slope" and (ratio := _RATIO.search(text)):
        rise = float(ratio["rise"].replace(",", "."))
        run = float(ratio["run"].replace(",", "."))
        if run <= 0:
            return None
        return Measurement(rise / run, "ratio", "ratio", text)

    # Take the first number that has a fitting unit, so "deck 5, 800 mm" reads 800 mm.
    for match in _NUMBER_WITH_UNIT.finditer(text):
        value = float(match["value"].replace(",", "."))
        unit = _UNIT_ALIASES.get((match["unit"] or "").lower())
        if quantity == "length" and unit in LENGTH_TO_MM:
            return Measurement(value * LENGTH_TO_MM[unit], "mm", unit, text)
        if quantity == "slope" and unit == "percent":
            return Measurement(value / 100, "ratio", "percent", text)
        if quantity == "slope" and unit == "degrees":
            return Measurement(math.tan(math.radians(value)), "ratio", "degrees", text)
        if quantity == "percentage" and unit == "percent":
            return Measurement(value, "percent", "percent", text)
    return None


def infer_quantity(value_text: str, description: str = "") -> str | None:
    """Work out what kind of value a design item has, for items without a rule."""
    is_slope = re.search(r"slope|gradient|incline|ramp", description, re.IGNORECASE)
    if _RATIO.search(value_text):
        return "slope"
    for quantity in ("length", "slope", "percentage"):
        if quantity == "slope" and not is_slope and "°" not in value_text and "deg" not in value_text:
            continue
        if parse_measurement(value_text, quantity) is not None:
            return quantity
    return None


def parse_limits(text: str, quantity: str) -> tuple[Limit, ...]:
    """Read every limit stated in text such as '36 inches (915 mm)', in its own unit."""
    limits: list[Limit] = []
    if quantity == "slope":
        for ratio in _RATIO.finditer(text):
            run = float(ratio["run"].replace(",", "."))
            if run > 0:
                limits.append(Limit(float(ratio["rise"].replace(",", ".")) / run, "ratio"))
    for match in _NUMBER_WITH_UNIT.finditer(text):
        unit = _UNIT_ALIASES.get((match["unit"] or "").lower())
        value = float(match["value"].replace(",", "."))
        if quantity == "length" and unit in LENGTH_TO_MM:
            limits.append(Limit(value, unit))
        elif quantity == "slope" and unit == "percent":
            limits.append(Limit(value / 100, "ratio"))
        elif quantity == "percentage" and unit == "percent":
            limits.append(Limit(value, "percent"))
    return tuple(limits)


def _limit_for(limits: tuple[Limit, ...], measurement: Measurement) -> Limit:
    """Use the limit written in the design's own unit system.

    The regulations state both units, and they are rounded separately: 36 inches
    is 914.4 mm, not 915 mm. A design in inches is judged against the inch value.
    """
    if measurement.original_unit in IMPERIAL:
        for limit in limits:
            if limit.unit in IMPERIAL:
                return limit
    for limit in limits:
        if limit.unit not in IMPERIAL:
            return limit
    return limits[0]


def _in_limit_unit(measurement: Measurement, limit: Limit) -> float:
    if limit.unit in LENGTH_TO_MM:
        return measurement.value / LENGTH_TO_MM[limit.unit]
    return measurement.value


def format_value(value: float, unit: str) -> str:
    if unit == "ratio":
        return f"1:{1 / value:.3g} ({value * 100:.1f} %)" if value > 0 else "level (0 %)"
    if unit == "percent":
        return f"{value:g} %"
    rounded = round(value, 1)
    return f"{rounded:g} {unit}"


def _below(value: float, limit: float) -> bool:
    return value < limit and not math.isclose(value, limit, rel_tol=_RELATIVE_TOLERANCE)


def _above(value: float, limit: float) -> bool:
    return value > limit and not math.isclose(value, limit, rel_tol=_RELATIVE_TOLERANCE)


def evaluate(rule: LibraryRule, value_text: str) -> Calculation:
    measurement = parse_measurement(value_text, rule.quantity)
    if measurement is None:
        return Calculation(
            "UNKNOWN", value_text, rule.required_text, "", "",
            f"Could not read a {rule.quantity} value with a unit from '{value_text}'.",
        )

    failures: list[tuple[str, str]] = []
    comparisons: list[str] = []
    design_text = ""
    for side, limits in (("min", rule.minimum), ("max", rule.maximum)):
        if not limits:
            continue
        limit = _limit_for(limits, measurement)
        design = _in_limit_unit(measurement, limit)
        design_text = format_value(design, limit.unit)
        required = format_value(limit.value, limit.unit)
        if side == "min":
            failed = _below(design, limit.value)
            comparisons.append(f"{design_text} {'<' if failed else '>='} {required} minimum")
            if failed:
                failures.append((side, _margin(limit.value - design, limit.unit)))
        else:
            failed = _above(design, limit.value)
            comparisons.append(f"{design_text} {'>' if failed else '<='} {required} maximum")
            if failed:
                failures.append((side, _margin(design - limit.value, limit.unit)))

    comparison = "; ".join(comparisons)
    if failures:
        side, margin = failures[0]
        word = "below the minimum" if side == "min" else "above the maximum"
        return Calculation("FAIL", design_text, rule.required_text, comparison, margin, f"{margin} {word}.")
    return Calculation("PASS", design_text, rule.required_text, comparison, "", "Within the limit.")


def _margin(difference: float, unit: str) -> str:
    if unit == "ratio":
        return f"{difference * 100:.1f} percentage points of slope"
    return format_value(difference, unit)
