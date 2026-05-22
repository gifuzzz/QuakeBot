# AGENTS.md

- Keep this project dependency-light; prefer the Python standard library unless a dependency clearly improves the harness.
- Run `pytest` before finalising changes.
- Preserve structured observations and structured JSON-like actions.
- Do not let agents mutate environment state directly. All state transitions must go through `QuakeBotEnv.step`.
- Keep the multi-survivor rescue and triage loop clear: detect, prioritise, free if trapped, reassure, survey, stabilise, evacuate, notify, report.
- Preserve target-specific survivor actions using survivor ids such as `survivor_office`.
- Prefer focused tests for any change to environment logic, validation rules, survivor state, task success, or scoring.
- Keep graphics and UI simple; the internship challenge is the agent-environment harness.
