"""Design check: design items -> rules -> calculation -> citation check -> summary.

Mistral reads the input and writes the summary. Python does everything that
decides the result: matching rules, calculating, and checking that the cited
regulation text really says what the rule library says.
"""

import json
import re

from . import llm as llm_module
from .rag import load_catalog
from .rules import LibraryRule, evaluate, load_library

NO_RULE = "NO_RULE"
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_SMALL_COUNTS = {str(number) for number in range(0, 21)}


def _normalize(text: str) -> str:
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def accept_items(items: list[dict], text: str | None, attributes: dict) -> tuple[list[dict], list[str]]:
    """Keep only items whose value is really in the input, so none are invented."""
    accepted: list[dict] = []
    warnings: list[str] = []
    source = _normalize(text) if text is not None else None
    for item in items:
        value_text = item.get("value_text", "").strip()
        attribute = item.get("attribute", llm_module.UNKNOWN_ATTRIBUTE)
        element = item.get("element", "").strip() or "design item"
        if not value_text:
            warnings.append(f"'{element}' has no value, so it was skipped.")
            continue
        if source is not None and _normalize(value_text) not in source:
            warnings.append(
                f"'{value_text}' for '{element}' is not in the input text, so it was rejected."
            )
            continue
        if attribute not in attributes:
            attribute = llm_module.UNKNOWN_ATTRIBUTE
        accepted.append({"element": element, "attribute": attribute, "value_text": value_text})
    return accepted, warnings


def verify_citation(rule: LibraryRule, retriever) -> dict:
    """Find the rule's quote in the indexed regulation text, on the stated page."""
    source = rule.source
    citation = {
        "filename": source.filename,
        "page": source.page,
        "section": source.section,
        "quote": source.quote,
        "verified": False,
        "reason": "",
    }
    if _normalize(rule.required_text) not in _normalize(source.quote):
        citation["reason"] = "The rule's required value is not in its own quote."
        return citation
    if retriever is None:
        citation["reason"] = "Regulation search is not available, so the quote was not checked."
        return citation

    quote = _normalize(source.quote)
    for result in retriever.search(source.quote, top_k=5):
        same_file = result["filename"] == source.filename
        on_page = result["page"] <= source.page <= result.get("page_end", result["page"])
        if same_file and on_page and quote in _normalize(result["text"]):
            citation.update(
                verified=True,
                reason="Quote found on the cited page.",
                chunk_id=result.get("chunk_id"),
                passage=result["text"],
            )
            return citation
    citation["reason"] = "The quote was not found on the cited page of the indexed document."
    return citation


def verification_steps(rule: LibraryRule, item: dict, calculation, citation: dict, source_status: str) -> list[str]:
    source = rule.source
    steps = [
        f"Open {source.filename} at PDF page {source.page}, section {source.section}.",
        f"Confirm it says: \"{source.quote}\"",
    ]
    if rule.exceptions:
        steps.append(f"Check whether an exception applies: {rule.exceptions}")
    steps.append(
        f"Measure the {item['element']} on the drawing. The design states {item['value_text']}."
    )
    if calculation.comparison:
        steps.append(f"Compare: {calculation.comparison}. Result: {calculation.status}.")
    if source_status == "proposed":
        steps.append("Note that this source is a proposed guideline, not a final regulation.")
    if not citation["verified"]:
        steps.append(f"The citation was not confirmed automatically: {citation['reason']}")
    return steps


def _overall(results: list[dict], warnings: list[str]) -> str:
    statuses = {result["status"] for result in results}
    if "FAIL" in statuses:
        return "FAIL"
    unverified = any(
        not result["citation"]["verified"] for result in results if result.get("citation")
    )
    if not results or warnings or statuses & {"UNKNOWN", NO_RULE} or unverified:
        return "NEEDS_REVIEW"
    return "PASS"


