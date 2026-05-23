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
    assert "mission_accounting" in encoded


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
    env = QuakeBotEnv(aftershock_step=2, block_basement_aftershock=True)
    env.step({"type": "look"})
    env.step({"type": "look"})
    assert env.aftershock_triggered
    assert env.rooms["Basement"].conditions["structural_risk"] == "severe"
    assert "Basement" not in env.rooms["Stairwell_B"].exits


def test_mission_cannot_finish_with_unaccounted_survivors():
    env = QuakeBotEnv()
    env.survivors["survivor_office"].evacuated = True
    env.survivors["survivor_apartment_a"].evacuated = True
    env.rescue_notified = True
    result = env.step({"type": "submit_report", "summary": "Two survivors rescued."})
    assert not result.ok
    assert "survivor_basement" in result.message
    assert not env.report_submitted


def test_survivor_cannot_be_marked_inaccessible_without_scan_or_access_attempt():
    env = QuakeBotEnv()
    env.survivors["survivor_basement"].discovered = True
    result = env.step({"type": "mark_survivor_inaccessible", "target": "survivor_basement"})
    assert not result.ok
    assert "before attempting access or scanning" in result.message


def test_scan_for_life_signs_confirms_basement_survivor_from_stairwell():
    env = QuakeBotEnv(aftershock_step=1)
    env.step({"type": "move", "target": "Lobby"})
    env.step({"type": "move", "target": "Stairwell_G"})
    env.step({"type": "move", "target": "Stairwell_B"})
    result = env.step({"type": "scan_for_life_signs"})
    survivor = env.survivors["survivor_basement"]
    assert result.ok
    assert survivor.discovered
    assert survivor.last_confirmed_location == "Basement"


def test_recommended_actions_point_to_basement_after_two_evacuations():
    env = QuakeBotEnv()
    env.survivors["survivor_office"].evacuated = True
    env.survivors["survivor_apartment_a"].evacuated = True
    env.rubble_status["Office"] = "removed"
    env.location = "Entrance"
    assert env.observe()["recommended_next_actions"] == [{"type": "move", "target": "Lobby"}]
    env.location = "Lobby"
    assert env.observe()["recommended_next_actions"] == [{"type": "move", "target": "Stairwell_G"}]


def test_inaccessible_basement_flow_requires_investigation_and_extraction_request():
    env = QuakeBotEnv(aftershock_step=1, block_basement_aftershock=True)
    env.step({"type": "move", "target": "Lobby"})
    env.step({"type": "move", "target": "Stairwell_G"})
    env.step({"type": "move", "target": "Stairwell_B"})
    env.step({"type": "scan_for_life_signs"})
    survivor = env.survivors["survivor_basement"]
    survivor.directly_assessed = True
    request = env.step({
        "type": "request_specialised_extraction",
        "target": "survivor_basement",
        "reason": "Basement access is blocked by severe structural collapse after scan from Stairwell_B.",
    })
    marked = env.step({"type": "mark_survivor_inaccessible", "target": "survivor_basement"})
    assert request.ok
    assert marked.ok
    assert survivor.extraction_requested
    assert survivor.inaccessible_confirmed
    assert survivor.accounted_for()


def test_no_carry_recommendation_for_trapped_survivor():
    env = QuakeBotEnv(aftershock_step=1)
    env.step({"type": "move", "target": "Lobby"})
    env.step({"type": "move", "target": "Stairwell_G"})
    env.step({"type": "move", "target": "Stairwell_B"})
    env.step({"type": "scan_for_life_signs"})
    env.step({"type": "move", "target": "Basement"})
    survivor = env.survivors["survivor_basement"]
    env.step({"type": "reassure_survivor", "target": "survivor_basement", "message": "I am here."})
    env.step({"type": "perform_primary_survey", "target": "survivor_basement"})
    env.step({"type": "apply_pressure_bandage", "target": "survivor_basement"})
    env.step({"type": "stabilise_survivor", "target": "survivor_basement"})
    actions = env.observe()["recommended_next_actions"]
    assert {"type": "carry_survivor", "target": "survivor_basement"} not in actions
    assert actions == [{"type": "request_specialised_extraction", "target": "survivor_basement"}]


def test_request_specialised_extraction_sets_awaiting_status():
    env = QuakeBotEnv(aftershock_step=1)
    env.step({"type": "move", "target": "Lobby"})
    env.step({"type": "move", "target": "Stairwell_G"})
    env.step({"type": "move", "target": "Stairwell_B"})
    env.step({"type": "scan_for_life_signs"})
    env.step({"type": "move", "target": "Basement"})
    env.step({"type": "perform_primary_survey", "target": "survivor_basement"})
    result = env.step({
        "type": "request_specialised_extraction",
        "target": "survivor_basement",
        "reason": "Directly assessed in severe structural risk; shoring team required.",
    })
    survivor = env.survivors["survivor_basement"]
    assert result.ok
    assert survivor.accounting_status == "awaiting_specialised_extraction"
    assert survivor.accounted_for()
    assert {"type": "carry_survivor", "target": "survivor_basement"} not in env.observe()["recommended_next_actions"]


