# GAWorld

GAWorld 是一个面向“城市社会行为实验”的生成式多智能体仿真项目。
它将人物画像、社会网络、环境扰动、政策事件与 LLM 决策过程结合起来，
用于观察个体行为、群体状态和长期演化的变化轨迹。

## 项目介绍

GAWorld 的核心目标不是“随机跑一群 Agent”，而是构建一个可对照、可回放、可扩展的社会实验场：

- 你可以定义事件（如限行、平台新规、就业冲击）并观察其影响。
- 你可以让同一批 Agent 在“有事件/无事件”两种场景并行运行，再做结果比较。
- 你可以保留跨天记忆，让 Agent 的行为逐步体现经验累积、习惯形成和关系变化。

该项目适合用于：

- 城市治理与政策影响的快速仿真验证
- 社会行为、风险传播、舆情响应的机制探索
- AI 社会模拟、复杂系统课程或研究演示
- Agent 记忆架构与行为一致性的工程实验

## What It Simulates

At runtime, each agent repeatedly goes through:

1. perception (context awareness)
2. planning (short-horizon intent)
3. action selection (state + memory + location + habit bias)
4. reflection (experience update)

Across days, GAWorld accumulates:

- episodic memories (structured events)
- long-term summaries
- habit strengths by time/location/activity context
- social relationship strength shifts

## Features
- Agent construction from CSV state seeds + Markdown profiles.
- Multi-backend LLM routing (Ollama / OpenAI / Anthropic-compatible).
- Daily schedule generation, action selection, and reflection loops.
- Weekday/weekend-aware daily routine generation with behavior differences.
- Policy events with inferred effects on agent state.
- Environment event system (natural + social events).
- External dynamic environment simulation (natural/economic/political/technology).
- Social network creation and emotion diffusion.
- Stateful memory and logs across runs.
- Pluggable economy module (currency, income/expense, savings/assets, wealth pursuit).
- External RAG info injection (timestamped), ingestible from CLI or files.
- Location-aware actions with per-agent, per-location LLM biasing.
- Time-aware location resolution (home at night, workplace during day with flexibility).
- City map generation from natural language descriptions.
- Reset command to clear stateful caches/logs and restart from day 1.
- Visualizations for social networks and state evolution.

## Project layout
- `generative_city_sim.py` main simulator + CLI entrypoint.
- `config.py` runtime configuration (LLM routing, sim params, data paths, events).
- `environment.py` environment event generator.
- `environment_config.json` environment and external environment configuration.
- `external_environment_server.py` standalone HTTP backend for shared external environment state.
- `hangzhou_agents_state_init.csv` seed state values per agent.
- `hangzhou_profiles_with_names.md` detailed agent profiles.
- `citymap.md` village map (hubs + nearby locations).
- `generate_citymap.py` city map generator (from text descriptions).
- `output/` simulation artifacts (logs, memory, plots, CSVs).
- `site/` static project-intro website (`index.html`, `styles.css`).
- `extensibility.py` hook dispatcher for custom lifecycle functions.
- `custom_hooks.py` example custom hook functions.
- `experience_store.py` structured episodic memory persistence.
- `human_realism.py` behavior realism helpers (needs/habits/intentions/consolidation).
- `economy_module.py` pluggable economy/wealth system via lifecycle hooks.

## Quickstart
1) Install deps:
```bash
pip install -r requirements.txt
```

2) Configure LLM access in `config.py`:
- Ollama (local): set `ollama_url` and model name.
- OpenAI: set `llm.providers.openai_gpt` and export `OPENAI_API_KEY`.
- Anthropic-compatible: set `llm.providers.claude` and export `ANTHROPIC_API_KEY` (or `api_key_env` you choose).

3) Run the simulation:
```bash
python generative_city_sim.py run
```

4) Open the static intro site (optional):
```bash
cd site
python -m http.server 8080
# then open http://localhost:8080
```

## CLI usage
Run a full simulation (default command when no subcommand is provided):
```bash
python generative_city_sim.py run
```

