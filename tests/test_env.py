from quakebot.scenario import ScenarioConfig
import json

from quakebot.env import QuakeBotEnv, Survivor, calculate_triage_priority


def build_severe_risk_board_room_env() -> QuakeBotEnv:
    from quakebot.scenario_builder import FloorSpec, RoomSpec, ScenarioSpec, SurvivorSpec

    entrance = RoomSpec("Entrance")
    hallway = RoomSpec("Hallway")
    board_room = RoomSpec(
        "Board Room",
        conditions={"structural_risk": "severe"},
    )
    entrance.connect(hallway)
    hallway.connect(board_room)

    ground = FloorSpec("ground", "Ground Floor", [entrance, hallway, board_room])
    survivor = SurvivorSpec(
        id="survivor_pari",
        name="Pari",
        location=board_room,
        trapped=True,
        reachable=False,
        conscious=True,
        responsive=True,
        breathing_status="laboured",
        pulse_status="weak",
        bleeding="severe",
        pain_level=8,
        can_walk=False,
        suspected_injuries=["crush injury"],
        priority="critical",
    )
    scenario = ScenarioSpec(
        id="severe_risk_bleeding_survivor",
        name="Severe Risk Bleeding Survivor",
        floors=[ground],
        survivors=[survivor],
    )
    return QuakeBotEnv(
        config=ScenarioConfig(survivor_location_mode="unknown"),
        layout=scenario.compile(),
    )


def reach_hallway(env: QuakeBotEnv) -> None:
    env.step({"type": "move", "target": "Lobby"})
    env.step({"type": "move", "target": "Hallway"})


def free_office_survivor(env: QuakeBotEnv) -> None:
    reach_hallway(env)
    env.step({"type": "clear_obstruction", "target": "Office"})
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
    assert "obstruction" in result.message


def test_office_obstruction_clearance_still_works():
    env = QuakeBotEnv()
    reach_hallway(env)
    assert env.observe()["blocked_paths"]["Office"]["status"] == "blocking"
    assert env.observe()["blocked_paths"]["Office"]["required_location"] == "Hallway"
    result = env.step({"type": "clear_obstruction", "target": "Office"})
    assert result.ok
    assert env.observe()["blocked_paths"] == {}
    assert env.survivors["survivor_office"].trapped


def test_recommended_actions_are_path_aware_for_office_rubble():
    env = QuakeBotEnv()
    env.survivors["survivor_basement"].evacuated = True
    env.survivors["survivor_apartment_a"].evacuated = True
    env.step({"type": "move", "target": "Lobby"})
    assert env.observe()["recommended_next_actions"] == [{"type": "move", "target": "Hallway"}]
    env.step({"type": "move", "target": "Hallway"})
    assert env.observe()["recommended_next_actions"] == [{"type": "clear_obstruction", "target": "Office"}]


def test_repeated_non_progress_actions_are_rejected():
    env = QuakeBotEnv()
    reach_hallway(env)
    env.step({"type": "clear_obstruction", "target": "Office"})
    repeated = env.step({"type": "clear_obstruction", "target": "Office"})
    assert not repeated.ok
    assert "already been removed" in repeated.message


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


def test_old_check_pulse_is_rejected_not_aliased():
    env = QuakeBotEnv()
    free_office_survivor(env)
    result = env.step({"type": "check_pulse", "target": "survivor_office"})
    assert not result.ok
    assert "Unsupported action type: check_pulse" in result.message


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
    env = QuakeBotEnv(aftershock_step=2, aftershock_blocks_exits=True, config=ScenarioConfig(aftershock_target_room='Basement'))
    env.step({"type": "look"})
    env.step({"type": "look"})
    assert env.aftershock_triggered
    assert env.rooms["Basement"].conditions["structural_risk"] == "severe"
    assert frozenset(["Stairwell_B", "Basement"]) in env.blocked_connections


def test_mission_cannot_finish_with_unaccounted_survivors():
    env = QuakeBotEnv()
    env.survivors["survivor_office"].evacuated = True
    env.survivors["survivor_apartment_a"].evacuated = True
    env.rescue_notified = True
    result = env.step({"type": "submit_report", "summary": "Two survivors rescued."})
    assert not result.ok
    assert "survivor_basement" in result.message
    assert not env.report_submitted


