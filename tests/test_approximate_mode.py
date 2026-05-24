from quakebot.agents import MockAgent
from quakebot.env import QuakeBotEnv
from quakebot.scenario import ScenarioConfig


def approximate_config() -> ScenarioConfig:
    return ScenarioConfig(
        survivor_count_mode="approximate",
        survivor_count=4,
        survivor_count_min=3,
        survivor_count_max=5,
        max_steps=160,
        aftershock_target_room="Basement",
    )


def account_for_survivors(env: QuakeBotEnv) -> None:
    env.survivors["survivor_office"].evacuated = True
    env.survivors["survivor_apartment_a"].evacuated = True
    basement = env.survivors["survivor_basement"]
    basement.discovered = True
    basement.directly_seen = True
    basement.directly_assessed = True
    basement.extraction_requested = True
    basement.handoff_complete = True
    env.location = "Entrance"


def test_exact_mode_completion_does_not_require_room_clearance():
    env = QuakeBotEnv()
    account_for_survivors(env)
    env.rescue_notified = True
    result = env.step({"type": "submit_report", "summary": "All known survivors accounted."})
    assert result.ok
    assert env.report_submitted


def test_approximate_mode_cannot_finish_with_uncleared_reachable_rooms():
    env = QuakeBotEnv(config=approximate_config())
    account_for_survivors(env)
    accounting = env.observe()["mission_accounting"]
    assert not accounting["mission_can_finish"]
    assert "uncleared_reachable_rooms" in accounting
    assert accounting["uncleared_reachable_rooms"]


def test_submit_report_rejected_in_approximate_mode_if_rooms_remain_uncleared():
    env = QuakeBotEnv(config=approximate_config())
    account_for_survivors(env)
    env.rescue_notified = True
    result = env.step({"type": "submit_report", "summary": "Known survivors accounted."})
    assert not result.ok
    assert "reachable rooms remain uncleared" in result.message
    assert not env.report_submitted


def test_search_room_updates_current_room_to_searched_then_cleared():
    env = QuakeBotEnv(config=approximate_config())
    env.step({"type": "move", "target": "Lobby"})
    result = env.step({"type": "search_room"})
    assert result.ok
    assert env.room_search_status["Lobby"] == "cleared"
    cleared = env.step({"type": "mark_room_cleared", "target": "Lobby"})
    assert cleared.ok
    assert env.room_search_status["Lobby"] == "cleared"


def test_mark_room_cleared_rejected_if_room_was_not_searched():
    env = QuakeBotEnv(config=approximate_config())
    result = env.step({"type": "mark_room_cleared", "target": "Apartment_B"})
    assert not result.ok
    assert "entered or scanned" in result.message


def test_room_search_status_appears_in_observations():
    env = QuakeBotEnv(config=approximate_config())
    obs = env.observe()
    assert obs["survivor_count_mode"] == "approximate"
    assert "room_search_status" in obs
    assert obs["room_search_status"]["Entrance"] == "cleared"
    assert "rooms_to_search" in obs


def test_scan_for_life_signs_can_reveal_nearby_survivor_cues():
    env = QuakeBotEnv(config=approximate_config(), aftershock_step=1)
    env.step({"type": "move", "target": "Lobby"})
    env.step({"type": "move", "target": "Stairwell_G"})
    env.step({"type": "move", "target": "Stairwell_B"})
    result = env.step({"type": "scan_for_life_signs"})
    assert result.ok
    assert env.survivors["survivor_basement"].discovered
    assert "survivor_basement" in result.message


def test_recommended_next_actions_point_toward_uncleared_rooms():
    env = QuakeBotEnv(config=approximate_config())
    account_for_survivors(env)
    env.rubble_status["Office"] = "removed"
    for room in env.room_search_status:
        env.room_search_status[room] = "cleared"
    env.room_search_status["Apartment_B"] = "discovered"
    env.location = "Entrance"
    assert env.observe()["recommended_next_actions"] == [{"type": "move", "target": "Lobby"}]
    env.location = "Upper_Hallway"
    assert env.observe()["recommended_next_actions"] == [{"type": "move", "target": "Apartment_B"}]
    env.location = "Apartment_B"
    assert env.observe()["recommended_next_actions"] == [{"type": "search_room"}]


def test_mock_agent_completes_approximate_mode_and_clears_reachable_rooms():
    env = QuakeBotEnv(config=approximate_config())
    agent = MockAgent(approximate=True)
    actions = []
    while not env.done:
        action = agent.act(env.observe())
        actions.append(action.type)
        result = env.step(action)
        assert not result.rejected, result.message

    accounting = env.observe()["mission_accounting"]
    assert env.report_submitted
    assert env.rescue_notified
    assert accounting["mission_can_finish"]
    assert accounting["uncleared_reachable_rooms"] == []
    assert "search_room" in actions
    assert "mark_room_cleared" in actions
    assert "cleared" in env.final_report or env.final_report
