from quakebot.agents import MockAgent
from quakebot.core.events import DebrisFallEvent
from quakebot.env import QuakeBotEnv
from quakebot.replay import run_episode_recording
from quakebot.scenario import ScenarioConfig


def random_config(seed: int = 42) -> ScenarioConfig:
    return ScenarioConfig(random_events_enabled=True, seed=seed, max_steps=140)


def event_sequence(seed: int) -> list[tuple[str, str, str]]:
    env = QuakeBotEnv(config=random_config(seed))
    agent = MockAgent()
    while not env.done and env.step_count < 35:
        env.step(agent.act(env.observe()))
    return [(event.type, event.location, event.message) for event in env.world_events]


def test_random_events_disabled_generates_no_structured_random_events():
    env = QuakeBotEnv()
    for _ in range(20):
        env.step({"type": "look"})
    assert env.world_events == []


def test_same_seed_produces_same_event_sequence():
    assert event_sequence(42) == event_sequence(42)


def test_different_seeds_can_produce_different_event_sequence():
    assert event_sequence(42) != event_sequence(43)


def test_debris_fall_can_increase_room_structural_risk():
    env = QuakeBotEnv(config=random_config())
    event = DebrisFallEvent(
        id="event_test",
        step=1,
        location="Lobby",
        severity="medium",
        message="Debris falls in Lobby.",
        effects={"structural_risk": "high"},
    )
    env._apply_world_event(event)
    assert env.rooms["Lobby"].conditions["structural_risk"] == "high"


def test_debris_fall_can_block_connection_and_reject_movement():
    env = QuakeBotEnv(config=random_config())
    event = DebrisFallEvent(
        id="event_test",
        step=1,
        location="Entrance",
        severity="medium",
        message="Debris blocks Entrance <-> Lobby.",
        effects={"blocked_connection": ["Entrance", "Lobby"]},
        affected_connection=("Entrance", "Lobby"),
    )
    env._apply_world_event(event)
    result = env.step({"type": "move", "target": "Lobby"})
    assert not result.ok
    assert "blocked connection" in result.message
    assert ["Entrance", "Lobby"] in env.observe()["blocked_connections"]


def test_pathfinding_avoids_blocked_connections():
    env = QuakeBotEnv(config=random_config())
    env.blocked_connections.add(env._connection_key("Entrance", "Lobby"))
    assert env.next_step_towards("Entrance", "Storage") is None


def test_debris_fall_on_survivor_worsens_stability_and_priority():
    env = QuakeBotEnv(config=random_config())
    survivor = env.survivors["survivor_apartment_a"]
    before = survivor.stability
    event = DebrisFallEvent(
        id="event_test",
        step=1,
        location="Apartment_A",
        severity="high",
        message="Debris falls near survivor_apartment_a.",
        effects={"stability_delta": -20, "pain_delta": 4, "structural_risk": "high"},
        affected_survivor_id="survivor_apartment_a",
    )
    env._apply_world_event(event)
    assert survivor.stability < before
    assert survivor.can_walk is False
    assert survivor.condition_history
    assert survivor.priority in {"medium", "high", "critical"}


def test_treat_survivor_control_bleeding_stops_severe_bleeding_deterioration():
    env = QuakeBotEnv(config=random_config())
    survivor = env.survivors["survivor_basement"]
    survivor.discovered = True
    env.location = "Basement"
    env.step({"type": "perform_primary_survey", "target": "survivor_basement"})
    env.step({"type": "treat_survivor", "target": "survivor_basement", "treatment": "control_bleeding"})
    env.step_count = 45
    events = env.event_engine.condition_worsening_events(env)
    assert survivor.bleeding_controlled
    assert all(event.effects.get("reason") != "uncontrolled severe bleeding" for event in events)


def test_treat_survivor_support_breathing_slows_laboured_breathing_deterioration():
    env = QuakeBotEnv(config=random_config())
    survivor = env.survivors["survivor_basement"]
    survivor.discovered = True
    env.location = "Basement"
    env.step({"type": "perform_primary_survey", "target": "survivor_basement"})
    env.step({"type": "treat_survivor", "target": "survivor_basement", "treatment": "support_breathing"})
    env.step_count = 48
    events = env.event_engine.condition_worsening_events(env)
    assert survivor.breathing_supported
    assert all(event.effects.get("reason") != "unsupported laboured breathing" for event in events)


def test_observation_includes_dynamic_event_fields():
    env = QuakeBotEnv(config=random_config())
    env._apply_world_event(
        DebrisFallEvent(
            id="event_test",
            step=1,
            location="Entrance",
            severity="medium",
            message="Debris blocks Entrance <-> Lobby.",
            effects={"blocked_connection": ["Entrance", "Lobby"]},
            affected_connection=("Entrance", "Lobby"),
        )
    )
    obs = env.observe()
    assert "recent_events" in obs
    assert "blocked_connections" in obs
    assert "active_hazards" in obs


def test_replay_snapshots_include_events_and_blocked_connections():
    snapshots = run_episode_recording(config=random_config(), max_steps=15)
    assert any(snapshot.events_this_step for snapshot in snapshots)
    assert "blocked_connections" in snapshots[-1].to_dict()


def test_mock_agent_completes_seeded_random_event_scenario():
    env = QuakeBotEnv(config=random_config(42))
    agent = MockAgent()
    rejected = []
    while not env.done:
        action = agent.act(env.observe())
        result = env.step(action)
        if result.rejected:
            rejected.append(result.message)
    assert env.report_submitted
    assert not rejected
    assert all(survivor.accounted_for() for survivor in env.survivors.values())
    assert env.world_events