def test_old_mark_survivor_inaccessible_is_rejected():
    env = QuakeBotEnv()
    env.survivors["survivor_basement"].discovered = True
    result = env.step({"type": "mark_survivor_inaccessible", "target": "survivor_basement"})
    assert not result.ok
    assert "Unsupported action type: mark_survivor_inaccessible" in result.message


def test_sense_area_life_signs_confirms_basement_survivor_from_stairwell():
    env = QuakeBotEnv(aftershock_step=1, config=ScenarioConfig(aftershock_target_room='Basement'))
    env.step({"type": "move", "target": "Lobby"})
    env.step({"type": "move", "target": "Stairwell_G"})
    env.step({"type": "move", "target": "Stairwell_B"})
    result = env.step({"type": "sense_area", "mode": "life_signs", "target": "Basement"})
    survivor = env.survivors["survivor_basement"]
    assert result.ok
    assert survivor.discovered
    assert survivor.last_confirmed_location == "Basement"


def test_no_repeated_life_sign_scan_after_survivor_detected():
    env = build_severe_risk_board_room_env()
    env.step({"type": "move", "target": "Hallway"})
    scan = env.step({"type": "sense_area", "mode": "life_signs", "target": "Board Room"})
    assert scan.ok
    assert env.survivors["survivor_pari"].discovered

    recommendations = env.observe()["recommended_next_actions"]
    assert recommendations
    assert recommendations[0] != {"type": "sense_area", "mode": "life_signs", "target": "Board Room"}
    assert not any(
        action["type"] == "sense_area" and action.get("mode") == "life_signs" and action.get("target") == "Board Room"
        for action in recommendations
    )


def test_severe_risk_room_blocks_casual_entry():
    env = build_severe_risk_board_room_env()
    env.step({"type": "move", "target": "Hallway"})
    result = env.step({"type": "move", "target": "Board Room"})
    assert not result.ok
    assert "emergency entry" in result.message


def test_severe_risk_room_allows_emergency_entry_for_confirmed_survivor():
    env = build_severe_risk_board_room_env()
    env.step({"type": "move", "target": "Hallway"})
    env.step({"type": "sense_area", "mode": "life_signs", "target": "Board Room"})
    result = env.step({"type": "move", "target": "Board Room"})
    assert result.ok
    assert env.location == "Board Room"


def test_bleeding_survivor_in_severe_room_prioritises_entry_or_treatment_over_search():
    env = build_severe_risk_board_room_env()
    env.step({"type": "move", "target": "Hallway"})
    env.step({"type": "sense_area", "mode": "life_signs", "target": "Board Room"})
    recommendations = env.observe()["recommended_next_actions"]
    assert recommendations
    assert recommendations[0]["type"] in {"move", "request_specialised_extraction"}
    assert not any(
        action["type"] == "sense_area" and action.get("mode") == "life_signs" and action.get("target") == "Board Room"
        for action in recommendations
    )


def test_sense_area_audio_and_vibration_work():
    env = QuakeBotEnv()
    reach_hallway(env)
    audio = env.step({"type": "sense_area", "mode": "audio"})
    vibration = env.step({"type": "sense_area", "mode": "vibration"})
    assert audio.ok
    assert vibration.ok
    assert "Audio sensors" in audio.message
    assert "vibration" in vibration.message


