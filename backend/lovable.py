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
  them in red where they are printed.
- The result is shown as soon as Python has checked the values. Mistral then
  writes the summary and reads the regulations for values no rule covers, in
  the background ("refining"), and the result updates as it goes.
- Every result names its regulation file and page, and the inspection has
  step-by-step next steps for the engineer, made by Python from the results.

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
from .checker import check_with_regulations, unsupported_numbers, verify_citation
from .documents import (
    MAX_FILE_BYTES, MAX_FILES, TEXT_TYPES, new_upload_folder, read_document, safe_name,
)
from .intake import find_items, read_files
from .rag import load_catalog
from .rules import IMPERIAL, LENGTH_TO_MM, LibraryRule, Limit, evaluate, load_library

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
_worker = ThreadPoolExecutor(max_workers=1)
# The slow AI part runs after the result is shown, one inspection at a time.
_refiner = ThreadPoolExecutor(max_workers=1)
# Rule quotes confirmed in the regulation index; they only change with the rule library.
_citation_cache: dict[tuple, dict] = {}
RANK = {"FAIL": 0, "UNKNOWN": 1, "PASS": 2}
AI_RULE_SET = "Read from regulation by AI"


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
                    "recommend_fail": f"Change {{element}} by {{diff}} to meet {regulation} {rule.source.section}.",
                    "missing_owner": OWNER,
                    "status": "approved",
                },
            })
    return checks


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
            _store[inspection_id] = _after_restart(json.loads(path.read_text(encoding="utf-8")))
        return _store[inspection_id]


def _after_restart(state: dict) -> dict:
    """A check read from disk has no job running: close what the last run left unfinished."""
    if state.get("status") in ("queued", "running"):
        state["status"] = "error"
        state["progress"] = {**state.get("progress", {}), "label": "The checker was restarted before this check finished. Drop the document again."}
    if state.get("refining"):
        state["refining"] = False
        state["progress"] = {"step": 4, "label": "Done"}
        if state.get("summary"):
            state["summary"].setdefault("note", "The AI step did not finish because the checker was restarted, so Python's summary is shown.")
    # Checks saved before next steps and summaries existed get them from their results.
    if state.get("status") == "done" and "next_steps" not in state:
        state["next_steps"] = _next_steps(state)
    if state.get("status") == "done" and not state.get("summary"):
        state["summary"] = {"text": _template_summary(state), "source": "python"}
    return state


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
    """The inspection as the app sees it, without the internal fields."""
    return {key: value for key, value in state.items() if not key.startswith("_")}


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


def _locate(folder: Path, filename: str, page: int | None, texts: list[str]) -> list[float] | None:
    """Where the first of these texts is printed on a PDF page, in PDF points from the bottom left."""
    import pypdfium2

    path = folder / filename
    if not page or path.suffix.lower() != ".pdf" or not path.is_file():
        return None
    document = pypdfium2.PdfDocument(str(path))
    try:
        if page > len(document):
            return None
        textpage = document[page - 1].get_textpage()
        boxes = []
        for text in texts:
            if len(text.strip()) < 2:
                continue
            searcher = textpage.search(text.strip(), match_case=False)
            found = searcher.get_next()
            searcher.close()
            if found is not None:
                boxes = [textpage.get_rect(index) for index in range(textpage.count_rects(*found))]
                break
        textpage.close()
        if not boxes:
            return None
    finally:
        document.close()
    margin = 1.5
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
        "order": item.get("source_order"),
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
        if item.get("source_file"):
            # The whole printed line is searched first: a value like "800 mm"
            # can appear several times on a page, the full line rarely does.
            line = (item.get("source_line") or "").split(" | ")[-1].strip()
            box = _locate(folder, item["source_file"], item.get("source_page"), [line, item["value_text"]])
            evidence["bbox"] = box
            if box and element["bbox"] == [0, 0, 0, 0]:
                element["bbox"], element["page"] = box, item["source_page"]
            elif box and element["page"] == item["source_page"]:
                # The mark covers every value of the element on that page.
                element["bbox"] = [
                    min(element["bbox"][0], box[0]), min(element["bbox"][1], box[1]),
                    max(element["bbox"][2], box[2]), max(element["bbox"][3], box[3]),
                ]
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
                "sources": [{
                    "filename": rule.source.filename, "page": rule.source.page, "section": rule.source.section,
                    "quote": rule.source.quote, "verified": bool(citation["verified"]), "closest": False,
                }],
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
        "rule_set": AI_RULE_SET,
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
        "sources": [{
            "filename": citation.get("filename", ""), "page": citation.get("page"), "section": citation.get("section", ""),
            "quote": citation.get("quote", ""), "verified": True, "closest": False,
        }] if citation else [{
            "filename": passage_item.get("filename", ""), "page": passage_item.get("page"),
            "section": passage_item.get("section") or "", "quote": (passage_item.get("text") or "")[:600],
            "verified": False, "closest": True,
        } for passage_item in passages[:3]],
        "audit": _audit(state, [
            ("regulation search", f"Searched the regulations for {item['property'] or item['element']}"),
            (f"reader · {state.get('_model', 'Mistral')} (Ollama, local)",
             f"Read the requirement from {citation.get('filename', 'the closest passages')}"
             + (f", {confidence} confidence after Python's review" if confidence else ", nothing reliable found")),
            (RULES_ENGINE, f"Evaluated {found.get('comparison')} → {found['status']}" if numeric else "Not evaluated: needs review"),
        ]),
    }


