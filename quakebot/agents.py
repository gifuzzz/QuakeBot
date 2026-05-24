"""Agent interfaces for QuakeBot."""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
import os
from typing import Any
from urllib import error, request

from .actions import Action, parse_action
from .prompts import SYSTEM_PROMPT


class BaseAgent(ABC):
    @abstractmethod
    def act(self, observation: dict[str, Any]) -> Action:
        """Return the next structured action."""


class MockAgent(BaseAgent):
    """Deterministic agent that completes the embodied rescue scenario."""

    def __init__(self, *, approximate: bool = False) -> None:
        self.approximate = approximate
        base_plan = [
            {"type": "move", "target": "Lobby"},
            {"type": "move", "target": "Hallway"},
            {"type": "sense_area", "mode": "vibration"},
            {"type": "sense_area", "mode": "audio"},
            {"type": "clear_obstruction", "target": "Office"},
            {"type": "move", "target": "Office"},
            {"type": "reassure_survivor", "target": "survivor_office", "message": "I'm here with you. You're not alone."},
            {"type": "ask_medical_question", "target": "survivor_office", "question": "Can you tell me your name?"},
            {"type": "ask_medical_question", "target": "survivor_office", "question": "Where does it hurt?"},
            {"type": "perform_primary_survey", "target": "survivor_office"},
            {"type": "treat_survivor", "target": "survivor_office", "treatment": "control_bleeding"},
            {"type": "treat_survivor", "target": "survivor_office", "treatment": "stabilise"},
            {"type": "free_survivor", "target": "survivor_office"},
            {"type": "evacuate_survivor", "target": "survivor_office"},
            {"type": "move", "target": "Lobby"},
            {"type": "move", "target": "Stairwell_G"},
            {"type": "move", "target": "Stairwell_1"},
            {"type": "move", "target": "Upper_Hallway"},
            {"type": "sense_area", "mode": "audio"},
            {"type": "move", "target": "Apartment_A"},
            {"type": "reassure_survivor", "target": "survivor_apartment_a", "message": "I'm here. We'll get you out together."},
            {"type": "ask_medical_question", "target": "survivor_apartment_a", "question": "Can you tell me your name?"},
            {"type": "ask_medical_question", "target": "survivor_apartment_a", "question": "Can you walk if I support you?"},
            {"type": "perform_primary_survey", "target": "survivor_apartment_a"},
            {"type": "treat_survivor", "target": "survivor_apartment_a", "treatment": "stabilise"},
            {"type": "evacuate_survivor", "target": "survivor_apartment_a"},
            {"type": "move", "target": "Lobby"},
            {"type": "move", "target": "Stairwell_G"},
            {"type": "move", "target": "Stairwell_B"},
            {"type": "sense_area", "mode": "life_signs", "target": "Basement"},
            {"type": "mark_hazard", "hazard_type": "severe_structural_risk"},
            {
                "type": "request_specialised_extraction",
                "target": "survivor_basement",
                "reason": "survivor_basement is directly assessed in severe structural risk: trapped, weak pulse, laboured breathing, severe bleeding treated; needs shoring and specialised extraction team.",
            },
            {"type": "look"},
            {"type": "look"},
            {"type": "look"},
            {"type": "look"},
            {"type": "look"},
            {"type": "look"},
            {"type": "look"},
            {"type": "look"},
            {"type": "handoff_to_specialised_team", "target": "survivor_basement"},
        ]
        
        self.plan = base_plan
        self.index = 0

    def act(self, observation: dict[str, Any]) -> Action:
        if self.index >= len(self.plan):
            return self._recommended_or_look(observation)
        planned = parse_action(self.plan[self.index])
        adaptive = self._adaptive_action(observation, planned)
        if adaptive is not None:
            self.index += 1
            return adaptive
        action = planned
        self.index += 1
        return action

    def _adaptive_action(self, observation: dict[str, Any], planned: Action) -> Action | None:
        recommended = observation.get("recommended_next_actions") or []
        if not isinstance(recommended, list):
            recommended = []
        location = observation.get("location")
        blocked = {frozenset(pair) for pair in observation.get("blocked_connections", []) if isinstance(pair, list)}
        if planned.type == "move":
            if planned.target not in observation.get("visible_exits", []):
                return self._recommended_or_look(observation)
            if frozenset((str(location), str(planned.target))) in blocked:
                return self._recommended_or_look(observation)
            if planned.target in {"Balcony", "Basement", "Utility_Room", "Generator_Room"} and recommended and not any(
                rec.get("type") == "move" and rec.get("target") == planned.target for rec in recommended
            ):
                return self._recommended_or_look(observation)
        if planned.type == "handoff_to_specialised_team":
            if not any(
                rec.get("type") == "handoff_to_specialised_team" and rec.get("target") == planned.target
                for rec in recommended
            ):
                return self._recommended_or_look(observation)
        accounting = observation.get("mission_accounting", {})
        if planned.type in {"call_rescue_team", "submit_report"} and not accounting.get("mission_can_finish", False):
            return self._recommended_or_look(observation)
        return None

    @staticmethod
    def _recommended_or_look(observation: dict[str, Any]) -> Action:
        recommended = observation.get("recommended_next_actions") or []
        if recommended:
            rec = recommended[0]
            if rec.get("type") == "submit_report":
                return Action(type="submit_report", summary=_default_report_summary(observation))
            if rec.get("type") == "call_rescue_team":
                return Action(type="call_rescue_team", location=observation.get("location"), reason=_default_handoff_reason(observation))
            if rec.get("type") == "request_specialised_extraction":
                return Action(type="request_specialised_extraction", target=rec.get("target"), reason="Survivor requires specialised extraction team.")
            return parse_action(rec)
        return Action(type="look")


