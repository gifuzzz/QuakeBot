from __future__ import annotations


class NavigationMixin:
    def _is_adjacent(self, room_a: str, room_b: str) -> bool:
        if room_a not in self.rooms or room_b not in self.rooms:
            return False
        return room_b in self.rooms[room_a].exits

    def _can_scan_from_here(self, target_room: str) -> bool:
        return target_room == self.location or self._is_adjacent(self.location, target_room)

    def _room_was_scanned_or_access_attempted(self, target_room: str) -> bool:
        return target_room in self.scanned_rooms or target_room in self.hazard_blocked_access

    def _is_safe_to_stand_in(self, room_name: str) -> bool:
        if room_name not in self.rooms:
            return False
        conditions = self.rooms[room_name].conditions
        return not conditions.get("electrical_hazard") and conditions.get("structural_risk") == "low" or conditions.get("structural_risk") == "medium" or conditions.get("structural_risk") is None

    def _can_enter_room(self, room_name: str) -> bool:
        return self._is_safe_to_stand_in(room_name)

    def _safe_access_points(self, target_room: str) -> list[str]:
        if target_room not in self.rooms:
            return []
        return [exit_name for exit_name in self.rooms[target_room].exits if self._is_safe_to_stand_in(exit_name)]

    def _room_requires_restricted_entry(self, room_name: str) -> bool:
        if room_name not in self.rooms:
            return False
        conditions = self.rooms[room_name].conditions
        return bool(conditions.get("electrical_hazard") or conditions.get("structural_risk") in {"high", "severe"})

    def _survivor_requires_emergency_entry(self, survivor) -> bool:
        if survivor is None or survivor.location not in self.rooms:
            return False
        if survivor.evacuated or survivor.handoff_complete or survivor.inaccessible_confirmed:
            return False
        conditions = self.rooms[survivor.location].conditions
        if not self._room_requires_restricted_entry(survivor.location):
            return False
        if not survivor.discovered:
            return False
        if not survivor.directly_assessed:
            return True
        if survivor.trapped:
            return True
        if survivor.bleeding == "severe" and not survivor.bleeding_controlled:
            return True
        if survivor.breathing_status in {"laboured", "not_breathing"} and not survivor.breathing_supported:
            return True
        if survivor.priority in {"high", "critical"} and not survivor.safe_to_leave:
            return True
        if survivor.extraction_requested and not survivor.safe_to_leave and not survivor.handoff_complete:
            return True
        if conditions.get("structural_risk") == "severe" and not survivor.safe_to_leave:
            return True
        return False

    def _can_emergency_enter_room(self, target_room: str) -> bool:
        if target_room not in self.rooms:
            return False
        if self.location not in self._safe_access_points(target_room):
            return False
        if not self._room_requires_restricted_entry(target_room):
            return False
        return any(
            self._survivor_requires_emergency_entry(survivor)
            for survivor in self.survivors.values()
            if survivor.location == target_room
        )

    def _can_enter_restricted_room(self, target_room: str) -> bool:
        if target_room not in self.rooms:
            return False
        if not self._room_requires_restricted_entry(target_room):
            return True
        if self._can_emergency_enter_room(target_room):
            return True
        if target_room in self.scanned_rooms:
            has_unaccounted_survivor = any(
                survivor.location == target_room and not survivor.accounted_for()
                for survivor in self.survivors.values()
            )
            if not has_unaccounted_survivor:
                return True
        return False

    def _nearest_safe_access_point(self, target_room: str) -> str | None:
        access_points = self._safe_access_points(target_room)
        if not access_points:
            return None
        if self.location in access_points:
            return self.location
        def dist(r):
            path = self._find_safe_path(self.location, r)
            return len(path) if path is not None else float('inf')
        reachable = [r for r in access_points if self._find_safe_path(self.location, r) is not None]
        if not reachable:
            return None
        return min(reachable, key=dist)

    def _is_valid_extraction_access_point(self, target_room: str) -> bool:
        if target_room not in self.rooms:
            return False
        if self.location not in self._safe_access_points(target_room):
            return False
        if target_room in self.rooms_confirmed_inaccessible or target_room in self.hazard_blocked_access:
            return True
        conditions = self.rooms[target_room].conditions
        return bool(conditions.get("electrical_hazard") or conditions.get("structural_risk") == "severe")

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
                if (conditions.get("electrical_hazard") or conditions.get("structural_risk") in {"high", "severe"}) and not self._can_enter_restricted_room(nxt):
                    continue
                if nxt in self.blocked_paths_config and self.rubble_status.get(nxt) != "removed":
                    continue
                seen.add(nxt)
                queue.append((nxt, path + [nxt]))
        return None

    def _find_path_ignoring_blocked_paths(self, start: str, goal: str) -> list[str] | None:
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
                if (conditions.get("electrical_hazard") or conditions.get("structural_risk") in {"high", "severe"}) and not self._can_enter_restricted_room(nxt):
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

    @staticmethod
    def _connection_key(a: str, b: str) -> frozenset[str]:
        return frozenset((a, b))

    def _remove_exit(self, a: str, b: str) -> None:
        self.rooms[a].exits = [exit_name for exit_name in self.rooms[a].exits if exit_name != b]
        self.rooms[b].exits = [exit_name for exit_name in self.rooms[b].exits if exit_name != a]
