from __future__ import annotations

from .actions import (
    Action,
    SENSE_AREA_MODES,
    TREATMENTS,
    VALID_ACTION_TYPES,
)


class ValidationMixin:
    def _validate(self, action: Action) -> tuple[bool, str, bool]:
        if action.type == "invalid":
            return False, action.reason or "Invalid action payload.", False
        if action.type not in VALID_ACTION_TYPES:
            return False, f"Unsupported action type: {action.type}", False

        if action.type == "move":
            if not action.target:
                return False, "move requires a target.", False
            return self._validate_move(action.target)

        if action.type == "sense_area":
            if action.mode not in SENSE_AREA_MODES:
                return False, "sense_area requires mode 'audio', 'vibration', or 'life_signs'.", False
            target = action.target or self.location
            if target not in self.rooms:
                return False, f"Cannot sense {target}; room does not exist.", False
            if not self._can_scan_from_here(target):
                return False, f"Cannot sense {target}; it is not current or adjacent to {self.location}.", False

        if action.type == "clear_obstruction":
            target = action.target or ""
            if not target or target not in self.rooms:
                return False, "clear_obstruction requires a valid room target.", False
            blocked = self.blocked_paths_config.get(target)
            if blocked is None:
                return False, f"{target} is not blocked by a configured obstruction.", False
            if self.rubble_status.get(target) == "removed":
                return False, f"Obstruction for {target} has already been removed.", False
            required_location = str(blocked.get("required_location", ""))
            if required_location and self.location != required_location:
                return False, f"Cannot clear obstruction for {target} from {self.location}. Move to {required_location} first.", False

        if action.type == "free_survivor":
            survivor = self._target_survivor(action.target)
            if survivor is None:
                return False, "free_survivor requires a valid survivor id target.", False
            if not survivor.discovered:
                return False, f"Cannot free_survivor before discovering {survivor.id}.", False
            if self.location != survivor.location:
                return False, "QuakeBot must be with that survivor to free them.", False
            if not survivor.trapped:
                return False, "Survivor is already free.", False
            if self.rooms[self.location].conditions.get("structural_risk") == "severe" and not survivor.stabilised:
                return False, "Cannot free survivor in severe structural risk before stabilisation and extraction support.", True

        if action.type in self._survivor_action_types():
            survivor = self._target_survivor(action.target)
            if survivor is None:
                return False, f"{action.type} requires a valid survivor id target.", False
            if not survivor.discovered:
                return False, f"Cannot {action.type} before discovering {survivor.id}.", False
            if action.type not in {"request_specialised_extraction", "handoff_to_specialised_team"} and self.location != survivor.location:
                return False, "QuakeBot must be with that survivor to perform this action.", False
            if action.type == "ask_medical_question" and not action.question:
                return False, "ask_medical_question requires a question.", False
            if action.type == "reassure_survivor" and not action.message:
                return False, "reassure_survivor requires a short message.", False
            if action.type == "treat_survivor":
                if action.treatment not in TREATMENTS:
                    return False, "treat_survivor requires treatment control_bleeding, support_breathing, stabilise, monitor, protect, or supply.", False
                if action.treatment == "control_bleeding" and survivor.bleeding == "none":
                    return False, "Bleeding control is not needed; no bleeding detected.", False
            if action.type == "evacuate_survivor":
                if survivor.trapped:
                    return False, "Cannot evacuate trapped survivor; use free_survivor or request_specialised_extraction first.", False
                if "perform_primary_survey" not in survivor.checks_completed:
                    return False, "Cannot evacuate survivor before primary survey.", False
                if survivor.evacuated:
                    return False, "Survivor is already evacuated.", False
                if not self._find_safe_path(self.location, "Entrance"):
                    return False, "No safe path to Entrance is available; request specialised extraction.", False
            if action.type == "request_specialised_extraction":
                if not action.reason:
                    return False, "request_specialised_extraction requires a detailed reason.", False
                if not survivor.directly_assessed and not survivor.discovered:
                    return False, "request_specialised_extraction requires a discovered or directly assessed survivor.", False
            if action.type == "handoff_to_specialised_team":
                if survivor.extraction_status != "arrived":
                    return False, f"Cannot handoff {survivor.id}: extraction team has not arrived yet.", False
                if self.location != survivor.location and not self._is_valid_extraction_access_point(survivor.location):
                    return False, f"Cannot handoff {survivor.id} from {self.location}; move to {survivor.location} first.", False

        if action.type == "mark_hazard" and not action.hazard_type:
            return False, "mark_hazard requires hazard_type.", False

        if action.type == "mark_room_cleared":
            target_room = action.target or self.location
            if target_room not in self.rooms:
                return False, "mark_room_cleared requires a valid room target.", False
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
            if not self._room_was_scanned_or_access_attempted(target_room):
                return False, "Cannot mark room inaccessible before an access or scan attempt.", False
            if not action.reason:
                return False, "mark_room_inaccessible requires a reason.", False

        if action.type == "call_rescue_team":
            required = self._minimum_evacuation_count()
            if self.completed_rescue_count() < required:
                return False, f"Notify rescue team after at least {required} survivor{'s' if required != 1 else ''} are evacuated or safely handed off.", False
            if self._mission_accounting()["unaccounted"]:
                return False, "Cannot notify final rescue handoff while survivors remain unaccounted.", False
            if self.config.survivor_count_mode == "approximate" and self._uncleared_reachable_rooms():
                return False, "Cannot notify final rescue handoff while reachable rooms remain uncleared.", False

        if action.type == "submit_report":
            if self.location != "Entrance":
                return False, "Cannot submit report unless QuakeBot is at Entrance.", False
            if self.completed_rescue_count() < self._minimum_evacuation_count() or not self.rescue_notified:
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
        if target in self.blocked_paths_config and self.rubble_status.get(target) != "removed":
            return False, f"Cannot enter {target} until the obstruction blocking access is removed.", False
        conditions = self.rooms[target].conditions
        if conditions.get("electrical_hazard"):
            if self._can_enter_restricted_room(target):
                return True, "", False
            return False, (
                f"Unsafe move rejected: {target} has an electrical hazard. "
                "Use emergency entry only when a discovered survivor requires rescue-critical intervention."
            ), True
        structural_risk = str(conditions.get("structural_risk", "low"))
        if structural_risk in {"high", "severe"}:
            if self._can_enter_restricted_room(target):
                return True, "", False
            return False, (
                f"Unsafe move rejected: {target} has {structural_risk} structural risk. "
                "Use emergency entry only when a discovered survivor in that room needs rescue-critical intervention."
            ), True
        return True, "", False
