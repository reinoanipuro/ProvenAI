"""API for the Lovable web app in web/app, mounted under /lovable.

The app was designed around "inspections": files go in, the app polls until
the inspection is done, then shows elements on the drawing with one result
per rule. This module provides that API on top of the existing pipeline:

- Design values are read from the files by the shared intake (Mistral reads,
  Python keeps only values that are really in the documents).
- Every PASS / FAIL comes from backend.rules.evaluate, as everywhere else.
- Items without an approved rule are looked up in the regulations
  (backend.checker.check_with_regulations) and always need review.
- Values found in a PDF get their position on the page, so the app can mark
  them on the drawing.

The app's types only know three element types (door, cabin, corridor) and
three statuses (PASS, FAIL, UNKNOWN), so richer results are mapped onto them:
anything uncertain is UNKNOWN or carries needs_review.
"""

import dataclasses
import json
import mimetypes
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import llm as llm_module
from .checker import _match_quote, approve_rule, check_with_regulations, verify_citation
from .documents import MAX_FILE_BYTES, MAX_FILES, new_upload_folder, safe_name
from .intake import find_items, read_files
from .rag import load_catalog
from .rules import IMPERIAL, LENGTH_TO_MM, LibraryRule, Limit, Source, evaluate, load_library, parse_limits

ROOT = Path(__file__).resolve().parent.parent
INSPECTION_DIR = ROOT / ".runtime" / "inspections"
STEPS = ["Queued", "Reading documents", "Finding design values (Mistral)", "Checking rules and regulations", "Done"]
# Regulation lookups take one to three minutes each on a laptop, so an
# inspection runs at most this many; the rest get the closest passages only.
MAX_AI_LOOKUPS = 6
RULES_ENGINE = "ProvenAI rules (Python)"
ELEMENT_TYPES = {
    "walking_route_clear_width": "corridor",
    "ramp_running_slope": "corridor",
    "handrail_height": "corridor",
    "guard_rail_height": "corridor",
    "door_clear_width": "door",
    "door_threshold_height": "door",
    "superstructure_door_sill_height": "door",
}
OWNER = "Design engineer"

_lock = threading.RLock()
_store: dict[str, dict] = {}
_proposals: dict[str, dict] = {}
_worker = ThreadPoolExecutor(max_workers=1)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def _symbol(op: str) -> str:
    return "≥" if op == ">=" else "≤"


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------- rules


def _display(limits: tuple[Limit, ...]) -> tuple[float, str]:
    """A limit in the unit the app shows: millimetres, or percent for slopes and ratios."""
    limit = next((item for item in limits if item.unit not in IMPERIAL), limits[0])
    if limit.unit in LENGTH_TO_MM:
        return round(limit.value * LENGTH_TO_MM[limit.unit], 3), "mm"
    if limit.unit == "ratio":
        return round(limit.value * 100, 2), "%"
    return limit.value, "%"


def _regulation(rule: LibraryRule, catalog: dict) -> str:
    return catalog.get(rule.source.filename, {}).get("regulation", rule.source.filename)


def _sides(rule: LibraryRule) -> list[tuple[str, str, LibraryRule]]:
    """A rule with a minimum and a maximum becomes two checks, as the app has one limit per check."""
    sides = []
    if rule.minimum:
        sides.append(("min", ">=", dataclasses.replace(rule, maximum=())))
    if rule.maximum:
        sides.append(("max", "<=", dataclasses.replace(rule, minimum=())))
    both = len(sides) == 2
    return [(f"{rule.id}-{side}" if both else rule.id, op, part) for side, op, part in sides]


