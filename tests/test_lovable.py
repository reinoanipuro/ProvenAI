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
        if inspection["status"] in ("done", "error"):
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


def test_rules_match_the_apps_format_and_pass_their_self_tests(client):
    rules = client.get("/lovable/rules").json()
    by_id = {rule["id"]: rule for rule in rules}

    assert by_id["ADA-403.5.1"]["condition"] == {
        "attr": "walking_route_clear_width", "label": "Clear width of a walking route or corridor",
        "op": ">=", "value": 915.0, "unit": "mm", "deficit": "too low or too small",
    }
    # A minimum-and-maximum rule becomes two checks, one limit each.
    assert by_id["ADA-505.4-min"]["condition"]["op"] == ">="
    assert by_id["ADA-505.4-max"]["condition"]["op"] == "<="
    assert by_id["ADA-405.2"]["condition"]["unit"] == "%"
    assert all(test["passed"] for rule in rules for test in rule["tests"])
    assert {rule_set["id"] for rule_set in client.get("/lovable/rulesets").json()} >= {"ada", "pvag", "load-line", "bwm"}


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


def test_engineer_answers_are_rechecked(client):
    inspection = create(client)
    corridor = next(element for element in inspection["elements"] if element["name"] == "Passenger corridor")

    updated = client.post(
        f"/lovable/inspections/{inspection['id']}/answers",
        json={"answers": [{"attr": "walking_route_clear_width", "element_id": corridor["id"], "value": 950}]},
    ).json()
    result = next(item for item in updated["results"] if item["id"] == f"ADA-403.5.1:{corridor['id']}")

    assert result["status"] == "PASS"
    assert result["evidence"][0]["method"] == "Engineer input"


def test_review_notes_and_listing(client):
    inspection = create(client)
    result_id = inspection["results"][0]["id"]
    base = f"/lovable/inspections/{inspection['id']}/results/{result_id}"

    client.post(f"{base}/review")
    updated = client.post(f"{base}/notes", json={"note": "Checked on site"}).json()
    result = next(item for item in updated["results"] if item["id"] == result_id)
    summaries = client.get("/lovable/inspections").json()

    assert result["reviewed"] and not result["needs_review"]
    assert result["notes"] == ["Checked on site"]
    assert summaries[0]["id"] == inspection["id"] and summaries[0]["counts"]["fail"] >= 1
    assert client.get(f"/lovable/inspections/{inspection['id']}/files/f0").status_code == 200
    assert client.get(f"/lovable/inspections/{inspection['id']}/files/../x").status_code == 404


def test_pasted_rule_without_a_source_cannot_be_approved(client):
    proposal = client.post("/lovable/rules", json={
        "text": "Cabin headroom shall be at least 2000 mm.", "clause_ref": "Made up", "rule_set_id": "ada",
        "applies_to": "cabin", "name": "Headroom",
    }).json()

    assert proposal["ok"] and proposal["rule"]["status"] == "proposed"
    response = client.post(f"/lovable/rules/{proposal['rule']['id']}/approve", json=proposal["rule"])
    assert response.status_code == 422
    assert client.post("/lovable/rules", json={"text": "Doors should be nice."}).json()["ok"] is False


def test_unknown_inspection_is_404(client):
    assert client.get("/lovable/inspections/nope").status_code == 404