def _evaluate_all(state: dict) -> None:
    state["results"] = _rule_results(state, state.get("_citations", {})) + state.get("_ai_results", [])
    state["next_steps"] = _next_steps(state)


def _groups(state: dict) -> list[dict]:
    """One entry per design value: its element, the worst status, and every result for it.

    Several rule sets can check the same value (ADA and PVAG), and the engineer
    should see one finding for it, not one per rule.
    """
    elements = {element["id"]: element for element in state.get("elements", [])}
    grouped: dict[tuple, list[dict]] = {}
    for result in state.get("results", []):
        grouped.setdefault((result["element_id"], ",".join(result["required_inputs"])), []).append(result)
    groups = []
    for (element_id, inputs), results in grouped.items():
        results = sorted(results, key=lambda result: RANK[result["status"]])
        element = elements.get(element_id, {"name": element_id, "attrs": {}})
        attr = element.get("attrs", {}).get(inputs.split(",")[0], {}) if inputs else {}
        groups.append({"element": element, "attr": attr, "status": results[0]["status"], "main": results[0], "results": results})
    return sorted(groups, key=lambda group: (RANK[group["status"]], group["element"].get("name", "")))


def _where(source: dict | None) -> str:
    return f"{source.get('filename', '')}, page {source.get('page')}" if source and source.get("filename") else ""


def _rules_text(results: list[dict]) -> str:
    names = []
    for result in results:
        name = result["clause_ref"].split(" · ")[0].strip()
        if name and name not in names:
            names.append(name)
    return " and ".join(names)


