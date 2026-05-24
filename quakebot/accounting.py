from __future__ import annotations

from typing import Any

from .models import Survivor, _priority_rank


class AccountingMixin:
    def _minimum_evacuation_count(self) -> int:
        return min(2, len(self.survivors))

    def _specialised_extraction_reason(self, survivor: Survivor | None = None) -> str:
        if survivor is not None and survivor.location in self.hazard_blocked_access:
            return f"{survivor.location} cannot be safely entered through the current route."
        return "Survivor cannot be safely evacuated through the current route."

    def _emergency_entry_action_for_survivor(self, survivor: Survivor) -> dict[str, str] | None:
        if survivor.location == self.location:
            return None
        if not self._can_emergency_enter_room(survivor.location):
            return None
        if self.location in self.rooms and survivor.location in self.rooms[self.location].exits:
            return {"type": "move", "target": survivor.location}
        access_point = self._nearest_safe_access_point(survivor.location)
        if access_point:
            if access_point == self.location:
                return {"type": "move", "target": survivor.location}
            next_step = self.next_step_towards(self.location, access_point)
            if next_step:
                return {"type": "move", "target": next_step}
        return None

    def _remote_survivor_recommendation(self, survivor: Survivor) -> dict[str, str] | None:
        if survivor.accounted_for() or survivor.location == self.location:
            return None

        emergency_action = self._emergency_entry_action_for_survivor(survivor)
        if emergency_action is not None:
            if self._was_action_recently_rejected(emergency_action):
                emergency_action = None
            else:
                return emergency_action

        blocked = self.blocked_paths_config.get(survivor.location)
        if blocked and self.rubble_status.get(survivor.location) != "removed" and str(blocked.get("type", "")) == "rubble":
            required_location = str(blocked.get("required_location", ""))
            if required_location:
                clear_action = {"type": "clear_obstruction", "target": survivor.location}
                if self.location == required_location:
                    if not self._was_action_recently_rejected(clear_action):
                        return clear_action
                else:
                    next_step = self.next_step_towards(self.location, required_location)
                    if next_step and not self._was_action_recently_rejected({"type": "move", "target": next_step}):
                        return {"type": "move", "target": next_step}

        if survivor.extraction_requested:
            if survivor.extraction_status == "arrived":
                if self._is_valid_extraction_access_point(survivor.location):
                    return {"type": "handoff_to_specialised_team", "target": survivor.id}
                access_point = self._nearest_safe_access_point(survivor.location)
                if access_point:
                    next_step = self.next_step_towards(self.location, access_point)
                    if next_step and not self._was_action_recently_rejected({"type": "move", "target": next_step}):
                        return {"type": "move", "target": next_step}
                return {"type": "request_specialised_extraction", "target": survivor.id, "reason": self._specialised_extraction_reason(survivor)}

            access_point = self._nearest_safe_access_point(survivor.location)
            if access_point:
                if self.location != access_point:
                    next_step = self.next_step_towards(self.location, access_point)
                    if next_step and not self._was_action_recently_rejected({"type": "move", "target": next_step}):
                        return {"type": "move", "target": next_step}
            if not survivor.extraction_requested:
                return {"type": "request_specialised_extraction", "target": survivor.id, "reason": self._specialised_extraction_reason(survivor)}

        if survivor.location in self.hazard_blocked_access:
            if not survivor.extraction_requested:
                return {"type": "request_specialised_extraction", "target": survivor.id, "reason": self._specialised_extraction_reason(survivor)}
            if survivor.extraction_status == "arrived" and self._is_valid_extraction_access_point(survivor.location):
                return {"type": "handoff_to_specialised_team", "target": survivor.id}
            access_point = self._nearest_safe_access_point(survivor.location)
            if access_point and self.location != access_point:
                next_step = self.next_step_towards(self.location, access_point)
                if next_step and not self._was_action_recently_rejected({"type": "move", "target": next_step}):
                    return {"type": "move", "target": next_step}
            return {"type": "request_specialised_extraction", "target": survivor.id, "reason": self._specialised_extraction_reason(survivor)}

        next_step = self.next_step_towards(self.location, survivor.location)
        if next_step:
            return {"type": "move", "target": next_step}

        access_point = self._nearest_safe_access_point(survivor.location)
        if access_point:
            if self.location == access_point:
                if survivor.extraction_requested and survivor.extraction_status == "arrived" and self._is_valid_extraction_access_point(survivor.location):
                    return {"type": "handoff_to_specialised_team", "target": survivor.id}
                if not survivor.extraction_requested:
                    return {"type": "request_specialised_extraction", "target": survivor.id, "reason": self._specialised_extraction_reason(survivor)}
            else:
                next_step = self.next_step_towards(self.location, access_point)
                if next_step:
                    return {"type": "move", "target": next_step}

        if not survivor.extraction_requested:
            return {"type": "request_specialised_extraction", "target": survivor.id, "reason": self._specialised_extraction_reason(survivor)}
        if survivor.extraction_status == "arrived" and self._is_valid_extraction_access_point(survivor.location):
            return {"type": "handoff_to_specialised_team", "target": survivor.id}
        return {"type": "request_specialised_extraction", "target": survivor.id, "reason": self._specialised_extraction_reason(survivor)}

    def _final_report_summary(self) -> str:
        statuses = [
            f"{survivor.id}: {survivor.accounting_status}, priority {survivor.priority}"
            for survivor in self.survivors.values()
            if survivor.discovered
        ]
        return "All survivors accounted. " + "; ".join(statuses)

    def _blocked_paths(self) -> dict[str, dict[str, str]]:
        blocked: dict[str, dict[str, str]] = {}
        for room, status in self.rubble_status.items():
            if status == "removed":
                continue
            config = self.blocked_paths_config.get(room, {})
            blocked[room] = {
                "reason": str(config.get("type", "rubble")),
                "status": status,
                "required_location": str(config.get("required_location", "Hallway")),
                "next_required_action": "clear_obstruction",
            }
        return blocked

    def _blocked_connections_observation(self) -> list[list[str]]:
        return [sorted(connection) for connection in sorted(self.blocked_connections, key=lambda c: sorted(c))]

    def _recommended_next_actions(self) -> list[dict[str, str]]:
        local = self._best_local_survivor()
        if local and not local.accounted_for():
            if local.extraction_status == "arrived":
                return [{"type": "handoff_to_specialised_team", "target": local.id}]
            if local.extraction_requested and not local.safe_to_leave:
                if local.bleeding == "severe" and not local.bleeding_controlled:
                    return [{"type": "treat_survivor", "target": local.id, "treatment": "control_bleeding"}]
                if local.breathing_status == "laboured" and not local.breathing_supported:
                    return [{"type": "treat_survivor", "target": local.id, "treatment": "support_breathing"}]
                return [{"type": "treat_survivor", "target": local.id, "treatment": "monitor"}]
            
            if not local.reassured:
                return [{"type": "reassure_survivor", "target": local.id, "message": "I'm here with you. You're not alone."}]
            if "perform_primary_survey" not in local.checks_completed:
                return [{"type": "perform_primary_survey", "target": local.id}]
            if local.bleeding == "severe" and not local.bleeding_controlled:
                return [{"type": "treat_survivor", "target": local.id, "treatment": "control_bleeding"}]
            if local.breathing_status == "laboured" and not local.breathing_supported:
                return [{"type": "treat_survivor", "target": local.id, "treatment": "support_breathing"}]
            if not local.stabilised:
                return [{"type": "treat_survivor", "target": local.id, "treatment": "stabilise"}]
            if local.trapped:
                if self.rooms[self.location].conditions.get("structural_risk") == "severe":
                    return [{"type": "request_specialised_extraction", "target": local.id, "reason": self._specialised_extraction_reason(local)}]
                return [{"type": "free_survivor", "target": local.id}]
            return [{"type": "evacuate_survivor", "target": local.id}]

        discovered_unaccounted = [s for s in self.survivors.values() if s.discovered and not s.accounted_for()]
        discovered_unaccounted.sort(key=lambda s: _priority_rank(s.priority), reverse=True)
        if discovered_unaccounted:
            target = discovered_unaccounted[0]
            action = self._remote_survivor_recommendation(target)
            if action:
                return [action]

        if self.config.survivor_location_mode == "unknown":
            search_action = self._recommended_search_action()
            if search_action:
                return [search_action]

            accounting = self._mission_accounting()
            can_finish = accounting.get("mission_can_finish") or accounting.get("reason_not_finished") == "Must be at Entrance to finish mission."
            if can_finish:
                if self.location != "Entrance":
                    next_step = self.next_step_towards(self.location, "Entrance")
                    return [{"type": "move", "target": next_step}] if next_step else []
                if not self.rescue_notified:
                    return [{"type": "call_rescue_team", "location": "Entrance", "reason": self._handoff_summary()}]
                if not self.report_submitted:
                    return [{"type": "submit_report", "summary": self._final_report_summary()}]
            return []

        # If there are any blocked paths (like rubble) blocking an unaccounted survivor, route to it
        has_discovered_critical = any(
            s.discovered and s.priority == "critical" and not s.accounted_for()
            and s.location in self.hazard_blocked_access
            for s in self.survivors.values()
        )
        if not has_discovered_critical:
            for t, b in self._blocked_paths().items():
                if b.get("reason") == "rubble":
                    if any(s.location == t and not s.accounted_for() for s in self.survivors.values()):
                        req_loc = b.get("required_location")
                        if req_loc:
                            if self.location == req_loc:
                                return [{"type": "clear_obstruction", "target": t}]
                            next_step = self.next_step_towards(self.location, req_loc)
                            if next_step:
                                return [{"type": "move", "target": next_step}]
        known = [s for s in self.survivors.values() if s.discovered and not s.accounted_for()]
        known.sort(key=lambda s: _priority_rank(s.priority), reverse=True)
        if known:
            target = known[0]
            action = self._remote_survivor_recommendation(target)
            if action:
                return [action]

        unaccounted = [s for s in self.survivors.values() if not s.accounted_for()]
        if unaccounted:
            target = sorted(unaccounted, key=lambda s: _priority_rank(s.priority), reverse=True)[0]
            if target.location != self.location:
                next_step = self.next_step_towards(self.location, target.location)
                if next_step:
                    return [{"type": "move", "target": next_step}]
                access_point = self._nearest_safe_access_point(target.location)
                if access_point:
                    if self.location == access_point:
                        if self.location not in self.scanned_rooms:
                            return [{"type": "sense_area", "mode": "life_signs", "target": target.location}]
                        if target.location in self.rooms[self.location].exits:
                            if self._find_safe_path(self.location, target.location):
                                return [{"type": "move", "target": target.location}]
                            if target.location not in self.scanned_rooms:
                                return [{"type": "sense_area", "mode": "life_signs", "target": target.location}]
                            if target.discovered:
                                return [{"type": "request_specialised_extraction", "target": target.id, "reason": self._specialised_extraction_reason(target)}]
                    else:
                        nxt = self.next_step_towards(self.location, access_point)
                        if nxt:
                            return [{"type": "move", "target": nxt}]
            if not target.discovered:
                access_point = self._nearest_safe_access_point(target.location)
                if access_point and access_point != self.location:
                    next_step = self.next_step_towards(self.location, access_point)
                    if next_step:
                        return [{"type": "move", "target": next_step}]
                return [{"type": "sense_area", "mode": "life_signs", "target": target.location}]
        if self.config.survivor_count_mode == "approximate":
            search_action = self._recommended_search_action()
            if search_action:
                return [search_action]
        accounting = self._mission_accounting()
        can_finish = accounting.get("mission_can_finish") or accounting.get("reason_not_finished") == "Must be at Entrance to finish mission."
        if can_finish:
            if self.location != "Entrance":
                next_step = self.next_step_towards(self.location, "Entrance")
                return [{"type": "move", "target": next_step}] if next_step else []
            if not self.rescue_notified:
                return [{"type": "call_rescue_team", "location": "Entrance", "reason": self._handoff_summary()}]
            if not self.report_submitted:
                return [{"type": "submit_report", "summary": self._final_report_summary()}]
        return []

    def _best_local_survivor(self) -> Survivor | None:
        local = self._local_survivors()
        local.sort(key=lambda s: _priority_rank(s.priority), reverse=True)
        return local[0] if local else None

    def _mission_accounting(self) -> dict[str, object]:
        survivors = list(self.survivors.values())
        discovered_survivors = [s for s in survivors if s.discovered]
        
        if self.config.survivor_location_mode == "unknown":
            unaccounted = [s.id for s in discovered_survivors if not s.accounted_for()]
            uncleared = self._uncleared_reachable_rooms()
            unidentified_cues = self._unidentified_survivor_cues()
            
            if self.config.survivor_count_mode == "exact":
                target_count = self.config.survivor_count or 0
                has_all_discovered = len(discovered_survivors) >= target_count
                can_finish = (
                    has_all_discovered
                    and not unaccounted
                    and not unidentified_cues
                    and self.location == "Entrance"
                )
                if not has_all_discovered:
                    reason = f"Only discovered {len(discovered_survivors)} of {target_count} survivors."
                elif unaccounted:
                    reason = f"{', '.join(unaccounted)} are discovered but unaccounted."
                elif unidentified_cues:
                    reason = "There are unresolved survivor cues."
                elif self.location != "Entrance":
                    reason = "Must be at Entrance to finish mission."
                else:
                    reason = ""
            else:
                can_finish = (
                    not uncleared
                    and not unaccounted
                    and self.location == "Entrance"
                )
                if uncleared:
                    reason = "Survivor locations are unknown; reachable rooms remain uncleared."
                elif unaccounted:
                    reason = f"{', '.join(unaccounted)} are discovered but unaccounted."
                elif self.location != "Entrance":
                    reason = "Must be at Entrance to finish mission."
                else:
                    reason = ""
                    
            return {
                "survivor_location_mode": self.config.survivor_location_mode,
                "survivor_count_mode": self.config.survivor_count_mode,
                "confirmed_survivors": len(discovered_survivors),
                "total_known_or_suspected_survivors": len(discovered_survivors),
                "estimated_survivors": self.config.survivor_count,
                "survivor_count_min": self.config.survivor_count_min,
                "survivor_count_max": self.config.survivor_count_max,
                "discovered_survivors": [s.id for s in discovered_survivors],
                "evacuated": [s.id for s in discovered_survivors if s.evacuated],
                "directly_assessed": [s.id for s in discovered_survivors if s.directly_assessed],
                "awaiting_specialised_extraction": [s.id for s in discovered_survivors if s.accounting_status == "awaiting_specialised_extraction"],
                "extraction_requested": [s.id for s in discovered_survivors if s.extraction_requested],
                "inaccessible_confirmed": [s.id for s in discovered_survivors if s.inaccessible_confirmed],
                "unidentified_survivor_cues": unidentified_cues,
                "uncleared_reachable_rooms": uncleared,
                "mission_can_finish": can_finish,
                "reason_not_finished": reason,
                "unaccounted": unaccounted,
                "unaccounted_survivors": unaccounted,
            }

        unaccounted = [s.id for s in survivors if not s.accounted_for()]
        uncleared = self._uncleared_reachable_rooms() if self.config.survivor_count_mode == "approximate" else []
        reason = ""
        if unaccounted:
            reason = f"{', '.join(unaccounted)} has not been evacuated, directly assessed with extraction requested, or confirmed inaccessible"
        elif uncleared:
            reason = "Survivor count is approximate; reachable rooms remain uncleared: " + ", ".join(uncleared)
        elif self.completed_rescue_count() < self._minimum_evacuation_count():
            required = self._minimum_evacuation_count()
            reason = f"Must evacuate or safely hand off at least {required} survivor{'s' if required != 1 else ''} to finish mission."
        elif self.location != "Entrance":
            reason = "Must be at Entrance to finish mission."
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
            "mission_can_finish": (
                not unaccounted
                and not uncleared
                and self.location == "Entrance"
                and self.completed_rescue_count() >= self._minimum_evacuation_count()
            ),
            "reason_not_finished": reason,
        }

    def _priority_reason(self) -> str:
        unaccounted = [s for s in self.survivors.values() if not s.accounted_for()]
        critical = [s for s in unaccounted if s.priority == "critical"]
        if critical and self.evacuated_count() > 0:
            return f"Critical cues detected from {critical[0].location}; prioritising assessment before mission handoff."
        if unaccounted and any(s.trapped for s in unaccounted) and self.location != "Entrance":
            return "Trapped survivor cue indicates a potentially critical situation; continue rescue safely."
        return ""

    def _safe_reachable_rooms_from_entrance(self) -> set[str]:
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
                if nxt in self.blocked_paths_config and self.rubble_status.get(nxt) != "removed":
                    continue
                seen.add(nxt)
                queue.append(nxt)
        return seen

    def _accounting_relevant_rooms_from_entrance(self) -> set[str]:
        start = "Entrance" if "Entrance" in self.rooms else next(iter(self.rooms))
        queue = [start]
        seen = {start}
        while queue:
            room_name = queue.pop(0)
            for nxt in self.rooms[room_name].exits:
                if nxt in seen:
                    continue
                if self._connection_key(room_name, nxt) in self.blocked_connections:
                    continue
                if nxt in self.blocked_paths_config and self.rubble_status.get(nxt) != "removed":
                    continue
                # Accounting-relevant rooms include unsafe rooms like Utility_Room
                seen.add(nxt)
                conditions = self.rooms[nxt].conditions
                if conditions.get("electrical_hazard") or conditions.get("structural_risk") == "severe":
                    continue
                queue.append(nxt)
        return seen

    def _uncleared_reachable_rooms(self) -> list[str]:
        relevant = self._accounting_relevant_rooms_from_entrance()
        return sorted(
            room
            for room in relevant
            if self.room_search_status.get(room) not in {"cleared", "inaccessible_confirmed"}
        )
