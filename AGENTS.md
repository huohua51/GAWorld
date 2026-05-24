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

# [GAWorld] recent context, 2026-05-24 7:29pm GMT+2

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (11,709t read) | 2,844,292t work | 100% savings

### May 16, 2026
471 6:01a 🔵 Config fix successful - 5 agents now running
473 6:32a 🟣 Academic paper written on misinformation spread research
### May 18, 2026
493 8:24p 🔵 Treatment B Experiment Data Validated
494 " 🔵 Agent 4 Information Isolation Pattern Confirmed
495 " 🔵 Agent 2 Stance Score Time-Series Drift
496 8:25p 🔵 Experiment Framework Available for Polarization and Emotion Contagion Studies
498 " 🔵 Unified Experiment Runner Framework with 9 Registered Experiments
502 " 🔴 Experiment Directory Creation Bug Confirmed - Still Unfixed
500 8:26p 🔴 Experiment Runner Directory Creation Bug in exp_polarization.py
504 " 🔴 Edit Attempt Shows userModified:false - Fix Not Applied
505 " 🔴 Fix Not Applied - All Experiment Scripts Have Same Bug
520 8:36p 🟣 Second Experiment and NeurIPS Paper Writing
521 " 🟣 Polarization Experiments Launched in Parallel
524 " 🟣 New Experiment Session Started
525 8:41p 🟣 exp_polarization Experiment Running
527 " 🟣 Second experiment in progress with NIPS paper output
529 8:51p ⚖️ Second experiment with NeurIPS paper output
531 8:52p 🟣 Second Experiment Running with NIPS Paper Generation
526 " ✅ Polarization Experiment Metrics Updating
533 9:02p 🔴 Fixed missing treatment attribute in analyze_experiment()
528 " 🔵 GAWorld polarization experiments running in parallel
530 9:12p 🟣 Polarization experiment running dual conditions
532 9:23p 🔵 Polarization Experiment Running with Dual Conditions
### May 19, 2026
534 3:13a 🟣 Created NeurIPS-format paper for polarization experiment
535 6:20p 🔵 Skills marketplace contains oba/superpowers collection
536 " ✅ Installed obra/superpowers@brainstorming skill globally
537 " ✅ Installed remaining 5 obra/superpowers skills globally
538 6:21p ✅ Installed systematic-debugging skill
539 " ✅ Installed writing-plans skill
540 " ✅ Installed requesting-code-review skill
541 6:22p ✅ Completed obra/superpowers collection - all 6 skills installed
542 " 🟣 Planning multi-agent research team for Experiment 3
543 " 🔵 GAWorld project contains 9 experiment modules
544 6:40p 🔵 GAWorld research vision documented in ideas.md
545 " 🔵 GAWorld unified experiment runner framework discovered
546 " 🔵 Exp_emotion_contagion selected as experiment for multi-agent team
547 7:07p ⚖️ Simulation duration reduced from 150 to 50 days
548 " 🟣 Multi-agent research team specification created
549 7:08p 🟣 Multi-agent research team implementation plan created
550 7:19p 🔵 generative_city_sim.py requires subcommand syntax
551 " 🔵 generative_city_sim.py requires subcommand syntax
552 " 🟣 Multi-agent research team architecture designed for GAWorld experiments
553 7:33p 🔵 50-day macro economy simulation is actively running
554 7:36p 🔵 Simulation runs full 24-hour day cycles per simulation day
555 7:41p 🔵 50-day simulation process has stopped
556 7:52p ⚖️ User chose 3-day simulation test to verify base simulator functionality
S161 Found generative_city_sim.py entry point is `_main` not `main` - import test failed (May 19 at 8:03 PM)
S162 Found key insight: simulation works when called directly but not via subprocess (May 19 at 8:08 PM)
S163 1-day simulation with 2 agents is running but only produces initialization data (May 19 at 8:08 PM)
S164 Simulation is running but slow due to LLM calls - proposing switch to exp_polarization (May 19 at 8:10 PM)
S165 Simulation running in background (PID 69881) - also checking exp_polarization data availability (May 19 at 8:12 PM)
557 8:13p ⚖️ User chose to run 3-day simulation in background with nohup
S167 Examining exp_polarization intervention metrics data in detail (May 19 at 8:13 PM)
558 8:14p 🟣 Multi-agent research team launched with exp_polarization data
S168 多智能体研究团队完成exp_polarization实验并撰写论文 (May 19 at 8:14 PM)
S166 Multi-agent research team launched with exp_polarization data - two background tasks running (May 19 at 8:14 PM)
S170 多智能体研究团队完成exp_polarization实验，后台exp_macro_economy仿真运行中 (May 19 at 8:15 PM)
559 8:16p 🔵 多智能体研究团队完成exp_polarization实验
560 " 🔵 exp_macro_economy后台仿真正在运行
### May 20, 2026
S169 多智能体研究团队完成exp_polarization实验并撰写论文 (May 20 at 4:25 AM)
**Investigated**: 探索了GAWorld平台上的exp_polarization实验数据，研究多样性干预对在线极化的影响。

**Learned**: 1) 多样性干预可能适得其反：干预组极化(1.514)高于控制组(1.462)+3.6%；2) Agent 4完全隔离：20%智能体零立场、零跨观点曝光；3) 方差降低≠极化减少。

**Completed**: 1) superpower技能安装完成；2) 4角色多智能体团队(Experimenter/Data Analyst/Paper Writer/Paper Reviewer)；3) exp_polarization数据验证；4) polarization_paper.md(234行)生成；5) shared_state.json更新为approved状态。

**Next Steps**: 3天仿真实验(PID 69881)在后台继续运行。


Access 2844k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>
