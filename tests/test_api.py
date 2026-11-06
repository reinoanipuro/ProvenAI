import pytest
from fastapi.testclient import TestClient

from backend import main


@pytest.fixture
def client(index, tmp_path, monkeypatch):
    # Reuse the session index and keep the database out of the real runtime folder.
    monkeypatch.setattr(main, "RegulatoryIndex", lambda *_: index)
    monkeypatch.setattr(main, "DATABASE", tmp_path / "inspections.sqlite3")
    with TestClient(main.app) as test_client:
        yield test_client


def test_full_flow_over_http(client):
    names = client.get("/samples").json()
    assert len(names) == 3

    sample = client.get(f"/samples/{names[2]}").json()
    inspection = client.post("/inspections", json=sample).json()
    assert inspection["overall"] == "UNKNOWN"
    assert client.get(f"/inspections/{inspection['id']}/audit").json()


def test_sample_name_cannot_traverse_paths(client):
    assert client.get("/samples/..%2F..%2Frules%2Fdeck_safety.json").status_code == 404
