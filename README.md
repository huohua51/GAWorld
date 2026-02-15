# GAWorld

GAWorld is a generative agent-based city simulation. It builds agents from profile data, generates daily schedules and actions with LLMs, simulates perceptions/plans/reflections across a timeline, applies policy and environment events, and logs state changes over time.

## Features
- Agent construction from CSV state seeds + Markdown profiles.
- Multi-backend LLM routing (Ollama / OpenAI / Anthropic-compatible).
- Daily schedule generation, action selection, and reflection loops.
- Policy events with inferred effects on agent state.
- Environment event system (natural + social events).
- Social network creation and emotion diffusion.
- Stateful memory and logs across runs.
- Location-aware actions with per-agent, per-location LLM biasing.
- Time-aware location resolution (home at night, workplace during day with flexibility).
- City map generation from natural language descriptions.
- Reset command to clear stateful caches/logs and restart from day 1.
- Visualizations for social networks and state evolution.

## Project layout
- `generative_city_sim.py` main simulator + CLI entrypoint.
- `config.py` runtime configuration (LLM routing, sim params, data paths, events).
- `environment.py` environment event generator.
- `hangzhou_agents_state_init.csv` seed state values per agent.
- `hangzhou_profiles_with_names.md` detailed agent profiles.
- `citymap.md` village map (hubs + nearby locations).
- `generate_citymap.py` city map generator (from text descriptions).
- `output/` simulation artifacts (logs, memory, plots, CSVs).
- `extensibility.py` hook dispatcher for custom lifecycle functions.
- `custom_hooks.py` example custom hook functions.
- `experience_store.py` structured episodic memory persistence.
- `human_realism.py` behavior realism helpers (needs/habits/intentions/consolidation).

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

Counterfactual event comparison (parallel with/without event):
```bash
python generative_city_sim.py compare-event \
  --event-name "临时交通限行" \
  --event-description "主干道限行导致通勤时间上升并影响出行决策" \
  --event-day 2 \
  --event-time 09:00 \
  --sim-days 3 \
  --seed 42
```

Generate a new city map from a text description:
```bash
python generate_citymap.py --description "a small city with about 1000 residents, in east china"
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

### Policy events
`policy_events` is a list of `{day, time, name, description}`. Effects are inferred via LLM and applied to agent state.

### Environment system
`environment` enables randomized natural/social events per tick:
- `enabled`, `event_chance`, `max_events_per_tick`
- `natural_events` and `social_events` lists

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
- `output/network/social_network.png` social graph snapshot.
- `output/state/agent_state_over_time.png` state evolution plot.
- `output/state/agent_state_history.csv` time series data.

## Code organization
- `generative_city_sim.py`: main simulation loop and core domain logic.
- `llm_providers.py`: LLM provider wrappers and routing logic.
- `memory_store.py`: JSON memory/log persistence plus vector DB retrieval.

## Notes on behavior
- Schedule/action generation is LLM-driven with a heuristic fallback.
- Agent state updates blend deterministic rules with small random noise.
- Social influence shifts emotion toward neighbors’ average.
- Location assignment uses `citymap.md` hubs + heuristic role matching and time-aware biasing.

## Security note
Avoid hardcoding API keys in `config.py`. Prefer environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or your custom `api_key_env`) and keep secrets out of source control.

## Troubleshooting
- Missing actions for a schedule: ensure the LLM provider is reachable; cached action spaces can be deleted from `output/memory` to regenerate.
- Empty logs or memory: verify `stateful` and output paths in `config.py`.
- Slow runs: reduce `sim_days`, agents in `agent_ids`, or increase `seconds_per_day`.