def _evaluate(rule: LibraryRule, attr: dict | None) -> dict:
    """The one place this adapter turns evidence into PASS / FAIL / UNKNOWN."""
    if not attr or attr.get("value") is None:
        return {"status": "UNKNOWN", "missing": True, "reason": "No value was found in the documents."}
    others = [item for item in attr.get("conflicts") or [] if item.get("value") != attr.get("value")]
    if others:
        values = " vs ".join(
            f"{_fmt(item['value'])} {item['unit']} ({item['source_file']})" for item in [attr, *others]
        )
        return {"status": "UNKNOWN", "conflict": True, "reason": f"Sources disagree: {values}. The tool does not pick one."}
    calculation = evaluate(rule, attr.get("value_text") or f"{attr['value']} {attr['unit']}")
    return {
        "status": calculation.status,
        "missing": calculation.status == "UNKNOWN",
        "reason": f"{calculation.comparison}. {calculation.reason}" if calculation.comparison else calculation.reason,
        "margin": calculation.margin,
    }


def _tests(rule: LibraryRule, op: str, value: float, unit: str) -> list[dict]:
    step = 1 if float(value).is_integer() else 0.1
    below, above = round(value - step, 2), round(value + step, 2)
    attr = lambda number: {"value": number, "unit": unit, "value_text": f"{number} {unit}"}  # noqa: E731
    conflict = {**attr(value), "source_file": "test-a", "conflicts": [{**attr(value - step), "source_file": "test-b"}]}
    cases = [
        ("Exact boundary", value, attr(value), "PASS"),
        ("Just below limit", below, attr(below), "FAIL" if op == ">=" else "PASS"),
        ("Just above limit", above, attr(above), "PASS" if op == ">=" else "FAIL"),
        ("Missing evidence", None, None, "UNKNOWN"),
        ("Contradictory sources", "conflict", conflict, "UNKNOWN"),
    ]
    tests = []
    for name, shown, evidence, expected in cases:
        actual = _evaluate(rule, evidence)["status"]
        tests.append({"name": name, "input": shown, "expected": expected, "actual": actual, "passed": actual == expected})
    return tests


def library_checks(rule_set_ids: list[str] | None = None) -> list[dict]:
    """Approved rules as the app's checks, each with the rule it is evaluated by."""
    attributes, rules = load_library()
    catalog = load_catalog()
    checks = []
    for rule in rules:
        regulation = _regulation(rule, catalog)
        if rule_set_ids and _slug(regulation) not in rule_set_ids:
            continue
        label = attributes.get(rule.attribute, {}).get("label", rule.attribute.replace("_", " "))
        for check_id, op, part in _sides(rule):
            value, unit = _display(part.minimum or part.maximum)
            word = "too low or too small" if op == ">=" else "too high or too large"
            checks.append({
                "rule": part,
                "lovable": {
                    "id": check_id,
                    "rule_set_id": _slug(regulation),
                    "rule_set": regulation,
                    "name": rule.title,
                    "clause_ref": f"{regulation} {rule.source.section} · {rule.source.filename} p.{rule.source.page}",
                    "clause_text": rule.source.quote,
                    "applies_to": ELEMENT_TYPES.get(rule.attribute, "cabin"),
                    "condition": {
                        "attr": rule.attribute, "label": label[:1].upper() + label[1:], "op": op,
                        "value": value, "unit": unit, "deficit": word,
                    },
                    "required_inputs": [rule.attribute],
                    "tests": _tests(part, op, value, unit),
                    "recommend_fail": f"Change {{element}} by {{diff}} to meet {regulation} {rule.source.section}.",
                    "missing_owner": OWNER,
                    "status": "approved",
                },
            })
    return checks


def rule_sets() -> list[dict]:
    _, rules = load_library()
    catalog = load_catalog()
    found: dict[str, dict] = {}
    for rule in rules:
        regulation = _regulation(rule, catalog)
        entry = found.setdefault(_slug(regulation), {
            "id": _slug(regulation), "name": regulation, "authority": regulation, "description": "", "_count": 0,
        })
        entry["_count"] += 1
    return [
        {**{key: value for key, value in entry.items() if not key.startswith("_")},
         "description": f"{entry['_count']} approved rules, each checked against its regulation page."}
        for entry in found.values()
    ]


# ---------------------------------------------------------------- inspections


