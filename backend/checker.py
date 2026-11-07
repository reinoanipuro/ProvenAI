"""Design and regulation check: input -> regulations -> Python review -> summary.

Mistral reads the input, reads the regulation passages the RAG finds, and
writes the summary. Python reviews everything Mistral says against the actual
passage text, does every calculation, and decides how far a result can be
trusted. Nothing Mistral says is used until Python has confirmed it.

Each result has a level:
- verified: an engineer-approved rule from the rule library, quote confirmed.
  This path is optional and can be switched off.
- ai_read: Mistral read the requirement from a regulation passage and Python
  confirmed it is really there. It has a confidence level, and an engineer
  must confirm it applies. Numeric ones can be approved as rules.
- manual_review: nothing reliable was found, so the closest passages are shown.
"""

import difflib
import json
import re
from pathlib import Path

from . import llm as llm_module
from .rag import REGULATIONS_DIR, load_catalog
from .rules import (
    RULE_LIBRARY_PATH,
    LibraryRule,
    Source,
    evaluate,
    infer_quantity,
    load_library,
    parse_limits,
)

NO_RULE = "NO_RULE"
REQUIREMENT_FOUND = "REQUIREMENT_FOUND"
VERIFIED = "verified"
AI_READ = "ai_read"
MANUAL_REVIEW = "manual_review"
PASSAGES_TO_READ = 4
SEARCH_RESULTS_PER_QUERY = 4
# How close a reworded quote must be to a passage sentence to be accepted.
QUOTE_MATCH_RATIO = 0.9
QUANTITIES = {"length", "slope", "percentage"}
# Sources Python flags, because they are not a complete, current, binding text.
WEAK_SOURCES = {
    "proposed": "the source is a proposed guideline, not a final regulation",
    "amendments_only": "the source only lists amendments, not the full regulation",
    "older_edition": "the source is an older edition",
    "excerpt": "the source is only an excerpt",
    "guidance": "the source is guidance, not the regulation itself",
    "unclassified": "the source document is not classified",
}
_STOPWORDS = {
    "with", "from", "that", "this", "shall", "have", "height", "width", "length", "level",
    "minimum", "maximum", "required", "requirement", "design", "item", "ship", "ships",
    "vessel", "vessels", "deck", "each", "other", "than", "more", "less", "which",
    "freeboard", "position", "main", "upper", "lower", "forward", "after", "port", "starboard",
}
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_SMALL_COUNTS = {str(number) for number in range(0, 21)}


def _clean(text: str) -> str:
    """Remove the hidden hyphen marks PDFs leave where a word was split, like 'ex\\x02cept'."""
    text = re.sub(r"[\x02­]\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize(text: str) -> str:
    text = _clean(text)
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60] or "item"


def _keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z]{4,}", text.lower())
    return {word.rstrip("s") for word in words if word not in _STOPWORDS}
def accept_items(items: list[dict], text: str | None, attributes: dict) -> tuple[list[dict], list[str]]:
    """Keep design values that are really in the input, and questions without a value."""
    accepted: list[dict] = []
    warnings: list[str] = []
    source = _normalize(text) if text is not None else None
    for item in items:
        value_text = item.get("value_text", "").strip()
        attribute = item.get("attribute", llm_module.UNKNOWN_ATTRIBUTE)
        element = item.get("element", "").strip() or "design item"
        measured = item.get("property", "").strip()
        if attribute not in attributes:
            attribute = llm_module.UNKNOWN_ATTRIBUTE
        if not measured and attribute in attributes:
            measured = attributes[attribute]["label"]
        if not value_text and not measured:
            warnings.append(f"'{element}' has no value or question, so it was skipped.")
            continue
        # Spaces are ignored, so "6%" matches "6 %"; a changed number still does not match.
        if value_text and source is not None and _normalize(value_text).replace(" ", "") not in source.replace(" ", ""):
            # An invented value is never used. The item is still answered as a question.
            warnings.append(
                f"'{value_text}' for '{element}' is not in the input text, so the value was "
                "dropped and only the requirement is looked up."
            )
            value_text = ""
            if not measured:
                continue
        accepted.append({
            "element": element,
            "property": measured,
            "attribute": attribute,
            "value_text": value_text,
            "search_query": item.get("search_query", "").strip(),
            "source": item.get("source", "").strip(),
        })
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

    passage = retriever.find_passage(source.filename, source.page, source.quote)
    if passage is not None:
        citation.update(
            verified=True,
            reason="Quote found on the cited page.",
            chunk_id=passage.get("chunk_id"),
            passage=passage["text"],
        )
        return citation
    citation["reason"] = "The quote was not found on the cited page of the indexed document."
    return citation


