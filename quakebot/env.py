"""Multi-floor symbolic disaster-response environment for QuakeBot."""

from __future__ import annotations

import random
from typing import Any

from .actions import Action, parse_action
from .action_handlers import ActionHandlersMixin
from .accounting import AccountingMixin
from .core.events import EventEngine, WorldEvent
from .memory import Memory
from .models import Room, Survivor, ActionResult, calculate_triage_priority
from .navigation import NavigationMixin
from .observations import ObservationMixin
from .scenario import LoadedLayout, ScenarioConfig, load_layout
from .tasks import ScoreBreakdown, is_success, score_environment
from .validation import ValidationMixin


GOAL = "Locate every known or suspected survivor, triage them, evacuate or account for each one, notify rescuers, and report hazards."


class QuakeBotEnv(
    ValidationMixin,
    ActionHandlersMixin,
    ObservationMixin,
    AccountingMixin,
    NavigationMixin,
):
    """Graph-based multi-floor rescue environment with medical triage."""
    def __init__(
        self,
        *,
        config: ScenarioConfig | None = None,
        layout: LoadedLayout | None = None,
        aftershock_step: int = 18,
        max_steps: int | None = None,
        starting_battery: int = 240,
        aftershock_blocks_exits: bool = False,
    ) -> None:
        self.config = config or ScenarioConfig()
        self.layout = layout if layout is not None else load_layout(self.config)
        self.aftershock_step = aftershock_step
        self.max_steps = max_steps if max_steps is not None else self.config.max_steps
        self.aftershock_blocks_exits = aftershock_blocks_exits
        self.room_to_floor = dict(self.layout.room_to_floor)
        self.blocked_paths_config = dict(self.layout.blocked_paths)
        self.rooms = self._build_world_from_layout(self.layout)
        self.survivors = self._build_survivors_from_layout(self.layout, self.config)
        self.location = "Entrance" if "Entrance" in self.rooms else next(iter(self.rooms))
        self.step_count = 0
        self.battery = starting_battery
        self.inventory: list[str] = []
        self.memory = Memory()
        self.event_log: list[str] = ["QuakeBot deployed at Entrance: multi-floor rescue mode active."]
        self.aftershock_triggered = False
        self.rubble_status: dict[str, str] = {
            room: str(blocked.get("status", "blocking"))
            for room, blocked in self.blocked_paths_config.items()
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
        self.last_rejected_actions: list[Action] = []
        self._search_room(self.location, automatic=True)
        self._sync_memory_from_current_room()

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
            self.last_rejected_actions.append(action)
            self._record_event(f"Rejected {action.type}: {reason}")
            return ActionResult(False, reason, self.observe(), self.done, self.score.total, True, unsafe)

        self.last_rejected_actions.clear()
        message = self._apply(action)
        self._sync_memory_from_current_room()
        
        for survivor in self.survivors.values():
            if survivor.extraction_eta_steps is not None and survivor.extraction_eta_steps > 0:
                survivor.extraction_eta_steps -= 1
                if survivor.extraction_eta_steps == 0:
                    survivor.extraction_status = "arrived"
            self._update_safe_to_leave(survivor)

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

    def completed_rescue_count(self) -> int:
        return sum(1 for survivor in self.survivors.values() if survivor.evacuated or survivor.handoff_complete)

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
                        "next_required_action": "clear_obstruction",
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

    def _highest_structural_risk_room(self) -> str | None:
        high_risk = [name for name, room in self.rooms.items() if room.conditions.get("structural_risk") == "severe"]
        if high_risk:
            return high_risk[0]
        high_risk = [name for name, room in self.rooms.items() if room.conditions.get("structural_risk") == "high"]
        if high_risk:
            return high_risk[0]
        return None

    def _active_survivor_room(self) -> str | None:
        active = [s.location for s in self.survivors.values() if not s.accounted_for() and not s.evacuated]
        if active:
            return active[0]
        return None

    def _basement_like_room(self) -> str | None:
        return next((r for r in self.rooms if "basement" in r.lower()), None)

    def _maybe_trigger_aftershock(self) -> None:
        if self.aftershock_triggered:
            return

        if self.step_count < self.aftershock_step:
            return

        self.aftershock_triggered = True

        target_room = (
            self.config.aftershock_target_room
            or self._highest_structural_risk_room()
            or self._active_survivor_room()
            or self._basement_like_room()
        )
        if not target_room:
            return

        room = self.rooms[target_room]
        room.conditions["structural_risk"] = "severe"

        for survivor in self.survivors.values():
            if survivor.location == target_room and not survivor.accounted_for():
                survivor.trapped = True
                survivor.priority = calculate_triage_priority(survivor, room.conditions)

        if self.aftershock_blocks_exits:
            for adjacent_room in room.exits:
                self.blocked_connections.add(self._connection_key(adjacent_room, target_room))

        self._record_event(
            f"Aftershock: {target_room} structural risk is severe; specialised extraction recommended."
        )
        self.memory.record_hazard(target_room, "severe_structural_risk")

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
                conditions.update(room_data.get("hazards", room_data.get("conditions", {})))
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
        for room_name, room in rooms.items():
            for exit_name in list(room.exits):
                if exit_name not in rooms:
                    continue
                reverse_exits = rooms[exit_name].exits
                if room_name not in reverse_exits:
                    reverse_exits.append(room_name)
        return rooms

    @staticmethod
    def _build_survivors_from_layout(layout: LoadedLayout, config: ScenarioConfig) -> dict[str, Survivor]:
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
                discovered=(config.survivor_location_mode == "known"),
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