def _path(inspection_id: str) -> Path:
    return INSPECTION_DIR / f"{safe_name(inspection_id)}.json"


def _save(state: dict) -> None:
    INSPECTION_DIR.mkdir(parents=True, exist_ok=True)
    _path(state["id"]).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _load(inspection_id: str) -> dict:
    with _lock:
        if inspection_id not in _store:
            path = _path(inspection_id)
            if not path.is_file():
                raise HTTPException(status_code=404, detail=f"Inspection {inspection_id} not found.")
            _store[inspection_id] = json.loads(path.read_text(encoding="utf-8"))
        return _store[inspection_id]


def _all() -> list[dict]:
    if INSPECTION_DIR.is_dir():
        for path in INSPECTION_DIR.glob("*.json"):
            try:
                _load(path.stem)
            except (HTTPException, json.JSONDecodeError):
                continue
    with _lock:
        return list(_store.values())


def _public(state: dict) -> dict:
    """The inspection as the app expects it, with reviews and notes applied."""
    reviews = state.get("_reviews", {})
    results = []
    for result in state.get("results", []):
        review = reviews.get(result["id"], {})
        reviewed = bool(review.get("reviewed"))
        results.append({
            **result,
            "reviewed": reviewed,
            "needs_review": result["needs_review"] and not reviewed,
            "notes": review.get("notes", []),
            "audit": result["audit"] + review.get("events", []),
        })
    public = {key: value for key, value in state.items() if not key.startswith("_")}
    public["results"] = results
    return public


def _deck(text: str) -> str:
    match = re.search(r"\bdeck\s*([0-9]+|[a-z]+)\b", text, re.IGNORECASE)
    return f"Deck {match.group(1)}" if match else ""


def _element_type(attribute: str, name: str) -> str:
    if attribute in ELEMENT_TYPES:
        return ELEMENT_TYPES[attribute]
    lowered = name.lower()
    if re.search(r"door|hatch|opening", lowered):
        return "door"
    if re.search(r"corridor|walkway|route|ramp|stair|passage|rail|gangway", lowered):
        return "corridor"
    return "cabin"


def _locate(folder: Path, filename: str, page: int | None, value_text: str) -> list[float] | None:
    """Where a value is printed on a PDF page, in PDF points from the bottom left."""
    import pypdfium2

    path = folder / filename
    if not page or path.suffix.lower() != ".pdf" or not path.is_file():
        return None
    document = pypdfium2.PdfDocument(str(path))
    try:
        if page > len(document):
            return None
        textpage = document[page - 1].get_textpage()
        searcher = textpage.search(value_text, match_case=False)
        found = searcher.get_next()
        searcher.close()
        if found is None:
            textpage.close()
            return None
        boxes = [textpage.get_rect(index) for index in range(textpage.count_rects(*found))]
        textpage.close()
    finally:
        document.close()
    margin = 8.0
    return [
        min(box[0] for box in boxes) - margin, min(box[1] for box in boxes) - margin,
        max(box[2] for box in boxes) + margin, max(box[3] for box in boxes) + margin,
    ]


def _attr(item: dict, rule: LibraryRule | None, folder: Path) -> dict:
    """Evidence for one design value, in the unit the app shows."""
    from .rules import parse_measurement

    quantity = rule.quantity if rule else None
    measurement = parse_measurement(item["value_text"], quantity) if quantity else None
    if measurement is None:
        value, unit = None, ""
    elif measurement.unit == "ratio":
        value, unit = round(measurement.value * 100, 2), "%"
    else:
        value, unit = round(measurement.value, 2), measurement.unit
    return {
        "value": value, "unit": unit, "value_text": item["value_text"],
        "confidence": "medium",
        "quote": item.get("source_line") or f"{item['element']}: {item['value_text']}",
        "source_file": item.get("source_file") or "typed input",
        "page": item.get("source_page"),
        "section": item.get("property", ""),
        "method": "Text",
    }


