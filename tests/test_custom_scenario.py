import pytest
from quakebot.env import QuakeBotEnv
from quakebot.scenario_builder import RoomSpec, FloorSpec, SurvivorSpec, ScenarioSpec

def test_custom_scenario_can_run():
    r1 = RoomSpec("Room1")
    r2 = RoomSpec("Room2")
    r1.connect(r2)
    f1 = FloorSpec("ground", "Ground Floor", [r1, r2])
    s1 = SurvivorSpec(
        id="s1",
        name="John",
        location=r2,
        trapped=True,
    )
    scenario = ScenarioSpec(id="custom", name="Custom", floors=[f1], survivors=[s1])
    
    env = QuakeBotEnv(layout=scenario.compile())
    env.location = "Room1"
    
    # Can run a step
    obs = env.observe()
    assert "Room1" in obs["location"]
    
    # Adjacent scan works without hardcoded stairwell names
    res = env.step({"type": "sense_area", "mode": "life_signs", "target": "Room2"})
    assert res.ok
    assert "Room2" in env.scanned_rooms
    assert "s1" in [s.id for s in env.survivors.values() if s.discovered]

def test_unsafe_custom_room_can_be_marked_inaccessible():
    r1 = RoomSpec("Room1")
    r2 = RoomSpec("Room2", conditions={"structural_risk": "severe"})
    r1.connect(r2)
    f1 = FloorSpec("ground", "Ground Floor", [r1, r2])
    scenario = ScenarioSpec(id="custom", name="Custom", floors=[f1], survivors=[])
    
    env = QuakeBotEnv(layout=scenario.compile())
    env.location = "Room1"
    
    env.step({"type": "sense_area", "mode": "life_signs", "target": "Room2"})
    res = env.step({"type": "mark_room_inaccessible", "target": "Room2", "reason": "Too dangerous"})
    assert res.ok
    assert "Room2" in env.rooms_confirmed_inaccessible


def test_clear_obstruction_works_in_custom_python_scenario():
    r1 = RoomSpec("Start", objects=["debris"])
    r2 = RoomSpec("Clinic", blocked_by={"type": "debris", "status": "blocking", "required_location": "Start"})
    r1.connect(r2)
    floor = FloorSpec("ground", "Ground Floor", [r1, r2])
    survivor = SurvivorSpec(id="custom_survivor", name="Mira", location=r2, trapped=True)
    scenario = ScenarioSpec(id="blocked_custom", name="Blocked Custom", floors=[floor], survivors=[survivor])

    env = QuakeBotEnv(layout=scenario.compile())
    env.location = "Start"
    result = env.step({"type": "clear_obstruction", "target": "Clinic"})

    assert result.ok
    assert env.rubble_status["Clinic"] == "removed"
    assert env.step({"type": "move", "target": "Clinic"}).ok
    assert env.survivors["custom_survivor"].discovered

def test_evacuated_survivor_produces_no_cues():
    r1 = RoomSpec("Room1")
    r2 = RoomSpec("Room2")
    r1.connect(r2)
    s1 = SurvivorSpec(id="s1", name="John", location=r1, trapped=True)
    scenario = ScenarioSpec(id="custom", name="Custom", floors=[FloorSpec("ground", "Ground", [r1, r2])], survivors=[s1])
    
    env = QuakeBotEnv(layout=scenario.compile())
    env.location = "Room2"
    obs = env.observe()
    assert "muffled knocking from Room1" in obs["heard_sounds"]
    
    env.survivors["s1"].evacuated = True
    obs2 = env.observe()
    assert "muffled knocking from Room1" not in obs2["heard_sounds"]

def test_hidden_observations_dont_leak():
    from quakebot.scenario import ScenarioConfig
    r1 = RoomSpec("Room1")
    s1 = SurvivorSpec(id="s1", name="John", location=r1)
    scenario = ScenarioSpec(id="custom", name="Custom", floors=[FloorSpec("ground", "Ground", [r1])], survivors=[s1])
    
    env = QuakeBotEnv(layout=scenario.compile(), config=ScenarioConfig(survivor_location_mode="unknown", survivor_count_mode="approximate", survivor_count_min=1, survivor_count_max=3))
    env.location = "Room1"
    
    obs = env.observe()
    assert obs["mission_accounting"]["estimated_survivors"] == 3
