import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from quakebot.api.server import app


def test_api_health_check():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_layout_metadata():
    client = TestClient(app)
    response = client.get("/layouts")
    assert response.status_code == 200
    payload = response.json()
    assert "semantic" in payload
    assert "visual" in payload
    assert "Entrance" in payload["semantic"]["room_to_floor"]


def test_api_start_episode_and_retrieve_snapshots():
    client = TestClient(app)
    started = client.post("/episodes/start", json={"max_steps": 80})
    assert started.status_code == 200
    episode_id = started.json()["episode_id"]

    snapshots = client.get(f"/episodes/{episode_id}/snapshots")
    assert snapshots.status_code == 200
    assert snapshots.json()["snapshots"]

    step = client.post(f"/episodes/{episode_id}/step")
    assert step.status_code == 200
    assert step.json()["cursor"] == 1

    first = client.get(f"/episodes/{episode_id}/snapshot/0")
    assert first.status_code == 200
    assert first.json()["step"] == 0
