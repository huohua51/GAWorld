# Personal Twin Design

## Goal

GAWorld is no longer only a city-scale simulator. It can also be used as a
local-first personal twin runtime:

- each user runs a twin on their own machine
- private memory, RAG, and local context stay on that machine
- the central relay only receives public profile fragments, public state, and
  social summaries
- the same twin can run daily, accumulate memory, and participate in a
  distributed virtual social network

## Runtime Layers

### 1. Local twin runtime

The local node owns:

- the agent profile
- memory files and vector DB
- local RAG and imported private context
- daily summaries and diaries
- What-if execution

In the current codebase this layer is composed mainly from:

- `generative_city_sim.py`
- `memory_store.py`
- `gaworld/work/`
- `openclaw_bridge.py` for external local personas

### 2. Relay-backed social layer

The central relay owns:

- agent directory
- public profile fragments
- public state fragments
- cross-node message routing
- social edges and recent social events
- tick synchronization

This layer is implemented in:

- `distributed_comm_server.py`
- `distributed_comm.py`

### 3. Dashboard and inspection layer

The local dashboard exposes:

- run control
- memory inspection
- interview
- distributed social snapshot
- personal-twin configuration visibility

This layer is implemented in:

- `dashboard_server.py`
- `site/dashboard/`

## Privacy Boundary

The design goal is local-first privacy, not central collection.

What stays local:

- raw memory entries
- full diaries
- imported private RAG
- detailed logs
- local decision context

What may be shared:

- public profile summary
- public status
- public state fragments such as stress or emotion scores
- social-summary text prepared for cross-node exchange

## Daily Twin Update

At the end of each simulated day the runtime now updates a public twin summary
derived from that day's memory, diary, and next-step intentions. That public
summary is attached to the in-memory agent profile and can be propagated to the
relay through later cross-node messages.

## What-if Flow

`personal-what-if` reuses the compare-event infrastructure and runs two
scenarios:

- baseline: continue from the same starting state
- scenario: inject one personal hypothetical event

Outputs include:

- scenario folders for baseline and injected branches
- `comparison_summary.md`
- `personal_twin_recommendation.md`

This gives each local twin a concrete way to explore counterfactual choices
without moving private context to the central server.
