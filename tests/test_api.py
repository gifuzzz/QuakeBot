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


def test_api_start_episode_with_frontend_custom_layout():
    client = TestClient(app)
    custom_layout = {
        "id": "api_custom",
        "name": "API Custom Scenario",
        "floors": [
            {
                "id": "ground",
                "name": "Ground Floor",
                "level": 0,
                "rooms": [
                    {"name": "Entrance", "connects_to": ["Office"]},
                    {"name": "Office", "connects_to": ["Entrance"]},
                ],
            }
        ],
        "survivors": [
            {
                "id": "survivor_office",
                "name": "Elena",
                "location": "Office",
                "trapped": False,
                "conscious": True,
                "responsive": True,
                "breathing_status": "normal",
                "pulse_status": "normal",
                "bleeding": "none",
                "pain_level": 2,
                "can_walk": True,
                "suspected_injuries": [],
                "priority": "medium",
            }
        ],
    }

    started = client.post(
        "/episodes/start",
        json={"max_steps": 80, "custom_layout": custom_layout},
    )
    assert started.status_code == 200
    episode_id = started.json()["episode_id"]

    snapshots = client.get(f"/episodes/{episode_id}/snapshots").json()["snapshots"]
    first = snapshots[0]
    assert set(first["room_states"]) == {"Entrance", "Office"}
    assert first["all_survivors"]["survivor_office"]["location"] == "Office"
    assert snapshots[-1]["action_ok"] is True
    assert snapshots[-1]["mission_accounting"]["mission_can_finish"] is True


def test_api_rejects_invalid_custom_layout_connection():
    client = TestClient(app)
    response = client.post(
        "/episodes/start",
        json={
            "custom_layout": {
                "id": "bad_custom",
                "name": "Bad Custom Scenario",
                "floors": [
                    {
                        "id": "ground",
                        "name": "Ground Floor",
                        "level": 0,
                        "rooms": [{"name": "Entrance", "connects_to": ["Missing_Room"]}],
                    }
                ],
                "survivors": [],
            }
        },
    )
    assert response.status_code == 422
    assert "unknown room" in response.json()["detail"]