class RecommendedActionAgent(BaseAgent):
    """Generic deterministic agent for user-built semantic scenarios."""

    def act(self, observation: dict[str, Any]) -> Action:
        recommended = observation.get("recommended_next_actions") or []
        if recommended:
            rec = recommended[0]
            if rec.get("type") == "submit_report":
                return Action(type="submit_report", summary=_default_report_summary(observation))
            if rec.get("type") == "call_rescue_team":
                return Action(type="call_rescue_team", location=observation.get("location"), reason=_default_handoff_reason(observation))
            if rec.get("type") == "request_specialised_extraction":
                return Action(type="request_specialised_extraction", target=rec.get("target"), reason="Survivor requires specialised extraction team.")
            return parse_action(rec)

        accounting = observation.get("mission_accounting", {})
        if accounting.get("mission_can_finish"):
            if observation.get("location") != "Entrance":
                for exit_name in observation.get("visible_exits", []):
                    return Action(type="move", target=exit_name)
            if not accounting.get("rescue_notified"):
                return Action(type="call_rescue_team", location=observation.get("location"), reason=_default_handoff_reason(observation))
            return Action(type="submit_report", summary=_default_report_summary(observation))

        return Action(type="look")


def _default_handoff_reason(observation: dict[str, Any]) -> str:
    accounting = observation.get("mission_accounting", {})
    evacuated = accounting.get("evacuated", [])
    awaiting = accounting.get("awaiting_specialised_extraction", [])
    label = "survivor" if len(evacuated) == 1 else "survivors"
    return f"{len(evacuated)} {label} evacuated; awaiting specialised extraction: {', '.join(awaiting) or 'none'}."


def _default_report_summary(observation: dict[str, Any]) -> str:
    survivors = observation.get("known_survivors", {})
    parts = []
    for survivor_id, status in survivors.items():
        parts.append(
            f"{survivor_id}: {status.get('accounting_status')} priority {status.get('priority')}, "
            f"stability {status.get('stability')}, checks {status.get('checks_completed')}."
        )
    accounting = observation.get("mission_accounting", {})
    rooms = accounting.get("uncleared_reachable_rooms", [])
    return "All survivors accounted. " + " ".join(parts) + f" Uncleared reachable rooms: {rooms}."

