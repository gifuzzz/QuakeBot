# QuakeBot

QuakeBot is a lightweight Python harness for an LLM-controlled humanoid rescue robot in a symbolic, multi-floor earthquake-response world.

The robot is physically embodied: it follows sound and vibration cues, braces against rubble, lifts debris with powerful hands, reassures survivors, checks pulse/breathing/airway/bleeding, performs simplified primary surveys, stabilises people, and carries or escorts them to safety.

The core architecture is deliberately strict: the LLM never mutates world state. It receives structured observations and returns exactly one structured JSON action. The environment validates actions, applies state transitions, rejects unsafe/impossible moves, updates memory, and scores the mission.

## Why This Is a Strong LLM-Agent Harness

- Multi-floor symbolic environment with Ground, Floor 1, and Basement.
- Multiple survivors with different medical states and triage priorities.
- Progress-aware observations with blocked paths and recommended next actions.
- Mission-accounting layer that prevents early completion while survivors remain unverified.
- Humanoid rescue actions, including rubble removal and carrying people.
- Simplified medical checks: pulse, breathing, airway, bleeding, responsiveness, mobility, primary survey.
- Prioritisation logic for critical/high/medium/low survivors.
- Dynamic hazards: an aftershock makes Basement structurally severe and can block access.
- Optional OpenAI-compatible, local Ollama, and Ollama Cloud agents.
- Deterministic `MockAgent` demo works without an API key.

## World

The default world is loaded from a semantic layout pack rather than being hardcoded in the environment. The active default pack is:

```text
quakebot/layouts/default/building.json
```

Ground:
- Entrance
- Lobby
- Hallway
- Office
- Storage
- Stairwell_G

Floor 1:
- Stairwell_1
- Upper_Hallway
- Apartment_A
- Apartment_B
- Balcony

Basement:
- Stairwell_B
- Basement
- Utility_Room
- Generator_Room

The default survivors are:

- `survivor_office`: trapped under Office rubble, rapid pulse, fast breathing, minor bleeding, cannot walk.
- `survivor_apartment_a`: injured and frightened on Floor 1, stable, can walk with assistance.
- `survivor_basement`: critical cues below, laboured breathing, weak pulse, severe bleeding, dangerous basement access after aftershock.

## Observation Schema

Observations are JSON-serialisable and include:

- `current_floor`, `floor_name`, `vertical_exits`
- room exits, local conditions, visible objects
- heard sounds, vibration cues, survivor cues
- `local_survivors`
- `known_survivors`
- `mission_accounting`
- `blocked_paths`
- `recommended_next_actions`
- memory and recent events

Example:

```json
{
  "location": "Hallway",
  "current_floor": 0,
  "floor_name": "Ground",
  "visible_exits": ["Lobby", "Office", "Storage"],
  "blocked_paths": {
    "Office": {
      "reason": "rubble",
      "status": "approached",
      "required_location": "Hallway",
      "next_required_action": "lift_rubble"
    }
  },
  "recommended_next_actions": [
    {"type": "lift_rubble", "target": "Office"}
  ],
  "mission_accounting": {
    "total_known_or_suspected_survivors": 3,
    "evacuated": ["survivor_office"],
    "unaccounted": ["survivor_apartment_a", "survivor_basement"],
    "mission_can_finish": false,
    "reason_not_finished": "survivor_apartment_a, survivor_basement has not been evacuated, directly assessed with extraction requested, or confirmed inaccessible"
  }
}
```

## Mission Accounting

QuakeBot does not optimise for partial success. The environment tracks every known or suspected survivor until each one is accounted for.

A survivor is accounted for only when one of these is true:

- `evacuated == true`
- `accounting_status == "awaiting_specialised_extraction"` after direct assessment, stabilisation, and extraction request
- `inaccessible_confirmed == true` after QuakeBot physically attempted access or scanned the hazard area

Final reports are rejected while `mission_accounting.unaccounted` is non-empty. This prevents an LLM agent from hallucinating completion, reporting an unverified survivor condition, or stopping after rescuing only the easiest two people.

Survivor accounting statuses are explicit:

- `unknown`
- `suspected`
- `located`
- `directly_assessed`
- `evacuated`
- `awaiting_specialised_extraction`
- `inaccessible_confirmed`

Only `evacuated`, `awaiting_specialised_extraction`, and `inaccessible_confirmed` are final statuses.

## Semantic Modular Layouts

QuakeBot's core simulation uses room-level semantic layouts, not coordinates. A layout pack defines floors, rooms, room connections, room hazards, blocked paths, items, and survivors. The environment loads this data through `ScenarioConfig` and the layout loader, then owns all state transitions at the symbolic room level.

