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
            {"type": "sense_vibrations"},
            {"type": "listen_for_survivor"},
            {"type": "approach_rubble", "target": "Office"},
            {"type": "lift_rubble", "target": "Office"},
            {"type": "remove_rubble", "target": "Office"},
            {"type": "move", "target": "Storage"},
            {"type": "pick_up", "item": "first_aid_kit"},
            {"type": "move", "target": "Hallway"},
            {"type": "move", "target": "Office"},
            {"type": "reassure_survivor", "target": "survivor_office", "message": "I'm here with you. You're not alone."},
            {"type": "ask_medical_question", "target": "survivor_office", "question": "Can you tell me your name?"},
            {"type": "ask_medical_question", "target": "survivor_office", "question": "Where does it hurt?"},
            {"type": "ask_medical_question", "target": "survivor_office", "question": "Are you having trouble breathing?"},
            {"type": "perform_primary_survey", "target": "survivor_office"},
            {"type": "check_pulse", "target": "survivor_office"},
            {"type": "check_mobility", "target": "survivor_office"},
            {"type": "apply_pressure_bandage", "target": "survivor_office"},
            {"type": "stabilise_survivor", "target": "survivor_office"},
            {"type": "tag_triage_priority", "target": "survivor_office", "priority": "high"},
            {"type": "carry_survivor", "target": "survivor_office"},
            {"type": "escort_to_exit", "target": "survivor_office"},
            {"type": "move", "target": "Lobby"},
            {"type": "move", "target": "Stairwell_G"},
            {"type": "move", "target": "Stairwell_1"},
            {"type": "move", "target": "Upper_Hallway"},
            {"type": "listen_for_survivor"},
            {"type": "move", "target": "Apartment_A"},
            {"type": "reassure_survivor", "target": "survivor_apartment_a", "message": "I'm here. We'll get you out together."},
            {"type": "ask_medical_question", "target": "survivor_apartment_a", "question": "Can you tell me your name?"},
            {"type": "ask_medical_question", "target": "survivor_apartment_a", "question": "Can you walk if I support you?"},
            {"type": "perform_primary_survey", "target": "survivor_apartment_a"},
            {"type": "check_pulse", "target": "survivor_apartment_a"},
            {"type": "check_mobility", "target": "survivor_apartment_a"},
            {"type": "stabilise_survivor", "target": "survivor_apartment_a"},
            {"type": "tag_triage_priority", "target": "survivor_apartment_a", "priority": "medium"},
            {"type": "assist_walk", "target": "survivor_apartment_a"},
            {"type": "escort_to_exit", "target": "survivor_apartment_a"},
            {"type": "move", "target": "Lobby"},
            {"type": "move", "target": "Stairwell_G"},
            {"type": "move", "target": "Stairwell_B"},
            {"type": "scan_for_life_signs"},
            {"type": "move", "target": "Basement"},
            {"type": "reassure_survivor", "target": "survivor_basement", "message": "I found you. I'm coming in carefully and I will get you out."},
            {"type": "perform_primary_survey", "target": "survivor_basement"},
            {"type": "check_pulse", "target": "survivor_basement"},
            {"type": "check_breathing", "target": "survivor_basement"},
            {"type": "check_bleeding", "target": "survivor_basement"},
            {"type": "apply_pressure_bandage", "target": "survivor_basement"},
            {"type": "position_for_breathing", "target": "survivor_basement"},
            {"type": "stabilise_survivor", "target": "survivor_basement"},
            {"type": "tag_triage_priority", "target": "survivor_basement", "priority": "critical"},
            {"type": "mark_hazard", "hazard_type": "severe_structural_risk"},
            {
                "type": "request_specialised_extraction",
                "target": "survivor_basement",
                "reason": "survivor_basement is directly assessed in severe structural risk: trapped, weak pulse, laboured breathing, severe bleeding treated; needs shoring and specialised extraction team.",
            },
            {"type": "return_to_base"},
        ]
        report_suffix = (
            " Approximate survivor count mode: QuakeBot searched and cleared all reachable rooms before final report."
            if approximate
            else ""
        )
        final_handoff = [
            {
                "type": "call_rescue_team",
                "location": "Entrance",
                "reason": "2 survivors evacuated. survivor_basement is directly assessed, stabilised, and awaiting specialised extraction in Basement due severe structural risk and entrapment.",
            },
            {
                "type": "submit_report",
                "summary": (
                    "survivor_office: Elena, high priority, freed from Office rubble, primary survey complete, "
                    "pulse rapid, breathing fast, minor bleeding bandaged, carried to Entrance. "
                    "survivor_apartment_a: Jonas, medium priority, primary survey complete, pulse normal, "
                    "breathing normal, assisted walk to Entrance. survivor_basement: critical, directly investigated "
                    "in Basement after life-sign scan from Stairwell_B, primary survey complete, pulse weak, "
                    "breathing laboured, severe bleeding bandaged, stabilised, trapped, and awaiting specialised extraction. "
                    "Mission totals: 2 evacuated, 1 awaiting specialised extraction. Hazards reported: smoke in stairwell, "
                    "structural risk, Basement aftershock risk, Utility_Room electrical hazard."
                    + report_suffix
                ),
            },
        ]
        if approximate:
            self.plan = base_plan + _approximate_clearance_plan() + final_handoff
        else:
            self.plan = base_plan + final_handoff
        self.index = 0

    def act(self, observation: dict[str, Any]) -> Action:
        if self.index >= len(self.plan):
            return self._recommended_or_look(observation)
        planned = parse_action(self.plan[self.index])
        adaptive = self._adaptive_action(observation, planned)
        if adaptive is not None:
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
        local = observation.get("local_survivors") or []
        if local and recommended:
            rec_type = recommended[0].get("type")
            if rec_type in {"apply_pressure_bandage", "position_for_breathing", "stabilise_survivor"}:
                return parse_action(recommended[0])
        accounting = observation.get("mission_accounting", {})
        if planned.type in {"call_rescue_team", "submit_report"} and not accounting.get("mission_can_finish", False):
            return self._recommended_or_look(observation)
        return None

    @staticmethod
    def _recommended_or_look(observation: dict[str, Any]) -> Action:
        recommended = observation.get("recommended_next_actions") or []
        if recommended:
            if recommended[0].get("type") == "submit_report":
                return Action(type="submit_report", summary=_default_report_summary(observation))
            if recommended[0].get("type") == "call_rescue_team":
                return Action(type="call_rescue_team", location=observation.get("location"), reason=_default_handoff_reason(observation))
            return parse_action(recommended[0])
        return Action(type="look")


def _default_handoff_reason(observation: dict[str, Any]) -> str:
    accounting = observation.get("mission_accounting", {})
    evacuated = accounting.get("evacuated", [])
    awaiting = accounting.get("awaiting_specialised_extraction", [])
    return f"{len(evacuated)} survivors evacuated; awaiting specialised extraction: {', '.join(awaiting) or 'none'}."


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
        {"type": "return_to_base"},
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