def _build_elements(state: dict, items: list[dict], folder: Path) -> list[dict]:
    """One element per design element name, with each value as an attribute."""
    _, rules = load_library()
    rule_for = {rule.attribute: rule for rule in rules}
    elements: dict[str, dict] = {}
    for item in items:
        key = re.sub(r"\s+", " ", item["element"].lower()).strip()
        attribute = item["attribute"] if item["attribute"] in rule_for else _slug(item["property"] or "value").replace("-", "_")
        element = elements.get(key)
        if element is None:
            element = {
                "id": f"E{len(elements) + 1:02d}",
                "type": _element_type(item["attribute"], item["element"]),
                "name": item["element"],
                "space": "",
                "deck": _deck(f"{item['element']} {item.get('source', '')}"),
                "page": item.get("source_page") or 1,
                "bbox": [0, 0, 0, 0],
                "accessible": True,
                "attrs": {},
            }
            elements[key] = element
        evidence = _attr(item, rule_for.get(item["attribute"]), folder)
        if element["bbox"] == [0, 0, 0, 0] and item.get("source_file"):
            box = _locate(folder, item["source_file"], item.get("source_page"), item["value_text"])
            if box:
                element["bbox"], element["page"] = box, item["source_page"]
        if attribute in element["attrs"]:
            element["attrs"][attribute].setdefault("conflicts", []).append(evidence)
        else:
            element["attrs"][attribute] = evidence
        item["_element_id"], item["_attr"] = element["id"], attribute
    return list(elements.values())


def _audit(state: dict, events: list[tuple[str, str]]) -> list[dict]:
    return [{"at": _now(), "actor": actor, "event": event} for actor, event in events]


def _rule_results(state: dict, citations: dict) -> list[dict]:
    results = []
    model = f"extractor · {state.get('_model', 'Mistral')} (Ollama, local)"
    for check in library_checks(state.get("rule_set_ids")):
        rule, lovable_rule = check["rule"], check["lovable"]
        condition = lovable_rule["condition"]
        for element in state["elements"]:
            attr = element["attrs"].get(rule.attribute)
            if attr is None:
                continue
            outcome = _evaluate(rule, attr)
            citation = citations.get(rule.id, {"verified": False, "reason": "not checked"})
            evidence = [{**attr, "attr": rule.attribute, "conflicts": None}, *[
                {**other, "attr": rule.attribute} for other in attr.get("conflicts") or []
            ]]
            failed = outcome["status"] == "FAIL"
            missing = [rule.attribute] if outcome.get("missing") or outcome.get("conflict") else []
            results.append({
                "id": f"{lovable_rule['id']}:{element['id']}",
                "check_id": lovable_rule["id"],
                "element_id": element["id"],
                "status": outcome["status"],
                "needs_review": bool(outcome.get("conflict")) or not citation["verified"],
                "rule_set": lovable_rule["rule_set"],
                "clause_ref": lovable_rule["clause_ref"],
                "clause_text": lovable_rule["clause_text"],
                "check_name": lovable_rule["name"],
                "condition": f"{condition['attr']} {_symbol(condition['op'])} {_fmt(condition['value'])}",
                "required_inputs": lovable_rule["required_inputs"],
                "measured": attr.get("value") if not missing else None,
                "required": f"{_symbol(condition['op'])} {_fmt(condition['value'])}",
                "unit": condition["unit"],
                "confidence": attr.get("confidence"),
                "reason": outcome["reason"],
                "recommendation": (
                    f"Change {element['name']} by {outcome.get('margin')} to meet the requirement." if failed
                    else f"Confirm the {condition['label'].lower()} of {element['name']} with the {OWNER.lower()}." if missing
                    else "No action required."
                ),
                "missing": missing,
                "evidence": evidence,
                "audit": _audit(state, [
                    ("ingest", f"Read {len(state['files'])} files"),
                    (model, f"Found {rule.attribute} = {attr['value_text']} in {attr['source_file']}"
                            + (f" p.{attr['page']}" if attr.get("page") else "")),
                    (RULES_ENGINE, f"Evaluated {condition['attr']} {_symbol(condition['op'])} {_fmt(condition['value'])} → {outcome['status']}"),
                    ("citation check", "Quote confirmed on the regulation page" if citation["verified"]
                     else f"Quote not confirmed: {citation['reason']}"),
                ]),
            })
    return results


