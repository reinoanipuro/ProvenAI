"""The fixed compliance workflow: RAG -> extraction -> rule engine -> traceable record."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .audit import AuditStore
from .config import MIN_CONFIDENCE
from .documents import ParsedDocument, parse_document
from .engine import evaluate, overall_status
from .extraction import Extractor, extract
from .rag import RegulatoryIndex
from .schemas import Extraction, Finding, Inspection, Rule


def load_rules(rules_dir: Path) -> list[Rule]:
    """Load every rule file in the folder. A new rule area needs no code changes."""
    rules = []
    for path in sorted(rules_dir.glob("*.json")):
        area = json.loads(path.read_text(encoding="utf-8"))
        rules.extend(
            Rule(**item, domain=area["domain"], regulation_file=area["regulation_file"])
            for item in area["rules"]
        )
    return rules


def _verify_sources(extraction: Extraction, document: ParsedDocument) -> Extraction:
    """Reject values whose quotes do not exist at the cited place in the document."""
    if extraction.value is None:
        return extraction
    lines = {(line.page, line.text) for line in document.lines}
    for source in extraction.sources:
        if source.file != document.filename or (source.page, source.quote) not in lines:
            return Extraction(
                attribute=extraction.attribute,
                status="UNVERIFIED",
                sources=extraction.sources,
                method=extraction.method,
                note=(
                    f"The extractor proposed '{extraction.value}', but its quote was not "
                    f"found on page {source.page} of the document."
                ),
            )
    return extraction


class Pipeline:
    def __init__(
        self,
        rules: list[Rule],
        index: RegulatoryIndex,
        audit: AuditStore,
        extractor: Extractor = extract,
        min_confidence: float = MIN_CONFIDENCE,
    ):
        self.rules = rules
        self.index = index
        self.audit = audit
        self.extractor = extractor
        self.min_confidence = min_confidence

    def run(self, filename: str, text: str) -> Inspection:
        document = parse_document(filename, text)
        inspection_id = uuid.uuid4().hex[:12]
        self.audit.log(inspection_id, "inspection_started", {
            "document": filename,
            "document_sha256": document.sha256,
            "min_confidence": self.min_confidence,
        })

        findings = []
        for rule in self.rules:
            evidence = self.index.verify_rule(rule)
            self.audit.log(inspection_id, "rule_source_checked", {
                "rule": rule.id, "evidence": evidence.model_dump(),
            })
            extraction = _verify_sources(self.extractor(document, rule), document)
            self.audit.log(inspection_id, "value_extracted", {
                "rule": rule.id, "extraction": extraction.model_dump(),
            })
            decision = evaluate(rule, evidence, extraction, self.min_confidence)
            self.audit.log(inspection_id, "rule_evaluated", {
                "rule": rule.id, "decision": decision.model_dump(),
            })
            findings.append(Finding(
                rule=rule, rule_evidence=evidence, extraction=extraction, decision=decision,
            ))

        inspection = Inspection(
            id=inspection_id,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            document=filename,
            document_sha256=document.sha256,
            overall=overall_status([f.decision.status for f in findings]),
            min_confidence=self.min_confidence,
            findings=findings,
        )
        self.audit.save_inspection(inspection)
        self.audit.log(inspection_id, "inspection_completed", {"overall": inspection.overall})
        return inspection
