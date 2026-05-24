# AGENTS.md

- Keep this project dependency-light; prefer the Python standard library unless a dependency clearly improves the harness.
- Use British English in documentation and user-facing project text where relevant.
- Run `pytest -q` after backend, environment, validation, agent, scoring, or API changes.
- Run `cd frontend && npm run build` after frontend changes. Use `npm ci` first when dependencies need to be installed or refreshed.
- Preserve structured observations and structured JSON-like actions.
- Do not let agents mutate environment state directly. All state transitions must go through `QuakeBotEnv.step`.
- Keep the core simulation semantic and room-level. Do not introduce coordinates, tiles, bounds, spawn points, or physics into core environment logic.
- Coordinates and visual positions are allowed only in optional UI/replay data.
- Keep canonical actions only. Do not add legacy aliases for removed actions; removed actions should stay rejected by validation.
- Keep the multi-survivor rescue and triage loop clear: detect, prioritise, free if trapped, reassure, survey, stabilise, evacuate, notify, report.
- Preserve target-specific survivor actions using survivor ids such as `survivor_office`.
- Keep the UI full-state Mission Control / Replay Dashboard separate from the restricted structured observation that agents receive.
- Prefer focused tests for any change to environment logic, validation rules, survivor state, task success, or scoring.
- Keep graphics and UI simple; the internship challenge is the agent-environment harness.
- Prefer small, controlled, reviewable changes over rewrites.