The default scenario config uses:

- `layout_pack="default"`
- active floors: `ground`, `floor_1`, `basement`
- `survivor_count_mode="exact"`
- `survivor_count=3`
- fixed seed
- random events disabled

The simulation layout intentionally contains no tile coordinates, bounds, spawn points, or pixel geometry. This keeps the LLM-agent harness focused on symbolic embodied reasoning: "move to Hallway", "scan Basement", "request specialised extraction", not "move to tile 12,7".

Visual presentation is separate. The optional pixel replay layout lives in:

```text
quakebot/layouts/default/visual.json
```

That file is only consumed by the Streamlit UI. The environment does not use it for movement, validation, survivor state, scoring, or mission completion.

## Unknown vs Known Survivor Locations

QuakeBot supports hiding survivor locations from the agent until they are discovered:

- `survivor_location_mode="known"` (default): The agent's initial observation contains full location details for all initial survivors.
- `survivor_location_mode="unknown"`: The agent receives no initial survivor details. Survivors must be discovered by entering their room, scanning for life signs, sensing vibrations, or listening for cues. The `mission_accounting` exposes only discovered survivors and unresolved cues. 

Demo with unknown locations (exact count):
```bash
python3 -m quakebot.demo --scenario hidden_survivors_exact
```

Demo with unknown locations (approximate count):
```bash
python3 -m quakebot.demo --scenario hidden_survivors_approximate
```

## Exact vs Approximate Survivor Counts

QuakeBot supports two mission-accounting modes:

- `exact`: the survivor count is known. The mission can finish after every known survivor is evacuated, awaiting specialised extraction after direct assessment, or confirmed inaccessible.
- `approximate`: the survivor count is uncertain. QuakeBot must account for all discovered survivors and search or clear every reachable room before the final report is accepted.

Approximate mode adds room-level search accounting:

- `unknown`
- `discovered`
- `searched`
- `cleared`
- `inaccessible_confirmed`

This prevents the agent from assuming the rescue is complete just because the obvious survivors are handled. In approximate mode, early final reports are rejected with the remaining unaccounted survivors and uncleared reachable rooms.

## Action Space

Navigation and search:
- `look`
- `move(target)`
- `inspect(target)`
- `search_room`
- `search_floor`
- `listen_for_survivor`
- `sense_vibrations`
- `scan_for_life_signs`

Physical rescue:
- `approach_rubble(target)`
- `lift_rubble(target)`
- `remove_rubble(target)`
- `carry_survivor(target)`
- `assist_walk(target)`
- `escort_to_exit(target)`

Survivor interaction:
- `reassure_survivor(target, message)`
- `ask_medical_question(target, question)`

Medical checks and stabilisation:
- `perform_primary_survey(target)`
- `check_pulse(target)`
- `check_breathing(target)`
- `check_airway(target)`
- `check_bleeding(target)`
- `check_responsiveness(target)`
- `check_mobility(target)`
- `apply_pressure_bandage(target)`
- `position_for_breathing(target)`
- `monitor_vitals(target)`
- `stabilise_survivor(target)`
- `tag_triage_priority(target, priority)`
- `request_medical_evac(target, reason)`
- `request_specialised_extraction(target, reason)`

Mission actions:
- `pick_up(item)`
- `mark_hazard(hazard_type)`
- `mark_room_cleared(target)`
- `mark_room_inaccessible(target, reason)`
- `mark_survivor_inaccessible(target)`
- `call_rescue_team(location, reason)`
- `return_to_base`
- `submit_report(summary)`

## Demo

```bash
python3 -m quakebot.demo
```

Approximate survivor count demo:

```bash
python3 -m quakebot.demo --approximate
```

Pause before each step:

```bash
python3 -m quakebot.demo --step
```

The deterministic demo rescues `survivor_office`, rescues `survivor_apartment_a`, then continues into the basement investigation instead of ending early. It scans from `Stairwell_B`, enters the damaged Basement, directly assesses `survivor_basement`, checks pulse/breathing/bleeding, stabilises severe bleeding and laboured breathing, requests specialised extraction because the survivor is trapped under severe structural risk, returns to Entrance, notifies rescue teams, and submits a survivor-specific final report only after all three survivors are accounted for.

## React Pixel-Art UI

The primary visual interface is a React + TypeScript pixel-art replay viewer. It consumes Python API data and does not reimplement simulation logic.

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

Then open the Vite URL, usually:

```text
http://localhost:5173
```

The React UI shows:

