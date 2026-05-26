# Repository Guidelines

## Project Structure & Module Organization

```
GAWorld/
├── gaworld/                  # 核心包（所有功能的正式实现）
│   ├── apps/                 # 服务器与可视化（dashboard, visualizer, …）
│   ├── behavior/             # 动态行为模块（dynamic.py）
│   ├── cognition/            # 人类真实感模块（realism.py）
│   ├── core/                 # Agent 基础与并发执行（agent.py, runner.py）
│   ├── distributed/          # 分布式通信（comm.py）
│   ├── economy/              # 经济模块（finance.py）
│   ├── env/                  # 环境系统（system.py）
│   ├── events/               # 生命事件（life.py）
│   ├── io/                   # IO 工具（avatar.py, http_guard.py, web_scrape.py）
│   ├── llm/                  # LLM 提供商（providers.py）
│   ├── memory/               # 记忆系统（store, experience, consolidation, decay, …）
│   ├── policy/               # 干预策略（intervention.py）
│   ├── settings/             # 配置（CONFIG, defaults, overrides）
│   ├── skills/               # 技能系统（schemas, registry, consolidation）
│   ├── sim/                  # 仿真逻辑（_action, _cognition, _location, …）
│   ├── social/               # 社交网络（network.py）
│   ├── work/                 # 工作模块（router, queue, market, adapters）
│   ├── world/                # 城市地图（city_map.py）
│   ├── hooks.py              # 生命周期钩子（HookBus）
│   ├── interests.py          # 兴趣与成长档案
│   └── logging_setup.py      # 日志配置
├── generative_city_sim.py    # CLI 入口（run / reset / interview）
├── legacy/                   # 旧版 flat 模块（已弃用，不参与构建）
├── scripts/                  # 辅助脚本（generate_citymap, …）
├── tests/                    # 测试套件（pytest）
├── data/                     # 数据资产（agents CSV, profiles MD, citymap MD）
└── output/                   # 生成产物（日志、记忆、图表）
```

**规则：新代码只写进 `gaworld/` 包，不添加新的根目录模块。**
旧 flat 模块的正式位置见 `legacy/README.md`。

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
- All new code goes into `gaworld/` sub-packages. No new root-level modules.
- Import from `gaworld.*` directly; the `legacy/` shims are deprecated and excluded from the build.

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

# [GAWorld] recent context, 2026-05-26 5:05am GMT+2

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (12,479t read) | 2,882,786t work | 100% savings

### May 18, 2026
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
557 8:13p ⚖️ User chose to run 3-day simulation in background with nohup
558 8:14p 🟣 Multi-agent research team launched with exp_polarization data
559 8:16p 🔵 多智能体研究团队完成exp_polarization实验
560 " 🔵 exp_macro_economy后台仿真正在运行
### May 20, 2026
S180 Multi-agent research team for GAWorld Experiment 4 (exp_network_evolution) (May 20 at 4:25 AM)
### May 24, 2026
S181 Multi-agent research team for GAWorld Experiment 4 (exp_network_evolution) (May 24 at 8:14 PM)
S184 Multi-agent research team completing GAWorld Experiment 4 (exp_network_evolution) - network evolution analysis (May 24 at 8:15 PM)
S185 Multi-agent research team completing GAWorld Experiment 4 (exp_network_evolution) - network evolution analysis with 4 agents (May 24 at 8:16 PM)
S182 Multi-agent research pipeline for GAWorld exp_network_evolution - Paper Writer completed outline, Data Analyst analyzing results (May 24 at 8:16 PM)
S183 GAWorld multi-agent research pipeline: Paper Writer outline done, Data Analyst analyzing network metrics (May 24 at 8:16 PM)
S186 Multi-agent research team for GAWorld exp_network_evolution - verifying experiment output files (May 24 at 8:16 PM)
S187 构建多智能体研究小组完成实验4的网络演化分析 (May 24 at 8:16 PM)
602 8:17p 🟣 Multi-agent research team architecture for experiment 4
603 8:18p 🔵 agent_5_schedule.json file missing from natural_evolution experiment
604 8:20p 🔵 exp_network_evolution.py and generative_city_sim.py running concurrently
605 8:25p 🔵 natural_evolution experiment actively writing agent memory files
607 " 🟣 Multi-agent research team framework for experiment 4
606 " 🔵 exp_network_evolution.py running with active agent log updates
608 8:37p 🔵 Multi-agent experiment 4 execution in progress
612 " 🔵 Network analysis completed for natural_evolution experiment
613 " 🔵 Log parsing bug: [InitLocation] lines contain empty home/work fields
### May 25, 2026
611 3:49a 🔴 日志解析修复成功
S188 多智能体研究小组完成实验4初步网络分析 (May 25 at 3:49 AM)
616 3:57a 🔵 Simulation process still running at PID 30636
617 4:00a 🔵 Simulation DID run Day 1 with actual interactions—earlier analysis missed them
618 4:01a 🔵 Simulation stalled at Day 1 despite process still running
620 " 🟣 Paper draft written for network_evolution experiment
621 " 🟣 Chinese academic paper expansion requested at ~8000 characters
S189 多智能体研究小组完成exp_network_evolution实验（网络演化+同质性分析） (May 25 at 4:01 AM)
622 " 🟣 Chinese academic paper completed at ~8500 characters

Access 2883k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>
