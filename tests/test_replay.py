import json

from quakebot.actions import Action
from quakebot.agents import RecommendedActionAgent
from quakebot.scenario import LoadedLayout, ScenarioConfig
from quakebot.replay import run_episode_recording, snapshots_to_dicts


def test_episode_recording_is_json_serialisable():
    snapshots = run_episode_recording()
    data = snapshots_to_dicts(snapshots)
    encoded = json.dumps(data)
    assert "robot_location" in encoded
    assert "known_survivors" in encoded
    assert "rubble_states" in encoded


def test_episode_recording_contains_final_success_state():
    snapshots = run_episode_recording()
    final = snapshots[-1]
    assert final.score > 0
    assert sum(1 for survivor in final.all_survivors.values() if survivor["evacuated"]) >= 2
    assert final.action is not None
    assert final.action["type"] == "submit_report"


def test_episode_snapshot_tracks_evacuation_state():
    snapshots = run_episode_recording()
    evacuated = [
        snapshot
        for snapshot in snapshots
        if snapshot.all_survivors["survivor_office"]["evacuated"]
    ]
    assert evacuated
    assert evacuated[0].all_survivors["survivor_office"]["accounting_status"] == "evacuated"


def test_episode_snapshots_include_terminal_style_transcript_text():
    snapshots = run_episode_recording()
    first_action_snapshot = snapshots[1]
    assert first_action_snapshot.transcript_text.startswith("Step 1\nObservation:")
    assert "\nAction: {" in first_action_snapshot.transcript_text
    assert "\nResult: ok -" in first_action_snapshot.transcript_text


def test_custom_layout_random_events_do_not_require_basement_room():
    class SlowAgent:
        def act(self, observation):
            return Action(type="look")

    layout = LoadedLayout(
        layout_id="custom_no_basement",
        name="Custom No Basement",
        floors={
            "ground": {
                "name": "Ground",
                "level": 0,
                "rooms": {
                    "Entrance": {"connects_to": ["Office"]},
                    "Office": {"connects_to": ["Entrance"]},
                },
            }
        },
        survivors={
            "survivor_office": {
                "name": "Elena",
                "location": "Office",
                "trapped": False,
                "reachable": True,
                "conscious": True,
                "responsive": True,
                "breathing_status": "normal",
                "pulse_status": "normal",
                "bleeding": "none",
                "pain_level": 1,
                "can_walk": True,
                "suspected_injuries": [],
                "priority": "medium",
            }
        },
        room_to_floor={"Entrance": "ground", "Office": "ground"},
        blocked_paths={},
    )
    config = ScenarioConfig(
        active_floors=["ground"],
        survivor_count_mode="exact",
        survivor_location_mode="known",
        survivor_count=1,
        random_events_enabled=True,
        max_steps=40,
    )

    snapshots = run_episode_recording(agent=SlowAgent(), config=config, layout=layout, max_steps=20)

    assert snapshots
    assert any(snapshot.events_this_step for snapshot in snapshots)


def test_recommended_action_agent_ignores_targetless_extraction_request():
    observation = {
        "recommended_next_actions": [{"type": "request_specialised_extraction"}],
        "mission_accounting": {"mission_can_finish": False},
        "location": "Office 1",
    }

    action = RecommendedActionAgent().act(observation)

    assert action.type == "look"