def test_sense_area_rejects_invalid_and_non_adjacent_targets():
    env = QuakeBotEnv()
    invalid = env.step({"type": "sense_area", "mode": "life_signs", "target": "Nowhere"})
    far = env.step({"type": "sense_area", "mode": "life_signs", "target": "Office"})
    assert not invalid.ok
    assert "does not exist" in invalid.message
    assert not far.ok
    assert "not current or adjacent" in far.message


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
    env = QuakeBotEnv(aftershock_step=1, aftershock_blocks_exits=True, config=ScenarioConfig(aftershock_target_room='Basement'))
    env.step({"type": "move", "target": "Lobby"})
    env.step({"type": "move", "target": "Stairwell_G"})
    env.step({"type": "move", "target": "Stairwell_B"})
    env.step({"type": "sense_area", "mode": "life_signs", "target": "Basement"})
    survivor = env.survivors["survivor_basement"]
    survivor.directly_assessed = True
    request = env.step({
        "type": "request_specialised_extraction",
        "target": "survivor_basement",
        "reason": "Basement access is blocked by severe structural collapse after scan from Stairwell_B.",
    })
    marked = env.step({"type": "mark_room_inaccessible", "target": "Basement", "reason": "Basement access blocked by severe structural collapse."})
    assert request.ok
    assert marked.ok
    assert survivor.extraction_requested
    assert "Basement" in env.rooms_confirmed_inaccessible


def test_no_carry_recommendation_for_trapped_survivor():
    env = QuakeBotEnv(aftershock_step=1, config=ScenarioConfig(aftershock_target_room='Basement'))
    env.step({"type": "move", "target": "Lobby"})
    env.step({"type": "move", "target": "Stairwell_G"})
    env.step({"type": "move", "target": "Stairwell_B"})
    env.step({"type": "sense_area", "mode": "life_signs", "target": "Basement"})
    survivor = env.survivors["survivor_basement"]
    actions = env.observe()["recommended_next_actions"]
    assert {"type": "carry_survivor", "target": "survivor_basement"} not in actions
    assert actions[0]["type"] in {"move", "request_specialised_extraction"}
    assert not any(action["type"] == "sense_area" and action.get("target") == "Basement" for action in actions)


def test_request_specialised_extraction_sets_awaiting_status():
    env = QuakeBotEnv(aftershock_step=1, config=ScenarioConfig(aftershock_target_room='Basement'))
    env.step({"type": "move", "target": "Lobby"})
    env.step({"type": "move", "target": "Stairwell_G"})
    env.step({"type": "move", "target": "Stairwell_B"})
    env.step({"type": "sense_area", "mode": "life_signs", "target": "Basement"})
    result = env.step({
        "type": "request_specialised_extraction",
        "target": "survivor_basement",
        "reason": "Directly assessed in severe structural risk; shoring team required.",
    })
    survivor = env.survivors["survivor_basement"]
    assert result.ok
    assert survivor.extraction_requested
    assert not survivor.accounted_for()
    assert {"type": "carry_survivor", "target": "survivor_basement"} not in env.observe()["recommended_next_actions"]


def test_handoff_rejected_when_robot_not_with_survivor():
    env = QuakeBotEnv()
    survivor = env.survivors["survivor_apartment_a"]
    survivor.discovered = True
    survivor.directly_assessed = True
    survivor.extraction_requested = True
    survivor.extraction_status = "arrived"
    env.location = "Entrance"

    result = env.step({"type": "handoff_to_specialised_team", "target": survivor.id})

    assert not result.ok
    assert "move to Apartment_A first" in result.message
    assert not survivor.handoff_complete


def test_handoff_succeeds_when_robot_is_with_arrived_extraction_team():
    env = QuakeBotEnv()
    survivor = env.survivors["survivor_apartment_a"]
    survivor.discovered = True
    survivor.directly_assessed = True
    survivor.extraction_requested = True
    survivor.extraction_status = "arrived"
    env.location = survivor.location

    result = env.step({"type": "handoff_to_specialised_team", "target": survivor.id})

    assert result.ok
    assert survivor.handoff_complete
    assert survivor.safe_to_leave


def test_recommendations_do_not_repeat_extraction_request_from_access_point():
    env = QuakeBotEnv()
    survivor = env.survivors["survivor_basement"]
    survivor.discovered = True
    survivor.directly_assessed = True
    survivor.extraction_requested = True
    survivor.extraction_status = "en_route"
    env.location = "Stairwell_B"
    env.hazard_blocked_access.add("Basement")

    recs = env.observe()["recommended_next_actions"]
    assert not any(rec["type"] == "request_specialised_extraction" and rec.get("target") == survivor.id for rec in recs)
    assert recs == [{"type": "look"}]


