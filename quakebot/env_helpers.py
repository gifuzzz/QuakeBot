from typing import Any

def highest_structural_risk_room(rooms: dict[str, Any]) -> str | None:
    high_risk = [name for name, room in rooms.items() if room.conditions.get("structural_risk") == "high"]
    if high_risk:
        return high_risk[0]
    return None

def active_survivor_room(survivors: dict[str, Any]) -> str | None:
    active = [s.location for s in survivors.values() if not s.accounted_for() and not s.evacuated]
    if active:
        return active[0]
    return None

def basement_like_room(rooms: dict[str, Any]) -> str | None:
    return next((r for r in rooms if "basement" in r.lower()), None)
