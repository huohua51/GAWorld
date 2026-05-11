# Repository Guidelines

## Project Structure & Module Organization
- Core simulator: `generative_city_sim.py` (CLI entrypoint, agent loop, LLM routing, scheduling, actions, logging, plots).
- Configuration: `config.py` (LLM providers, routing, simulation params, data paths, events).
- Environment events: `environment.py`.
- Data assets: `data/hangzhou_agents_state_init.csv`, `data/hangzhou_profiles_with_names.md`, `data/citymap.md`.
- Map generator: `scripts/generate_citymap.py` (build a new `data/citymap.md` from a text description).
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
  - `python scripts/generate_citymap.py --description "a small city with about 1000 residents, in east china"`

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


<claude-mem-context>
# Memory Context

# [GAWorld] recent context, 2026-05-11 7:44pm GMT+2

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 28 obs (6,443t read) | 1,471,078t work | 100% savings

### Apr 29, 2026
18 6:44a 🔵 Avatar generation not functioning
19 " 🔵 Avatar SVG files exist on disk but not rendering in UI
20 " 🔵 HTTP server root mismatch prevents avatar loading
21 6:45a 🔴 Generated missing avatar SVGs for all 51 agents
28 7:05a 🔴 人生事件在网页面板中未显示
29 " 🔴 为网页面板添加人生事件 API 端点
31 " 🔴 人生事件 UI 面板完整实现
32 " 🔴 人生事件面板交互逻辑与自动刷新完整落地
34 7:06a 🔵 人生事件在模拟引擎中的完整数据流确认
35 " 🟣 新增 tests/test_life_events.py 单元测试
36 " 🔵 人生事件面板验证上线
### May 11, 2026
300 7:30p 🔄 Project file and folder structure reorganization
301 " 🔵 GAWorld project structure inventory
303 " 🔵 config.py structure and dependencies mapped
304 " 🔵 gaworld/ typed config wrapper and migration status
302 7:31p 🔵 Large files and directory structure identified
305 7:32p ⚖️ Plan: split root config.py into gaworld/settings/ submodules
306 " 🟣 Project file organization and refactoring initiated
307 7:40p 🔄 Settings module split: runtime.py → behavior.py
308 " 🔄 Tests and project structure docs added
309 " 🔵 Import smoke test passes after settings refactor
310 7:41p 🔵 CONFIG content equivalence verified via git diff
311 " ✅ pyproject.toml pythonpath fixed for pytest module discovery
312 " 🔵 All 7 tests pass after settings refactor
313 " 🔵 Pre-existing pytest collection errors in test suite
314 7:42p 🔴 tests/__init__.py added to enable fixtures subpackage import
315 " 🔵 Full test suite: 282 passed, 2 pre-existing failures
316 " 🔄 Settings refactor complete: config.py reduced from 631 to 12 lines

Access 1471k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>
