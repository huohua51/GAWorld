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

# [GAWorld] recent context, 2026-06-13 1:39pm GMT+8

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (23,304t read) | 0t work

### Jun 6, 2026
836 12:49a 🔵 Job training subsidy policy comparison report details
837 " 🔵 Network evolution natural_evolution experiment configuration
838 " 🔵 Macro economy wellbeing dynamics: 3-day agent study findings
839 " 🔵 Memory consistency experiment: 4 treatments designed, Phase 2 stalled in 3 of 4
846 12:51a 🔵 Polarization diversity intervention produced null/inverse result
847 " 🔵 Medical reform policy effect is near-zero (weakest of all 4 policies)
848 " 🔵 Policy intervention strength ranking from comparison CSVs
849 " 🔵 Network evolution natural_evolution interrupted at Day 1 with sparse network
850 " 🔵 Memory consistency comparative study details: agent 34 (徐桂兰) as test subject
851 " 🔵 Transport behavior rain weather effects quantified
852 12:52a 🔵 Misinformation intervention reward buffering quantified
853 " 🔵 Polarization experiment state file confirms 9.0% stance variance reduction and +3.6% polarization increase
854 " 🔵 EXP-VAL-001 ABM validation framework: real-world Hangzhou benchmarks
855 " 🔵 EXP-EMO-001 emotion contagion: 4 treatments with seeding design
856 " 🔵 Unified runner ExperimentRegistry: 9 experiments with planned treatments and durations
857 " 🔵 EXP-INFO-001 misinfo proposal: H1-H4 hypotheses and experimental design
860 " ⚖️ Primary session pivots from retrospective summary to executing EXP-EMO-001 and EXP-VAL-001
S258 总结已运行的GAWorld仿真实验，生成结构化markdown报告（研究问题、设计、运行、结果、发现），供后续分析与撰写参考 (Jun 6 at 12:52 AM)
S260 Continue execution of two unrun experiments (EXP-EMO-001 emotion contagion, EXP-VAL-001 ABM validation) per user request "继续完成两个尚未运行的实验" (Jun 6 at 12:55 AM)
S261 完成两个未运行的实验 (EXP-EMO-001 情绪传染 + EXP-VAL-001 ABM验证) (Jun 6 at 1:25 AM)
861 1:26a 🟣 EXP-EMO-001 and EXP-VAL-001 launched as background tasks (3-day smoke tests)
862 " 🔵 Observer harness appears to re-feed identical tool sequences 9 seconds apart
863 1:34a 🔵 REFERENCE_BENCHMARKS is a module-level dict in exp_abm_validation.py
864 " 🔵 EXP-EMO-001 control background task bmz7pqjrl still running, no output after 12s
865 " 🔵 EXP-EMO-001 seed_agents target out-of-range agent IDs in TREATMENTS config
866 1:38a 🔴 EXP-EMO-001 control background task hung for 5+ minutes with empty output
867 1:39a 🔵 Both experiments are producing real output despite empty stdout
868 " 🔵 State CSV output is gated behind per-step flush, not directory creation
870 " 🔵 Primary session has path bug: looking for timeline.jsonl in logs/ but it lives in environment/
871 " 🔴 EXP-VAL-001 failed: LLM API returned HTTP 500 with "new_sensitive" content filter
872 " 🔵 EXP-VAL-001 silently degrades on missing economy_module and generate_agent_rag_seed
873 " 🔵 LLM provider configuration: only 1 provider, no fallback chain
869 1:40a 🔵 Per-agent logs exist but environment/timeline.jsonl is empty
874 1:50a 🔴 Primary session fixed state-CSV schema mismatch in both experiment analyzers
875 " 🔵 Transport mode data source: environment/agent_*.log not state/agent_state_history.csv
876 1:51a 🔵 Primary session confirmed 17 prior experiments produced state/agent_state_history.csv files
877 " 🔴 Primary session discovered ledger uses engel_coefficient (alternative spelling), not engels_coefficient
879 " 🔴 Emotion contagion simulation stalled at Day 1 08:32 for 10+ minutes
878 1:52a 🔵 Emotion contagion simulation is alive: Day 1 timeline has 4 events with rich detail
880 2:01a ⚖️ Primary session killed the stalled emotion contagion run after 28:49
881 " 🔵 hangzhou_agents_state_init.csv uses WIDE format with BOM; runtime state CSV is LONG format
882 " ⚖️ Primary session pivots to EXP-VAL-001 after killing EXP-EMO-001
883 2:03a 🟣 Primary session launched master run: all 4 EMO treatments + ABM validation in single task bzeah2mry
884 " 🔵 Cleanup script wipes prior partial results before relaunch
S263 继续等待 - 持续监控 bzeah2mry 后台仿真任务, 回应"进展如何"进度检查 (Jun 6 at 2:04 AM)
S264 持续监控 bzeah2mry 仿真任务, 多次轮询检查状态, 决定进入 20 分钟轮询模式 (ScheduleWakeup) (Jun 6 at 7:48 AM)
S262 进展如何 - 检查 EXP-EMO-001 (4 treatments) 和 EXP-VAL-001 的运行状态 (Jun 6 at 7:48 AM)
S265 持续监控 bzeah2mry, 诊断 SSL 重试循环导致仿真拖慢, 主会话向用户提出 4 个选项 (Jun 6 at 7:59 AM)
S267 用户决策"重试" — 主会话准备重跑实验, 复检 bzeah2mry 状态确认需要新启动 (Jun 6 at 8:00 AM)
885 9:09a 🔵 LLM API DNS resolution failure killed all experiment runs
S266 实验全面失败 — 所有 5 个仿真 (4 EMO + 1 ABM) 因 DNS 故障无法完成, 主会话向用户报告状态并提供重跑脚本 (Jun 6 at 9:09 AM)
886 " 🔵 All experiments produced zero state CSVs before DNS failure
887 10:39a 🔵 Network restored; cleanup triggered automatic directory recreation
888 " ✅ Parallel background tasks launched for retry with reduced days
889 10:40a ✅ 4 parallel Python processes running for EMO+ABM retry
891 " ✅ EMO control treatment advancing — Day 1 00:28 in 11 minutes wall-clock
892 " 🔵 Timeline writes throttled to ~hourly sim time, agent logs are per-action
890 " 🔵 LLM calls now succeeding — agent preferences being generated
893 10:50a ✅ Both experiments advancing — EMO at Day 1 08:32, ABM at 2 timeline entries
S268 用户"重试"决策后, 主会话成功启动两个并行 bgtask, EMO 推进到 Day 1 08:32, ABM 启动并产出 timeline 数据 (Jun 6 at 10:58 AM)
**Investigated**: - 网络恢复确认: curl https://api.minimaxi.com 返回 404 HTML 而非 DNS 错误
    - 清理策略: 先 import-based 删除 (recreate 副作用), 再 pure-shutil 二次清理成功
    - 重试策略: 启动两个并行 bgtask bzidxzfmr (EMO 4 treatments, days=5) + bhvlxcm54 (ABM validation, days=7)
    - 进程数: 4 个 generative_city_sim 进程 (2 父 bgtask + 2 子 simulation)
    - EMO control 进度: 00:28 → 08:32 (8h 4min 模拟时间), 3 行 timeline
    - ABM validation 进度: 2 行 timeline 启动
    - 4 个 EMO treatment 目录: 只有 control/ 在运行

