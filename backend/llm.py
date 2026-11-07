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
            return json.loads(reply["message"]["content"])
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as error:
            raise LLMUnavailableError(
                f"Mistral ({self.model}) did not answer at {self.url}: {error}"
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
                        "attribute": {"type": "string", "enum": [*attributes, UNKNOWN_ATTRIBUTE]},
                        "value_text": {"type": "string"},
                    },
                    "required": ["element", "attribute", "value_text"],
                },
            }
        },
        "required": ["items"],
    }
    system = (
        "You read ship design descriptions written by engineers. List every measured design "
        "value in the text. For each one give: element, the design element such as 'deck 5 "
        "corridor'; attribute, the best matching name from the list, or 'unknown' if none fits; "
        "value_text, the value with its unit copied exactly as written in the text, such as "
        "'800 mm' or '1:14'. Never convert, round or invent values. Answer in JSON only.\n\n"
        f"Attribute names:\n{choices}"
    )
    return chat_items(llm.chat_json(system, f"Design description:\n{text}", schema))


def chat_items(reply: dict) -> list[dict]:
    items = reply.get("items", []) if isinstance(reply, dict) else []
    return [
        {key: str(item.get(key, "")).strip() for key in ("element", "attribute", "value_text")}
        for item in items
        if isinstance(item, dict)
    ]


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
        "passed. Say when a source is only proposed or has an unverified citation. Write 3 to 5 "
        "sentences of plain text with no Markdown, bullets or bold. Answer in JSON only."
    )
    reply = llm.chat_json(system, json.dumps(facts, ensure_ascii=False), schema, max_tokens=300)
    summary = str(reply.get("summary", ""))
    return re.sub(r"\s+", " ", re.sub(r"[*_#`]+", "", summary)).strip()
