"""Episode recording helpers for visual replay."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .actions import Action
from .agents import BaseAgent, MockAgent
from .env import ActionResult, QuakeBotEnv
from .renderer import format_step
from .scenario import LoadedLayout, ScenarioConfig


@dataclass(frozen=True)
class EpisodeStep:
    """A serialisable snapshot of one environment step."""

    step: int
    robot_location: str
    current_floor: int
    floor_name: str
    action: dict[str, Any] | None
    action_description: str
    action_result: str
    action_ok: bool
    battery: int
    inventory: list[str]
    carrying_survivor: str | None
    room_states: dict[str, dict[str, Any]]
    rubble_states: dict[str, str]
    hazard_states: dict[str, dict[str, Any]]
    known_survivors: dict[str, dict[str, Any]]
    all_survivors: dict[str, dict[str, Any]]
    score: int
    dialogue_event_log: list[str]
    recommended_next_actions: list[dict[str, str]]
    blocked_paths: dict[str, dict[str, str]]
    mission_accounting: dict[str, Any]
    room_search_status: dict[str, str]
    rooms_to_search: list[str]
    events_this_step: list[dict[str, Any]]
    blocked_connections: list[list[str]]
    transcript_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "robot_location": self.robot_location,
            "current_floor": self.current_floor,
            "floor_name": self.floor_name,
            "action": self.action,
            "action_description": self.action_description,
            "action_result": self.action_result,
            "action_ok": self.action_ok,
            "battery": self.battery,
            "inventory": self.inventory,
            "carrying_survivor": self.carrying_survivor,
            "room_states": self.room_states,
            "rubble_states": self.rubble_states,
            "hazard_states": self.hazard_states,
            "known_survivors": self.known_survivors,
            "all_survivors": self.all_survivors,
            "score": self.score,
            "dialogue_event_log": self.dialogue_event_log,
            "recommended_next_actions": self.recommended_next_actions,
            "blocked_paths": self.blocked_paths,
            "mission_accounting": self.mission_accounting,
            "room_search_status": self.room_search_status,
            "rooms_to_search": self.rooms_to_search,
            "events_this_step": self.events_this_step,
            "blocked_connections": self.blocked_connections,
            "transcript_text": self.transcript_text,
        }


def run_episode_recording(
    agent: BaseAgent | None = None,
    *,
    config: ScenarioConfig | None = None,
    layout: LoadedLayout | None = None,
    max_steps: int | None = None,
) -> list[EpisodeStep]:
    """Run an episode and return replayable serialisable snapshots."""

    env = QuakeBotEnv(config=config, layout=layout)
    actor = agent or MockAgent(approximate=(config.survivor_count_mode == "approximate") if config else False)
    snapshots = [_snapshot(env, None, None)]
    while not env.done:
        observation = env.observe()
        action = actor.act(observation)
        result = env.step(action)
        snapshots.append(_snapshot(env, action, result, transcript_observation=observation))
        if max_steps is not None and env.step_count >= max_steps:
            break
    return snapshots


def stream_episode_recording(
    agent: BaseAgent | None = None,
    *,
    config: ScenarioConfig | None = None,
    layout: LoadedLayout | None = None,
    max_steps: int | None = None,
):
    """Run an episode and yield serialisable snapshots one by one."""

    env = QuakeBotEnv(config=config, layout=layout)
    actor = agent or MockAgent(approximate=(config.survivor_count_mode == "approximate") if config else False)
    yield _snapshot(env, None, None)
    while not env.done:
        observation = env.observe()
        action = actor.act(observation)
        result = env.step(action)
        yield _snapshot(env, action, result, transcript_observation=observation)
        if max_steps is not None and env.step_count >= max_steps:
            break


def snapshots_to_dicts(snapshots: list[EpisodeStep]) -> list[dict[str, Any]]:
    return [snapshot.to_dict() for snapshot in snapshots]


def _snapshot(
    env: QuakeBotEnv,
    action: Action | None,
    result: ActionResult | None,
    *,
    transcript_observation: dict[str, Any] | None = None,
) -> EpisodeStep:
    observation = env.observe()
    return EpisodeStep(
        step=env.step_count,
        robot_location=env.location,
        current_floor=observation["current_floor"],
        floor_name=observation["floor_name"],
        action=action.to_dict() if action else None,
        action_description=_describe_action(action),
        action_result=result.message if result else "Episode ready.",
        action_ok=result.ok if result else True,
        battery=env.battery,
        inventory=list(env.inventory),
        carrying_survivor=_carrying_survivor(env),
        room_states=_room_states(env),
        rubble_states=dict(env.rubble_status),
        hazard_states=_hazard_states(env),
        known_survivors=observation["known_survivors"],
        all_survivors={sid: _survivor_snapshot(survivor) for sid, survivor in env.survivors.items()},
        score=env.score.total,
        dialogue_event_log=list(env.event_log),
        recommended_next_actions=observation["recommended_next_actions"],
        blocked_paths=observation["blocked_paths"],
        mission_accounting=observation["mission_accounting"],
        room_search_status=observation["room_search_status"],
        rooms_to_search=observation["rooms_to_search"],
        events_this_step=observation.get("events_this_step", []),
        blocked_connections=observation.get("blocked_connections", []),
        transcript_text=_transcript_text(env, action, result, transcript_observation),
    )


def _describe_action(action: Action | None) -> str:
    if action is None:
        return "Initial state"
    args = []
    if action.target:
        args.append(action.target)
    if action.item:
        args.append(action.item)
    if action.priority:
        args.append(action.priority)
    return f"{action.type}({', '.join(args)})" if args else action.type


def _transcript_text(
    env: QuakeBotEnv,
    action: Action | None,
    result: ActionResult | None,
    observation: dict[str, Any] | None,
) -> str:
    if action is None or result is None:
        return "Step 0\nObservation: initial deployment\nAction: none\nResult: Episode ready."
    return format_step(env.step_count, observation or env.observe(), action, result)


def _carrying_survivor(env: QuakeBotEnv) -> str | None:
    carried = [survivor.id for survivor in env.survivors.values() if survivor.carried and not survivor.evacuated]
    return carried[0] if carried else None


def _room_states(env: QuakeBotEnv) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    for name, room in env.rooms.items():
        survivors = [sid for sid, survivor in env.survivors.items() if survivor.location == name and not survivor.evacuated]
        states[name] = {
            "floor": room.floor,
            "floor_name": room.floor_name,
            "exits": list(room.exits),
            "objects": list(room.objects),
            "items": list(room.items),
            "survivors": survivors,
            "conditions": dict(room.conditions),
        }
    return states


def _hazard_states(env: QuakeBotEnv) -> dict[str, dict[str, Any]]:
    hazards: dict[str, dict[str, Any]] = {}
    for name, room in env.rooms.items():
        conditions = room.conditions
        active = {
            key: value
            for key, value in conditions.items()
            if value not in (False, "none", "normal", "low")
        }
        if active:
            hazards[name] = active
    return hazards


def _survivor_snapshot(survivor: Any) -> dict[str, Any]:
    return {
        "id": survivor.id,
        "name": survivor.name,
        "location": survivor.location,
        "trapped": survivor.trapped,
        "reachable": survivor.reachable,
        "conscious": survivor.conscious,
        "responsive": survivor.responsive,
        "breathing_status": survivor.breathing_status,
        "pulse_status": survivor.pulse_status,
        "bleeding": survivor.bleeding,
        "pain_level": survivor.pain_level,
        "can_walk": survivor.can_walk,
        "suspected_injuries": list(survivor.suspected_injuries),
        "triage_questions_answered": list(survivor.triage_questions_answered),
        "checks_completed": list(survivor.checks_completed),
        "stabilised": survivor.stabilised,
        "carried": survivor.carried,
        "evacuated": survivor.evacuated,
        "priority": survivor.priority,
        "discovered": survivor.discovered,
        "directly_seen": survivor.directly_seen,
        "directly_assessed": survivor.directly_assessed,
        "pulse_checked": survivor.pulse_checked,
        "breathing_checked": survivor.breathing_checked,
        "bleeding_checked": survivor.bleeding_checked,
        "extraction_requested": survivor.extraction_requested,
        "inaccessible_confirmed": survivor.inaccessible_confirmed,
        "last_confirmed_location": survivor.last_confirmed_location,
        "last_confirmed_step": survivor.last_confirmed_step,
        "accounted_for": survivor.accounted_for(),
        "accounting_status": survivor.accounting_status,
        "medical_evac_requested": survivor.medical_evac_requested,
        "stability": survivor.stability,
        "bleeding_controlled": survivor.bleeding_controlled,
        "airway_clear": survivor.airway_clear,
        "breathing_supported": survivor.breathing_supported,
        "last_checked_step": survivor.last_checked_step,
        "condition_history": list(survivor.condition_history),
    }
