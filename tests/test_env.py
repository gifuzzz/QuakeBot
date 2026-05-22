import json

from quakebot.env import QuakeBotEnv, Survivor, calculate_triage_priority


def reach_hallway(env: QuakeBotEnv) -> None:
    env.step({"type": "move", "target": "Lobby"})
    env.step({"type": "move", "target": "Hallway"})


def free_office_survivor(env: QuakeBotEnv) -> None:
    reach_hallway(env)
    env.step({"type": "approach_rubble", "target": "Office"})
    env.step({"type": "lift_rubble", "target": "Office"})
    env.step({"type": "remove_rubble", "target": "Office"})
    env.step({"type": "move", "target": "Office"})


def test_initial_observation_is_json_serialisable():
    env = QuakeBotEnv()
    encoded = json.dumps(env.observe())
    assert "Entrance" in encoded
    assert "current_floor" in encoded
    assert "recommended_next_actions" in encoded


def test_multi_floor_graph_connectivity():
    env = QuakeBotEnv()
    assert "Stairwell_1" in env.rooms["Stairwell_G"].exits
    assert "Stairwell_B" in env.rooms["Stairwell_G"].exits
    assert "Apartment_A" in env.rooms["Upper_Hallway"].exits
    assert "Generator_Room" in env.rooms["Basement"].exits


def test_observation_includes_current_floor():
    env = QuakeBotEnv()
    obs = env.observe()
    assert obs["current_floor"] == 0
    assert obs["floor_name"] == "Ground"


def test_multiple_survivors_exist_in_world_state():
    env = QuakeBotEnv()
    assert set(env.survivors) == {"survivor_office", "survivor_apartment_a", "survivor_basement"}


def test_valid_movement_changes_location():
    env = QuakeBotEnv()
    result = env.step({"type": "move", "target": "Lobby"})
    assert result.ok
    assert env.location == "Lobby"


def test_blocked_office_cannot_be_entered_before_rubble_removal():
    env = QuakeBotEnv()
    reach_hallway(env)
    result = env.step({"type": "move", "target": "Office"})
    assert not result.ok
    assert "rubble" in result.message


def test_office_rubble_progression_still_works():
    env = QuakeBotEnv()
    reach_hallway(env)
    assert env.observe()["blocked_paths"]["Office"]["status"] == "blocking"
    assert env.observe()["blocked_paths"]["Office"]["required_location"] == "Hallway"
    env.step({"type": "approach_rubble", "target": "Office"})
    assert env.observe()["blocked_paths"]["Office"]["status"] == "approached"
    env.step({"type": "lift_rubble", "target": "Office"})
    assert env.observe()["blocked_paths"]["Office"]["status"] == "lifted"
    env.step({"type": "remove_rubble", "target": "Office"})
    assert env.observe()["blocked_paths"] == {}
    assert not env.survivors["survivor_office"].trapped


def test_recommended_actions_are_path_aware_for_office_rubble():
    env = QuakeBotEnv()
    env.step({"type": "move", "target": "Lobby"})
    assert env.observe()["recommended_next_actions"] == [{"type": "move", "target": "Hallway"}]
    env.step({"type": "move", "target": "Hallway"})
    assert env.observe()["recommended_next_actions"] == [{"type": "approach_rubble", "target": "Office"}]


def test_repeated_non_progress_actions_are_rejected():
    env = QuakeBotEnv()
    reach_hallway(env)
    env.step({"type": "approach_rubble", "target": "Office"})
    repeated = env.step({"type": "approach_rubble", "target": "Office"})
    assert not repeated.ok
    assert "lift_rubble" in repeated.message


def test_perform_primary_survey_updates_core_checks():
    env = QuakeBotEnv()
    free_office_survivor(env)
    result = env.step({"type": "perform_primary_survey", "target": "survivor_office"})
    checks = env.survivors["survivor_office"].checks_completed
    assert result.ok
    assert "check_airway" in checks
    assert "check_breathing" in checks
    assert "check_pulse" in checks
    assert "check_bleeding" in checks
    assert "check_responsiveness" in checks


def test_check_pulse_updates_survivor_checks_completed():
    env = QuakeBotEnv()
    free_office_survivor(env)
    result = env.step({"type": "check_pulse", "target": "survivor_office"})
    assert result.ok
    assert "check_pulse" in env.survivors["survivor_office"].checks_completed


def test_triage_priority_calculation_works_for_all_levels():
    critical = Survivor("c", None, "Basement", True, False, True, True, "laboured", "weak", "severe", 8, False, [], "critical")
    high = Survivor("h", None, "Office", True, False, True, True, "fast", "rapid", "minor", 6, False, [], "high")
    medium = Survivor("m", None, "Apartment_A", False, True, True, True, "fast", "normal", "minor", 4, False, [], "medium")
    low = Survivor("l", None, "Lobby", False, True, True, True, "normal", "normal", "none", 1, True, [], "low")
    assert calculate_triage_priority(critical) == "critical"
    assert calculate_triage_priority(high) == "high"
    assert calculate_triage_priority(medium) == "medium"
    assert calculate_triage_priority(low) == "low"


def test_survivor_specific_bleeding_answer():
    env = QuakeBotEnv()
    free_office_survivor(env)
    result = env.step({"type": "ask_medical_question", "target": "survivor_office", "question": "Are you bleeding?"})
    assert result.ok
    assert "left arm is bleeding" in result.message


def test_aftershock_modifies_world_state():
    env = QuakeBotEnv(aftershock_step=2)
    env.step({"type": "look"})
    env.step({"type": "look"})
    assert env.aftershock_triggered
    assert env.rooms["Basement"].conditions["structural_risk"] == "severe"
    assert "Basement" not in env.rooms["Stairwell_B"].exits
