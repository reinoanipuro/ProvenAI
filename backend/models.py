from dataclasses import dataclass


@dataclass(frozen=True)
class Evidence:
    attribute: str
    value: str | None
    unit: str
    confidence: float
    quote: str
    source: str


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    attribute: str
    operator: str
    threshold: float
    unit: str
    labels: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    rule_id: str
    status: str
    reason: str
    evidence: Evidence | None
