# GAWorld Dashboard Enhancement — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add economic summary panel and agent state radar chart to the GAWorld dashboard using Chart.js.

**Architecture:** Progressive enhancement — add Chart.js via CDN, create a `charts.js` module for chart lifecycle, add 1 new backend API endpoint. No build tools, no framework migration.

**Tech Stack:** Python 3.11+ (`http.server`), vanilla JS, Chart.js 4.x (CDN)

---

## File Structure

| File | Change |
|------|--------|
| `dashboard_server.py` | +1 new endpoint `GET /api/economy/{id}` |
| `site/dashboard/charts.js` | **Create** — Chart.js radar chart widget |
| `site/dashboard/index.html` | +Chart.js CDN, +radar panel markup |
| `site/dashboard/styles.css` | +chart container styles |
| `site/dashboard/app.js` | +wire chart loading on agent switch |

---

### Task 1: Add economy API endpoint

**Files:**
- Modify: `dashboard_server.py:308-316` (add `_economy_payload`)
- Modify: `dashboard_server.py:340-358` (add route)

- [ ] **Step 1: Add `_economy_payload` helper**

Insert after `_latest_trace_meta()` (line 316):

```python
def _economy_payload(agent_id):
    memory_dir = _effective_config().get("memory_dir", "output/memory")
    path = os.path.join(REPO_ROOT, memory_dir, f"agent_{agent_id}_economy.json")
    data = _read_json_file(path, {})
    if not data:
        return {"agent_id": int(agent_id), "error": "Economy data not found"}
    return {"agent_id": int(agent_id), "economy": data}
```

- [ ] **Step 2: Add route in `_handle_api_get`**

Add before the fallback 404 (line 357):

```python
        if path.startswith("/api/economy/") and len(path.split("/")) == 4:
            agent_id = path.split("/")[3]
            return self._json_response(_economy_payload(agent_id))
```

- [ ] **Step 3: Verify endpoint**

Run: `python -c "from dashboard_server import _economy_payload; print(_economy_payload(1))"`
Expected: `{'agent_id': 1, 'economy': {}}` or `{'agent_id': 1, 'error': 'Economy data not found'}`

- [ ] **Step 4: Commit**

```bash
git add dashboard_server.py
git commit -m "feat: add GET /api/economy/{id} endpoint"
```

---

### Task 2: Add Chart.js CDN and radar chart panel to HTML

**Files:**
- Modify: `site/dashboard/index.html`

- [ ] **Step 1: Add Chart.js CDN script tag**

Insert before the closing `</body>` tag, before the `app.js` script:

```html
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
  <script src="/site/dashboard/charts.js"></script>
```

- [ ] **Step 2: Add radar chart panel**

Add after the Interview panel closing `</section>` (before the closing `</aside>`):

```html
        <section class="panel">
          <div class="section-head">
            <div>
              <p class="kicker">Agent State</p>
              <h2>智能体状态</h2>
            </div>
            <button id="reloadRadarBtn" class="button small">刷新</button>
          </div>
          <div class="chart-container">
            <canvas id="radarChart" width="400" height="400" aria-label="agent state radar chart"></canvas>
            <p id="radarPlaceholder" class="placeholder-text">暂无状态数据。</p>
          </div>
        </section>
```

- [ ] **Step 3: Add economy summary panel**

Add after the Memory panel in the lower grid, before the Run Log panel:

```html
      <section class="panel">
        <div class="section-head">
          <div>
            <p class="kicker">Economy</p>
            <h2>经济状况</h2>
          </div>
          <button id="reloadEconBtn" class="button small">刷新</button>
        </div>
        <div id="economySummary" class="economy-grid">
          <p class="placeholder-text">暂无经济数据。</p>
        </div>
      </section>
```

- [ ] **Step 4: Commit**

```bash
git add site/dashboard/index.html
git commit -m "feat: add Chart.js CDN and radar/economy panel markup"
```

---

### Task 3: Add chart styles

**Files:**
- Modify: `site/dashboard/styles.css`

- [ ] **Step 1: Add chart and economy styles**

Append to end of `styles.css`:

```css
.chart-container {
  position: relative;
  width: 100%;
  max-width: 420px;
  margin: 0 auto;
}

.chart-container canvas {
  display: block;
  width: 100% !important;
  height: auto !important;
}

.placeholder-text {
  color: var(--muted);
  font-size: 13px;
  text-align: center;
  padding: 32px 12px;
  margin: 0;
}

.economy-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 8px;
}

.econ-card {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 12px;
  text-align: center;
  background: #fffef9;
}

.econ-card .label {
  font-size: 11px;
  color: var(--muted);
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.econ-card .value {
  font-size: 22px;
  font-weight: 900;
  color: var(--ink);
  margin-top: 4px;
  font-family: "SF Mono", "Cascadia Code", Consolas, monospace;
}

.econ-card .value.positive { color: var(--green); }
.econ-card .value.negative { color: var(--red); }

@media (max-width: 720px) {
  .economy-grid { grid-template-columns: 1fr; }
  .chart-container { max-width: 100%; }
}
```

- [ ] **Step 2: Commit**

```bash
git add site/dashboard/styles.css
git commit -m "feat: add chart and economy card styles"
```

---

### Task 4: Create charts.js — radar chart module

**Files:**
- Create: `site/dashboard/charts.js`

- [ ] **Step 1: Write charts.js**

Complete new file:

```javascript
/* Chart.js wrappers for GAWorld dashboard.
 * Separate module so app.js handles data fetching and charts.js handles Chart.js lifecycle.
 */

const chartState = {
  radar: null,
};

/* ── Radar: agent state dimensions ────────────────────────────── */

const RADAR_LABELS = {
  energy: "精力",
  social: "社交",
  recreation: "娱乐",
  health: "健康",
  hygiene: "卫生",
  environment: "环境",
  hunger: "饱腹",
};

const RADAR_COLORS = {
  border: "rgba(19, 121, 91, 0.85)",
  background: "rgba(19, 121, 91, 0.15)",
  point: "rgba(19, 121, 91, 1)",
};

function initRadarChart(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;
  if (chartState.radar) {
    chartState.radar.destroy();
    chartState.radar = null;
  }
  const ctx = canvas.getContext("2d");
  chartState.radar = new Chart(ctx, {
    type: "radar",
    data: {
      labels: [],
      datasets: [{
        label: "当前状态",
        data: [],
        borderColor: RADAR_COLORS.border,
        backgroundColor: RADAR_COLORS.background,
        pointBackgroundColor: RADAR_COLORS.point,
        pointBorderColor: "#fffef9",
        pointRadius: 4,
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { display: false },
      },
      scales: {
        r: {
          beginAtZero: true,
          max: 1.0,
          ticks: {
            stepSize: 0.2,
            font: { size: 10 },
            backdropColor: "transparent",
          },
          grid: { color: "rgba(203, 215, 205, 0.6)" },
          angleLines: { color: "rgba(203, 215, 205, 0.6)" },
          pointLabels: {
            font: { size: 12, weight: "bold" },
            color: "#17211d",
          },
        },
      },
    },
  });
  return chartState.radar;
}

function updateRadarChart(state) {
  if (!chartState.radar) return;
  const labels = [];
  const values = [];
  for (const [key, label] of Object.entries(RADAR_LABELS)) {
    const val = state[key];
    if (val !== undefined && val !== null) {
      labels.push(label);
      values.push(Number(val));
    }
  }
  if (labels.length === 0) {
    document.getElementById("radarPlaceholder").style.display = "block";
    chartState.radar.canvas.style.display = "none";
    return;
  }
  document.getElementById("radarPlaceholder").style.display = "none";
  chartState.radar.canvas.style.display = "block";
  chartState.radar.data.labels = labels;
  chartState.radar.data.datasets[0].data = values;
  chartState.radar.update();
}
```

- [ ] **Step 2: Commit**

```bash
git add site/dashboard/charts.js
git commit -m "feat: add radar chart module with Chart.js"
```

---

### Task 5: Wire charts into app.js

**Files:**
- Modify: `site/dashboard/app.js`

- [ ] **Step 1: Add radar chart element reference**

Add to the `els` object (after `memoryBox` line, around line 40):

```javascript
  radarChart: document.getElementById("radarChart"),
  radarPlaceholder: document.getElementById("radarPlaceholder"),
  economySummary: document.getElementById("economySummary"),
  reloadRadarBtn: document.getElementById("reloadRadarBtn"),
  reloadEconBtn: document.getElementById("reloadEconBtn"),
```