def test_handoff_removes_survivor_presence_and_counts_toward_mission_finish():
    env = QuakeBotEnv()
    handed_off = env.survivors["survivor_apartment_a"]
    handed_off.discovered = True
    handed_off.directly_assessed = True
    handed_off.extraction_requested = True
    handed_off.extraction_status = "arrived"
    env.location = handed_off.location

    result = env.step({"type": "handoff_to_specialised_team", "target": handed_off.id})

    assert result.ok
    obs = env.observe()
    assert obs["local_survivors"] == []
    assert "survivor" not in obs["visible_objects"]
    assert handed_off.id not in env.observe()["known_survivors"] or env.observe()["known_survivors"][handed_off.id]["accounted_for"]

    env.survivors["survivor_office"].evacuated = True
    env.survivors["survivor_basement"].inaccessible_confirmed = True
    env.location = "Entrance"
    env.rescue_notified = True

    accounting = env._mission_accounting()
    assert accounting["mission_can_finish"] is True

    report = env.step({"type": "submit_report", "summary": "Two survivors were evacuated or safely handed off, and remaining hazards were reported."})
    assert report.ok
    assert report.done
    assert env.done


def test_final_report_blocked_until_specialised_survivor_safe_or_handed_off():
    env = QuakeBotEnv()
    env.survivors["survivor_office"].evacuated = True
    env.survivors["survivor_apartment_a"].evacuated = True
    basement = env.survivors["survivor_basement"]
    basement.discovered = True
    basement.directly_seen = True
    basement.directly_assessed = True
    basement.extraction_requested = True
    basement.extraction_status = "en_route"
    basement.safe_to_leave = False
    basement.handoff_complete = False
    env.rescue_notified = True
    env.location = "Entrance"

    result = env.step({"type": "submit_report", "summary": "All survivors accounted."})

    assert not result.ok
    assert "survivor_basement" in result.message


def test_treat_survivor_treatments_update_state():
    env = QuakeBotEnv()
    basement = env.survivors["survivor_basement"]
    basement.discovered = True
    env.location = "Basement"
    env.step({"type": "perform_primary_survey", "target": "survivor_basement"})
    assert env.step({"type": "treat_survivor", "target": "survivor_basement", "treatment": "control_bleeding"}).ok
    assert env.step({"type": "treat_survivor", "target": "survivor_basement", "treatment": "support_breathing"}).ok
    assert env.step({"type": "treat_survivor", "target": "survivor_basement", "treatment": "stabilise"}).ok
    assert env.step({"type": "treat_survivor", "target": "survivor_basement", "treatment": "monitor"}).ok
    assert basement.bleeding_controlled
    assert basement.breathing_supported
    assert basement.stabilised
    assert basement.last_monitored_step is not None


def test_evacuate_survivor_handles_walking_and_carried_survivors():
    env = QuakeBotEnv()
    apt = env.survivors["survivor_apartment_a"]
    apt.discovered = True
    env.location = "Apartment_A"
    env.step({"type": "perform_primary_survey", "target": apt.id})
    walking = env.step({"type": "evacuate_survivor", "target": apt.id})
    assert walking.ok
    assert apt.evacuated

    env = QuakeBotEnv()
    free_office_survivor(env)
    office = env.survivors["survivor_office"]
    env.step({"type": "perform_primary_survey", "target": office.id})
    env.step({"type": "free_survivor", "target": office.id})
    carried = env.step({"type": "evacuate_survivor", "target": office.id})
    assert carried.ok
    assert office.evacuated
    assert "carried evacuation" in carried.message


