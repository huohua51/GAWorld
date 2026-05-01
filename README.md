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
- Realistic personal economy simulation (tax, social insurance, investment, macro cycles)
- Realistic location system with category-based spatial matching, transport cost calculation, rush-hour and weather effects, and commute memory
- Dynamic behavior system: mood-driven spontaneous urges, social encounter chains, need-based interrupts, environment event cascades, and commitment-aware schedule interruption
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
- `economy_module.py`: realistic personal finance layer (tax, social insurance, Engel spending, investment, macro cycles)
- `dynamic_behavior.py`: dynamic behavior system (spontaneous urges, social chains, need interrupts, environment responses, schedule insertion)
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
- `economy`: personal finance settings (tax brackets, social insurance rates, Engel curve, investment, macro cycle, shocks)
- `dynamic_behavior`: dynamic behavior system settings (enabled flag)
- `intervention`: lightweight recommendation / exposure control and evaluation settings
- `policy_events`: scheduled policy shocks
- `distributed`: multi-machine communication settings

### PolicySim-Style Intervention Evaluation

`CONFIG["intervention"]` enables a deterministic, no-network intervention layer inspired by
PolicySim. At each agent step, the simulator builds a small feed from relational, personalized,
and headline-like sources, applies local exposure-control heuristics, injects the feed into
perception, and records stance / toxicity / misinformation / cross-viewpoint reward metrics.

This feature does not perform SFT/DPO model training and does not call external moderation APIs.

### Economy Module

`CONFIG["economy"]` drives a realistic personal finance simulation modeled on the Chinese
economic system. Every agent maintains a full financial profile that evolves across simulation
days through four interlocking subsystems:

**Tax & Social Insurance (个税 + 五险一金)**

Each agent has a gross monthly salary derived from their job band and income skill. The module
calculates individual social insurance contributions (pension 8%, medical 2%, unemployment 0.5%,
housing fund 8%) with a base salary floor of 4,462 CNY and cap of 36,000 CNY. Personal income
tax uses China's 7-bracket progressive rate table (3%–45%, monthly exemption 5,000 CNY, with
configurable special deductions). The full pipeline `gross → SI deduction → tax → net salary`
runs at initialization and recalculates monthly when salary changes.

**Engel-Coefficient Spending**

Instead of flat random expense ranges, agents allocate their consumption budget according to an
income-indexed Engel coefficient curve. Low-income agents spend ~48% of consumption on food
with a ~5% savings rate; high-income agents spend ~15% on food with a ~40% savings rate. Eight
spending categories (food, housing, transport, clothing, leisure, education, healthcare, misc)
are weighted by income elasticity of demand: necessities (food 0.5, healthcare 0.6) grow slowly
with income while luxuries (leisure 1.5, clothing 1.2) scale up. Monthly budgets are
automatically recalculated whenever salary changes.

**Multi-Account System & Investment**

Agents hold four separate accounts: checking (活期), savings (储蓄), investment (投资), and
housing fund (公积金). Risk preference maps to three portfolio profiles — conservative
(deposits 70% / funds 25% / stocks 5%), moderate (40/40/20), and aggressive (15/35/50). Each
month, investment returns are simulated using Gaussian distributions calibrated to each asset
class (deposits ~2.5% annual, funds ~6%±8%, stocks ~8%±22%). Excess checking balance is
automatically transferred to savings and investment accounts based on a configurable buffer
threshold.

**Macro-Economic Cycles & Shock Events**

A simulation-level macro cycle rotates through four phases — expansion, peak, contraction, and
trough — each lasting 60–180 days. Each phase applies multipliers to income, expenses, layoff
risk, and raise probability. Industry-specific conditions (tech, finance, medical, education,
service, trade) shift independently. Inflation accumulates daily and erodes purchasing power.
At the individual level, agents face random economic shocks: layoffs (income cut 50–85%,
recovery 30–90 days), raises/promotions, medical emergencies (with social insurance
reimbursement at 50–85%), and annual year-end bonuses (13th-month salary).

Economy outputs include `output/economy/daily_ledger.csv`, per-agent ledgers, wealth snapshots,
and `macro_state.json`.

