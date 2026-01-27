# Repository Guidelines

## Project Structure & Module Organization
- Core simulator: `generative_city_sim.py` (CLI entrypoint, agent loop, LLM routing, scheduling, actions, logging, plots).
- Configuration: `config.py` (LLM providers, routing, simulation params, data paths, events).
- Environment events: `environment.py`.
- Data assets: `hangzhou_agents_state_init.csv`, `hangzhou_profiles_with_names.md`, `citymap.md`.
- Outputs: `output/` (logs, memory, plots, CSVs). Treat as generated artifacts.
- Backups: `backup/` (historical scripts; not part of active runtime).

## Build, Test, and Development Commands
- Install deps: `pip install -r requirements.txt`
- Run simulation: `python generative_city_sim.py run`
- Interview an agent:
  - `python generative_city_sim.py interview --agent-id 31 --question "Question"`
  - `python generative_city_sim.py interview --agent-id 31 --questions-file questions.txt`

There is no build step beyond installing Python dependencies.

## Coding Style & Naming Conventions
- Python-only repo; follow standard PEP 8 conventions.
- Indentation: 4 spaces, no tabs.
- Naming: `snake_case` for functions/vars, `UpperCamelCase` for classes, constants in `ALL_CAPS`.
- No formatter or linter is configured; keep changes minimal and consistent with existing style.

## Testing Guidelines
- No automated test suite is present.
- If adding tests, place them under a new `tests/` directory and use `test_*.py` naming.
- Prefer lightweight, reproducible tests (mock LLM calls and avoid network dependencies).

## Commit & Pull Request Guidelines
- Existing history uses short, lowercase summary messages (e.g., `updated`, `sync`, `requirement`). Keep commits concise and imperative.
- PRs (if used) should include: scope summary, config changes, and any new runtime outputs avoided or ignored.

## Security & Configuration Tips
- Do not hardcode API keys in `config.py`; use environment variables (e.g., `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).
- Keep generated files out of commits (`output/` content should usually remain local).