def test_custom_frontend_layout_has_free_route_to_entrance():
    from quakebot.scenario_builder import FloorSpec, RoomSpec, ScenarioSpec, SurvivorSpec

    entrance = RoomSpec("Entrance")
    hallway = RoomSpec(
        "Hallway",
        conditions={"smoke": "light", "structural_risk": "medium"},
        objects=["loose_debris"],
    )
    office = RoomSpec(
        "Office",
        conditions={"smoke": "light", "structural_risk": "medium"},
        objects=["rubble"],
        blocked_by={"type": "rubble", "status": "blocking", "required_location": "Hallway"},
    )
    cafeteria = RoomSpec("Cafeteria")
    stairs0 = RoomSpec("Stairs Level 0")
    office1 = RoomSpec("Office 1")
    office2 = RoomSpec("Office 2")
    office3 = RoomSpec("Office 3")
    board = RoomSpec("Board Room")
    hallway1 = RoomSpec("Hallway 1")
    stairs1 = RoomSpec("Stairs Level 1")

    entrance.connect(hallway)
    hallway.connect(office)
    hallway.connect(cafeteria)
    hallway.connect(stairs0)
    stairs0.connect(stairs1)
    office1.connect(hallway1)
    office1.connect(board)
    office2.connect(hallway1)
    office3.connect(hallway1)
    board.connect(office1)
    hallway1.connect(office3)
    hallway1.connect(office2)
    hallway1.connect(office1)
    stairs1.connect(stairs0)
    stairs1.connect(hallway1)

    scenario = ScenarioSpec(
        "frontend_custom",
        "Frontend Custom Rescue",
        [
            FloorSpec("ground", "Ground Floor", [entrance, hallway, office, cafeteria, stairs0]),
            FloorSpec("floor_level_1", "Floor 1", [office1, office2, office3, board, hallway1, stairs1]),
        ],
        [
            SurvivorSpec(
                "survivor_pari",
                "Pari",
                board,
                trapped=False,
                reachable=False,
                conscious=False,
                responsive=False,
                breathing_status="fast",
                pulse_status="rapid",
                bleeding="minor",
                pain_level=12,
                can_walk=False,
                priority="high",
            ),
            SurvivorSpec(
                "survivor_luigi",
                "Luigi",
                office1,
                trapped=True,
                reachable=False,
                conscious=False,
                responsive=False,
                breathing_status="normal",
                pulse_status="normal",
                bleeding="none",
                pain_level=3,
                can_walk=False,
                suspected_injuries=["lost his pp"],
                priority="critical",
            ),
        ],
    )
    env = QuakeBotEnv(layout=scenario.compile())
    for action in [
        {"type": "move", "target": "Hallway"},
        {"type": "clear_obstruction", "target": "Office"},
        {"type": "move", "target": "Stairs Level 0"},
        {"type": "move", "target": "Stairs Level 1"},
        {"type": "move", "target": "Hallway 1"},
        {"type": "move", "target": "Office 1"},
        {"type": "reassure_survivor", "target": "survivor_luigi", "message": "I'm here with you. You're not alone."},
        {"type": "perform_primary_survey", "target": "survivor_luigi"},
        {"type": "treat_survivor", "target": "survivor_luigi", "treatment": "stabilise"},
        {"type": "free_survivor", "target": "survivor_luigi"},
    ]:
        assert env.step(action).ok

    result = env.step({"type": "evacuate_survivor", "target": "survivor_luigi"})
    assert result.ok
    assert "Entrance" in result.message


def test_custom_multi_floor_layout_normalises_one_way_stair_links_for_evacuation():
    from quakebot.scenario_builder import FloorSpec, RoomSpec, ScenarioSpec, SurvivorSpec

    entrance = RoomSpec("Entrance")
    hallway = RoomSpec("Hallway")
    stairs0 = RoomSpec("Stairs Level 0")
    office1 = RoomSpec("Office 1")
    hallway1 = RoomSpec("Hallway 1")
    stairs1 = RoomSpec("Stairs Level 1")

    entrance.connect(hallway)
    hallway.connect(stairs0)
    stairs0.connect(stairs1)
    office1.connect(hallway1)
    stairs1.connect(hallway1)

    scenario = ScenarioSpec(
        "frontend_custom_one_way",
        "Frontend Custom One-Way Rescue",
        [
            FloorSpec("ground", "Ground Floor", [entrance, hallway, stairs0]),
            FloorSpec("floor_level_1", "Floor 1", [office1, hallway1, stairs1]),
        ],
        [
            SurvivorSpec(
                "survivor_luigi",
                "Luigi",
                office1,
                trapped=False,
                reachable=True,
                conscious=False,
                responsive=False,
                breathing_status="normal",
                pulse_status="normal",
                bleeding="none",
                pain_level=3,
                can_walk=False,
                priority="critical",
            ),
        ],
    )
    env = QuakeBotEnv(layout=scenario.compile())
    env.location = "Office 1"
    env.survivors["survivor_luigi"].discovered = True
    env.survivors["survivor_luigi"].checks_completed = ["perform_primary_survey"]

    result = env.step({"type": "evacuate_survivor", "target": "survivor_luigi"})
    assert result.ok
    assert "Stairs Level 1" in result.message
    assert env.location == "Entrance"