def _next_steps(state: dict) -> list[dict]:
    """What the engineer should do now, in order, worked out by Python from the results.

    Fixes come first, then values the engineer must confirm or check by hand,
    then anything that could not be read. Each step points to the results it
    resolves and to the regulation page to read.
    """
    attributes, _ = load_library()
    steps: list[dict] = []

    def add(kind: str, title: str, detail: str, group: dict | None = None, source: dict | None = None) -> None:
        position = group["attr"].get("order") if group else None
        steps.append({
            "kind": kind, "title": title, "detail": detail,
            "result_ids": [result["id"] for result in group["results"]] if group else [],
            "element_id": group["element"].get("id") if group else None,
            "source": source,
            "_order": position if position is not None else 10**9,
        })

    groups = _groups(state)
    for group in groups:
        if group["status"] != "FAIL":
            continue
        name, main, attr = group["element"].get("name", ""), group["main"], group["attr"]
        source = (main.get("sources") or [None])[0]
        failing = [result for result in group["results"] if result["status"] == "FAIL"]
        ai = main["rule_set"] == AI_RULE_SET
        where = _where(source)
        add(
            "confirm" if ai else "fix",
            f"{'Confirm and fix' if ai else 'Fix'} {name}: {main['check_name']}",
            f"The document gives {attr.get('value_text', main['measured'])}; {_rules_text(failing)} "
            f"require{'s' if len(failing) == 1 else ''} {main['required']} {main['unit']}. {main['recommendation']}"
            + (f" Read {where}." if where else "")
            + (" The limit was read by AI: confirm it applies before changing the design." if ai else ""),
            group, source,
        )
    for group in groups:
        if group["status"] != "UNKNOWN":
            continue
        name, main, attr = group["element"].get("name", ""), group["main"], group["attr"]
        source = (main.get("sources") or [None])[0]
        label = attributes.get(main["required_inputs"][0], {}).get("label", "") if main["required_inputs"] else ""
        if "disagree" in main["reason"]:
            values = ", ".join(dict.fromkeys(
                [attr.get("value_text", "")] + [item.get("value_text", "") for item in attr.get("conflicts") or []]
            ))
            add("confirm", f"Confirm one value for {name}",
                f"The documents give different values ({values}). Correct the document so it states one value, "
                "then check it again.", group, source)
        elif main["rule_set"] == AI_RULE_SET:
            where = _where(source)
            place = f"Start with {where}, the closest passage found." if where else (
                "No regulation passage matched; the regulation that covers it may be missing from the index."
            )
            add("check", f"Check by hand: {name} ({attr.get('value_text', '')})",
                f"No approved rule covers this value, and the AI could not read a clear limit for it. {place}",
                group, source)
        else:
            add("measure", f"State the {label or 'value'} of {name}",
                f"The document does not state it clearly, so {_rules_text(group['results'])} could not be checked. "
                "Add the value to the document and check it again.", group, source)
    # The engineer works down the document, so the notes follow the order of the values in it.
    steps.sort(key=lambda step: step["_order"])
    for warning in state.get("warnings", [])[:5]:
        add("check", "Check what could not be read", warning)
    if not groups:
        add("check", "No design values were found",
            "Make sure the document states values with units next to what they describe, "
            "such as 'Corridor 5-12, clear width: 850 mm', then check it again.")
    elif steps:
        add("recheck", "Check the corrected document again",
            "When the changes are made, drop the revised document on the start page to confirm every issue is closed.")
    else:
        add("info", "No action needed",
            f"All {len(groups)} values that were found meet the regulations. Keep this result as the check record.")
    for number, step in enumerate(steps, start=1):
        step["number"] = number
        step.pop("_order", None)
    return steps


def _facts(state: dict, limit: int = 30) -> list[dict]:
    """The checked results, as plain facts for Mistral's summary."""
    facts = []
    for group in _groups(state)[:limit]:
        main = group["main"]
        fact = {
            "element": group["element"].get("name", ""),
            "check": main["check_name"],
            "result": {"FAIL": "FAIL", "PASS": "PASS"}.get(group["status"], "not checked"),
            "design": group["attr"].get("value_text", ""),
        }
        if main["required"]:
            fact["required"] = f"{main['required']} {main['unit']}".strip()
        if main["rule_set"] == AI_RULE_SET and group["status"] != "UNKNOWN":
            fact["result"] = f"possible {group['status']}"
            fact["confidence"] = main.get("confidence") or "low"
        elif group["status"] != "UNKNOWN":
            fact["regulation"] = _rules_text(group["results"])
        facts.append(fact)
    return facts


def _template_summary(state: dict) -> str:
    """Python's own summary, shown until Mistral's is ready or if Mistral's fails the number check."""
    groups = _groups(state)
    if not groups:
        return "No design values with a matching rule were found in the documents, so nothing was checked."
    fails = [group for group in groups if group["status"] == "FAIL"]
    unknown = [group for group in groups if group["status"] == "UNKNOWN"]
    passed = [group for group in groups if group["status"] == "PASS"]
    parts = []
    if fails:
        listed = "; ".join(
            f"{group['element'].get('name', '')} has {group['attr'].get('value_text', '')} where "
            f"{group['main']['required']} {group['main']['unit']} is required"
            for group in fails[:5]
        )
        parts.append(f"{len(fails)} of {len(groups)} values do not meet the regulations: {listed}"
                     + ("; and more, see the list." if len(fails) > 5 else "."))
    if passed:
        parts.append(f"{len(passed)} value{'s' if len(passed) != 1 else ''} meet the regulations.")
    if unknown:
        parts.append(f"{len(unknown)} value{'s' if len(unknown) != 1 else ''} could not be checked automatically "
                     "and need an engineer's review.")
    if not fails and not unknown:
        parts.insert(0, "The design meets every regulation that was checked.")
    return " ".join(parts)