def verification_steps(
    rule: LibraryRule, item: dict, calculation, citation: dict, source_status: str, level: str
) -> list[str]:
    source = rule.source
    steps = []
    if level == AI_READ:
        steps.append(
            "This requirement was read by Mistral from the regulation text and is not an "
            "approved rule. Confirm it before relying on the result."
        )
    steps += [
        f"Open {source.filename} at PDF page {source.page}, section {source.section}.",
        f"Confirm it says: \"{source.quote}\"",
    ]
    if rule.exceptions:
        steps.append(f"Check whether an exception or condition applies: {rule.exceptions}")
    if level == AI_READ:
        steps.append(f"Confirm this requirement applies to the {item['element']}.")
    if item["value_text"]:
        steps.append(
            f"Measure the {item['element']} on the drawing. The design states {item['value_text']}."
        )
    if calculation is not None and calculation.comparison:
        steps.append(f"Compare: {calculation.comparison}. Result: {calculation.status}.")
    if source_status in WEAK_SOURCES:
        steps.append(f"Note that {WEAK_SOURCES[source_status]}.")
    if not citation["verified"]:
        steps.append(f"The citation was not confirmed automatically: {citation['reason']}")
    return steps


def _passage_view(passage: dict) -> dict:
    return {
        key: passage.get(key)
        for key in ("filename", "page", "page_end", "section", "regulation", "status", "chunk_id", "text")
    }


def find_passages(item: dict, retriever) -> list[dict]:
    """Search with several wordings and keep the best passages.

    Only RegulatoryRetriever.search() is used, so the RAG itself is unchanged.
    """
    measured = item["property"] or item["element"]
    queries = [item.get("search_query", ""), f"{measured} of {item['element']}", f"{measured} requirement"]
    best: dict[str, dict] = {}
    for query in dict.fromkeys(query.strip() for query in queries if query.strip()):
        for passage in retriever.search(query, top_k=SEARCH_RESULTS_PER_QUERY):
            key = passage.get("chunk_id") or f"{passage['filename']}:{passage['page']}"
            current = best.get(key)
            if current is None or passage.get("rerank_score", 0) > current.get("rerank_score", 0):
                best[key] = passage
    ranked = sorted(best.values(), key=lambda passage: passage.get("rerank_score", 0), reverse=True)
    return ranked[:PASSAGES_TO_READ]


def _match_quote(quote: str, passage_text: str) -> tuple[str | None, str]:
    """Return the passage's own wording for Mistral's quote, or None if it is not there.

    A word-for-word match is used as it is. Otherwise the closest sentence in the
    passage is accepted only if it is almost identical, and its own text replaces
    Mistral's, so a reworded quote can never reach the engineer.
    """
    quote = _clean(quote)
    if len(quote) < 10:
        return None, "The quote is too short."
    if _normalize(quote) in _normalize(passage_text):
        return quote, "Found word for word."
    sentences = [part for part in re.split(r"(?<=[.;:])\s+", _clean(passage_text)) if len(part) >= 10]
    best, score = None, 0.0
    for size in (1, 2):
        for start in range(len(sentences)):
            candidate = " ".join(sentences[start : start + size])
            ratio = difflib.SequenceMatcher(None, _normalize(quote), _normalize(candidate)).ratio()
            if ratio > score:
                best, score = candidate, ratio
    if best is not None and score >= QUOTE_MATCH_RATIO:
        return best, f"Mistral's quote differed slightly ({score:.0%} match), so the passage's own wording is used."
    return None, f"The closest sentence only matched {score:.0%}."


