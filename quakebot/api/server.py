"""Minimal FastAPI server exposing QuakeBot replay episodes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from quakebot.agents import MockAgent, OllamaAgent
from quakebot.replay import EpisodeStep, run_episode_recording, snapshots_to_dicts
from quakebot.scenario import ScenarioConfig, load_layout, load_visual_layout


class EpisodeStartRequest(BaseModel):
    active_floors: list[str] = Field(default_factory=lambda: ["ground", "floor_1", "basement"])
    survivor_count_mode: str = "exact"
    survivor_count: int | None = 3
    survivor_count_min: int | None = None
    survivor_count_max: int | None = None
    seed: int = 7
    random_events_enabled: bool = False
    max_steps: int = 120


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "quakebot-api"}


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
    agent = MockAgent(approximate=config.survivor_count_mode == "approximate")
    snapshots = run_episode_recording(agent, config=config, max_steps=config.max_steps)
    episode_id = uuid4().hex
    _episodes[episode_id] = EpisodeState(episode_id=episode_id, config=config, snapshots=snapshots)
    return {
        "episode_id": episode_id,
        "config": asdict(config),
        "snapshot_count": len(snapshots),
        "final_score": snapshots[-1].score if snapshots else 0,
        "final_step": snapshots[-1].step if snapshots else 0,
    }


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
    if request.survivor_count_mode == "approximate":
        return ScenarioConfig(
            active_floors=request.active_floors,
            survivor_count_mode="approximate",
            survivor_count=request.survivor_count,
            survivor_count_min=request.survivor_count_min if request.survivor_count_min is not None else 3,
            survivor_count_max=request.survivor_count_max if request.survivor_count_max is not None else 5,
            seed=request.seed,
            random_events_enabled=request.random_events_enabled,
            max_steps=request.max_steps,
        )
    return ScenarioConfig(
        active_floors=request.active_floors,
        survivor_count_mode="exact",
        survivor_count=request.survivor_count if request.survivor_count is not None else 3,
        seed=request.seed,
        random_events_enabled=request.random_events_enabled,
        max_steps=request.max_steps,
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
