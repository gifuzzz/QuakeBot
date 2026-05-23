import json

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


def test_episode_snapshot_tracks_carrying_state():
    snapshots = run_episode_recording()
    carrying = [snapshot for snapshot in snapshots if snapshot.carrying_survivor]
    assert carrying
    assert carrying[0].carrying_survivor == "survivor_office"


def test_episode_snapshots_include_terminal_style_transcript_text():
    snapshots = run_episode_recording()
    first_action_snapshot = snapshots[1]
    assert first_action_snapshot.transcript_text.startswith("Step 1\nObservation:")
    assert "\nAction: {" in first_action_snapshot.transcript_text
    assert "\nResult: ok -" in first_action_snapshot.transcript_text