**Learned**: - **网络恢复后 LLM API 真实可用**: agent_1.log 输出结构化偏好数据 (编程技能 priority 0.68, 运动 priority 0.60) 证明 API 返回有效内容
    - **Timeline 写入与 agent log 写入节奏不同**: agent log 持续更新, timeline 约每小时模拟时间才刷一次 (throttled)
    - **Timeline 与 agent log 的 mtime 差异**: 揭示 timeline writer 全局锁/批量 flush 行为
    - **推进速度估算**: 8h 模拟时间 / ~3-4 min wall-clock ≈ 120x realtime (比 bzeah2mry 估算的 0.39x 显著更好)
    - **降低天数有效**: 5 天 vs 原 14 天, 7 天 vs 原 30 天, 大幅减少暴露在 API 风险下的时间窗口
    - **并行策略有效**: EMO 和 ABM 同步推进, 互不阻塞
    - **状态 CSV 仍在等待**: state/ 目录尚未生成, 需要每个 treatment 完成才会落盘
    - **Timeline throttling rate**: ~1 entry per ~30-60 sim minutes, 跟 bzeah2mry run 的 101 entries / 4 days 一致

**Completed**: - 网络健康检查 ✅
    - 旧失败结果清理 ✅
    - 重试命令准备 (5-7 天简化版) ✅
    - 两个并行 bgtask 启动并运行中 ✅
    - EMO control 推进至 Day 1 08:32 (3 行 timeline)
    - ABM validation 启动并产出 2 行 timeline
    - 实时监控机制建立 (timeline + agent log + 进程数)

**Next Steps**: - 继续等待 EMO control 跑完 Day 1 → Day 5 (预计 45 min - 1.5h)
    - 完成后 4 个 EMO treatment 顺序执行 (control → happy → sad → sparse)
    - ABM validation 7 天并行进行
    - 每 5-10 分钟检查 timeline 进度
    - 关注: 是否有新的网络中断, 是否有 step_history 持久化触发
    - 最终: 跑 compare_treatments() + generate_report()
</claude-mem-context>