def review_answer(answer: dict, passages: list[dict], item: dict, catalog: dict) -> dict:
    """Python's review of Mistral's reading: every claim is checked against the passage.

    Hard checks reject the reading. Soft checks lower the confidence and are
    shown to the engineer, so it is clear why a result is or is not trusted.
    """
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str = "", hard: bool = False) -> bool:
        checks.append({"check": name, "passed": passed, "detail": detail, "hard": hard})
        return passed

    review = {"ok": False, "checks": checks, "confidence": "none", "rule": None, "problem": ""}
    by_id = {passage.get("chunk_id"): passage for passage in passages}
    passage = by_id.get(answer.get("chunk_id"))
    if not check("Cited passage was one of those searched", passage is not None, hard=True):
        review["problem"] = "it cited a passage that was not provided"
        return review
    review["passage"] = passage
    quote, how = _match_quote(str(answer.get("quote", "")), passage["text"])
    if not check("Quote is in the passage", quote is not None, how, hard=True):
        review["problem"] = "its quote is not in the passage"
        return review
    review["quote"] = quote

    numeric = answer.get("requirement_type") == "numeric"
    min_text = str(answer.get("min_text", "")).strip()
    max_text = str(answer.get("max_text", "")).strip()
    quantity = None
    minimum: tuple = ()
    maximum: tuple = ()
    if numeric:
        if not check("A limit value was given", bool(min_text or max_text), hard=True):
            review["problem"] = "it called the requirement numeric but gave no limit"
            return review
        for limit_text in (min_text, max_text):
            if limit_text and not check(
                f"Limit '{limit_text}' is in the quote",
                _normalize(limit_text) in _normalize(quote),
                hard=True,
            ):
                review["problem"] = f"the limit '{limit_text}' is not in its quote"
                return review
        description = f"{item['property']} {item['element']} {quote}"
        quantity = (
            infer_quantity(item["value_text"], description)
            if item["value_text"]
            else infer_quantity(min_text or max_text, description)
        )
        if item["value_text"] and not check(
            "Design value has a unit that can be compared", quantity is not None, hard=True
        ):
            review["problem"] = f"the design value '{item['value_text']}' has no comparable unit"
            return review
        if quantity:
            minimum = parse_limits(min_text, quantity) if min_text else ()
            maximum = parse_limits(max_text, quantity) if max_text else ()
            if item["value_text"] and not check(
                "Limit unit matches the design value", bool(minimum or maximum), hard=True
            ):
                review["problem"] = "the limit has no unit that matches the design value"
                return review
            chosen = {(limit.value, limit.unit) for limit in (*minimum, *maximum)}
            others = [
                limit for limit in parse_limits(quote, quantity)
                if (limit.value, limit.unit) not in chosen
            ]
            check(
                "Quote states only one limit",
                not others,
                f"It also states {', '.join(f'{limit.value:g} {limit.unit}' for limit in others)}."
                if others else "",
            )

    topic = _keywords(item["property"]) or _keywords(item["element"])
    passage_words = _keywords(f"{passage.get('section', '')} {passage['text']}")
    check(
        "Passage is about the same topic",
        bool(topic & passage_words) if topic else True,
        "" if topic & passage_words else f"None of '{', '.join(sorted(topic))}' appear in the passage.",
    )
    # Every word naming the element, not its location, must appear in the rule:
    # "superstructure door" is not covered by a rule for deckhouse doorways.
    core = re.split(r"\s(?:on|in|at|of the|for)\s|[:,(]", item["element"].lower())[0]
    element_words = _keywords(core)
    covered_words = _keywords(f"{answer.get('applies_to', '')} {quote}")
    missing = sorted(
        word for word in element_words
        if not any(word.startswith(other) or other.startswith(word) for other in covered_words)
    )
    same_element = check(
        "Requirement covers the same kind of element",
        bool(element_words) and not missing,
        f"The rule covers '{answer.get('applies_to', '')}'; it does not mention: {', '.join(missing)}."
        if missing else "",
    )
    status = catalog.get(passage["filename"], {}).get("status", passage.get("status", "unclassified"))
    check("Source is a full, current regulation text", status not in WEAK_SOURCES, WEAK_SOURCES.get(status, ""))

    stated = str(answer.get("answer", "")).strip()
    allowed = set(_NUMBER.findall(passage["text"])) | set(_NUMBER.findall(item["value_text"]))
    invented = [number for number in _NUMBER.findall(stated) if number not in allowed]
    if not check(
        "Answer only uses numbers from the passage",
        not invented,
        f"It added {', '.join(invented)}." if invented else "",
    ) or not stated:
        stated = f"The passage states: \"{quote}\""
    review["answer"] = stated

    soft_failures = sum(1 for item_check in checks if not item_check["passed"] and not item_check["hard"])
    review["confidence"] = "high" if soft_failures == 0 else "medium" if soft_failures == 1 else "low"
    if not same_element:
        # A rule for another kind of element is the most misleading mistake, so it caps confidence.
        review["confidence"] = "low"
    review["ok"] = True

    if numeric and quantity and (minimum or maximum):
        required_text = " and ".join(
            f"{text} {side}" for text, side in ((min_text, "minimum"), (max_text, "maximum")) if text
        )
        failed_notes = " ".join(
            item_check["detail"] for item_check in checks
            if not item_check["passed"] and item_check["detail"]
        )
        measured = item["property"] or item["element"]
        review["rule"] = LibraryRule(
            id=f"CANDIDATE-{_slug(measured)}",
            title=f"{measured[:1].upper()}{measured[1:]} ({passage.get('regulation', '')} {passage.get('section', '')})".strip(),
            attribute=_slug(measured),
            quantity=quantity,
            minimum=minimum,
            maximum=maximum,
            required_text=required_text,
            exceptions=f"{failed_notes} {str(answer.get('conditions', '')).strip()}".strip(),
            source=Source(
                filename=passage["filename"],
                page=passage["page"],
                section=passage.get("section", ""),
                quote=quote,
            ),
        )
    return review


