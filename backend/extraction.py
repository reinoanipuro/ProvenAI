"""Document Intelligence: find a rule's value in a plan, with its source and confidence.

This demo uses a transparent rule-based extractor so it runs offline. Any extractor,
including an LLM, can replace it by following the `Extractor` signature. The pipeline
checks every returned quote against the document, and the extractor never decides
PASS or FAIL.

Confidence scores here are fixed heuristics, not calibrated probabilities.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from .documents import Line, ParsedDocument
from .schemas import Extraction, Rule, SourceRef
from .units import ALIASES, to_base

Extractor = Callable[[ParsedDocument, Rule], Extraction]

CONFIDENCE_PRIMARY_LABEL = 0.95
CONFIDENCE_ALTERNATE_LABEL = 0.85
CONFIDENCE_UNCERTAIN = 0.50
CONFIDENCE_CONFLICT = 0.30

_HEDGES = re.compile(
    r"\b(?:approx|approximately|about|around|circa|ca|roughly|estimated|preliminary|"
    r"assumed|tbd|tbc|up to|to be (?:confirmed|determined|defined|measured|checked))\b"
    r"|~|±|\+/-"
    r"|\d\s*(?:to|[-–—/])\s*\d",  # ranges such as 1100-1200 mm or 1100 to 1200 mm
    re.IGNORECASE,
)
# The lookbehind rejects partial reads: "1100-1200 mm" must not be read as "1200 mm".
_NUMBER = r"(?<![\d.,\-–—/])(\d{1,3}(?:[  ]\d{3})+|\d+(?:[.,]\d+)?)"


@dataclass(frozen=True)
class _Candidate:
    value: str
    unit: str
    key: Decimal | str
    line: Line
    confidence: float
    note: str


def _parse_number(raw: str) -> tuple[Decimal, str]:
    """Return the number and a note if its format could be read more than one way."""
    if " " in raw or " " in raw:
        joined = raw.replace(" ", "").replace(" ", "")
        return Decimal(joined), f"'{raw}' looks like a space-separated number; confirm it."
    if re.fullmatch(r"\d+[.,]\d{3}", raw):
        return (
            Decimal(raw.replace(",", ".")),
            f"'{raw}' could be a decimal or a thousands separator.",
        )
    return Decimal(raw.replace(",", ".")), ""


def _values_in(text: str, rule: Rule) -> list[tuple[str, str, Decimal | str, str]]:
    """Return (value, unit, comparison key, format note) for each value in the text."""
    if rule.kind == "classification":
        pattern = rf"\b{re.escape(rule.class_prefix)}\s*-?\s*(\d+)\b"
        return [
            (name, "", name, "")
            for name in (f"{rule.class_prefix}-{m.group(1)}" for m in re.finditer(pattern, text))
        ]

    aliases = ALIASES[rule.dimension]
    units = "|".join(sorted(map(re.escape, aliases), key=len, reverse=True))
    found = []
    for match in re.finditer(rf"{_NUMBER}\s*({units})\b", text, re.IGNORECASE):
        number, note = _parse_number(match.group(1))
        unit = aliases[match.group(2).lower()]
        found.append((format(number, "f"), unit, to_base(number, unit, rule.dimension), note))
    return found


def _source(document: ParsedDocument, line: Line) -> SourceRef:
    return SourceRef(
        file=document.filename,
        section=line.section,
        page=line.page,
        line=line.number,
        quote=line.text,
    )


def extract(document: ParsedDocument, rule: Rule) -> Extraction:
    candidates: list[_Candidate] = []
    label_only: list[Line] = []

    for line in document.lines:
        lowered = line.text.lower()
        for position, label in enumerate(rule.labels):
            start = lowered.find(label.lower())
            if start < 0:
                continue
            values = _values_in(line.text[start + len(label):], rule)
            if not values:
                label_only.append(line)
            hedged = bool(_HEDGES.search(line.text))
            base = CONFIDENCE_PRIMARY_LABEL if position == 0 else CONFIDENCE_ALTERNATE_LABEL
            for value, unit, key, note in values:
                uncertain = hedged or bool(note)
                reason = note or ("The text is hedged or gives a range." if hedged else "")
                candidates.append(
                    _Candidate(
                        value, unit, key, line,
                        CONFIDENCE_UNCERTAIN if uncertain else base,
                        reason,
                    )
                )
            break

    if not candidates:
        if label_only:
            return Extraction(
                attribute=rule.attribute,
                status="NO_VALUE",
                sources=[_source(document, line) for line in label_only],
                note="The document mentions this item but gives no usable value.",
            )
        return Extraction(
            attribute=rule.attribute,
            status="MISSING",
            note=f"No mention found. Searched for: {', '.join(rule.labels)}.",
        )

    sources = []
    for candidate in candidates:
        source = _source(document, candidate.line)
        if source not in sources:
            sources.append(source)

    if len({candidate.key for candidate in candidates}) > 1:
        stated = ", ".join(f"{c.value} {c.unit}".strip() for c in candidates)
        return Extraction(
            attribute=rule.attribute,
            status="AMBIGUOUS",
            confidence=CONFIDENCE_CONFLICT,
            sources=sources,
            note=f"The document states conflicting values: {stated}.",
        )

    # All candidates agree, so the least certain mention sets the confidence.
    weakest = min(candidates, key=lambda candidate: candidate.confidence)
    return Extraction(
        attribute=rule.attribute,
        status="LOW_CONFIDENCE" if weakest.confidence == CONFIDENCE_UNCERTAIN else "FOUND",
        value=weakest.value,
        unit=weakest.unit,
        confidence=weakest.confidence,
        sources=sources,
        note=weakest.note,
    )
