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