def _ai_result(state: dict, item: dict, found: dict) -> dict:
    """A result read from the regulation text by Mistral; it always needs review."""
    citation = found.get("citation") or {}
    passages = found.get("passages") or []
    passage = passages[0] if passages else {}
    element = next(element for element in state["elements"] if element["id"] == item["_element_id"])
    attr = element["attrs"].get(item["_attr"], {})
    numeric = found.get("status") in ("PASS", "FAIL")
    clause_ref = (
        f"{found.get('regulation', '')} {citation.get('section', '')} · {citation.get('filename', '')} p.{citation.get('page', '')}"
        if citation else f"Closest passage: {passage.get('filename', '')} p.{passage.get('page', '')}"
    )
    confidence = found.get("confidence")
    return {
        "id": f"AI-{item['_attr']}:{element['id']}",
        "check_id": found.get("rule_id") or f"AI-{item['_attr']}",
        "element_id": element["id"],
        "status": found["status"] if numeric else "UNKNOWN",
        "needs_review": True,
        "rule_set": "Read from regulation by AI",
        "clause_ref": clause_ref.strip(" ·"),
        "clause_text": citation.get("quote") or (passage.get("text") or "")[:400],
        "check_name": f"{item['property'] or item['element']} ({'AI-read, ' + confidence + ' confidence' if confidence else 'manual review'})",
        "condition": found.get("comparison") or "",
        "required_inputs": [item["_attr"]],
        "measured": attr.get("value") if numeric else None,
        "required": found.get("required") or "",
        "unit": attr.get("unit") or "",
        "confidence": confidence,
        "reason": found.get("answer") or found.get("reason") or "",
        "recommendation": (
            "Confirm this requirement applies, then approve it as a rule or correct the design."
            if found.get("level") == "ai_read" else
            "No approved rule or stated limit was found. Review the closest regulation passages by hand."
        ),
        "missing": [] if numeric else [item["_attr"]],
        "evidence": [{**attr, "attr": item["_attr"], "conflicts": None}] if attr else [],
        "audit": _audit(state, [
            ("regulation search", f"Searched the regulations for {item['property'] or item['element']}"),
            (f"reader · {state.get('_model', 'Mistral')} (Ollama, local)",
             f"Read the requirement from {citation.get('filename', 'the closest passages')}"
             + (f", {confidence} confidence after Python's review" if confidence else ", nothing reliable found")),
            (RULES_ENGINE, f"Evaluated {found.get('comparison')} → {found['status']}" if numeric else "Not evaluated: needs review"),
        ]),
    }


def _questions(state: dict) -> list[dict]:
    """Missing or unreadable values the engineer can enter to resolve UNKNOWN checks."""
    attributes, _ = load_library()
    questions: dict[str, dict] = {}
    for result in state["results"]:
        if result["status"] != "UNKNOWN" or result["check_id"].startswith("AI-"):
            continue
        for attr in result["missing"]:
            label = attributes.get(attr, {}).get("label", attr.replace("_", " "))
            question = questions.setdefault(attr, {
                "attr": attr, "label": label[:1].upper() + label[1:], "unit": result["unit"], "owner": OWNER,
                "resolves_count": 0, "element_ids": [], "check_ids": [],
            })
            question["resolves_count"] += 1
            if result["element_id"] not in question["element_ids"]:
                question["element_ids"].append(result["element_id"])
            question["check_ids"].append(result["id"])
    return sorted(questions.values(), key=lambda question: -question["resolves_count"])


