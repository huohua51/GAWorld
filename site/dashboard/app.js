const state = {
  config: null,
  agents: [],
  selectedAgentId: null,
  lifeEventTemplates: [],
  lifeEvents: [],
  trace: null,
  frameIndex: 0,
  pollTimer: null,
  avatarCache: new Map(),
  tracePlaying: false,
  traceTimer: null,
  traceSpeedMs: 1200,
};

const els = {
  agentIdsInput: document.getElementById("agentIdsInput"),
  simDaysInput: document.getElementById("simDaysInput"),
  secondsPerDayInput: document.getElementById("secondsPerDayInput"),
  timeStepInput: document.getElementById("timeStepInput"),
  defaultProviderSelect: document.getElementById("defaultProviderSelect"),
  scheduleProviderSelect: document.getElementById("scheduleProviderSelect"),
  realtimeInput: document.getElementById("realtimeInput"),
  saveConfigBtn: document.getElementById("saveConfigBtn"),
  runBtn: document.getElementById("runBtn"),
  resetRunBtn: document.getElementById("resetRunBtn"),
  stopBtn: document.getElementById("stopBtn"),
  runStatusBadge: document.getElementById("runStatusBadge"),
  traceStatus: document.getElementById("traceStatus"),
  messageLine: document.getElementById("messageLine"),
  reloadTraceBtn: document.getElementById("reloadTraceBtn"),
  tracePlayBtn: document.getElementById("tracePlayBtn"),
  frameTitle: document.getElementById("frameTitle"),
  mapCanvas: document.getElementById("mapCanvas"),
  timelineSlider: document.getElementById("timelineSlider"),
  timelineLabel: document.getElementById("timelineLabel"),
  latestFrameBox: document.getElementById("latestFrameBox"),
  selectedAgentAvatar: document.getElementById("selectedAgentAvatar"),
  agentSelect: document.getElementById("agentSelect"),
  profileEditor: document.getElementById("profileEditor"),
  saveProfileBtn: document.getElementById("saveProfileBtn"),
  refreshAgentBtn: document.getElementById("refreshAgentBtn"),
  interviewContext: document.getElementById("interviewContext"),
  interviewQuestions: document.getElementById("interviewQuestions"),
  interviewBtn: document.getElementById("interviewBtn"),
  interviewOutput: document.getElementById("interviewOutput"),
  lifeEventTemplateSelect: document.getElementById("lifeEventTemplateSelect"),
  lifeEventAgentInput: document.getElementById("lifeEventAgentInput"),
  lifeEventModeSelect: document.getElementById("lifeEventModeSelect"),
  lifeEventDayInput: document.getElementById("lifeEventDayInput"),
  lifeEventTimeInput: document.getElementById("lifeEventTimeInput"),
  lifeEventSeverityInput: document.getElementById("lifeEventSeverityInput"),
  lifeEventTitleInput: document.getElementById("lifeEventTitleInput"),
  lifeEventDescriptionInput: document.getElementById("lifeEventDescriptionInput"),
  useSelectedAgentBtn: document.getElementById("useSelectedAgentBtn"),
  addLifeEventBtn: document.getElementById("addLifeEventBtn"),
  reloadLifeEventsBtn: document.getElementById("reloadLifeEventsBtn"),
  lifeEventListBox: document.getElementById("lifeEventListBox"),
  reloadStatusBtn: document.getElementById("reloadStatusBtn"),
};

const ctx = els.mapCanvas.getContext("2d");

// ── Charts State ─────────────────────────────────────────────
const chartState = {
  stateData: null,
  economyDailyData: null,
  macroData: null,
  locationData: {},
  interventionData: null,
  socialNetworkData: null,
  workMarketData: null,
  activitySummaryData: null,
  timelineData: {},
  selectedStateAgents: [],
  selectedEconomyAgents: [],
  selectedLocationAgents: [],
  selectedInterventionAgents: [],
  selectedTimelineAgents: [],
  stepTimeMaps: {}, // agentId -> [{step, day, time}]
  stateCharts: {}, // agentId -> echarts instance
  economyCharts: {},
  locationCharts: {},
  interventionCharts: {},
  socialChart: null,
  workChart: null,
  activitySummaryChart: null,
};

// ── Charts Elements ───────────────────────────────────────────
const chartEls = {
  stateAgentSelect: document.getElementById("stateAgentSelect"),
  economyAgentSelect: document.getElementById("economyAgentSelect"),
  locationAgentSelect: document.getElementById("locationAgentSelect"),
  interventionAgentSelect: document.getElementById("interventionAgentSelect"),
  timelineAgentSelect: document.getElementById("timelineAgentSelect"),
  stateChartContainer: document.getElementById("stateChartContainer"),
  economyChartContainer: document.getElementById("economyChartContainer"),
  locationChartContainer: document.getElementById("locationChartContainer"),
  interventionChartContainer: document.getElementById("interventionChartContainer"),
  timelineContainer: document.getElementById("timelineContainer"),
  activitySummaryChart: document.getElementById("activitySummaryChart"),
  socialChart: document.getElementById("socialChart"),
  workChart: document.getElementById("workChart"),
  macroInfoContent: document.getElementById("macroInfoContent"),
  reloadStateChartBtn: document.getElementById("reloadStateChartBtn"),
  reloadEconomyChartBtn: document.getElementById("reloadEconomyChartBtn"),
  reloadLocationChartBtn: document.getElementById("reloadLocationChartBtn"),
  reloadSocialChartBtn: document.getElementById("reloadSocialChartBtn"),
  reloadInterventionChartBtn: document.getElementById("reloadInterventionChartBtn"),
  reloadActivityChartBtn: document.getElementById("reloadActivityChartBtn"),
  reloadWorkChartBtn: document.getElementById("reloadWorkChartBtn"),
  reloadTimelineBtn: document.getElementById("reloadTimelineBtn"),
};

// ── Multi-select helper ───────────────────────────────────────
function buildAgentMultiOptions(selectEl, agents, selectedIds) {
  if (!selectEl) return;
  selectEl.innerHTML = "";
  agents.forEach((id) => {
    const opt = document.createElement("option");
    opt.value = String(id);
    const name = (state.agents.find((a) => Number(a.id) === Number(id)) || {}).name || `Agent ${id}`;
    opt.textContent = `${String(id).padStart(2, "0")} · ${name}`;
    opt.selected = selectedIds.includes(Number(id));
    selectEl.appendChild(opt);
  });
  syncAgentCheckboxList(selectEl);
}

function getSelectedAgents(selectEl) {
  if (!selectEl) return [];
  return Array.from(selectEl.selectedOptions).map((o) => Number(o.value));
}

