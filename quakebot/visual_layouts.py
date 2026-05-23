"""Visual-only pixel layout helpers for the Streamlit replay UI."""

from __future__ import annotations

from dataclasses import dataclass

from .scenario import load_visual_layout


@dataclass(frozen=True)
class RoomRegion:
    name: str
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass(frozen=True)
class FloorLayout:
    name: str
    width: int
    height: int
    rooms: dict[str, RoomRegion]
    doors: tuple[tuple[int, int], ...]
    stairs: tuple[tuple[int, int], ...]
    rubble: dict[str, tuple[int, int]]
    items: dict[str, tuple[int, int]]


def load_floor_layouts(layout_pack: str = "default") -> dict[str, FloorLayout]:
    data = load_visual_layout(layout_pack)
    layouts: dict[str, FloorLayout] = {}
    for floor_name, floor in data["floors"].items():
        layouts[floor_name] = FloorLayout(
            name=floor_name,
            width=int(floor["width"]),
            height=int(floor["height"]),
            rooms={
                room_name: RoomRegion(
                    room_name,
                    int(region["x"]),
                    int(region["y"]),
                    int(region["width"]),
                    int(region["height"]),
                )
                for room_name, region in floor["rooms"].items()
            },
            doors=tuple(tuple(point) for point in floor.get("doors", [])),  # type: ignore[arg-type]
            stairs=tuple(tuple(point) for point in floor.get("stairs", [])),  # type: ignore[arg-type]
            rubble={room: tuple(point) for room, point in floor.get("rubble", {}).items()},  # type: ignore[arg-type]
            items={item: tuple(point) for item, point in floor.get("items", {}).items()},  # type: ignore[arg-type]
        )
    return layouts


FLOOR_LAYOUTS = load_floor_layouts()
FLOOR_NAMES = tuple(FLOOR_LAYOUTS)