def _approximate_clearance_plan() -> list[dict[str, str]]:
    return [
        {"type": "search_room"},
        {"type": "mark_room_cleared", "target": "Entrance"},
        {"type": "move", "target": "Lobby"},
        {"type": "search_room"},
        {"type": "mark_room_cleared", "target": "Lobby"},
        {"type": "move", "target": "Hallway"},
        {"type": "search_room"},
        {"type": "mark_room_cleared", "target": "Hallway"},
        {"type": "move", "target": "Office"},
        {"type": "search_room"},
        {"type": "mark_room_cleared", "target": "Office"},
        {"type": "move", "target": "Hallway"},
        {"type": "move", "target": "Storage"},
        {"type": "search_room"},
        {"type": "mark_room_cleared", "target": "Storage"},
        {"type": "move", "target": "Hallway"},
        {"type": "move", "target": "Lobby"},
        {"type": "move", "target": "Stairwell_G"},
        {"type": "search_room"},
        {"type": "mark_room_cleared", "target": "Stairwell_G"},
        {"type": "move", "target": "Stairwell_B"},
        {"type": "search_room"},
        {"type": "mark_room_cleared", "target": "Stairwell_B"},
        {"type": "move", "target": "Stairwell_G"},
        {"type": "move", "target": "Stairwell_1"},
        {"type": "search_room"},
        {"type": "mark_room_cleared", "target": "Stairwell_1"},
        {"type": "move", "target": "Upper_Hallway"},
        {"type": "search_room"},
        {"type": "mark_room_cleared", "target": "Upper_Hallway"},
        {"type": "move", "target": "Apartment_A"},
        {"type": "search_room"},
        {"type": "mark_room_cleared", "target": "Apartment_A"},
        {"type": "move", "target": "Upper_Hallway"},
        {"type": "move", "target": "Apartment_B"},
        {"type": "search_room"},
        {"type": "mark_room_cleared", "target": "Apartment_B"},
        {"type": "move", "target": "Balcony"},
        {"type": "search_room"},
        {"type": "mark_room_cleared", "target": "Balcony"},
        {"type": "move", "target": "Apartment_B"},
        {"type": "move", "target": "Upper_Hallway"},
        {"type": "move", "target": "Stairwell_1"},
        {"type": "move", "target": "Stairwell_G"},
        {"type": "move", "target": "Lobby"},
        {"type": "move", "target": "Entrance"},
    ]


class OpenAIAgent(BaseAgent):
    """Optional OpenAI-compatible chat-completions agent.

    This uses only the standard library so the project remains dependency-light.
    It is inactive unless an API key is present.
    """

    def __init__(
        self,
        *,
        model: str = "gpt-4.1-mini",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 30,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def act(self, observation: dict[str, Any]) -> Action:
        if not self.available:
            return Action(type="invalid", reason="OPENAI_API_KEY is not set.")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(observation, sort_keys=True)},
            ],
            "temperature": 0,
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            return parse_action(content)
        except Exception as exc:  # pragma: no cover - network path is optional
            return Action(type="invalid", reason=f"LLM request failed: {exc}")


class OllamaAgent(BaseAgent):
    """Optional Ollama chat agent for local Ollama or Ollama Cloud.

    Local Ollama does not require an API key, but it does require a running
    server and a pulled model, for example ``ollama pull llama3.1``.
    Ollama Cloud requires ``OLLAMA_API_KEY`` and uses ``https://ollama.com``.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        host: str | None = None,
        api_key: str | None = None,
        cloud: bool = False,
        timeout: int = 60,
    ) -> None:
        self.cloud = cloud
        self.model = model or os.getenv("OLLAMA_MODEL") or ("gpt-oss:120b" if cloud else "llama3.1")
        default_host = "https://ollama.com" if cloud else "http://localhost:11434"
        self.host = (host or os.getenv("OLLAMA_HOST") or default_host).rstrip("/")
        self.api_key = api_key or os.getenv("OLLAMA_API_KEY")
        self.timeout = timeout

    @property
    def available(self) -> bool:
        if self.cloud and not self.api_key:
            return False
        req = request.Request(f"{self.host}/api/tags", headers=self._headers(), method="GET")
        try:
            with request.urlopen(req, timeout=2):
                return True
        except (OSError, error.URLError):
            return False

    def act(self, observation: dict[str, Any]) -> Action:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(observation, sort_keys=True)},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.host}/api/chat",
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data.get("message", {}).get("content", "")
            return parse_action(content)
        except Exception as exc:  # pragma: no cover - local service path is optional
            return Action(type="invalid", reason=f"Ollama request failed: {exc}")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