### Location System

`city_map_system.py` provides a realistic spatial layer for agent movement decisions.
Instead of hardcoded location names, the system uses category-based spatial matching
to resolve where agents should go for any activity.

**Transport Cost Calculation**

Each transport mode has a fare structure calibrated to Chinese urban transit: bus flat
fare (2 CNY), metro distance-based (base 2 + 0.45/km beyond 4 km free), taxi with
base fare and per-km rate (13 + 2.5/km beyond 3 km free), car with per-km fuel cost
and optional parking. Rush-hour detection (7:00–9:00, 17:00–19:00) applies a 1.45×
time multiplier and 1.3× taxi surcharge. Travel costs are deducted from the agent's
transport expense category in the economy module.

**Weather-Aware Mode Selection**

When weather conditions are active, the transport mode selector re-evaluates choices
using weather adjustment weights. In rain or snow, open-air modes (walk, bike, e-bike)
are heavily penalised and agents switch to sheltered alternatives (bus, metro, taxi).

**Category-Based Location Resolution**

Activities and job titles are mapped to location categories (education, medical,
commerce, leisure, transit, etc.) through keyword dictionaries. The spatial resolver
finds the nearest matching nodes from the agent's current position, weighted by time-
of-day bias, agent profile, and habitual preference. This replaces the previous
approach of hardcoded location name lists, making the system work with any city map.

**Commute Memory**

Agents track frequent places, preferred transport modes, and commute route statistics
(average travel time, trip count). These accumulate over simulation days and feed back
into location decisions — agents develop habitual patterns and prefer familiar places.

**Area Price Levels**

Different area categories carry price-level multipliers (commerce 1.35×, industry
0.80×, education 0.85×, etc.) that influence spending behavior when agents are in
those areas.

### Dynamic Behavior System

`dynamic_behavior.py` makes agent daily routines feel more human by injecting
context-aware schedule changes. The system is opt-in via `CONFIG["dynamic_behavior"]["enabled"]`
and runs once per agent per time-step, before the LLM-based activity adjustment.

**Commitment-Aware Interruption**

Every activity carries a commitment level (0.95 for exams and surgery, 0.70 for work, 0.15 for
browsing the phone). Interrupt candidates must overcome this commitment barrier plus a
personality-dependent threshold (self-control, risk preference) to change the scheduled activity.
Even net-positive interrupts pass through a stochastic acceptance gate.

**Mood-Driven Spontaneous Urges**

The agent's emotional state is classified into one of six mood categories (happy, stressed, tired,
bored, anxious, lonely). Each mood maps to a pool of context-appropriate urges — a stressed agent
might want to take a walk alone, while a bored agent might pick up their phone. Time-of-day
filters prevent unrealistic urges (no shopping at midnight), and personality scaling adjusts
probabilities (extroverts get more social urges).

**Social Encounter Chains**

When agents share the same location, encounter probability is computed from relationship closeness
and social need. Close friends may invite each other for meals (time-aware: lunch vs dinner),
acquaintances exchange brief greetings, and strangers may exhibit behaviour contagion — joining a
queue or watching a street event.

**Environment Event Cascades**

Weather, traffic, commercial, news, and emergency events are classified and converted into
interrupt candidates with personality-differentiated priority. Primary events can trigger cascade
chains: rain leads to taxi queues and slippery roads, traffic congestion leads to potential
lateness and mood drops. Cascade events fire probabilistically and accumulate mood effects.

**Need-Based Interrupts**

Physiological needs (hunger, fatigue) and task pressure generate interrupt candidates. Hunger
interrupts receive a bonus near meal times. Low energy triggers rest urges. High time pressure
pushes agents to handle urgent tasks.

**Schedule Insertion**

When an interrupt wins, the system can insert the new activity into the schedule with resumable
support — the original activity resumes after the interruption if there's room in the schedule.

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
- `output/economy/daily_ledger.csv`, `wealth_snapshot.csv`, `macro_state.json`
- `output/economy/agents/agent_<id>_ledger.csv`, `agent_<id>_snapshot.json`
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
