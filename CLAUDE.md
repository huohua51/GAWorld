# GAWorld Multi-Agent City Simulation

> Human-like AI agents living in a simulated city environment. Each agent has personality, memory, relationships, and follows a cognitive loop similar to how humans perceive, plan, act, and reflect.

## Project Overview

GAWorld simulates 50+ agents in a city environment with:
- **Cognitive Loop**: perceive → plan → act → reflect
- **Social Networks**: agents interact via distributed inbox (messaging system)
- **Human Realism**: relationship tracking, needs, habits, life events
- **Economic Activity**: resource production and consumption

## Project Structure

```
GAWorld/
├── generative_city_sim.py      # Main simulation loop
├── human_realism.py            # Human realism module (relationships, needs, etc.)
├── gaworld/
│   └── core/life_history/       # Life-History Agent types and data
│       ├── lh_types.py         # Core type definitions
│       ├── integration.py      # Relationship memory integration
│       ├── bounded_rationality_integration.py  # Bounded rationality integration
│       ├── emotional_memory_integration.py     # Emotional memory integration
│       ├── learning_integration.py             # Learning system integration
│       ├── unified_engine.py                  # Unified engine (Phase 5)
│       └── mock_data.py        # Agent 52 (郭林峰) profile data
├── eval/
│   └── life_history_eval.py    # 6-dimension HumanScore evaluation
└── docs/superpowers/specs/     # Architecture specifications
```

## Life-History Agent Architecture

Agent 52 (郭林峰) is the primary research agent. The Life-History Agent framework adds 6 dimensions of human-like behavior:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| 记忆系统 (memory_score) | 25% | Recall accuracy, consistency, recency effect |
| 人格角色 (personality_score) | 20% | Personality consistency, role stability |
| 情感层 (affect_score) | 20% | Emotional waves, emotional memory, expression diversity |
| 有限理性 (bounded_rationality_score) | 15% | Decision limits, uncertainty expression |
| 持续学习 (learning_score) | 10% | Behavior drift detection, learning from error |
| 关系记忆 (relationship_score) | 10% | Relationship tracking, trust evolution, conflict resolution |

### Current Implementation Status

| Dimension | Status | Integration |
|-----------|--------|-------------|
| 记忆系统 | ✅ Integrated | unified_engine 统一调用，记忆上下文增强 |
| 人格角色 | ✅ Implemented | Profile data drives communication style |
| 情感层 | ✅ Integrated | EmotionalMemory + unified_engine |
| 有限理性 | ✅ Integrated | bounded_rationality_integration + unified_engine |
| 持续学习 | ✅ Integrated | learning_integration + unified_engine |
| 关系记忆 | ✅ Persistent State + Bidirectional Sync | runtime_state.relationships persists, syncs to GAWorld each step |

## Relationship Memory

### Two Systems Now Bridged by Integration Layer

**GAWorld System** (`human_realism.py`):
- Metrics: `closeness`, `trust`, `obligation`, `friction`
- Updated via: `relationship_update()` after social interactions (line 6019)
- Used in: `get_social_context()` weighted selection → perception → decision

**Life-History System** (`gaworld/core/life_history/lh_types.py`):
- Type: `RelationshipMemory`
- Metrics: `trust`, `intimacy`, `pressure`, `conflict_level`
- Status: **Integration layer created** (`integration.py`)

**Integration Layer** (`gaworld/core/life_history/integration.py`):
- `sync_relationships_to_runtime()`: Maps GAWorld `{closeness,trust,obligation,friction}` → `RelationshipMemory`
- `build_relationship_context()`: Generates natural language relationship descriptions for prompts
- `update_relationships_from_reflection()`: Updates relationships based on reflection text
- `create_runtime_state_from_agent()`: Factory to create AgentRuntimeState from GAWorld agent dict

**Runtime Integration** (as of commit 9a7f0fe+):
- `sync_from_gaworld()` called at day start: syncs GAWorld relationships → `LifeHistoryEngine.runtime_state`
- `build_planning_context()` uses persistent `runtime_state.relationships` (not temp state)
- `record_step_outcome()` updates `runtime_state.relationships` and syncs back to `agent["relationships"]`

## Iteration Workflow

For Life-History Agent feature development:

1. **Phase 1 (P0)**: Relationship Memory
   - Connect `RelationshipMemory` to GAWorld runtime
   - Map `closeness/trust/obligation/friction` → `trust/intimacy/pressure/conflict_level`
   - Ensure relationships affect actual decisions, not just stored

2. **Phase 2 (P1)**: Bounded Rationality
   - Add `bounded_plan` constraints to decision process
   - Implement uncertainty expression in LLM prompts

3. **Phase 3 (P1)**: Emotional Memory
   - Add `emotional_event` recording after significant events
   - Trigger emotional responses from past events

