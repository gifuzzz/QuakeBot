# QuakeBot

QuakeBot is a dependency-light Python harness for an LLM-controlled humanoid rescue robot in a semantic, room-level earthquake environment.

The agent receives structured observations and returns one JSON action. The environment validates that action, owns all state transitions, updates mission accounting, and rejects unsafe or unsupported behaviour. The core simulation stays symbolic: rooms, floors, connections, hazards, survivors, and high-level rescue actions rather than coordinates, tiles, bounds, or spawn points.

## Why This Harness

- Multi-floor semantic building with Ground, Floor 1, and Basement.
- Multiple survivors with stable ids, medical state, entrapment, evacuation, and extraction status.
- Small public action space designed for reliable LLM control.
- Progress-aware observations with blocked paths, hazards, survivor cues, and recommended next actions.
- Mission accounting prevents early completion while survivors or reachable rooms remain unresolved.
- Optional deterministic mock, OpenAI-compatible, local Ollama, and Ollama Cloud agents.
- React Mission Control / Replay Dashboard for visual inspection without moving simulation authority into the UI.

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
- `handoff_to_specialised_team(target)`

Mission completion:

- `call_rescue_team(location?, reason?)`
- `submit_report(summary)`

Removed legacy action names are rejected. For example, `scan_for_life_signs` is not converted; the environment rejects it with guidance to use `sense_area` with `mode="life_signs"`.

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
{"type": "clear_obstruction", "target": "Office"}
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

`evacuate_survivor` chooses the appropriate assisted or carried narrative from survivor state:

```json
{"type": "evacuate_survivor", "target": "survivor_apartment_a"}
```

Trapped survivors cannot be evacuated until `free_survivor` succeeds or specialised extraction is requested and handed off.

## Mission Accounting

A survivor is accounted for only when they are evacuated, handed off to a specialised team, confirmed inaccessible at room level, or awaiting specialised extraction with a safe final state. Specialised extraction is not instant completion: `awaiting_specialised_extraction` is final only when the survivor is `safe_to_leave` or `handoff_complete`.

Critical survivors remain unresolved unless stabilised and safe to leave, evacuated, or handed off.

Final reports are rejected while `mission_accounting.unaccounted` is non-empty. In approximate survivor-count mode, final reports are also rejected until reachable rooms are searched or cleared.

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
    name="Elena",
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

## Demo

```bash
python3 -m quakebot.demo --scenario default
python3 -m quakebot.demo --scenario hidden_survivors_approximate
python3 -m quakebot.demo --approximate
```

The deterministic mock agent uses only canonical actions. It detects survivors, clears blocked access, performs primary surveys, treats survivors, evacuates two survivors, requests and hands off specialised extraction where needed, notifies rescuers, and submits a final report.

## React Mission Control / Replay Dashboard

Start the backend:

```bash
uvicorn quakebot.api.server:app --reload
```

Start the frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend is a Mission Control / Replay Dashboard. It shows replay snapshots, current action JSON, survivor cards, hazards, blocked routes, events, score, and mission accounting. The Python environment remains the source of truth for validation, transitions, scoring, and completion.

The Scenario panel can also submit a complete custom semantic layout as JSON: floors, rooms, room connections, hazards, objects, survivor cues, blocked access, and survivors. This is configuration only. The UI does not mutate world state during an episode; it sends the layout to the backend, and `QuakeBotEnv.step` still owns every transition.

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

## Dynamic Events And Health

Random events are optional and seeded. They can raise structural risk, block room connections, spread smoke, or worsen survivor condition.

Survivors track simplified health state such as `stability`, `bleeding_controlled`, `airway_clear`, `breathing_supported`, `last_checked_step`, `last_monitored_step`, and `condition_history`. `treat_survivor` changes this virtual state. This is a simulation mechanic, not medical advice.

## Tests

```bash
pytest
```

## Design Notes

QuakeBot is not a medical advice tool. It is a focused LLM-agent harness for humanoid rescue reasoning: structured perception, structured JSON actions, validation, environment-owned state transitions, dynamic hazards, replay, and scoring.