def test_recommendations_handle_generic_obstruction_types_in_custom_layouts():
    from quakebot.scenario_builder import FloorSpec, RoomSpec, ScenarioSpec, SurvivorSpec

    entrance = RoomSpec("Entrance")
    hallway = RoomSpec("Hallway", blocked_by={"type": "collapsed_wall", "status": "blocking", "required_location": "Entrance"})
    stairs0 = RoomSpec("Stairs Level 0")
    hallway1 = RoomSpec("Hallway 1")
    office1 = RoomSpec("Office 1")
    board = RoomSpec("Board Room", blocked_by={"type": "furniture", "status": "blocking", "required_location": "Office 1"})

    entrance.connect(hallway)
    hallway.connect(stairs0)
    stairs1 = RoomSpec("Stairs Level 1")
    stairs0.connect(stairs1)
    stairs1.connect(hallway1)
    hallway1.connect(office1)
    office1.connect(board)

    scenario = ScenarioSpec(
        "frontend_custom_obstructions",
        "Frontend Custom Obstructions",
        [
            FloorSpec("ground", "Ground Floor", [entrance, hallway, stairs0]),
            FloorSpec("floor_level_1", "Floor 1", [hallway1, office1, board, stairs1]),
        ],
        [
            SurvivorSpec(
                "survivor_pari",
                "Pari",
                board,
                trapped=False,
                reachable=False,
                conscious=False,
                responsive=False,
                breathing_status="fast",
                pulse_status="rapid",
                bleeding="minor",
                pain_level=12,
                can_walk=False,
                priority="high",
            ),
        ],
    )
    env = QuakeBotEnv(layout=scenario.compile(), config=ScenarioConfig(active_floors=["ground", "floor_level_1"], survivor_count=1))

    assert env.observe()["recommended_next_actions"] == [{"type": "clear_obstruction", "target": "Hallway"}]

    assert env.step({"type": "clear_obstruction", "target": "Hallway"}).ok
    assert env.step({"type": "move", "target": "Hallway"}).ok
    assert env.step({"type": "move", "target": "Stairs Level 0"}).ok
    assert env.step({"type": "move", "target": "Stairs Level 1"}).ok
    assert env.step({"type": "move", "target": "Hallway 1"}).ok

    assert env.observe()["recommended_next_actions"] == [{"type": "move", "target": "Office 1"}]

    assert env.step({"type": "move", "target": "Office 1"}).ok
    assert env.observe()["recommended_next_actions"] == [{"type": "clear_obstruction", "target": "Board Room"}]


def test_trapped_survivor_cannot_be_evacuated_until_freed():
    env = QuakeBotEnv()
    free_office_survivor(env)
    env.step({"type": "perform_primary_survey", "target": "survivor_office"})
    result = env.step({"type": "evacuate_survivor", "target": "survivor_office"})
    assert not result.ok
    assert "Cannot evacuate trapped survivor" in result.message


def test_recommendations_only_contain_canonical_actions():
    from quakebot.actions import VALID_ACTION_TYPES

    env = QuakeBotEnv()
    for _ in range(12):
        for action in env.observe()["recommended_next_actions"]:
            assert action["type"] in VALID_ACTION_TYPES
        recs = env.observe()["recommended_next_actions"]
        if not recs:
            break
        env.step(recs[0])


