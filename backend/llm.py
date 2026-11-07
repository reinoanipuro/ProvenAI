"""Local Mistral through Ollama, always answering in a fixed JSON schema.

The model has two jobs only: turn the engineer's input into design items, and
write a summary of results that Python has already calculated and checked.
"""

import json
import os
import re
import urllib.error
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
LLM_MODEL = os.environ.get("PROVENAI_LLM_MODEL", "ministral-3:8b")
# A CPU-only laptop needs about a minute per call, so allow plenty of time.
LLM_TIMEOUT_SECONDS = int(os.environ.get("PROVENAI_LLM_TIMEOUT", "600"))
UNKNOWN_ATTRIBUTE = "unknown"


class LLMUnavailableError(RuntimeError):
    """Ollama could not be reached or did not return valid JSON."""


class LLMBadOutputError(LLMUnavailableError):
    """Ollama answered, but the JSON was invalid, usually cut off at the length limit."""


class OllamaClient:
    def __init__(self, model: str = LLM_MODEL, url: str = OLLAMA_URL, timeout: int = LLM_TIMEOUT_SECONDS):
        self.model = model
        self.url = url.rstrip("/")
        self.timeout = timeout

    def chat_json(self, system: str, user: str, schema: dict, max_tokens: int = 400) -> dict:
        body = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": max_tokens},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        request = urllib.request.Request(
            f"{self.url}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                reply = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise LLMUnavailableError(
                f"Mistral ({self.model}) did not answer at {self.url}: {error}"
            ) from error
        try:
            return json.loads(reply["message"]["content"])
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise LLMBadOutputError(
                f"Mistral ({self.model}) returned invalid JSON, probably cut off: {error}"
            ) from error


def parse_design(llm, text: str, attributes: dict[str, dict]) -> list[dict]:
    """Ask Mistral which design items the input describes, with each value as written."""
    choices = "\n".join(f"- {name}: {details['label']}" for name, details in attributes.items())
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "element": {"type": "string"},
                        "property": {"type": "string"},
                        "attribute": {"type": "string", "enum": [*attributes, UNKNOWN_ATTRIBUTE]},
                        "value_text": {"type": "string"},
                        "search_query": {"type": "string"},
                    },
                    "required": ["element", "property", "attribute", "value_text", "search_query"],
                },
            }
        },
        "required": ["items"],
    }
    system = (
        "You read ship design descriptions and regulation questions written by engineers. List "
        "every design value and every question to check. For each one give: element, the design "
        "element such as 'deck 5 corridor'; property, what is measured or asked about in plain "
        "words such as 'clear width' or 'sill height'; attribute, the matching name from the "
        "list, or 'unknown' if none fits exactly; value_text, the value with its unit copied "
        "exactly as written such as '800 mm' or '1:14', or an empty string \"\" when the text "
        "gives no value, as in a question; search_query, a short search for the regulation that sets this requirement, "
        "using regulation wording such as 'height of sills of doorways in superstructures'. "
        "Never convert, round or invent values. Answer in JSON only.\n\n"
        f"Attribute names:\n{choices}"
    )
    # About 100 tokens per item; the caller sends few enough lines to fit.
    return chat_items(llm.chat_json(system, f"Engineer input:\n{text}", schema, max_tokens=1500))


def chat_items(reply: dict) -> list[dict]:
    items = reply.get("items", []) if isinstance(reply, dict) else []
    return [
        {
            key: str(item.get(key, "")).strip()
            for key in ("element", "property", "attribute", "value_text", "search_query")
        }
        for item in items
        if isinstance(item, dict)
    ]


def extract_requirement(
    llm, element: str, measured: str, passages: list[dict], design_value: str = ""
) -> dict:
    """Ask Mistral which passage sets the requirement for this item, and what it says.

    Its answer is only a proposal: the checker confirms the passage, the quote
    and the limits are really there before using them, and labels the result.
    """
    schema = {
        "type": "object",
        "properties": {
            "found": {"type": "boolean"},
            "chunk_id": {"type": "string"},
            "quote": {"type": "string"},
            "requirement_type": {"type": "string", "enum": ["numeric", "qualitative", "none"]},
            "min_text": {"type": "string"},
            "max_text": {"type": "string"},
            "applies_to": {"type": "string"},
            "answer": {"type": "string"},
            "conditions": {"type": "string"},
        },
        "required": [
            "found", "chunk_id", "quote", "requirement_type", "min_text", "max_text",
            "applies_to", "answer", "conditions",
        ],
    }
    system = (
        "You find requirements in regulation passages. Decide whether one passage states the "
        "requirement for the property of the design element. A general rule covers the specific "
        "elements it includes: a rule for walking surfaces or accessible routes covers corridors, "
        "and a rule for doors covers cabin doors. Do not use a rule for a different kind of "
        "element: a rule for companionways does not cover superstructure doors. Quote the "
        "requirement sentence itself, not a heading or table title. If none does, set "
        "found to false and leave the other fields empty. If one does, give: chunk_id; quote, "
        "the sentence with the requirement copied exactly; requirement_type, numeric if it "
        "states a minimum or maximum value, otherwise qualitative; min_text and max_text, the "
        "limit values copied exactly as written such as '36 inches (915 mm)', empty if none; "
        "applies_to, the element the passage says it covers, in its own words; answer, one "
        "sentence saying what the passage requires; conditions, any exceptions or conditions. "
        "Never convert or invent values. Answer in JSON only."
    )
    context = "\n\n".join(
        f"[{passage['chunk_id']}] {passage.get('regulation', '')} ({passage.get('status', '')}) "
        f"{passage.get('section', '')}\n{passage['text']}"
        for passage in passages
    )
    value_line = f"\nDesign value: {design_value}" if design_value else ""
    user = (
        f"Design element: {element}\nProperty: {measured}{value_line}\n\nPassages:\n{context}"
    )
    reply = llm.chat_json(system, user, schema, max_tokens=400)
    return {key: reply.get(key, "") for key in schema["properties"]} if isinstance(reply, dict) else {}


def summarize(llm, facts: list[dict]) -> str:
    """Ask Mistral to explain results that Python has already calculated."""
    schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
    }
    system = (
        "You write short summaries of ship design compliance checks for engineers. The checks "
        "were already calculated. Use only the facts given and copy every number exactly as "
        "written; do not calculate anything new. Start with the failed checks. An item marked "
        "'not checked' was not evaluated: say it needs manual review, never that it failed or "
        "passed. A 'possible result' came from a limit read by AI: call it a possible pass or "
        "possible fail that an engineer must confirm, and mention its confidence. An "
        "'answered' item is a question: give the answer from the facts. Use the source_status "
        "exactly as written, such as guidance or proposed, and do not name other standards. "
        "Write 3 to 5 sentences of plain text with no Markdown, bullets or bold. Answer in "
        "JSON only."
    )
    reply = llm.chat_json(system, json.dumps(facts, ensure_ascii=False), schema, max_tokens=300)
    summary = str(reply.get("summary", ""))
    # Underscores are kept, because rule IDs such as CANDIDATE-sill_height contain them.
    return re.sub(r"\s+", " ", re.sub(r"[*#`]+", "", summary)).strip()
