"""Terminal rendering helpers for demo transcripts."""

from __future__ import annotations

from typing import Any

from .actions import Action
from .env import ActionResult


def format_observation_summary(obs: dict[str, Any]) -> str:
    conditions = obs["local_conditions"]
    return (
        f"at {obs['location']} | exits={obs['visible_exits']} | "
        f"objects={obs['visible_objects']} | sounds={obs['heard_sounds']} | "
        f"vibrations={obs.get('vibration_cues', [])} | survivor_cues={obs.get('survivor_cues', [])} | "
        f"blocked={obs.get('blocked_paths', {})} | recommended={obs.get('recommended_next_actions', [])} | "
        f"battery={obs['battery']} | smoke={conditions['smoke']} | "
        f"structural={conditions['structural_risk']}"
    )


def format_action(action: Action) -> str:
    return str(action.to_dict())


def format_step(step: int, obs: dict[str, Any], action: Action, result: ActionResult) -> str:
    status = "ok" if result.ok else "rejected"
    return "\n".join(
        [
            f"Step {step}",
            f"Observation: {format_observation_summary(obs)}",
            f"Action: {format_action(action)}",
            f"Result: {status} - {result.message}",
        ]
    )


def format_transcript(entries: list[str], final_report: str | None, score: int) -> str:
    lines = ["=== QuakeBot Transcript ===", *entries, f"Final score: {score}"]
    if final_report:
        lines.append(f"Final report: {final_report}")
    return "\n\n".join(lines)