def test_recommended_actions_validate_as_emitted():
    from quakebot.actions import parse_action

    env = QuakeBotEnv(aftershock_step=1, config=ScenarioConfig(aftershock_target_room="Basement"))
    visited_recommendations = 0
    for _ in range(40):
        recs = env.observe()["recommended_next_actions"]
        for recommendation in recs:
            valid, reason, _ = env._validate(parse_action(recommendation))
            assert valid, f"{recommendation} did not validate: {reason}"
            if recommendation["type"] == "move":
                assert recommendation["target"] in env.rooms[env.location].exits
            visited_recommendations += 1
        if not recs:
            break
        env.step(recs[0])
    assert visited_recommendations > 0


def test_recommended_moves_are_adjacent():
    env = QuakeBotEnv()
    for _ in range(30):
        recs = env.observe()["recommended_next_actions"]
        for recommendation in recs:
            if recommendation["type"] == "move":
                assert recommendation["target"] in env.rooms[env.location].exits
        if not recs:
            break
        env.step(recs[0])


def test_final_report_accepted_with_final_accounting_statuses():
    env = QuakeBotEnv()
    env.survivors["survivor_office"].evacuated = True
    env.survivors["survivor_apartment_a"].evacuated = True
    basement = env.survivors["survivor_basement"]
    basement.discovered = True
    basement.directly_seen = True
    basement.directly_assessed = True
    basement.extraction_requested = True
    basement.handoff_complete = True
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
    assert "muffled calling from Apartment_A" in obs_upper["heard_sounds"]
    
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


def test_rooms_to_search_in_unknown_exact_mode_before_all_discovered():
    from quakebot.scenario import ScenarioConfig

    env = QuakeBotEnv(config=ScenarioConfig(survivor_location_mode="unknown"))
    search_rooms = env.observe()["rooms_to_search"]
    assert "Lobby" in search_rooms
    assert "Hallway" in search_rooms
    assert search_rooms


def test_unknown_exact_mode_recommendation_progresses_past_lobby():
    from quakebot.scenario import ScenarioConfig

    env = QuakeBotEnv(config=ScenarioConfig(survivor_location_mode="unknown"))
    assert env.observe()["recommended_next_actions"] == [{"type": "move", "target": "Lobby"}]
    assert env.step({"type": "move", "target": "Lobby"}).ok
    assert env.observe()["recommended_next_actions"] == [{"type": "move", "target": "Hallway"}]


def test_rooms_to_search_in_approximate_mode():
    from quakebot.scenario import ScenarioConfig
    env = QuakeBotEnv(config=ScenarioConfig(survivor_count_mode="approximate", survivor_count_min=1, survivor_count_max=5))
    search_rooms = env.observe()["rooms_to_search"]
    assert "Storage" in search_rooms
    assert "Office" not in search_rooms  # Blocked initially

def test_unknown_mode_initial_observation_does_not_expose_ids():
    from quakebot.scenario import ScenarioConfig
    env = QuakeBotEnv(config=ScenarioConfig(survivor_location_mode="unknown"))
    obs = env.observe()
    obs_str = json.dumps(obs)
    assert "survivor_office" not in obs_str
    assert "survivor_apartment_a" not in obs_str
    assert "survivor_basement" not in obs_str

def test_unknown_mode_initial_recommendations_do_not_expose_hidden_ids_or_locations():
    from quakebot.scenario import ScenarioConfig
    env = QuakeBotEnv(config=ScenarioConfig(survivor_location_mode="unknown"))
    recommendations = json.dumps(env.observe()["recommended_next_actions"])
    assert "survivor_office" not in recommendations
    assert "survivor_apartment_a" not in recommendations
    assert "survivor_basement" not in recommendations
    assert "Office" not in recommendations
    assert "Apartment_A" not in recommendations
    assert "Basement" not in recommendations

def test_unknown_mode_initial_mission_accounting_no_unaccounted():
    from quakebot.scenario import ScenarioConfig
    env = QuakeBotEnv(config=ScenarioConfig(survivor_location_mode="unknown"))
    accounting = env.observe()["mission_accounting"]
    assert accounting["unaccounted"] == []
    assert accounting["discovered_survivors"] == []
    assert accounting["confirmed_survivors"] == 0
    assert accounting["estimated_survivors"] == 3