def test_final_report_accepted_with_final_accounting_statuses():
    env = QuakeBotEnv()
    env.survivors["survivor_office"].evacuated = True
    env.survivors["survivor_apartment_a"].evacuated = True
    basement = env.survivors["survivor_basement"]
    basement.discovered = True
    basement.directly_seen = True
    basement.directly_assessed = True
    basement.extraction_requested = True
    env.rescue_notified = True
    result = env.step({"type": "submit_report", "summary": "All survivors accounted."})
    assert result.ok
    assert env.report_submitted


def test_shortest_path_helper_returns_next_hop():
    env = QuakeBotEnv()
    assert env.next_step_towards("Entrance", "Stairwell_G") == "Lobby"
    assert env.next_step_towards("Stairwell_1", "Apartment_A") == "Upper_Hallway"


def test_office_cues_disappear_after_evacuation():
    env = QuakeBotEnv()
    reach_hallway(env)
    
    obs_hallway = env.observe()
    assert "muffled knocking from Office" in obs_hallway["survivor_cues"]
    assert "muffled knocking from Office" in obs_hallway["heard_sounds"]
    assert "weak vibration toward Office" in obs_hallway["vibration_cues"]
    assert "Hallway" in env._rooms_with_survivor_cues()
    assert "Office" in env._rooms_with_survivor_cues()
    
    env.survivors["survivor_office"].evacuated = True
    
    obs_hallway_after = env.observe()
    assert "muffled knocking from Office" not in obs_hallway_after["survivor_cues"]
    assert "muffled knocking from Office" not in obs_hallway_after["heard_sounds"]
    assert "weak vibration toward Office" not in obs_hallway_after["vibration_cues"]
    
    env.location = "Office"
    obs_office = env.observe()
    assert "weak voice from rubble" not in obs_office["heard_sounds"]
    assert "survivor" not in obs_office["visible_objects"]


def test_apartment_a_cues_disappear_after_evacuation():
    env = QuakeBotEnv()
    env.step({"type": "move", "target": "Lobby"})
    env.step({"type": "move", "target": "Stairwell_G"})
    env.step({"type": "move", "target": "Stairwell_1"})
    env.step({"type": "move", "target": "Upper_Hallway"})
    
    obs_upper = env.observe()
    assert "frightened calling from Apartment_A" in obs_upper["heard_sounds"]
    
    env.survivors["survivor_apartment_a"].evacuated = True
    
    obs_upper_after = env.observe()
    assert "frightened calling from Apartment_A" not in obs_upper_after["heard_sounds"]


def test_rooms_with_survivor_cues_dynamic():
    env = QuakeBotEnv()
    assert "Hallway" in env._rooms_with_survivor_cues()
    assert "Office" in env._rooms_with_survivor_cues()
    assert "Upper_Hallway" in env._rooms_with_survivor_cues()
    assert "Apartment_A" in env._rooms_with_survivor_cues()
    assert "Basement" in env._rooms_with_survivor_cues()
    
    env.survivors["survivor_office"].evacuated = True
    assert "Office" not in env._rooms_with_survivor_cues()
    
    env.survivors["survivor_basement"].evacuated = True
    assert "Hallway" not in env._rooms_with_survivor_cues()
    assert "Basement" not in env._rooms_with_survivor_cues()


def test_recommendation_does_not_loop_to_storage_after_office_evac():
    env = QuakeBotEnv()
    env.survivors["survivor_office"].evacuated = True
    env.rubble_status["Office"] = "removed"
    env.location = "Hallway"
    
    actions = env.observe()["recommended_next_actions"]
    assert actions == [{"type": "move", "target": "Lobby"}]


def test_rooms_to_search_in_exact_mode():
    env = QuakeBotEnv()
    search_rooms = env.observe()["rooms_to_search"]
    assert "Storage" not in search_rooms
    assert "Hallway" in search_rooms
    
    env.survivors["survivor_office"].evacuated = True
    env.survivors["survivor_apartment_a"].evacuated = True
    env.survivors["survivor_basement"].evacuated = True
    assert not env.observe()["rooms_to_search"]


def test_rooms_to_search_in_approximate_mode():
    from quakebot.scenario import ScenarioConfig
    env = QuakeBotEnv(config=ScenarioConfig(survivor_count_mode="approximate", survivor_count_min=1, survivor_count_max=5))
    search_rooms = env.observe()["rooms_to_search"]
    assert "Storage" in search_rooms
    assert "Office" not in search_rooms  # Blocked initially
