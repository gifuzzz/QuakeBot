"""Minimal FastAPI server exposing QuakeBot replay episodes."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from quakebot.agents import MockAgent, OllamaAgent, OpenAIAgent, RecommendedActionAgent
from quakebot.replay import EpisodeStep, run_episode_recording, snapshots_to_dicts, stream_episode_recording
from quakebot.scenario import LoadedLayout, ScenarioConfig, load_layout, load_visual_layout


class RoomLayoutRequest(BaseModel):
    name: str
    connects_to: list[str] = Field(default_factory=list)
    hazards: dict[str, Any] = Field(default_factory=dict)
    objects: list[str] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    sounds: list[str] = Field(default_factory=list)
    vibration_cues: list[str] = Field(default_factory=list)
    survivor_cues: list[str] = Field(default_factory=list)
    blocked_by: dict[str, Any] | None = None


class FloorLayoutRequest(BaseModel):
    id: str
    name: str
    level: int = 0
    rooms: list[RoomLayoutRequest] = Field(default_factory=list)


class SurvivorLayoutRequest(BaseModel):
    id: str
    name: str | None = None
    location: str
    trapped: bool = False
    reachable: bool | None = None
    conscious: bool = True
    responsive: bool = True
    breathing_status: str = "normal"
    pulse_status: str = "normal"
    bleeding: str = "none"
    pain_level: int = 0
    can_walk: bool = True
    suspected_injuries: list[str] = Field(default_factory=list)
    priority: str = "medium"


class CustomLayoutRequest(BaseModel):
    id: str = "frontend_custom"
    name: str = "Frontend Custom Scenario"
    floors: list[FloorLayoutRequest] = Field(default_factory=list)
    survivors: list[SurvivorLayoutRequest] = Field(default_factory=list)


class EpisodeStartRequest(BaseModel):
    scenario: str | None = None
    agent_type: str = "mock"
    model: str | None = None
    api_key: str | None = None
    active_floors: list[str] = Field(default_factory=lambda: ["ground", "floor_1", "basement"])
    survivor_count_mode: str = "exact"
    survivor_location_mode: str = "known"
    survivor_count: int | None = 3
    survivor_count_min: int | None = None
    survivor_count_max: int | None = None
    seed: int = 7
    random_events_enabled: bool = False
    max_steps: int = 120
    custom_layout: CustomLayoutRequest | None = None
    save_json: bool = False


@dataclass
class EpisodeState:
    episode_id: str
    config: ScenarioConfig
    snapshots: list[EpisodeStep]
    cursor: int = 0


app = FastAPI(title="QuakeBot API", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_episodes: dict[str, EpisodeState] = {}


def _next_episode_snapshot(iterator: Any) -> tuple[bool, EpisodeStep | None]:
    try:
        return False, next(iterator)
    except StopIteration:
        return True, None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "quakebot-api"}


@app.get("/replays")
def list_replays() -> dict[str, Any]:
    import os
    import glob
    if not os.path.exists("simulation_recordings"):
        os.makedirs("simulation_recordings")
    files = glob.glob("simulation_recordings/*.json")
    files.sort(key=os.path.getmtime, reverse=True)
    return {"replays": [os.path.basename(f) for f in files]}


@app.get("/replays/{filename}")
def get_replay(filename: str) -> list[dict[str, Any]]:
    import os
    import json
    if not filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Invalid replay filename.")
    filepath = os.path.join("simulation_recordings", filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Replay not found.")
    with open(filepath, "r") as f:
        return json.load(f)


@app.get("/layouts")
def layouts() -> dict[str, Any]:
    config = ScenarioConfig()
    layout = load_layout(config)
    return {
        "scenario": asdict(config),
        "semantic": {
            "id": layout.layout_id,
            "name": layout.name,
            "floors": layout.floors,
            "survivors": layout.survivors,
            "room_to_floor": layout.room_to_floor,
            "blocked_paths": layout.blocked_paths,
        },
        "visual": load_visual_layout(config.layout_pack),
    }


@app.post("/episodes/start")
def start_episode(request: EpisodeStartRequest) -> dict[str, Any]:
    config = _config_from_request(request)
    layout = _layout_from_request(request)
    if request.agent_type == "ollama":
        agent = OllamaAgent(model=request.model, api_key=request.api_key)
        if not agent.available:
            raise HTTPException(status_code=503, detail="Ollama agent is not available.")
    elif request.agent_type == "ollama-cloud":
        agent = OllamaAgent(model=request.model, api_key=request.api_key, cloud=True)
        if not agent.available:
            raise HTTPException(status_code=503, detail="Ollama Cloud agent is not available.")
    elif request.agent_type == "openai":
        agent = OpenAIAgent(model=request.model or "gpt-4o", api_key=request.api_key)
        if not agent.available:
            raise HTTPException(status_code=503, detail="OpenAI API key is missing or invalid.")
    elif request.scenario in {"generated_small", "severe_risk_bleeding_survivor"} and request.agent_type == "mock":
        if request.scenario == "generated_small":
            agent = RecommendedActionAgent()
        else:
            from quakebot.demo import SevereRiskDemoAgent
            agent = SevereRiskDemoAgent()
    elif layout is not None:
        agent = RecommendedActionAgent()
    else:
        agent = MockAgent(approximate=config.survivor_count_mode == "approximate")
    snapshots = run_episode_recording(agent, config=config, layout=layout, max_steps=config.max_steps)
    episode_id = uuid4().hex
    
    if request.save_json:
        import json
        import os
        from datetime import datetime
        if not os.path.exists("simulation_recordings"):
            os.makedirs("simulation_recordings")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}-{episode_id}.json"
        filepath = os.path.join("simulation_recordings", filename)
        with open(filepath, "w") as f:
            json.dump(snapshots_to_dicts(snapshots), f, indent=2)
            
    _episodes[episode_id] = EpisodeState(episode_id=episode_id, config=config, snapshots=snapshots)
    return {
        "episode_id": episode_id,
        "config": asdict(config),
        "snapshot_count": len(snapshots),
        "final_score": snapshots[-1].score if snapshots else 0,
        "final_step": snapshots[-1].step if snapshots else 0,
    }


@app.websocket("/episodes/stream")
async def stream_episode(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        data = await websocket.receive_text()
        request = EpisodeStartRequest.model_validate_json(data)
        config = _config_from_request(request)
        layout = _layout_from_request(request)
        if request.agent_type == "ollama":
            agent = OllamaAgent(model=request.model, api_key=request.api_key)
            if not agent.available:
                await websocket.send_json({"error": "Ollama agent is not available."})
                await websocket.close()
                return
        elif request.agent_type == "ollama-cloud":
            agent = OllamaAgent(model=request.model, api_key=request.api_key, cloud=True)
            if not agent.available:
                await websocket.send_json({"error": "Ollama Cloud agent is not available."})
                await websocket.close()
                return
        elif request.agent_type == "openai":
            agent = OpenAIAgent(model=request.model or "gpt-4o", api_key=request.api_key)
            if not agent.available:
                await websocket.send_json({"error": "OpenAI API key is missing or invalid."})
                await websocket.close()
                return
        elif request.scenario in {"generated_small", "severe_risk_bleeding_survivor"} and request.agent_type == "mock":
            if request.scenario == "generated_small":
                agent = RecommendedActionAgent()
            else:
                from quakebot.demo import SevereRiskDemoAgent
                agent = SevereRiskDemoAgent()
        elif layout is not None:
            agent = RecommendedActionAgent()
        else:
            agent = MockAgent(approximate=config.survivor_count_mode == "approximate")
            
        snapshots = []
        iterator = iter(stream_episode_recording(agent, config=config, layout=layout, max_steps=config.max_steps))
        while True:
            done, snapshot = await asyncio.to_thread(_next_episode_snapshot, iterator)
            if done or snapshot is None:
                break
            snapshots.append(snapshot)
            await websocket.send_json(snapshot.to_dict())
            
        if request.save_json:
            import json
            import os
            from datetime import datetime
            if not os.path.exists("simulation_recordings"):
                os.makedirs("simulation_recordings")
            episode_id = uuid4().hex
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}-{episode_id}.json"
            filepath = os.path.join("simulation_recordings", filename)
            with open(filepath, "w") as f:
                json.dump(snapshots_to_dicts(snapshots), f, indent=2)
            
        await websocket.close()
    except HTTPException as exc:
        await websocket.send_json({"error": str(exc.detail)})
        await websocket.close()
    except WebSocketDisconnect:
        pass


@app.get("/episodes/{episode_id}/snapshots")
def get_snapshots(episode_id: str) -> dict[str, Any]:
    episode = _episode(episode_id)
    return {"episode_id": episode_id, "snapshots": snapshots_to_dicts(episode.snapshots), "cursor": episode.cursor}


@app.get("/episodes/{episode_id}/snapshot/{step}")
def get_snapshot(episode_id: str, step: int) -> dict[str, Any]:
    episode = _episode(episode_id)
    return episode.snapshots[_step_index(episode, step)].to_dict()


@app.post("/episodes/{episode_id}/step")
def step_episode(episode_id: str) -> dict[str, Any]:
    episode = _episode(episode_id)
    episode.cursor = min(episode.cursor + 1, len(episode.snapshots) - 1)
    return {"episode_id": episode_id, "cursor": episode.cursor, "snapshot": episode.snapshots[episode.cursor].to_dict()}


@app.post("/episodes/{episode_id}/reset")
def reset_episode(episode_id: str) -> dict[str, Any]:
    episode = _episode(episode_id)
    episode.cursor = 0
    return {"episode_id": episode_id, "cursor": 0, "snapshot": episode.snapshots[0].to_dict()}


def _config_from_request(request: EpisodeStartRequest) -> ScenarioConfig:
    if request.scenario:
        from quakebot.demo import _scenario_config
        return _scenario_config(
            approximate=request.survivor_count_mode == "approximate",
            random_events=request.random_events_enabled,
            seed=request.seed,
            scenario=request.scenario,
        )

    active_floors = [floor.id for floor in request.custom_layout.floors] if request.custom_layout else request.active_floors
    survivor_count = len(request.custom_layout.survivors) if request.custom_layout else request.survivor_count
    if request.survivor_count_mode == "approximate":
        return ScenarioConfig(
            active_floors=active_floors,
            survivor_count_mode="approximate",
            survivor_location_mode=request.survivor_location_mode,
            survivor_count=survivor_count,
            survivor_count_min=request.survivor_count_min if request.survivor_count_min is not None else 3,
            survivor_count_max=request.survivor_count_max if request.survivor_count_max is not None else 5,
            seed=request.seed,
            random_events_enabled=request.random_events_enabled,
            max_steps=request.max_steps,
        )
    return ScenarioConfig(
        active_floors=active_floors,
        survivor_count_mode="exact",
        survivor_location_mode=request.survivor_location_mode,
        survivor_count=survivor_count if survivor_count is not None else 3,
        seed=request.seed,
        random_events_enabled=request.random_events_enabled,
        max_steps=request.max_steps,
    )


def _layout_from_request(request: EpisodeStartRequest) -> LoadedLayout | None:
    if request.scenario == "generated_small":
        from quakebot.demo import _generated_small_layout
        return _generated_small_layout()
    if request.scenario == "severe_risk_bleeding_survivor":
        from quakebot.demo import _severe_risk_bleeding_survivor_layout
        return _severe_risk_bleeding_survivor_layout()

    custom = request.custom_layout
    if custom is None:
        return None
    if not custom.floors:
        raise HTTPException(status_code=422, detail="Custom layout requires at least one floor.")

    floors: dict[str, Any] = {}
    room_to_floor: dict[str, str] = {}
    blocked_paths: dict[str, dict[str, Any]] = {}
    for floor in custom.floors:
        if not floor.rooms:
            raise HTTPException(status_code=422, detail=f"Floor '{floor.id}' requires at least one room.")
        rooms: dict[str, Any] = {}
        for room in floor.rooms:
            if room.name in room_to_floor:
                raise HTTPException(status_code=422, detail=f"Room '{room.name}' appears more than once.")
            room_to_floor[room.name] = floor.id
            data: dict[str, Any] = {"connects_to": list(dict.fromkeys(room.connects_to))}
            if room.hazards:
                data["hazards"] = dict(room.hazards)
            if room.objects:
                data["objects"] = list(room.objects)
            if room.items:
                data["items"] = list(room.items)
            if room.sounds:
                data["sounds"] = list(room.sounds)
            if room.vibration_cues:
                data["vibration_cues"] = list(room.vibration_cues)
            if room.survivor_cues:
                data["survivor_cues"] = list(room.survivor_cues)
            if room.blocked_by:
                data["blocked_by"] = dict(room.blocked_by)
                blocked_paths[room.name] = dict(room.blocked_by)
            rooms[room.name] = data
        floors[floor.id] = {"name": floor.name, "level": floor.level, "rooms": rooms}

    for floor in floors.values():
        for room_name, room in floor["rooms"].items():
            unknown_targets = [target for target in room["connects_to"] if target not in room_to_floor]
            if unknown_targets:
                raise HTTPException(
                    status_code=422,
                    detail=f"Room '{room_name}' connects to unknown room(s): {', '.join(unknown_targets)}.",
                )

    survivors: dict[str, Any] = {}
    for survivor in custom.survivors:
        if survivor.location not in room_to_floor:
            raise HTTPException(status_code=422, detail=f"Survivor '{survivor.id}' location does not exist.")
        survivors[survivor.id] = {
            "name": survivor.name,
            "location": survivor.location,
            "trapped": survivor.trapped,
            "reachable": survivor.reachable if survivor.reachable is not None else not survivor.trapped,
            "conscious": survivor.conscious,
            "responsive": survivor.responsive,
            "breathing_status": survivor.breathing_status,
            "pulse_status": survivor.pulse_status,
            "bleeding": survivor.bleeding,
            "pain_level": survivor.pain_level,
            "can_walk": survivor.can_walk,
            "suspected_injuries": list(survivor.suspected_injuries),
            "priority": survivor.priority,
        }

    return LoadedLayout(
        layout_id=custom.id,
        name=custom.name,
        floors=floors,
        survivors=survivors,
        room_to_floor=room_to_floor,
        blocked_paths=blocked_paths,
    )


def _episode(episode_id: str) -> EpisodeState:
    try:
        return _episodes[episode_id]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Episode not found.") from exc


def _step_index(episode: EpisodeState, step: int) -> int:
    for index, snapshot in enumerate(episode.snapshots):
        if snapshot.step == step:
            return index
    raise HTTPException(status_code=404, detail="Snapshot step not found.")
