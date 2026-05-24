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
| 记忆系统 | ✅ Implemented | Vector DB retrieval with recency scoring |
| 人格角色 | ✅ Implemented | Profile data drives communication style |
| 情感层 | ⚠️ Integration Layer Ready | `emotional_memory_integration.py` provides event tracking, decay, context generation; needs runtime hook |
| 有限理性 | ⚠️ Integration Layer Ready | `bounded_rationality_integration.py` bridges types and GAWorld state; needs runtime hook |
| 持续学习 | ❌ Not implemented | No behavior drift detection |
| 关系记忆 | ⚠️ Integration Layer Ready | `integration.py` bridges two systems; needs runtime hook in GAWorld |

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

**Next Step**: Add `sync_relationships_to_runtime()` call in `on_agent_post_step` hook (line ~6232) to actually sync relationships during simulation.

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
# Run simulation with Agent 52
python generative_city_sim.py --agents 52 --days 1

# Run Life-History evaluation
python eval/life_history_eval.py 52

# Output evaluation report
# → output/eval/agent_52_life_history_eval.md
```

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

### 2026-05-24 (Iteration 3): Emotional Memory Integration Layer
- Created `emotional_memory_integration.py` with:
  - `EmotionalEventType`: 12 types (SUCCESS, FAILURE, SOCIAL_SUPPORT, etc.)
  - `EmotionalEvent`: Single emotional experience with decay
  - `EmotionalMemory`: Collection with `decay_all()`, `get_recent_events()`, etc.
  - `infer_emotional_event_from_gaworld()`: Detects emotional changes from GAWorld state
  - `get_emotional_context_from_memory()`: Generates prompt context from past events
  - `decay_emotional_memory_if_needed()`: Scheduled decay mechanism
- Updated `__init__.py` to export emotional memory classes
- Updated mock scores: `affect_score: 9 → 12` (60%)

### 2026-05-24 (Iteration 2): Bounded Rationality Integration Layer
- Created `bounded_rationality_integration.py` with 5 functions
- Updated mock scores: `bounded_rationality_score: 5 → 8` (53.3%)

### 2026-05-24 (Iteration 1): Relationship Memory Integration Layer Created
- Created `integration.py` with 4 functions
- Updated mock scores: `relationship_score: 0 → 4` (20%)

### 2026-05-24: Life-History Agent Evaluation Framework Created
- Added 6-dimension HumanScore evaluation
- Relationship memory currently 0% due to parallel systems
- Bounded rationality not affecting decision process
- Emotional memory not persisting across events

### 2026-05-24: Two Relationship Systems Identified
- GAWorld uses `{closeness, trust, obligation, friction}`
- Life-History uses `{trust, intimacy, pressure, conflict_level}`
- Integration needed before scoring can improve

---
*Last Updated: 2026-05-24*