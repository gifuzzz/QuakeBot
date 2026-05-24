from __future__ import annotations

from .actions import Action
from .models import Survivor, calculate_triage_priority


class ActionHandlersMixin:
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

    def _do_search_room(self, action: Action) -> str:
        self._search_room(self.location)
        found = self._nearby_survivors(include_current=True)
        for survivor in found:
            self._confirm_survivor(survivor, directly_seen=survivor.location == self.location)
        if found:
            return "QuakeBot searches the room and accounts for signs of: " + ", ".join(
                f"{s.id} at {s.location}" for s in found
            ) + "."
        return f"QuakeBot searches {self.location}; no survivor is found here."

    def _do_sense_area(self, action: Action) -> str:
        target = action.target or self.location
        if action.mode == "audio":
            sounds = self._heard_sounds(target)
            if not sounds:
                return f"No clear survivor sound detected in {target}."
            for survivor in self._survivors_detectable_from(target):
                self._confirm_survivor(survivor, directly_seen=survivor.location == self.location)
            clue = "; ".join(sounds)
            self.memory.record_survivor_clue(clue)
            return f"Audio sensors isolate survivor cues in {target}: {clue}."

        if action.mode == "vibration":
            cues = self._vibration_cues(target)
            if not cues:
                return f"No survivor-like vibration detected in {target}."
            for survivor in self._survivors_detectable_from(target):
                self._confirm_survivor(survivor, directly_seen=survivor.location == self.location)
            clue = "; ".join(cues)
            self.memory.record_survivor_clue(clue)
            return f"QuakeBot senses vibration cues in {target}: {clue}."

        self.scanned_rooms.add(target)
        if target == self.location:
            self._mark_searched(target)
        else:
            self._mark_scanned(target)
            self.hazard_blocked_access.add(target)

        found = [s for s in self.survivors.values() if s.location == target and not s.evacuated]
        for survivor in found:
            self._confirm_survivor(survivor, directly_seen=survivor.location == self.location)
            self._discover_room(survivor.location)
        if found:
            return f"Life-sign scan of {target} detects: " + ", ".join(f"{s.id} at {s.location}" for s in found) + "."
        self._auto_clear_room_if_empty(target)
        return f"No life signs detected in {target}."

    def _do_clear_obstruction(self, action: Action) -> str:
        target = action.target or ""
        status = self.rubble_status.get(target)
        if target not in self.blocked_paths_config:
            return f"No obstruction is configured for {target}."
        if status == "removed":
            return f"Obstruction for {target} has already been removed."

        blocked = self.blocked_paths_config[target]
        required_location = str(blocked.get("required_location", self.location))
        obstruction_type = str(blocked.get("type", "obstruction"))
        self.rubble_status[target] = "removed"
        connection = self._connection_key(required_location, target)
        self.blocked_connections.discard(connection)
        self.rooms[required_location].objects = [
            obj for obj in self.rooms[required_location].objects if obj not in {obstruction_type, "rubble", "debris", "obstruction"}
        ]
        self._discover_room(target)
        self._mark_scanned(target)
        for survivor in self.survivors.values():
            if survivor.location == target and not survivor.evacuated:
                self._confirm_survivor(survivor, directly_seen=False)
        return f"QuakeBot clears the {obstruction_type} blocking {target}; access from {required_location} is open."

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

    def _do_treat_survivor(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        treatment = action.treatment or ""
        if treatment == "control_bleeding":
            survivor.bleeding_controlled = survivor.bleeding in {"minor", "severe"}
            survivor.stabilised = True
            survivor.stability = min(100, survivor.stability + (8 if survivor.bleeding == "severe" else 4))
            self._mark_stabilised_after_worsening(survivor)
            self._add_check(survivor, "treat_survivor:control_bleeding")
            return f"QuakeBot controls bleeding for {survivor.id}."
        if treatment == "support_breathing":
            survivor.breathing_supported = survivor.breathing_status in {"laboured", "fast", "not_breathing"}
            survivor.airway_clear = survivor.breathing_status != "not_breathing"
            survivor.stabilised = True
            survivor.stability = min(100, survivor.stability + 6)
            self._mark_stabilised_after_worsening(survivor)
            self._add_check(survivor, "treat_survivor:support_breathing")
            return f"QuakeBot supports breathing for {survivor.id}."
        if treatment == "stabilise":
            survivor.stabilised = True
            if survivor.breathing_status == "laboured":
                survivor.breathing_supported = True
            survivor.stability = min(100, survivor.stability + 5)
            self._mark_stabilised_after_worsening(survivor)
            self._add_check(survivor, "treat_survivor:stabilise")
            return f"QuakeBot stabilises {survivor.id} before movement."
        if treatment == "monitor":
            survivor.last_checked_step = self.step_count
            survivor.last_monitored_step = self.step_count
            self._add_check(survivor, "treat_survivor:monitor")
            return f"QuakeBot monitors {survivor.id}: breathing {survivor.breathing_status}, pulse {survivor.pulse_status}."
        if treatment == "protect":
            self._add_check(survivor, "treat_survivor:protect")
            return f"QuakeBot protects {survivor.id} from immediate debris and hazard exposure."
        if "first_aid_kit" in self.inventory:
            self._add_check(survivor, "treat_survivor:supply")
            return f"QuakeBot uses available first-aid supplies for {survivor.id}."
        return "No modelled supplies are available; use another treatment or request specialised extraction."

    def _do_free_survivor(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        survivor.trapped = False
        survivor.reachable = True
        return f"QuakeBot carefully frees {survivor.id} from survivor-specific entrapment."

    def _do_evacuate_survivor(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        path = self._find_safe_path(self.location, "Entrance")
        assert path is not None
        old_location = self.location
        self.location = "Entrance"
        survivor.location = "Entrance"
        survivor.carried = False
        survivor.evacuated = True
        if survivor.id not in self.evacuation_order:
            self.evacuation_order.append(survivor.id)
        self._mark_searched(old_location)
        self._auto_clear_room_if_empty(old_location)
        method = "assisted evacuation" if survivor.can_walk else "carried evacuation"
        return f"QuakeBot completes {method} for {survivor.id} to Entrance via {' -> '.join(path)}."

    def _do_mark_hazard(self, action: Action) -> str:
        hazard = action.hazard_type or "unknown"
        self.hazard_marks.setdefault(self.location, []).append(hazard)
        for event in self.world_events:
            if event.location == self.location and event.id not in self.responded_to_random_hazards:
                self.responded_to_random_hazards.add(event.id)
        self.memory.record_hazard(self.location, hazard)
        return f"QuakeBot marks {hazard} at {self.location}."

    def _do_request_specialised_extraction(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        survivor.extraction_requested = True
        if survivor.extraction_status == "not_requested":
            survivor.extraction_status = "en_route"
            survivor.extraction_eta_steps = self.random.randint(4, 8)
        self._confirm_survivor(survivor, directly_seen=survivor.location == self.location)
        return f"Specialised extraction requested for {survivor.id}: {action.reason}. ETA: {survivor.extraction_eta_steps} steps."

    def _do_handoff_to_specialised_team(self, action: Action) -> str:
        survivor = self._target_survivor(action.target)
        assert survivor is not None
        if survivor.extraction_status == "arrived":
            survivor.handoff_complete = True
            survivor.safe_to_leave = True
            if survivor.id not in self.evacuation_order:
                self.evacuation_order.append(survivor.id)
            return f"Specialised extraction team completes handoff for {survivor.id}. Survivor is safely extracted."
        self.invalid_actions += 1
        return f"Cannot handoff {survivor.id}: extraction team has not arrived yet."

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

    def _do_submit_report(self, action: Action) -> str:
        self.report_submitted = True
        self.final_report = action.summary
        summary = (action.summary or "").lower()
        self.hazards_reported_in_final_report = any(
            word in summary for word in ("smoke", "hazard", "structural", "electrical", "aftershock", "basement")
        )
        return "Final rescue report submitted."

    def _survivors_detectable_from(self, target: str) -> list[Survivor]:
        rooms = set(self.rooms[target].exits) | {target}
        return [s for s in self.survivors.values() if s.location in rooms and not s.evacuated]

    def _add_check(self, survivor: Survivor, check: str) -> None:
        if check not in survivor.checks_completed:
            survivor.checks_completed.append(check)
        if check == "perform_primary_survey":
            survivor.directly_assessed = True
            survivor.last_checked_step = self.step_count
            self._confirm_survivor(survivor, directly_seen=True)
            survivor.pulse_checked = True
            survivor.breathing_checked = True
            survivor.airway_clear = survivor.breathing_status != "not_breathing"
            survivor.bleeding_checked = True

    def _update_safe_to_leave(self, survivor: Survivor) -> None:
        if survivor.handoff_complete:
            survivor.safe_to_leave = True
            survivor.immediate_life_threats_stabilised = True
            return
        if survivor.priority != "critical":
            survivor.safe_to_leave = True
            survivor.immediate_life_threats_stabilised = True
            return
        stabilised = True
        if survivor.bleeding == "severe" and not survivor.bleeding_controlled:
            stabilised = False
        if not survivor.airway_clear:
            stabilised = False
        if survivor.breathing_status == "laboured" and not survivor.breathing_supported:
            stabilised = False
        if not survivor.pulse_checked:
            stabilised = False
        survivor.immediate_life_threats_stabilised = stabilised
        survivor.safe_to_leave = stabilised and self.rooms[survivor.location].conditions.get("structural_risk") != "severe"

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
            "ask_medical_question",
            "reassure_survivor",
            "perform_primary_survey",
            "treat_survivor",
            "handoff_to_specialised_team",
            "request_specialised_extraction",
            "free_survivor",
            "evacuate_survivor",
        }

    def _mark_stabilised_after_worsening(self, survivor: Survivor) -> None:
        if survivor.condition_history:
            self.stabilised_after_worsening.add(survivor.id)

    def _handoff_summary(self) -> str:
        return f"{self.evacuated_count()} survivors evacuated; statuses: " + "; ".join(
            f"{s.id} {s.priority} {s.public_status()['status']}" for s in self.survivors.values() if s.discovered
        )
