# QuakeBot

QuakeBot is a dependency-light Python harness for an LLM-controlled humanoid rescue robot in a semantic, room-level earthquake environment.

The agent receives structured observations and returns one JSON action. The environment validates that action, owns all state transitions, updates mission accounting, and rejects unsafe or unsupported behaviour. The core simulation stays symbolic: rooms, floors, connections, hazards, survivors, and high-level rescue actions rather than coordinates, tiles, bounds, or spawn points.

## What This Demonstrates

- Multi-floor semantic building with Ground, Floor 1, and Basement.
- Multiple survivors with stable ids, medical state, entrapment, evacuation, and extraction status.
- Small public action space designed for reliable LLM control.
- Progress-aware observations with blocked paths, hazards, dynamic survivor cues (driven by survivor state rather than static room configuration), and recommended next actions.
- Restricted emergency entry for severe/high-risk rooms when a discovered survivor needs rescue-critical intervention.
- Mission accounting prevents early completion while survivors or reachable rooms remain unresolved.
- Optional deterministic mock, OpenAI-compatible, local Ollama, and Ollama Cloud agents.
- React Mission Control / Replay Dashboard for visual inspection without moving simulation authority into the UI.

The main contribution is the harness, not a claim that rescue autonomy is fully solved. The system demonstrates a clean observe -> JSON action -> validate -> transition loop for an LLM-style agent in a virtual rescue world.

## Quick Start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
pytest -q
python3 -m quakebot.demo --scenario default
```

## Demo Commands

```bash
python3 -m quakebot.demo --scenario default
python3 -m quakebot.demo --scenario hidden_survivors_approximate
python3 -m quakebot.demo --approximate
python3 -m quakebot.demo --scenario generated_small --seed 7
python3 -m quakebot.demo --scenario severe_risk_bleeding_survivor
```

`generated_small` is a compact scenario-builder demo with a blocked room, an unsafe utility room, an initially unknown survivor location, and approximate survivor-count accounting.
`severe_risk_bleeding_survivor` is a compact emergency-entry demo with a severe-risk board room, a discovered trapped survivor with severe bleeding, and no repetitive life-sign scan loop.

## Architecture

```text
Agent / LLM
  -> JSON action
Validator
  -> valid action
Environment
  -> state transition
Observation
  -> restricted structured observation back to agent
