"""Multi-floor symbolic disaster-response environment for QuakeBot."""

from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Any

from .actions import Action, VALID_ACTION_TYPES, parse_action
from .core.events import EventEngine, WorldEvent
from .memory import Memory
from .scenario import LoadedLayout, ScenarioConfig, load_layout
from .tasks import ScoreBreakdown, is_success, score_environment


GOAL = "Locate every known or suspected survivor, triage them, evacuate or account for each one, notify rescuers, and report hazards."
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
    directly_seen: bool = False
    directly_assessed: bool = False
    pulse_checked: bool = False
    breathing_checked: bool = False
    bleeding_checked: bool = False
    extraction_requested: bool = False
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
        return self.accounting_status in {"evacuated", "awaiting_specialised_extraction", "inaccessible_confirmed"}

    @property
    def accounting_status(self) -> str:
        if self.evacuated:
            return "evacuated"
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


class QuakeBotEnv:
    """Graph-based multi-floor rescue environment with medical triage."""

    def __init__(
        self,
        *,
        config: ScenarioConfig | None = None,
        aftershock_step: int = 18,
        max_steps: int | None = None,
        starting_battery: int = 240,
        block_basement_aftershock: bool = False,
    ) -> None:
        self.config = config or ScenarioConfig()
        self.layout = load_layout(self.config)
        self.aftershock_step = aftershock_step
        self.max_steps = max_steps if max_steps is not None else self.config.max_steps
        self.block_basement_aftershock = block_basement_aftershock
        self.room_to_floor = dict(self.layout.room_to_floor)
        self.blocked_paths_config = dict(self.layout.blocked_paths)
        self.rooms = self._build_world_from_layout(self.layout)
        self.survivors = self._build_survivors_from_layout(self.layout)
        self.location = "Entrance"
        self.step_count = 0
        self.battery = starting_battery
        self.inventory: list[str] = []
        self.memory = Memory()
        self.event_log: list[str] = ["QuakeBot deployed at Entrance: multi-floor rescue mode active."]
        self.aftershock_triggered = False
        self.rubble_status: dict[str, str] = {
            room: str(blocked.get("status", "blocking"))
            for room, blocked in self.blocked_paths_config.items()
            if blocked.get("type") == "rubble"
        }
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
        self.scanned_rooms: set[str] = set()
        self.rooms_cleared: set[str] = set()
        self.hazard_blocked_access: set[str] = set()
        self.blocked_connections: set[frozenset[str]] = set()
        self.random = random.Random(self.config.seed)
        self.event_engine = EventEngine(seed=self.config.seed)
        self.world_events: list[WorldEvent] = []
        self.events_this_step: list[WorldEvent] = []
        self.random_aftershock_triggered = False
        self.responded_to_random_hazards: set[str] = set()
        self.alternate_route_uses = 0
        self.stabilised_after_worsening: set[str] = set()
        self.critical_deterioration_ignored = 0
        self.blocked_connection_attempts = 0
        self.room_search_status: dict[str, str] = {room_name: "unknown" for room_name in self.rooms}
        self.rooms_confirmed_inaccessible: set[str] = set()
        self.room_inaccessible_reasons: dict[str, str] = {}
        self._search_room(self.location, automatic=True)
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
            "visible_objects": self._visible_objects(room.name),
            "heard_sounds": self._heard_sounds(room.name),
            "vibration_cues": self._vibration_cues(room.name),
            "survivor_cues": self._survivor_cues(room.name),
            "local_survivors": self._local_survivor_observations(),
            "inventory": list(self.inventory),
            "battery": self.battery,
            "blocked_paths": self._blocked_paths(),
            "blocked_connections": self._blocked_connections_observation(),
            "active_hazards": self._active_hazards(),
            "recommended_next_actions": self._recommended_next_actions(),
            "priority_reason": self._priority_reason(),
            "survivor_count_mode": self.config.survivor_count_mode,
            "known_or_estimated_survivor_count": self._known_or_estimated_survivor_count(),
            "room_search_status": dict(self.room_search_status),
            "rooms_to_search": self._rooms_to_search(),
            "rooms_confirmed_inaccessible": sorted(self.rooms_confirmed_inaccessible),
            "rooms_with_survivor_cues": self._rooms_with_survivor_cues(),
            "known_survivors": self._known_survivors(),
            "mission_accounting": self._mission_accounting(),
            "known_floors": self._known_floors(),
            "known_map": self.memory.to_dict(),
            "recent_events": [event.to_dict() for event in self.world_events[-5:]] + self.event_log[-5:],
            "events_this_step": [event.to_dict() for event in self.events_this_step],
            "condition_changes_since_last_step": self._condition_changes_since_last_step(),
        }

    def step(self, payload: str | dict[str, Any] | Action) -> ActionResult:
        if self.done:
            return ActionResult(False, "Episode is already complete.", self.observe(), True, self.score.total, True)
        action = parse_action(payload)
        self.step_count += 1
        self.battery = max(0, self.battery - 2)
        self.events_this_step = []
        if not self.config.random_events_enabled:
            self._maybe_trigger_aftershock()

        valid, reason, unsafe = self._validate(action)
        if not valid:
            if action.type == "move" and "blocked connection" in reason:
                self.blocked_connection_attempts += 1
                if action.target:
                    self.hazard_blocked_access.add(action.target)
            if unsafe:
                self.unsafe_attempts += 1
                if action.type == "move" and action.target:
                    self.hazard_blocked_access.add(action.target)
                    self._mark_room_inaccessible(action.target, reason)
            else:
                self.invalid_actions += 1
            self._record_event(f"Rejected {action.type}: {reason}")
            return ActionResult(False, reason, self.observe(), self.done, self.score.total, True, unsafe)

        message = self._apply(action)
        self._sync_memory_from_current_room()
        self._advance_dynamic_events(action.type)
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
            required_location = self.blocked_paths_config[action.target].get("required_location", "Hallway")
            if self.location != required_location:
                return False, f"{action.target} rubble can only be approached from {required_location}.", False
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
            required_location = self.blocked_paths_config[target].get("required_location", "Hallway")
            if self.location != required_location:
                return False, f"{target} rubble can only be removed from {required_location}.", False
            status = self.rubble_status[target]
            if action.type == "lift_rubble" and status == "blocking":
                return False, "QuakeBot must approach and brace against the rubble first.", False
            if action.type == "lift_rubble" and status == "lifted":
                return False, "Rubble already lifted. Next physical rescue action should be remove_rubble.", False
            if action.type == "remove_rubble" and status != "lifted":
                return False, "Rubble must be lifted before remove_rubble.", False
            if status == "removed":
                return False, f"{target} rubble has already been removed.", False
        if action.type in {"free_survivor", "remove_debris_from_survivor"}:
            survivor = self._target_survivor(action.target)
            if survivor is None:
                return False, f"{action.type} requires a valid survivor id target.", False
            if self.location != survivor.location:
                return False, "QuakeBot must be with that survivor to free them.", False
            if not survivor.trapped:
                return False, "Survivor is already free.", False
            if self.rooms[self.location].conditions.get("structural_risk") == "severe" and not survivor.stabilised:
                return False, "Cannot free survivor in severe structural risk before stabilisation and extraction support.", True
        if action.type == "pick_up":
            item = action.item or action.target
            if not item or item not in self.rooms[self.location].items:
                return False, f"Cannot pick up {item}; it is not visible here.", False
        if action.type in self._survivor_action_types():
            survivor = self._target_survivor(action.target)
            if survivor is None:
                return False, f"{action.type} requires a valid survivor id target.", False
            if not survivor.discovered and action.type not in {
                "scan_for_life_signs",
                "request_medical_evac",
                "request_specialised_extraction",
                "mark_survivor_inaccessible",
            }:
                return False, f"Cannot {action.type} before discovering {survivor.id}.", False
            if action.type not in {"request_medical_evac", "request_specialised_extraction", "mark_survivor_inaccessible"} and self.location != survivor.location:
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
            if action.type in {"request_medical_evac", "request_specialised_extraction"} and not action.reason:
                return False, f"{action.type} requires a detailed reason.", False
            if action.type == "request_specialised_extraction" and not survivor.directly_assessed:
                return False, "request_specialised_extraction requires direct survivor assessment first.", False
            if action.type == "mark_survivor_inaccessible":
                scanned_access = survivor.location in self.scanned_rooms or (
                    survivor.location == "Basement" and "Stairwell_B" in self.scanned_rooms
                )
                if survivor.location not in self.hazard_blocked_access and not scanned_access:
                    return False, "Cannot mark survivor inaccessible before attempting access or scanning the hazard area.", False
                if not survivor.discovered:
                    return False, "Cannot mark an undiscovered survivor inaccessible.", False
        if action.type == "mark_hazard" and not action.hazard_type:
            return False, "mark_hazard requires hazard_type.", False
        if action.type == "mark_room_cleared":
            target_room = action.target or self.location
            if target_room != self.location and target_room not in self.scanned_rooms:
                return False, "A room can only be marked cleared after QuakeBot has entered or scanned it.", False
            if self.room_search_status.get(target_room) not in {"searched", "cleared"}:
                return False, "Cannot mark room cleared before it has been searched.", False
            if self._room_has_unaccounted_survivor_or_cue(target_room):
                return False, "Cannot mark room cleared while survivor cues or unaccounted survivors remain.", False
        if action.type == "mark_room_inaccessible":
            target_room = action.target
            if not target_room or target_room not in self.rooms:
                return False, "mark_room_inaccessible requires a valid room target.", False
            if target_room not in self.hazard_blocked_access:
                return False, "Cannot mark room inaccessible before an access or scan attempt.", False
            if not action.reason:
                return False, "mark_room_inaccessible requires a reason.", False
        if action.type == "call_rescue_team":
            if self.evacuated_count() < 2:
                return False, "Notify rescue team after at least two survivors are evacuated.", False
            if self._mission_accounting()["unaccounted"]:
                return False, "Cannot notify final rescue handoff while survivors remain unaccounted.", False
            if self.config.survivor_count_mode == "approximate" and self._uncleared_reachable_rooms():
                return False, "Cannot notify final rescue handoff while reachable rooms remain uncleared.", False
        if action.type == "submit_report":
            if self.location != "Entrance":
                return False, "Cannot submit report unless QuakeBot is at Entrance.", False
            if self.evacuated_count() < 2 or not self.rescue_notified:
                return False, "Cannot submit report before minimum evacuation and rescue notification.", False
            accounting = self._mission_accounting()
            if not accounting["mission_can_finish"]:
                self.invalid_actions += 9
                return False, str(accounting["reason_not_finished"]), False
            if not action.summary:
                return False, "submit_report requires a summary.", False
        return True, "", False

    def _validate_move(self, target: str) -> tuple[bool, str, bool]:
        room = self.rooms[self.location]
        if target not in room.exits:
            return False, f"Cannot move to {target}; it is not adjacent to {self.location}.", False
        if self._connection_key(self.location, target) in self.blocked_connections:
            return False, f"Cannot move to {target}; blocked connection {self.location} <-> {target}.", False
        if target == "Office" and self.rubble_status.get("Office") != "removed":
            return False, "Cannot enter Office until rubble blocking the doorway is removed.", False
        conditions = self.rooms[target].conditions
        if conditions.get("electrical_hazard"):
            return False, f"Unsafe move rejected: {target} has an electrical hazard.", True
        if conditions.get("structural_risk") == "severe":
            if target == "Basement" and self.location == "Stairwell_B" and "Stairwell_B" in self.scanned_rooms:
                return True, "", False
            if self.config.random_events_enabled:
                return False, f"Unsafe move rejected: {target} has severe structural risk.", True
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
        self._search_room(self.location, automatic=True)
        return f"QuakeBot moves to {self.location}."

    def _do_inspect(self, action: Action) -> str:
        return f"QuakeBot inspects {action.target or self.location}."

    def _do_search_room(self, action: Action) -> str:
        self._search_room(self.location)
        found = self._nearby_survivors(include_current=True)
        for survivor in found:
            self._confirm_survivor(survivor, directly_seen=survivor.location == self.location)
        if found:
            return "QuakeBot searches the room and accounts for signs of: " + ", ".join(f"{s.id} at {s.location}" for s in found) + "."
        return f"QuakeBot searches {self.location}; no survivor is found here."

    def _do_search_floor(self, action: Action) -> str:
        room = self.rooms[self.location]
        floor_rooms = [name for name, candidate in self.rooms.items() if candidate.floor == room.floor]
        remaining = [name for name in floor_rooms if self.room_search_status.get(name) not in {"cleared", "inaccessible_confirmed"}]
        return f"{room.floor_name} rooms still needing search: {', '.join(remaining) or 'none'}."

    def _do_listen_for_survivor(self, action: Action) -> str:
        room = self.rooms[self.location]
        if not room.sounds:
            return "No clear survivor sound detected here."
        for survivor in self._nearby_survivors():
            self._confirm_survivor(survivor, directly_seen=False)
        clue = "; ".join(room.sounds)
        self.memory.record_survivor_clue(clue)
        return f"Audio sensors isolate survivor cues: {clue}."

    def _do_sense_vibrations(self, action: Action) -> str:
        room = self.rooms[self.location]
        if not room.vibration_cues:
            return "No survivor-like vibration detected here."
        for survivor in self._nearby_survivors():
            self._confirm_survivor(survivor, directly_seen=False)
        clue = "; ".join(room.vibration_cues)
        self.memory.record_survivor_clue(clue)
        return f"QuakeBot feels structural vibration cues: {clue}."

    def _do_scan_for_life_signs(self, action: Action) -> str:
        self.scanned_rooms.add(self.location)
        self._mark_searched(self.location)
        found = self._nearby_survivors(include_current=True)
        for survivor in found:
            self._confirm_survivor(survivor, directly_seen=survivor.location == self.location)
            self._discover_room(survivor.location)
        if found:
            return "Life-sign scan detects: " + ", ".join(f"{s.id} at {s.location}" for s in found) + "."
        self._auto_clear_room_if_empty(self.location)
        return "No life signs detected nearby."

    def _do_approach_rubble(self, action: Action) -> str:
        target = action.target or "Office"
        self.rubble_status[target] = "approached"
        return f"QuakeBot plants its feet, braces its large hands against the {target} rubble, and prepares to lift."

    def _do_lift_rubble(self, action: Action) -> str:
        target = action.target or "Office"
        self.rubble_status[target] = "lifted"
        return f"QuakeBot lifts the {target} rubble with both hands, holding it clear."

    def _do_remove_rubble(self, action: Action) -> str:
        target = action.target or "Office"
        self.rubble_status[target] = "removed"
        if target in self.blocked_paths_config:
            req_loc = self.blocked_paths_config[target].get("required_location")
            if req_loc:
                conn_key = self._connection_key(req_loc, target)
                if conn_key in self.blocked_connections:
                    self.blocked_connections.remove(conn_key)

        if target == "Office":
            survivor = self.survivors["survivor_office"]
            survivor.trapped = False
            survivor.reachable = True
            self._confirm_survivor(survivor, directly_seen=False)
            self.rooms["Hallway"].objects = [obj for obj in self.rooms["Hallway"].objects if obj != "rubble"]
            return "QuakeBot removes the rubble by hand. survivor_office is freed and reachable."
            
        return f"QuakeBot removes the debris blocking {target}."

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
        survivor.bleeding_controlled = True
        survivor.stability = min(100, survivor.stability + 8)
        self._mark_stabilised_after_worsening(survivor)
        self._add_check(survivor, "apply_pressure_bandage")
        return f"QuakeBot applies a pressure bandage to {survivor.id}."

    def _do_position_for_breathing(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        survivor.stabilised = True
        survivor.breathing_supported = True
        survivor.stability = min(100, survivor.stability + 6)
        self._mark_stabilised_after_worsening(survivor)
        self._add_check(survivor, "position_for_breathing")
        return f"QuakeBot positions {survivor.id} to support breathing."

    def _do_stabilise_survivor(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        survivor.stabilised = True
        if survivor.breathing_status == "laboured":
            survivor.breathing_supported = True
        survivor.stability = min(100, survivor.stability + 5)
        self._mark_stabilised_after_worsening(survivor)
        self._add_check(survivor, "stabilise_survivor")
        return f"QuakeBot stabilises {survivor.id} before movement."

    def _do_free_survivor(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        survivor.trapped = False
        survivor.reachable = True
        return f"QuakeBot carefully removes debris pinning {survivor.id}; the survivor is free."

    _do_remove_debris_from_survivor = _do_free_survivor

    def _do_monitor_vitals(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        self._add_check(survivor, "monitor_vitals")
        survivor.last_checked_step = self.step_count
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
        old_location = self.location
        self.location = "Entrance"
        survivor.location = "Entrance"
        survivor.carried = False
        survivor.evacuated = True
        if survivor.id not in self.evacuation_order:
            self.evacuation_order.append(survivor.id)
            
        self._mark_searched(old_location)
        self._auto_clear_room_if_empty(old_location)
        
        return f"QuakeBot escorts {survivor.id} to Entrance via {' -> '.join(path)}."

    def _do_mark_hazard(self, action: Action) -> str:
        hazard = action.hazard_type or "unknown"
        self.hazard_marks.setdefault(self.location, []).append(hazard)
        for event in self.world_events:
            if event.location == self.location and event.id not in self.responded_to_random_hazards:
                self.responded_to_random_hazards.add(event.id)
        self.memory.record_hazard(self.location, hazard)
        return f"QuakeBot marks {hazard} at {self.location}."

    def _do_request_medical_evac(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        survivor.medical_evac_requested = True
        survivor.extraction_requested = True
        self._confirm_survivor(survivor, directly_seen=survivor.location == self.location)
        return f"Medical evacuation requested for {survivor.id}: {action.reason or 'specialised extraction required'}."

    def _do_request_specialised_extraction(self, action: Action) -> str:
        return self._do_request_medical_evac(action)

    def _do_mark_survivor_inaccessible(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        survivor.inaccessible_confirmed = True
        self._confirm_survivor(survivor, directly_seen=survivor.location == self.location)
        return f"{survivor.id} marked inaccessible after direct hazard investigation near {survivor.location}."

    def _do_mark_room_cleared(self, action: Action) -> str:
        room = action.target or self.location
        self.rooms_cleared.add(room)
        self.room_search_status[room] = "cleared"
        return f"QuakeBot marks {room} cleared after search."

    def _do_mark_room_inaccessible(self, action: Action) -> str:
        room = action.target or ""
        self._mark_room_inaccessible(room, action.reason or "access blocked")
        return f"QuakeBot marks {room} inaccessible: {action.reason or 'access blocked'}."

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
        if check in {"check_airway", "check_breathing", "check_pulse", "check_bleeding", "check_responsiveness", "perform_primary_survey"}:
            survivor.directly_assessed = True
            survivor.last_checked_step = self.step_count
            self._confirm_survivor(survivor, directly_seen=True)
        if check in {"check_pulse", "perform_primary_survey"}:
            survivor.pulse_checked = True
        if check in {"check_breathing", "perform_primary_survey"}:
            survivor.breathing_checked = True
        if check in {"check_airway", "perform_primary_survey"}:
            survivor.airway_clear = survivor.breathing_status != "not_breathing"
        if check in {"check_bleeding", "perform_primary_survey"}:
            survivor.bleeding_checked = True

    def _confirm_survivor(self, survivor: Survivor, *, directly_seen: bool) -> None:
        survivor.discovered = True
        survivor.last_confirmed_location = survivor.location
        survivor.last_confirmed_step = self.step_count
        if directly_seen:
            survivor.directly_seen = True
        self.memory.record_survivor(survivor.id)

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
            "request_specialised_extraction",
            "mark_survivor_inaccessible",
            "free_survivor",
            "remove_debris_from_survivor",
            "carry_survivor",
            "assist_walk",
            "escort_to_exit",
        }

    def _blocked_paths(self) -> dict[str, dict[str, str]]:
        blocked: dict[str, dict[str, str]] = {}
        for room, status in self.rubble_status.items():
            if status == "removed":
                continue
            config = self.blocked_paths_config.get(room, {})
            next_action = {"blocking": "approach_rubble", "approached": "lift_rubble", "lifted": "remove_rubble"}[status]
            blocked[room] = {
                "reason": str(config.get("type", "rubble")),
                "status": status,
                "required_location": str(config.get("required_location", "Hallway")),
                "next_required_action": str(config.get("next_required_action", next_action)) if status == "blocking" else next_action,
            }
        return blocked

    def _blocked_connections_observation(self) -> list[list[str]]:
        return [sorted(connection) for connection in sorted(self.blocked_connections, key=lambda c: sorted(c))]

    def _active_hazards(self) -> dict[str, dict[str, Any]]:
        hazards: dict[str, dict[str, Any]] = {}
        for room_name, room in self.rooms.items():
            active = {
                key: value
                for key, value in room.conditions.items()
                if value not in (False, "none", "normal", "low")
            }
            if active:
                hazards[room_name] = active
        return hazards

    def _condition_changes_since_last_step(self) -> list[str]:
        changes: list[str] = []
        for survivor in self.survivors.values():
            for item in survivor.condition_history[-3:]:
                if f"step {self.step_count}" in item:
                    changes.append(item)
        return changes

    def _recommended_next_actions(self) -> list[dict[str, str]]:
        carried = [s for s in self.survivors.values() if s.carried and not s.evacuated]
        if carried:
            if self._find_safe_path(self.location, "Entrance"):
                return [{"type": "escort_to_exit", "target": carried[0].id}]
            return [{"type": "request_specialised_extraction", "target": carried[0].id}]
        local = self._best_local_survivor()
        if local and not local.evacuated:
            if local.accounting_status == "awaiting_specialised_extraction":
                if self.location != "Entrance":
                    next_step = self.next_step_towards(self.location, "Entrance")
                    if next_step:
                        return [{"type": "move", "target": next_step}]
                    return [{"type": "return_to_base"}]
                if self._mission_accounting()["mission_can_finish"] and not self.rescue_notified:
                    return [{"type": "call_rescue_team", "location": "Entrance"}]
                return []
            if not local.reassured:
                return [{"type": "reassure_survivor", "target": local.id, "message": "I'm here with you. You're not alone."}]
            if "perform_primary_survey" not in local.checks_completed:
                return [{"type": "perform_primary_survey", "target": local.id}]
            if "check_pulse" not in local.checks_completed:
                return [{"type": "check_pulse", "target": local.id}]
            if local.bleeding == "severe" and not local.bleeding_controlled:
                return [{"type": "apply_pressure_bandage", "target": local.id}]
            if local.breathing_status == "laboured" and not local.breathing_supported:
                return [{"type": "position_for_breathing", "target": local.id}]
            if not local.stabilised:
                return [{"type": "stabilise_survivor", "target": local.id}]
            if local.trapped:
                if self.rooms[self.location].conditions.get("structural_risk") == "severe":
                    return [{"type": "request_specialised_extraction", "target": local.id}]
                return [{"type": "free_survivor", "target": local.id}]
            if local.can_walk:
                return [{"type": "assist_walk", "target": local.id}, {"type": "escort_to_exit", "target": local.id}]
            return [{"type": "carry_survivor", "target": local.id}, {"type": "escort_to_exit", "target": local.id}]
        if not self.survivors["survivor_office"].accounted_for() and self.rubble_status.get("Office") != "removed":
            if self.location == "Hallway":
                next_action = self._blocked_paths()["Office"]["next_required_action"]
                return [{"type": next_action, "target": "Office"}]
            next_step = self.next_step_towards(self.location, "Hallway")
            if next_step:
                return [{"type": "move", "target": next_step}]
        known = [s for s in self.survivors.values() if s.discovered and not s.accounted_for()]
        known.sort(key=lambda s: _priority_rank(s.priority), reverse=True)
        if known:
            target = known[0]
            if target.location != self.location:
                next_step = self.next_step_towards(self.location, target.location)
                if next_step:
                    return [{"type": "move", "target": next_step}]
                if target.location == "Basement" and self.location == "Stairwell_B":
                    if self.location not in self.scanned_rooms:
                        return [{"type": "scan_for_life_signs"}]
                    if "Basement" in self.rooms["Stairwell_B"].exits:
                        return [{"type": "move", "target": "Basement"}]
                    if target.location in self.hazard_blocked_access:
                        return [{"type": "request_specialised_extraction", "target": target.id}, {"type": "mark_survivor_inaccessible", "target": target.id}]
                if not target.extraction_requested:
                    return [{"type": "request_specialised_extraction", "target": target.id}]
                if self.location != "Entrance":
                    return [{"type": "return_to_base"}]
        
        unaccounted = [s for s in self.survivors.values() if not s.accounted_for()]
        if unaccounted:
            target = sorted(unaccounted, key=lambda s: _priority_rank(s.priority), reverse=True)[0]
            if target.location != self.location:
                next_step = self.next_step_towards(self.location, target.location)
                if next_step:
                    return [{"type": "move", "target": next_step}]
                if target.location == "Basement" and self.location == "Stairwell_B":
                    if self.location not in self.scanned_rooms:
                        return [{"type": "scan_for_life_signs"}]
                    if "Basement" in self.rooms["Stairwell_B"].exits:
                        return [{"type": "move", "target": "Basement"}]
            if not target.discovered:
                next_step = self.next_step_towards(self.location, "Stairwell_B")
                if next_step:
                    return [{"type": "move", "target": next_step}]
                return [{"type": "scan_for_life_signs"}]
        if self.config.survivor_count_mode == "approximate":
            search_action = self._recommended_search_action()
            if search_action:
                return [search_action]
        if self._mission_accounting()["mission_can_finish"] and not self.rescue_notified:
            return [{"type": "call_rescue_team", "location": "Entrance"}]
        if self._mission_accounting()["mission_can_finish"] and self.rescue_notified and not self.report_submitted:
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
                "stability": s.stability,
                "bleeding_controlled": s.bleeding_controlled,
                "breathing_supported": s.breathing_supported,
            }
            for s in self._local_survivors()
        ]

    def _known_survivors(self) -> dict[str, dict[str, object]]:
        return {s.id: s.public_status() for s in self.survivors.values() if s.discovered}

    def _mission_accounting(self) -> dict[str, object]:
        survivors = list(self.survivors.values())
        unaccounted = [s.id for s in survivors if not s.accounted_for()]
        uncleared = self._uncleared_reachable_rooms() if self.config.survivor_count_mode == "approximate" else []
        reason = ""
        if unaccounted:
            reason = f"{', '.join(unaccounted)} has not been evacuated, directly assessed with extraction requested, or confirmed inaccessible"
        elif uncleared:
            reason = "Survivor count is approximate; reachable rooms remain uncleared: " + ", ".join(uncleared)
        return {
            "survivor_count_mode": self.config.survivor_count_mode,
            "estimated_survivors": self.config.survivor_count,
            "survivor_count_min": self.config.survivor_count_min,
            "survivor_count_max": self.config.survivor_count_max,
            "confirmed_survivors": sum(1 for s in survivors if s.discovered),
            "total_known_or_suspected_survivors": len(survivors),
            "evacuated": [s.id for s in survivors if s.evacuated],
            "directly_assessed": [s.id for s in survivors if s.directly_assessed],
            "awaiting_specialised_extraction": [s.id for s in survivors if s.accounting_status == "awaiting_specialised_extraction"],
            "extraction_requested": [s.id for s in survivors if s.extraction_requested],
            "inaccessible_confirmed": [s.id for s in survivors if s.inaccessible_confirmed],
            "accounting_statuses": {s.id: s.accounting_status for s in survivors},
            "unaccounted": unaccounted,
            "unaccounted_survivors": unaccounted,
            "uncleared_reachable_rooms": uncleared,
            "mission_can_finish": not unaccounted and not uncleared and self.location == "Entrance" and self.evacuated_count() >= 2,
            "reason_not_finished": reason,
        }

    def _priority_reason(self) -> str:
        if not self.survivors["survivor_basement"].accounted_for() and self.evacuated_count() >= 2:
            return "Critical cues detected from Basement; prioritising basement assessment before mission handoff."
        if self.location == "Hallway" and "weak tapping below from Basement" in self.rooms["Hallway"].survivor_cues:
            return "Basement cue indicates a potentially critical trapped survivor; stable callers should still be rescued once current survivor is safe."
        return ""

    def _known_floors(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for room in self.memory.visited_rooms:
            if room in self.rooms:
                grouped.setdefault(self.rooms[room].floor_name, []).append(room)
        return {floor: sorted(rooms) for floor, rooms in sorted(grouped.items())}

    def _known_or_estimated_survivor_count(self) -> int | dict[str, int | None]:
        if self.config.survivor_count_mode == "exact":
            return self.config.survivor_count or len(self.survivors)
        return {
            "estimate": self.config.survivor_count,
            "min": self.config.survivor_count_min,
            "max": self.config.survivor_count_max,
        }

    def _discover_room(self, room_name: str) -> None:
        if self.room_search_status.get(room_name) == "unknown":
            self.room_search_status[room_name] = "discovered"
        for exit_name in self.rooms[room_name].exits:
            if self.room_search_status.get(exit_name) == "unknown":
                self.room_search_status[exit_name] = "discovered"

    def _mark_searched(self, room_name: str) -> None:
        if self.room_search_status.get(room_name) != "inaccessible_confirmed":
            self.room_search_status[room_name] = "searched"
        self.scanned_rooms.add(room_name)

    def _search_room(self, room_name: str, *, automatic: bool = False) -> None:
        self._discover_room(room_name)
        self._mark_searched(room_name)
        if automatic:
            self._auto_clear_room_if_empty(room_name)

    def _auto_clear_room_if_empty(self, room_name: str) -> None:
        if not self._room_has_unaccounted_survivor_or_cue(room_name):
            self.room_search_status[room_name] = "cleared"
            self.rooms_cleared.add(room_name)

    def _room_has_unaccounted_survivor_or_cue(self, room_name: str) -> bool:
        if any(s.location == room_name and not s.accounted_for() for s in self.survivors.values()):
            return True
        if not (self._survivor_cues(room_name) or self._heard_sounds(room_name) or self._vibration_cues(room_name)):
            return False

        cue_locations = set(self.rooms[room_name].exits) | {room_name}
        if room_name in {"Hallway", "Stairwell_B", "Stairwell_G"}:
            cue_locations.add("Basement")
        return any(s.location in cue_locations and not s.accounted_for() for s in self.survivors.values())

    def _mark_room_inaccessible(self, room_name: str, reason: str) -> None:
        if room_name in self.rooms:
            self.room_search_status[room_name] = "inaccessible_confirmed"
            self.rooms_confirmed_inaccessible.add(room_name)
            self.room_inaccessible_reasons[room_name] = reason

    def _reachable_rooms_from_entrance(self) -> set[str]:
        queue = ["Entrance"]
        seen = {"Entrance"}
        while queue:
            room_name = queue.pop(0)
            for nxt in self.rooms[room_name].exits:
                if nxt in seen:
                    continue
                if self._connection_key(room_name, nxt) in self.blocked_connections:
                    continue
                conditions = self.rooms[nxt].conditions
                if conditions.get("electrical_hazard") or conditions.get("structural_risk") == "severe":
                    continue
                if nxt == "Office" and self.rubble_status.get("Office") != "removed":
                    continue
                seen.add(nxt)
                queue.append(nxt)
        return seen

    def _uncleared_reachable_rooms(self) -> list[str]:
        reachable = self._reachable_rooms_from_entrance()
        return sorted(
            room
            for room in reachable
            if self.room_search_status.get(room) not in {"cleared", "inaccessible_confirmed"}
        )

    def _rooms_to_search(self) -> list[str]:
        if self.config.survivor_count_mode == "approximate":
            return self._uncleared_reachable_rooms()
        return [room for room in self._rooms_with_survivor_cues() if self._room_has_unaccounted_survivor_or_cue(room)]

    def _rooms_with_survivor_cues(self) -> list[str]:
        return sorted(
            room_name
            for room_name in self.rooms
            if self._survivor_cues(room_name) or self._heard_sounds(room_name) or self._vibration_cues(room_name)
        )

    def _recommended_search_action(self) -> dict[str, str] | None:
        uncleared = self._uncleared_reachable_rooms()
        if not uncleared:
            if self.location != "Entrance":
                next_step = self.next_step_towards(self.location, "Entrance")
                return {"type": "move", "target": next_step} if next_step else {"type": "return_to_base"}
            return None
        if self.location in uncleared:
            status = self.room_search_status.get(self.location)
            if status in {"unknown", "discovered"}:
                return {"type": "search_room"}
            if status == "searched":
                return {"type": "mark_room_cleared", "target": self.location}
        target = self._nearest_room(uncleared)
        if target:
            next_step = self.next_step_towards(self.location, target)
            if next_step:
                return {"type": "move", "target": next_step}
        return None

    def _nearest_room(self, room_names: list[str]) -> str | None:
        best: tuple[int, str] | None = None
        for room_name in room_names:
            path = self._find_safe_path(self.location, room_name)
            if not path:
                continue
            candidate = (len(path), room_name)
            if best is None or candidate < best:
                best = candidate
        return best[1] if best else None

    def _is_survivor_cue_active(self, survivor_id: str, hearer_room: str) -> bool:
        if survivor_id not in self.survivors:
            return False
        survivor = self.survivors[survivor_id]
        if survivor.evacuated:
            return False
        if survivor.inaccessible_confirmed:
            return False
        if survivor.accounting_status == "awaiting_specialised_extraction":
            if hearer_room not in {survivor.location, "Stairwell_B"}:
                return False
        return True

    def _heard_sounds(self, room_name: str) -> list[str]:
        sounds = list(self.rooms[room_name].sounds)
        if room_name == "Hallway" and self._is_survivor_cue_active("survivor_office", room_name):
            sounds.append("muffled knocking from Office")
        if room_name == "Office" and self._is_survivor_cue_active("survivor_office", room_name):
            sounds.append("weak voice from rubble")
        if room_name == "Upper_Hallway" and self._is_survivor_cue_active("survivor_apartment_a", room_name):
            sounds.append("frightened calling from Apartment_A")
        if room_name == "Apartment_A" and self._is_survivor_cue_active("survivor_apartment_a", room_name):
            sounds.append("person calling for help")
        if room_name == "Basement" and self._is_survivor_cue_active("survivor_basement", room_name):
            sounds.append("intermittent tapping")
        return sounds

    def _vibration_cues(self, room_name: str) -> list[str]:
        cues = list(self.rooms[room_name].vibration_cues)
        if room_name == "Hallway" and self._is_survivor_cue_active("survivor_office", room_name):
            cues.append("weak vibration toward Office")
        if room_name == "Basement" and self._is_survivor_cue_active("survivor_basement", room_name):
            cues.append("weak tapping below")
        return cues

    def _survivor_cues(self, room_name: str) -> list[str]:
        cues = list(self.rooms[room_name].survivor_cues)
        if room_name == "Hallway" and self._is_survivor_cue_active("survivor_office", room_name):
            cues.append("muffled knocking from Office")
        if room_name == "Hallway" and self._is_survivor_cue_active("survivor_basement", room_name):
            cues.append("weak tapping below from Basement")
        
        if room_name == self.location:
            for survivor in self.survivors.values():
                if survivor.location == self.location and not survivor.evacuated:
                    cues.append(f"{survivor.id}: {survivor.visible_condition()}")
        return cues

    def _visible_objects(self, room_name: str) -> list[str]:
        room = self.rooms[room_name]
        objs = list(room.objects + room.items)
        if room_name == self.location:
            has_local_survivor = any(not s.evacuated and s.location == room_name for s in self.survivors.values())
            if has_local_survivor:
                objs.append("survivor")
        return objs

    def _nearby_survivors(self, *, include_current: bool = False) -> list[Survivor]:
        locations = set(self.rooms[self.location].exits)
        if self.location == "Stairwell_B":
            locations.add("Basement")
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
                if self._connection_key(room, nxt) in self.blocked_connections:
                    continue
                conditions = self.rooms[nxt].conditions
                if conditions.get("electrical_hazard") or conditions.get("structural_risk") == "severe":
                    continue
                if nxt == "Office" and self.rubble_status.get("Office") != "removed":
                    continue
                seen.add(nxt)
                queue.append((nxt, path + [nxt]))
        return None

    def next_step_towards(self, current_room: str, target_room: str) -> str | None:
        path = self._find_safe_path(current_room, target_room)
        if path and self.blocked_connections:
            self.alternate_route_uses += 1
        return path[1] if path and len(path) > 1 else None

    def _next_step_toward(self, goal: str) -> str | None:
        return self.next_step_towards(self.location, goal)

    def _advance_dynamic_events(self, action_type: str) -> None:
        if not self.config.random_events_enabled:
            return
        events = self.event_engine.condition_worsening_events(self)
        world_event = self.event_engine.maybe_world_event(self, action_type)
        if world_event is not None:
            events.append(world_event)
        for event in events:
            self._apply_world_event(event)

    def _apply_world_event(self, event: WorldEvent) -> None:
        self.world_events.append(event)
        self.events_this_step.append(event)
        effects = event.effects
        if event.type == "aftershock":
            self.random_aftershock_triggered = True
            self.aftershock_triggered = True
            self.rooms[event.location].conditions["structural_risk"] = str(effects.get("structural_risk", "severe"))
            self.memory.record_hazard(event.location, "random_aftershock")
        elif event.type in {"debris_fall", "exit_blocked"}:
            if "structural_risk" in effects:
                self._raise_structural_risk(event.location, str(effects["structural_risk"]))
            if "blocked_connection" in effects:
                a, b = effects["blocked_connection"]
                self.blocked_connections.add(self._connection_key(str(a), str(b)))
                target_room = str(b) if event.location == str(a) else str(a)
                if target_room not in self.rubble_status:
                    self.rubble_status[target_room] = "blocking"
                    self.blocked_paths_config[target_room] = {
                        "type": "debris",
                        "required_location": event.location,
                        "next_required_action": "approach_rubble",
                    }
            if event.affected_survivor_id:
                survivor = self.survivors[event.affected_survivor_id]
                survivor.stability = max(0, survivor.stability + int(effects.get("stability_delta", -10)))
                survivor.pain_level = min(10, survivor.pain_level + int(effects.get("pain_delta", 1)))
                survivor.can_walk = False
                if survivor.bleeding == "none":
                    survivor.bleeding = "minor"
                survivor.priority = calculate_triage_priority(survivor, self.rooms[survivor.location].conditions)
                survivor.condition_history.append(f"step {event.step}: {event.message}")
        elif event.type == "smoke_spread":
            self.rooms[event.location].conditions["smoke"] = str(effects.get("smoke", "low"))
            self.memory.record_hazard(event.location, f"smoke:{effects.get('smoke', 'low')}")
        elif event.type == "survivor_condition_worsens" and event.affected_survivor_id:
            survivor = self.survivors[event.affected_survivor_id]
            survivor.stability = max(0, survivor.stability + int(effects.get("stability_delta", -5)))
            if survivor.stability < 45 and survivor.pulse_status == "rapid":
                survivor.pulse_status = "weak"
            survivor.priority = calculate_triage_priority(survivor, self.rooms[survivor.location].conditions)
            survivor.condition_history.append(f"step {event.step}: {event.message}")
            if survivor.priority == "critical" and not survivor.stabilised:
                self.critical_deterioration_ignored += 1
        self._record_event(event.message)

    def _raise_structural_risk(self, room_name: str, new_risk: str) -> None:
        ranks = {"low": 0, "medium": 1, "high": 2, "severe": 3}
        current = str(self.rooms[room_name].conditions.get("structural_risk", "low"))
        if ranks.get(new_risk, 0) > ranks.get(current, 0):
            self.rooms[room_name].conditions["structural_risk"] = new_risk
            self.memory.record_hazard(room_name, f"structural_risk:{new_risk}")

    @staticmethod
    def _connection_key(a: str, b: str) -> frozenset[str]:
        return frozenset((a, b))

    def _mark_stabilised_after_worsening(self, survivor: Survivor) -> None:
        if survivor.condition_history:
            self.stabilised_after_worsening.add(survivor.id)

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
                self._confirm_survivor(survivor, directly_seen=True)
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
    def _base_conditions() -> dict[str, Any]:
        return {"smoke": "none", "temperature": "normal", "structural_risk": "low", "gas_detected": False, "electrical_hazard": False}

    @classmethod
    def _build_world_from_layout(cls, layout: LoadedLayout) -> dict[str, Room]:
        rooms: dict[str, Room] = {}
        normal = cls._base_conditions()
        for floor_id, floor in layout.floors.items():
            floor_level = int(floor.get("level", 0))
            floor_name = str(floor.get("name", floor_id))
            for room_name, room_data in floor["rooms"].items():
                conditions = dict(normal)
                conditions.update(room_data.get("hazards", {}))
                rooms[room_name] = Room(
                    name=room_name,
                    floor=floor_level,
                    floor_name=floor_name,
                    exits=list(room_data.get("connects_to", [])),
                    conditions=conditions,
                    objects=list(room_data.get("objects", [])),
                    sounds=list(room_data.get("sounds", [])),
                    vibration_cues=list(room_data.get("vibration_cues", [])),
                    survivor_cues=list(room_data.get("survivor_cues", [])),
                    items=list(room_data.get("items", [])),
                )
        return rooms

    @staticmethod
    def _build_survivors_from_layout(layout: LoadedLayout) -> dict[str, Survivor]:
        survivors: dict[str, Survivor] = {}
        for survivor_id, data in layout.survivors.items():
            survivor = Survivor(
                id=survivor_id,
                name=data.get("name"),
                location=str(data["location"]),
                trapped=bool(data.get("trapped", False)),
                reachable=bool(data.get("reachable", not data.get("trapped", False))),
                conscious=bool(data.get("conscious", True)),
                responsive=bool(data.get("responsive", True)),
                breathing_status=str(data.get("breathing_status", "normal")),
                pulse_status=str(data.get("pulse_status", "normal")),
                bleeding=str(data.get("bleeding", "none")),
                pain_level=int(data.get("pain_level", 0)),
                can_walk=bool(data.get("can_walk", True)),
                suspected_injuries=list(data.get("suspected_injuries", [])),
                priority=str(data.get("priority", "medium")),
                stability=int(data.get("stability", 100)),
                bleeding_controlled=bool(data.get("bleeding_controlled", False)),
                breathing_supported=bool(data.get("breathing_supported", False)),
                airway_clear=bool(data.get("airway_clear", True)),
            )
            survivor.priority = calculate_triage_priority(survivor)
            survivors[survivor_id] = survivor
        return survivors

    @staticmethod
    def _build_world() -> dict[str, Room]:
        normal = {"smoke": "none", "temperature": "normal", "structural_risk": "low", "gas_detected": False, "electrical_hazard": False}
        return {
            "Entrance": Room("Entrance", 0, "Ground", ["Lobby"], dict(normal)),
            "Lobby": Room("Lobby", 0, "Ground", ["Entrance", "Hallway", "Stairwell_G"], dict(normal)),
            "Hallway": Room("Hallway", 0, "Ground", ["Lobby", "Office", "Storage"], {**normal, "structural_risk": "medium"}, objects=["rubble"]),
            "Office": Room("Office", 0, "Ground", ["Hallway"], {**normal, "structural_risk": "medium"}),
            "Storage": Room("Storage", 0, "Ground", ["Hallway"], dict(normal), items=["first_aid_kit"]),
            "Stairwell_G": Room("Stairwell_G", 0, "Ground", ["Lobby", "Stairwell_1", "Stairwell_B"], {**normal, "smoke": "low"}),
            "Stairwell_1": Room("Stairwell_1", 1, "Floor 1", ["Stairwell_G", "Upper_Hallway"], dict(normal)),
            "Upper_Hallway": Room("Upper_Hallway", 1, "Floor 1", ["Stairwell_1", "Apartment_A", "Apartment_B"], dict(normal)),
            "Apartment_A": Room("Apartment_A", 1, "Floor 1", ["Upper_Hallway"], dict(normal)),
            "Apartment_B": Room("Apartment_B", 1, "Floor 1", ["Upper_Hallway", "Balcony"], {**normal, "structural_risk": "medium"}),
            "Balcony": Room("Balcony", 1, "Floor 1", ["Apartment_B"], {**normal, "structural_risk": "high"}),
            "Stairwell_B": Room("Stairwell_B", -1, "Basement", ["Stairwell_G", "Basement"], {**normal, "structural_risk": "medium"}),
            "Basement": Room("Basement", -1, "Basement", ["Stairwell_B", "Utility_Room", "Generator_Room"], {**normal, "structural_risk": "high"}),
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
