# GAWorld Dashboard Enhancement — Design Spec

## Overview

Enhance the GAWorld local dashboard (currently vanilla JS + Python `http.server`) with interactive data visualizations, following a **progressive enhancement** strategy — no build tools, no framework migration, no backend rewrite.

**Goal:** Transform the dashboard from "readable JSON dumps" to "actionable visual analytics" for simulation researchers.

**Strategy:** Route A — Progressive Enhancement (selected)

---

## Architecture

### Current
```
app.js (vanilla fetch API)  →  dashboard_server.py (http.server, 12 endpoints)  →  simulation data (JSON/CSV files)
```

### After Phase 1
```
app.js (unchanged)           →  dashboard_server.py (+2 endpoints)  →  simulation data
charts.js (Chart.js, CDN)   ↗
```

Chart.js is loaded via `<script>` tag from CDN — no npm, no bundler, no build step.

---

## Chart Library Decision

**Chart.js** (selected over uPlot and ECharts):
- 50 KB gzipped, zero build step (`<script src="...">`)
- Native JS API, no framework dependency
- Supports all needed chart types: line, radar, bar
- Sufficient performance for dashboard-scale data (< 1000 points per series)

---

## Components

### Panel 1: Economy Trend (Line Chart)

**Location:** New panel below the Memory section in `lower-grid`.

**Data source:** `GET /api/economy/{agent_id}`

**Response format:**
```json
{
  "agent_id": 1,
  "days": [1, 2, 3, ...],
  "income": [200, 150, ...],
  "expense": [80, 120, ...],
  "balance": [5000, 5100, ...]
}
```

**Backend:** Reads `output/memory/agent_{id}_economy.json`, extracts the per-day `daily_income`, `daily_expense`, `balance` arrays.

**Chart config:** Multi-line chart, X axis = day, Y axis = amount. Three series with distinct colors. Legend on hover. Auto-updates on agent switch.

### Panel 2: Agent State Radar (Radar Chart)

**Location:** Replace the raw `stateMemoryBox` (schedule/habits/intentions JSON dump) with a radar chart showing current agent needs.

**Data source:** Already available via `GET /api/agents/{id}/memory` (the `state` field).

**Dimensions:** energy, social, recreation, health, hygiene, environment, hunger (as available from agent state).

**Backend:** No new endpoint needed — the radar chart reads from the existing memory endpoint.

**Chart config:** Radar chart with 6-7 axes, fills with semi-transparent color. Shows "current value" vs "target/threshold" overlay.

### Bonus (P1, deferred): Multi-Agent State Comparison

Multi-line chart comparing one metric (e.g., energy) across multiple selected agents. Data from `GET /api/state-history` which reads `output/state/agent_state_history.csv`. Phase 1 implements the infrastructure; the comparison UI ships in a follow-up.

---

## API Changes

### New Endpoints

```
GET /api/economy/{agent_id}
  → 200: {agent_id, days[], income[], expense[], balance[]}
  → 404: {error: "Economy data not found"}

GET /api/state-history
  → 200: {agents: [{agent_id, metric, values[]}], days: int}
  → 404: {error: "State history not found or empty"}
```

### No Changes to Existing Endpoints

All 12 current endpoints remain unchanged. The new endpoints follow the same error handling pattern (`_json_response`, try/except with 500 fallback).

---

## File Changes

| File | Change |
|------|--------|
| `site/dashboard/index.html` | Add Chart.js CDN script tag, add two new `<section class="panel">` containers for charts |
| `site/dashboard/styles.css` | Add `.chart-container`, `.chart-grid`, chart-specific responsive rules |
| `site/dashboard/app.js` | Wire agent-switch event to chart re-render, add loadEconomy() / loadStateRadar() calls |
| `site/dashboard/charts.js` | **New file.** Chart.js instances: `initEconomyChart()`, `initRadarChart()`, `updateEconomyChart()`, `updateRadarChart()` |
| `dashboard_server.py` | Add `_economy_payload(agent_id)`, `_state_history_payload()`, route in `_handle_api_get` |

Charts.js is kept separate from app.js for clean separation of concerns — app.js handles data fetching and wiring, charts.js handles Chart.js lifecycle.

---

## Data Flow

```
Agent switch in dropdown
  → app.js calls loadMemory() + loadEconomy()
  → loadEconomy() fetches /api/economy/{id}
  → passes data to charts.js: updateEconomyChart(data)
  → charts.js calls chart.data.datasets[...].data = newData; chart.update()

Polling (existing 2.5s interval)
  → refreshStatus() + loadTrace() (unchanged)
  → No auto-poll for chart data (static historical data, no need)
```

---

## Error Handling

- Economy data not found → Show "暂无经济数据" placeholder in chart area
- State data missing → Show "暂无状态数据" in radar area
- Chart.js load failure → Graceful degradation: hide chart, show text message
- Backend 500 → Caught by existing `_handle_api_get` try/except pattern

---

## Testing

- Manual: Visual verification of chart rendering across 3 agents
- Manual: Verify chart updates on agent switch
- Manual: Edge case — agent with no economy data shows placeholder
- Existing: `tests/test_economy_module.py` validates data format
- New (optional): curl test for `/api/economy/{id}` endpoint

---

## Future (Post-Phase 1)

- Economy trend: Add zoom/pan, date range selector
- State radar: Overlay multiple agents for comparison
- Multi-agent line chart comparison (P1)
- Environment event timeline
- SSE push for real-time chart updates (when simulation is running)
- Data export (CSV download button on each chart)