```

The environment is the only owner of state transitions. Agents, prompts, replay code, the API, and the React dashboard submit actions or display snapshots; they do not mutate rescue state directly.

## World

The default semantic layout is loaded from:

```text
quakebot/layouts/default/building.json
```

Default rooms:

- Ground: Entrance, Lobby, Hallway, Office, Storage, Stairwell_G
- Floor 1: Stairwell_1, Upper_Hallway, Apartment_A, Apartment_B, Balcony
- Basement: Stairwell_B, Basement, Utility_Room, Generator_Room

Default survivors:

- `survivor_office`: trapped in Office, fast breathing, rapid pulse, minor bleeding, cannot walk.
- `survivor_apartment_a`: stable walking survivor on Floor 1.
- `survivor_basement`: critical basement survivor with laboured breathing, weak pulse, severe bleeding, and unsafe access after aftershock.

## Observation Contract

Observations are JSON-serialisable and include current room/floor, visible exits, local hazards, visible objects, audio/vibration/life-sign cues, local survivors, known survivors, blocked paths, blocked connections, room search status, mission accounting, recent events, and `recommended_next_actions`.

The agent only receives this structured observation. The React UI may show full replay state for Mission Control inspection, including hidden survivor positions, but that is presentation-only and not the agent truth.

## Canonical Action Space

The public action space is intentionally small and high-level.

Navigation / perception:

- `look`
- `move(target)`
- `search_room`
- `sense_area(mode, target?)`

Room accounting / hazards:

- `clear_obstruction(target)`
- `mark_room_cleared(target?)`
- `mark_room_inaccessible(target, reason)`
- `mark_hazard(hazard_type)`

Survivor interaction / care:

- `reassure_survivor(target, message)`
- `ask_medical_question(target, question)`
- `perform_primary_survey(target)`
- `treat_survivor(target, treatment)`
- `free_survivor(target)`

Evacuation / extraction:

- `evacuate_survivor(target)`
- `request_specialised_extraction(target, reason)`
- `handoff_to_specialised_team(target)`: hands off the survivor to the extraction team, which safely moves them to the Entrance and completes their evacuation.

Mission completion:

- `call_rescue_team(location?, reason?)`
- `submit_report(summary)`

Removed legacy action names are rejected. For example, `scan_for_life_signs` is not converted; the environment rejects it with guidance to use `sense_area` with `mode="life_signs"`.

High or severe structural risk blocks casual entry. QuakeBot may still enter under a validated emergency rescue protocol when life signs or a discovered survivor create an immediate life-safety need. The environment logs the risk and still owns every state transition.

## Action Details

`sense_area` replaces separate listening, vibration, and life-sign scan actions:

```json
{"type": "sense_area", "mode": "audio"}
{"type": "sense_area", "mode": "vibration"}
{"type": "sense_area", "mode": "life_signs", "target": "Utility_Room"}
```

The target defaults to the current room. It may be the current room or an adjacent room, including an unsafe adjacent room scanned from the doorway.

`clear_obstruction` is for blocked rooms, rubble paths, and blocked doorways:

```json
{ "type": "clear_obstruction", "target": "Office" }
```

`free_survivor` is distinct: it only frees a located survivor from survivor-specific entrapment after access to the room has already been resolved.

`treat_survivor` replaces individual medical sub-actions:

```json
{"type": "treat_survivor", "target": "survivor_basement", "treatment": "control_bleeding"}
{"type": "treat_survivor", "target": "survivor_basement", "treatment": "support_breathing"}
{"type": "treat_survivor", "target": "survivor_office", "treatment": "stabilise"}
{"type": "treat_survivor", "target": "survivor_office", "treatment": "monitor"}
```

Supported treatments are `control_bleeding`, `support_breathing`, `stabilise`, `monitor`, `protect`, and `supply`.

Use an explicit item action to secure supplies:

```json
{"type": "collect_item", "item": "first_aid_kit"}
```

Treatment actions require a completed `perform_primary_survey` first. `supply` also requires QuakeBot to have already collected the `first_aid_kit`, and using `supply` consumes that kit.

`evacuate_survivor` chooses the appropriate assisted or carried narrative from survivor state:

```json
{ "type": "evacuate_survivor", "target": "survivor_apartment_a" }
```

Trapped survivors cannot be evacuated until `free_survivor` succeeds or specialised extraction is requested and handed off.

## Mission Accounting

A survivor is accounted for only when they are evacuated, handed off to a specialised team, confirmed inaccessible at room level, or awaiting specialised extraction with a safe final state. Specialised extraction is not instant completion: `awaiting_specialised_extraction` is final only when the survivor is `safe_to_leave` or `handoff_complete`.

Critical survivors remain unresolved unless stabilised and safe to leave, evacuated, or handed off.

Final reports are rejected while `mission_accounting.unaccounted` is non-empty. In approximate survivor-count mode, final reports are also rejected until reachable rooms are searched or cleared.

## Validation And State Ownership

Every action is parsed into the canonical action schema, validated, and then applied through `QuakeBotEnv.step`. Unsupported or removed actions are rejected; they are not aliased into newer actions. Invalid item collection, invalid handoffs, unsafe movement, non-adjacent sensing, premature reports, missing extraction reasons, and premature room clearing all return clean failed action results.

`recommended_next_actions` is a planner hint inside the observation. Recommendations are generated from current environment state and are intended to be directly executable JSON actions, but the validator still remains the authority.

## Hidden And Approximate Modes

Known-location mode exposes initial survivor ids and locations. Unknown-location mode hides survivor ids and exact locations until discovery. Initial unknown observations do not expose hidden survivor ids, hidden survivor rooms, global hidden cue rooms, or hidden survivor counts.

Approximate mode exposes count estimates such as `estimated_survivors`, `survivor_count_min`, and `survivor_count_max`, and requires room search accounting before completion.

Run hidden-location demos:

```bash
python3 -m quakebot.demo --scenario hidden_survivors_exact
python3 -m quakebot.demo --scenario hidden_survivors_approximate
```

## Python Scenario Builder

Custom scenarios can be built in Python without changing the environment:

```python
from quakebot.env import QuakeBotEnv
from quakebot.scenario_builder import RoomSpec, FloorSpec, SurvivorSpec, ScenarioSpec

entrance = RoomSpec("Entrance")
office = RoomSpec("Office")
entrance.connect(office)

ground = FloorSpec("ground", "Ground Floor", [entrance, office])

survivor = SurvivorSpec(
    id="survivor_001",
    name="Pari",
    location=office,
    trapped=True,
    breathing_status="fast",
    bleeding="minor",
    can_walk=False,
)

scenario = ScenarioSpec(
    id="custom_rescue",
    name="Custom Rescue Scenario",
    floors=[ground],
    survivors=[survivor],
)