- [ ] **Step 2: Add loadEconomy function**

Add after `loadMemory()` (around line 177):

```javascript
async function loadEconomy() {
  if (!state.selectedAgentId) return;
  try {
    const payload = await api(`/api/economy/${state.selectedAgentId}`);
    const econ = payload.economy;
    if (!econ || econ.error) {
      els.economySummary.innerHTML = '<p class="placeholder-text">暂无经济数据。</p>';
      return;
    }
    const balance = Number(econ.balance) || 0;
    const income = Number(econ.daily_income) || 0;
    const expense = Number(econ.daily_expense) || 0;
    els.economySummary.innerHTML = `
      <div class="econ-card"><div class="label">余额</div><div class="value ${balance >= 0 ? 'positive' : 'negative'}">${balance.toFixed(0)}</div></div>
      <div class="econ-card"><div class="label">今日收入</div><div class="value positive">+${income.toFixed(0)}</div></div>
      <div class="econ-card"><div class="label">今日支出</div><div class="value negative">-${expense.toFixed(0)}</div></div>
    `;
  } catch (error) {
    els.economySummary.innerHTML = `<p class="placeholder-text">经济数据读取失败: ${error.message}</p>`;
  }
}
```

- [ ] **Step 3: Add loadStateRadar function**

Add after `loadEconomy()`:

```javascript
async function loadStateRadar() {
  if (!state.selectedAgentId) return;
  try {
    const payload = await api(`/api/agents/${state.selectedAgentId}/memory`);
    const agentState = payload.memory && Array.isArray(payload.memory)
      ? payload.memory[payload.memory.length - 1]
      : null;
    const radarState = (agentState && agentState.state) || {};
    updateRadarChart(radarState);
  } catch (error) {
    els.radarPlaceholder.textContent = "状态数据读取失败";
    els.radarPlaceholder.style.display = "block";
  }
}
```

- [ ] **Step 4: Initialize radar chart in init()**

In the `init()` function (line 333), add after `loadConfig()`:

```javascript
  initRadarChart("radarChart");
```

- [ ] **Step 5: Wire chart loading into agent switch**

In the `bindEvents()` section, the agent select change handler should also call the new load functions. Find the handler (line 315) and add calls:

```javascript
  els.agentSelect.addEventListener("change", async () => {
    state.selectedAgentId = Number(els.agentSelect.value);
    await loadProfile();
    await loadMemory();
    await loadEconomy();
    await loadStateRadar();
    renderTrace();
  });
```

- [ ] **Step 6: Wire reload buttons**

Add in `bindEvents()`, after the existing reloadMemoryBtn handler:

```javascript
  els.reloadRadarBtn.addEventListener("click", () => loadStateRadar().catch((error) => message(error.message, "error")));
  els.reloadEconBtn.addEventListener("click", () => loadEconomy().catch((error) => message(error.message, "error")));
```

- [ ] **Step 7: Load charts on init**

In `init()`, add calls after `loadMemory()`:

```javascript
  await loadEconomy();
  await loadStateRadar();
```

- [ ] **Step 8: Verify no JS errors**

Run: restart the dashboard and check the browser console for errors.
Expected: No `Uncaught ReferenceError: Chart is not defined` or other errors.

- [ ] **Step 9: Commit**

```bash
git add site/dashboard/app.js
git commit -m "feat: wire economy and radar chart into dashboard app"
```

---

### Task 6: Integration check and manual test

- [ ] **Step 1: Verify dashboard starts without errors**

```bash
source .venv/bin/activate && python dashboard_server.py --port 8767 &
sleep 2
curl -s http://localhost:8767/api/config | head -c 200
```

Expected: JSON config response. Kill the server after verifying.

- [ ] **Step 2: Verify economy endpoint**

```bash
curl -s http://localhost:8767/api/economy/1
```

Expected: `{"agent_id":1,"economy":{}}` (no simulation data yet) or populated data.

- [ ] **Step 3: Run existing tests to confirm no regressions**

```bash
source .venv/bin/activate && python -m pytest tests/ -q --tb=short
```

Expected: Same results as before (108 passed, 2 failed).

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: integration cleanup after dashboard Phase 1"
```
