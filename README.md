# QuakeBot

QuakeBot is a lightweight Python harness for an LLM-controlled humanoid rescue robot in a symbolic, multi-floor earthquake-response world.

The robot is physically embodied: it follows sound and vibration cues, braces against rubble, lifts debris with powerful hands, reassures survivors, checks pulse/breathing/airway/bleeding, performs simplified primary surveys, stabilises people, and carries or escorts them to safety.

The core architecture is deliberately strict: the LLM never mutates world state. It receives structured observations and returns exactly one structured JSON action. The environment validates actions, applies state transitions, rejects unsafe/impossible moves, updates memory, and scores the mission.

## Why This Is a Strong LLM-Agent Harness

- Multi-floor symbolic environment with Ground, Floor 1, and Basement.
- Multiple survivors with different medical states and triage priorities.
- Progress-aware observations with blocked paths and recommended next actions.
- Humanoid rescue actions, including rubble removal and carrying people.
- Simplified medical checks: pulse, breathing, airway, bleeding, responsiveness, mobility, primary survey.
- Prioritisation logic for critical/high/medium/low survivors.
- Dynamic hazards: an aftershock makes Basement structurally severe and can block access.
- Optional OpenAI-compatible, local Ollama, and Ollama Cloud agents.
- Deterministic `MockAgent` demo works without an API key.

## World

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
- `survivor_basement`: critical cues below, laboured breathing, weak pulse, severe bleeding, unsafe access after aftershock.

## Observation Schema

Observations are JSON-serialisable and include:

- `current_floor`, `floor_name`, `vertical_exits`
- room exits, local conditions, visible objects
- heard sounds, vibration cues, survivor cues
- `local_survivors`
- `known_survivors`
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
  ]
}
```

## Action Space

Navigation and search:
- `look`
- `move(target)`
- `inspect(target)`
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

Mission actions:
- `pick_up(item)`
- `mark_hazard(hazard_type)`
- `call_rescue_team(location, reason)`
- `return_to_base`
- `submit_report(summary)`

## Demo

```bash
python3 -m quakebot.demo
```

Pause before each step:

```bash
python3 -m quakebot.demo --step
```

The deterministic demo rescues `survivor_office`, rescues `survivor_apartment_a`, detects the critical basement survivor, requests specialised extraction because the Basement becomes unsafe, notifies rescue teams, and submits a survivor-specific final report.

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

## Tests

```bash
pytest
```

## Design Notes

This is not a medical advice tool. It is a simplified rescue simulation designed to show a clean LLM-agent harness for humanoid robotics: structured perception, structured actions, validation, stateful environment transitions, memory, dynamic hazards, and mission scoring.
