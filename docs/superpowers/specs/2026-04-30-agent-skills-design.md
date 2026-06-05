# Agent Skill System

## Goal

Add a skill system to GAWorld agents — each agent has 2-3 initial skills with levels and XP progress, displayed in the dashboard. This is Layer 1 of a multi-layer system; future layers will add XP growth from actions and skill effects on task economy.

## Architecture

- **Data:** Per-agent JSON file (`output/memory/agent_{id}_skills.json`), same pattern as existing memory/economy files
- **Simulator:** Assign random skills on agent init, persist to JSON
- **Dashboard API:** New endpoint `GET /api/agents/{id}/skills`
- **Frontend:** Skills panel in right sidebar, between Profile and Interview sections

## Skill Catalog

13 skills across 4 categories. Each skill has a Chinese name, English key, and category.

| Category | Skills |
|----------|--------|
| **crafting** | 木工 (woodworking), 烹饪 (cooking), 手工 (handicraft), 缝纫 (tailoring) |
| **service** | 运输 (transportation), 清洁 (cleaning), 安保 (security) |
| **social** | 教学 (teaching), 娱乐 (entertainment), 谈判 (negotiation) |
| **knowledge** | 采集 (gathering), 勘探 (exploration), 医疗 (medicine) |

## Data Model

```json
{
  "agent_id": 5,
  "skills": [
    {
      "key": "woodworking",
      "name": "木工",
      "category": "crafting",
      "level": 2,
      "xp": 45,
      "xp_next": 100
    },
    {
      "key": "cooking",
      "name": "烹饪",
      "category": "crafting",
      "level": 1,
      "xp": 30,
      "xp_next": 100
    }
  ]
}
```

- `level`: 1–5
- `xp`: current experience points
- `xp_next`: XP required for next level (100 for levels 1-4, 0 at max level 5)
- Each agent starts with 2-3 random skills at level 1, 0 XP

## API

```
GET /api/agents/{id}/skills → {"agent_id": 5, "skills": [...]}
GET /api/agents/{id}/skills?refresh=1 → force re-read from disk
```

Returns empty skills array if file not found (agent has no skills).

## Dashboard Panel

Insert in `right-stack` between Profile and Interview sections.

### Layout
```
┌─────────────────────────────────┐
│ Kicker: Skills                  │
│ H2: 技能                         │
│                                 │
│ ┌──────────┐ ┌──────────┐      │
│ │ 木工 Lv.2│ │ 烹饪 Lv.1│      │
│ │ ████░░░░░│ │ ██░░░░░░░│      │
│ │ 45/100   │ │ 30/100   │      │
│ └──────────┘ └──────────┘      │
│                                 │
│ ┌──────────┐ ┌──────────┐      │
│ │ 手工 Lv.1│ │ 运输 Lv.3│      │
│ │ ░░░░░░░░░│ │ ██████░░░│      │
│ │ 0/100    │ │ 86/150   │      │
│ └──────────┘ └──────────┘      │
└─────────────────────────────────┘
```

### States

| State | Display |
|-------|---------|
| **Loading** | Placeholder text "读取技能中..." |
| **Has skills** | 2-column grid of skill cards |
| **No skills** | Placeholder text "该智能体暂无技能" |
| **Error** | Placeholder text "技能数据读取失败: {msg}" |

### Component Design

Each skill card shows:
- Skill name (Chinese) + level badge
- XP progress bar (background fill based on xp/xp_next ratio)
- XP text ("45/100")

Level badge colors:
- Lv.1: muted text
- Lv.2-3: teal
- Lv.4-5: gold

## Simulator Changes

Add `assign_initial_skills(agent)` function that:
1. Picks 2-3 random skills from the catalog
2. Sets level=1, xp=0
3. Saves to `output/memory/agent_{id}_skills.json`

Call this during agent initialization in the simulation run flow.

## Files Changed

| File | Change |
|------|--------|
| `generative_city_sim.py` | Add `assign_initial_skills()`, call during agent init |
| `dashboard_server.py` | Add `_skills_payload()`, add route `GET /api/agents/{id}/skills` |
| `site/dashboard/index.html` | Add skills panel markup in right-stack |
| `site/dashboard/app.js` | Add `loadSkills()`, wire into `selectAgent()` and init |
| `site/dashboard/charts.js` | No changes |
| `site/dashboard/styles.css` | Add skill-card/skill-grid/skill-bar styles |

## Out of Scope (Layer 2+)

- XP gain from agent actions during simulation
- Skill effects on task outcomes or economy
- Skill synergy or prerequisites
- Skill training/learning new skills mid-simulation
- Integration with future gig/task system
