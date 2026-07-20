const state = {
  config: null,
  agents: [],
  selectedAgentId: null,
  lifeEventTemplates: [],
  lifeEvents: [],
  trace: null,
  traceGeneratedAt: null,
  // Frames captured live from latest_frame.json between trace flushes
  // (the simulator only rewrites simulation_trace.json every N frames).
  liveFrames: new Map(),
  frameIndex: 0,
  follow: true,
  running: false,
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
  followLatestInput: document.getElementById("followLatestInput"),
  latestFrameBox: document.getElementById("latestFrameBox"),
  selectedAgentAvatar: document.getElementById("selectedAgentAvatar"),
  agentSelect: document.getElementById("agentSelect"),
  profileEditor: document.getElementById("profileEditor"),
  saveProfileBtn: document.getElementById("saveProfileBtn"),
  toggleSimBtn: document.getElementById("toggleSimBtn"),
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
  goalsPanel: document.getElementById("goalsPanel"),
  goalsEditor: document.getElementById("goalsEditor"),
  goalsEditBtn: document.getElementById("goalsEditBtn"),
  goalsSaveBtn: document.getElementById("goalsSaveBtn"),
  reloadStatusBtn: document.getElementById("reloadStatusBtn"),
  runLogBox: document.getElementById("runLogBox"),
};

// Terrain-map rendering (avatars, trails, landmarks, zoom/pan) is provided by
// the shared CityMapView module, used identically by the simviz replay tab.
const mapView = new CityMapView(els.mapCanvas, {
  getSelectedAgentId: () => state.selectedAgentId,
  emptyText: "等待轨迹数据…",
});

function traceAgentMap() {
  const agents = (state.trace && Array.isArray(state.trace.agents)) ? state.trace.agents : [];
  return new Map(agents.map((agent) => [Number(agent.id), agent]));
}