def test_initial_hidden_survivors_approximate_observation_has_no_location_leak():
    env = QuakeBotEnv(
        config=ScenarioConfig(
            survivor_location_mode="unknown",
            survivor_count_mode="approximate",
            survivor_count=4,
            survivor_count_min=2,
            survivor_count_max=5,
        )
    )
    obs = env.observe()
    accounting = obs["mission_accounting"]
    assert obs["known_survivors"] == {}
    assert obs["discovered_survivors"] == []
    assert obs["unknown_survivor_cues"] == []
    assert obs["rooms_with_survivor_cues"] == []
    assert accounting["total_known_or_suspected_survivors"] == 0

def test_entering_office_discovers_survivor():
    from quakebot.scenario import ScenarioConfig
    env = QuakeBotEnv(config=ScenarioConfig(survivor_location_mode="unknown"))
    reach_hallway(env)
    env.step({"type": "clear_obstruction", "target": "Office"})
    env.step({"type": "move", "target": "Office"})
    
    obs = env.observe()
    assert "survivor_office" in obs["known_survivors"]
    assert "survivor_office" in obs["mission_accounting"]["discovered_survivors"]
    assert "survivor_office" in obs["mission_accounting"]["unaccounted"]

def test_sense_area_life_signs_discovers_hidden_survivor():
    from quakebot.scenario import ScenarioConfig
    env = QuakeBotEnv(config=ScenarioConfig(survivor_location_mode="unknown"))
    env.step({"type": "move", "target": "Lobby"})
    env.step({"type": "move", "target": "Stairwell_G"})
    env.step({"type": "move", "target": "Stairwell_B"})
    env.step({"type": "sense_area", "mode": "life_signs", "target": "Basement"})
    
    obs = env.observe()
    assert "survivor_basement" in obs["known_survivors"]

def test_health_details_hidden_before_discovery():
    from quakebot.scenario import ScenarioConfig
    env = QuakeBotEnv(config=ScenarioConfig(survivor_location_mode="unknown"))
    reach_hallway(env)
    obs = env.observe()
    assert "muffled knocking from Office" in obs["unknown_survivor_cues"]
    assert "survivor_office" not in str(obs["unknown_survivor_cues"])

def test_exact_unknown_mode_cannot_finish_early():
    from quakebot.scenario import ScenarioConfig
    env = QuakeBotEnv(config=ScenarioConfig(survivor_location_mode="unknown", survivor_count_mode="exact", survivor_count=3))
    assert not env.observe()["mission_accounting"]["mission_can_finish"]

def test_approximate_unknown_mode_cannot_finish_before_clearing():
    from quakebot.scenario import ScenarioConfig
    env = QuakeBotEnv(config=ScenarioConfig(survivor_location_mode="unknown", survivor_count_mode="approximate", survivor_count_min=1, survivor_count_max=5))
    assert not env.observe()["mission_accounting"]["mission_can_finish"]
    assert len(env.observe()["mission_accounting"]["uncleared_reachable_rooms"]) > 0

def test_mockagent_hidden_survivors_exact():
    from quakebot.demo import run_episode
    env = run_episode(agent_kind="mock", approximate=False, scenario="hidden_survivors_exact")
    assert env.done
    assert env.score.total > 0
    assert env._mission_accounting()["mission_can_finish"]

def test_mockagent_hidden_survivors_approximate():
    from quakebot.demo import run_episode
    env = run_episode(agent_kind="mock", approximate=True, scenario="hidden_survivors_approximate")
    assert env.done
    assert env.score.total > 0
    assert not env._mission_accounting()["uncleared_reachable_rooms"]
    assert env._mission_accounting()["mission_can_finish"]

def test_generated_small_demo_completes():
    from quakebot.demo import run_episode
    env = run_episode(agent_kind="mock", scenario="generated_small", seed=7)
    assert env.done
    assert env.report_submitted
    assert env._mission_accounting()["mission_can_finish"]


def test_severe_risk_bleeding_survivor_demo_completes():
    from quakebot.demo import run_episode

    env = run_episode(agent_kind="mock", scenario="severe_risk_bleeding_survivor", seed=7)
    assert env.done
    assert env.report_submitted
    assert env._mission_accounting()["mission_can_finish"]