Reset the simulation (clears memory/logs/caches and restarts day count):
```bash
python generative_city_sim.py reset
```

Interview a specific agent:
```bash
python generative_city_sim.py interview --agent-id 31 --question "Question 1" --question "Question 2"
```

Or from a file with one question per line:
```bash
python generative_city_sim.py interview --agent-id 31 --questions-file questions.txt
```

Optional interview context:
```bash
python generative_city_sim.py interview --agent-id 31 --question "Question" --context "Short background context"
```

Add one external RAG info item (supports optional timestamp):
```bash
python generative_city_sim.py rag-add \
  --agent-id 31 \
  --text "周末更倾向于骑行和逛书店" \
  --timestamp "2026-02-18 09:30" \
  --source "manual"
```

Import external RAG info from file (`.txt/.md/.json/.jsonl`):
```bash
python generative_city_sim.py rag-import \
  --agent-id 31 \
  --file output/test_extra_info.txt \
  --source "profile_notes"
```

`txt/md` examples (one per line or blank-line blocks):
- `[2026-02-10 18:00] 工作日晚上偏好在家做饭`
- `2026-02-12 10:00 | 周末会和朋友去河边慢跑`

Counterfactual event comparison (parallel with/without event):
```bash
python generative_city_sim.py compare-event \
  --event-name "临时交通限行" \
  --event-description "主干道限行导致通勤时间上升并影响出行决策" \
  --event-day 2 \
  --event-time 09:00 \
  --sim-days 3 \
  --llm-provider openai_gpt \
  --seed 42
```

Generate a new city map from a text description:
```bash
python generate_citymap.py --description "a small city with about 1000 residents, in east china"
```

Run external environment backend server (shared by multiple simulations / machines):
```bash
python external_environment_server.py --host 0.0.0.0 --port 8765
```
Override LLM generation mode when needed:
```bash
python external_environment_server.py --no-llm
python external_environment_server.py --use-llm
```

## Configuration guide
All runtime settings live in `config.py`.

### LLM routing
`CONFIG["llm"]` defines providers and routing.
- `providers`: named backends with `type` (`ollama`, `openai`, `claude`/`anthropic`), `model`, `url`/`base_url`, timeouts, and auth options.
- `routing.default`: default provider for tasks.
- `routing.tasks`: override provider per task (e.g., `schedule`, `actions`, `interview`).
- `routing.agents`: optional override by agent id (string key).

### Simulation parameters
- `agent_ids`: list of agent IDs to simulate.
- `sim_days`: number of days to run.
- `seconds_per_day`: wall-clock seconds per simulated day.
- `print_agent_profile`: print each agent profile at startup.
- `time_step_minutes`: optional timeline granularity (e.g., `10`, `120`, `2h`). If unset, uses schedule times only.
- `background`: background context injected into environment descriptions.
- `calendar.start_date`: simulation start date (`YYYY-MM-DD` or `today`), default `today`.
- `calendar.start_weekday`: weekday name for Day 1 (`monday` ... `sunday`).
- `calendar.weekend_days`: which weekdays count as weekend (default `["saturday","sunday"]`).

### External RAG info
- `external_rag.top_k`: number of external info hits injected into prompts.
- Imported/added external info is stored as `entry_type="external_info"` in vector DB and appended into agent memory.
- Timestamp is optional but recommended for time-sensitive facts.
- `external_rag.bootstrap` can seed initial RAG background for a newly initialized agent.
- `external_rag.bootstrap.profile_items`: number of profile-derived background memories/knowledge items.
- `external_rag.bootstrap.web_items`: number of web-selected items to summarize into `external_info`.
- `external_rag.bootstrap.only_when_empty`: only seed when the agent has no existing `external_info`.

### Data sources
- `csv_path`: seed state values.
- `md_path`: detailed profiles.
- `map_path`: village map file (default `citymap.md`).

