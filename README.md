# GAWorld

[English](./README.md) | [中文](./README.zh-CN.md)

GAWorld is a generative multi-agent simulator for urban social behavior experiments.
It combines agent profiles, memory, social influence, environment events, policy shocks,
economy, map-based movement, lightweight platform-intervention evaluation, and LLM-driven
decision making into a replayable simulation workflow.

## Overview

GAWorld is designed as a controllable social experiment sandbox rather than a simple agent demo.
You can:

- run the same agents under different events or policies
- compare counterfactual scenarios in parallel
- preserve memory, habits, and relationships across days
- inspect traces, logs, interviews, and per-agent memory artifacts
- evaluate PolicySim-style recommendation / exposure interventions without extra APIs
- edit runtime parameters and profiles through a local dashboard

Typical use cases:

- urban governance and policy simulation
- agent memory and behavior-consistency experiments
- social behavior and risk propagation studies
- teaching demos for complex systems or agent-based simulation

## Core Loop

Each agent repeatedly goes through:

1. perception
2. planning
3. routine / action generation
4. action execution
5. reflection and memory update

Across days, the simulator accumulates:

- episodic memories
- long-term summaries
- habits by context
- intentions
- relationship shifts
- financial state changes

## Main Features

- Seed agents from CSV state values and Markdown profiles
- Create new agents from social media pages or extracted text
- Multi-backend LLM routing: Ollama, OpenAI-compatible, Anthropic-compatible
- External RAG injection from CLI or files
- Policy events and environment events
- PolicySim-inspired recommendation / exposure intervention metrics
- Economy / wealth module
- Location-aware actions and travel
- City map generation and route playback
- Visualization trace export
- Agent interview CLI
- Local dashboard for config editing, profile editing, run control, memory inspection, and interview
- Distributed multi-machine mode with relay-based communication

## Project Structure

- `generative_city_sim.py`: main simulator and CLI entrypoint
- `config.py`: runtime configuration
- `llm_providers.py`: provider wrappers and task routing
- `environment.py`: environment event system
- `intervention_policy.py`: lightweight recommendation, exposure control, stance, and risk metrics
- `human_realism.py`: realism helpers, intentions, habits, memory consolidation
- `economy_module.py`: economy / wealth layer
- `memory_store.py`: memory persistence and vector DB helpers
- `city_map_system.py`: graph, routes, travel, and tile map generation
- `simulation_visualizer.py`: trace writer for playback
- `dashboard_server.py`: local dashboard backend
- `hangzhou_agents_state_init.csv`: seed state values
- `hangzhou_profiles_with_names.md`: agent profiles
- `citymap.md`: city map data
- `site/dashboard/`: local dashboard frontend
- `site/simviz/`: playback viewer
- `output/`: generated artifacts

## Quickstart

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the simulator:

```bash
python generative_city_sim.py run
```

Reset stateful artifacts:

```bash
python generative_city_sim.py reset
```

Start the dashboard:

```bash
python generative_city_sim.py dashboard --port 8766
```

Then open:

```text
http://127.0.0.1:8766/dashboard
```

Serve the visualization viewer directly:

```bash
python generative_city_sim.py serve-viz --port 8000
```

Then open:

```text
http://127.0.0.1:8000/site/simviz/index.html
```

## CLI

Show help:

```bash
python generative_city_sim.py --help
```

Run simulation:

```bash
python generative_city_sim.py run
```

Reset simulation:

```bash
python generative_city_sim.py reset
```

Interview an agent:

```bash
python generative_city_sim.py interview --agent-id 31 --question "Why did you choose this action today?"
python generative_city_sim.py interview --agent-id 31 --questions-file questions.txt
```

Create an agent from social content:

```bash
python generative_city_sim.py create-agent-from-social --url "https://weibo.com/..."
python generative_city_sim.py create-agent-from-social --file output/source_page.txt --name "New Agent"
```

Add external RAG info:

```bash
python generative_city_sim.py rag-add \
  --agent-id 31 \
  --text "Prefers cycling and bookstores on weekends" \
  --timestamp "2026-02-18 09:30" \
  --source "manual"
```

Import external RAG info:

```bash
python generative_city_sim.py rag-import \
  --agent-id 31 \
  --file output/test_extra_info.txt \
  --source "profile_notes"
```

Compare an event against a no-event baseline:

```bash
python generative_city_sim.py compare-event \
  --event-name "Temporary Traffic Restriction" \
  --event-description "Travel time increases on arterial roads and affects commuting decisions" \
  --event-day 2 \
  --event-time 09:00 \
  --sim-days 3 \
  --llm-provider minimax \
  --seed 42
```

The comparison report includes regular city-state metrics and intervention metrics such as
`stance_score`, `toxicity_score`, `misinformation_risk`, `cross_viewpoint_exposure`, and
`intervention_reward`.

Generate a city map:

```bash
python generate_citymap.py --description "a small city with about 1000 residents, in east china"
```

Run the distributed relay:

```bash
python generative_city_sim.py serve-distributed --host 0.0.0.0 --port 8877
```

## Dashboard

The local dashboard provides:

- runtime config editing
- LLM routing selection
- profile editing
- simulation start / stop
- trace playback
- per-agent memory inspection
- interview execution
- run log viewing

The dashboard stores local overrides in `dashboard_config.json`.
Those values override `config.py` at runtime.

## Configuration

All base settings live in `config.py`.

Important fields:

- `agent_ids`: agents included in the run
- `sim_days`: number of simulated days
- `seconds_per_day`: wall-clock seconds per simulated day
- `time_step_minutes`: optional fixed timeline step
- `llm.providers`: provider registry
- `llm.routing.default`: default provider
- `llm.routing.tasks`: task-specific provider overrides
- `memory_dir`, `log_dir`, `vector_db_path`: persistence locations
- `visualization.output_dir`: trace output folder
- `intervention`: lightweight recommendation / exposure control and evaluation settings
- `policy_events`: scheduled policy shocks
- `distributed`: multi-machine communication settings

### PolicySim-Style Intervention Evaluation

`CONFIG["intervention"]` enables a deterministic, no-network intervention layer inspired by
PolicySim. At each agent step, the simulator builds a small feed from relational, personalized,
and headline-like sources, applies local exposure-control heuristics, injects the feed into
perception, and records stance / toxicity / misinformation / cross-viewpoint reward metrics.

This feature does not perform SFT/DPO model training and does not call external moderation APIs.

### LLM Backends

The project supports:

- `ollama`
- OpenAI-compatible endpoints
- Anthropic-compatible endpoints

For Minimax China-region Anthropic compatibility, the project supports:

- `ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic`
- `MINIMAX_API_KEY` or `ANTHROPIC_AUTH_TOKEN`

## Outputs

Generated artifacts are written under `output/`, including:

- `output/logs/agent_<id>.log`
- `output/memory/agent_<id>.json`
- `output/memory/agent_<id>_episodes.jsonl`
- `output/memory/vector_db.sqlite`
- `output/economy/`
- `output/environment/timeline.jsonl`
- `output/intervention/intervention_metrics.csv`
- `output/visualization/simulation_trace.json`
- `output/visualization/latest_frame.json`
- `output/network/`
- `output/state/`

## Notes

- `dashboard_config.json` can override `config.py`
- stateful runs may reuse memory and schedules from earlier runs
- after changing memory schema settings, run `reset`
- if a provider appears wrong at runtime, check both `config.py` and `dashboard_config.json`

## Additional Docs

- [中文 README](./README.zh-CN.md)
- [Tutorial](./TUTORIAL.md)
- [Repository Guidelines](./AGENTS.md)
