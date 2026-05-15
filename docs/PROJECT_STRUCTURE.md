# Project Structure

GAWorld is mid-migration from a flat script layout to a package layout.
Keep active cross-cutting code in `gaworld/`; keep root modules as stable
CLI/backward-compat entrypoints until their callers have been migrated.

## Active Runtime

- `generative_city_sim.py`: legacy CLI entrypoint and simulator loop.
- `config.py`: compatibility shim that exposes `CONFIG`.
- `data/`: tracked seed data and local baseline inputs.
- `gaworld/settings/`: focused configuration fragments assembled into the legacy `CONFIG` dict.
- `gaworld/core/`: typed core abstractions used by new code.
- `gaworld/io/`: IO helpers such as HTTP guards and web scraping.
- `gaworld/interests.py`: per-agent interest and skill-growth profile derivation, persistence, matching, and progress updates.
- `gaworld/work/`: real-work task routing, queueing, adapters, and market data.
- `gaworld/apps/`: runnable local servers and dashboard backend entrypoints.
- `scripts/`: developer and launch utilities that are not imported by runtime modules.
- `examples/`: sample external-agent inputs and integration examples.

## Configuration Layout

- `gaworld/settings/llm.py`: LLM provider and routing defaults.
- `gaworld/settings/runtime.py`: core simulation, paths, memory, planning, and concurrency defaults.
- `gaworld/settings/environment.py`: external environment, distributed simulation, and OpenClaw defaults.
- `gaworld/settings/behavior.py`: news, intervention, interests, human-realism, and dynamic-behavior defaults.
- `gaworld/settings/economy.py`: personal finance and macro-economy defaults.
- `gaworld/settings/integrations.py`: extension hooks and real-work execution defaults.
- `gaworld/settings/overrides.py`: dashboard, environment file, and `GAWORLD_CONFIG_OVERRIDES` merge logic.

## Data Layout

- `data/hangzhou_agents_state_init.csv`: seed state values.
- `data/hangzhou_profiles_with_names.md`: seed agent profiles.
- `data/citymap.md`: default city map.
- `data/news_source.md` and `data/news_cache.json`: news/RAG seed material.
- `data/environment_config.json`: environment-server override input.

Root-level imports like `from config import CONFIG` remain supported.
New code that needs config assembly should prefer `gaworld.settings`.

## Generated Or Auxiliary Content

- `output/`: generated simulation artifacts, logs, memory, plots, CSVs.
  - `output/memory/agent_<id>_growth.json`: per-agent hobby/skill progress state.
  - `output/memory/growth_profiles.json`: cached LLM-derived growth profiles.
- `site/`: dashboard and visualization frontends.
- `video/`: Remotion video project.
- `tmp/`: local temporary/generated scratch content.
- `backup/`: historical scripts, not active runtime.
