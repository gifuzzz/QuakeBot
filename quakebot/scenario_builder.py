from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .scenario import LoadedLayout


@dataclass
class RoomSpec:
    name: str
    conditions: dict[str, Any] = field(default_factory=dict)
    items: list[str] = field(default_factory=list)
    blocked_by: dict[str, Any] | None = None
    sounds: list[str] = field(default_factory=list)
    vibration_cues: list[str] = field(default_factory=list)
    survivor_cues: list[str] = field(default_factory=list)
    exits: set[str] = field(default_factory=set)

    def connect(self, other: RoomSpec) -> None:
        self.exits.add(other.name)
        other.exits.add(self.name)


@dataclass
class FloorSpec:
    id: str
    name: str
    rooms: list[RoomSpec] = field(default_factory=list)


@dataclass
class SurvivorSpec:
    id: str
    name: str | None
    location: RoomSpec | str
    trapped: bool = False
    reachable: bool = True
    conscious: bool = True
    responsive: bool = True
    breathing_status: str = "normal"
    pulse_status: str = "normal"
    bleeding: str = "none"
    pain_level: int = 0
    can_walk: bool = True
    suspected_injuries: list[str] = field(default_factory=list)
    priority: str = "medium"


@dataclass
class ScenarioSpec:
    id: str
    name: str
    floors: list[FloorSpec] = field(default_factory=list)
    survivors: list[SurvivorSpec] = field(default_factory=list)

    def compile(self) -> LoadedLayout:
        floors_dict = {}
        room_to_floor = {}
        blocked_paths = {}

        for floor in self.floors:
            rooms_dict = {}
            for room in floor.rooms:
                room_to_floor[room.name] = floor.id
                room_data: dict[str, Any] = {
                    "connects_to": list(room.exits),
                }
                if room.conditions:
                    room_data["conditions"] = room.conditions
                if room.items:
                    room_data["items"] = room.items
                if room.blocked_by:
                    room_data["blocked_by"] = room.blocked_by
                    blocked_paths[room.name] = room.blocked_by
                if room.sounds:
                    room_data["sounds"] = room.sounds
                if room.vibration_cues:
                    room_data["vibration_cues"] = room.vibration_cues
                if room.survivor_cues:
                    room_data["survivor_cues"] = room.survivor_cues
                
                rooms_dict[room.name] = room_data

            floors_dict[floor.id] = {
                "name": floor.name,
                "rooms": rooms_dict,
            }

        survivors_dict = {}
        for survivor in self.survivors:
            location_name = survivor.location.name if isinstance(survivor.location, RoomSpec) else survivor.location
            survivors_dict[survivor.id] = {
                "name": survivor.name,
                "location": location_name,
                "trapped": survivor.trapped,
                "reachable": survivor.reachable,
                "conscious": survivor.conscious,
                "responsive": survivor.responsive,
                "breathing_status": survivor.breathing_status,
                "pulse_status": survivor.pulse_status,
                "bleeding": survivor.bleeding,
                "pain_level": survivor.pain_level,
                "can_walk": survivor.can_walk,
                "suspected_injuries": survivor.suspected_injuries,
                "priority": survivor.priority,
            }

        return LoadedLayout(
            layout_id=self.id,
            name=self.name,
            floors=floors_dict,
            survivors=survivors_dict,
            room_to_floor=room_to_floor,
            blocked_paths=blocked_paths,
        )
