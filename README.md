# QuakeBot

First, thank you for taking the time to review my submission.

QuakeBot is a semantic disaster-response harness for autonomous humanoid rescue agents. It places an agent into a constrained virtual earthquake scenario, gives it restricted structured observations, accepts JSON-like actions, validates them, applies environment-owned state transitions, and records the mission as a replay.

The project is intentionally harness-first. The main challenge here is the interface between an intelligent agent and an environment it can act in, not graphics or physics.

## Recommended Experience

QuakeBot is frontend-first and Docker-first.

The recommended way to review the project is the React Mission Control Dashboard, which shows:

- floor-by-floor replay
- QuakeBot movement
- survivor state
- hazards and blocked rooms
- mission timeline
- replay controls
- mission accounting
- scenario configuration

The dashboard is for human inspection. It may show full replay or world state.

The agent does not receive that view. The agent only receives restricted structured observations representing what QuakeBot could plausibly perceive from its current situation in the environment.

## Quick Start

Run the full stack with Docker:

```bash
docker compose up --build
```

Then open:

```text
http://localhost:5173
```

This starts the backend API and the React dashboard. Scenario selection happens in the dashboard, and selecting a new scenario starts the simulation automatically.

## Manual Local Run

Backend:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
uvicorn quakebot.api.server:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Then open `http://localhost:5173`.

## Using the Web UI

The dashboard is intended to be the main way to explore QuakeBot.

Typical flow:

1. Open `http://localhost:5173`.
2. Configure simulation settings in the configuration panel.
3. Click "Start Episode" to start the simulation.
4. Use the replay controls to pause, resume, step through, or restart the episode.
5. Switch floors to inspect the building level by level.
6. Follow the mission log, current action, survivor cards, and mission accounting panels as the run unfolds.

Main panels:

- floor map: visual replay of rooms, hazards, obstructions, QuakeBot, and survivors
- scenario configuration: choose the scenario, agent mode, and mission settings
- replay controls: play, pause, step, scrub, and restart
- mission log and timeline: review what happened and when
- robot status and current action: inspect the agent's present state
- survivor cards and mission accounting: track discovery, treatment, evacuation, and unresolved rooms or cues

The UI is a human-facing inspection and replay tool. It is intentionally richer than the agent's own view of the world.

## What The Harness Does

QuakeBot runs the loop below:

```text
restricted observation
-> agent chooses structured action
-> validator checks legality and safety
-> environment applies the transition
-> new observation, score, and mission accounting
```

The LLM never mutates world state directly. All state changes go through `QuakeBotEnv.step`.

## Core Design Choices

### 1. Semantic room-level simulation

The core environment reasons in rooms, connections, hazards, survivors, and rescue state.

It does not depend on coordinates, tiles, spawn points, physics, or geometry-heavy movement. Optional visual positions exist only for replay and UI rendering.

### 2. Restricted observations and hidden information

The environment can hide survivor locations, identities, and medical details until QuakeBot discovers them. In the flagship unknown-location scenarios, the agent must search, scan, and account for rooms rather than reading hidden truth.

### 3. Canonical action space

The public action set is intentionally small and stable:

- navigation and perception: `look`, `move`, `search_room`, `sense_area`
- room accounting and hazards: `clear_obstruction`, `mark_room_cleared`, `mark_room_inaccessible`, `mark_hazard`
- survivor interaction and care: `reassure_survivor`, `ask_medical_question`, `perform_primary_survey`, `treat_survivor`, `free_survivor`
- evacuation and extraction: `evacuate_survivor`, `request_specialised_extraction`, `handoff_to_specialised_team`
- mission completion: `call_rescue_team`, `submit_report`

Removed legacy actions are rejected rather than silently aliased.

### 4. LLMs do not get planner hints

OpenAI and Ollama agents do not receive environment-generated `recommended_next_actions`. Earlier versions exposed those hints, and the model tended to follow them instead of reasoning independently.

Recommended actions still exist internally for deterministic baselines and debugging, but LLM prompts receive only restricted observations.

### 5. Dangerous rooms support emergency rescue

High-risk rooms are not treated as permanently untouchable. Casual exploration may be rejected, but rescue-critical entry can still be allowed for life-saving intervention such as surveying, stabilising, freeing, and evacuating a confirmed survivor.

## Agent Modes

- `MockAgent`: deterministic baseline for demos and regression tests
- `RecommendedActionAgent`: debugging and deterministic evaluation
- `OpenAIAgent` / `OllamaAgent`: optional LLM backends using the same observation and action interface

## Example Scenarios

Terminal demos still exist, but they are secondary to the dashboard experience.

```bash
python -m quakebot.demo --scenario default
python -m quakebot.demo --scenario hidden_survivors_approximate
python -m quakebot.demo --scenario severe_risk_bleeding_survivor --seed 7
```

## Scenario Authoring

Scenarios are semantic and data-driven. They can be loaded from layouts or built in Python using `ScenarioSpec`, `FloorSpec`, `RoomSpec`, and `SurvivorSpec`.

## Project Structure

```text
quakebot/   core environment, validation, observations, accounting, replay, agents, API
frontend/   React Mission Control Dashboard
tests/      focused backend and replay tests
```

## Verification

Backend tests:

```bash
pytest -q
```

Frontend build:

```bash
cd frontend
npm run build
```

## Limitations

This project was developed rapidly during university coursework deadlines and final bachelor examinations. AI-assisted coding tools were used for implementation, refactoring, debugging, and iteration.

QuakeBot should be read as a prototype harness and systems-design project, not as a production system.

Current limitations include:

- semantic room-level simulation rather than physics-based rescue
- simplified medical modelling
- a deterministic baseline agent
- imperfect LLM rescue reasoning
- the dashboard can show more state than the agent itself receives
- LLM agents can still loop or choose poor actions, but those failures are exposed and constrained by validation and mission accounting

## Why This Project Exists

QuakeBot explores a simple question: what does a good harness for autonomous rescue reasoning look like?

The main ideas are constrained autonomy, explicit validation, hidden information, environment-owned transitions, replayability, and human-readable mission accounting.
