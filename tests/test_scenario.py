from quakebot.agents import MockAgent
from quakebot.env import QuakeBotEnv
from quakebot.scenario import ScenarioConfig, load_layout


def test_scenario_config_defaults_match_demo():
    config = ScenarioConfig()
    assert config.layout_pack == "default"
    assert config.active_floors == ["ground", "floor_1", "basement"]
    assert config.survivor_count_mode == "exact"
    assert config.survivor_count == 3
    assert config.random_events_enabled is False
    assert config.max_steps == 100


def test_semantic_layout_file_loads_expected_rooms_and_connections():
    layout = load_layout(ScenarioConfig())
    expected = {
        "Entrance",
        "Lobby",
        "Hallway",
        "Office",
        "Storage",
        "Stairwell_G",
        "Stairwell_1",
        "Upper_Hallway",
        "Apartment_A",
        "Apartment_B",
        "Balcony",
        "Stairwell_B",
        "Basement",
        "Utility_Room",
        "Generator_Room",
    }
    rooms = {room for floor in layout.floors.values() for room in floor["rooms"]}
    assert expected.issubset(rooms)
    assert "Hallway" in layout.floors["ground"]["rooms"]["Lobby"]["connects_to"]
    assert "Stairwell_B" in layout.floors["ground"]["rooms"]["Stairwell_G"]["connects_to"]


def test_layout_room_to_floor_mapping():
    layout = load_layout(ScenarioConfig())
    assert layout.room_to_floor["Office"] == "ground"
    assert layout.room_to_floor["Apartment_A"] == "floor_1"
    assert layout.room_to_floor["Basement"] == "basement"


def test_layout_hazards_blockages_and_survivors_load():
    layout = load_layout(ScenarioConfig())
    assert layout.floors["ground"]["rooms"]["Hallway"]["hazards"]["structural_risk"] == "medium"
    assert layout.floors["basement"]["rooms"]["Utility_Room"]["hazards"]["electrical_hazard"] is True
    assert layout.blocked_paths["Office"]["type"] == "rubble"
    assert layout.blocked_paths["Office"]["status"] == "blocking"
    assert layout.survivors["survivor_basement"]["breathing_status"] == "laboured"
    assert layout.survivors["survivor_basement"]["pulse_status"] == "weak"
    assert layout.survivors["survivor_basement"]["bleeding"] == "severe"


def test_environment_initialises_from_scenario_config():
    env = QuakeBotEnv(config=ScenarioConfig(max_steps=77))
    assert env.max_steps == 77
    assert env.room_to_floor["Office"] == "ground"
    assert env.rooms["Storage"].items == ["first_aid_kit"]
    assert env.rooms["Utility_Room"].conditions["electrical_hazard"] is True
    assert env.rubble_status["Office"] == "blocking"
    assert env.survivors["survivor_office"].breathing_status == "fast"


def test_visual_layout_is_not_required_for_environment_logic(monkeypatch):
    def fail_visual_load(*args, **kwargs):
        raise AssertionError("visual layout should not be used by QuakeBotEnv")

    monkeypatch.setattr("quakebot.scenario.load_visual_layout", fail_visual_load)
    env = QuakeBotEnv(config=ScenarioConfig())
    assert env.location == "Entrance"
    assert "Lobby" in env.rooms["Entrance"].exits


def test_mock_agent_still_completes_default_layout_scenario():
    env = QuakeBotEnv(config=ScenarioConfig())
    agent = MockAgent()
    while not env.done:
        result = env.step(agent.act(env.observe()))
        assert not result.rejected, result.message
    assert env.report_submitted
    assert all(survivor.accounted_for() for survivor in env.survivors.values())