env = QuakeBotEnv(layout=scenario.compile())
```

The same builder is used by the `generated_small` demo, which proves the loop can run outside the hand-authored default path.
The `severe_risk_bleeding_survivor` demo uses the same builder and exercises emergency entry into a severe-risk room after a life-sign scan.

## Agent Modes

The deterministic `MockAgent` is a baseline policy for repeatable demos and tests. It consumes observations and public mission accounting, emits only canonical actions, and does not directly mutate environment state. Optional OpenAI-compatible and Ollama agents use the same observation/action harness.

## React Mission Control / Replay Dashboard

Start the backend:

```bash
uvicorn quakebot.api.server:app --reload
```

Run with Docker Compose:

```bash
docker compose up --build
```

This starts:

- the FastAPI backend on `http://localhost:8000`
- the Vite frontend on `http://localhost:5173`

If you also want a local Ollama container:

```bash
docker compose --profile ollama up --build
```

In that setup, the backend can reach Ollama at `http://ollama:11434`. The frontend uses a Vite proxy, so browser requests stay on `localhost:5173` while the container forwards API and WebSocket traffic to `http://backend:8000`.

Start the frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend is a Mission Control / Replay Dashboard. It shows replay snapshots, current action JSON, survivor cards, hazards, blocked routes, events, score, and mission accounting. The Python environment remains the source of truth for validation, transitions, scoring, and completion.

Session replays are automatically saved to the `simulation_recordings/` directory upon backend API completion. These files can be loaded back into the UI for later inspection.

The Scenario panel can be used to select pre-configured demo scenarios (such as `generated_small` or `severe_risk_bleeding_survivor`) or to submit a complete custom semantic layout as JSON: floors, rooms, room connections, hazards, objects, blocked access, and survivors. This is configuration only. The UI does not mutate world state during an episode; it sends the layout/scenario configuration to the backend, and `QuakeBotEnv.step` still owns every transition.

Build the frontend:

```bash
cd frontend
npm run build
```

## Optional LLM Agents

OpenAI-compatible:

```bash
export OPENAI_API_KEY=...
python3 -m quakebot.demo --openai
```

Local Ollama:

```bash
ollama pull llama3.1
ollama serve
python3 -m quakebot.demo --ollama
```

The parser attempts to extract the first JSON object from markdown-wrapped or prose-wrapped model output before treating a response as invalid.

## Evaluation Results

Local validation for this submission:

| Scenario                        | Agent                             | Result | Final report accepted | Notes                                                                                                           |
| ------------------------------- | --------------------------------- | ------ | --------------------- | --------------------------------------------------------------------------------------------------------------- |
| `default`                       | `MockAgent`                       | Pass   | Yes                   | Multi-survivor default rescue with obstruction, evacuation, and specialised extraction handoff.                 |
| `hidden_survivors_approximate`  | `MockAgent`                       | Pass   | Yes                   | Hidden survivor ids/locations until discovery; room accounting required before completion.                      |
| `--approximate`                 | `MockAgent`                       | Pass   | Yes                   | Known survivors with approximate survivor count and room-clearance requirement.                                 |
| `generated_small --seed 7`      | `RecommendedActionAgent` baseline | Pass   | Yes                   | Custom semantic layout with blocked access, unsafe room, unknown survivor location, and approximate accounting. |
| `severe_risk_bleeding_survivor` | `SevereRiskDemoAgent` baseline    | Pass   | Yes                   | Emergency-entry scenario with a severe-risk board room, life-sign detection, and rescue-critical triage.        |

## Dynamic Events And Health

Random events are optional and seeded. They can raise structural risk, block room connections, spread smoke, or worsen survivor condition.

Survivors track simplified health state such as `stability`, `bleeding_controlled`, `airway_clear`, `breathing_supported`, `last_checked_step`, `last_monitored_step`, and `condition_history`. `treat_survivor` changes this virtual state and can also improve the underlying visible bleeding, breathing, pulse, and triage state. This is a simulation mechanic, not medical advice.

## Tests

```bash
pytest -q
```

## Known Limitations

- QuakeBot is not a medical advice tool.
- The simulation is semantic and room-level, not coordinate-, physics-, or robotics-accurate.
- The deterministic baseline agent is for repeatable evaluation; optional LLM agents may still make poor choices, but they are constrained by the same validator.
- The dashboard is a replay and inspection surface, not the agent's observation channel.
- A survivor awaiting specialised extraction is not considered complete just because extraction was requested.
- Scenario realism is intentionally limited so the harness remains clear and dependency-light.
