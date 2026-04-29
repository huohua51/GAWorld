const state = {
  config: null,
  agents: [],
  selectedAgentId: null,
  lifeEventTemplates: [],
  lifeEvents: [],
  trace: null,
  frameIndex: 0,
  pollTimer: null,
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
  frameTitle: document.getElementById("frameTitle"),
  mapCanvas: document.getElementById("mapCanvas"),
  timelineSlider: document.getElementById("timelineSlider"),
  timelineLabel: document.getElementById("timelineLabel"),
  latestFrameBox: document.getElementById("latestFrameBox"),
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
  reloadMemoryBtn: document.getElementById("reloadMemoryBtn"),
  memoryBox: document.getElementById("memoryBox"),
  stateMemoryBox: document.getElementById("stateMemoryBox"),
  episodesBox: document.getElementById("episodesBox"),
  agentLogBox: document.getElementById("agentLogBox"),
  reloadStatusBtn: document.getElementById("reloadStatusBtn"),
  runLogBox: document.getElementById("runLogBox"),
};

const ctx = els.mapCanvas.getContext("2d");
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
    option.selected = agent.id === state.selectedAgentId;
    els.agentSelect.appendChild(option);
  });
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
  els.runLogBox.textContent = status.log_tail || "暂无运行日志。";
  if (status.running) loadTrace(false).catch(() => {});
}

async function loadTrace(showErrors = true) {
  try {
    const response = await fetch(`/output/visualization/simulation_trace.json?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.trace = await response.json();
    const frames = Array.isArray(state.trace.frames) ? state.trace.frames : [];
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

function renderTrace() {
  const frame = currentFrame();
  const frames = state.trace && Array.isArray(state.trace.frames) ? state.trace.frames : [];
  if (!frame) {
    drawEmptyMap();
    return;
  }
  els.frameTitle.textContent = `Day ${frame.day} · ${frame.time}`;
  els.traceStatus.textContent = `${frames.length} 帧 · ${state.trace.meta && state.trace.meta.finished ? "已完成" : "写入中"}`;
  els.timelineSlider.max = String(Math.max(0, frames.length - 1));
  els.timelineSlider.value = String(state.frameIndex);
  els.timelineLabel.textContent = `${frame.date || ""} ${frame.weekday || ""} ${frame.time || ""}`.trim();
  els.latestFrameBox.textContent = JSON.stringify(frame, null, 2);
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

  (frame.agents || []).forEach((agent) => {
    const node = nodes.get(agent.target_location) || nodes.get(agent.resolved_location);
    if (!node) return;
    const x = offsetX + node.tile_x * scale + scale / 2;
    const y = offsetY + node.tile_y * scale + scale / 2;
    const color = agentColors[Math.abs(Number(agent.agent_id || 0)) % agentColors.length];
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, agent.agent_id === state.selectedAgentId ? 11 : 8, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#fffef9";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = "#17211d";
    ctx.font = "12px Aptos";
    ctx.fillText(agent.name || agent.agent_id, x + 12, y - 9);
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
  els.saveConfigBtn.addEventListener("click", () => saveConfig().catch((error) => message(error.message, "error")));
  els.runBtn.addEventListener("click", () => runSimulation(false).catch((error) => message(error.message, "error")));
  els.resetRunBtn.addEventListener("click", () => runSimulation(true).catch((error) => message(error.message, "error")));
  els.stopBtn.addEventListener("click", () => stopSimulation().catch((error) => message(error.message, "error")));
  els.reloadTraceBtn.addEventListener("click", () => loadTrace(true));
  els.reloadStatusBtn.addEventListener("click", () => refreshStatus().catch((error) => message(error.message, "error")));
  els.agentSelect.addEventListener("change", async () => {
    state.selectedAgentId = Number(els.agentSelect.value);
    await loadProfile();
    await loadMemory();
    renderTrace();
  });
  els.saveProfileBtn.addEventListener("click", () => saveProfile().catch((error) => message(error.message, "error")));
  els.refreshAgentBtn.addEventListener("click", () => loadProfile().catch((error) => message(error.message, "error")));
  els.reloadMemoryBtn.addEventListener("click", () => loadMemory().catch((error) => message(error.message, "error")));
  els.interviewBtn.addEventListener("click", () => interview().catch((error) => {
    els.interviewOutput.textContent = error.message;
  }));
  els.lifeEventTemplateSelect.addEventListener("change", () => {
    els.lifeEventTitleInput.value = "";
    els.lifeEventDescriptionInput.value = "";
    applyLifeEventTemplate();
  });
  els.useSelectedAgentBtn.addEventListener("click", () => {
    if (state.selectedAgentId) els.lifeEventAgentInput.value = String(state.selectedAgentId);
  });
  els.addLifeEventBtn.addEventListener("click", () => addLifeEvent().catch((error) => message(error.message, "error")));
  els.reloadLifeEventsBtn.addEventListener("click", () => loadLifeEvents().catch((error) => message(error.message, "error")));
  els.timelineSlider.addEventListener("input", () => {
    state.frameIndex = Number(els.timelineSlider.value || 0);
    renderTrace();
  });
}

async function init() {
  bindEvents();
  await loadConfig();
  await loadAgents();
  await loadLifeEvents();
  await loadProfile();
  await loadMemory();
  await refreshStatus();
  await loadTrace(false);
  state.pollTimer = window.setInterval(() => {
    refreshStatus().catch(() => {});
    loadTrace(false).catch(() => {});
    loadLifeEvents().catch(() => {});
  }, 2500);
}

init().catch((error) => message(error.message, "error"));