- scenario configuration for active floors, exact/approximate survivor count, seed, random events, and max steps
- one-floor-at-a-time pixel-art map for Ground, Floor 1, and Basement
- QuakeBot, survivors, evacuated survivors, specialised extraction state, rubble, hazards, blocked routes, stairs, and first-aid items
- current action JSON, result, and generated events for the selected step
- replay controls: previous, next, play/pause, reset, jump to start/end, and step slider
- robot status, survivor medical cards, mission accounting, mission log, and random-event timeline

The frontend is read-only with respect to simulation state except through API commands. The Python environment remains the source of truth, and the UI renders serialisable replay snapshots.

Backend API endpoints:

- `GET /health`
- `GET /layouts`
- `POST /episodes/start`
- `GET /episodes/{episode_id}/snapshots`
- `GET /episodes/{episode_id}/snapshot/{step}`
- `POST /episodes/{episode_id}/step`
- `POST /episodes/{episode_id}/reset`

Screenshot placeholder: run the backend and frontend above, start an episode, then capture the pixel map centred in the page.

## Streamlit Visual Demo

The Streamlit UI remains available as a legacy/prototype replay viewer.

Launch the Streamlit presentation layer:

```bash
streamlit run quakebot/app.py
```

The visual demo replays the same environment episode as a step-by-step interface. It shows:

- Next, previous, reset, end, and auto-play controls.
- Agent source selection: MockAgent, Ollama Cloud, local Ollama, or OpenAI-compatible.
- A floor-by-floor pixel-art tile map with a selector for Ground, Floor 1, and Basement.
- QuakeBot's current tile/room, including whether it is carrying a survivor.
- Survivor, evacuated survivor, item, stairs, door, rubble, blocked, and hazard sprites.
- Current action JSON, action description, and result.
- Survivor cards with pulse, breathing, bleeding, mobility, checks completed, priority, and evacuation state.
- Robot status: location, floor, battery, inventory, carrying state, score, and mission progress.
- Mission log and dialogue events.
- Mission accounting, including whether the mission can finish and which survivors remain unaccounted.
- A full terminal-style step transcript matching the text demo.

The UI is intentionally separate from the simulation. `quakebot/replay.py` runs the existing `QuakeBotEnv` and records serialisable `EpisodeStep` snapshots. `quakebot/layouts.py` defines static pixel-map room regions, doors, stairs, rubble, and item coordinates. `quakebot/app.py` only renders those snapshots and layouts, so presentation code does not own world state or rescue transitions.

To use Ollama Cloud in the visual UI:

```bash
export OLLAMA_API_KEY=...
streamlit run quakebot/app.py
```

Then choose `Ollama Cloud` in the sidebar, set a model such as `gpt-oss:20b`, and click `Generate Episode`.

To use local Ollama in the visual UI:

```bash
ollama pull llama3.1
ollama serve
streamlit run quakebot/app.py
```

Then choose `Local Ollama` in the sidebar.

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

Ollama Cloud:

```bash
export OLLAMA_API_KEY=...
python3 -m quakebot.demo --ollama-cloud --ollama-model gpt-oss:20b
```

The parser attempts to extract the first JSON object from markdown-wrapped or prose-wrapped model output before treating a response as invalid.

## Dynamic Events and Survivor Health

Random events are optional and seeded. The environment uses a local `random.Random(seed)` instance, so the same seed plus the same action sequence produces the same event sequence.

Dynamic events can include:

- aftershocks that raise structural risk
- debris falls that increase room danger or block room-to-room connections
- smoke spreading between connected rooms
- survivor condition worsening from entrapment, severe bleeding, or laboured breathing

Survivors track simplified health state:

- `stability`
- `bleeding_controlled`
- `airway_clear`
- `breathing_supported`
- `last_checked_step`
- `condition_history`

Medical actions affect this virtual state. `apply_pressure_bandage` controls severe bleeding deterioration, `position_for_breathing` supports laboured breathing, `stabilise_survivor` improves stability, and `monitor_vitals` updates the latest checked step. This is a simulation mechanic, not medical advice.

Blocked connections are shown in observations and replay snapshots. Movement through a blocked connection is rejected, and pathfinding/recommended actions avoid blocked edges when a safe alternative exists.

Run seeded dynamic demos:

```bash
python3 -m quakebot.demo --random-events
python3 -m quakebot.demo --random-events --seed 42
python3 -m quakebot.demo --approximate --random-events --seed 42
```

## Tests

```bash
pytest
```

## Design Notes

This is not a medical advice tool. It is a simplified rescue simulation designed to show a clean LLM-agent harness for humanoid robotics: structured perception, structured actions, validation, stateful environment transitions, memory, dynamic hazards, and mission scoring.