def proposed_rule(rule: LibraryRule, label: str) -> dict:
    """The rule in rule library format, ready for an engineer to approve."""
    proposal = {
        "attribute": {"name": rule.attribute, "label": label, "quantity": rule.quantity},
        "rule": {
            "id": rule.id,
            "title": rule.title,
            "attribute": rule.attribute,
            "required_text": rule.required_text,
            "exceptions": rule.exceptions,
            "source": {
                "filename": rule.source.filename,
                "page": rule.source.page,
                "section": rule.source.section,
                "quote": rule.source.quote,
            },
        },
    }
    for key, limits in (("min", rule.minimum), ("max", rule.maximum)):
        if limits:
            proposal["rule"][key] = [{"value": limit.value, "unit": limit.unit} for limit in limits]
    return proposal


def check_with_regulations(item: dict, llm, retriever, catalog: dict) -> dict:
    """Find the requirement in the regulations with Mistral, then review it in Python."""
    measured = item["property"] or item["element"]
    result = {**item, "status": NO_RULE, "level": MANUAL_REVIEW, "passages": []}
    if retriever is None:
        result["reason"] = "Regulation search is not available."
        return result

    passages = find_passages(item, retriever)
    result["passages"] = [_passage_view(passage) for passage in passages]
    if llm is None or not passages:
        result["reason"] = "Review the closest regulation passages by hand."
        return result

    try:
        answer = llm_module.extract_requirement(
            llm, item["element"], measured, passages, item["value_text"]
        )
    except llm_module.LLMUnavailableError as error:
        result["reason"] = f"Mistral could not read the passages: {error}"
        return result
    if not answer.get("found") or answer.get("requirement_type") == "none":
        result["reason"] = (
            "No requirement for this was found in the closest passages. Review them by hand. "
            "The documents that cover it may be missing, such as DNV class rules."
        )
        return result

    review = review_answer(answer, passages, item, catalog)
    result["review"] = review["checks"]
    if not review["ok"]:
        result["reason"] = (
            f"Mistral's reading failed Python's review: {review['problem']}. "
            "Review the passages by hand."
        )
        return result

    passage = review["passage"]
    document = catalog.get(passage["filename"], {})
    source_status = document.get("status", passage.get("status", "unclassified"))
    rule = review["rule"]
    citation = {
        "filename": passage["filename"],
        "page": passage["page"],
        "section": passage.get("section", ""),
        "quote": review["quote"],
        "verified": True,
        "reason": "Quote found word for word in the regulation passage.",
    }
    base = {
        **item,
        "level": AI_READ,
        "confidence": review["confidence"],
        "regulation": document.get("regulation", passage.get("regulation", passage["filename"])),
        "source_status": source_status,
        "answer": review["answer"],
        "citation": citation,
        "review": review["checks"],
        "passages": result["passages"],
    }

    if rule is not None and item["value_text"]:
        calculation = evaluate(rule, item["value_text"])
        return {
            **base,
            "rule_id": rule.id,
            "rule_title": rule.title,
            "status": calculation.status,
            "design": calculation.design,
            "required": calculation.required,
            "comparison": calculation.comparison,
            "margin": calculation.margin,
            "reason": calculation.reason,
            "verification_steps": verification_steps(
                rule, item, calculation, citation, source_status, AI_READ
            ),
            "proposed_rule": proposed_rule(rule, f"{measured} of {item['element']}"),
        }

    # A question, or a requirement Python cannot calculate: show it for the engineer to judge.
    reason = (
        "The requirement is not a number Python can compare, so the engineer must judge it."
        if item["value_text"] else "Answer to the question, from the regulation text."
    )
    steps = [
        "This was read by Mistral from the regulation text. Confirm it before relying on it.",
        f"Open {passage['filename']} at PDF page {passage['page']}, section {passage.get('section', '')}.",
        f"Confirm it says: \"{review['quote']}\"",
    ]
    if answer.get("conditions"):
        steps.append(f"Check the conditions: {answer['conditions']}")
    if source_status in WEAK_SOURCES:
        steps.append(f"Note that {WEAK_SOURCES[source_status]}.")
    return {
        **base,
        "status": REQUIREMENT_FOUND,
        "required": rule.required_text if rule is not None else "",
        "reason": reason,
        "verification_steps": steps,
        **({"proposed_rule": proposed_rule(rule, f"{measured} of {item['element']}")} if rule else {}),
    }


