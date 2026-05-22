"""Action schema and defensive parsing for QuakeBot agents."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping


VALID_ACTION_TYPES = {
    "look",
    "move",
    "inspect",
    "listen_for_survivor",
    "sense_vibrations",
    "scan_for_life_signs",
    "approach_rubble",
    "lift_rubble",
    "remove_rubble",
    "clear_rubble",
    "pick_up",
    "assess_injuries",
    "ask_medical_question",
    "reassure_survivor",
    "deliver_supply",
    "stabilise_survivor",
    "check_pulse",
    "check_breathing",
    "check_airway",
    "check_bleeding",
    "check_responsiveness",
    "check_mobility",
    "perform_primary_survey",
    "apply_pressure_bandage",
    "position_for_breathing",
    "monitor_vitals",
    "tag_triage_priority",
    "request_medical_evac",
    "carry_survivor",
    "assist_walk",
    "escort_to_exit",
    "mark_hazard",
    "call_rescue_team",
    "return_to_base",
    "submit_report",
}


@dataclass(frozen=True)
class Action:
    """A structured action requested by an agent.

    The environment decides whether the action is valid and owns every state
    transition. This class deliberately contains no world mutation logic.
    """

    type: str
    target: str | None = None
    item: str | None = None
    hazard_type: str | None = None
    location: str | None = None
    reason: str | None = None
    question: str | None = None
    message: str | None = None
    priority: str | None = None
    summary: str | None = None
    raw: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"type": self.type}
        for field in ("target", "item", "hazard_type", "location", "reason", "question", "message", "priority", "summary"):
            value = getattr(self, field)
            if value is not None:
                data[field] = value
        return data


def parse_action(payload: str | Mapping[str, Any] | Action) -> Action:
    """Parse an agent response into an Action.

    Invalid JSON or malformed payloads become an ``invalid`` action so the
    harness can reject them cleanly instead of crashing.
    """

    if isinstance(payload, Action):
        return payload

    raw: Any = payload
    if isinstance(payload, str):
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError:
            extracted = extract_first_json_object(payload)
            if extracted is None:
                return Action(type="invalid", reason="Agent response was not valid JSON.")
            raw = extracted

    if not isinstance(raw, Mapping):
        return Action(type="invalid", reason="Action must be a JSON object.")

    action_type = raw.get("type")
    if not isinstance(action_type, str):
        return Action(type="invalid", reason="Action is missing string field 'type'.", raw=raw)

    kwargs: dict[str, Any] = {"type": action_type, "raw": raw}
    for field in ("target", "item", "hazard_type", "location", "reason", "question", "message", "priority", "summary"):
        value = raw.get(field)
        if value is not None and not isinstance(value, str):
            return Action(type="invalid", reason=f"Field '{field}' must be a string.", raw=raw)
        kwargs[field] = value
    return Action(**kwargs)


def extract_first_json_object(text: str) -> Mapping[str, Any] | None:
    """Extract the first balanced JSON object from a model response."""

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            return value
    return None
