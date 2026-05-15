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

# [GAWorld] recent context, 2026-05-15 7:01pm GMT+2

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (12,445t read) | 3,572,306t work | 100% savings

### May 11, 2026
307 7:40p 🔄 Settings module split: runtime.py → behavior.py
309 " 🔵 Import smoke test passes after settings refactor
310 7:41p 🔵 CONFIG content equivalence verified via git diff
311 " ✅ pyproject.toml pythonpath fixed for pytest module discovery
312 " 🔵 All 7 tests pass after settings refactor
313 " 🔵 Pre-existing pytest collection errors in test suite
314 7:42p 🔴 tests/__init__.py added to enable fixtures subpackage import
315 " 🔵 Full test suite: 282 passed, 2 pre-existing failures
316 " 🔄 Settings refactor complete: config.py reduced from 631 to 12 lines
344 8:38p 🟣 为智能体增加兴趣爱好系统
345 " 🔵 GAWorld项目结构和关键模块概览
346 " 🔵 智能体选择动作的决策系统架构
348 8:40p 🔵 Remotion plugin skill structure documented
349 " 🔵 GAWorld project structure overview
350 " 🔵 docs/TUTORIAL.md - Chinese user tutorial documented
351 " 🔵 CHANGELOG.md reveals recent major features and architecture
352 " 🔵 GAWorldIntro.tsx scene structure revealed
354 " 🟣 GAWorldTutorialCN.tsx Chinese tutorial video created
355 8:43p ✅ Root.tsx updated to register two compositions
356 " ✅ package.json render scripts updated for dual video output
357 " 🔴 TypeScript/esbuild error in GAWorldTutorialCN.tsx line 385
358 " 🔴 Fixed JSX parsing error in GAWorldTutorialCN.tsx line 385
359 " 🔵 GAWorldTutorialCN still frame rendered successfully
360 " 🟣 Remotion中文教程文档编写
361 " 🟣 Remotion GAWorld中文教程视频帧渲染
### May 13, 2026
386 7:59p 🔵 GAWorld 项目现有文档结构
387 " 🔵 GAWorld 项目完整技术栈梳理
S130 为GAWorld项目创建文档：初学者教程（~20页）和科学研究方向头脑风暴 (May 13 at 8:06 PM)
S129 为GAWorld项目撰写面向零基础初学者的中文详细教程（20页左右，含图片和表格，md格式） (May 13 at 8:06 PM)
S131 Continue creating experiment proposals from ideas.md brainstorming document (May 13 at 8:11 PM)
### May 14, 2026
392 6:03p ⚖️ Research Experiment Workflow Established
394 " 🔵 EXP-INFO-001 Misinformation Spread Proposal Content
395 " 🔵 4 Research Proposal Details Analyzed
393 6:04p 🔵 9 Research Proposal Experiments Identified
396 6:06p 🔵 GAWorld Infrastructure Analysis Complete
397 " 🔵 EXP-TRANS-001 Transportation Behavior Proposal
398 " 🟣 GAWorld Experiment Framework Established
399 6:38p 🔵 Unified Experiment Runner Framework exists with 9 registered experiments
400 " 🔴 Experiment directory creation missing in base ExperimentRunner
402 6:42p 🔴 Fixed mkdir in exp_memory_consistency.py run method
401 6:43p 🔴 Fixed missing directory creation in exp_misinfo_spread.py run method
403 6:45p 🔴 Fixed exp_abm_validation.py missing mkdir in run method
404 " 🔵 Experiment framework uses non-existent CLI arguments for simulation
405 6:46p 🔴 Fixed experiment runner CLI incompatibility using environment variables
406 " 🔵 Simulation requires reset before first run after model changes
407 " 🔵 Memory model version check fails with per-experiment memory_dir override
408 " ⚖️ 实验框架搭建决策：隔离操作规范
412 " 🔵 Memory Model Version System with Compatibility Enforcement
413 " 🟣 Per-Experiment Memory Directory Isolation
414 6:56p 🔵 Experiment Framework Creates Isolated Output Directories
409 " 🔵 Memory Model Version Control机制发现
410 " ✅ 实验运行器恢复memory_dir配置覆盖
411 " 🔵 GAWORLD_CONFIG_OVERRIDES环境变量机制
S132 Run research experiments from docs/proposals - established experiment framework with 9 experiment scripts and unified runner (May 14 at 7:02 PM)
**Investigated**: Explored docs/proposals directory structure, checked simulation configuration system, examined memory model versioning, tested simulation execution with config overrides

**Learned**: - GAWorld uses memory_model_version tracking (currently version 3) with _enforce_memory_model_compat() validation
    - Each experiment needs isolated memory directory to prevent version conflicts
    - Simulation CLI doesn't support --sim-days directly - requires GAWORLD_CONFIG_OVERRIDES environment variable
    - Full simulations take 5+ minutes even for 2-day runs

**Completed**: - Created 9 experiment scripts in docs/proposals/experiments/ covering: misinformation spread, polarization, macro economy, emotion contagion, memory consistency, network evolution, policy framework, transport behavior, ABM validation
    - Built run_experiment.py unified framework with --list, --run, --analyze, --compare actions
    - Created docs/proposals/results/ directory structure for experiment outputs
    - Experiment output dirs (e.g., exp_misinfo_spread/control/) contain experiment_config.json and isolated memory subdirectories

**Next Steps**: Manual test of single experiment to validate output format, then either adjust experiment scripts or reduce default simulation days (14→2-3) for faster iteration before running all 9 experiments


Access 3572k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>
