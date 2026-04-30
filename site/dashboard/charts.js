/* Chart.js wrappers for GAWorld dashboard.
 * Separate module so app.js handles data fetching and charts.js handles Chart.js lifecycle.
 */

const chartState = {
  radar: null,
  economy: null,
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

const MULTI_AGENT_COLORS = [
  { border: "rgba(19, 121, 91, 0.85)", background: "rgba(19, 121, 91, 0.15)", point: "rgba(19, 121, 91, 1)" },
  { border: "rgba(183, 62, 62, 0.85)", background: "rgba(183, 62, 62, 0.15)", point: "rgba(183, 62, 62, 1)" },
  { border: "rgba(56, 88, 102, 0.85)", background: "rgba(56, 88, 102, 0.15)", point: "rgba(56, 88, 102, 1)" },
  { border: "rgba(214, 168, 30, 0.85)", background: "rgba(214, 168, 30, 0.15)", point: "rgba(214, 168, 30, 1)" },
  { border: "rgba(110, 95, 151, 0.85)", background: "rgba(110, 95, 151, 0.15)", point: "rgba(110, 95, 151, 1)" },
  { border: "rgba(31, 138, 155, 0.85)", background: "rgba(31, 138, 155, 0.15)", point: "rgba(31, 138, 155, 1)" },
  { border: "rgba(138, 91, 48, 0.85)", background: "rgba(138, 91, 48, 0.15)", point: "rgba(138, 91, 48, 1)" },
];

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
    data: { labels: [], datasets: [] },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: { legend: { display: false } },
      scales: {
        r: {
          beginAtZero: true,
          max: 1.0,
          ticks: { stepSize: 0.2, font: { size: 10 }, backdropColor: "transparent" },
          grid: { color: "rgba(203, 215, 205, 0.6)" },
          angleLines: { color: "rgba(203, 215, 205, 0.6)" },
          pointLabels: { font: { size: 12, weight: "bold" }, color: "#17211d" },
        },
      },
    },
  });
  return chartState.radar;
}

function updateRadarChart(state, overlayAgents) {
  if (!chartState.radar) return;
  const isCompare = Array.isArray(overlayAgents) && overlayAgents.length > 0;

  if (!isCompare) {
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
      document.getElementById("radarLegend").style.display = "none";
      return;
    }
    document.getElementById("radarPlaceholder").style.display = "none";
    chartState.radar.canvas.style.display = "block";
    document.getElementById("radarLegend").style.display = "none";
    chartState.radar.data.labels = labels;
    chartState.radar.data.datasets = [{
      label: "当前状态",
      data: values,
      borderColor: RADAR_COLORS.border,
      backgroundColor: RADAR_COLORS.background,
      pointBackgroundColor: RADAR_COLORS.point,
      pointBorderColor: "#fffef9",
      pointRadius: 4,
      borderWidth: 2,
    }];
    chartState.radar.update();
    return;
  }

  const allLabels = Object.values(RADAR_LABELS);
  chartState.radar.data.labels = allLabels;
  chartState.radar.data.datasets = overlayAgents.map((agent, i) => {
    const colors = MULTI_AGENT_COLORS[i % MULTI_AGENT_COLORS.length];
    const values = [];
    for (const key of Object.keys(RADAR_LABELS)) {
      const val = agent.state && agent.state[key];
      values.push(val !== undefined && val !== null ? Number(val) : null);
    }
    return {
      label: agent.name || `Agent ${agent.agent_id}`,
      data: values,
      borderColor: colors.border,
      backgroundColor: colors.background,
      pointBackgroundColor: colors.point,
      pointBorderColor: "#fffef9",
      pointRadius: 4,
      borderWidth: 2,
    };
  });
  document.getElementById("radarPlaceholder").style.display = "none";
  chartState.radar.canvas.style.display = "block";
  chartState.radar.update();
  updateRadarLegend(overlayAgents);
}

function updateRadarLegend(overlayAgents) {
  const legend = document.getElementById("radarLegend");
  if (!Array.isArray(overlayAgents) || overlayAgents.length === 0) {
    legend.style.display = "none";
    return;
  }
  legend.innerHTML = overlayAgents.map((agent, i) => {
    const colors = MULTI_AGENT_COLORS[i % MULTI_AGENT_COLORS.length];
    const isSelected = agent.agent_id === window.__selectedAgentId__;
    return `<span class="radar-legend-item" style="${isSelected ? "font-weight:900" : ""}">
      <span class="radar-legend-swatch" style="background:${colors.border}"></span>
      ${agent.name || `Agent ${agent.agent_id}`}
    </span>`;
  }).join("");
  legend.style.display = "flex";
}

/* ── Economy: balance / income / expense trend ──────────────────── */

const ECONOMY_COLORS = {
  balance: { border: "rgba(19, 121, 91, 0.9)", background: "rgba(19, 121, 91, 0.1)" },
  income: { border: "rgba(56, 88, 102, 0.9)", background: "rgba(56, 88, 102, 0.1)" },
  expense: { border: "rgba(183, 62, 62, 0.9)", background: "rgba(183, 62, 62, 0.1)" },
};

function initEconomyChart(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return null;
  if (chartState.economy) {
    chartState.economy.destroy();
    chartState.economy = null;
  }
  const ctx = canvas.getContext("2d");
  chartState.economy = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "余额", data: [], borderColor: ECONOMY_COLORS.balance.border, backgroundColor: ECONOMY_COLORS.balance.background, fill: true, tension: 0.3, pointRadius: 3 },
        { label: "收入", data: [], borderColor: ECONOMY_COLORS.income.border, backgroundColor: ECONOMY_COLORS.income.background, fill: false, tension: 0.3, pointRadius: 2, borderDash: [4, 3] },
        { label: "支出", data: [], borderColor: ECONOMY_COLORS.expense.border, backgroundColor: ECONOMY_COLORS.expense.background, fill: false, tension: 0.3, pointRadius: 2, borderDash: [4, 3] },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, padding: 12, font: { size: 11 } } },
        tooltip: { mode: "index", intersect: false },
      },
      scales: {
        x: {
          title: { display: true, text: "Day", font: { size: 11 } },
          ticks: { font: { size: 10 } },
          grid: { color: "rgba(203, 215, 205, 0.4)" },
        },
        y: {
          beginAtZero: true,
          ticks: { font: { size: 10 } },
          grid: { color: "rgba(203, 215, 205, 0.4)" },
        },
      },
      interaction: { mode: "index", intersect: false },
    },
  });
  return chartState.economy;
}

function updateEconomyChart(data) {
  if (!chartState.economy) return;
  const history = Array.isArray(data) ? data : [];
  const placeholder = document.getElementById("economyChartPlaceholder");
  if (history.length === 0) {
    placeholder.style.display = "block";
    chartState.economy.canvas.style.display = "none";
    return;
  }
  placeholder.style.display = "none";
  chartState.economy.canvas.style.display = "block";
  chartState.economy.data.labels = history.map((row) => `Day ${row.day}`);
  chartState.economy.data.datasets[0].data = history.map((row) => row.balance);
  chartState.economy.data.datasets[1].data = history.map((row) => row.income);
  chartState.economy.data.datasets[2].data = history.map((row) => row.expense);
  chartState.economy.update();
}
