from dataclasses import dataclass, field
from typing import Any

PRIORITIES = {"low", "medium", "high", "critical"}


@dataclass
class Room:
    name: str
    floor: int
    floor_name: str
    exits: list[str]
    conditions: dict[str, Any]
    objects: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)


@dataclass
class Survivor:
    id: str
    name: str | None
    location: str
    trapped: bool
    reachable: bool
    conscious: bool
    responsive: bool
    breathing_status: str
    pulse_status: str
    bleeding: str
    pain_level: int
    can_walk: bool
    suspected_injuries: list[str]
    priority: str
    triage_questions_answered: list[str] = field(default_factory=list)
    checks_completed: list[str] = field(default_factory=list)
    stabilised: bool = False
    carried: bool = False
    evacuated: bool = False
    discovered: bool = False
    directly_seen: bool = False
    directly_assessed: bool = False
    pulse_checked: bool = False
    breathing_checked: bool = False
    bleeding_checked: bool = False
    extraction_requested: bool = False
    extraction_eta_steps: int | None = None
    extraction_status: str = "not_requested"
    safe_to_leave: bool = False
    immediate_life_threats_stabilised: bool = False
    last_monitored_step: int | None = None
    handoff_complete: bool = False
    inaccessible_confirmed: bool = False
    last_confirmed_location: str | None = None
    last_confirmed_step: int | None = None
    reassured: bool = False
    medical_evac_requested: bool = False
    stability: int = 100
    bleeding_controlled: bool = False
    airway_clear: bool = True
    breathing_supported: bool = False
    last_checked_step: int | None = None
    condition_history: list[str] = field(default_factory=list)

    def visible_condition(self) -> str:
        if self.bleeding == "severe":
            bleeding = "severe bleeding"
        elif self.bleeding == "minor":
            bleeding = "minor bleeding"
        else:
            bleeding = "no obvious bleeding"
        trapped = "trapped" if self.trapped else "not trapped"
        awareness = "awake" if self.conscious else "unconscious"
        return f"{awareness}, {trapped}, {bleeding}, breathing {self.breathing_status}"

    def public_status(self) -> dict[str, object]:
        return {
            "last_known_location": self.location,
            "status": "evacuated" if self.evacuated else "trapped" if self.trapped else "reachable",
            "priority": self.priority,
            "evacuated": self.evacuated,
            "checks_completed": list(self.checks_completed),
            "triage_questions_answered": list(self.triage_questions_answered),
            "stabilised": self.stabilised,
            "carried": self.carried,
            "discovered": self.discovered,
            "directly_seen": self.directly_seen,
            "directly_assessed": self.directly_assessed,
            "pulse_checked": self.pulse_checked,
            "breathing_checked": self.breathing_checked,
            "bleeding_checked": self.bleeding_checked,
            "extraction_requested": self.extraction_requested,
            "extraction_eta_steps": self.extraction_eta_steps,
            "extraction_status": self.extraction_status,
            "safe_to_leave": self.safe_to_leave,
            "immediate_life_threats_stabilised": self.immediate_life_threats_stabilised,
            "last_monitored_step": self.last_monitored_step,
            "handoff_complete": self.handoff_complete,
            "inaccessible_confirmed": self.inaccessible_confirmed,
            "last_confirmed_location": self.last_confirmed_location,
            "last_confirmed_step": self.last_confirmed_step,
            "accounted_for": self.accounted_for(),
            "accounting_status": self.accounting_status,
            "stability": self.stability,
            "bleeding_controlled": self.bleeding_controlled,
            "airway_clear": self.airway_clear,
            "breathing_supported": self.breathing_supported,
            "last_checked_step": self.last_checked_step,
            "condition_history": list(self.condition_history[-5:]),
        }

    def accounted_for(self) -> bool:
        if self.accounting_status == "awaiting_specialised_extraction":
            return self.safe_to_leave or self.handoff_complete
        return self.accounting_status in {"evacuated", "handoff_complete", "inaccessible_confirmed"}

    @property
    def accounting_status(self) -> str:
        if self.evacuated:
            return "evacuated"
        if self.handoff_complete:
            return "handoff_complete"
        if self.inaccessible_confirmed:
            return "inaccessible_confirmed"
        if self.directly_assessed and self.extraction_requested:
            return "awaiting_specialised_extraction"
        if self.directly_assessed:
            return "directly_assessed"
        if self.directly_seen:
            return "located"
        if self.discovered:
            return "suspected"
        return "unknown"

    def answer(self, question: str) -> str:
        text = question.lower()
        name = self.name or "I do not remember"
        if "name" in text:
            return f"My name is {name}."
        if "hurt" in text or "pain" in text:
            if "leg" in " ".join(self.suspected_injuries).lower():
                return "My left arm hurts, and my legs feel pinned."
            return "My side hurts, but I can talk to you."
        if "bleed" in text or "blood" in text:
            if self.bleeding == "severe":
                return "Yes, I am bleeding badly."
            if self.bleeding == "minor":
                return "Yes, my left arm is bleeding, but not heavily."
            return "I do not think I am bleeding."
        if "breath" in text:
            if self.breathing_status == "laboured":
                return "It is hard to breathe, but I am trying."
            if self.breathing_status == "fast":
                return "I can breathe, but I am scared and breathing fast."
            if self.breathing_status == "not_breathing":
                return ""
            return "I can breathe normally."
        if "leg" in text or "walk" in text or "move" in text:
            return "I can walk if you support me." if self.can_walk else "I can feel them, but I cannot stand safely."
        if "dizzy" in text:
            return "A little, but I can answer you."
        if "confus" in text or "know where" in text or "conscious" in text:
            return "I know you are here. I can answer you." if self.responsive else "I feel confused."
        if "trapped" in text or "stuck" in text or "pinned" in text:
            return "Yes, I am pinned." if self.trapped else "No, I can move with help."
        return "I can answer you. Please help me."


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str
    observation: dict[str, Any]
    done: bool
    score: int
    rejected: bool = False
    unsafe: bool = False


def calculate_triage_priority(survivor: Survivor, conditions: dict[str, Any] | None = None) -> str:
    conditions = conditions or {}
    worsening_hazard = survivor.trapped and conditions.get("structural_risk") == "severe"
    if (
        survivor.pulse_status == "none"
        or survivor.breathing_status == "not_breathing"
        or survivor.bleeding == "severe"
        or (not survivor.conscious and not survivor.responsive)
        or worsening_hazard
    ):
        return "critical"
    if (
        survivor.pulse_status == "weak"
        or survivor.breathing_status == "laboured"
        or survivor.trapped
        or survivor.bleeding == "severe"
    ):
        return "high"
    if survivor.conscious and survivor.breathing_status in {"normal", "fast"} and survivor.bleeding in {"none", "minor"} and not survivor.can_walk:
        return "medium"
    if survivor.can_walk and survivor.suspected_injuries and survivor.pain_level >= 3:
        return "medium"
    if survivor.can_walk and survivor.bleeding in {"none", "minor"} and survivor.breathing_status == "normal":
        return "low"
    return "medium"


def _priority_rank(priority: str) -> int:
    return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(priority, 0)