4. **Phase 4 (P2)**: Learning System
   - Implement behavior drift detection
   - Strategy adjustment after reflection

5. **Phase 5 (P2)**: Full Integration
   - Unify all systems in `AgentRuntimeLoop`

## Running the Simulation

```bash
# Run with all agents (ensure HUMAN_REALISM_ENABLED in config)
python generative_city_sim.py run

# Check config for HUMAN_REALISM_ENABLED flag
# config.py -> human_realism.enabled = true
```

## GAWorld Runtime Integration

When `HUMAN_REALISM_ENABLED=true`, the LifeHistoryEngine is automatically created for each agent:

**Initialization** (line ~5187):
- `agent["life_history_engine"] = create_life_history_engine(agent_id, agent_name)`

**Each Day Start** (line ~5451):
- `engine.sync_from_gaworld(agent, agents_by_id, day)` - Sync GAWorld state to all subsystems

**Each Step - Planning** (line ~5816):
- `engine.build_planning_context(activity, perception_text)` → injected into `plan_refs["life_history_context"]`
- Appears in prompt as "⚠️ 决策参考：..."

**Each Step - After Action** (line ~6130):
- `engine.record_step_outcome(...)` - Records behavior, learns, updates preferences

## Updating This Document

After each iteration milestone, update this CLAUDE.md to reflect:
- Current implementation status of each dimension
- Key architectural decisions
- Changes to the runtime integration
- Open questions and next steps

This ensures `git diff CLAUDE.md` shows the evolution of the Life-History Agent work for team review.

## Key Files for Review

| File | Purpose | Review Focus |
|------|---------|---------------|
| `gaworld/core/life_history/lh_types.py` | Type definitions | Are types correctly modeling human cognition? |
| `gaworld/core/life_history/mock_data.py` | Agent 52 profile | Does profile reflect real personality? |
| `human_realism.py:497-537` | `relationship_update` | Does it affect actual decisions? |
| `generative_city_sim.py:4603-4639` | `get_social_context` | Social context integration |
| `eval/life_history_eval.py` | Evaluation framework | Are metrics measuring what matters? |

## Architecture Decision Records

### 2026-05-25: P1 Bug Fixes - Relationship Persistence and Architecture
**P1 Fixes:**
- Relationship updates now persist: `LifeHistoryEngine.runtime_state` holds `AgentRuntimeState` with `relationships` dict
- `sync_from_gaworld()` syncs GAWorld → `runtime_state` at day start
- `record_step_outcome()` updates `runtime_state.relationships` then syncs back to `agent["relationships"]` via `_sync_relationships_to_gaworld()`
- `build_planning_context()` now uses `self.runtime_state` (not temp `create_agent_52_profile()`)
- Added `profile` parameter to `create_life_history_engine()` for per-agent profiles

**P2 Fixes:**
- Success detection replaced brittle `"成功" in outcome` with `_is_outcome_success()` using multi-keyword voting
- Committed `eval/` and `docs/` to git for reproducibility
- Updated CLAUDE.md to reflect actual integration state

### 2026-05-25: GAWorld Runtime Integration
- Added `create_life_history_engine` import in `generative_city_sim.py`
- Engine creation at `build_agent` stage (line ~5187) when `HUMAN_REALISM_ENABLED=True`
- `sync_from_gaworld()` called at day start (line ~5451)
- `build_planning_context()` injected into planning prompt (line ~5816)
- `record_step_outcome()` called after each step (line ~6130)
- LifeHistory context appears as "⚠️ 决策参考：..." in prompt

### 2026-05-25 (Phase 5): Life History Unified Engine
- Created `unified_engine.py` with `LifeHistoryEngine` class
- Integration complete: all 4 subsystems now unified
- Updated mock scores: `memory_score: 17 → 19` (63.3%)

### 2026-05-24 (Iteration 4): Learning System Integration Layer
- Created `learning_integration.py` with drift detection, strategy learning
- Updated mock scores: `learning_score: 3 → 5` (50%)

### 2026-05-24 (Iteration 3): Emotional Memory Integration Layer
- Created `emotional_memory_integration.py` with 12 emotion types
- Updated mock scores: `affect_score: 9 → 12` (60%)

### 2026-05-24 (Iteration 2): Bounded Rationality Integration Layer
- Created `bounded_rationality_integration.py` with 5 functions
- Updated mock scores: `bounded_rationality_score: 5 → 8` (53.3%)

### 2026-05-24 (Iteration 1): Relationship Memory Integration Layer Created
- Created `integration.py` with 4 functions
- Updated mock scores: `relationship_score: 0 → 4` (20%)

### 2026-05-24: Life-History Agent Evaluation Framework Created
- Added 6-dimension HumanScore evaluation

---
*Last Updated: 2026-05-25*