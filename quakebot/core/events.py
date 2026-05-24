"""Seeded dynamic event models and generation for QuakeBot."""

from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Any, Literal


EventType = Literal["aftershock", "debris_fall", "exit_blocked", "smoke_spread", "survivor_condition_worsens"]
Severity = Literal["low", "medium", "high", "severe", "critical"]


@dataclass(frozen=True)
class WorldEvent:
    """Serializable world event owned and applied by the environment."""

    id: str
    type: EventType
    step: int
    location: str
    severity: Severity
    message: str
    effects: dict[str, Any] = field(default_factory=dict)
    affected_survivor_id: str | None = None
    affected_connection: tuple[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "step": self.step,
            "location": self.location,
            "severity": self.severity,
            "message": self.message,
            "effects": dict(self.effects),
        }
        if self.affected_survivor_id:
            data["affected_survivor_id"] = self.affected_survivor_id
        if self.affected_connection:
            data["affected_connection"] = list(self.affected_connection)
        return data


class DebrisFallEvent(WorldEvent):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(type="debris_fall", **kwargs)


class ExitBlockedEvent(WorldEvent):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(type="exit_blocked", **kwargs)


class AftershockEvent(WorldEvent):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(type="aftershock", **kwargs)


class SmokeSpreadEvent(WorldEvent):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(type="smoke_spread", **kwargs)


class SurvivorConditionWorsensEvent(WorldEvent):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(type="survivor_condition_worsens", **kwargs)


class EventEngine:
    """Small deterministic event generator using only a local RNG."""

    def __init__(self, *, seed: int) -> None:
        self.rng = random.Random(seed)
        self.counter = 0

    def next_id(self) -> str:
        self.counter += 1
        return f"event_{self.counter:04d}"

    def maybe_world_event(self, env: Any, action_type: str) -> WorldEvent | None:
        """Generate a modest world event from current environment context."""

        step = int(env.step_count)
        if step > 0 and step % 14 == 0 and not getattr(env, "random_aftershock_triggered", False):
            target = self._aftershock_target(env)
            if target is None:
                return None
            return AftershockEvent(
                id=self.next_id(),
                step=step,
                location=target,
                severity="severe",
                message=f"A seeded aftershock shakes the building; {target} structural risk rises to severe.",
                effects={"structural_risk": "severe"},
            )

        if step > 0 and step % 11 == 0:
            smoky_rooms = [name for name, room in env.rooms.items() if room.conditions.get("smoke") not in (None, "none")]
            if smoky_rooms:
                source = self.rng.choice(smoky_rooms)
                targets = [room for room in env.rooms[source].exits if env.rooms[room].conditions.get("smoke") in (None, "none")]
            else:
                targets = []
            if targets:
                target = self.rng.choice(targets)
                return SmokeSpreadEvent(
                    id=self.next_id(),
                    step=step,
                    location=target,
                    severity="low",
                    message=f"Smoke drifts from {source} into {target}.",
                    effects={"smoke": "low", "source": source},
                )

        if step >= 20 and action_type in {"move", "clear_obstruction", "free_survivor", "evacuate_survivor"}:
            room = env.rooms[env.location]
            risk = room.conditions.get("structural_risk")
            probability = {"medium": 0.10, "high": 0.16, "severe": 0.08}.get(risk, 0.03)
            if self.rng.random() < probability:
                return self._debris_event(env, severity="medium" if risk in {None, "low"} else "high")

        return None

    def _aftershock_target(self, env: Any) -> str | None:
        configured = getattr(getattr(env, "config", None), "aftershock_target_room", None)
        if configured in getattr(env, "rooms", {}):
            return configured
        for helper_name in ("_highest_structural_risk_room", "_active_survivor_room", "_basement_like_room"):
            helper = getattr(env, helper_name, None)
            if callable(helper):
                target = helper()
                if target in env.rooms:
                    return target
        rooms = getattr(env, "rooms", {})
        return next(iter(rooms), None)

    def condition_worsening_events(self, env: Any) -> list[WorldEvent]:
        """Generate deterministic survivor deterioration events each step."""

        events: list[WorldEvent] = []
        for survivor in env.survivors.values():
            if survivor.evacuated or survivor.accounted_for():
                continue
            if not survivor.discovered:
                continue
            if survivor.bleeding == "severe" and not survivor.bleeding_controlled and env.step_count % 3 == 0:
                events.append(
                    SurvivorConditionWorsensEvent(
                        id=self.next_id(),
                        step=env.step_count,
                        location=survivor.location,
                        severity="high",
                        message=f"{survivor.id}'s severe bleeding reduces stability.",
                        effects={"stability_delta": -8, "reason": "uncontrolled severe bleeding"},
                        affected_survivor_id=survivor.id,
                    )
                )
            if survivor.breathing_status == "laboured" and not survivor.breathing_supported and env.step_count % 4 == 0:
                events.append(
                    SurvivorConditionWorsensEvent(
                        id=self.next_id(),
                        step=env.step_count,
                        location=survivor.location,
                        severity="high",
                        message=f"{survivor.id}'s laboured breathing lowers stability.",
                        effects={"stability_delta": -6, "reason": "unsupported laboured breathing"},
                        affected_survivor_id=survivor.id,
                    )
                )
            if survivor.trapped and env.step_count % 6 == 0:
                events.append(
                    SurvivorConditionWorsensEvent(
                        id=self.next_id(),
                        step=env.step_count,
                        location=survivor.location,
                        severity="medium",
                        message=f"{survivor.id} remains trapped and loses stability.",
                        effects={"stability_delta": -3, "reason": "prolonged entrapment"},
                        affected_survivor_id=survivor.id,
                    )
                )
        return events

    def _debris_event(self, env: Any, *, severity: Severity) -> WorldEvent:
        room_name = env.location
        room = env.rooms[room_name]
        survivors = [s for s in env.survivors.values() if s.location == room_name and not s.evacuated]
        if survivors and self.rng.random() < 0.45:
            survivor = self.rng.choice(survivors)
            return DebrisFallEvent(
                id=self.next_id(),
                step=env.step_count,
                location=room_name,
                severity=severity,
                message=f"Debris falls near {survivor.id}, causing new pain and instability.",
                effects={"stability_delta": -10, "pain_delta": 2, "structural_risk": "high"},
                affected_survivor_id=survivor.id,
            )
        blockable = [target for target in room.exits if target != "Entrance"]
        if blockable and self.rng.random() < 0.55:
            target = self.rng.choice(blockable)
            return DebrisFallEvent(
                id=self.next_id(),
                step=env.step_count,
                location=room_name,
                severity=severity,
                message=f"Debris falls in {room_name}, blocking {room_name} <-> {target}.",
                effects={"structural_risk": "high", "blocked_connection": [room_name, target]},
                affected_connection=(room_name, target),
            )
        return DebrisFallEvent(
            id=self.next_id(),
            step=env.step_count,
            location=room_name,
            severity=severity,
            message=f"Debris falls in {room_name}; structural risk increases.",
            effects={"structural_risk": "high"},
        )