def _facts(results: list[dict]) -> list[dict]:
    facts = []
    for result in results:
        if result["status"] == NO_RULE:
            facts.append({"element": result["element"], "design": result["value_text"],
                          "result": "not checked: no matching rule, needs manual review"})
            continue
        facts.append({
            "rule": result["rule_id"],
            "regulation": result["regulation"],
            "source_status": result["source_status"],
            "element": result["element"],
            "result": result["status"],
            "design": result["design"],
            "required": result["required"],
            "comparison": result["comparison"],
            "margin": result["margin"],
            "citation": "verified" if result["citation"]["verified"] else "not verified",
        })
    return facts


def template_summary(results: list[dict], warnings: list[str]) -> str:
    checked = [result for result in results if result["status"] != NO_RULE]
    failed = [result for result in checked if result["status"] == "FAIL"]
    parts = [f"{len(failed)} of {len(checked)} rule checks failed."]
    for result in failed:
        parts.append(
            f"{result['element']} ({result['rule_id']}, {result['regulation']}): "
            f"{result['comparison']}, {result['reason']}"
        )
    review = [result for result in results if result["status"] in ("UNKNOWN", NO_RULE)]
    if review:
        parts.append(f"{len(review)} items need manual review.")
    if warnings:
        parts.append(f"{len(warnings)} input values were rejected or skipped.")
    return " ".join(parts)


def unsupported_numbers(summary: str, facts: list[dict]) -> list[str]:
    """Numbers in the summary that do not appear in the checked facts."""
    allowed = {number.replace(",", ".") for number in _NUMBER.findall(json.dumps(facts))}
    found = [number.replace(",", ".") for number in _NUMBER.findall(summary)]
    return [number for number in found if number not in allowed and number not in _SMALL_COUNTS]


def check_design(
    text: str | None = None,
    items: list[dict] | None = None,
    llm=None,
    retriever=None,
    summarize: bool = True,
    library: tuple[dict, list[LibraryRule]] | None = None,
) -> dict:
    attributes, rules = library or load_library()
    catalog = load_catalog()

    if items is None:
        if not text or llm is None:
            raise ValueError("Give design items, or design text and a language model.")
        items = llm_module.parse_design(llm, text, attributes)
        parsed_by = "mistral"
    else:
        parsed_by = "engineer"
    accepted, warnings = accept_items(items, text, attributes)

    results: list[dict] = []
    for item in accepted:
        matching = [rule for rule in rules if rule.attribute == item["attribute"]]
        if not matching:
            results.append({
                **item,
                "status": NO_RULE,
                "reason": "No checked rule covers this item, so it needs manual review.",
            })
            continue
        for rule in matching:
            calculation = evaluate(rule, item["value_text"])
            citation = verify_citation(rule, retriever)
            document = catalog.get(rule.source.filename, {})
            source_status = document.get("status", "unclassified")
            results.append({
                **item,
                "rule_id": rule.id,
                "rule_title": rule.title,
                "regulation": document.get("regulation", rule.source.filename),
                "source_status": source_status,
                "status": calculation.status,
                "design": calculation.design,
                "required": calculation.required,
                "comparison": calculation.comparison,
                "margin": calculation.margin,
                "reason": calculation.reason,
                "citation": citation,
                "verification_steps": verification_steps(
                    rule, item, calculation, citation, source_status
                ),
            })

    # Decided before the summary, so a failed summary cannot change the result.
    overall = _overall(results, warnings)
    summary = template_summary(results, warnings)
    summary_source = "template"
    if summarize and llm is not None and results:
        facts = _facts(results)
        try:
            written = llm_module.summarize(llm, facts)
        except llm_module.LLMUnavailableError as error:
            warnings.append(f"Mistral summary failed, so a template summary is shown: {error}")
        else:
            extra = unsupported_numbers(written, facts)
            if not written:
                warnings.append("Mistral returned an empty summary, so a template summary is shown.")
            elif extra:
                warnings.append(
                    "Mistral's summary had numbers not in the results "
                    f"({', '.join(extra)}), so a template summary is shown."
                )
            else:
                summary, summary_source = written, "mistral"

    return {
        "overall": overall,
        "parsed_by": parsed_by,
        "items": accepted,
        "results": results,
        "summary": summary,
        "summary_source": summary_source,
        "warnings": warnings,
    }