def _write_summary(state: dict, llm) -> None:
    """Mistral explains the results; Python rejects the summary if it has a number not in them."""
    with _lock:
        state["progress"] = {"step": 4, "label": "Done · AI is writing the summary"}
        _save(state)
        facts = _facts(state)
    if not facts:
        return
    try:
        text = llm_module.summarize(llm, facts)
    except llm_module.LLMUnavailableError as error:
        with _lock:
            state["summary"]["note"] = f"The AI summary is not available ({error}), so Python's summary is shown."
        return
    extra = unsupported_numbers(text, facts)
    with _lock:
        _mark(state, "AI summary")
        if text and not extra:
            state["summary"] = {"text": text, "source": "mistral"}
        else:
            state["summary"] = {
                "text": _template_summary(state), "source": "python",
                "note": "The AI summary used numbers that are not in the results, so Python's summary is shown.",
            }
        _save(state)


def _mark(state: dict, label: str) -> None:
    """When each stage ended, in seconds from the upload, so the time can be shown and improved."""
    state.setdefault("timings", []).append({"label": label, "at": round(time.time() - state.get("_started", time.time()), 1)})


def _progress(state: dict, step: int, label: str | None = None) -> None:
    with _lock:
        if step > state.get("progress", {}).get("step", 0) and step > 1:
            _mark(state, STEPS[step - 1])
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
        _progress(state, 2)
        items, item_warnings = find_items(documents, llm, attributes)
        _progress(state, 3)
        with _lock:
            state["elements"] = _build_elements(state, items, folder)
        retriever = get_retriever()
        state["_citations"] = _citations(rules, retriever)
        catalog = load_catalog()
        covered = {rule.attribute for rule in rules}
        unmatched = _uncovered_items(items, covered)
        ai_results = []
        for number, item in enumerate(unmatched, start=1):
            # Only the regulation search here, which takes seconds; Mistral reads the passages afterwards.
            _progress(state, 3, f"Finding regulation passages for values no rule covers ({number} of {len(unmatched)})")
            ai_results.append(_ai_result(state, item, check_with_regulations(item, None, retriever, catalog)))
        with _lock:
            state["warnings"] = warnings + item_warnings
            state["_ai_results"] = ai_results
            _evaluate_all(state)
            state["summary"] = {"text": _template_summary(state), "source": "python"}
            state["refining"] = True
            state["duration_s"] = round(time.time() - state["_started"])
        _progress(state, 4, "Done · AI is writing the summary")
        _refiner.submit(_refine, state, unmatched, llm, retriever, catalog)
    except Exception as error:  # noqa: BLE001 - the app shows any failure as an error state
        with _lock:
            state["status"] = "error"
            state["refining"] = False
            state["progress"] = {"step": state["progress"]["step"], "label": f"Failed: {error}"}
            _save(state)


def _uncovered_items(items: list[dict], covered: set[str]) -> list[dict]:
    """Items for the AI lookup: values no rule covers, without repeats of a value a rule already checks.

    Mistral can read one printed value twice, once matched to a rule and once as an
    unknown property. The second reading must not become a separate "to check" finding.
    """
    def same_value(item: dict) -> tuple:
        line = (item.get("source_line") or "").split(" | ")[-1]
        squash = lambda text: re.sub(r"\s+", " ", str(text or "")).strip().lower()
        return (squash(item["element"]), squash(item["value_text"]), squash(line), item.get("source_file"), item.get("source_page"))

    checked = {same_value(item) for item in items if item["attribute"] in covered}
    unmatched, seen = [], set()
    for item in items:
        key = same_value(item)
        if item["attribute"] in covered or key in checked or key in seen:
            continue
        seen.add(key)
        unmatched.append(item)
    return unmatched


