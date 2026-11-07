"""The API used by the Lovable web app (web/app), with a fake Mistral and search."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import api, documents, lovable

SAMPLES = Path("data/samples/designs")


class FakeLLM:
    model = "fake-mistral"

    def chat_json(self, system, user, schema, max_tokens=400):
        if "items" in schema["properties"]:
            items = []
            if "Clear width: 800 mm" in user:
                items.append({"element": "Passenger corridor", "property": "clear width",
                              "attribute": "walking_route_clear_width", "value_text": "800 mm", "search_query": ""})
            if "Height above stair nosings: 900 mm" in user:
                items.append({"element": "Stair handrail", "property": "height",
                              "attribute": "handrail_height", "value_text": "900 mm", "search_query": ""})
            if "frame 120" in user:
                items.append({"element": "Hull plate", "property": "thickness",
                              "attribute": "unknown", "value_text": "300 mm", "search_query": ""})
            return {"items": items}
        if "found" in schema["properties"]:
            return {"found": False}
        return {"summary": ""}


class FakeRetriever:
    def search(self, query, top_k=5):
        from backend.rules import load_library

        for rule in load_library()[1]:
            if rule.source.quote == query:
                return [{"filename": rule.source.filename, "page": rule.source.page, "page_end": rule.source.page,
                         "chunk_id": "c", "text": rule.source.quote}]
        return []

    def find_passage(self, filename, page, quote):
        from backend.rules import load_library

        for rule in load_library()[1]:
            if (rule.source.filename, rule.source.page, rule.source.quote) == (filename, page, quote):
                return {"filename": filename, "page": page, "page_end": page, "chunk_id": "c", "text": quote}
        return None


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(lovable, "INSPECTION_DIR", tmp_path / "inspections")
    monkeypatch.setattr(lovable, "_store", {})
    monkeypatch.setattr(api, "llm", FakeLLM())
    monkeypatch.setattr(api, "_optional_retriever", lambda: FakeRetriever())
    monkeypatch.setattr(api, "retriever", FakeRetriever())
    return TestClient(api.app)


def wait_until_done(client, inspection_id):
    for _ in range(200):
        inspection = client.get(f"/lovable/inspections/{inspection_id}").json()
        # Also wait for the background AI step, which saves the inspection when it ends.
        if inspection["status"] == "error" or (inspection["status"] == "done" and not inspection["refining"]):
            return inspection
        time.sleep(0.05)
    raise AssertionError("inspection did not finish")


def create(client):
    files = [
        ("files", ("deck5.txt", (SAMPLES / "deck5_accessibility.txt").read_bytes(), "text/plain")),
        ("files", ("notes.docx", (SAMPLES / "open_deck_notes.docx").read_bytes(), "application/octet-stream")),
    ]
    response = client.post("/lovable/inspections", data={"name": "Deck 5"}, files=files)
    assert response.status_code == 200
    return wait_until_done(client, response.json()["id"])


def test_rules_become_one_check_per_limit():
    by_id = {check["lovable"]["id"]: check["lovable"] for check in lovable.library_checks()}

    assert by_id["ADA-403.5.1"]["condition"] == {
        "attr": "walking_route_clear_width", "label": "Clear width of a walking route or corridor",
        "op": ">=", "value": 915.0, "unit": "mm", "deficit": "too low or too small",
    }
    # A minimum-and-maximum rule becomes two checks, one limit each.
    assert by_id["ADA-505.4-min"]["condition"]["op"] == ">="
    assert by_id["ADA-505.4-max"]["condition"]["op"] == "<="
    assert by_id["ADA-405.2"]["condition"]["unit"] == "%"


def test_inspection_runs_and_python_decides(client):
    inspection = create(client)

    assert inspection["status"] == "done"
    results = {result["id"]: result for result in inspection["results"]}
    corridor = next(element for element in inspection["elements"] if element["name"] == "Passenger corridor")
    width = results[f"ADA-403.5.1:{corridor['id']}"]
    assert width["status"] == "FAIL"
    assert width["measured"] == 800 and width["required"] == "≥ 915"
    assert corridor["type"] == "corridor"
    assert "deck5.txt" in width["evidence"][0]["source_file"]

    handrail = next(element for element in inspection["elements"] if element["name"] == "Stair handrail")
    assert results[f"ADA-505.4-min:{handrail['id']}"]["status"] == "PASS"
    assert results[f"ADA-505.4-max:{handrail['id']}"]["status"] == "PASS"

    # No approved rule and nothing found in the regulations: unknown, and needs review.
    plate = next(result for result in inspection["results"] if result["check_id"].startswith("AI-"))
    assert plate["status"] == "UNKNOWN" and plate["needs_review"]


def test_result_has_regulation_pages_next_steps_and_a_summary(client):
    from backend.rules import load_library

    inspection = create(client)
    for _ in range(200):
        if not inspection["refining"]:
            break
        time.sleep(0.05)
        inspection = client.get(f"/lovable/inspections/{inspection['id']}").json()

    corridor = next(element for element in inspection["elements"] if element["name"] == "Passenger corridor")
    width = next(result for result in inspection["results"] if result["id"] == f"ADA-403.5.1:{corridor['id']}")
    rule = next(rule for rule in load_library()[1] if rule.id == "ADA-403.5.1")
    assert width["sources"][0] == {
        "filename": rule.source.filename, "page": rule.source.page, "section": rule.source.section,
        "quote": rule.source.quote, "verified": True, "closest": False,
    }

    steps = inspection["next_steps"]
    assert steps[0]["kind"] == "fix" and "Passenger corridor" in steps[0]["title"]
    assert width["id"] in steps[0]["result_ids"] and f"page {rule.source.page}" in steps[0]["detail"]
    assert any(step["kind"] == "check" and "Hull plate" in step["title"] for step in steps)
    assert steps[-1]["kind"] == "recheck" and [step["number"] for step in steps] == list(range(1, len(steps) + 1))
    # The fake Mistral writes an empty summary, so Python's own summary is kept.
    assert inspection["summary"]["source"] == "python" and "800 mm" in inspection["summary"]["text"]
    assert inspection["status"] == "done" and inspection["progress"]["label"] == "Done"


def test_listing_files_and_text_view(client):
    inspection = create(client)
    summaries = client.get("/lovable/inspections").json()
    text = client.get(f"/lovable/inspections/{inspection['id']}/files/f0/text").json()

    assert summaries[0]["id"] == inspection["id"] and summaries[0]["counts"]["fail"] >= 1
    assert client.get(f"/lovable/inspections/{inspection['id']}/files/f0").status_code == 200
    assert client.get(f"/lovable/inspections/{inspection['id']}/files/../x").status_code == 404
    assert "Clear width: 800 mm" in text["pages"][0]["text"]


def test_too_many_files_are_refused(client):
    files = [("files", (f"f{number}.txt", b"x", "text/plain")) for number in range(11)]

    assert client.post("/lovable/inspections", data={"name": "x"}, files=files).status_code == 422


def test_unknown_inspection_is_404(client):
    assert client.get("/lovable/inspections/nope").status_code == 404


def test_a_check_cut_short_by_a_restart_is_closed(client):
    inspection = create(client)
    path = lovable._path(inspection["id"])
    saved = path.read_text(encoding="utf-8")
    lovable._store.clear()
    path.write_text(saved.replace('"refining": false', '"refining": true'), encoding="utf-8")

    reloaded = client.get(f"/lovable/inspections/{inspection['id']}").json()

    assert reloaded["refining"] is False and reloaded["progress"]["label"] == "Done"


def test_value_read_twice_is_not_checked_again_by_ai():
    from backend.lovable import _uncovered_items

    line = "Cabin corridor | Clear width 1,200 mm"
    matched = {"element": "Cabin corridor", "attribute": "walking_route_clear_width", "value_text": "1,200 mm", "source_line": line, "source_file": "a.txt", "source_page": 1}
    repeat = {**matched, "attribute": "unknown", "element": "cabin  corridor"}
    other = {**matched, "attribute": "unknown", "value_text": "2 m", "source_line": "Cabin corridor | Height 2 m"}
    assert _uncovered_items([matched, repeat, other, dict(other)], {"walking_route_clear_width"}) == [other]


def test_next_steps_follow_the_order_of_the_document():
    from backend.lovable import _next_steps

    def result(element_id, status, order):
        return {
            "id": f"R:{element_id}", "element_id": element_id, "status": status, "required_inputs": ["x"],
            "check_name": "Check", "rule_set": "ada", "required": "≥ 1", "unit": "mm", "measured": 0,
            "recommendation": "", "reason": "", "sources": [], "clause_ref": "ADA 1", "evidence": [{"order": order}],
        }

    elements = [
        {"id": "E1", "name": "Late item", "attrs": {"x": {"value_text": "1 mm", "order": 9}}},
        {"id": "E2", "name": "Early item", "attrs": {"x": {"value_text": "2 mm", "order": 2}}},
    ]
    state = {"elements": elements, "warnings": [], "results": [result("E1", "FAIL", 9), result("E2", "UNKNOWN", 2)]}
    steps = _next_steps(state)
    assert [step["element_id"] for step in steps[:2]] == ["E2", "E1"]
    assert all("_order" not in step for step in steps)
