from __future__ import annotations

from typing import Any

from .models import Room, Survivor


GOAL = "Locate every known or suspected survivor, triage them, evacuate or account for each one, notify rescuers, and report hazards."


class ObservationMixin:
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
            "survivor_location_mode": self.config.survivor_location_mode,
            "room_search_status": dict(self.room_search_status),
            "rooms_to_search": self._rooms_to_search(),
            "rooms_confirmed_inaccessible": sorted(self.rooms_confirmed_inaccessible),
            "rooms_with_survivor_cues": self._rooms_with_survivor_cues() if self.config.survivor_location_mode != "unknown" else [],
            "unknown_survivor_cues": self._unidentified_survivor_cues() if self.config.survivor_location_mode == "unknown" else [],
            "discovered_survivors": [s.id for s in self.survivors.values() if s.discovered],
            "known_survivors": self._known_survivors(),
            "mission_accounting": self._mission_accounting(),
            "known_floors": self._known_floors(),
            "known_map": self.memory.to_dict(),
            "recent_events": [event.to_dict() for event in self.world_events[-5:]] + self.event_log[-5:],
            "events_this_step": [event.to_dict() for event in self.events_this_step],
            "condition_changes_since_last_step": self._condition_changes_since_last_step(),
        }

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

    def _unidentified_survivor_cues(self) -> list[str]:
        cues = []
        if self.config.survivor_location_mode == "unknown":
            room_name = self.location
            if self._room_has_unaccounted_survivor_or_cue(room_name):
                cues.extend(self._survivor_cues(room_name))
                cues.extend(self._heard_sounds(room_name))
                cues.extend(self._vibration_cues(room_name))
        else:
            for room_name in self._rooms_with_survivor_cues():
                if self._room_has_unaccounted_survivor_or_cue(room_name):
                    cues.extend(self._survivor_cues(room_name))
                    cues.extend(self._heard_sounds(room_name))
                    cues.extend(self._vibration_cues(room_name))
        return list(set(cues))

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
        if self.room_search_status.get(room_name) not in {"inaccessible_confirmed", "cleared"}:
            self.room_search_status[room_name] = "searched"
        self.scanned_rooms.add(room_name)

    def _mark_scanned(self, room_name: str) -> None:
        if self.room_search_status.get(room_name) in {"unknown", "discovered"}:
            self.room_search_status[room_name] = "scanned"
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
        for s in self.survivors.values():
            if s.location in cue_locations and not s.accounted_for():
                return True
        return False

    def _mark_room_inaccessible(self, room_name: str, reason: str) -> None:
        if room_name in self.rooms:
            self.room_search_status[room_name] = "inaccessible_confirmed"
            self.rooms_confirmed_inaccessible.add(room_name)
            self.room_inaccessible_reasons[room_name] = reason

    def _rooms_to_search(self) -> list[str]:
        if self.config.survivor_count_mode == "approximate":
            return self._uncleared_reachable_rooms()
        if self.config.survivor_location_mode == "unknown":
            return []
        return [room for room in self._rooms_with_survivor_cues() if self._room_has_unaccounted_survivor_or_cue(room)]

    def _rooms_with_survivor_cues(self) -> list[str]:
        return sorted(
            room_name
            for room_name in self.rooms
            if self._survivor_cues(room_name) or self._heard_sounds(room_name) or self._vibration_cues(room_name)
        )

    def _was_action_recently_rejected(self, action_dict: dict[str, str]) -> bool:
        for rejected in self.last_rejected_actions[-3:]:
            if rejected.type == action_dict.get("type") and rejected.target == action_dict.get("target"):
                return True
        return False

    def _recommended_search_action(self) -> dict[str, str] | None:
        uncleared = self._rooms_to_search()
        if not uncleared:
            if self.location != "Entrance":
                next_step = self.next_step_towards(self.location, "Entrance")
                return {"type": "move", "target": next_step} if next_step else None
            return None
        if self.location in uncleared:
            status = self.room_search_status.get(self.location)
            if status in {"unknown", "discovered"}:
                return {"type": "search_room"}
            if status == "searched":
                return {"type": "mark_room_cleared", "target": self.location}
                
        # Check adjacent unsafe/uncleared rooms
        for adj in self.rooms[self.location].exits:
            if adj in uncleared:
                path = self._find_safe_path(self.location, adj)
                if not path:
                    status = self.room_search_status.get(adj)
                    if status in {"unknown", "discovered"}:
                        scan_action = {"type": "sense_area", "mode": "life_signs", "target": adj}
                        if not self._was_action_recently_rejected(scan_action):
                            return scan_action
                    if status in {"scanned", "searched"}:
                        inaccess_action = {"type": "mark_room_inaccessible", "target": adj, "reason": "unsafe to enter due to hazards"}
                        if not self._was_action_recently_rejected(inaccess_action):
                            return inaccess_action
                        
        target = self._nearest_room(uncleared)
        if target:
            next_step = self.next_step_towards(self.location, target)
            if next_step:
                return {"type": "move", "target": next_step}
                
        # If no safe path to uncleared rooms, route to adjacent safe rooms to scan them
        best_unsafe_route: tuple[int, str, str] | None = None
        for room_name in uncleared:
            if self._find_safe_path(self.location, room_name) is None:
                for adj in self.rooms[room_name].exits:
                    path = self._find_safe_path(self.location, adj)
                    if path is not None:
                        candidate = (len(path), adj, room_name)
                        if best_unsafe_route is None or candidate < best_unsafe_route:
                            best_unsafe_route = candidate
                            
        if best_unsafe_route:
            adj_room = best_unsafe_route[1]
            if adj_room != self.location:
                next_step = self.next_step_towards(self.location, adj_room)
                if next_step:
                    return {"type": "move", "target": next_step}
                    
        return None


    def _is_survivor_cue_active(self, survivor_id: str, hearer_room: str) -> bool:
        if survivor_id not in self.survivors:
            return False
        survivor = self.survivors[survivor_id]
        if survivor.accounted_for():
            return False
        return True

    def _heard_sounds(self, room_name: str) -> list[str]:
        sounds = list(self.rooms[room_name].sounds)
        for s in self.survivors.values():
            if not self._is_survivor_cue_active(s.id, room_name): continue
            if s.location == room_name:
                if s.conscious and s.responsive: sounds.append(f"weak voice from {room_name}")
                elif s.trapped: sounds.append(f"intermittent tapping from {room_name}")
            elif self._is_adjacent(room_name, s.location):
                if s.trapped: sounds.append(f"muffled knocking from {s.location}")
                elif s.conscious and s.responsive: sounds.append(f"muffled calling from {s.location}")
        return sounds

    def _vibration_cues(self, room_name: str) -> list[str]:
        cues = list(self.rooms[room_name].vibration_cues)
        for s in self.survivors.values():
            if not self._is_survivor_cue_active(s.id, room_name): continue
            if s.trapped and self._is_adjacent(room_name, s.location):
                cues.append(f"weak vibration toward {s.location}")
        return cues

    def _survivor_cues(self, room_name: str) -> list[str]:
        cues = list(self.rooms[room_name].survivor_cues)
        for s in self.survivors.values():
            if not self._is_survivor_cue_active(s.id, room_name): continue
            if s.trapped and self._is_adjacent(room_name, s.location):
                cues.append(f"muffled knocking from {s.location}")
        if room_name == self.location:
            for survivor in self.survivors.values():
                if survivor.location == self.location and not survivor.evacuated:
                    if self.config.survivor_location_mode == "unknown" and not survivor.discovered:
                        cues.append("unidentified survivor: " + survivor.visible_condition())
                    else:
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
        # if self.location == "Stairwell_B":
        #     locations.add("Basement")
        if include_current:
            locations.add(self.location)
        return [s for s in self.survivors.values() if s.location in locations and not s.evacuated]

    def _vertical_exits(self, room: Room) -> list[str]:
        return [exit_name for exit_name in room.exits if self.rooms[exit_name].floor != room.floor]

    def _sync_memory_from_current_room(self) -> None:
        room = self.rooms[self.location]
        self.memory.record_room(room.name, room.exits)
        for item in room.items:
            self.memory.record_item(item, room.name)
        for survivor in self.survivors.values():
            if survivor.location == self.location and not survivor.evacuated:
                self._confirm_survivor(survivor, directly_seen=True)
            if survivor.discovered:
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