def _evaluate_all(state: dict) -> None:
    state["results"] = _rule_results(state, state.get("_citations", {})) + state.get("_ai_results", [])
    state["questions"] = _questions(state)


def _progress(state: dict, step: int, label: str | None = None) -> None:
    with _lock:
        state["progress"] = {"step": step, "label": label or STEPS[step]}
        state["status"] = "done" if step >= 4 else "queued" if step == 0 else "running"
        _save(state)


def _run(state: dict, files: list[tuple[str, bytes]], get_llm, get_retriever) -> None:
    folder = ROOT / state["_folder"]
    try:
        _progress(state, 1)
        documents, warnings = read_files(files, folder)
        _progress(state, 2)
        attributes, rules = load_library()
        llm = get_llm()
        state["_model"] = getattr(llm, "model", "Mistral")
        items, item_warnings = find_items(documents, llm, attributes)
        state["_warnings"] = warnings + item_warnings
        _progress(state, 3)
        with _lock:
            state["elements"] = _build_elements(state, items, folder)
        retriever = get_retriever()
        state["_citations"] = {
            rule.id: {key: value for key, value in verify_citation(rule, retriever).items() if key != "passage"}
            for rule in rules
        }
        catalog = load_catalog()
        ai_results = []
        unmatched = [item for item in items if item["attribute"] not in {rule.attribute for rule in rules}]
        for number, item in enumerate(unmatched, start=1):
            _progress(state, 3, f"Looking up item {number} of {len(unmatched)} in the regulations")
            found = check_with_regulations(
                item, llm if number <= MAX_AI_LOOKUPS else None, retriever, catalog
            )
            ai_results.append(_ai_result(state, item, found))
        with _lock:
            state["_ai_results"] = ai_results
            _evaluate_all(state)
        _progress(state, 4)
    except Exception as error:  # noqa: BLE001 - the app shows any failure as an error state
        with _lock:
            state["status"] = "error"
            state["progress"] = {"step": state["progress"]["step"], "label": f"Failed: {error}"}
            _save(state)


# ---------------------------------------------------------------- proposals


def _propose(payload: dict, get_retriever) -> dict:
    """A rule proposed from pasted regulation text, kept as a proposal until approved.

    Approval needs the text's source page, so the regulations are searched for
    it; without a source the proposal can be tested but not approved.
    """
    text = str(payload.get("text", "")).strip()
    lowered = text.lower()
    op = ">=" if re.search(r"at least|minimum|not less than|no less than", lowered) else (
        "<=" if re.search(r"maximum|not exceed|not more than|no more than|at most", lowered) else None
    )
    quantity = "length"
    limits = parse_limits(text, quantity) or parse_limits(text, "percentage")
    if limits and limits[0].unit == "percent":
        quantity = "percentage"
    if not op or not limits:
        return {"ok": False, "error": "No measurable limit with minimum or maximum wording was found. Nothing was proposed."}

    source = None
    retriever = get_retriever()
    if retriever is not None:
        for passage in retriever.search(text, top_k=5):
            quote, _ = _match_quote(text, passage["text"])
            if quote:
                source = Source(passage["filename"], passage["page"], passage.get("section", ""), quote)
                break
    attribute = _slug(payload.get("name") or "proposed value").replace("-", "_")
    rule = LibraryRule(
        id=f"PROPOSED-{attribute}", title=str(payload.get("name") or "Proposed rule"), attribute=attribute,
        quantity=quantity, minimum=limits if op == ">=" else (), maximum=limits if op == "<=" else (),
        required_text=next((match.group(0) for match in re.finditer(r"\d+(?:[.,]\d+)?\s*\S+", text)), ""),
        exceptions="", source=source or Source("", 0, "", text),
    )
    value, unit = _display(limits)
    lovable_rule = {
        "id": rule.id, "rule_set_id": payload.get("rule_set_id") or "", "rule_set": payload.get("rule_set_id") or "",
        "name": rule.title,
        "clause_ref": payload.get("clause_ref") or (f"{source.filename} p.{source.page}" if source else "No source found"),
        "clause_text": text, "applies_to": payload.get("applies_to") or "cabin",
        "condition": {"attr": attribute, "label": rule.title, "op": op, "value": value, "unit": unit,
                      "deficit": "below minimum" if op == ">=" else "above maximum"},
        "required_inputs": [attribute], "tests": _tests(rule, op, value, unit),
        "recommend_fail": "Change {element} by {diff} to comply.", "missing_owner": OWNER, "status": "proposed",
    }
    with _lock:
        _proposals[rule.id] = {"lovable": lovable_rule, "rule": rule, "has_source": source is not None}
    return {"ok": True, "rule": lovable_rule}