### Memory & logs
- `stateful`: if true, preserves memory and schedules across runs.
- `memory_dir`: JSON memory/schedule/action/locations per agent.
- `log_dir`: per-agent logs.
- `memory_model_version`: memory schema version marker used for compatibility checks.
- `require_clean_reset_on_memory_model_change`: if true, simulator blocks run until `reset` is executed after a version change.
- `vector_db_path`: sqlite vector store for memory + logs (with `vector_db_dim`, `vector_db_top_k`, `vector_db_max_chars`).

### Human realism
`human_realism` enables day-to-day experience accumulation and more human-like behavior:
- `enabled`: toggle realism enhancements.
- `llm.max_extra_calls_per_agent_day`: cap extra LLM calls for intentions + consolidation.
- `memory.max_episodes_per_agent`: cap per-agent episodic memory entries.
- `memory.daily_consolidation_top_k`: number of salient episodes used for day-end consolidation.
- `memory.salience_threshold`: threshold for high-salience episode selection.
- `memory.decay_half_life_days`: salience decay half-life for older episodes.
- `behavior.habit_learning_rate`: rate of habit strengthening.
- `behavior.inertia_weight`: repeated action/activity inertia bonus.
- `behavior.need_weights`: weights for `energy`, `hunger`, and `social_need` in action choice.

### Economy module
`economy` adds a currency/property layer for each agent:
- `enabled`: toggle the module.
- `currency`: currency symbol/code (default `CNY`).
- `output_dir`: output folder for economy ledgers.
- `hours_per_step`: simulated hours for each timeline step (auto-derived from `time_step_minutes` when present).
- `initial_savings_months_min/max`: initialize savings using monthly-income multiples.
- `rent_income_ratio`, `daily_utilities_cost`, `base_living_cost_per_hour`: baseline housing/living costs.
- `income_volatility`, `min_hourly_income`, `target_work_hours_per_day`: dynamic income controls.
- `asset_safety_days`, `income_seek_threshold`: how strongly low assets trigger income-seeking behavior.
- `income_seek_activities`: preferred activities when a high wealth-drive agent seeks more income.
- `expense_ranges`: category spending ranges (`food`, `clothing`, `housing`, `transport`, etc.).

The module is attached through extension hooks by default:
- `on_simulation_start`
- `on_day_start`
- `on_agent_pre_step`
- `on_agent_post_step`
- `on_day_end`
- `on_simulation_end`

### Policy events
`policy_events` is a list of `{day, time, name, description}`. Effects are inferred via LLM and applied to agent state.

### Environment system
`environment` enables randomized natural/social events per tick:
- `enabled`, `event_chance`, `max_events_per_tick`
- `natural_events` and `social_events` lists
- Environment settings are loaded from `/Users/cw/dev/GAWorld/environment_config.json` by default.

### External dynamic environment
`external_environment` simulates broader external context with structured events:
- `enabled`, `seed`, `max_events_per_tick`
- `generator.mode`: `llm` or `rules` (fallback). In `llm` mode, environment is generated from description, not fixed templates.
- `generator.description`: scenario description used by LLM to synthesize daily environment and evolution rules.
- `generator.history_days`: how many recent day summaries are fed back for temporal evolution.
- `natural`: daily weather + extreme weather alerts
- `economic`: market volatility + macro events
- `political`: policy/governance announcements
- `technology`: platform/tech diffusion events
- `intraday`: short-term shocks for each domain

Generated events are written to `output/environment/timeline.jsonl` and injected into runtime context.
If LLM generation fails or returns invalid JSON, the system automatically falls back to rule-based generation.
You can switch environment config file via `CONFIG["environment_config_path"]` in `/Users/cw/dev/GAWorld/config.py`.

### Remote environment service
To decouple environment simulation from agent simulation, enable remote mode in `environment_config.json`:
- `external_environment_service.enabled`: `true`
- `external_environment_service.base_url`: e.g. `http://10.0.0.8:8765`
- `external_environment_service.timeout`: request timeout seconds
- `environment_server.use_llm`: default LLM mode for backend server (can be overridden by CLI flags)

