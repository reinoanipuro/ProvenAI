"""Data contracts shared by every pipeline stage."""

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["PASS", "FAIL", "UNKNOWN"]
ExtractionStatus = Literal[
    "FOUND",           # one clear value, with a source
    "LOW_CONFIDENCE",  # a value exists, but it is hedged or its format is ambiguous
    "AMBIGUOUS",       # the document states conflicting values
    "NO_VALUE",        # the attribute is mentioned but no usable value is given
    "MISSING",         # the attribute is not mentioned
    "UNVERIFIED",      # the extractor's quote could not be found in the document
]


class Rule(BaseModel):
    """A machine-readable rule tied to one regulation clause. Defined as data, not code."""

    id: str
    domain: str
    title: str
    attribute: str
    kind: Literal["numeric", "classification"]
    operator: str
    threshold: str
    unit: str = ""
    dimension: str = ""
    class_prefix: str = ""
    scale: list[str] = Field(default_factory=list)
    regulation_file: str
    clause: str
    threshold_quote: str
    query: str
    labels: list[str]


class Passage(BaseModel):
    """Verbatim regulation text returned by the vector search."""

    file: str
    clause: str
    title: str
    page: int
    text: str
    relevance: float


class RuleEvidence(BaseModel):
    """Result of checking a rule against the regulation text retrieved for it."""

    verified: bool
    note: str
    passage: Passage | None = None


class SourceRef(BaseModel):
    file: str
    section: str
    page: int | None = None
    line: int | None = None
    quote: str


class Extraction(BaseModel):
    attribute: str
    status: ExtractionStatus
    value: str | None = None
    unit: str = ""
    confidence: float = 0.0
    sources: list[SourceRef] = Field(default_factory=list)
    method: str = "rule_based_extractor"
    note: str = ""


class Decision(BaseModel):
    status: Status
    reason: str
    computation: str = ""


class Finding(BaseModel):
    rule: Rule
    rule_evidence: RuleEvidence
    extraction: Extraction
    decision: Decision


class Inspection(BaseModel):
    id: str
    created_at: str
    document: str
    document_sha256: str
    overall: Status
    min_confidence: float
    findings: list[Finding]


class InspectionRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=1_000_000)