# ---------------------------------------------------------------- routes


def create_router(get_llm, get_retriever) -> APIRouter:
    router = APIRouter(tags=["Lovable web app"])

    @router.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @router.get("/rulesets")
    def list_rule_sets() -> list[dict]:
        return rule_sets()

    @router.get("/rules")
    def list_rules() -> list[dict]:
        with _lock:
            proposed = [entry["lovable"] for entry in _proposals.values()]
        return [check["lovable"] for check in library_checks()] + proposed

    @router.post("/rules")
    def propose_rule(payload: dict) -> dict:
        return _propose(payload, get_retriever)

    @router.post("/rules/{rule_id}/approve")
    def approve(rule_id: str, payload: dict) -> dict:
        approved = {check["lovable"]["id"]: check["lovable"] for check in library_checks()}
        if rule_id in approved:
            return approved[rule_id]
        with _lock:
            entry = _proposals.get(rule_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"No proposed rule {rule_id}.")
        if any(not test.get("passed") for test in entry["lovable"]["tests"]):
            raise HTTPException(status_code=422, detail="Every self-test must pass before approval.")
        if not entry["has_source"]:
            raise HTTPException(
                status_code=422,
                detail="This text was not found in the regulation PDFs, so it cannot be approved without a source page.",
            )
        rule: LibraryRule = entry["rule"]
        proposal = {
            "attribute": {"name": rule.attribute, "label": rule.title, "quantity": rule.quantity},
            "rule": {
                "id": rule.id.replace("PROPOSED-", "CANDIDATE-"), "title": rule.title, "attribute": rule.attribute,
                "required_text": rule.required_text, "exceptions": "",
                "source": dataclasses.asdict(rule.source),
                **({"min": [dataclasses.asdict(limit) for limit in rule.minimum]} if rule.minimum else {}),
                **({"max": [dataclasses.asdict(limit) for limit in rule.maximum]} if rule.maximum else {}),
            },
        }
        try:
            approve_rule(proposal)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        with _lock:
            _proposals.pop(rule_id, None)
        return {**entry["lovable"], "status": "approved"}

    @router.get("/inspections")
    def list_inspections() -> list[dict]:
        summaries = []
        for state in sorted(_all(), key=lambda state: state["created_at"], reverse=True):
            public = _public(state)
            results = public["results"]
            summaries.append({
                "id": state["id"], "name": state["name"], "created_at": state["created_at"],
                "file_count": len(state["files"]), "status": state["status"],
                "counts": {
                    "pass": sum(result["status"] == "PASS" for result in results),
                    "fail": sum(result["status"] == "FAIL" for result in results),
                    "unknown": sum(result["status"] == "UNKNOWN" for result in results),
                    "review": sum(bool(result["needs_review"]) for result in results),
                },
            })
        return summaries

    @router.get("/inspections/{inspection_id}")
    def get_inspection(inspection_id: str) -> dict:
        with _lock:
            return _public(_load(inspection_id))

    @router.post("/inspections")
    def create_inspection(
        name: str = Form(default=""),
        files: list[UploadFile] = File(...),
        ruleset_ids: list[str] = Form(default=[]),
    ) -> dict:
        if len(files) > MAX_FILES:
            raise HTTPException(status_code=422, detail=f"Drop at most {MAX_FILES} files at a time.")
        upload_id, folder = new_upload_folder()
        folder.mkdir(parents=True, exist_ok=True)
        received, listed = [], []
        for number, upload in enumerate(files):
            data = upload.file.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                continue
            filename = safe_name(upload.filename or f"file{number}")
            (folder / filename).write_bytes(data)
            received.append((filename, data))
            entry = {"id": f"f{number}", "name": filename, "size": len(data),
                     "type": upload.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"}
            if filename.lower().endswith(".pdf"):
                import pypdfium2

                try:
                    document = pypdfium2.PdfDocument(data)
                    entry["pages"] = len(document)
                    document.close()
                except pypdfium2.PdfiumError:
                    pass
            listed.append(entry)
        state = {
            "id": f"insp-{upload_id}", "name": name.strip() or "Untitled inspection", "project": "",
            "created_at": _now(), "status": "queued", "progress": {"step": 0, "label": STEPS[0]},
            "rule_set_ids": [item for item in ruleset_ids if item], "files": listed,
            "elements": [], "results": [], "questions": [],
            "_folder": str(folder.relative_to(ROOT)) if folder.is_relative_to(ROOT) else str(folder),
            "_reviews": {}, "_ai_results": [], "_citations": {}, "_started": time.time(),
        }
        with _lock:
            _store[state["id"]] = state
            _save(state)
        _worker.submit(_run, state, received, get_llm, get_retriever)
        return {"id": state["id"]}

    @router.post("/inspections/{inspection_id}/answers")
    def submit_answers(inspection_id: str, payload: dict) -> dict:
        with _lock:
            state = _load(inspection_id)
            units = {check["rule"].attribute: check["lovable"]["condition"]["unit"] for check in library_checks()}
            for answer in payload.get("answers", []):
                element = next((item for item in state["elements"] if item["id"] == answer.get("element_id")), None)
                value = answer.get("value")
                if element is None or not isinstance(value, (int, float)):
                    continue
                attr = answer.get("attr", "")
                unit = units.get(attr, "mm")
                element["attrs"][attr] = {
                    "value": value, "unit": unit, "value_text": f"{value} {unit}", "confidence": "high",
                    "quote": f"Entered by engineer: {value} {unit}", "source_file": "Manual entry",
                    "page": None, "section": "Missing information form", "method": "Engineer input",
                }
            _evaluate_all(state)
            _save(state)
            return _public(state)

    @router.post("/inspections/{inspection_id}/results/{result_id}/review")
    def mark_reviewed(inspection_id: str, result_id: str) -> dict:
        with _lock:
            state = _load(inspection_id)
            review = state["_reviews"].setdefault(result_id, {"notes": [], "events": []})
            review["reviewed"] = True
            review["events"].append({"at": _now(), "actor": "engineer", "event": "Marked as reviewed"})
            _save(state)
            return _public(state)

    @router.post("/inspections/{inspection_id}/results/{result_id}/notes")
    def add_note(inspection_id: str, result_id: str, payload: dict) -> dict:
        note = str(payload.get("note", "")).strip()[:2000]
        with _lock:
            state = _load(inspection_id)
            if note:
                review = state["_reviews"].setdefault(result_id, {"notes": [], "events": []})
                review["notes"].append(note)
                review["events"].append({"at": _now(), "actor": "engineer", "event": f"Note: {note}"})
                _save(state)
            return _public(state)

    @router.get("/inspections/{inspection_id}/files/{file_id}")
    def get_file(inspection_id: str, file_id: str) -> FileResponse:
        with _lock:
            state = _load(inspection_id)
        entry = next((item for item in state["files"] if item["id"] == file_id), None)
        if entry is None:
            raise HTTPException(status_code=404, detail="File not found.")
        path = (ROOT / state["_folder"] / entry["name"]).resolve()
        if not path.is_file():
            raise HTTPException(status_code=404, detail="File not found.")
        return FileResponse(path, media_type=entry["type"], filename=entry["name"])

    return router
