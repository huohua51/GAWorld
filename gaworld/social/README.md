# GAWorld Social System

This package is the social-interaction subsystem wired into the main
`generative_city_sim.py` loop through extension hooks in `config.py`.

The subsystem does three things:

1. Builds a weighted social graph from agent attributes.
2. Simulates pairwise interaction and message diffusion during each time tick.
3. Writes emotion, relationship, social memory, and daily relationship
   reflection changes back to the main agent state.

## Runtime Flow

```text
generative_city_sim.py
  -> HookBus emits on_simulation_start
  -> gaworld.social.hooks creates SocialInteractionRuntime
  -> HookBus emits on_time_tick
  -> runtime decides interactions and generates dialogue
  -> runtime updates emotion, stress, trust, closeness, friction
  -> salient events are written as social memories
  -> HookBus emits on_agent_pre_step
  -> pending events, recent social memories, and relationship reflection are injected into social_context
  -> original perception / planning / action / reflection continues
  -> HookBus emits on_day_end
  -> daily relationship reflections are persisted
```

## Files

- `schemas.py`: typed records for agents, relationship edges, decisions, and
  interaction events.
- `network.py`: converts agent attributes into a weighted social graph.
- `decision.py`: decides who interacts, interaction type, topic, probability,
  and message diffusion targets.
- `motivation.py`: translates existing simulator events, relationship state, and
  agent state into social motives. It does not generate new world events.
- `llm_events.py`: generates dialogue and structured state deltas. It uses a
  deterministic mock by default and can call a configured LLM.
- `memory.py`: converts salient social interactions into agent memory, vector
  entries, and recent in-session social memory snippets.
- `reflection.py`: writes end-of-day relationship reflections for agents who
  participated in social interactions.
- `runtime.py`: bridges the social graph with the main simulator state.
- `hooks.py`: extension-hook entry points used by `config.py`.

## Configuration

The active config lives in `config.py` under `social_interactions`.

```python
"social_interactions": {
    "enabled": True,
    "llm": os.environ.get("SOCIAL_INTERACTION_LLM", "mock"),
    "seed": 20260602,
    "network_seed": 42,
    "avg_degree": 6,
    "weak_tie_probability": 0.12,
    "max_events_per_tick": 2,
    "max_diffusion_targets": 1,
    "memory_salience_threshold": 0.50,
    "output_jsonl": "output/social_interactions/events.jsonl",
}
```

Use mock mode for local runs:

```bash
python generative_city_sim.py run
```

Use MiniMax for social dialogue generation:

```bash
export MINIMAX_API_KEY=...
export SOCIAL_INTERACTION_LLM=minimax
python generative_city_sim.py run
```

Generated social outputs:

```text
output/social_interactions/
├── events.jsonl
├── daily_summary.md
├── social_timeline.md
├── relationship_changes.csv
└── dashboard.html
```

In addition, salient events are appended to each involved agent's persistent
memory as `social_memory` entries, and end-of-day summaries are written as
`social_reflection` entries.