function resolveAssetPath(assetPath) {
  const text = String(assetPath || "").trim();
  if (!text) return "";
  if (/^(https?:)?\/\//.test(text) || text.startsWith("data:")) return text;
  // The trace stores paths relative to the visualization output dir
  // (e.g. "avatars/agent_33.svg"), not relative to this page.
  if (!text.startsWith("/")) return `/output/visualization/${text}`;
  return text;
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

let messageTimer = null;
function message(text, tone = "") {
  els.messageLine.textContent = text || "";
  els.messageLine.className = `toast${text ? " show" : ""}${tone ? ` ${tone}` : ""}`;
  if (messageTimer) window.clearTimeout(messageTimer);
  if (text) {
    messageTimer = window.setTimeout(() => {
      els.messageLine.className = "toast";
    }, tone === "error" ? 10000 : 4000);
  }
}

// Enable/disable controls according to whether a simulation is running:
// run buttons and run-config inputs lock while running, stop unlocks.
function syncRunButtons() {
  const running = Boolean(state.running);
  els.runBtn.disabled = running;
  els.resetRunBtn.disabled = running;
  els.stopBtn.disabled = !running;
  [
    els.agentIdsInput,
    els.simDaysInput,
    els.secondsPerDayInput,
    els.timeStepInput,
    els.defaultProviderSelect,
    els.scheduleProviderSelect,
    els.realtimeInput,
  ].forEach((el) => { el.disabled = running; });
  if (els.toggleSimBtn) els.toggleSimBtn.disabled = running;
  document.body.classList.toggle("is-running", running);
}

// Wrap an async click handler: disable the button and show a spinner while
// it runs, and surface any error on the message line.
function withBusy(btn, fn) {
  return async () => {
    if (btn.disabled) return;
    btn.disabled = true;
    btn.classList.add("busy");
    try {
      await fn();
    } catch (error) {
      message(error.message, "error");
    } finally {
      btn.disabled = false;
      btn.classList.remove("busy");
      // Re-apply run-state locking in case this button is one of the
      // run controls (e.g. 停止 must stay disabled once nothing runs).
      syncRunButtons();
    }
  };
}

// Replace a log box's text, keeping it pinned to the bottom if the user
// hasn't scrolled up.
function setLogText(el, text) {
  if (el.textContent === text) return;
  const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
  el.textContent = text;
  if (nearBottom) el.scrollTop = el.scrollHeight;
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

// The toolbar "Agent IDs" input is the single source of truth for which
// agents run in the simulation; the profile dropdown mirrors it live.
function configuredIdSet() {
  return new Set(
    els.agentIdsInput.value
      .split(",")
      .map((part) => Number(part.trim()))
      .filter((id) => Number.isFinite(id) && id > 0)
  );
}

function refreshAgentOptionLabels() {
  const configured = configuredIdSet();
  Array.from(els.agentSelect.options).forEach((option) => {
    const agent = state.agents.find((item) => Number(item.id) === Number(option.value));
    if (!agent) return;
    const inSim = configured.has(Number(agent.id));
    option.textContent = `${inSim ? "▶ " : ""}${String(agent.id).padStart(2, "0")} · ${agent.name}${inSim ? "（仿真中）" : ""}`;
  });
  updateToggleSimBtn();
}

function updateToggleSimBtn() {
  if (!els.toggleSimBtn) return;
  const inSim = configuredIdSet().has(Number(state.selectedAgentId));
  els.toggleSimBtn.textContent = inSim ? "✓ 仿真中 · 点击移出" : "加入仿真";
  els.toggleSimBtn.classList.toggle("primary", inSim);
}

function toggleSelectedAgentInSim() {
  const id = Number(state.selectedAgentId);
  if (!id) return;
  const ids = configuredIdSet();
  if (ids.has(id)) ids.delete(id);
  else ids.add(id);
  els.agentIdsInput.value = Array.from(ids).sort((a, b) => a - b).join(",");
  refreshAgentOptionLabels();
  message(`Agent ${id} 已${ids.has(id) ? "加入" : "移出"}仿真名单，点击「保存配置」或「运行仿真」生效`);
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
    option.textContent = `${String(agent.id).padStart(2, "0")} · ${agent.name}`;
    option.selected = agent.id === state.selectedAgentId;
    els.agentSelect.appendChild(option);
  });
  refreshAgentOptionLabels();
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

function escapeGoalsHtml(text) {
  const div = document.createElement("div");
  div.textContent = String(text == null ? "" : text);
  return div.innerHTML;
}

function renderGoals(goals) {
  if (!els.goalsPanel) return;
  const tiers = [
    ["life_goals", __("goals.life")],
    ["long_term_goals", __("goals.long")],
    ["short_term_goals", __("goals.short")],
  ];
  const hasAny = goals && tiers.some(([k]) => Array.isArray(goals[k]) && goals[k].length);
  if (!hasAny) {
    els.goalsPanel.textContent = __("goals.empty");
    return;
  }
  const parts = [];
  for (const [key, label] of tiers) {
    const items = (goals[key] || []).filter(Boolean);
    if (!items.length) continue;
    const rows = items.map((g) => {
      const progress = typeof g.progress === "number"
        ? ` <progress max="1" value="${g.progress}"></progress> ${Math.round(g.progress * 100)}%`
        : "";
      const status = g.status && g.status !== "active"
        ? ` <em>[${escapeGoalsHtml(g.status)}]</em>` : "";
      return `<li>${escapeGoalsHtml(g.title)}${progress}${status}</li>`;
    }).join("");
    parts.push(`<h4>${escapeGoalsHtml(label)}</h4><ul>${rows}</ul>`);
  }
  const lastReview = (goals.review_log || []).slice(-1)[0];
  if (lastReview) {
    parts.push(`<p>Day ${Number(lastReview.day) || 0}: ${escapeGoalsHtml(lastReview.summary)}</p>`);
  }
  els.goalsPanel.innerHTML = parts.join("");
}

async function loadGoals() {
  if (!state.selectedAgentId) return;
  const goals = await api(`/api/agents/${state.selectedAgentId}/goals`);
  renderGoals(goals || {});
  if (els.goalsEditor) {
    els.goalsEditor.value = JSON.stringify(goals || {}, null, 2);
  }
}

async function saveGoals() {
  if (!state.selectedAgentId) return;
  let payload;
  try {
    payload = JSON.parse(els.goalsEditor.value);
  } catch (e) {
    message(__("goals.invalid_json"), "error");
    return;
  }
  await api(`/api/agents/${state.selectedAgentId}/goals`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await loadGoals();
  message(__("goals.saved"));
}

async function runSimulation(reset = false) {
  message(reset ? "正在重置并启动仿真..." : __("sim.starting"));
  const payload = { reset, config: configPayloadFromForm() };
  await api("/api/run/start", { method: "POST", body: JSON.stringify(payload) });
  state.follow = true;
  message("仿真已启动，地图将实时跟随最新帧");
  await refreshStatus();
}

async function stopSimulation() {
  await api("/api/run/stop", { method: "POST", body: "{}" });
  message("已停止仿真");
  await refreshStatus();
}

async function refreshStatus() {
  const status = await api("/api/run/status");
  state.running = Boolean(status.running);
  syncRunButtons();
  els.runStatusBadge.textContent = status.running ? __("sim.running") : status.returncode == null ? __("sim.not_run") : __("sim.finished") + " " + status.returncode;
  els.runStatusBadge.className = `status-badge ${status.running ? "running" : status.returncode === 0 ? "done" : status.returncode ? "error" : ""}`;
  setLogText(els.runLogBox, status.log_tail || __("run_log.no_log"));
  if (status.running) loadTrace(false).catch(() => {});
}

// The simulator only rewrites simulation_trace.json every N frames but
// updates latest_frame.json on every step, so a live view has to merge both.
function allFrames() {
  const traceFrames = state.trace && Array.isArray(state.trace.frames) ? state.trace.frames : [];
  if (!state.liveFrames.size) return traceFrames;
  const lastFlushed = traceFrames.length
    ? Number(traceFrames[traceFrames.length - 1].index ?? traceFrames.length - 1)
    : -1;
  const extra = Array.from(state.liveFrames.values())
    .filter((frame) => Number(frame.index) > lastFlushed)
    .sort((a, b) => Number(a.index) - Number(b.index));
  return traceFrames.concat(extra);
}

async function loadTrace(showErrors = true) {
  try {
    const response = await fetch(`/output/visualization/simulation_trace.json?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const trace = await response.json();
    const generatedAt = trace.meta && trace.meta.generated_at;
    if (generatedAt && generatedAt !== state.traceGeneratedAt) {
      // New run: drop frames captured from the previous run.
      state.traceGeneratedAt = generatedAt;
      state.liveFrames.clear();
      state.frameIndex = 0;
      state.follow = true;
      state.avatarCache.clear();
    }
    state.trace = trace;
  } catch (error) {
    if (showErrors) {
      els.traceStatus.textContent = __("trace.load_failed") + ": " + error.message;
      drawEmptyMap();
    }
    if (!state.trace) return;
  }
  try {
    const response = await fetch(`/output/visualization/latest_frame.json?t=${Date.now()}`, { cache: "no-store" });
    if (response.ok) {
      const latest = await response.json();
      const frame = latest && latest.frame;
      if (frame && frame.index != null && Array.isArray(frame.agents)) {
        state.liveFrames.set(Number(frame.index), frame);
      }
    }
  } catch (_error) {
    // latest_frame is best-effort; the flushed trace still renders.
  }
  const traceFrames = Array.isArray(state.trace.frames) ? state.trace.frames : [];
  const lastFlushed = traceFrames.length
    ? Number(traceFrames[traceFrames.length - 1].index ?? traceFrames.length - 1)
    : -1;
  Array.from(state.liveFrames.keys()).forEach((key) => {
    if (key <= lastFlushed) state.liveFrames.delete(key);
  });
  const frames = allFrames();
  if (!frames.length) state.frameIndex = 0;
  else if (state.follow) state.frameIndex = frames.length - 1;
  else state.frameIndex = Math.min(state.frameIndex, frames.length - 1);
  renderTrace();
}

function currentFrame() {
  return allFrames()[state.frameIndex] || null;
}

function renderTrace() {
  const frames = allFrames();
  const frame = frames[state.frameIndex] || null;
  if (!frame) {
    // No agent frames yet — but if the trace already carries the map, draw it
    // (terrain + nodes) instead of a blank placeholder, so the city map is
    // visible as soon as a run starts, before any frame is produced.
    const mapNodes = state.trace && state.trace.map && state.trace.map.nodes;
    if (Array.isArray(mapNodes) && mapNodes.length) {
      drawMap([]);
    } else {
      drawEmptyMap();
    }
    if (state.trace) els.traceStatus.textContent = "轨迹已初始化 · 0 帧";
    return;
  }
  renderSelectedAgentAvatar();
  els.frameTitle.textContent = `Day ${frame.day} · ${frame.time}`;
  const finished = state.trace.meta && state.trace.meta.finished;
  const liveCount = frames.length - (Array.isArray(state.trace.frames) ? state.trace.frames.length : 0);
  els.traceStatus.textContent = `${frames.length} 帧${liveCount > 0 ? `（含 ${liveCount} 实时帧）` : ""} · ${finished ? "已完成" : "写入中"}`;
  els.timelineSlider.max = String(Math.max(0, frames.length - 1));
  els.timelineSlider.value = String(state.frameIndex);
  els.timelineLabel.textContent = `${frame.date || ""} ${frame.weekday || ""} ${frame.time || ""}`.trim();
  if (els.followLatestInput) els.followLatestInput.checked = state.follow;
  els.latestFrameBox.textContent = JSON.stringify(frame, null, 2);
  drawMap(frames.slice(0, state.frameIndex + 1));
}

function drawEmptyMap() {
  mapView.renderEmpty(__("trace.waiting"));
  els.frameTitle.textContent = __("trace.not_loaded");
  els.timelineLabel.textContent = __("trace.no_frames");
  els.latestFrameBox.textContent = __("trace.no_current_frame");
}

// The terrain map (baked tiles, place markers, LOD landmark labels, agent
// trails, large avatars, zoom/pan) is rendered by the shared CityMapView
// module (site/shared/citymap-view.js) — the same renderer the simviz replay
// tab uses, so the two views stay identical.
function drawMap(framesUpTo) {
  mapView.setTrace(state.trace);
  mapView.render(framesUpTo);
}

function setupMapInteractions() {
  // Zoom (wheel / buttons) + pan (drag) are wired inside CityMapView.
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
  if (!questions.length) {
    els.interviewOutput.textContent = "请先在上方输入至少一个问题（每行一个）。";
    return;
  }
  const payload = {
    agent_id: state.selectedAgentId,
    context: els.interviewContext.value.trim(),
    questions,
  };
  const startedAt = Date.now();
  els.interviewOutput.textContent = "采访运行中... 0s";
  const timer = window.setInterval(() => {
    const elapsed = Math.round((Date.now() - startedAt) / 1000);
    els.interviewOutput.textContent = `采访运行中... ${elapsed}s（LLM 生成通常需要 1-3 分钟）`;
  }, 1000);
  try {
    const result = await api("/api/interview", { method: "POST", body: JSON.stringify(payload) });
    els.interviewOutput.textContent = [result.stdout, result.stderr].filter(Boolean).join("\n") || __f("interview.no_result", {code: result.returncode});
  } finally {
    window.clearInterval(timer);
  }
}

function bindEvents() {
  els.saveConfigBtn.addEventListener("click", withBusy(els.saveConfigBtn, saveConfig));
  els.runBtn.addEventListener("click", withBusy(els.runBtn, () => runSimulation(false)));
  els.resetRunBtn.addEventListener("click", withBusy(els.resetRunBtn, () => runSimulation(true)));
  els.stopBtn.addEventListener("click", withBusy(els.stopBtn, stopSimulation));
  els.reloadTraceBtn.addEventListener("click", withBusy(els.reloadTraceBtn, async () => {
    await loadTrace(true);
    message("轨迹已刷新");
  }));
  els.reloadStatusBtn.addEventListener("click", withBusy(els.reloadStatusBtn, async () => {
    await refreshStatus();
    message("运行状态已刷新");
  }));
  els.agentSelect.addEventListener("change", async () => {
    state.selectedAgentId = Number(els.agentSelect.value);
    renderSelectedAgentAvatar();
    updateToggleSimBtn();
    renderTrace();
    try {
      await loadProfile();
      await loadMemory();
      await loadGoals();
    } catch (error) {
      message(error.message, "error");
    }
  });
  els.agentIdsInput.addEventListener("input", refreshAgentOptionLabels);
  if (els.toggleSimBtn) els.toggleSimBtn.addEventListener("click", toggleSelectedAgentInSim);
  els.saveProfileBtn.addEventListener("click", withBusy(els.saveProfileBtn, saveProfile));
  els.refreshAgentBtn.addEventListener("click", withBusy(els.refreshAgentBtn, async () => {
    await loadProfile();
    message("Profile 已刷新");
  }));
  els.reloadMemoryBtn.addEventListener("click", withBusy(els.reloadMemoryBtn, async () => {
    await loadMemory();
    await loadGoals();
    message("记忆已刷新");
  }));
  if (els.goalsEditBtn) els.goalsEditBtn.addEventListener("click", () => {
    const show = els.goalsEditor.style.display === "none";
    els.goalsEditor.style.display = show ? "block" : "none";
    els.goalsSaveBtn.style.display = show ? "inline-block" : "none";
  });
  if (els.goalsSaveBtn) els.goalsSaveBtn.addEventListener("click", withBusy(els.goalsSaveBtn, saveGoals));
  els.interviewBtn.addEventListener("click", withBusy(els.interviewBtn, () => interview().catch((error) => {
    els.interviewOutput.textContent = `采访失败：${error.message}`;
  })));
  els.lifeEventTemplateSelect.addEventListener("change", () => {
    els.lifeEventTitleInput.value = "";
    els.lifeEventDescriptionInput.value = "";
    applyLifeEventTemplate();
  });
  els.useSelectedAgentBtn.addEventListener("click", () => {
    if (state.selectedAgentId) {
      els.lifeEventAgentInput.value = String(state.selectedAgentId);
      message(`人生事件目标已设为 Agent ${state.selectedAgentId}`);
    }
  });
  els.addLifeEventBtn.addEventListener("click", withBusy(els.addLifeEventBtn, addLifeEvent));
  els.reloadLifeEventsBtn.addEventListener("click", withBusy(els.reloadLifeEventsBtn, async () => {
    await loadLifeEvents();
    message("人生事件已刷新");
  }));
  els.fosExportBtn.addEventListener("click", () => fosExport().catch((error) => message(error.message, "error")));
  els.fosCopyBtn.addEventListener("click", () => {
    const text = els.fosOutputBox.textContent;
    if (text && text !== window.__("fos_export.no_output")) {
      navigator.clipboard.writeText(text).then(() => message("Copied!")).catch(() => message("Copy failed"));
    }
  });
  els.timelineSlider.addEventListener("input", () => {
    state.frameIndex = Number(els.timelineSlider.value || 0);
    // Scrubbing away from the newest frame pauses follow; dragging back to
    // the end resumes it.
    state.follow = state.frameIndex >= allFrames().length - 1;
    renderTrace();
  });
  if (els.followLatestInput) {
    els.followLatestInput.addEventListener("change", () => {
      state.follow = els.followLatestInput.checked;
      if (state.follow) {
        const frames = allFrames();
        state.frameIndex = frames.length ? frames.length - 1 : 0;
      }
      renderTrace();
    });
  }
  els.selectedAgentAvatar.addEventListener("error", () => {
    els.selectedAgentAvatar.style.visibility = "hidden";
  });
  els.selectedAgentAvatar.addEventListener("load", () => {
    els.selectedAgentAvatar.style.visibility = "visible";
  });
}

async function init() {
  bindEvents();
  setupMapInteractions();
  drawEmptyMap();
  const steps = [
    ["配置", loadConfig],
    ["人物列表", loadAgents],
    ["人生事件", loadLifeEvents],
    ["Profile", loadProfile],
    ["记忆", loadMemory],
    ["目标", loadGoals],
    ["运行状态", refreshStatus],
  ];
  for (const [label, step] of steps) {
    try {
      await step();
    } catch (error) {
      message(`${label}加载失败: ${error.message}`, "error");
    }
  }
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
  loadGoals().catch(() => {});
  renderTrace();
});

init().catch((error) => message(error.message, "error"));
