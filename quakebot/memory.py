"""Lightweight structured memory for discovered rescue-world facts."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Memory:
    """Agent-facing memory maintained by the environment."""

    visited_rooms: set[str] = field(default_factory=set)
    known_connections: dict[str, set[str]] = field(default_factory=dict)
    discovered_hazards: dict[str, list[str]] = field(default_factory=dict)
    discovered_survivors: set[str] = field(default_factory=set)
    survivor_clues: list[str] = field(default_factory=list)
    survivor_status: dict[str, object] = field(default_factory=dict)
    item_locations: dict[str, str] = field(default_factory=dict)
    event_history: list[str] = field(default_factory=list)

    def record_room(self, room: str, exits: list[str]) -> None:
        self.visited_rooms.add(room)
        self.known_connections.setdefault(room, set()).update(exits)
        for exit_name in exits:
            self.known_connections.setdefault(exit_name, set()).add(room)

    def record_hazard(self, room: str, hazard: str) -> None:
        hazards = self.discovered_hazards.setdefault(room, [])
        if hazard not in hazards:
            hazards.append(hazard)

    def record_survivor(self, room: str) -> None:
        self.discovered_survivors.add(room)

    def record_survivor_clue(self, clue: str) -> None:
        if clue not in self.survivor_clues:
            self.survivor_clues.append(clue)

    def update_survivor_status(self, status: dict[str, object]) -> None:
        self.survivor_status.update(status)

    def record_item(self, item: str, room: str) -> None:
        self.item_locations[item] = room

    def record_event(self, event: str) -> None:
        self.event_history.append(event)

    def to_dict(self) -> dict[str, object]:
        return {
            "visited_rooms": sorted(self.visited_rooms),
            "known_connections": {
                room: sorted(exits) for room, exits in sorted(self.known_connections.items())
            },
            "discovered_hazards": {
                room: sorted(hazards) for room, hazards in sorted(self.discovered_hazards.items())
            },
            "discovered_survivor_locations": sorted(self.discovered_survivors),
            "survivor_clues": list(self.survivor_clues),
            "survivor_status": dict(sorted(self.survivor_status.items())),
            "item_locations": dict(sorted(self.item_locations.items())),
            "event_history": list(self.event_history),
        }
