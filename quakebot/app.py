"""Streamlit visual replay for QuakeBot."""

from __future__ import annotations

import json
import os
import time
from html import escape
from typing import Any

from quakebot.agents import MockAgent, OllamaAgent, OpenAIAgent
from quakebot.scenario import ScenarioConfig
from quakebot.visual_layouts import FLOOR_LAYOUTS, FLOOR_NAMES, FloorLayout

try:
    from .replay import run_episode_recording, snapshots_to_dicts
except ImportError:  # Streamlit runs this file as a script.
    from quakebot.replay import run_episode_recording, snapshots_to_dicts


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="QuakeBot Visual Demo", layout="wide")
    _inject_css(st)
    st.markdown(
        """
        <div class="hero">
          <div>
            <div class="eyebrow">Symbolic Disaster-Response Harness</div>
            <h1>QuakeBot Visual Rescue Replay</h1>
          </div>
          <div class="hero-note">Structured observations → validated actions → environment-owned state</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    config = _agent_sidebar(st)
    if "replay_config" not in st.session_state:
        st.session_state.replay_config = {"agent_kind": "mock", "model": "", "host": "", "api_key": "", "max_steps": 100}
    if "snapshots" not in st.session_state:
        st.session_state.snapshots = _build_snapshots(st.session_state.replay_config)
        st.session_state.step_index = 0

    if config["run_clicked"] or config["reset_clicked"]:
        st.session_state.replay_config = config
        st.session_state.snapshots = _build_snapshots(config)
        st.session_state.step_index = 0

    snapshots = st.session_state.snapshots
    max_index = len(snapshots) - 1
    if "step_index" not in st.session_state:
        st.session_state.step_index = 0
    st.session_state.step_index = max(0, min(st.session_state.step_index, max_index))

    controls = st.columns([1, 1, 1, 1, 3])
    with controls[0]:
        if st.button("Previous", use_container_width=True):
            st.session_state.step_index = max(0, st.session_state.step_index - 1)
    with controls[1]:
        if st.button("Next", use_container_width=True):
            st.session_state.step_index = min(max_index, st.session_state.step_index + 1)
    with controls[2]:
        if st.button("Reset", use_container_width=True):
            st.session_state.step_index = 0
    with controls[3]:
        if st.button("End", use_container_width=True):
            st.session_state.step_index = max_index
    with controls[4]:
        autoplay = st.toggle("Auto-play", value=False)

    snapshot = snapshots[st.session_state.step_index]
    st.progress(snapshot["step"] / max(snapshots[-1]["step"], 1), text=f"Step {snapshot['step']} of {snapshots[-1]['step']}")
    render_overview(st, snapshot, snapshots[-1])

    left, right = st.columns([2.2, 1])
    with left:
        render_building_map(st, snapshot)
        log_tab, transcript_tab, data_tab = st.tabs(["Mission Log", "Step Transcript", "Snapshot Data"])
        with log_tab:
            render_mission_log(st, snapshot)
        with transcript_tab:
            render_full_transcript(st, snapshots, st.session_state.step_index)
        with data_tab:
            render_snapshot_data(st, snapshot)
    with right:
        render_robot_status(st, snapshot)
        render_action_panel(st, snapshot)
        render_survivor_cards(st, snapshot)

    if autoplay and st.session_state.step_index < max_index:
        time.sleep(0.8)
        st.session_state.step_index += 1
        st.rerun()


def render_overview(st: Any, snapshot: dict[str, Any], final_snapshot: dict[str, Any]) -> None:
    accounting = snapshot.get("mission_accounting", {})
    survivors = snapshot["all_survivors"].values()
    evacuated = sum(1 for survivor in survivors if survivor["accounting_status"] == "evacuated")
    awaiting = sum(1 for survivor in snapshot["all_survivors"].values() if survivor["accounting_status"] == "awaiting_specialised_extraction")
    unaccounted = len(accounting.get("unaccounted", []))
    battery_class = "ok" if snapshot["battery"] > 35 else "warn" if snapshot["battery"] > 15 else "danger"
    finish_class = "ok" if accounting.get("mission_can_finish") else "warn"
    cards = [
        ("Step", f"{snapshot['step']} / {final_snapshot['step']}", "ok"),
        ("Score", str(snapshot["score"]), "ok"),
        ("Battery", f"{snapshot['battery']}%", battery_class),
        ("Evacuated", str(evacuated), "ok"),
        ("Awaiting Extraction", str(awaiting), "warn" if awaiting else "ok"),
        ("Unaccounted", str(unaccounted), "danger" if unaccounted else "ok"),
        ("Can Finish", "Yes" if accounting.get("mission_can_finish") else "No", finish_class),
    ]
    html = ["<div class='overview-grid'>"]
    for label, value, status in cards:
        html.append(
            f"<div class='metric-card {status}'><div class='metric-label'>{escape(label)}</div>"
            f"<div class='metric-value'>{escape(value)}</div></div>"
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_building_map(st: Any, snapshot: dict[str, Any]) -> None:
    st.subheader("Pixel Rescue Map")
    current_floor = snapshot["floor_name"]
    floor_name = st.radio(
        "Floor",
        FLOOR_NAMES,
        index=FLOOR_NAMES.index(current_floor) if current_floor in FLOOR_NAMES else 0,
        horizontal=True,
        key=f"floor-selector-{snapshot['step']}",
    )
    st.markdown(
        """
        <div class="legend">
          <span><i class="legend-dot robot-dot"></i>QuakeBot</span>
          <span><i class="legend-dot survivor-dot"></i>Survivor</span>
          <span><i class="legend-dot hazard-dot"></i>Hazard</span>
          <span><i class="legend-dot blocked-dot"></i>Blocked</span>
          <span><i class="legend-dot done-dot"></i>Evacuated</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(render_floor_map(snapshot, floor_name), unsafe_allow_html=True)
    render_floor_summaries(st, snapshot, floor_name)


def render_floor_map(snapshot: dict[str, Any], floor_name: str) -> str:
    layout = FLOOR_LAYOUTS[floor_name]
    room_for_tile = _room_lookup(layout)
    tile_overlays = _tile_overlays(snapshot, layout)
    cells = []
    for y in range(layout.height):
        for x in range(layout.width):
            room = room_for_tile.get((x, y))
            tile_type = "wall"
            title = "wall"
            if room:
                tile_type = "floor"
                title = room
            if (x, y) in layout.doors:
                tile_type = "door"
                title = f"door near {room or 'corridor'}"
            if (x, y) in layout.stairs:
                tile_type = "stairs"
                title = f"stairs on {floor_name}"
            overlay = tile_overlays.get((x, y), "")
            hazard_room = bool(room and room in snapshot["hazard_states"])
            blocked_room = bool(room and room in snapshot["rubble_states"] and snapshot["rubble_states"][room] != "removed")
            classes = ["pixel-tile", f"tile-{tile_type}"]
            if hazard_room:
                classes.append("tile-hazard")
            if blocked_room:
                classes.append("tile-blocked")
            cells.append(
                f"<div class='{' '.join(classes)}' title='{escape(title)}' "
                f"style='grid-column:{x + 1};grid-row:{y + 1};'>{overlay}</div>"
            )

    labels = [
        (
            f"<div class='room-label' style='grid-column:{region.x + 1} / span {region.width};"
            f"grid-row:{region.y + 1};'>{escape(room_name)}</div>"
        )
        for room_name, region in layout.rooms.items()
    ]
    return (
        f"<div class='pixel-map-wrap'><div class='pixel-map-title'>{escape(floor_name)}</div>"
        f"<div class='pixel-map' style='grid-template-columns:repeat({layout.width}, 26px);"
        f"grid-template-rows:repeat({layout.height}, 26px);'>"
        + "".join(cells)
        + "".join(labels)
        + "</div></div>"
    )


def render_floor_summaries(st: Any, snapshot: dict[str, Any], selected_floor: str) -> None:
    summaries = []
    for floor_name in FLOOR_NAMES:
        rooms = [
            room
            for room, state in snapshot["room_states"].items()
            if state["floor_name"] == floor_name
        ]
        survivors = [
            sid
            for sid, survivor in snapshot["all_survivors"].items()
            if snapshot["room_states"].get(survivor["location"], {}).get("floor_name") == floor_name
            and survivor["accounting_status"] != "evacuated"
        ]
        hazards = [room for room in rooms if room in snapshot["hazard_states"]]
        robot = " robot" if snapshot["floor_name"] == floor_name else ""
        selected = " selected" if selected_floor == floor_name else ""
        summaries.append(
            f"<div class='floor-summary{selected}{robot}'><strong>{escape(floor_name)}</strong>"
            f"<span>{len(survivors)} active survivor(s)</span><span>{len(hazards)} hazard room(s)</span></div>"
        )
    st.markdown("<div class='floor-summary-row'>" + "".join(summaries) + "</div>", unsafe_allow_html=True)


def render_robot_status(st: Any, snapshot: dict[str, Any]) -> None:
    st.subheader("Robot Status")
    carrying = snapshot["carrying_survivor"] or "None"
    st.markdown(
        f"""
        <div class="side-panel">
          <div class="status-row"><span>Location</span><strong>{escape(snapshot['robot_location'])}</strong></div>
          <div class="status-row"><span>Floor</span><strong>{escape(snapshot['floor_name'])}</strong></div>
          <div class="status-row"><span>Battery</span><strong>{snapshot['battery']}%</strong></div>
          <div class="status-row"><span>Inventory</span><strong>{escape(', '.join(snapshot['inventory']) or 'Empty')}</strong></div>
          <div class="status-row"><span>Carrying</span><strong>{escape(carrying)}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    evacuated = sum(1 for survivor in snapshot["all_survivors"].values() if survivor["evacuated"])
    discovered = sum(1 for survivor in snapshot["all_survivors"].values() if survivor["discovered"])
    st.caption(f"Mission progress: {discovered} discovered, {evacuated} evacuated")
    accounting = snapshot.get("mission_accounting", {})
    if accounting:
        render_accounting_panel(st, accounting)
    if snapshot["recommended_next_actions"]:
        st.write("**Recommended next actions:**")
        st.code(json.dumps(snapshot["recommended_next_actions"], indent=2), language="json")


def render_action_panel(st: Any, snapshot: dict[str, Any]) -> None:
    st.subheader("Current Action")
    status = "accepted" if snapshot["action_ok"] else "rejected"
    st.markdown(
        f"<div class='action-card {status}'><div class='action-title'>{escape(snapshot['action_description'])}</div>"
        f"<div class='action-result'>{escape(snapshot['action_result'])}</div></div>",
        unsafe_allow_html=True,
    )
    st.code(json.dumps(snapshot["action"], indent=2) if snapshot["action"] else "Initial state", language="json")


def render_survivor_cards(st: Any, snapshot: dict[str, Any]) -> None:
    st.subheader("Survivors")
    for survivor in snapshot["all_survivors"].values():
        expanded = survivor["discovered"] and survivor["accounting_status"] not in {"evacuated", "inaccessible_confirmed"}
        label = f"{survivor['id']} · {survivor['accounting_status']} · {survivor['priority']}"
        with st.expander(label, expanded=expanded):
            st.markdown(_survivor_card(survivor), unsafe_allow_html=True)


def render_mission_log(st: Any, snapshot: dict[str, Any]) -> None:
    for event in snapshot["dialogue_event_log"][-12:]:
        st.markdown(f"<div class='log-line'>{escape(event)}</div>", unsafe_allow_html=True)


def render_full_transcript(st: Any, snapshots: list[dict[str, Any]], current_index: int) -> None:
    st.subheader("Full Step Transcript")
    current_only = st.toggle("Show transcript up to current step", value=True)
    visible = snapshots[: current_index + 1] if current_only else snapshots
    transcript = "\n\n".join(snapshot["transcript_text"] for snapshot in visible if snapshot["step"] > 0)
    st.text_area("Terminal-style episode trace", transcript, height=420, disabled=True)


def render_snapshot_data(st: Any, snapshot: dict[str, Any]) -> None:
    compact = {
        "mission_accounting": snapshot.get("mission_accounting", {}),
        "recommended_next_actions": snapshot.get("recommended_next_actions", []),
        "blocked_paths": snapshot.get("blocked_paths", {}),
        "hazard_states": snapshot.get("hazard_states", {}),
    }
    st.code(json.dumps(compact, indent=2), language="json")


def render_accounting_panel(st: Any, accounting: dict[str, Any]) -> None:
    statuses = accounting.get("accounting_statuses", {})
    chips = "".join(_status_chip(sid, status) for sid, status in statuses.items())
    unaccounted = ", ".join(accounting.get("unaccounted", [])) or "None"
    st.markdown(
        f"""
        <div class="accounting-panel">
          <div class="panel-title">Mission Accounting</div>
          <div class="chip-row">{chips}</div>
          <div class="small-muted">Unaccounted: {escape(unaccounted)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _agent_sidebar(st: Any) -> dict[str, Any]:
    with st.sidebar:
        st.header("Episode Source")
        agent_kind = st.selectbox(
            "Agent",
            ["mock", "ollama-cloud", "ollama-local", "openai"],
            format_func={
                "mock": "MockAgent",
                "ollama-cloud": "Ollama Cloud",
                "ollama-local": "Local Ollama",
                "openai": "OpenAI-compatible",
            }.__getitem__,
        )
        default_model = {
            "mock": "",
            "ollama-cloud": os.getenv("OLLAMA_MODEL", "gpt-oss:20b"),
            "ollama-local": os.getenv("OLLAMA_MODEL", "llama3.1"),
            "openai": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        }[agent_kind]
        model = st.text_input("Model", value=default_model, disabled=agent_kind == "mock")
        survivor_count_mode = st.selectbox(
            "Survivor count mode",
            ["exact", "approximate"],
            format_func={"exact": "Exact known count", "approximate": "Approximate estimate"}.__getitem__,
        )
        default_host = "http://localhost:11434" if agent_kind == "ollama-local" else ""
        host = st.text_input("Host", value=os.getenv("OLLAMA_HOST", default_host), disabled=agent_kind != "ollama-local")
        api_key = ""
        if agent_kind == "ollama-cloud":
            api_key = st.text_input("OLLAMA_API_KEY", value=os.getenv("OLLAMA_API_KEY", ""), type="password")
        elif agent_kind == "openai":
            api_key = st.text_input("OPENAI_API_KEY", value=os.getenv("OPENAI_API_KEY", ""), type="password")
        random_events = st.checkbox("Seeded random events", value=False)
        seed = st.number_input("Random seed", min_value=0, max_value=999999, value=42, step=1, disabled=not random_events)
        max_steps = st.slider("Max replay steps", min_value=20, max_value=120, value=100, step=5)
        run_clicked = st.button("Generate Episode", type="primary", use_container_width=True)
        reset_clicked = st.button("Reset Replay", use_container_width=True)
        st.caption("LLM runs may take longer and can consume API credits. The UI records a replay first, then visualises it.")
    return {
        "agent_kind": agent_kind,
        "model": model,
        "host": host,
        "api_key": api_key,
        "max_steps": max_steps,
        "survivor_count_mode": survivor_count_mode,
        "random_events": random_events,
        "seed": int(seed),
        "run_clicked": run_clicked,
        "reset_clicked": reset_clicked,
    }


def _build_snapshots(config: dict[str, Any]) -> list[dict[str, Any]]:
    import streamlit as st

    agent = _make_agent(config)
    if isinstance(agent, (OllamaAgent, OpenAIAgent)) and not agent.available:
        st.warning("Selected agent is not available. Falling back to MockAgent.")
        agent = MockAgent(approximate=config["survivor_count_mode"] == "approximate")
    scenario = _scenario_config(config)
    with st.spinner("Recording episode..."):
        return snapshots_to_dicts(run_episode_recording(agent, config=scenario, max_steps=int(config["max_steps"])))


def _make_agent(config: dict[str, Any]) -> Any:
    kind = config["agent_kind"]
    if kind == "ollama-cloud":
        return OllamaAgent(model=config["model"] or None, api_key=config["api_key"] or None, cloud=True)
    if kind == "ollama-local":
        return OllamaAgent(model=config["model"] or None, host=config["host"] or None)
    if kind == "openai":
        return OpenAIAgent(model=config["model"] or "gpt-4.1-mini", api_key=config["api_key"] or None)
    return MockAgent(approximate=config.get("survivor_count_mode") == "approximate")


def _scenario_config(config: dict[str, Any]) -> ScenarioConfig:
    random_events = bool(config.get("random_events"))
    seed = int(config.get("seed", 7))
    if config.get("survivor_count_mode") != "approximate":
        return ScenarioConfig(random_events_enabled=random_events, seed=seed, max_steps=max(140, int(config.get("max_steps", 120))))
    return ScenarioConfig(
        survivor_count_mode="approximate",
        survivor_count=4,
        survivor_count_min=3,
        survivor_count_max=5,
        random_events_enabled=random_events,
        seed=seed,
        max_steps=max(160, int(config.get("max_steps", 120))),
    )


def _room_lookup(layout: FloorLayout) -> dict[tuple[int, int], str]:
    lookup: dict[tuple[int, int], str] = {}
    for room_name, region in layout.rooms.items():
        for y in range(region.y, region.y + region.height):
            for x in range(region.x, region.x + region.width):
                lookup[(x, y)] = room_name
    return lookup


def _tile_overlays(snapshot: dict[str, Any], layout: FloorLayout) -> dict[tuple[int, int], str]:
    overlays: dict[tuple[int, int], list[str]] = {}

    def add(room_name: str, sprite: str, *, offset: tuple[int, int] = (0, 0), title: str = "") -> None:
        region = layout.rooms.get(room_name)
        if not region:
            return
        x, y = region.center
        x += offset[0]
        y += offset[1]
        overlays.setdefault((x, y), []).append(f"<span title='{escape(title or sprite)}'>{sprite}</span>")

    robot_room = snapshot["robot_location"]
    carrying = snapshot["carrying_survivor"]
    add(robot_room, "QB" if not carrying else "QB+", title=f"QuakeBot{f' carrying {carrying}' if carrying else ''}")

    for sid, survivor in snapshot["all_survivors"].items():
        location = survivor["location"]
        if survivor["accounting_status"] == "evacuated":
            if layout.name == "Ground":
                add("Entrance", "EV", offset=(1, 1), title=f"{sid} evacuated")
            continue
        if snapshot["room_states"].get(location, {}).get("floor_name") == layout.name and survivor["discovered"]:
            sprite = "SV" if survivor["accounting_status"] != "awaiting_specialised_extraction" else "MED"
            add(location, sprite, offset=(1, 0), title=f"{sid}: {survivor['accounting_status']}")

    for room_name, hazards in snapshot["hazard_states"].items():
        if room_name in layout.rooms:
            hazard_text = ",".join(f"{key}={value}" for key, value in hazards.items())
            add(room_name, "HZ", offset=(-1, 1), title=hazard_text)

    for room_name, status in snapshot["rubble_states"].items():
        if status != "removed":
            position = layout.rubble.get(room_name)
            if position is None and room_name in layout.rooms:
                position = layout.rooms[room_name].center
            if position is not None:
                overlays.setdefault(position, []).append(f"<span title='rubble: {escape(status)}'>RB</span>")

    for item_name, position in layout.items.items():
        room_state = snapshot["room_states"].get(_room_for_item(layout, position), {})
        if item_name in room_state.get("items", []):
            overlays.setdefault(position, []).append(f"<span title='{escape(item_name)}'>+</span>")

    return {position: "<div class='sprite-stack'>" + "".join(items) + "</div>" for position, items in overlays.items()}


def _room_for_item(layout: FloorLayout, position: tuple[int, int]) -> str:
    lookup = _room_lookup(layout)
    return lookup.get(position, "")


def _survivor_card(survivor: dict[str, Any]) -> str:
    checks = ", ".join(survivor["checks_completed"]) or "None"
    name = survivor["name"] or "Unknown"
    status_class = _status_class(survivor["accounting_status"])
    return f"""
    <div class="survivor-card {status_class}">
      <div class="survivor-card-head">
        <strong>{escape(name)}</strong>
        {_status_chip(survivor["id"], survivor["accounting_status"])}
      </div>
      <div class="survivor-grid">
        <span>Location</span><strong>{escape(survivor["location"])}</strong>
        <span>Priority</span><strong>{escape(survivor["priority"])}</strong>
        <span>Breathing</span><strong>{escape(survivor["breathing_status"])}</strong>
        <span>Pulse</span><strong>{escape(survivor["pulse_status"])}</strong>
        <span>Bleeding</span><strong>{escape(survivor["bleeding"])}</strong>
        <span>Mobility</span><strong>{'Can walk' if survivor["can_walk"] else 'Cannot walk'}</strong>
        <span>Trapped</span><strong>{survivor["trapped"]}</strong>
        <span>Stabilised</span><strong>{survivor["stabilised"]}</strong>
      </div>
      <div class="checks">{escape(checks)}</div>
    </div>
    """


def _status_chip(label: str, status: str) -> str:
    return f"<span class='status-chip {_status_class(status)}'>{escape(label)}: {escape(status.replace('_', ' '))}</span>"


def _status_class(status: str) -> str:
    return {
        "evacuated": "status-ok",
        "awaiting_specialised_extraction": "status-warn",
        "inaccessible_confirmed": "status-warn",
        "directly_assessed": "status-info",
        "located": "status-info",
        "suspected": "status-warn",
        "unknown": "status-danger",
    }.get(status, "status-info")


def _inject_css(st: Any) -> None:
    st.markdown(
        """
        <style>
        :root {
            --qb-ink: #18212f;
            --qb-muted: #667085;
            --qb-border: #d8dee8;
            --qb-panel: #ffffff;
            --qb-bg: #f6f8fb;
            --qb-blue: #1f6feb;
            --qb-green: #168a4a;
            --qb-amber: #b7791f;
            --qb-red: #c2413a;
            --qb-cyan: #0e7490;
        }
        .block-container {
            padding-top: 1.1rem;
            padding-bottom: 2rem;
        }
        .hero {
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 18px;
            border: 1px solid var(--qb-border);
            border-radius: 8px;
            padding: 18px 20px;
            margin-bottom: 14px;
            background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
        }
        .hero h1 {
            margin: 0;
            font-size: 2rem;
            letter-spacing: 0;
            color: var(--qb-ink);
        }
        .eyebrow {
            color: var(--qb-cyan);
            font-size: 0.78rem;
            text-transform: uppercase;
            font-weight: 750;
            letter-spacing: 0.04rem;
            margin-bottom: 4px;
        }
        .hero-note {
            color: var(--qb-muted);
            font-size: 0.92rem;
            text-align: right;
            max-width: 360px;
        }
        .overview-grid {
            display: grid;
            grid-template-columns: repeat(7, minmax(0, 1fr));
            gap: 10px;
            margin: 12px 0 18px;
        }
        .metric-card {
            border: 1px solid var(--qb-border);
            border-left-width: 4px;
            border-radius: 8px;
            background: var(--qb-panel);
            padding: 10px 12px;
            min-height: 76px;
        }
        .metric-card.ok { border-left-color: var(--qb-green); }
        .metric-card.warn { border-left-color: var(--qb-amber); }
        .metric-card.danger { border-left-color: var(--qb-red); }
        .metric-label {
            color: var(--qb-muted);
            font-size: 0.76rem;
            font-weight: 650;
            text-transform: uppercase;
        }
        .metric-value {
            color: var(--qb-ink);
            font-size: 1.35rem;
            font-weight: 800;
            margin-top: 6px;
        }
        .legend {
            display: flex;
            flex-wrap: wrap;
            gap: 10px 16px;
            color: var(--qb-muted);
            font-size: 0.84rem;
            margin-bottom: 8px;
        }
        .legend span {
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .legend-dot {
            width: 9px;
            height: 9px;
            border-radius: 999px;
            display: inline-block;
        }
        .robot-dot { background: var(--qb-blue); }
        .survivor-dot { background: var(--qb-amber); }
        .hazard-dot { background: var(--qb-red); }
        .blocked-dot { background: #d97706; }
        .done-dot { background: var(--qb-green); }
        .pixel-map-wrap {
            border: 1px solid var(--qb-border);
            border-radius: 8px;
            background: #1f2937;
            padding: 12px;
            overflow-x: auto;
            margin-bottom: 12px;
            box-shadow: inset 0 0 0 3px #111827;
        }
        .pixel-map-title {
            color: #e5e7eb;
            font-weight: 850;
            text-transform: uppercase;
            letter-spacing: 0.04rem;
            margin-bottom: 10px;
            font-size: 0.84rem;
        }
        .pixel-map {
            display: grid;
            gap: 0;
            width: max-content;
            border: 4px solid #111827;
            background: #0f172a;
            image-rendering: pixelated;
        }
        .pixel-tile {
            width: 26px;
            height: 26px;
            box-sizing: border-box;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: "Courier New", monospace;
            font-size: 0.58rem;
            font-weight: 900;
            letter-spacing: 0;
            line-height: 1;
            border-right: 1px solid rgba(15, 23, 42, 0.22);
            border-bottom: 1px solid rgba(15, 23, 42, 0.22);
            color: #111827;
        }
        .tile-wall {
            background:
                linear-gradient(45deg, rgba(255,255,255,0.04) 25%, transparent 25% 50%, rgba(0,0,0,0.08) 50% 75%, transparent 75%),
                #334155;
        }
        .tile-floor {
            background:
                linear-gradient(90deg, rgba(255,255,255,0.18) 1px, transparent 1px),
                linear-gradient(0deg, rgba(0,0,0,0.08) 1px, transparent 1px),
                #cbd5e1;
            background-size: 13px 13px;
        }
        .tile-door {
            background: #a16207;
            box-shadow: inset 0 0 0 3px #78350f;
        }
        .tile-stairs {
            background: repeating-linear-gradient(0deg, #64748b 0 4px, #94a3b8 4px 8px);
        }
        .tile-hazard {
            background:
                repeating-linear-gradient(45deg, rgba(220, 38, 38, 0.65) 0 4px, rgba(254, 202, 202, 0.65) 4px 8px),
                #fecaca;
        }
        .tile-blocked {
            background:
                repeating-linear-gradient(135deg, #92400e 0 4px, #f59e0b 4px 8px),
                #f59e0b;
        }
        .room-label {
            align-self: start;
            justify-self: start;
            z-index: 2;
            margin: 2px;
            padding: 1px 3px;
            background: rgba(15, 23, 42, 0.72);
            color: #f8fafc;
            font-family: "Courier New", monospace;
            font-size: 0.52rem;
            font-weight: 800;
            pointer-events: none;
            max-width: calc(100% - 4px);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .sprite-stack {
            display: flex;
            flex-direction: column;
            gap: 1px;
            z-index: 3;
            align-items: center;
            justify-content: center;
        }
        .sprite-stack span {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 18px;
            min-height: 12px;
            padding: 1px 2px;
            border: 2px solid #111827;
            box-shadow: 2px 2px 0 rgba(17, 24, 39, 0.65);
            background: #f8fafc;
        }
        .sprite-stack span[title^="QuakeBot"] {
            background: #60a5fa;
            color: #0f172a;
        }
        .sprite-stack span[title*="survivor"] {
            background: #fbbf24;
        }
        .sprite-stack span[title*="awaiting"] {
            background: #fca5a5;
        }
        .sprite-stack span[title^="rubble"] {
            background: #92400e;
            color: #fef3c7;
        }
        .sprite-stack span[title*="hazard"],
        .sprite-stack span[title*="structural"],
        .sprite-stack span[title*="electrical"],
        .sprite-stack span[title*="gas"] {
            background: #ef4444;
            color: #fff;
        }
        .floor-summary-row {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 8px;
            margin-bottom: 12px;
        }
        .floor-summary {
            border: 1px solid var(--qb-border);
            border-left: 4px solid #94a3b8;
            border-radius: 8px;
            padding: 8px 10px;
            background: #ffffff;
            display: flex;
            flex-direction: column;
            gap: 2px;
            color: var(--qb-muted);
            font-size: 0.82rem;
        }
        .floor-summary.selected {
            border-left-color: var(--qb-blue);
        }
        .floor-summary.robot {
            background: #eff6ff;
        }
        .floor-summary strong {
            color: var(--qb-ink);
        }
        .side-panel, .accounting-panel, .action-card, .survivor-card {
            border: 1px solid var(--qb-border);
            border-radius: 8px;
            background: var(--qb-panel);
            padding: 12px;
            margin-bottom: 12px;
        }
        .status-row {
            display: flex;
            justify-content: space-between;
            gap: 14px;
            padding: 6px 0;
            border-bottom: 1px solid #eef1f5;
            font-size: 0.9rem;
        }
        .status-row:last-child { border-bottom: 0; }
        .status-row span, .small-muted {
            color: var(--qb-muted);
        }
        .panel-title {
            font-weight: 800;
            color: var(--qb-ink);
            margin-bottom: 8px;
        }
        .chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-bottom: 8px;
        }
        .status-chip {
            display: inline-flex;
            align-items: center;
            max-width: 100%;
            border-radius: 999px;
            border: 1px solid var(--qb-border);
            padding: 3px 8px;
            font-size: 0.76rem;
            font-weight: 700;
            overflow-wrap: anywhere;
        }
        .status-ok {
            border-color: rgba(22, 138, 74, 0.35);
            background: #ecfdf3;
            color: #146c43;
        }
        .status-warn {
            border-color: rgba(183, 121, 31, 0.35);
            background: #fffbeb;
            color: #8a5a12;
        }
        .status-danger {
            border-color: rgba(194, 65, 58, 0.35);
            background: #fff1f0;
            color: #a5352f;
        }
        .status-info {
            border-color: rgba(14, 116, 144, 0.35);
            background: #ecfeff;
            color: #0e6175;
        }
        .action-card {
            border-left: 4px solid var(--qb-green);
        }
        .action-card.rejected {
            border-left-color: var(--qb-red);
            background: #fff7f7;
        }
        .action-title {
            color: var(--qb-ink);
            font-weight: 800;
            margin-bottom: 6px;
        }
        .action-result {
            color: var(--qb-muted);
            font-size: 0.9rem;
            line-height: 1.35;
        }
        .survivor-card {
            margin-bottom: 0;
        }
        .survivor-card-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            margin-bottom: 10px;
        }
        .survivor-grid {
            display: grid;
            grid-template-columns: minmax(76px, 0.8fr) minmax(0, 1.2fr);
            gap: 5px 10px;
            font-size: 0.86rem;
        }
        .survivor-grid span {
            color: var(--qb-muted);
        }
        .checks {
            margin-top: 10px;
            color: var(--qb-muted);
            font-size: 0.78rem;
            line-height: 1.35;
        }
        .log-line {
            border-left: 3px solid var(--qb-blue);
            background: #f8fafc;
            padding: 8px 10px;
            margin-bottom: 7px;
            border-radius: 0 8px 8px 0;
            color: var(--qb-ink);
            font-size: 0.9rem;
        }
        div[data-testid="stExpander"] {
            border: 1px solid var(--qb-border);
            border-radius: 8px;
        }
        @media (max-width: 980px) {
            .overview-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .hero {
                align-items: flex-start;
                flex-direction: column;
            }
            .hero-note {
                text-align: left;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