def _citations(rules: list[LibraryRule], retriever) -> dict:
    """Each rule's quote confirmed on its regulation page, worked out once per rule."""
    citations = {}
    for rule in rules:
        key = (rule.id, rule.source.filename, rule.source.page, rule.source.quote, rule.required_text)
        with _lock:
            cached = _citation_cache.get(key)
        if cached is None:
            cached = {name: value for name, value in verify_citation(rule, retriever).items() if name != "passage"}
            if retriever is not None:
                with _lock:
                    _citation_cache[key] = cached
        citations[rule.id] = cached
    return citations


def _refine(state: dict, unmatched: list[dict], llm, retriever, catalog: dict) -> None:
    """After the result is shown: Mistral's summary, then Mistral reads the regulations for uncovered values."""
    try:
        _write_summary(state, llm)
        lookups = unmatched[:MAX_AI_LOOKUPS]
        changed = False
        for number, item in enumerate(lookups, start=1):
            with _lock:
                state["progress"] = {
                    "step": 4,
                    "label": f"Done · AI is reading the regulations for value {number} of {len(lookups)} that no rule covers",
                }
                _save(state)
            result = _ai_result(state, item, check_with_regulations(item, llm, retriever, catalog))
            with _lock:
                state["_ai_results"] = [result if old["id"] == result["id"] else old for old in state["_ai_results"]]
                _evaluate_all(state)
                _save(state)
            changed = changed or result["status"] != "UNKNOWN"
        if changed:
            _write_summary(state, llm)
    except Exception as error:  # noqa: BLE001 - the shown result stays; only the refinement stops
        with _lock:
            state.setdefault("warnings", []).append(f"The AI step stopped early: {error}")
    finally:
        with _lock:
            _mark(state, "AI finished")
            state["refining"] = False
            state["progress"] = {"step": 4, "label": "Done"}
            _save(state)


def warm_up(get_retriever) -> None:
    """Load the regulation search and confirm the rule quotes before the first upload."""
    def run() -> None:
        try:
            _citations(load_library()[1], get_retriever())
        except Exception:  # noqa: BLE001 - the first inspection does this itself if warm-up fails
            pass

    _worker.submit(run)


# ---------------------------------------------------------------- routes


def create_router(get_llm, get_retriever) -> APIRouter:
    router = APIRouter(tags=["Lovable web app"])

    @router.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @router.get("/inspections")
    def list_inspections() -> list[dict]:
        summaries = []
        for state in sorted(_all(), key=lambda state: state["created_at"], reverse=True):
            # One count per design value, as on the result page: a value checked by ADA and PVAG counts once.
            statuses = [group["status"] for group in _groups(state)]
            summaries.append({
                "id": state["id"], "name": state["name"], "created_at": state["created_at"],
                "file_count": len(state["files"]), "status": state["status"],
                "counts": {
                    "pass": statuses.count("PASS"), "fail": statuses.count("FAIL"), "unknown": statuses.count("UNKNOWN"),
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
            "elements": [], "results": [],
            "summary": None, "next_steps": [], "warnings": [], "refining": False,
            "_folder": str(folder.relative_to(ROOT)) if folder.is_relative_to(ROOT) else str(folder),
            "_ai_results": [], "_citations": {}, "_started": time.time(),
        }
        with _lock:
            _store[state["id"]] = state
            _save(state)
        _worker.submit(_run, state, received, get_llm, get_retriever)
        return {"id": state["id"]}

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

    @router.get("/inspections/{inspection_id}/files/{file_id}/text")
    def get_file_text(inspection_id: str, file_id: str) -> dict:
        """The text of a text or Word file, so the app can show it with the issues marked."""
        with _lock:
            state = _load(inspection_id)
        entry = next((item for item in state["files"] if item["id"] == file_id), None)
        path = (ROOT / state["_folder"] / entry["name"]).resolve() if entry else None
        if path is None or not path.is_file() or path.suffix.lower() not in TEXT_TYPES | {".docx"}:
            raise HTTPException(status_code=404, detail="No text view for this file.")
        document = read_document(entry["name"], path.read_bytes(), path.parent)
        return {"pages": [{"page": page.number, "text": page.text} for page in document.pages]}

    return router