def _overall(results: list[dict], warnings: list[str]) -> str:
    """Only an approved rule can fail the design outright; AI-read results report issues."""
    if any(result["status"] == "FAIL" and result["level"] == VERIFIED for result in results):
        return "FAIL"
    if any(result["status"] == "FAIL" for result in results):
        return "ISSUES_FOUND"
    uncertain = any(
        result["level"] == MANUAL_REVIEW
        or result["status"] in ("UNKNOWN", NO_RULE)
        or result.get("confidence") == "low"
        or not result.get("citation", {}).get("verified", False)
        for result in results
    )
    if not results or warnings or uncertain:
        return "NEEDS_REVIEW"
    if all(result["level"] == VERIFIED for result in results):
        return "PASS"
    if all(result["status"] == REQUIREMENT_FOUND for result in results):
        return "ANSWERED"
    return "NO_ISSUES_FOUND"


def _facts(results: list[dict]) -> list[dict]:
    facts = []
    for result in results:
        if result["level"] == MANUAL_REVIEW:
            facts.append({"element": result["element"], "design": result["value_text"],
                          "result": "not checked: no requirement found, needs manual review"})
            continue
        fact = {
            "check": (
                "approved rule" if result["level"] == VERIFIED
                else "possible result: requirement read by AI from the regulation, engineer must confirm"
            ),
            "regulation": result["regulation"],
            "source_status": result["source_status"],
            "element": result["element"],
            "citation": "verified" if result["citation"]["verified"] else "not verified",
        }
        if result.get("confidence"):
            fact["confidence"] = result["confidence"]
        if result["status"] == REQUIREMENT_FOUND:
            fact.update(result="answered", answer=result["answer"])
        else:
            fact.update(
                rule=result["rule_id"], result=result["status"], design=result["design"],
                required=result["required"], comparison=result["comparison"], margin=result["margin"],
            )
        facts.append(fact)
    return facts


