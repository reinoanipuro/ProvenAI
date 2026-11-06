import json

from backend.audit import AuditStore
from backend.config import REGULATIONS_DIR, SAMPLES_DIR
from backend.pipeline import Pipeline, load_rules
from backend.rag import RegulatoryIndex
from backend.schemas import Extraction, SourceRef

COMPLIANT = "1_compliant_cabin_deck.md"
VIOLATIONS = "2_violations_crew_area.md"
INCOMPLETE = "3_incomplete_service_deck.md"


def run_sample(pipeline, name):
    return pipeline.run(name, (SAMPLES_DIR / name).read_text(encoding="utf-8"))


def statuses(inspection):
    return {f.rule.id: f.decision.status for f in inspection.findings}


def test_all_rules_verify_against_the_retrieved_regulation(rules, index):
    assert len({rule.domain for rule in rules}) == 3
    for rule in rules:
        evidence = index.verify_rule(rule)
        assert evidence.verified, f"{rule.id}: {evidence.note}"


def test_compliant_plan(pipeline):
    inspection = run_sample(pipeline, COMPLIANT)
    assert inspection.overall == "PASS"
    assert set(statuses(inspection).values()) == {"PASS"}


def test_plan_with_violations(pipeline):
    inspection = run_sample(pipeline, VIOLATIONS)
    assert inspection.overall == "FAIL"
    assert statuses(inspection) == {
        "ER-1": "FAIL", "ER-2": "FAIL", "ER-3": "PASS",
        "FS-1": "FAIL", "FS-2": "PASS", "DS-1": "PASS",
    }


def test_incomplete_plan_gives_unknown_not_guesses(pipeline):
    inspection = run_sample(pipeline, INCOMPLETE)
    assert inspection.overall == "UNKNOWN"
    assert statuses(inspection) == {
        "ER-1": "UNKNOWN", "ER-2": "PASS", "ER-3": "PASS",
        "FS-1": "UNKNOWN", "FS-2": "UNKNOWN", "DS-1": "UNKNOWN",
    }


def test_every_decision_has_a_full_source_reference(pipeline):
    for name in (COMPLIANT, VIOLATIONS):
        for finding in run_sample(pipeline, name).findings:
            assert finding.decision.computation
            assert finding.rule_evidence.passage.clause == finding.rule.clause
            source = finding.extraction.sources[0]
            assert source.file and source.section and source.page and source.quote


def test_results_are_repeatable(pipeline):
    def outcome():
        return [f.decision for f in run_sample(pipeline, VIOLATIONS).findings]
    assert outcome() == outcome()


def test_hallucinated_extraction_is_rejected(rules, index, audit):
    """A confident value with an invented quote must not reach a PASS."""
    def hallucinating_extractor(document, rule):
        return Extraction(
            attribute=rule.attribute, status="FOUND", value="9999", unit=rule.unit,
            confidence=0.99, method="fake_llm",
            sources=[SourceRef(
                file=document.filename, section="2", page=1, quote="Width is 9999 mm.",
            )],
        )

    pipeline = Pipeline(rules, index, audit, extractor=hallucinating_extractor)
    inspection = run_sample(pipeline, COMPLIANT)
    assert inspection.overall == "UNKNOWN"
    assert {f.extraction.status for f in inspection.findings} == {"UNVERIFIED"}


def test_changed_regulation_makes_rule_unknown(rules, audit, tmp_path):
    """If a clause no longer supports a rule, the engine must not apply it."""
    regulations = tmp_path / "regulations"
    regulations.mkdir()
    for path in REGULATIONS_DIR.glob("*.md"):
        text = path.read_text(encoding="utf-8").replace("at least 1200 mm", "at least 1500 mm")
        (regulations / path.name).write_text(text, encoding="utf-8")

    pipeline = Pipeline(rules, RegulatoryIndex(tmp_path / "chroma", regulations), audit)
    result = statuses(run_sample(pipeline, COMPLIANT))
    assert result["ER-1"] == "UNKNOWN"
    assert result["ER-2"] == "PASS"


def test_new_rule_area_needs_only_data_files(tmp_path):
    """The scalability claim: a new area is one regulation file plus one rule file."""
    regulations = tmp_path / "regulations"
    rules_dir = tmp_path / "rules"
    regulations.mkdir()
    rules_dir.mkdir()
    (regulations / "accommodation.md").write_text(
        "<!-- page: 1 -->\n## 4.2 Cabin ceilings\n"
        "The ceiling height of a cabin shall be at least 2100 mm.\n",
        encoding="utf-8",
    )
    (rules_dir / "accommodation.json").write_text(json.dumps({
        "domain": "Accommodation",
        "regulation_file": "accommodation.md",
        "rules": [{
            "id": "AC-1", "title": "Cabin ceiling height", "attribute": "ceiling_height",
            "kind": "numeric", "dimension": "length", "operator": ">=",
            "threshold": "2100", "unit": "mm", "clause": "4.2",
            "threshold_quote": "at least 2100 mm",
            "query": "minimum ceiling height of a cabin", "labels": ["cabin ceiling height"],
        }],
    }), encoding="utf-8")

    pipeline = Pipeline(
        load_rules(rules_dir),
        RegulatoryIndex(tmp_path / "chroma", regulations),
        AuditStore(tmp_path / "db.sqlite3"),
    )
    assert pipeline.run("plan.md", "Cabin ceiling height: 2.05 m").overall == "FAIL"
    assert pipeline.run("plan.md", "Cabin ceiling height: 2.2 m").overall == "PASS"
    assert pipeline.run("plan.md", "No relevant content.").overall == "UNKNOWN"


def test_each_step_is_logged(pipeline):
    inspection = run_sample(pipeline, COMPLIANT)
    events = [event["event"] for event in pipeline.audit.events(inspection.id)]
    assert events[0] == "inspection_started"
    assert events[-1] == "inspection_completed"
    assert events.count("rule_evaluated") == len(inspection.findings)
