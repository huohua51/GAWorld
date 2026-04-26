# Repository Guidelines

## Project Structure & Module Organization
- Core simulator: `generative_city_sim.py` (CLI entrypoint, agent loop, LLM routing, scheduling, actions, logging, plots).
- Configuration: `config.py` (LLM providers, routing, simulation params, data paths, events).
- Environment events: `environment.py`.
- Data assets: `hangzhou_agents_state_init.csv`, `hangzhou_profiles_with_names.md`, `citymap.md`.
- Map generator: `generate_citymap.py` (build a new `citymap.md` from a text description).
- Outputs: `output/` (logs, memory, plots, CSVs). Treat as generated artifacts.
- Backups: `backup/` (historical scripts; not part of active runtime).

## Build, Test, and Development Commands
- Install deps: `pip install -r requirements.txt`
- Run simulation: `python generative_city_sim.py run`
- Reset simulation (clear caches/logs and restart day count): `python generative_city_sim.py reset`
- Interview an agent:
  - `python generative_city_sim.py interview --agent-id 31 --question "Question"`
  - `python generative_city_sim.py interview --agent-id 31 --questions-file questions.txt`
- Generate a new city map:
  - `python generate_citymap.py --description "a small city with about 1000 residents, in east china"`

There is no build step beyond installing Python dependencies.

## Coding Style & Naming Conventions
- Python ≥ 3.11; follow standard PEP 8 conventions.
- Indentation: 4 spaces, no tabs.
- Naming: `snake_case` for functions/vars, `UpperCamelCase` for classes, constants in `ALL_CAPS`.
- Formatter / linter / type-checker are configured in `pyproject.toml`:
  - `ruff check .` and `ruff format --check .` (rules pinned to `E`/`F`/`W`/`I`/`UP`/`B`/`C4`/`SIM`/`PIE`/`RUF`).
  - `black .` (line length 110).
  - `mypy gaworld` (strict typing on the new `gaworld/` tree, advisory elsewhere).
- New cross-cutting code lives under `gaworld/` (see `CHANGELOG.md` for the migration map).

## Testing Guidelines
- Tests live under `tests/` and use `pytest` discovery (`test_*.py`).
- Run locally: `pytest tests` (or `python -m unittest discover -s tests -p 'test_*.py'`).
- New code MUST be covered by tests in the same PR; coverage is reported by `pytest-cov` in CI.
- Prefer lightweight, reproducible tests: mock LLM calls (`call_llm`) and avoid real network IO.

## Commit & Pull Request Guidelines
- Existing history uses short, lowercase summary messages (e.g., `updated`, `sync`, `requirement`). Keep commits concise and imperative.
- PRs (if used) should include: scope summary, config changes, and any new runtime outputs avoided or ignored.

## Security & Configuration Tips
- Do not hardcode API keys in `config.py`; use environment variables (e.g., `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).
- Keep generated files out of commits (`output/` content should usually remain local).
