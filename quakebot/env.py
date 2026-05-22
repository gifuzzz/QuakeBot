"""Multi-floor symbolic disaster-response environment for QuakeBot."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .actions import Action, VALID_ACTION_TYPES, parse_action
from .memory import Memory
from .tasks import ScoreBreakdown, is_success, score_environment


GOAL = "Locate survivors across floors, triage them, evacuate at least two, notify rescuers, and report hazards."
PRIORITIES = {"low", "medium", "high", "critical"}


@dataclass
class Room:
    name: str
    floor: int
    floor_name: str
    exits: list[str]
    conditions: dict[str, Any]
    objects: list[str] = field(default_factory=list)
    sounds: list[str] = field(default_factory=list)
    vibration_cues: list[str] = field(default_factory=list)
    survivor_cues: list[str] = field(default_factory=list)
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
    reassured: bool = False
    medical_evac_requested: bool = False

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
        }

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


class QuakeBotEnv:
    """Graph-based multi-floor rescue environment with medical triage."""

    def __init__(
        self,
        *,
        aftershock_step: int = 18,
        max_steps: int = 100,
        starting_battery: int = 120,
        block_basement_aftershock: bool = True,
    ) -> None:
        self.aftershock_step = aftershock_step
        self.max_steps = max_steps
        self.block_basement_aftershock = block_basement_aftershock
        self.rooms = self._build_world()
        self.survivors = self._build_survivors()
        self.location = "Entrance"
        self.step_count = 0
        self.battery = starting_battery
        self.inventory: list[str] = []
        self.memory = Memory()
        self.event_log: list[str] = ["QuakeBot deployed at Entrance: multi-floor rescue mode active."]
        self.aftershock_triggered = False
        self.rubble_status: dict[str, str] = {"Office": "blocking"}
        self.rescue_notified = False
        self.report_submitted = False
        self.hazards_reported_in_final_report = False
        self.invalid_actions = 0
        self.unsafe_attempts = 0
        self.fatal_hazard_entered = False
        self.final_report: str | None = None
        self.evacuation_order: list[str] = []
        self.triage_tags: dict[str, str] = {}
        self.hazard_marks: dict[str, list[str]] = {}
        self._sync_memory_from_current_room()

    def observe(self) -> dict[str, Any]:
        room = self.rooms[self.location]
        return {
            "step": self.step_count,
            "location": self.location,
            "current_floor": room.floor,
            "floor_name": room.floor_name,
            "goal": GOAL,
            "visible_exits": list(room.exits),
            "vertical_exits": self._vertical_exits(room),
            "local_conditions": dict(room.conditions),
            "visible_objects": list(room.objects + room.items),
            "heard_sounds": list(room.sounds),
            "vibration_cues": list(room.vibration_cues),
            "survivor_cues": self._survivor_cues(room),
            "local_survivors": self._local_survivor_observations(),
            "inventory": list(self.inventory),
            "battery": self.battery,
            "blocked_paths": self._blocked_paths(),
            "recommended_next_actions": self._recommended_next_actions(),
            "known_survivors": self._known_survivors(),
            "known_floors": self._known_floors(),
            "known_map": self.memory.to_dict(),
            "recent_events": self.event_log[-7:],
        }

    def step(self, payload: str | dict[str, Any] | Action) -> ActionResult:
        if self.done:
            return ActionResult(False, "Episode is already complete.", self.observe(), True, self.score.total, True)
        action = parse_action(payload)
        self.step_count += 1
        self.battery = max(0, self.battery - 2)
        self._maybe_trigger_aftershock()

        valid, reason, unsafe = self._validate(action)
        if not valid:
            if unsafe:
                self.unsafe_attempts += 1
            else:
                self.invalid_actions += 1
            self._record_event(f"Rejected {action.type}: {reason}")
            return ActionResult(False, reason, self.observe(), self.done, self.score.total, True, unsafe)

        message = self._apply(action)
        self._sync_memory_from_current_room()
        if self.battery == 0:
            self._record_event("Battery depleted.")
        return ActionResult(True, message, self.observe(), self.done, self.score.total)

    @property
    def done(self) -> bool:
        return is_success(self) or self.battery <= 0 or self.step_count >= self.max_steps or self.fatal_hazard_entered

    @property
    def score(self) -> ScoreBreakdown:
        return score_environment(self)

    def detected_count(self) -> int:
        return sum(1 for survivor in self.survivors.values() if survivor.discovered)

    def evacuated_count(self) -> int:
        return sum(1 for survivor in self.survivors.values() if survivor.evacuated)

    def _validate(self, action: Action) -> tuple[bool, str, bool]:
        if action.type == "invalid":
            return False, action.reason or "Invalid action payload.", False
        if action.type not in VALID_ACTION_TYPES:
            return False, f"Unknown action type: {action.type}", False
        if action.type == "move":
            if not action.target:
                return False, "move requires a target.", False
            return self._validate_move(action.target)
        if action.type == "approach_rubble":
            if action.target not in self.rubble_status:
                return False, "No rubble interaction exists for that target.", False
            if self.location != "Hallway":
                return False, "Office rubble can only be approached from Hallway.", False
            status = self.rubble_status[action.target]
            if status == "approached":
                return False, "Rubble already approached. Next physical rescue action should be lift_rubble.", False
            if status == "lifted":
                return False, "Rubble already lifted. Next physical rescue action should be remove_rubble.", False
            if status == "removed":
                return False, "Rubble already removed. Next action should be move to Office.", False
        if action.type in {"lift_rubble", "remove_rubble", "clear_rubble"}:
            target = action.target or ""
            if target not in self.rubble_status:
                return False, "No rubble interaction exists for that target.", False
            if self.location != "Hallway":
                return False, "Office rubble can only be removed from Hallway.", False
            status = self.rubble_status[target]
            if action.type == "lift_rubble" and status == "blocking":
                return False, "QuakeBot must approach and brace against the rubble first.", False
            if action.type == "lift_rubble" and status == "lifted":
                return False, "Rubble already lifted. Next physical rescue action should be remove_rubble.", False
            if action.type == "remove_rubble" and status != "lifted":
                return False, "Rubble must be lifted before remove_rubble.", False
            if status == "removed":
                return False, "Office entrance rubble has already been removed.", False
        if action.type == "pick_up":
            item = action.item or action.target
            if not item or item not in self.rooms[self.location].items:
                return False, f"Cannot pick up {item}; it is not visible here.", False
        if action.type in self._survivor_action_types():
            survivor = self._target_survivor(action.target)
            if survivor is None:
                return False, f"{action.type} requires a valid survivor id target.", False
            if not survivor.discovered and action.type not in {"scan_for_life_signs", "request_medical_evac"}:
                return False, f"Cannot {action.type} before discovering {survivor.id}.", False
            if action.type not in {"request_medical_evac"} and self.location != survivor.location:
                return False, "QuakeBot must be with that survivor to perform this action.", False
            if action.type in {"ask_medical_question"} and not action.question:
                return False, "ask_medical_question requires a question.", False
            if action.type == "reassure_survivor" and not action.message:
                return False, "reassure_survivor requires a short message.", False
            if action.type == "deliver_supply" and "first_aid_kit" not in self.inventory:
                return False, "Cannot deliver first aid without first_aid_kit.", False
            if action.type == "apply_pressure_bandage" and survivor.bleeding == "none":
                return False, "Pressure bandage is not needed; no bleeding detected.", False
            if action.type in {"carry_survivor", "assist_walk", "escort_to_exit"}:
                if survivor.trapped:
                    return False, "Cannot move survivor before freeing them from rubble.", False
                if "perform_primary_survey" not in survivor.checks_completed:
                    return False, "Cannot move survivor before primary survey.", False
                if action.type == "carry_survivor" and survivor.carried:
                    return False, "Survivor is already being carried. Next action should be escort_to_exit.", False
                if action.type == "assist_walk" and not survivor.can_walk:
                    return False, "Survivor cannot walk; carry action is required.", False
                if action.type == "escort_to_exit" and survivor.evacuated:
                    return False, "Survivor is already evacuated. Next action should be call_rescue_team or continue search.", False
            if action.type == "tag_triage_priority" and action.priority not in PRIORITIES:
                return False, "tag_triage_priority requires priority low, medium, high, or critical.", False
        if action.type == "mark_hazard" and not action.hazard_type:
            return False, "mark_hazard requires hazard_type.", False
        if action.type == "call_rescue_team":
            if self.evacuated_count() < 2:
                return False, "Notify rescue team after at least two survivors are evacuated.", False
        if action.type == "submit_report":
            if self.location != "Entrance":
                return False, "Cannot submit report unless QuakeBot is at Entrance.", False
            if self.evacuated_count() < 2 or not self.rescue_notified:
                return False, "Cannot submit report before minimum evacuation and rescue notification.", False
            if not action.summary:
                return False, "submit_report requires a summary.", False
        return True, "", False

    def _validate_move(self, target: str) -> tuple[bool, str, bool]:
        room = self.rooms[self.location]
        if target not in room.exits:
            return False, f"Cannot move to {target}; it is not adjacent to {self.location}.", False
        if target == "Office" and self.rubble_status.get("Office") != "removed":
            return False, "Cannot enter Office until rubble blocking the doorway is removed.", False
        conditions = self.rooms[target].conditions
        if conditions.get("electrical_hazard"):
            return False, f"Unsafe move rejected: {target} has an electrical hazard.", True
        if conditions.get("structural_risk") == "severe":
            return False, f"Unsafe move rejected: {target} has severe structural risk.", True
        return True, "", False

    def _apply(self, action: Action) -> str:
        handler = getattr(self, f"_do_{action.type}", None)
        message = handler(action) if handler else "No-op."
        self._record_event(message)
        return message

    def _do_look(self, action: Action) -> str:
        return f"QuakeBot scans {self.location} for hazards, survivors, and vertical exits."

    def _do_move(self, action: Action) -> str:
        self.location = action.target or self.location
        return f"QuakeBot moves to {self.location}."

    def _do_inspect(self, action: Action) -> str:
        return f"QuakeBot inspects {action.target or self.location}."

    def _do_listen_for_survivor(self, action: Action) -> str:
        room = self.rooms[self.location]
        if not room.sounds:
            return "No clear survivor sound detected here."
        for survivor in self._nearby_survivors():
            survivor.discovered = True
            self.memory.record_survivor(survivor.id)
        clue = "; ".join(room.sounds)
        self.memory.record_survivor_clue(clue)
        return f"Audio sensors isolate survivor cues: {clue}."

    def _do_sense_vibrations(self, action: Action) -> str:
        room = self.rooms[self.location]
        if not room.vibration_cues:
            return "No survivor-like vibration detected here."
        for survivor in self._nearby_survivors():
            survivor.discovered = True
            self.memory.record_survivor(survivor.id)
        clue = "; ".join(room.vibration_cues)
        self.memory.record_survivor_clue(clue)
        return f"QuakeBot feels structural vibration cues: {clue}."

    def _do_scan_for_life_signs(self, action: Action) -> str:
        found = self._nearby_survivors(include_current=True)
        for survivor in found:
            survivor.discovered = True
            self.memory.record_survivor(survivor.id)
        if found:
            return "Life-sign scan detects: " + ", ".join(f"{s.id} at {s.location}" for s in found) + "."
        return "No life signs detected nearby."

    def _do_approach_rubble(self, action: Action) -> str:
        self.rubble_status[action.target or "Office"] = "approached"
        return "QuakeBot plants its feet, braces its large hands against the Office rubble, and prepares to lift."

    def _do_lift_rubble(self, action: Action) -> str:
        self.rubble_status[action.target or "Office"] = "lifted"
        return "QuakeBot lifts the concrete slab with both hands, holding it clear of the doorway."

    def _do_remove_rubble(self, action: Action) -> str:
        self.rubble_status[action.target or "Office"] = "removed"
        survivor = self.survivors["survivor_office"]
        survivor.trapped = False
        survivor.reachable = True
        survivor.discovered = True
        self.rooms["Hallway"].objects = [obj for obj in self.rooms["Hallway"].objects if obj != "rubble"]
        self.memory.record_survivor(survivor.id)
        return "QuakeBot removes the rubble by hand. survivor_office is freed and reachable."

    _do_clear_rubble = _do_remove_rubble

    def _do_pick_up(self, action: Action) -> str:
        item = action.item or action.target or ""
        self.rooms[self.location].items.remove(item)
        self.inventory.append(item)
        return f"QuakeBot picks up {item}."

    def _do_reassure_survivor(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        survivor.reassured = True
        return f"QuakeBot tells {survivor.id}: '{action.message}'"

    def _do_ask_medical_question(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        answer = survivor.answer(action.question or "")
        survivor.triage_questions_answered.append(action.question or "")
        return f"QuakeBot asks {survivor.id}: '{action.question}' Answer: '{answer}'"

    def _do_assess_injuries(self, action: Action) -> str:
        return self._do_perform_primary_survey(action)

    def _do_perform_primary_survey(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        for check in ("check_airway", "check_breathing", "check_pulse", "check_bleeding", "check_responsiveness", "perform_primary_survey"):
            self._add_check(survivor, check)
        survivor.priority = calculate_triage_priority(survivor, self.rooms[survivor.location].conditions)
        return (
            f"Primary survey for {survivor.id}: airway clear, breathing {survivor.breathing_status}, "
            f"pulse {survivor.pulse_status}, bleeding {survivor.bleeding}, priority {survivor.priority}."
        )

    def _do_check_pulse(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        self._add_check(survivor, "check_pulse")
        return f"Pulse is {survivor.pulse_status} but present." if survivor.pulse_status != "none" else "No pulse detected."

    def _do_check_breathing(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        self._add_check(survivor, "check_breathing")
        return f"Breathing is {survivor.breathing_status}."

    def _do_check_airway(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        self._add_check(survivor, "check_airway")
        return "Airway clear." if survivor.breathing_status != "not_breathing" else "Airway requires immediate support."

    def _do_check_bleeding(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        self._add_check(survivor, "check_bleeding")
        return f"Bleeding status: {survivor.bleeding}."

    def _do_check_responsiveness(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        self._add_check(survivor, "check_responsiveness")
        return "Survivor is conscious and answering questions." if survivor.responsive else "Survivor is not responsive."

    def _do_check_mobility(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        self._add_check(survivor, "check_mobility")
        return "Survivor can walk with assistance." if survivor.can_walk else "Survivor cannot stand safely."

    def _do_deliver_supply(self, action: Action) -> str:
        return self._do_apply_pressure_bandage(action)

    def _do_apply_pressure_bandage(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        survivor.stabilised = True
        self._add_check(survivor, "apply_pressure_bandage")
        return f"QuakeBot applies a pressure bandage to {survivor.id}."

    def _do_position_for_breathing(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        survivor.stabilised = True
        self._add_check(survivor, "position_for_breathing")
        return f"QuakeBot positions {survivor.id} to support breathing."

    def _do_stabilise_survivor(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        survivor.stabilised = True
        self._add_check(survivor, "stabilise_survivor")
        return f"QuakeBot stabilises {survivor.id} before movement."

    def _do_monitor_vitals(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        self._add_check(survivor, "monitor_vitals")
        return f"QuakeBot monitors vitals for {survivor.id}: breathing {survivor.breathing_status}, pulse {survivor.pulse_status}."

    def _do_tag_triage_priority(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        survivor.priority = action.priority or survivor.priority
        self.triage_tags[survivor.id] = survivor.priority
        return f"{survivor.id} tagged as {survivor.priority} priority."

    def _do_carry_survivor(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        survivor.carried = True
        return f"QuakeBot lifts {survivor.id} securely in both arms."

    def _do_assist_walk(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        survivor.carried = True
        return f"QuakeBot supports {survivor.id} in an assisted walk."

    def _do_escort_to_exit(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        path = self._find_safe_path(self.location, "Entrance")
        if not path:
            self.invalid_actions += 1
            return "No safe path to Entrance is available."
        self.location = "Entrance"
        survivor.location = "Entrance"
        survivor.carried = False
        survivor.evacuated = True
        if survivor.id not in self.evacuation_order:
            self.evacuation_order.append(survivor.id)
        return f"QuakeBot escorts {survivor.id} to Entrance via {' -> '.join(path)}."

    def _do_mark_hazard(self, action: Action) -> str:
        hazard = action.hazard_type or "unknown"
        self.hazard_marks.setdefault(self.location, []).append(hazard)
        self.memory.record_hazard(self.location, hazard)
        return f"QuakeBot marks {hazard} at {self.location}."

    def _do_request_medical_evac(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        survivor.medical_evac_requested = True
        survivor.discovered = True
        return f"Medical evacuation requested for {survivor.id}: {action.reason or 'specialised extraction required'}."

    def _do_call_rescue_team(self, action: Action) -> str:
        self.rescue_notified = True
        return f"Rescue team notified: {action.reason or self._handoff_summary()}."

    def _do_return_to_base(self, action: Action) -> str:
        path = self._find_safe_path(self.location, "Entrance")
        if path:
            self.location = "Entrance"
            return f"QuakeBot returns to Entrance via {' -> '.join(path)}."
        self.invalid_actions += 1
        return "No safe known path to Entrance."

    def _do_submit_report(self, action: Action) -> str:
        self.report_submitted = True
        self.final_report = action.summary
        summary = (action.summary or "").lower()
        self.hazards_reported_in_final_report = any(
            word in summary for word in ("smoke", "hazard", "structural", "electrical", "aftershock", "basement")
        )
        return "Final multi-survivor rescue report submitted."

    def _add_check(self, survivor: Survivor, check: str) -> None:
        if check not in survivor.checks_completed:
            survivor.checks_completed.append(check)

    def _target_survivor(self, target: str | None) -> Survivor | None:
        if target in self.survivors:
            return self.survivors[target]  # type: ignore[index]
        local = self._local_survivors()
        if target == "survivor" and local:
            return local[0]
        return None

    @staticmethod
    def _survivor_action_types() -> set[str]:
        return {
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
        }

    def _blocked_paths(self) -> dict[str, dict[str, str]]:
        blocked: dict[str, dict[str, str]] = {}
        for room, status in self.rubble_status.items():
            if status == "removed":
                continue
            next_action = {"blocking": "approach_rubble", "approached": "lift_rubble", "lifted": "remove_rubble"}[status]
            blocked[room] = {
                "reason": "rubble",
                "status": status,
                "required_location": "Hallway",
                "next_required_action": next_action,
            }
        return blocked

    def _recommended_next_actions(self) -> list[dict[str, str]]:
        carried = [s for s in self.survivors.values() if s.carried and not s.evacuated]
        if carried:
            return [{"type": "escort_to_exit", "target": carried[0].id}]
        if self.rubble_status["Office"] != "removed":
            if self.location == "Hallway":
                next_action = self._blocked_paths()["Office"]["next_required_action"]
                return [{"type": next_action, "target": "Office"}]
            next_step = self._next_step_toward("Hallway")
            if next_step:
                return [{"type": "move", "target": next_step}]
        local = self._best_local_survivor()
        if local and not local.evacuated:
            if not local.reassured:
                return [{"type": "reassure_survivor", "target": local.id}]
            if "perform_primary_survey" not in local.checks_completed:
                return [{"type": "perform_primary_survey", "target": local.id}]
            if "check_pulse" not in local.checks_completed:
                return [{"type": "check_pulse", "target": local.id}]
            if local.bleeding == "severe" and not local.stabilised:
                return [{"type": "apply_pressure_bandage", "target": local.id}]
            if not local.stabilised:
                return [{"type": "stabilise_survivor", "target": local.id}]
            if local.can_walk:
                return [{"type": "assist_walk", "target": local.id}, {"type": "escort_to_exit", "target": local.id}]
            return [{"type": "carry_survivor", "target": local.id}, {"type": "escort_to_exit", "target": local.id}]
        known = [s for s in self.survivors.values() if s.discovered and not s.evacuated]
        known.sort(key=lambda s: _priority_rank(s.priority), reverse=True)
        if known:
            target = known[0]
            if target.location != self.location:
                next_step = self._next_step_toward(target.location)
                if next_step:
                    return [{"type": "move", "target": next_step}]
                if not target.medical_evac_requested:
                    return [{"type": "request_medical_evac", "target": target.id}]
                if self.location != "Entrance":
                    return [{"type": "return_to_base"}]
        if self.evacuated_count() >= 2 and not self.rescue_notified:
            return [{"type": "call_rescue_team", "location": "Entrance"}]
        if self.evacuated_count() >= 2 and self.rescue_notified and not self.report_submitted:
            return [{"type": "submit_report"}]
        return []

    def _best_local_survivor(self) -> Survivor | None:
        local = self._local_survivors()
        local.sort(key=lambda s: _priority_rank(s.priority), reverse=True)
        return local[0] if local else None

    def _local_survivors(self) -> list[Survivor]:
        return [s for s in self.survivors.values() if s.location == self.location and s.discovered and not s.evacuated]

    def _local_survivor_observations(self) -> list[dict[str, object]]:
        return [
            {
                "id": s.id,
                "reachable": s.reachable,
                "conscious": s.conscious,
                "visible_condition": s.visible_condition(),
                "priority": s.priority,
            }
            for s in self._local_survivors()
        ]

    def _known_survivors(self) -> dict[str, dict[str, object]]:
        return {s.id: s.public_status() for s in self.survivors.values() if s.discovered}

    def _known_floors(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for room in self.memory.visited_rooms:
            if room in self.rooms:
                grouped.setdefault(self.rooms[room].floor_name, []).append(room)
        return {floor: sorted(rooms) for floor, rooms in sorted(grouped.items())}

    def _survivor_cues(self, room: Room) -> list[str]:
        cues = list(room.survivor_cues)
        for survivor in self.survivors.values():
            if survivor.location == self.location and not survivor.evacuated:
                cues.append(f"{survivor.id}: {survivor.visible_condition()}")
        return cues

    def _nearby_survivors(self, *, include_current: bool = False) -> list[Survivor]:
        locations = set(self.rooms[self.location].exits)
        if include_current:
            locations.add(self.location)
        return [s for s in self.survivors.values() if s.location in locations and not s.evacuated]

    def _vertical_exits(self, room: Room) -> list[str]:
        return [exit_name for exit_name in room.exits if self.rooms[exit_name].floor != room.floor]

    def _find_safe_path(self, start: str, goal: str) -> list[str] | None:
        queue: list[tuple[str, list[str]]] = [(start, [start])]
        seen = {start}
        while queue:
            room, path = queue.pop(0)
            if room == goal:
                return path
            for nxt in self.rooms[room].exits:
                if nxt in seen:
                    continue
                conditions = self.rooms[nxt].conditions
                if conditions.get("electrical_hazard") or conditions.get("structural_risk") == "severe":
                    continue
                if nxt == "Office" and self.rubble_status["Office"] != "removed":
                    continue
                seen.add(nxt)
                queue.append((nxt, path + [nxt]))
        return None

    def _next_step_toward(self, goal: str) -> str | None:
        path = self._find_safe_path(self.location, goal)
        return path[1] if path and len(path) > 1 else None

    def _maybe_trigger_aftershock(self) -> None:
        if self.aftershock_triggered or self.step_count < self.aftershock_step:
            return
        self.rooms["Basement"].conditions["structural_risk"] = "severe"
        self.survivors["survivor_basement"].priority = calculate_triage_priority(
            self.survivors["survivor_basement"], self.rooms["Basement"].conditions
        )
        if self.block_basement_aftershock:
            self._remove_exit("Stairwell_B", "Basement")
        self.aftershock_triggered = True
        self._record_event("Aftershock: Basement structural risk is severe; specialised extraction recommended.")
        self.memory.record_hazard("Basement", "severe_structural_risk")

    def _remove_exit(self, a: str, b: str) -> None:
        self.rooms[a].exits = [exit_name for exit_name in self.rooms[a].exits if exit_name != b]
        self.rooms[b].exits = [exit_name for exit_name in self.rooms[b].exits if exit_name != a]

    def _sync_memory_from_current_room(self) -> None:
        room = self.rooms[self.location]
        self.memory.record_room(room.name, room.exits)
        for item in room.items:
            self.memory.record_item(item, room.name)
        for survivor in self.survivors.values():
            if survivor.location == self.location and not survivor.evacuated:
                survivor.discovered = True
                self.memory.record_survivor(survivor.id)
            self.memory.update_survivor_status({survivor.id: survivor.public_status()})
        conditions = room.conditions
        if conditions.get("smoke") not in (None, "none"):
            self.memory.record_hazard(room.name, f"smoke:{conditions['smoke']}")
        if conditions.get("electrical_hazard"):
            self.memory.record_hazard(room.name, "electrical_hazard")
        if conditions.get("structural_risk") in {"medium", "high", "severe"}:
            self.memory.record_hazard(room.name, f"structural_risk:{conditions['structural_risk']}")

    def _record_event(self, event: str) -> None:
        self.event_log.append(event)
        self.memory.record_event(event)

    def _handoff_summary(self) -> str:
        return f"{self.evacuated_count()} survivors evacuated; statuses: " + "; ".join(
            f"{s.id} {s.priority} {s.public_status()['status']}" for s in self.survivors.values() if s.discovered
        )

    @staticmethod
    def _build_world() -> dict[str, Room]:
        normal = {"smoke": "none", "temperature": "normal", "structural_risk": "low", "gas_detected": False, "electrical_hazard": False}
        return {
            "Entrance": Room("Entrance", 0, "Ground", ["Lobby"], dict(normal)),
            "Lobby": Room("Lobby", 0, "Ground", ["Entrance", "Hallway", "Stairwell_G"], dict(normal)),
            "Hallway": Room("Hallway", 0, "Ground", ["Lobby", "Office", "Storage"], {**normal, "structural_risk": "medium"}, objects=["rubble"], sounds=["muffled knocking from Office"], vibration_cues=["weak vibration toward Office"], survivor_cues=["muffled knocking from Office", "weak tapping below from Basement"]),
            "Office": Room("Office", 0, "Ground", ["Hallway"], {**normal, "structural_risk": "medium"}, objects=["survivor"], sounds=["weak voice from rubble"]),
            "Storage": Room("Storage", 0, "Ground", ["Hallway"], dict(normal), items=["first_aid_kit"]),
            "Stairwell_G": Room("Stairwell_G", 0, "Ground", ["Lobby", "Stairwell_1", "Stairwell_B"], {**normal, "smoke": "low"}),
            "Stairwell_1": Room("Stairwell_1", 1, "Floor 1", ["Stairwell_G", "Upper_Hallway"], dict(normal)),
            "Upper_Hallway": Room("Upper_Hallway", 1, "Floor 1", ["Stairwell_1", "Apartment_A", "Apartment_B"], dict(normal), sounds=["frightened calling from Apartment_A"]),
            "Apartment_A": Room("Apartment_A", 1, "Floor 1", ["Upper_Hallway"], dict(normal), sounds=["person calling for help"]),
            "Apartment_B": Room("Apartment_B", 1, "Floor 1", ["Upper_Hallway", "Balcony"], {**normal, "structural_risk": "medium"}),
            "Balcony": Room("Balcony", 1, "Floor 1", ["Apartment_B"], {**normal, "structural_risk": "high"}),
            "Stairwell_B": Room("Stairwell_B", -1, "Basement", ["Stairwell_G", "Basement"], {**normal, "structural_risk": "medium"}),
            "Basement": Room("Basement", -1, "Basement", ["Stairwell_B", "Utility_Room", "Generator_Room"], {**normal, "structural_risk": "high"}, sounds=["intermittent tapping"], vibration_cues=["weak tapping below"]),
            "Utility_Room": Room("Utility_Room", -1, "Basement", ["Basement"], {**normal, "electrical_hazard": True, "structural_risk": "medium"}),
            "Generator_Room": Room("Generator_Room", -1, "Basement", ["Basement"], {**normal, "gas_detected": True, "structural_risk": "medium"}),
        }

    @staticmethod
    def _build_survivors() -> dict[str, Survivor]:
        survivors = {
            "survivor_office": Survivor("survivor_office", "Elena", "Office", True, False, True, True, "fast", "rapid", "minor", 6, False, ["leg pinned", "left arm cut"], "high"),
            "survivor_apartment_a": Survivor("survivor_apartment_a", "Jonas", "Apartment_A", False, True, True, True, "normal", "normal", "none", 4, True, ["sprained ankle", "anxiety"], "medium"),
            "survivor_basement": Survivor("survivor_basement", None, "Basement", True, False, True, True, "laboured", "weak", "severe", 8, False, ["possible crush injury", "severe bleeding"], "critical"),
        }
        for survivor in survivors.values():
            survivor.priority = calculate_triage_priority(survivor)
        return survivors


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
