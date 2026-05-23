"""Scenario configuration and semantic layout loading."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Literal


SurvivorCountMode = Literal["exact", "approximate"]


@dataclass(frozen=True)
class ScenarioConfig:
    """Runtime scenario selection for the symbolic rescue environment."""

    scenario_name: str = "Default Earthquake Building"
    layout_pack: str = "default"
    active_floors: list[str] | None = None
    survivor_count_mode: SurvivorCountMode = "exact"
    survivor_count: int | None = 3
    survivor_count_min: int | None = None
    survivor_count_max: int | None = None
    seed: int = 7
    random_events_enabled: bool = False
    max_steps: int = 100

    def __post_init__(self) -> None:
        if self.active_floors is None:
            object.__setattr__(self, "active_floors", ["ground", "floor_1", "basement"])
        if self.survivor_count_mode not in {"exact", "approximate"}:
            raise ValueError("survivor_count_mode must be 'exact' or 'approximate'.")
        if self.survivor_count_mode == "exact" and self.survivor_count is None:
            raise ValueError("exact survivor_count_mode requires survivor_count.")
        if self.survivor_count_mode == "approximate" and (
            self.survivor_count_min is None or self.survivor_count_max is None
        ):
            raise ValueError("approximate survivor_count_mode requires survivor_count_min and survivor_count_max.")


@dataclass(frozen=True)
class LoadedLayout:
    """Semantic room-level layout data used by the environment."""

    layout_id: str
    name: str
    floors: dict[str, Any]
    survivors: dict[str, Any]
    room_to_floor: dict[str, str]
    blocked_paths: dict[str, dict[str, Any]]


def load_layout(config: ScenarioConfig | None = None) -> LoadedLayout:
    """Load and validate the semantic layout pack for a scenario."""

    config = config or ScenarioConfig()
    path = _layout_pack_dir(config.layout_pack) / "building.json"
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return _validate_layout(data, config)


def load_visual_layout(layout_pack: str = "default") -> dict[str, Any]:
    """Load optional visual-only layout data.

    The environment never calls this helper; it is for presentation code.
    """

    path = _layout_pack_dir(layout_pack) / "visual.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _layout_pack_dir(layout_pack: str) -> Path:
    return Path(__file__).with_name("layouts") / layout_pack


def _validate_layout(data: dict[str, Any], config: ScenarioConfig) -> LoadedLayout:
    for key in ("id", "name", "floors", "survivors"):
        if key not in data:
            raise ValueError(f"Layout is missing required field: {key}")
    floors = data["floors"]
    survivors = data["survivors"]
    if not isinstance(floors, dict) or not floors:
        raise ValueError("Layout floors must be a non-empty object.")
    if not isinstance(survivors, dict):
        raise ValueError("Layout survivors must be an object.")

    active_floors = list(config.active_floors or [])
    room_to_floor: dict[str, str] = {}
    blocked_paths: dict[str, dict[str, Any]] = {}
    for floor_id in active_floors:
        if floor_id not in floors:
            raise ValueError(f"Active floor '{floor_id}' is not present in layout.")
        floor = floors[floor_id]
        rooms = floor.get("rooms")
        if not isinstance(rooms, dict) or not rooms:
            raise ValueError(f"Floor '{floor_id}' must define rooms.")
        for room_name, room in rooms.items():
            if room_name in room_to_floor:
                raise ValueError(f"Room '{room_name}' appears on multiple floors.")
            if "connects_to" not in room:
                raise ValueError(f"Room '{room_name}' is missing connects_to.")
            room_to_floor[room_name] = floor_id
            if "blocked_by" in room:
                blocked_paths[room_name] = dict(room["blocked_by"])

    for room_name, floor_id in room_to_floor.items():
        room = floors[floor_id]["rooms"][room_name]
        for target in room.get("connects_to", []):
            if target not in room_to_floor:
                raise ValueError(f"Room '{room_name}' connects to unknown room '{target}'.")

    for survivor_id, survivor in survivors.items():
        if "location" not in survivor:
            raise ValueError(f"Survivor '{survivor_id}' is missing location.")
        if survivor["location"] not in room_to_floor:
            raise ValueError(f"Survivor '{survivor_id}' is in unknown room '{survivor['location']}'.")

    return LoadedLayout(
        layout_id=str(data["id"]),
        name=str(data["name"]),
        floors={floor_id: floors[floor_id] for floor_id in active_floors},
        survivors=survivors,
        room_to_floor=room_to_floor,
        blocked_paths=blocked_paths,
    )