When enabled, `generative_city_sim.py` fetches day/tick environment state from the server instead of generating it locally.
This allows multiple agent simulators (including on different machines) to share one dynamic environment timeline.

### News / social media
`news` enables optional web reading and memory capture:
- `enabled`: toggle web reading.
- `sources_path`: Markdown file with one URL per line (or Markdown links).
- `cache_path`: JSON cache file for offline reads.
- `use_cache_first`: prefer cache items when available.
- `daily_chance`: probability an agent reads news each day.
- `max_reads_per_day`: max reads per agent per day.
- `timeout`, `max_chars`, `user_agent`: fetch controls.

### Extensibility hooks
`extensions` allows adding new functions without editing the core simulation loop.
- Configure `CONFIG["extensions"]["hooks"]` with lifecycle phases.
- Each hook entry is a `module:function` path importable by Python.
- Set `extensions.strict=true` to fail fast when a hook raises an error.

Supported phases:
- `on_simulation_start`
- `on_day_start`
- `on_time_tick`
- `on_agent_pre_step`
- `on_agent_post_step`
- `on_day_end`
- `on_simulation_end`

Minimal example in `config.py`:
```python
"extensions": {
    "strict": False,
    "hooks": {
        "on_day_start": ["custom_hooks:increase_weekend_mobility"],
        "on_agent_post_step": ["custom_hooks:annotate_low_emotion"],
    },
}
```

## Outputs
Simulation output is written under `output/`:
- `output/logs/agent_<id>.log` event-by-event logs.
- `output/memory/agent_<id>.json` long-term memory.
- `output/memory/agent_<id>_episodes.jsonl` structured episodic memory entries.
- `output/memory/agent_<id>_schedule.json` cached schedules.
- `output/memory/agent_<id>_actions.json` cached action space.
- `output/memory/agent_<id>_locations.json` cached locations.
- `output/memory/agent_<id>_location_action_bias.json` cached location action bias.
- `output/memory/agent_<id>_habits.json` learned context-action preferences.
- `output/memory/agent_<id>_intentions.json` day-level intentions.
- `output/memory/agent_<id>_relationships.json` relationship closeness/trust snapshots.
- `output/memory/sim_state.json` last simulated day for stateful runs.
- `output/memory/vector_db.sqlite` vector memory store (logs + summaries).
- `output/economy/daily_ledger.csv` daily income/expense/balance ledger.
- `output/economy/wealth_snapshot.csv` end-of-run wealth snapshot by agent.
- `output/economy/agents/agent_<id>_ledger.csv` per-agent daily ledger.
- `output/economy/agents/agent_<id>_snapshot.json` per-agent final finance snapshot.
- `output/environment/timeline.jsonl` day/tick external environment timeline.
- `output/network/social_network.png` social graph snapshot.
- `output/state/agent_state_over_time.png` state evolution plot.
- `output/state/agent_state_history.csv` time series data.

## Code organization
- `generative_city_sim.py`: main simulation loop and core domain logic.
- `llm_providers.py`: LLM provider wrappers and routing logic.
- `memory_store.py`: JSON memory/log persistence plus vector DB retrieval.

## Notes on behavior
- Schedule/action generation is LLM-driven with a heuristic fallback.
- Daily routine prompts include weekday/weekend context; weekend routines are profile-driven (job/personality/habits).
- Planning and scheduling prompts retrieve `external_info` entries as additional context.
- Agent state updates blend deterministic rules with small random noise.
- Social influence shifts emotion toward neighbors’ average.
- Location assignment uses `citymap.md` hubs + heuristic role matching and time-aware biasing.

## Security note
Avoid hardcoding API keys in `config.py`. Prefer environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or your custom `api_key_env`) and keep secrets out of source control.

## Troubleshooting
- Missing actions for a schedule: ensure the LLM provider is reachable; cached action spaces can be deleted from `output/memory` to regenerate.
- Empty logs or memory: verify `stateful` and output paths in `config.py`.
- Slow runs: reduce `sim_days`, agents in `agent_ids`, or increase `seconds_per_day`.