function enableClickToggleMultiSelect(selectEl) {
  if (!selectEl || !selectEl.multiple || selectEl.dataset.clickToggle === "1") return;
  selectEl.dataset.clickToggle = "1";
  selectEl.title = selectEl.title || "单击切换选择；Ctrl/Shift 也可多选";
  selectEl.addEventListener("mousedown", (event) => {
    if (event.target.tagName !== "OPTION") return;
    event.preventDefault();
    event.target.selected = !event.target.selected;
    selectEl.focus();
    selectEl.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

function enhanceAgentMultiSelect(selectEl) {
  if (!selectEl || !selectEl.multiple || selectEl.dataset.checkboxList === "1") return;
  selectEl.dataset.checkboxList = "1";
  selectEl.classList.add("agent-native-select");
  const list = document.createElement("div");
  list.className = "agent-check-list";
  list.setAttribute("role", "listbox");
  list.setAttribute("aria-multiselectable", "true");
  selectEl.insertAdjacentElement("afterend", list);
  syncAgentCheckboxList(selectEl);
}

function syncAgentCheckboxList(selectEl) {
  if (!selectEl || selectEl.dataset.checkboxList !== "1") return;
  const list = selectEl.nextElementSibling;
  if (!list || !list.classList.contains("agent-check-list")) return;
  list.innerHTML = "";
  Array.from(selectEl.options).forEach((option) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `agent-check-item${option.selected ? " selected" : ""}`;
    item.setAttribute("role", "option");
    item.setAttribute("aria-selected", option.selected ? "true" : "false");
    item.dataset.value = option.value;
    item.innerHTML = `<span class="agent-check-box" aria-hidden="true"></span><span class="agent-check-text">${option.textContent}</span>`;
    item.addEventListener("click", () => {
      option.selected = !option.selected;
      selectEl.dispatchEvent(new Event("change", { bubbles: true }));
      syncAgentCheckboxList(selectEl);
    });
    list.appendChild(item);
  });
}

// ── Chart Color Palettes ─────────────────────────────────────
const CHART_COLORS = [
  "#13795b", "#b73e3e", "#385866", "#d6a81e",
  "#6e5f97", "#1f8a9b", "#8a5b30", "#82a661",
];

// Metric category color map (per agent chart) - distinct colors per metric
const METRIC_CATEGORY_COLORS = {
  psychological: ["#1f77b4", "#3a8ed8", "#5fa6e8", "#84bff0", "#a9d4f5", "#cde6fa", "#e8f1fc", "#4a7fb8", "#2e5f8c", "#6b9ed4"],
  city: ["#ff7f0e", "#ff9933", "#ffb366", "#ffcc99", "#ffe0bf", "#ff5722", "#e64a19", "#bf360c", "#f57c00", "#ffa726"],
  policy: ["#9467bd", "#a98ec9", "#bca6d6", "#cfbfe2", "#dcd0eb", "#7b3f9b", "#5d2c7a", "#9b6dc7", "#b389d6", "#cab0e0"],
  intervention: ["#e377c2", "#e890d1", "#efa9dc", "#f4c2e6", "#f9dbef", "#c44ba0", "#a02e7f", "#d363ab", "#dc85c0", "#eaa6d4"],
  economic: ["#2ca02c", "#3eb53e", "#5bc45b", "#7fd47f", "#a3e2a3", "#c8f0c8", "#1a7a1a", "#0e5c0e", "#37a137", "#52b952"],
};

const ECONOMY_COLORS = {
  income: "#24a148",
  expense: "#2563eb",
  net: "#7c3aed",
  balance: "#16a34a",
  checking: "#0284c7",
  savings: "#0ea5e9",
  investment: "#f97316",
  housing_fund: "#ea580c",
  wealth_drive: "#9333ea",
  econ_security: "#64748b",
  hourly_income: "#0891b2",
  engel_coefficient: "#db2777",
};

function metricCategory(metric) {
  if (["emotion", "stress", "energy", "hunger", "social_need", "fatigue_debt", "self_control", "time_pressure"].includes(metric)) return "psychological";
  if (["city_identity", "mobility_intent"].includes(metric)) return "city";
  if (["policy_sensitivity", "platform_dependence", "risk_preference", "voice_propensity"].includes(metric)) return "policy";
  if (["stance_score", "toxicity_score", "misinformation_risk", "cross_viewpoint_exposure", "intervention_reward"].includes(metric)) return "intervention";
  return "economic";
}

function getMetricColor(metric, indexInCategory) {
  const cat = metricCategory(metric);
  const palette = METRIC_CATEGORY_COLORS[cat];
  return palette[indexInCategory % palette.length];
}

// ── Per-agent chart panel creation helper ────────────────────
function clearChartContainer(containerEl) {
  if (!containerEl) return;
  containerEl.innerHTML = "";
}

function createAgentSubPanel(containerEl, agentId, agentName, title) {
  const wrap = document.createElement("div");
  wrap.className = "agent-sub-panel";
  wrap.dataset.agentId = String(agentId);
  const header = document.createElement("div");
  header.className = "agent-sub-head";
  header.innerHTML = `<span class="agent-sub-id">#${String(agentId).padStart(2, "0")}</span><span class="agent-sub-name">${agentName}</span>`;
  wrap.appendChild(header);
  if (title) {
    const subTitle = document.createElement("div");
    subTitle.className = "agent-sub-title";
    subTitle.textContent = title;
    wrap.appendChild(subTitle);
  }
  const chartHolder = document.createElement("div");
  chartHolder.className = "agent-sub-chart";
  wrap.appendChild(chartHolder);
  containerEl.appendChild(wrap);
  return chartHolder;
}

// Build a step -> day map for axis labelling
function buildStepDayLabelFormatter(steps) {
  // steps: [{step, day, time}, ...]
  const stepToDay = {};
  let prevDay = null;
  steps.forEach((entry) => {
    if (entry.day == null) return;
    stepToDay[entry.step] = entry.day;
    prevDay = entry.day;
  });
  return (value) => {
    const day = stepToDay[value];
    if (day != null) {
      return `Day ${day}\nstep ${value}`;
    }
    return `step ${value}`;
  };
}

// ── State chart (one chart per agent) ───────────────────────
async function loadStateChartData() {
  chartState.stateData = await api("/api/metrics/state");
  // Default to first agent selected
  if (!chartState.selectedStateAgents.length && chartState.stateData.agents && chartState.stateData.agents.length) {
    chartState.selectedStateAgents = [chartState.stateData.agents[0]];
  }
  buildAgentMultiOptions(chartEls.stateAgentSelect, chartState.stateData.agents || [], chartState.selectedStateAgents);
  // Sync the select element selection
  Array.from(chartEls.stateAgentSelect.options).forEach((opt) => {
    opt.selected = chartState.selectedStateAgents.includes(Number(opt.value));
  });
  await renderStateCharts();
}

async function renderStateCharts() {
  if (!chartState.stateData) return;
  const { data, metrics } = chartState.stateData;
  const container = chartEls.stateChartContainer;
  if (!container) return;
  // Dispose existing chart instances
  Object.values(chartState.stateCharts).forEach((c) => { try { c.dispose(); } catch (_e) {} });
  chartState.stateCharts = {};
  clearChartContainer(container);
  if (!chartState.selectedStateAgents.length || !metrics.length) {
    container.innerHTML = '<div class="chart-empty">请选择至少一个 Agent</div>';
    return;
  }
  // Build per-agent sub panels
  for (const agentId of chartState.selectedStateAgents) {
    const agentMeta = (state.agents.find((a) => Number(a.id) === Number(agentId))) || {};
    const agentName = agentMeta.name || `Agent ${agentId}`;
    const holder = createAgentSubPanel(container, agentId, agentName, "状态指标趋势");
    // Lazy load step-time map
    if (!chartState.stepTimeMaps[agentId]) {
      try {
        chartState.stepTimeMaps[agentId] = await api(`/api/metrics/step-time-map/${agentId}`);
      } catch (_e) {
        chartState.stepTimeMaps[agentId] = [];
      }
    }
    const stepMap = chartState.stepTimeMaps[agentId] || [];
    // Group by metric for this agent
    const metricData = {};
    data.filter((r) => Number(r.agent_id) === Number(agentId)).forEach((r) => {
      if (!metricData[r.metric]) metricData[r.metric] = [];
      metricData[r.metric].push([r.step, r.value]);
    });
    // Sort each series
    Object.keys(metricData).forEach((m) => {
      metricData[m].sort((a, b) => a[0] - b[0]);
    });
    // Build series: one line per metric, color from category palette
    const usedColors = {};
    const series = [];
    Object.keys(metricData).forEach((m) => {
      if (!usedColors[metricCategory(m)]) usedColors[metricCategory(m)] = 0;
      const colorIdx = usedColors[metricCategory(m)]++;
      const color = getMetricColor(m, colorIdx);
      series.push({
        name: m,
        type: "line",
        data: metricData[m],
        showSymbol: metricData[m].length <= 24,
        lineStyle: { color, width: 1.5 },
        itemStyle: { color },
        smooth: 0.2,
        emphasis: { focus: "series" },
      });
    });
    // All steps for x-axis
    const allSteps = [...new Set(data.filter((r) => Number(r.agent_id) === Number(agentId)).map((r) => r.step))].sort((a, b) => a - b);
    const fmt = buildStepDayLabelFormatter(stepMap);
    const chart = echarts.init(holder);
    chart.setOption({
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        formatter: (params) => {
          if (!params || !params.length) return "";
          const step = params[0].value[0];
          const dayInfo = stepMap.find((s) => s.step === step);
          let s = `<strong>step ${step}</strong>`;
          if (dayInfo && dayInfo.day != null) s += ` &nbsp;Day ${dayInfo.day}`;
          if (dayInfo && dayInfo.time) s += ` &nbsp;${dayInfo.time}`;
          s += "<br/>";
          params.forEach((p) => {
            s += `<span style="color:${p.color}">●</span> ${p.seriesName}: ${p.value[1].toFixed(4)}<br/>`;
          });
          return s;
        },
      },
      legend: { type: "scroll", bottom: 4, textStyle: { fontSize: 10, color: "#17211d" }, padding: [4, 0, 0, 0] },
      grid: { top: 8, right: 16, bottom: 80, left: 56, containLabel: false },
      xAxis: {
        type: "category",
        data: allSteps.map(String),
        name: "step",
        nameLocation: "end",
        nameGap: 18,
        nameTextStyle: { color: "#17211d", fontSize: 10, fontWeight: 700, padding: [8, 0, 0, 0] },
        axisLabel: {
          color: "#17211d",
          fontSize: 10,
          formatter: fmt,
          interval: Math.max(0, Math.floor(allSteps.length / 12) - 1),
          margin: 12,
        },
        axisLine: { lineStyle: { color: "#5c6860" } },
      },
      yAxis: {
        type: "value",
        name: "Value",
        nameLocation: "center",
        nameGap: 42,
        nameTextStyle: { color: "#17211d", fontSize: 10, fontWeight: 700 },
        axisLabel: { color: "#17211d", fontSize: 10, formatter: (v) => v.toFixed(2) },
        axisLine: { lineStyle: { color: "#5c6860" } },
        splitLine: { lineStyle: { color: "#cbd7cd" } },
      },
      series,
    }, true);
    chartState.stateCharts[agentId] = chart;
  }
}

// ── Economy chart (one chart per agent) ─────────────────────
async function loadEconomyChartData() {
  chartState.economyDailyData = await api("/api/metrics/economy/daily");
  if (!chartState.selectedEconomyAgents.length && chartState.economyDailyData.agents && chartState.economyDailyData.agents.length) {
    chartState.selectedEconomyAgents = [chartState.economyDailyData.agents[0]];
  }
  buildAgentMultiOptions(chartEls.economyAgentSelect, chartState.economyDailyData.agents || [], chartState.selectedEconomyAgents);
  Array.from(chartEls.economyAgentSelect.options).forEach((opt) => {
    opt.selected = chartState.selectedEconomyAgents.includes(Number(opt.value));
  });
  await loadMacroChartData();
  await renderEconomyCharts();
}

async function loadMacroChartData() {
  chartState.macroData = await api("/api/metrics/macro");
  // Update macro info bar
  if (chartEls.macroInfoContent && chartState.macroData) {
    const d = chartState.macroData;
    const phase = d.phase || "—";
    const infl = d.inflation_rate != null ? (d.inflation_rate * 100).toFixed(2) + "%" : "—";
    const unemp = d.unemployment_rate != null ? (d.unemployment_rate * 100).toFixed(2) + "%" : "—";
    const cum = d.cumulative_inflation != null ? ((d.cumulative_inflation - 1) * 100).toFixed(2) + "%" : "—";
    const phaseCounter = d.phase_day_counter != null ? d.phase_day_counter : "?";
    const phaseDuration = d.phase_duration != null ? d.phase_duration : "?";
    chartEls.macroInfoContent.innerHTML = `<b>阶段</b> ${phase} (${phaseCounter}/${phaseDuration}) · <b>通胀</b> ${infl} · <b>失业</b> ${unemp} · <b>累积通胀</b> ${cum}`;
  }
}

async function renderEconomyCharts() {
  if (!chartState.economyDailyData) return;
  const { data } = chartState.economyDailyData;
  const container = chartEls.economyChartContainer;
  if (!container) return;
  Object.values(chartState.economyCharts).forEach((c) => { try { c.dispose(); } catch (_e) {} });
  chartState.economyCharts = {};
  clearChartContainer(container);
  if (!chartState.selectedEconomyAgents.length) {
    container.innerHTML = '<div class="chart-empty">请选择至少一个 Agent</div>';
    return;
  }
  for (const agentId of chartState.selectedEconomyAgents) {
    const agentMeta = (state.agents.find((a) => Number(a.id) === Number(agentId))) || {};
    const agentName = agentMeta.name || `Agent ${agentId}`;
    const holder = createAgentSubPanel(container, agentId, agentName, "左：现金流与净资产；右上：账户余额；右下：安全感、收入效率与消费结构");

    const rows = data.filter((r) => Number(r.agent_id) === Number(agentId));
    if (!rows.length) {
      holder.innerHTML = '<div class="chart-empty">无经济数据</div>';
      continue;
    }
    // Aggregate by day (keep first row per day)
    const dayMap = {};
    rows.forEach((r) => { if (!dayMap[r.day]) dayMap[r.day] = r; });
    const days = Object.keys(dayMap).map(Number).sort((a, b) => a - b);

    const income = days.map((d) => [d, dayMap[d].income]);
    const expense = days.map((d) => [d, dayMap[d].expense]);
    const net = days.map((d) => [d, dayMap[d].net]);
    const balance = days.map((d) => [d, dayMap[d].balance]);
    const checking = days.map((d) => [d, dayMap[d].checking]);
    const savings = days.map((d) => [d, dayMap[d].savings]);
    const investment = days.map((d) => [d, dayMap[d].investment]);
    const housing = days.map((d) => [d, dayMap[d].housing_fund]);
    const wealthDrive = days.map((d) => [d, dayMap[d].wealth_drive]);
    const econSec = days.map((d) => [d, dayMap[d].econ_security]);
    const engel = days.map((d) => [d, dayMap[d].engel_coefficient]);
    const hourly = days.map((d) => [d, dayMap[d].hourly_income]);

    const C = ECONOMY_COLORS;
    const series = [
      // LEFT GRID: income/expense (bar) + balance/net (line, right axis)
      { name: "income", type: "bar", data: income, xAxisIndex: 0, yAxisIndex: 0, itemStyle: { color: C.income, opacity: 0.92 }, barMaxWidth: 16, barGap: 0, barCategoryGap: "18%" },
      { name: "expense", type: "bar", data: expense, xAxisIndex: 0, yAxisIndex: 0, itemStyle: { color: C.expense, opacity: 0.9 }, barMaxWidth: 16, barCategoryGap: "18%" },
      { name: "net", type: "line", data: net, xAxisIndex: 0, yAxisIndex: 1, lineStyle: { color: C.net, width: 2.2 }, itemStyle: { color: C.net }, smooth: 0.2, showSymbol: true, symbolSize: 7 },
      { name: "balance", type: "line", data: balance, xAxisIndex: 0, yAxisIndex: 1, lineStyle: { color: C.balance, width: 2.4 }, itemStyle: { color: C.balance }, smooth: 0.2, showSymbol: true, symbolSize: 7 },

      // RIGHT GRID (top): account balances
      { name: "checking", type: "line", data: checking, xAxisIndex: 1, yAxisIndex: 2, lineStyle: { color: C.checking, width: 2 }, itemStyle: { color: C.checking }, smooth: 0.2, showSymbol: true, symbolSize: 6 },
      { name: "savings", type: "line", data: savings, xAxisIndex: 1, yAxisIndex: 2, lineStyle: { color: C.savings, width: 2 }, itemStyle: { color: C.savings }, smooth: 0.2, showSymbol: true, symbolSize: 6 },
      { name: "investment", type: "line", data: investment, xAxisIndex: 1, yAxisIndex: 2, lineStyle: { color: C.investment, width: 2 }, itemStyle: { color: C.investment }, smooth: 0.2, showSymbol: true, symbolSize: 6 },
      { name: "housing_fund", type: "line", data: housing, xAxisIndex: 1, yAxisIndex: 2, lineStyle: { color: C.housing_fund, width: 2 }, itemStyle: { color: C.housing_fund }, smooth: 0.2, showSymbol: true, symbolSize: 6 },

      // RIGHT GRID (bottom): ratios / scores
      { name: "wealth_drive", type: "line", data: wealthDrive, xAxisIndex: 2, yAxisIndex: 3, lineStyle: { color: C.wealth_drive, width: 2 }, itemStyle: { color: C.wealth_drive }, smooth: 0.2, showSymbol: true, symbolSize: 6 },
      { name: "econ_security", type: "line", data: econSec, xAxisIndex: 2, yAxisIndex: 3, lineStyle: { color: C.econ_security, width: 2 }, itemStyle: { color: C.econ_security }, smooth: 0.2, showSymbol: true, symbolSize: 6 },
      { name: "hourly_income", type: "line", data: hourly, xAxisIndex: 2, yAxisIndex: 3, lineStyle: { color: C.hourly_income, width: 2 }, itemStyle: { color: C.hourly_income }, smooth: 0.2, showSymbol: true, symbolSize: 6 },
      { name: "engel_coefficient", type: "line", data: engel, xAxisIndex: 2, yAxisIndex: 3, lineStyle: { color: C.engel_coefficient, width: 2 }, itemStyle: { color: C.engel_coefficient }, smooth: 0.2, showSymbol: true, symbolSize: 6 },
    ];

    const chart = echarts.init(holder);
    chart.setOption({
      backgroundColor: "transparent",
      title: [
        { text: "现金流 / 净资产", left: 48, top: 0, textStyle: { color: "#385866", fontSize: 11, fontWeight: 800 } },
        { text: "账户余额", left: "55%", top: 0, textStyle: { color: "#385866", fontSize: 11, fontWeight: 800 } },
        { text: "行为比率 / 得分", left: "55%", top: "58%", textStyle: { color: "#385866", fontSize: 11, fontWeight: 800 } },
      ],
      tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
      legend: { type: "scroll", bottom: 6, left: 18, right: 18, itemWidth: 18, itemHeight: 10, textStyle: { fontSize: 11, color: "#17211d", fontWeight: 700 }, padding: [4, 0, 0, 0] },
      grid: [
        // Left: inc/exp + balance (primary yAxis index 0, secondary index 1)
        { left: 58, right: "55%", top: 38, bottom: 118 },
        // Right top: accounts (yAxis index 2)
        { left: "56%", right: 18, top: 38, bottom: 118, height: "40%" },
        // Right bottom: rates/scores (yAxis index 3)
        { left: "56%", right: 18, top: "65%", bottom: 118, height: "22%" },
      ],
      xAxis: [
        { type: "category", data: days.map(String), gridIndex: 0, axisLabel: { color: "#17211d", fontSize: 9 }, axisLine: { lineStyle: { color: "#5c6860" } } },
        { type: "category", data: days.map(String), gridIndex: 1, axisLabel: { color: "#17211d", fontSize: 9, show: false }, axisLine: { lineStyle: { color: "#5c6860" } } },
        { type: "category", data: days.map(String), gridIndex: 2, axisLabel: { color: "#17211d", fontSize: 9 }, axisLine: { lineStyle: { color: "#5c6860" } } },
      ],
      yAxis: [
        // index 0: Left primary (income/expense)
        { type: "value", gridIndex: 0, name: "收入/支出", nameLocation: "center", nameGap: 36, nameTextStyle: { color: "#17211d", fontSize: 9 }, axisLabel: { color: "#17211d", fontSize: 9, formatter: (v) => v.toFixed(0) }, splitLine: { lineStyle: { color: "#cbd7cd" } } },
        // index 1: Left secondary (balance)
        { type: "value", gridIndex: 0, name: "资产", nameLocation: "center", nameGap: 50, nameTextStyle: { color: "#17211d", fontSize: 9 }, axisLabel: { color: "#17211d", fontSize: 9, formatter: (v) => v.toFixed(0) }, splitLine: { show: false } },
        // index 2: Right top (accounts)
        { type: "value", gridIndex: 1, name: "账户", nameLocation: "center", nameGap: 36, nameTextStyle: { color: "#17211d", fontSize: 9 }, axisLabel: { color: "#17211d", fontSize: 9, formatter: (v) => v.toFixed(0) }, splitLine: { lineStyle: { color: "#cbd7cd" } } },
        // index 3: Right bottom (rates/scores)
        { type: "value", gridIndex: 2, name: "比率/得分", nameLocation: "center", nameGap: 36, nameTextStyle: { color: "#17211d", fontSize: 9 }, axisLabel: { color: "#17211d", fontSize: 9 }, splitLine: { lineStyle: { color: "#cbd7cd" } } },
      ],
      series,
    }, true);
    chartState.economyCharts[agentId] = chart;
  }
}

// ── Location chart (one panel per agent) ────────────────────
async function loadLocationChartData() {
  const container = chartEls.locationChartContainer;
  if (!container) return;
  Object.values(chartState.locationCharts).forEach((c) => { try { c.dispose(); } catch (_e) {} });
  chartState.locationCharts = {};
  chartState.locationData = {};
  clearChartContainer(container);
  if (!chartState.selectedLocationAgents.length) {
    container.innerHTML = '<div class="chart-empty">请选择至少一个 Agent</div>';
    return;
  }
  // Build the dropdown (use state agents)
  buildAgentMultiOptions(chartEls.locationAgentSelect, (chartState.stateData && chartState.stateData.agents) || state.agents.map((a) => a.id), chartState.selectedLocationAgents);
  Array.from(chartEls.locationAgentSelect.options).forEach((opt) => {
    opt.selected = chartState.selectedLocationAgents.includes(Number(opt.value));
  });
  for (const agentId of chartState.selectedLocationAgents) {
    // Load per-day timeline from new endpoint
    let history;
    try {
      history = await api(`/api/metrics/location-history/${agentId}`);
    } catch (_e) {
      history = { days: [], is_demo: true };
    }
    chartState.locationData[agentId] = history;
    const agentMeta = (state.agents.find((a) => Number(a.id) === Number(agentId))) || {};
    const agentName = agentMeta.name || `Agent ${agentId}`;
    const holder = createAgentSubPanel(container, agentId, agentName, "每天每个时间点到达过的地点");

    if (!history.days || !history.days.length) {
      holder.innerHTML = '<div class="chart-empty">暂无位置数据</div>';
      continue;
    }

    // Top facts row
    const latestDay = history.days[history.days.length - 1];
    const lastItem = latestDay.items[latestDay.items.length - 1];
    const facts = document.createElement("div");
    facts.className = "loc-facts";
    const factRows = [
      { label: "家", value: lastItem.location ? "" : "" },
      { label: "最新到达", value: `${latestDay.date || ""} ${lastItem.time} @ ${lastItem.location}` },
      { label: "上次交通", value: `${lastItem.transport_mode || "—"} · ${(lastItem.distance_km || 0).toFixed(2)} km` },
    ];
    factRows.forEach((f) => {
      const row = document.createElement("div");
      row.className = "loc-row";
      row.innerHTML = `<span class="loc-label">${f.label}</span><span class="loc-value">${f.value}</span>`;
      facts.appendChild(row);
    });
    holder.appendChild(facts);

    // Per-day collapsible tables
    const list = document.createElement("div");
    list.className = "loc-day-list";
    history.days.forEach((day) => {
      const details = document.createElement("details");
      details.className = "loc-day";
      details.open = history.days.length <= 2; // auto-open if few days
      const summary = document.createElement("summary");
      summary.innerHTML = `<b>Day ${day.day}</b> · ${day.date || ""} ${day.weekday || ""} · <span class="muted">${day.items.length} 个 step</span>`;
      details.appendChild(summary);
      const table = document.createElement("table");
      table.className = "loc-table";
      table.innerHTML = `
        <thead>
          <tr>
            <th>时间</th>
            <th>地点</th>
            <th>活动</th>
            <th>交通</th>
            <th>距离(km)</th>
            <th>→ 下一站</th>
          </tr>
        </thead>
        <tbody></tbody>
      `;
      const tbody = table.querySelector("tbody");
      day.items.forEach((it) => {
        const tr = document.createElement("tr");
        const inTransitTag = it.in_transit ? ' <span class="in-transit">在途</span>' : "";
        tr.innerHTML = `
          <td class="loc-time">${it.time}${inTransitTag}</td>
          <td class="loc-place">${it.location}</td>
          <td class="loc-act">${it.activity || "—"}<br/><small class="sched">${it.scheduled_activity || ""}</small></td>
          <td class="loc-mode">${it.transport_mode || "—"}</td>
          <td class="loc-dist">${(it.distance_km || 0).toFixed(2)}</td>
          <td class="loc-next">${it.next_time ? `${it.next_time} → ${it.next_location}` : "—"}</td>
        `;
        tbody.appendChild(tr);
      });
      details.appendChild(table);
      list.appendChild(details);
    });
    holder.appendChild(list);
  }
}

// ── Social network chart (single force-directed graph) ──────
async function loadActivitySummaryData() {
  chartState.activitySummaryData = await api("/api/metrics/activity-summary");
  renderActivitySummaryChart();
}

function renderActivitySummaryChart() {
  const container = chartEls.activitySummaryChart;
  const data = chartState.activitySummaryData;
  if (!container || !data) return;
  if (chartState.activitySummaryChart) {
    try { chartState.activitySummaryChart.dispose(); } catch (_e) {}
    chartState.activitySummaryChart = null;
  }
  if (!data.frame_count) {
    container.innerHTML = '<div class="chart-empty">暂无轨迹汇总数据</div>';
    return;
  }
  container.innerHTML = "";
  const activity = data.activity_counts || [];
  const locations = data.location_counts || [];
  const transport = data.transport_counts || [];
  const distance = data.distance_by_agent || [];
  const chart = echarts.init(container);
  chart.setOption({
    backgroundColor: "transparent",
    title: [
      { text: `轨迹帧 ${data.frame_count} · 天数 ${data.day_count} · Agent ${data.agent_count}`, left: 8, top: 0, textStyle: { fontSize: 12, color: "#13795b", fontWeight: 900 } },
      { text: "活动类型", left: 8, top: 30, textStyle: { fontSize: 11, color: "#385866", fontWeight: 800 } },
      { text: "热门地点", left: "52%", top: 30, textStyle: { fontSize: 11, color: "#385866", fontWeight: 800 } },
      { text: "交通方式", left: 8, top: "56%", textStyle: { fontSize: 11, color: "#385866", fontWeight: 800 } },
      { text: "Agent 通勤距离", left: "52%", top: "56%", textStyle: { fontSize: 11, color: "#385866", fontWeight: 800 } },
    ],
    tooltip: { trigger: "item" },
    grid: [
      { left: 90, right: "52%", top: 58, height: "32%" },
      { left: "58%", right: 20, top: 58, height: "32%" },
      { left: "58%", right: 20, top: "66%", bottom: 22 },
    ],
    xAxis: [
      { type: "value", gridIndex: 0, name: "次数", nameLocation: "end", nameTextStyle: { color: "#385866", fontSize: 10, fontWeight: 700 }, axisLabel: { color: "#17211d", fontSize: 10 }, splitLine: { lineStyle: { color: "#cbd7cd" } } },
      { type: "value", gridIndex: 1, name: "次数", nameLocation: "end", nameTextStyle: { color: "#385866", fontSize: 10, fontWeight: 700 }, axisLabel: { color: "#17211d", fontSize: 10 }, splitLine: { lineStyle: { color: "#cbd7cd" } } },
      { type: "category", gridIndex: 2, name: "Agent", nameLocation: "middle", nameGap: 28, data: distance.map((d) => `#${d.agent_id}`), axisLabel: { color: "#17211d", fontSize: 10 }, axisLine: { lineStyle: { color: "#5c6860" } } },
    ],
    yAxis: [
      { type: "category", gridIndex: 0, inverse: true, data: activity.map((d) => d.name), axisLabel: { color: "#17211d", fontSize: 10 }, axisLine: { lineStyle: { color: "#5c6860" } } },
      { type: "category", gridIndex: 1, inverse: true, data: locations.map((d) => d.name), axisLabel: { color: "#17211d", fontSize: 10, width: 110, overflow: "truncate" }, axisLine: { lineStyle: { color: "#5c6860" } } },
      { type: "value", gridIndex: 2, name: "km", nameLocation: "end", nameTextStyle: { color: "#385866", fontSize: 10, fontWeight: 700 }, axisLabel: { color: "#17211d", fontSize: 10 }, splitLine: { lineStyle: { color: "#cbd7cd" } } },
    ],
    series: [
      { name: "活动次数", type: "bar", xAxisIndex: 0, yAxisIndex: 0, data: activity.map((d) => d.value), itemStyle: { color: "#13795b" }, barMaxWidth: 14 },
      { name: "到访次数", type: "bar", xAxisIndex: 1, yAxisIndex: 1, data: locations.map((d) => d.value), itemStyle: { color: "#385866" }, barMaxWidth: 14 },
      { name: "交通方式", type: "pie", radius: ["24%", "42%"], center: ["23%", "77%"], data: transport, avoidLabelOverlap: true, minShowLabelAngle: 8, label: { color: "#17211d", fontSize: 10, formatter: "{b}\n{c}" }, labelLine: { length: 14, length2: 18 }, itemStyle: { borderColor: "#fffef9", borderWidth: 1 } },
      { name: "通勤距离", type: "bar", xAxisIndex: 2, yAxisIndex: 2, data: distance.map((d) => d.value), itemStyle: { color: "#d6a81e" }, barMaxWidth: 24 },
    ],
  }, true);
  chartState.activitySummaryChart = chart;
}

async function loadSocialChartData() {
  chartState.socialNetworkData = await api("/api/metrics/social-network");
  renderSocialChart();
}

function renderSocialChart() {
  if (!chartState.socialNetworkData || !chartEls.socialChart) return;
  const data = chartState.socialNetworkData;
  const demoBadge = document.getElementById("socialDemoBadge");
  if (demoBadge) demoBadge.hidden = !data.is_demo;
  // Dispose existing
  if (chartState.socialChart) {
    try { chartState.socialChart.dispose(); } catch (_e) {}
    chartState.socialChart = null;
  }
  const nodes = data.nodes || [];
  const edges = data.edges || [];
  const categories = [
    { name: "agent", itemStyle: { color: "#13795b" } },
    { name: "ghost", itemStyle: { color: "#d6a81e" } },
  ];
  const tierMap = { inner: 36, close: 26, acquaintance: 16, weak: 10 };
  nodes.forEach((n) => {
    n.category = n.kind === "agent" ? 0 : 1;
    n.symbolSize = n.kind === "agent" ? 38 : (tierMap[n.tier] || 16);
    n.value = n.value || 0;
  });
  edges.forEach((e) => {
    e.lineStyle = { width: Math.max(1, e.value * 1.2), color: roleColor(e.role) };
  });
  const chart = echarts.init(chartEls.socialChart);
  chart.setOption({
    backgroundColor: "transparent",
    tooltip: {
      formatter: (p) => {
        if (p.dataType === "edge") {
          return `<strong>${p.data.source} → ${p.data.target}</strong><br/>` +
            `role: ${p.data.role}<br/>` +
            `closeness: ${p.data.closeness.toFixed(2)}, trust: ${p.data.trust.toFixed(2)}<br/>` +
            `friction: ${p.data.friction.toFixed(2)} (Dunbar: ${p.data.tier})`;
        }
        return `<strong>${p.data.name}</strong><br/>` +
          `kind: ${p.data.kind}<br/>` +
          (p.data.role ? `role: ${p.data.role}<br/>` : "") +
          (p.data.tier ? `tier: ${p.data.tier}<br/>` : "");
      },
    },
    legend: [{ data: categories.map((c) => c.name), bottom: 0, textStyle: { color: "#17211d" } }],
    animationDurationUpdate: 800,
    animationEasingUpdate: "quinticInOut",
    series: [{
      type: "graph",
      layout: "force",
      data: nodes,
      links: edges,
      categories,
      roam: true,
      draggable: true,
      label: {
        show: true,
        position: "right",
        color: "#17211d",
        fontWeight: 700,
        fontSize: 11,
      },
      force: {
        repulsion: 220,
        edgeLength: 90,
        gravity: 0.05,
      },
      emphasis: { focus: "adjacency", lineStyle: { width: 3 } },
    }],
  }, true);
  chartState.socialChart = chart;
}

function roleColor(role) {
  const palette = {
    mother: "#b73e3e", father: "#1f8a9b", sibling: "#9467bd",
    spouse: "#d6a81e", child: "#82a661",
    best_friend: "#13795b", close_friend: "#385866", friend: "#6e5f97",
    coworker: "#1f77b4", boss: "#ff7f0e", subordinate: "#2ca02c",
    mentor: "#e377c2", client: "#17becf",
    ex: "#999999",
    old_friend: "#a98ec9", classmate: "#8c564b", neighbor: "#bcbd22",
  };
  return palette[role] || "#cbd7cd";
}

// ── Intervention chart (one heatmap per agent) ──────────────
async function loadInterventionChartData() {
  chartState.interventionData = await api("/api/metrics/intervention");
  const agents = (chartState.interventionData.agents && chartState.interventionData.agents.length)
    ? chartState.interventionData.agents
    : [...new Set((chartState.interventionData.data || []).map((r) => Number(r.agent_id)).filter(Boolean))].sort((a, b) => a - b);
  chartState.interventionData.agents = agents;
  if (!chartState.selectedInterventionAgents.length && agents.length) {
    chartState.selectedInterventionAgents = agents;
  }
  buildAgentMultiOptions(chartEls.interventionAgentSelect, agents, chartState.selectedInterventionAgents);
  Array.from(chartEls.interventionAgentSelect.options).forEach((opt) => {
    opt.selected = chartState.selectedInterventionAgents.includes(Number(opt.value));
  });
  await renderInterventionCharts();
}

async function renderInterventionCharts() {
  if (!chartState.interventionData) return;
  const { data } = chartState.interventionData;
  const container = chartEls.interventionChartContainer;
  if (!container) return;
  Object.values(chartState.interventionCharts).forEach((c) => { try { c.dispose(); } catch (_e) {} });
  chartState.interventionCharts = {};
  clearChartContainer(container);
  if (!chartState.selectedInterventionAgents.length) {
    container.innerHTML = '<div class="chart-empty">请选择至少一个 Agent</div>';
    return;
  }
  for (const agentId of chartState.selectedInterventionAgents) {
    const agentMeta = (state.agents.find((a) => Number(a.id) === Number(agentId))) || {};
    const agentName = agentMeta.name || `Agent ${agentId}`;
    const holder = createAgentSubPanel(container, agentId, agentName, "平台干预指标 (热力图)");

    const metricLabels = {
      stance_score: "立场倾向",
      toxicity_score: "攻击性风险",
      misinformation_risk: "误信息风险",
      cross_viewpoint_exposure: "跨观点暴露",
      intervention_reward: "干预收益",
    };
    const metrics = ["stance_score", "toxicity_score", "misinformation_risk", "cross_viewpoint_exposure", "intervention_reward"];
    const agentRows = data.filter((r) => Number(r.agent_id) === Number(agentId));
    if (!agentRows.length) {
      holder.innerHTML = '<div class="chart-empty">无干预数据</div>';
      continue;
    }
    // x-axis: composite label "day time"
    const xLabels = [];
    const seen = new Set();
    agentRows.forEach((r) => {
      const lbl = `D${r.day} ${r.time}`;
      if (!seen.has(lbl)) { seen.add(lbl); xLabels.push(lbl); }
    });
    const series = metrics.map((m, mi) => ({
      name: m,
      type: "heatmap",
      data: agentRows.map((r) => {
        const lbl = `D${r.day} ${r.time}`;
        const xi = xLabels.indexOf(lbl);
        return [xi, mi, Number(r[m])];
      }),
      label: { show: false },
      emphasis: { itemStyle: { borderColor: "#17211d", borderWidth: 1 } },
    }));
    const chart = echarts.init(holder);
    chart.setOption({
      backgroundColor: "transparent",
      tooltip: {
        position: "top",
        formatter: (p) => `${xLabels[p.value[0]]} · ${metrics[p.value[1]]}: ${Number(p.value[2]).toFixed(3)}`,
      },
      grid: { top: 30, left: 128, right: 88, bottom: 92 },
      xAxis: {
        type: "category",
        name: "仿真时间",
        nameLocation: "middle",
        nameGap: 58,
        nameTextStyle: { color: "#385866", fontSize: 11, fontWeight: 800 },
        data: xLabels,
        splitArea: { show: true },
        axisLabel: { color: "#17211d", fontSize: 9, rotate: 38, margin: 12 },
        axisLine: { lineStyle: { color: "#5c6860" } },
      },
      yAxis: {
        type: "category",
        data: metrics,
        splitArea: { show: true },
        axisLabel: { color: "#17211d", fontSize: 10, formatter: (value) => metricLabels[value] || value },
        axisLine: { lineStyle: { color: "#5c6860" } },
      },
      visualMap: {
        min: -0.2,
        max: 0.6,
        calculable: true,
        orient: "vertical",
        right: 10,
        top: 48,
        itemHeight: 150,
        itemWidth: 12,
        text: ["高", "低"],
        textStyle: { color: "#17211d", fontSize: 10 },
        inRange: { color: ["#385866", "#82a661", "#d6a81e", "#c2410c", "#7c3aed"] },
      },
      series,
    }, true);
    chartState.interventionCharts[agentId] = chart;
  }
}

// ── Work market chart (single panel, table + cards) ─────────
async function loadWorkChartData() {
  chartState.workMarketData = await api("/api/metrics/work-market");
  renderWorkChart();
}

function renderWorkChart() {
  if (!chartState.workMarketData || !chartEls.workChart) return;
  const data = chartState.workMarketData;
  const demoBadge = document.getElementById("workDemoBadge");
  if (demoBadge) demoBadge.hidden = !data.is_demo;
  if (chartState.workChart) {
    try { chartState.workChart.dispose(); } catch (_e) {}
    chartState.workChart = null;
  }
  const jobs = data.jobs || [];
  const container = chartEls.workChart;
  container.innerHTML = "";
  if (!jobs.length) {
    container.innerHTML = '<div class="chart-empty">暂无工作市场数据</div>';
    return;
  }
  // Build a header summary + a list of cards
  const summary = document.createElement("div");
  summary.className = "work-summary";
  const open = jobs.filter((j) => j.status === "open").length;
  const taken = jobs.filter((j) => j.status === "taken" || j.taken_by_agent_id).length;
  const totalReward = jobs.reduce((acc, j) => acc + Number(j.reward_econ || 0), 0);
  summary.innerHTML = `<span class="work-stat"><b>${jobs.length}</b> 个岗位</span><span class="work-stat open"><b>${open}</b> 待接</span><span class="work-stat taken"><b>${taken}</b> 已接</span><span class="work-stat"><b>${totalReward.toFixed(2)}</b> 累积 reward_econ</span>`;
  container.appendChild(summary);
  const grid = document.createElement("div");
  grid.className = "work-grid";
  jobs.forEach((job) => {
    const card = document.createElement("div");
    card.className = `work-card ${job.status === "open" ? "open" : "taken"}`;
    const skills = (job.required_skills || []).map((s) => `<span class="skill-tag">${s}</span>`).join("");
    const status = job.status || "open";
    const takenBy = job.taken_by_agent_id != null ? `#${String(job.taken_by_agent_id).padStart(2, "0")}` : "—";
    card.innerHTML = `
      <div class="work-card-head">
        <span class="work-card-id">${job.job_id || ""}</span>
        <span class="work-card-status">${status}</span>
      </div>
      <div class="work-card-title">${job.title || "(未命名)"}</div>
      <div class="work-card-desc">${job.description || ""}</div>
      <div class="work-card-meta">
        <span><b>Reward:</b> ${job.reward_text || `×${job.reward_econ}`}</span>
        <span><b>Deadline:</b> Day ${job.deadline_sim_day ?? "?"}</span>
        <span><b>Taken by:</b> ${takenBy}</span>
      </div>
      <div class="work-card-skills">${skills}</div>
    `;
    grid.appendChild(card);
  });
  container.appendChild(grid);
}

// ── Resize charts on window resize ──────────────────────────
window.addEventListener("resize", () => {
  Object.values(chartState.stateCharts).forEach((c) => { try { c.resize(); } catch (_e) {} });
  Object.values(chartState.economyCharts).forEach((c) => { try { c.resize(); } catch (_e) {} });
  Object.values(chartState.locationCharts).forEach((c) => { try { c.resize(); } catch (_e) {} });
  Object.values(chartState.interventionCharts).forEach((c) => { try { c.resize(); } catch (_e) {} });
  if (chartState.socialChart) { try { chartState.socialChart.resize(); } catch (_e) {} }
  if (chartState.activitySummaryChart) { try { chartState.activitySummaryChart.resize(); } catch (_e) {} }
});

// ── Charts Events ────────────────────────────────────────────
function safeOn(el, event, handler) {
  if (el && typeof el.addEventListener === "function") {
    el.addEventListener(event, handler);
  }
}

safeOn(chartEls.reloadStateChartBtn, "click", () => loadStateChartData());
safeOn(chartEls.reloadEconomyChartBtn, "click", () => loadEconomyChartData());
safeOn(chartEls.reloadLocationChartBtn, "click", () => loadLocationChartData());
safeOn(chartEls.reloadSocialChartBtn, "click", () => loadSocialChartData());
safeOn(chartEls.reloadInterventionChartBtn, "click", () => loadInterventionChartData());
safeOn(chartEls.reloadActivityChartBtn, "click", () => loadActivitySummaryData());
safeOn(chartEls.reloadWorkChartBtn, "click", () => loadWorkChartData());

safeOn(chartEls.stateAgentSelect, "change", () => {
  chartState.selectedStateAgents = getSelectedAgents(chartEls.stateAgentSelect);
  syncAgentCheckboxList(chartEls.stateAgentSelect);
  renderStateCharts();
});

safeOn(chartEls.economyAgentSelect, "change", () => {
  chartState.selectedEconomyAgents = getSelectedAgents(chartEls.economyAgentSelect);
  syncAgentCheckboxList(chartEls.economyAgentSelect);
  renderEconomyCharts();
});

safeOn(chartEls.locationAgentSelect, "change", () => {
  chartState.selectedLocationAgents = getSelectedAgents(chartEls.locationAgentSelect);
  syncAgentCheckboxList(chartEls.locationAgentSelect);
  loadLocationChartData();
});

safeOn(chartEls.interventionAgentSelect, "change", () => {
  chartState.selectedInterventionAgents = getSelectedAgents(chartEls.interventionAgentSelect);
  syncAgentCheckboxList(chartEls.interventionAgentSelect);
  renderInterventionCharts();
});

safeOn(chartEls.timelineAgentSelect, "change", () => {
  chartState.selectedTimelineAgents = getSelectedAgents(chartEls.timelineAgentSelect);
  syncAgentCheckboxList(chartEls.timelineAgentSelect);
  loadTimelineChartData();
});
safeOn(chartEls.reloadTimelineBtn, "click", () => loadTimelineChartData());

// ── Daily Timeline (schedule × actual) per agent ─────────────
async function loadTimelineChartData() {
  const container = chartEls.timelineContainer;
  if (!container) return;
  chartState.timelineData = {};
  clearChartContainer(container);
  if (!chartState.selectedTimelineAgents.length) {
    container.innerHTML = '<div class="chart-empty">请选择至少一个 Agent</div>';
    return;
  }
  // Build the dropdown
  buildAgentMultiOptions(chartEls.timelineAgentSelect, (chartState.stateData && chartState.stateData.agents) || state.agents.map((a) => a.id), chartState.selectedTimelineAgents);
  Array.from(chartEls.timelineAgentSelect.options).forEach((opt) => {
    opt.selected = chartState.selectedTimelineAgents.includes(Number(opt.value));
  });
  for (const agentId of chartState.selectedTimelineAgents) {
    let payload;
    try {
      payload = await api(`/api/metrics/daily-timeline/${agentId}`);
    } catch (_e) {
      payload = { schedule: [], days: [], is_demo: true };
    }
    chartState.timelineData[agentId] = payload;
    const agentMeta = (state.agents.find((a) => Number(a.id) === Number(agentId))) || {};
    const agentName = agentMeta.name || `Agent ${agentId}`;
    const card = document.createElement("div");
    card.className = "agent-sub-panel timeline-card";
    card.dataset.agentId = String(agentId);
    const head = document.createElement("div");
    head.className = "agent-sub-head";
    head.innerHTML = `<span class="agent-sub-id">#${String(agentId).padStart(2, "0")}</span><span class="agent-sub-name">${agentName}</span>`;
    card.appendChild(head);
    const title = document.createElement("div");
    title.className = "agent-sub-title";
    title.textContent = "schedule (预定) vs actual (实际)";
    card.appendChild(title);

    if ((!payload.days || !payload.days.length) && (!payload.schedule || !payload.schedule.length)) {
      card.innerHTML += '<div class="chart-empty">无数据</div>';
      container.appendChild(card);
      continue;
    }

    // Schedule pill row
    const schedWrap = document.createElement("div");
    schedWrap.className = "schedule-row";
    schedWrap.innerHTML = `<span class="schedule-label">每日预定：</span>`;
    const pills = (payload.schedule || []).map((s) => {
      return `<span class="sched-pill" title="计划活动">${s.time} ${s.activity}</span>`;
    }).join("<span class=\"sched-arrow\">→</span>");
    schedWrap.innerHTML += pills;
    card.appendChild(schedWrap);

    // Per-day step timeline
    const dayList = document.createElement("div");
    dayList.className = "loc-day-list";
    (payload.days || []).forEach((day, dayIndex, daysList) => {
      const details = document.createElement("details");
      details.className = "loc-day";
      details.open = dayIndex === daysList.length - 1;
      const sum = document.createElement("summary");
      sum.innerHTML = `<b>Day ${day.day}</b> · ${day.date || ""} ${day.weekday || ""} · <span class="muted">${day.items.length} 个 step</span>`;
      details.appendChild(sum);
      const list = document.createElement("div");
      list.className = "timeline-step-list";
      let previousActivity = "";
      day.items.forEach((it) => {
        const stepEl = document.createElement("div");
        stepEl.className = "timeline-step";
        const inTransitTag = it.in_transit ? ' <span class="in-transit">在途</span>' : "";
        const activity = String(it.activity || "").trim();
        const activityText = activity && activity !== previousActivity ? activity : "";
        if (activity) previousActivity = activity;
        stepEl.innerHTML = `
          <div class="timeline-step-time">${it.time}${inTransitTag}</div>
          <div class="timeline-step-arrow">→</div>
          <div class="timeline-step-body">
            <div class="timeline-step-place">${it.location}</div>
            ${activityText ? `<div class="timeline-step-act">${activityText}</div>` : ""}
            <div class="timeline-step-meta">${it.transport_mode || "—"} · ${(it.distance_km || 0).toFixed(2)} km</div>
          </div>
          ${it.next_time ? `<div class="timeline-step-arrow">→</div><div class="timeline-step-next">${it.next_time} @ ${it.next_location}</div>` : ""}
        `;
        list.appendChild(stepEl);
      });
      details.appendChild(list);
      dayList.appendChild(details);
    });
    card.appendChild(dayList);
    container.appendChild(card);
  }
}

// ── Init Charts ───────────────────────────────────────────────
async function initCharts() {
  await loadStateChartData().catch(() => {});
  await loadEconomyChartData().catch(() => {});
  if (chartState.stateData && chartState.stateData.agents && chartState.stateData.agents.length) {
    chartState.selectedLocationAgents = [chartState.stateData.agents[0]];
    chartState.selectedTimelineAgents = chartState.stateData.agents;
  }
  await loadLocationChartData().catch(() => {});
  await loadActivitySummaryData().catch(() => {});
  await loadSocialChartData().catch(() => {});
  await loadInterventionChartData().catch(() => {});
  await loadWorkChartData().catch(() => {});
  await loadTimelineChartData().catch(() => {});
}
const tileColors = {
  ".": "#e5ece4",
  "#": "#7d8c82",
  "=": "#f3cf63",
  "~": "#7fb3be",
  "*": "#82a661",
  "r": "#d8d7c3",
  "c": "#d6a81e",
  "e": "#8db0c2",
  "m": "#d98b8b",
  "i": "#a3aaa1",
  "g": "#bcc87c",
  "l": "#72a773",
  "t": "#9b8fc0",
  "+": "#b28bd6",
  "d": "#cfc9a6",
};
const agentColors = ["#13795b", "#b73e3e", "#385866", "#d6a81e", "#6e5f97", "#1f8a9b", "#8a5b30"];

function traceAgentMap() {
  const agents = (state.trace && Array.isArray(state.trace.agents)) ? state.trace.agents : [];
  return new Map(agents.map((agent) => [Number(agent.id), agent]));
}

function resolveAssetPath(assetPath) {
  const text = String(assetPath || "").trim();
  if (!text) return "";
  if (/^(https?:)?\/\//.test(text) || text.startsWith("data:")) return text;
  try {
    return new URL(text, window.location.href).href;
  } catch (_error) {
    return text;
  }
}

function getAgentAvatarPath(agentId) {
  const meta = traceAgentMap().get(Number(agentId));
  const fallbackPath = `/output/visualization/avatars/agent_${Number(agentId || 0)}.svg`;
  return resolveAssetPath((meta && meta.avatar_path) || fallbackPath);
}

function loadAvatar(path) {
  const resolved = resolveAssetPath(path);
  if (!resolved) return null;
  if (state.avatarCache.has(resolved)) {
    const cached = state.avatarCache.get(resolved);
    return cached.loaded ? cached.img : null;
  }
  const img = new Image();
  img.decoding = "async";
  state.avatarCache.set(resolved, { img, loaded: false });
  img.onload = () => {
    const item = state.avatarCache.get(resolved);
    if (item) item.loaded = true;
    renderTrace();
  };
  img.onerror = () => {
    state.avatarCache.delete(resolved);
  };
  img.src = resolved;
  return null;
}

function renderSelectedAgentAvatar() {
  if (!state.selectedAgentId) {
    els.selectedAgentAvatar.removeAttribute("src");
    els.selectedAgentAvatar.alt = "";
    return;
  }
  const selected = state.agents.find((agent) => Number(agent.id) === Number(state.selectedAgentId));
  const avatarPath = getAgentAvatarPath(state.selectedAgentId);
  els.selectedAgentAvatar.src = avatarPath;
  els.selectedAgentAvatar.alt = `${selected ? selected.name : `Agent ${state.selectedAgentId}`} avatar`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok || payload.error) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function message(text, tone = "") {
  els.messageLine.textContent = text || "";
  els.messageLine.className = tone;
}

function configPayloadFromForm() {
  const defaultProvider = els.defaultProviderSelect.value;
  const scheduleProvider = els.scheduleProviderSelect.value || defaultProvider;
  return {
    agent_ids: els.agentIdsInput.value,
    sim_days: Number(els.simDaysInput.value || 1),
    seconds_per_day: Number(els.secondsPerDayInput.value || 10),
    simulate_realtime: els.realtimeInput.checked,
    time_step_minutes: els.timeStepInput.value.trim(),
    llm: {
      routing: {
        default: defaultProvider,
        tasks: { schedule: scheduleProvider },
      },
    },
  };
}

async function loadConfig() {
  state.config = await api("/api/config");
  const cfg = state.config;
  els.agentIdsInput.value = (cfg.agent_ids || []).join(",");
  els.simDaysInput.value = cfg.sim_days || 1;
  els.secondsPerDayInput.value = cfg.seconds_per_day || 10;
  els.timeStepInput.value = cfg.time_step_minutes == null ? "" : cfg.time_step_minutes;
  els.realtimeInput.checked = Boolean(cfg.simulate_realtime);
  const providers = (cfg.llm && cfg.llm.providers) || [];
  const routing = (cfg.llm && cfg.llm.routing) || {};
  fillProviderSelect(els.defaultProviderSelect, providers, routing.default);
  fillProviderSelect(els.scheduleProviderSelect, providers, (routing.tasks || {}).schedule || routing.default);
}

function fillProviderSelect(select, providers, selected) {
  select.innerHTML = "";
  providers.forEach((provider) => {
    const option = document.createElement("option");
    option.value = provider;
    option.textContent = provider;
    option.selected = provider === selected;
    select.appendChild(option);
  });
}

async function saveConfig() {
  await api("/api/config", { method: "POST", body: JSON.stringify(configPayloadFromForm()) });
  await loadConfig();
  message("配置已写入 dashboard_config.json");
}

async function loadAgents() {
  const payload = await api("/api/agents");
  state.agents = payload.agents || [];
  if (!state.selectedAgentId && state.agents.length) {
    const configured = state.agents.find((agent) => agent.configured);
    state.selectedAgentId = (configured || state.agents[0]).id;
  }
  els.agentSelect.innerHTML = "";
  state.agents.forEach((agent) => {
    const option = document.createElement("option");
    option.value = String(agent.id);
    option.textContent = `${String(agent.id).padStart(2, "0")} · ${agent.name}${agent.configured ? " · active" : ""}`;
    // Multi-select: pre-select currently selected agent
    option.selected = Number(agent.id) === Number(state.selectedAgentId);
    els.agentSelect.appendChild(option);
  });
  syncAgentCheckboxList(els.agentSelect);
  renderSelectedAgentAvatar();
}

function selectedLifeEventTemplate() {
  const key = els.lifeEventTemplateSelect.value;
  return state.lifeEventTemplates.find((item) => item.key === key) || {};
}

function fillLifeEventTemplates() {
  els.lifeEventTemplateSelect.innerHTML = "";
  state.lifeEventTemplates.forEach((template) => {
    const option = document.createElement("option");
    option.value = template.key;
    option.textContent = template.title || template.key;
    els.lifeEventTemplateSelect.appendChild(option);
  });
  applyLifeEventTemplate();
}

function applyLifeEventTemplate() {
  const template = selectedLifeEventTemplate();
  if (!template.key) return;
  if (!els.lifeEventTitleInput.value.trim()) {
    els.lifeEventTitleInput.value = template.title || "";
  }
  if (!els.lifeEventDescriptionInput.value.trim()) {
    els.lifeEventDescriptionInput.value = template.description || "";
  }
  els.lifeEventSeverityInput.value = template.severity == null ? 0.7 : template.severity;
}

function renderLifeEvents() {
  const events = state.lifeEvents || [];
  if (!events.length) {
    els.lifeEventListBox.textContent = "暂无人生事件。";
    return;
  }
  els.lifeEventListBox.textContent = events.slice().reverse().map((event) => {
    const target = (event.agent_ids || []).length ? `#${event.agent_ids.join(",#")}` : "所有 Agent";
    const when = event.schedule_mode === "immediate"
      ? "下一时间步"
      : `Day ${event.day || "?"} ${event.time || "当前时间"}`;
    const status = event.status === "consumed"
      ? `已触发 Day ${event.triggered_day || "?"} ${event.triggered_time || ""}`.trim()
      : "待触发";
    return [
      `[${status}] ${event.title || "人生事件"}`,
      `目标：${target} · 触发：${when} · 强度：${Number(event.severity || 0).toFixed(2)}`,
      event.description || "",
    ].join("\n");
  }).join("\n\n");
}

async function loadLifeEvents() {
  const payload = await api("/api/life-events");
  state.lifeEventTemplates = payload.templates || [];
  state.lifeEvents = payload.events || [];
  if (!els.lifeEventTemplateSelect.options.length) fillLifeEventTemplates();
  renderLifeEvents();
}

function lifeEventPayloadFromForm() {
  return {
    template_key: els.lifeEventTemplateSelect.value,
    agent_ids: els.lifeEventAgentInput.value.trim(),
    schedule_mode: els.lifeEventModeSelect.value,
    day: els.lifeEventDayInput.value.trim(),
    time: els.lifeEventTimeInput.value.trim(),
    severity: Number(els.lifeEventSeverityInput.value || 0.7),
    title: els.lifeEventTitleInput.value.trim(),
    description: els.lifeEventDescriptionInput.value.trim(),
  };
}

async function addLifeEvent() {
  const payload = lifeEventPayloadFromForm();
  const result = await api("/api/life-events", { method: "POST", body: JSON.stringify(payload) });
  state.lifeEvents = result.events || [];
  renderLifeEvents();
  message("人生事件已加入队列");
}

async function loadProfile() {
  if (!state.selectedAgentId) return;
  const profile = await api(`/api/agents/${state.selectedAgentId}/profile`);
  els.profileEditor.value = profile.text || "";
}

async function saveProfile() {
  if (!state.selectedAgentId) return;
  await api(`/api/agents/${state.selectedAgentId}/profile`, {
    method: "POST",
    body: JSON.stringify({ text: els.profileEditor.value }),
  });
  await loadAgents();
  message("Profile 已保存");
}

async function loadMemory() {
  if (!state.selectedAgentId) return;
  const payload = await api(`/api/agents/${state.selectedAgentId}/memory`);
  els.memoryBox.textContent = JSON.stringify(payload.memory || [], null, 2);
  els.stateMemoryBox.textContent = JSON.stringify({
    schedule: payload.schedule || {},
    habits: payload.habits || {},
    intentions: payload.intentions || {},
  }, null, 2);
  els.episodesBox.textContent = payload.episodes_tail || "暂无 episode。";
  els.agentLogBox.textContent = payload.log_tail || "暂无 agent 日志。";
}

async function runSimulation(reset = false) {
  message("正在启动仿真...");
  const payload = { reset, config: configPayloadFromForm() };
  await api("/api/run/start", { method: "POST", body: JSON.stringify(payload) });
  await refreshStatus();
}

async function stopSimulation() {
  await api("/api/run/stop", { method: "POST", body: "{}" });
  await refreshStatus();
}

async function refreshStatus() {
  const status = await api("/api/run/status");
  els.runStatusBadge.textContent = status.running ? "运行中" : status.returncode == null ? "未运行" : `已结束 ${status.returncode}`;
  els.runStatusBadge.className = `status-badge ${status.running ? "running" : status.returncode === 0 ? "done" : status.returncode ? "error" : ""}`;
  if (status.running) loadTrace(false).catch(() => {});
}

async function loadTrace(showErrors = true) {
  try {
    const response = await fetch(`/output/visualization/simulation_trace.json?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.trace = await response.json();
    const frames = Array.isArray(state.trace.frames) ? state.trace.frames : [];
    // Clamp frame index to new bounds without interrupting playback.
    state.frameIndex = frames.length ? Math.min(state.frameIndex, frames.length - 1) : 0;
    renderTrace();
  } catch (error) {
    if (showErrors) {
      els.traceStatus.textContent = `轨迹读取失败: ${error.message}`;
      drawEmptyMap();
    }
  }
}

function currentFrame() {
  const frames = state.trace && Array.isArray(state.trace.frames) ? state.trace.frames : [];
  return frames[state.frameIndex] || null;
}

function frameSummaryText(frame) {
  const agents = Array.isArray(frame.agents) ? frame.agents : [];
  const lines = [
    `Day ${frame.day ?? "?"}  ${frame.date || ""} ${frame.weekday || ""} ${frame.time || ""}`.trim(),
    `Agents: ${agents.length}`,
    "",
  ];
  agents.forEach((agent) => {
    const travel = agent.travel || {};
    const location = agent.resolved_location || agent.location || "?";
    const transport = travel.mode ? `${travel.mode}, ${Number(travel.distance_km || 0).toFixed(2)} km` : "无移动";
    lines.push(`#${String(agent.agent_id).padStart(2, "0")} ${agent.name || ""}`);
    lines.push(`  位置: ${location}`);
    lines.push(`  活动: ${agent.activity || "—"}`);
    lines.push(`  计划: ${agent.scheduled_activity || "—"}`);
    lines.push(`  交通: ${transport}`);
  });
  return lines.join("\n");
}

function renderTrace() {
  const frame = currentFrame();
  const frames = state.trace && Array.isArray(state.trace.frames) ? state.trace.frames : [];
  if (!frame) {
    drawEmptyMap();
    return;
  }
  renderSelectedAgentAvatar();
  els.frameTitle.textContent = `Day ${frame.day} · ${frame.time}`;
  els.traceStatus.textContent = `${frames.length} 帧 · ${state.trace.meta && state.trace.meta.finished ? "已完成" : "写入中"}`;
  els.timelineSlider.max = String(Math.max(0, frames.length - 1));
  els.timelineSlider.value = String(state.frameIndex);
  els.timelineLabel.textContent = `${frame.date || ""} ${frame.weekday || ""} ${frame.time || ""}`.trim();
  els.latestFrameBox.textContent = frameSummaryText(frame);
  drawMap(frame);
}

function drawEmptyMap() {
  ctx.clearRect(0, 0, els.mapCanvas.width, els.mapCanvas.height);
  ctx.fillStyle = "#e5ece4";
  ctx.fillRect(0, 0, els.mapCanvas.width, els.mapCanvas.height);
  ctx.fillStyle = "#385866";
  ctx.font = "24px Georgia";
  ctx.fillText("等待 simulation_trace.json", 40, 56);
  els.frameTitle.textContent = "未加载轨迹";
  els.timelineLabel.textContent = "暂无帧";
  els.latestFrameBox.textContent = "暂无当前帧。";
}

function drawMap(frame) {
  const map = (state.trace || {}).map || {};
  const tileMap = map.tile_map || {};
  const terrain = Array.isArray(tileMap.terrain) ? tileMap.terrain : [];
  const width = Number(tileMap.width || 160);
  const height = Number(tileMap.height || 112);
  const scale = Math.max(4, Math.floor(Math.min(els.mapCanvas.width / width, els.mapCanvas.height / height)));
  const offsetX = Math.floor((els.mapCanvas.width - width * scale) / 2);
  const offsetY = Math.floor((els.mapCanvas.height - height * scale) / 2);
  const nodes = new Map((map.nodes || []).map((node) => [node.id, node]));

  ctx.clearRect(0, 0, els.mapCanvas.width, els.mapCanvas.height);
  ctx.fillStyle = "#dfe8df";
  ctx.fillRect(0, 0, els.mapCanvas.width, els.mapCanvas.height);
  terrain.forEach((line, row) => {
    String(line).split("").forEach((cell, col) => {
      ctx.fillStyle = tileColors[cell] || tileColors["."];
      ctx.fillRect(offsetX + col * scale, offsetY + row * scale, scale, scale);
    });
  });

  (map.nodes || []).forEach((node) => {
    const x = offsetX + node.tile_x * scale + scale / 2;
    const y = offsetY + node.tile_y * scale + scale / 2;
    ctx.fillStyle = node.kind === "hub" ? "#17211d" : "#385866";
    ctx.fillRect(x - 3, y - 3, 6, 6);
  });

  // Build an overlay DOM (HTML) for clickable / hoverable agent markers
  // so we can show full names + location names on hover.
  let overlay = document.getElementById("mapAgentOverlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "mapAgentOverlay";
    overlay.style.cssText = "position:absolute;inset:0;pointer-events:none;";
    els.mapCanvas.parentElement.style.position = els.mapCanvas.parentElement.style.position || "relative";
    els.mapCanvas.parentElement.appendChild(overlay);
  }
  overlay.innerHTML = "";

  (frame.agents || []).forEach((agent) => {
    const node = nodes.get(agent.target_location) || nodes.get(agent.resolved_location);
    if (!node) return;
    const x = offsetX + node.tile_x * scale + scale / 2;
    const y = offsetY + node.tile_y * scale + scale / 2;
    const color = agentColors[Math.abs(Number(agent.agent_id || 0)) % agentColors.length];
    const radius = agent.agent_id === state.selectedAgentId ? 13 : 10;
    const avatarImage = loadAvatar(getAgentAvatarPath(agent.agent_id));
    ctx.save();
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.closePath();
    ctx.clip();
    if (avatarImage) {
      ctx.drawImage(avatarImage, x - radius, y - radius, radius * 2, radius * 2);
    } else {
      ctx.fillStyle = color;
      ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
    }
    ctx.restore();
    ctx.strokeStyle = "#fffef9";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.stroke();

    // Draw label on canvas (name @ location) — fallback
    const labelText = `${agent.name || agent.agent_id} @ ${agent.resolved_location || agent.location || "?"}`;
    ctx.font = "11px Aptos";
    const textWidth = ctx.measureText(labelText).width;
    // Label background pill
    ctx.fillStyle = "rgba(23, 33, 29, 0.78)";
    const lx = x + radius + 4;
    const ly = y - radius - 4;
    ctx.fillRect(lx, ly, textWidth + 8, 16);
    ctx.fillStyle = "#fffef9";
    ctx.fillText(labelText, lx + 4, ly + 12);

    // Also add an HTML hit zone for hover tooltip
    const hit = document.createElement("div");
    hit.style.cssText = `position:absolute;left:${x - radius}px;top:${y - radius}px;width:${radius * 2}px;height:${radius * 2}px;border-radius:50%;pointer-events:auto;cursor:pointer;`;
    hit.title = `${agent.name || "Agent " + agent.agent_id} @ ${agent.resolved_location || agent.location || "?"}\n` +
      `activity: ${agent.activity || "—"}\n` +
      `scheduled: ${agent.scheduled_activity || "—"}\n` +
      `action: ${(agent.action || "").slice(0, 80)}`;
    overlay.appendChild(hit);
  });
}

async function interview() {
  if (!state.selectedAgentId) return;
  els.interviewOutput.textContent = "采访运行中...";
  const questions = els.interviewQuestions.value.split("\n").map((line) => line.trim()).filter(Boolean);
  const payload = {
    agent_id: state.selectedAgentId,
    context: els.interviewContext.value.trim(),
    questions,
  };
  const result = await api("/api/interview", { method: "POST", body: JSON.stringify(payload) });
  els.interviewOutput.textContent = [result.stdout, result.stderr].filter(Boolean).join("\n") || `returncode=${result.returncode}`;
}

function bindEvents() {
  [
    els.agentSelect,
    chartEls.stateAgentSelect,
    chartEls.economyAgentSelect,
    chartEls.locationAgentSelect,
    chartEls.interventionAgentSelect,
    chartEls.timelineAgentSelect,
  ].forEach((selectEl) => {
    enableClickToggleMultiSelect(selectEl);
    enhanceAgentMultiSelect(selectEl);
  });
  safeOn(els.saveConfigBtn, "click", () => saveConfig().catch((error) => message(error.message, "error")));
  safeOn(els.runBtn, "click", () => runSimulation(false).catch((error) => message(error.message, "error")));
  safeOn(els.resetRunBtn, "click", () => runSimulation(true).catch((error) => message(error.message, "error")));
  safeOn(els.stopBtn, "click", () => stopSimulation().catch((error) => message(error.message, "error")));
  safeOn(els.reloadTraceBtn, "click", () => loadTrace(true));
  safeOn(els.reloadStatusBtn, "click", () => refreshStatus().catch((error) => message(error.message, "error")));
  safeOn(els.agentSelect, "change", async () => {
    const selected = Array.from(els.agentSelect.selectedOptions || []).map((o) => Number(o.value));
    if (selected.length) {
      state.selectedAgentId = selected[0];
    }
    syncAgentCheckboxList(els.agentSelect);
    renderSelectedAgentAvatar();
    await loadProfile();
    renderTrace();
  });
  safeOn(els.saveProfileBtn, "click", () => saveProfile().catch((error) => message(error.message, "error")));
  safeOn(els.refreshAgentBtn, "click", () => loadProfile().catch((error) => message(error.message, "error")));
  safeOn(els.interviewBtn, "click", () => interview().catch((error) => {
    els.interviewOutput.textContent = error.message;
  }));
  safeOn(els.lifeEventTemplateSelect, "change", () => {
    els.lifeEventTitleInput.value = "";
    els.lifeEventDescriptionInput.value = "";
    applyLifeEventTemplate();
  });
  safeOn(els.useSelectedAgentBtn, "click", () => {
    if (state.selectedAgentId) els.lifeEventAgentInput.value = String(state.selectedAgentId);
  });
  safeOn(els.addLifeEventBtn, "click", () => addLifeEvent().catch((error) => message(error.message, "error")));
  safeOn(els.reloadLifeEventsBtn, "click", () => loadLifeEvents().catch((error) => message(error.message, "error")));
  safeOn(els.timelineSlider, "input", () => {
    state.frameIndex = Number(els.timelineSlider.value || 0);
    renderTrace();
  });
  safeOn(els.tracePlayBtn, "click", () => toggleTracePlayback());
}

function toggleTracePlayback() {
  if (!state.trace || !Array.isArray(state.trace.frames) || state.trace.frames.length === 0) {
    message("暂无轨迹数据可播放", "error");
    return;
  }
  if (state.tracePlaying) {
    stopTracePlayback();
  } else {
    startTracePlayback();
  }
}

function startTracePlayback() {
  state.tracePlaying = true;
  if (els.tracePlayBtn) {
    els.tracePlayBtn.textContent = "⏸";
    els.tracePlayBtn.title = "暂停";
  }
  if (state.traceTimer) clearInterval(state.traceTimer);
  state.traceTimer = window.setInterval(() => {
    const frames = (state.trace && state.trace.frames) || [];
    if (!frames.length) {
      stopTracePlayback();
      return;
    }
    state.frameIndex = (state.frameIndex + 1) % frames.length;
    renderTrace();
  }, state.traceSpeedMs);
}

function stopTracePlayback() {
  state.tracePlaying = false;
  if (state.traceTimer) {
    clearInterval(state.traceTimer);
    state.traceTimer = null;
  }
  if (els.tracePlayBtn) {
    els.tracePlayBtn.textContent = "▶";
    els.tracePlayBtn.title = "点击自动播放";
  }
}

async function init() {
  try { bindEvents(); } catch (e) { console.error("bindEvents failed:", e); }
  // Run each step independently so one failure doesn't break the rest
  await Promise.allSettled([
    loadConfig(),
    loadAgents(),
    loadLifeEvents(),
    loadProfile(),
    refreshStatus(),
    loadTrace(false),
  ]);
  try { await initCharts(); } catch (e) { console.error("initCharts failed:", e); }
  state.pollTimer = window.setInterval(() => {
    refreshStatus().catch(() => {});
    loadTrace(false).catch(() => {});
    loadLifeEvents().catch(() => {});
  }, 8000);
}

init().catch((error) => {
  console.error("init failed:", error);
  try { message(error.message, "error"); } catch (_) {}
});