def template_summary(results: list[dict], warnings: list[str]) -> str:
    parts = []
    checked = [result for result in results if result["level"] == VERIFIED]
    if checked:
        failed = [result for result in checked if result["status"] == "FAIL"]
        parts.append(f"{len(failed)} of {len(checked)} approved rules failed.")
        for result in failed:
            parts.append(
                f"{result['element']} ({result['rule_id']}, {result['regulation']}): "
                f"{result['comparison']}, {result['reason']}"
            )
    for result in results:
        if result["level"] != AI_READ:
            continue
        if result["status"] == REQUIREMENT_FOUND:
            parts.append(f"{result['element']}: {result['answer']} ({result['regulation']}).")
        else:
            parts.append(
                f"Possible {result['status']} for {result['element']} ({result['comparison']}, "
                f"{result['regulation']}, {result['confidence']} confidence); an engineer must confirm it."
            )
    review = [result for result in results if result["level"] == MANUAL_REVIEW]
    if review:
        parts.append(f"{len(review)} items need manual review.")
    if warnings:
        parts.append(f"{len(warnings)} input values were rejected or skipped.")
    return " ".join(parts) or "Nothing was checked."


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
    use_rule_library: bool = True,
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
        matching = [
            rule for rule in rules
            if use_rule_library and item["value_text"] and rule.attribute == item["attribute"]
        ]
        if not matching:
            results.append(check_with_regulations(item, llm, retriever, catalog))
            continue
        for rule in matching:
            calculation = evaluate(rule, item["value_text"])
            citation = verify_citation(rule, retriever)
            document = catalog.get(rule.source.filename, {})
            source_status = document.get("status", "unclassified")
            results.append({
                **item,
                "level": VERIFIED,
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
                    rule, item, calculation, citation, source_status, VERIFIED
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


def approve_rule(
    proposal: dict,
    path: Path = RULE_LIBRARY_PATH,
    regulations_dir: Path = REGULATIONS_DIR,
) -> str:
    """Add an engineer-approved rule to the library, after checking it again."""
    attribute = proposal.get("attribute") or {}
    rule = dict(proposal.get("rule") or {})
    name = str(attribute.get("name", ""))
    if not re.fullmatch(r"[a-z0-9_]{1,60}", name) or rule.get("attribute") != name:
        raise ValueError("The rule needs a lowercase attribute name that matches the rule.")
    if attribute.get("quantity") not in QUANTITIES:
        raise ValueError(f"The quantity must be one of: {', '.join(sorted(QUANTITIES))}.")
    if not rule.get("min") and not rule.get("max"):
        raise ValueError("The rule needs a minimum or a maximum.")
    for limit in [*rule.get("min", []), *rule.get("max", [])]:
        if not isinstance(limit.get("value"), (int, float)) or not limit.get("unit"):
            raise ValueError("Every limit needs a numeric value and a unit.")
    source = rule.get("source") or {}
    if not (regulations_dir / str(source.get("filename", ""))).is_file():
        raise ValueError("The source file is not in the regulations folder.")
    quote = _normalize(str(source.get("quote", "")))
    for part in re.split(r" and |\b(?:minimum|maximum)\b", _normalize(str(rule.get("required_text", "")))):
        if part.strip() and part.strip() not in quote:
            raise ValueError(f"The required value '{part.strip()}' is not in the quote.")

    data = json.loads(path.read_text(encoding="utf-8"))
    taken = {existing["id"] for existing in data["rules"]}
    base_id = str(rule.get("id", "")).replace("CANDIDATE-", "APPROVED-") or f"APPROVED-{name}"
    rule["id"], number = base_id, 2
    while rule["id"] in taken:
        rule["id"], number = f"{base_id}-{number}", number + 1
    data["attributes"].setdefault(
        name, {"label": str(attribute.get("label", name)), "quantity": attribute["quantity"]}
    )
    data["rules"].append(rule)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rule["id"]
