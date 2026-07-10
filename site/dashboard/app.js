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
  fosHintInput: document.getElementById("fosHintInput"),
  fosEnglishCheckbox: document.getElementById("fosEnglishCheckbox"),
  fosExportBtn: document.getElementById("fosExportBtn"),
  fosCopyBtn: document.getElementById("fosCopyBtn"),
  fosOutputBox: document.getElementById("fosOutputBox"),
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
  message(__("config.saved"));
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
    els.lifeEventListBox.textContent = __("life_event.none");
    return;
  }
  els.lifeEventListBox.textContent = events.slice().reverse().map((event) => {
    const target = (event.agent_ids || []).length ? `#${event.agent_ids.join(",#")}` : __("agent.all");
    const when = event.schedule_mode === "immediate"
      ? __("life_event.immediate")
      : __f("life_event.scheduled_fmt", {day: event.day || "?", time: event.time || __("life_event.current_time")});
    const status = event.status === "consumed"
      ? __f("life_event.triggered_at", {day: event.triggered_day || "?", time: event.triggered_time || ""})
      : __("life_event.pending");
    return [
      `[${status}] ${event.title || __("life_event.event_prefix")}`,
      __f("life_event.detail", {target: target, when: when, severity: Number(event.severity || 0).toFixed(2)}),
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
  message(__("life_event.queued"));
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
  message(__("common.saved"));
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
  els.episodesBox.textContent = payload.episodes_tail || __("memory.no_episodes");
  els.agentLogBox.textContent = payload.log_tail || __("memory.no_agent_log");
}

async function runSimulation(reset = false) {
  message(__("sim.starting"));
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
  els.runStatusBadge.textContent = status.running ? __("sim.running") : status.returncode == null ? __("sim.not_run") : __("sim.finished") + " " + status.returncode;
  els.runStatusBadge.className = `status-badge ${status.running ? "running" : status.returncode === 0 ? "done" : status.returncode ? "error" : ""}`;
  els.runLogBox.textContent = status.log_tail || __("run_log.no_log");
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
      els.traceStatus.textContent = __("trace.load_failed") + ": " + error.message;
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
  renderSelectedAgentAvatar();
  els.frameTitle.textContent = `Day ${frame.day} · ${frame.time}`;
  els.traceStatus.textContent = __f("trace.status", {count: frames.length, status: state.trace.meta && state.trace.meta.finished ? __("trace.completed") : __("trace.writing")});
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
  ctx.fillText(__("trace.waiting"), 40, 56);
  els.frameTitle.textContent = __("trace.not_loaded");
  els.timelineLabel.textContent = __("trace.no_frames");
  els.latestFrameBox.textContent = __("trace.no_current_frame");
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
    const radius = agent.agent_id === state.selectedAgentId ? 11 : 8;
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
    ctx.fillStyle = "#17211d";
    ctx.font = "12px Aptos";
    ctx.fillText(agent.name || agent.agent_id, x + 12, y - 9);
  });
}

async function fosExport() {
  const hint = els.fosHintInput.value.trim() || null;
  const english = els.fosEnglishCheckbox.checked;
  els.fosOutputBox.textContent = window.__("fos_export.generating");
  const payload = { hint, english };
  const result = await api("/api/fos-export", { method: "POST", body: JSON.stringify(payload) });
  if (result.error) {
    els.fosOutputBox.textContent = "Error: " + result.error;
    return;
  }
  let output = result.prompt;
  if (result.summary) {
    output = result.summary + "\n\n" + output;
  }
  els.fosOutputBox.textContent = output;
}

async function interview() {
  if (!state.selectedAgentId) return;
  els.interviewOutput.textContent = __("interview.running");
  const questions = els.interviewQuestions.value.split("\n").map((line) => line.trim()).filter(Boolean);
  const payload = {
    agent_id: state.selectedAgentId,
    context: els.interviewContext.value.trim(),
    questions,
  };
  const result = await api("/api/interview", { method: "POST", body: JSON.stringify(payload) });
  els.interviewOutput.textContent = [result.stdout, result.stderr].filter(Boolean).join("\n") || __f("interview.no_result", {code: result.returncode});
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
    renderSelectedAgentAvatar();
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
  els.fosExportBtn.addEventListener("click", () => fosExport().catch((error) => message(error.message, "error")));
  els.fosCopyBtn.addEventListener("click", () => {
    const text = els.fosOutputBox.textContent;
    if (text && text !== window.__("fos_export.no_output")) {
      navigator.clipboard.writeText(text).then(() => message("Copied!")).catch(() => message("Copy failed"));
    }
  });
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

// Re-render dynamic UI when language changes
window.addEventListener("locale-changed", function () {
  refreshStatus().catch(() => {});
  loadTrace(false).catch(() => {});
  loadLifeEvents().catch(() => {});
  loadMemory().catch(() => {});
  renderTrace();
});

init().catch((error) => message(error.message, "error"));
