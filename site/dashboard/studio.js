/* GAWorld Agent Studio — display + edit UI wired to the dashboard API.
 * Fields map to GAWorld's real seed model: identity + 9 normalized [0,1]
 * state variables (CSV), narrative profile (Markdown), memory / skills /
 * finance (read-only, populated by the simulator). */

"use strict";

const STATE_VARS = [
  { key: "emotion",             cn: "情绪",     en: "emotion",             lo: "消极",   hi: "积极" },
  { key: "stress",              cn: "压力",     en: "stress",              lo: "无压力", hi: "极高" },
  { key: "econ_security",       cn: "经济安全感", en: "econ security",     lo: "不安全", hi: "安全" },
  { key: "city_identity",       cn: "城市认同", en: "city identity",       lo: "疏离",   hi: "认同" },
  { key: "policy_sensitivity",  cn: "政策敏感度", en: "policy sensitivity", lo: "迟钝",  hi: "敏感" },
  { key: "platform_dependence", cn: "平台依赖", en: "platform dependence", lo: "多元",   hi: "绑定" },
  { key: "risk_preference",     cn: "风险偏好", en: "risk preference",     lo: "厌恶",   hi: "偏好" },
  { key: "voice_propensity",    cn: "公共表达", en: "voice propensity",    lo: "沉默",   hi: "主动" },
  { key: "mobility_intent",     cn: "流动意愿", en: "mobility intent",     lo: "定居",   hi: "流动" },
];
const BEHAVIOR_KEYS = ["mobility_intent", "voice_propensity", "risk_preference", "platform_dependence", "policy_sensitivity"];

const store = {
  agents: [],
  currentId: null,
  detail: null,
  creating: false,
  step: 1,
  draft: null, // { identity:{...}, state:{...}, profile_text, narrative:{personality, job} }
  goalsDraft: null, // working copy of the three-tier goals, edited inline in step 6
  goalSeq: 0, // counter for client-side ids of newly added goals
  stateDirty: false, // step 2 sliders moved but not yet confirmed
  profileEditing: false, // step 1 profile shows rendered Markdown until this flips
  profileEdit: "", // buffer for the profile textarea, discarded on cancel
  socialDraft: null, // working copy of the relationship edges, edited inline in step 5
  socialRemoved: [], // ids deleted from socialDraft, sent with the next save
  familyPreview: null, // server-side family preview for the current agent (step 5)
  familyDraft: null, // working copy of this agent's family override
  familyLoading: false, // guards the lazy preview fetch against retry loops
  financeDraft: null, // working copy of the editable finance state (step 7)
  memGraph: null, // { svg, nodes } for the inline memory graph
  memGraphBig: null, // { svg, nodes } for the zoomed modal graph
  memPick: null, // index into memGraph.nodes of the node whose body is shown
};

const $ = (sel) => document.querySelector(sel);

async function api(path, options = {}) {
  const res = await fetch(path, { cache: "no-store", headers: { "Content-Type": "application/json" }, ...options });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok || payload.error) throw new Error(payload.error || `HTTP ${res.status}`);
  return payload;
}

function foot(msg, tone = "") {
  const box = $("#footMsg");
  box.textContent = msg || "";
  box.className = "foot-msg " + tone;
}

function esc(text) {
  return String(text == null ? "" : text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function clamp01(v) { return Math.max(0, Math.min(1, Number(v) || 0)); }

/* Minimal Markdown → HTML, same subset the homepage profile panel renders. */
function renderMarkdown(md) {
  const inline = (t) => esc(t)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
  const lines = String(md || "").replace(/\r\n?/g, "\n").split("\n");
  let html = "";
  let inList = false;
  const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
  for (const ln of lines) {
    const h = ln.match(/^(#{1,4})\s+(.*)$/);
    const li = ln.match(/^\s*[-*]\s+(.*)$/);
    if (h) {
      closeList();
      const lvl = Math.min(h[1].length + 1, 5);
      html += `<h${lvl}>${inline(h[2])}</h${lvl}>`;
    } else if (li) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(li[1])}</li>`;
    } else if (ln.trim() === "") {
      closeList();
    } else {
      closeList();
      html += `<p>${inline(ln)}</p>`;
    }
  }
  closeList();
  return html;
}

/* ---------- avatar ---------- */
function placeholderAvatar(name) {
  const ch = esc((name || "?").trim().slice(0, 1) || "?");
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 120'><rect width='120' height='120' fill='#e3ede4'/><text x='60' y='78' font-family='Georgia,serif' font-size='58' fill='#13795b' text-anchor='middle'>${ch}</text></svg>`;
  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}
function setAvatar(id, name) {
  const img = $("#subjectAvatar");
  const ph = placeholderAvatar(name);
  if (id == null) { img.src = ph; return; }
  img.onerror = () => { img.onerror = null; img.src = ph; };
  img.src = `/output/visualization/avatars/agent_${Number(id)}.svg`;
}

/* ---------- radar ---------- */
function radarSVG(stateObj, withLabels) {
  const cx = 100, cy = 100, R = withLabels ? 66 : 74, n = STATE_VARS.length;
  const ang = (i) => (-90 + (i * 360) / n) * (Math.PI / 180);
  const pt = (i, r) => [cx + Math.cos(ang(i)) * r, cy + Math.sin(ang(i)) * r];
  let rings = "";
  [0.25, 0.5, 0.75, 1].forEach((f) => {
    const p = STATE_VARS.map((_, i) => pt(i, R * f).map((v) => v.toFixed(1)).join(",")).join(" ");
    rings += `<polygon points="${p}" fill="none" stroke="#cbd7cd" stroke-width="1"/>`;
  });
  let spokes = "", labels = "";
  STATE_VARS.forEach((v, i) => {
    const [x, y] = pt(i, R);
    spokes += `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="#e0e8e0" stroke-width="1"/>`;
    if (withLabels) {
      const [lx, ly] = pt(i, R + 15);
      const anchor = Math.abs(lx - cx) < 6 ? "middle" : (lx > cx ? "start" : "end");
      labels += `<text x="${lx.toFixed(1)}" y="${(ly + 3).toFixed(1)}" font-size="8.5" fill="#5c6860" text-anchor="${anchor}">${v.cn}</text>`;
    }
  });
  const poly = STATE_VARS.map((v, i) => pt(i, R * clamp01(stateObj[v.key])).map((c) => c.toFixed(1)).join(",")).join(" ");
  const dots = STATE_VARS.map((v, i) => { const [x, y] = pt(i, R * clamp01(stateObj[v.key])); return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.2" fill="#13795b"/>`; }).join("");
  return `<svg viewBox="0 0 200 200">${rings}${spokes}<polygon points="${poly}" fill="rgba(19,121,91,0.18)" stroke="#13795b" stroke-width="1.6"/>${dots}${labels}</svg>`;
}

/* ---------- data ---------- */
async function loadAgents() {
  const payload = await api("/api/agents");
  store.agents = payload.agents || [];
  const sel = $("#agentSelect");
  sel.innerHTML = store.agents.map((a) => `<option value="${a.id}">${esc(a.id)} · ${esc(a.name)}</option>`).join("");
  if (store.agents.length && store.currentId == null) {
    store.currentId = store.agents[0].id;
  }
  sel.value = String(store.currentId);
}

function draftFromDetail(d) {
  return {
    identity: { ...d.identity },
    state: { ...d.state },
    profile_text: d.profile_text || "",
    narrative: { personality: "", job: "" },
  };
}

function blankDraft() {
  const state = {};
  STATE_VARS.forEach((v) => (state[v.key] = v.key === "emotion" ? 0.55 : 0.5));
  return {
    identity: { id: null, name: "", gender: "女", age: 30, hukou: "本地", residence: "杭州" },
    state,
    profile_text: "",
    narrative: { personality: "", job: "" },
  };
}

async function selectAgent(id) {
  store.creating = false;
  store.currentId = Number(id);
  $("#saveHint").textContent = "加载中…";
  const d = await api(`/api/agents/${id}/detail`);
  store.detail = d;
  store.draft = draftFromDetail(d);
  store.goalsDraft = cloneGoals(d.goals);
  store.socialDraft = cloneRelations(d.social);
  store.socialRemoved = [];
  store.financeDraft = cloneFinance(d.finance_state);
  store.stateDirty = false;
  store.profileEditing = false;
  store.memPick = null;
  store.familyPreview = null;
  store.familyDraft = null;
  $("#saveHint").textContent = "已加载 · 自动回填";
  renderSubject();
  renderStep();
  // The family preview is a second request; render once without it so the
  // step is never blank, then again when it lands.
  loadFamilyPreview().then(() => { if (store.step === 5) renderStep(); });
}

function startCreate() {
  store.creating = true;
  store.currentId = null;
  store.detail = null;
  store.draft = blankDraft();
  store.goalsDraft = null;
  store.socialDraft = null;
  store.socialRemoved = [];
  store.financeDraft = null;
  store.stateDirty = false;
  store.profileEditing = false;
  store.memPick = null;
  store.familyPreview = null;
  store.familyDraft = null;
  store.step = 1;
  setActiveStepButton();
  $("#saveHint").textContent = "新建居民（未保存）";
  renderSubject();
  renderStep();
  foot("新建模式：填写身份与状态后点“保存”创建", "");
}

/* ---------- subject rail ---------- */
function renderSubject() {
  const dr = store.draft;
  if (!dr) return;
  const idt = dr.identity;
  setAvatar(store.creating ? null : store.currentId, idt.name);
  $("#subjectName").textContent = idt.name || (store.creating ? "新居民" : "—");
  const bits = [store.creating ? "未分配 ID" : `ID ${store.currentId}`, idt.gender, idt.age ? `${idt.age}岁` : "", idt.residence].filter(Boolean);
  $("#subjectMeta").textContent = bits.join(" · ");
  $("#miniRadar").outerHTML = `<svg id="miniRadar" viewBox="0 0 200 200">${radarSVG(dr.state, false).replace(/^<svg[^>]*>|<\/svg>$/g, "")}</svg>`;
}

/* ---------- steps ---------- */
function setActiveStepButton() {
  document.querySelectorAll(".step").forEach((b) => {
    const n = Number(b.dataset.step);
    b.classList.toggle("is-active", n === store.step);
    b.classList.toggle("is-done", n < store.step);
  });
}

function field(label, inputHTML) {
  return `<label class="field"><span>${esc(label)}</span>${inputHTML}</label>`;
}

function renderStep() {
  if (!store.draft) { $("#stepBody").innerHTML = `<p class="section-note">请选择或新建一个居民。</p>`; return; }
  setActiveStepButton();
  const fn = [null, stepIdentity, stepState, stepSkills, stepMemory, stepSocial, stepBehavior, stepReview][store.step];
  $("#stepBody").innerHTML = fn();
  bindStep();
}

function stepIdentity() {
  const i = store.draft.identity;
  const extra = store.creating
    ? `<div class="card"><h3>叙事种子（新建）</h3>
        ${field("职业 / 工作节奏", `<input data-nar="job" value="${esc(store.draft.narrative.job)}" placeholder="如：互联网初级工程师，晚 9-10 点下班">`)}
        ${field("性格 / 情绪特征", `<textarea data-nar="personality" placeholder="内向理性，绩效期焦虑…">${esc(store.draft.narrative.personality)}</textarea>`)}
      </div>`
    : profileCard();
  return `
    <h2 class="section-title">身份</h2>
    <p class="section-note">定义这位数字居民是谁。这些字段写入状态 CSV 与 profile。</p>
    <div class="cols side">
      <div>
        <div class="card">
          <h3>基础信息</h3>
          ${field("姓名", `<input data-idt="name" value="${esc(i.name)}">`)}
          <div class="grid2">
            ${field("性别", `<input data-idt="gender" value="${esc(i.gender)}">`)}
            ${field("年龄", `<input data-idt="age" type="number" min="16" max="90" value="${esc(i.age)}">`)}
          </div>
          <div class="grid2">
            ${field("户籍", `<input data-idt="hukou" value="${esc(i.hukou)}">`)}
            ${field("居住地", `<input data-idt="residence" value="${esc(i.residence)}">`)}
          </div>
        </div>
        ${extra}
      </div>
      <div class="card">
        <h3>状态速览</h3>
        <div class="viz-wrap">${radarSVG(store.draft.state, true)}</div>
      </div>
    </div>`;
}

/* Profile reads as rendered Markdown; “编辑” swaps in the raw source, and the
 * change only reaches the profile file once 确认修改 is pressed. */
function profileCard() {
  if (!store.profileEditing) {
    return `<div class="card">
      <h3>叙事 Profile
        <button type="button" id="editProfileBtn" class="mini-btn">编辑</button></h3>
      <div class="profile-md md-body" data-empty="尚无 profile 文本——点“编辑”开始撰写。">${renderMarkdown(store.draft.profile_text)}</div>
    </div>`;
  }
  return `<div class="card">
    <h3>叙事 Profile（Markdown）</h3>
    <label class="field"><span>确认后写回 profile 文件</span>
      <textarea data-profile-edit style="min-height:220px">${esc(store.profileEdit)}</textarea></label>
    <div class="confirm-bar">
      <span class="confirm-hint">编辑 Markdown 源码，确认后写入</span>
      <button type="button" id="cancelProfileBtn" class="button">取消</button>
      <button type="button" id="confirmProfileBtn" class="button primary">确认修改</button>
    </div>
  </div>`;
}

async function confirmProfile() {
  if (store.creating || store.currentId == null) return;
  try {
    foot("保存 Profile…");
    await api(`/api/agents/${store.currentId}/profile`, {
      method: "POST", body: JSON.stringify({ text: store.profileEdit }),
    });
    store.draft.profile_text = store.profileEdit;
    if (store.detail) store.detail.profile_text = store.profileEdit;
    store.profileEditing = false;
    foot("Profile 已写入", "ok");
    renderStep();
  } catch (err) {
    foot("Profile 保存失败：" + err.message, "err");
  }
}

function stepState() {
  const st = store.draft.state;
  const rows = STATE_VARS.map((v) => `
    <div class="slider-row" data-var="${v.key}">
      <div class="slabel"><span>${v.cn} <span class="en">${v.en}</span></span><span class="val">${st[v.key].toFixed(2)}</span></div>
      <input type="range" min="0" max="1" step="0.01" value="${st[v.key]}" data-state="${v.key}">
      <div class="poles"><span>${v.lo}</span><span>${v.hi}</span></div>
    </div>`).join("");
  return `
    <h2 class="section-title">状态 · 性格</h2>
    <p class="section-note">九个归一化 [0,1] 状态变量——GAWorld 的“性格与内在状态”。拖动即时更新雷达，调整后点“确认修改”写入 CSV 与 profile。</p>
    <div class="cols side">
      <div class="card">${rows}
        <div class="confirm-bar">
          <span class="confirm-hint" id="stateHint">${store.stateDirty ? "有未确认的修改" : "与已保存的设定一致"}</span>
          <button type="button" id="confirmStateBtn" class="button primary"${store.stateDirty ? "" : " disabled"}>确认修改</button>
        </div>
      </div>
      <div class="card"><h3>状态雷达</h3><div class="viz-wrap" id="bigRadar">${radarSVG(st, true)}</div></div>
    </div>`;
}

function markStateDirty() {
  store.stateDirty = true;
  const hint = $("#stateHint");
  if (hint) hint.textContent = "有未确认的修改";
  const btn = $("#confirmStateBtn");
  if (btn) btn.disabled = false;
}

async function confirmState() {
  if (!(await save())) return;
  store.stateDirty = false;
  const hint = $("#stateHint");
  if (hint) hint.textContent = "已确认并写入";
  const btn = $("#confirmStateBtn");
  if (btn) btn.disabled = true;
}

const KIND_LABELS = { hobby: "兴趣", skill: "技能" };
const COG_LABELS = {
  skill_breadth: "技能广度", deliverable_capacity: "产出能力", growth_level: "成长水平",
  memory_volume: "记忆积累", external_knowledge: "外部知识",
};

function chips(arr, cls = "") {
  return (arr && arr.length)
    ? `<div class="chips">${arr.map((s) => `<span class="chip ${cls}">${esc(s)}</span>`).join("")}</div>`
    : "";
}

function growthRows(growth) {
  const items = (growth && growth.items) || [];
  if (!items.length) return `<p class="section-note">尚无成长档案——运行仿真后由 gaworld/interests.py 派生。</p>`;
  return items.map((it) => {
    const practiced = it.total_minutes > 0
      ? `累计 ${it.total_minutes} 分钟 · 连续 ${it.streak_days} 天 · 最近第 ${it.last_practiced_day} 天练习`
      : "尚未开始练习";
    return `<div class="bar-row"><div class="bl">
        <b>${esc(it.name)} <span class="tag">${KIND_LABELS[it.kind] || esc(it.kind)}</span></b>
        <small>${esc(it.motivation || it.category || "")}</small>
        <small class="growth-change">${practiced}</small></div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.round(clamp01(it.level) * 100)}%"></div></div></div>`;
  }).join("");
}

function stepSkills() {
  const d = store.detail || {};
  const caps = d.capabilities;
  const priv = d.private_skills || [];
  const lib = d.skills || [];
  const cog = d.cognition;

  const capCard = `<div class="card"><h3>能力画像 ${caps && caps.job_label ? `<span class="tag">${esc(caps.job_label)}</span>` : ""}</h3>
    ${caps
      ? `${chips(caps.skills)}${(caps.deliverables || []).length ? `<p class="section-note">可交付物</p>${chips(caps.deliverables)}` : ""}
         ${caps.notes ? `<p class="section-note">${esc(caps.notes)}</p>` : ""}`
      : `<p class="section-note">能力画像未生成——运行仿真后从 output/work/capabilities.json 读取。</p>`}</div>`;
  const privCard = `<div class="card"><h3>私有技能 <span class="tag">${priv.length} 项</span></h3>
    ${priv.length
      ? priv.map((s) => `<div class="bar-row"><div class="bl"><b>${esc(s.title)}</b><small>${esc(s.file)} · 经验蒸馏</small></div></div>`).join("")
      : `<p class="section-note">尚无私有技能——仿真中按经验蒸馏生成。</p>`}</div>`;
  const libCard = `<div class="card"><h3>全局技能库 <span class="tag">${lib.length} 项</span></h3>
    ${lib.length ? chips(lib.map((s) => s.title)) : `<p class="section-note">技能库为空（data/skills）。</p>`}</div>`;
  const cogCard = `<div class="card"><h3>认知指数</h3>
    ${cog
      ? `<div class="cog-score">${cog.score}</div>
         ${Object.keys(COG_LABELS).map((key) => `
           <div class="bar-row"><div class="bl"><b>${COG_LABELS[key]}</b></div>
           <div class="bar-track"><div class="bar-fill" style="width:${Math.round(clamp01(cog.components[key]) * 100)}%"></div></div></div>`).join("")}
         <p class="section-note">由技能 / 成长 / 记忆 / 外部知识派生的透明指数（60–140），非测量智商。</p>`
      : `<p class="section-note">加载后显示。</p>`}</div>`;
  return `
    <h2 class="section-title">能力 · 技能</h2>
    <p class="section-note">能力画像与技能来自仿真产出；兴趣与成长实时读取 agent 成长档案（level / 练习时长 / 连续天数）。</p>
    <div class="cols two">
      <div>${capCard}<div class="card"><h3>兴趣与成长 <span class="tag">${((d.growth || {}).items || []).length} 项</span></h3>${growthRows(d.growth)}</div></div>
      <div>${cogCard}${privCard}${libCard}</div>
    </div>`;
}

/* ---------- memory (step 4) ---------- */
const MEMORY_GROUPS = [
  { key: "long", label: "长期记忆", color: "#385866" },
  { key: "rag", label: "外部知识", color: "#d6a81e" },
  { key: "habit", label: "习惯", color: "#13795b" },
  { key: "intent", label: "意图", color: "#17211d" },
  { key: "sched", label: "日程", color: "#7a8b80" },
];
const INTENT_LABELS = {
  priorities: "优先事项", avoidances: "回避", target_social: "社交目标",
  target_recovery: "恢复目标", growth_focus: "成长焦点",
};
const PHASE_LABELS = { morning: "上午", afternoon: "下午", evening: "傍晚", night: "夜间" };

/** Strip the [额外信息…] tag and the trailing bigram keyword tail. */
function memoryBody(text) {
  return String(text || "").replace(/^\[额外信息[^\]]*\]\s*/, "").split("关键词:")[0].trim();
}
function preview(text, n = 16) {
  const t = String(text || "").trim();
  return t.length > n ? t.slice(0, n) + "…" : t;
}

/** Turn the detail payload's memory bodies into graph groups + list rows. */
function memoryGroups() {
  const mem = (store.detail && store.detail.memory) || {};
  const long = [], rag = [];
  (mem.long_term || []).forEach((item) => {
    const body = memoryBody(item.text) || item.text;
    (item.rag ? rag : long).push({ title: preview(body), text: body });
  });
  const habit = (mem.habits || []).map((h) => ({
    title: preview(h.activity || h.key),
    text: `${PHASE_LABELS[h.phase] || h.phase || ""} · ${h.activity || h.key}\n倾向动作：${h.preferred_action || "—"}\n强度 ${clamp01(h.strength).toFixed(2)}${h.last_updated_day == null ? "" : ` · 第 ${h.last_updated_day} 天更新`}`,
  }));
  const intent = [];
  Object.keys(mem.intentions || {}).forEach((key) => {
    const value = mem.intentions[key];
    (Array.isArray(value) ? value : [value]).filter(Boolean).forEach((v) => {
      intent.push({ title: preview(String(v)), text: `${INTENT_LABELS[key] || key}：${v}` });
    });
  });
  const sched = (mem.schedule || []).map((s) => ({
    title: `${s.time} ${preview(s.activity, 8)}`,
    text: `${s.time} · ${s.activity}`,
  }));
  const byKey = { long, rag, habit, intent, sched };
  return MEMORY_GROUPS.map((g) => Object.assign({}, g, { items: byKey[g.key] || [] }));
}

/** Radial graph: agent at the centre, one hub per memory kind, items as leaves. */
function memoryGraphSVG(groups, size, maxLeaves) {
  const cx = size / 2, cy = size / 2;
  const active = groups.filter((g) => g.items.length);
  const nodes = [];
  if (!active.length) {
    return { svg: `<svg viewBox="0 0 ${size} ${size}"><text x="${cx}" y="${cy}" font-size="${size / 20}" fill="#5c6860" text-anchor="middle">尚无记忆</text></svg>`, nodes, hidden: 0 };
  }
  const hubR = size * 0.23, leafRa = size * 0.36, leafRb = size * 0.44;
  const leafSize = size > 400 ? 5.5 : 3.6;
  let edges = "", hubs = "", dots = "", labels = "";
  let hidden = 0;
  active.forEach((g, gi) => {
    const a0 = (-90 + (gi * 360) / active.length) * (Math.PI / 180);
    const hx = cx + Math.cos(a0) * hubR, hy = cy + Math.sin(a0) * hubR;
    edges += `<line x1="${cx}" y1="${cy}" x2="${hx.toFixed(1)}" y2="${hy.toFixed(1)}" stroke="#cbd7cd" stroke-width="1.2"/>`;
    const shown = g.items.slice(0, maxLeaves);
    hidden += g.items.length - shown.length;
    const span = ((Math.PI * 2) / active.length) * 0.8;
    shown.forEach((item, li) => {
      const t = shown.length === 1 ? 0.5 : li / (shown.length - 1);
      const a = a0 - span / 2 + span * t;
      const r = li % 2 ? leafRb : leafRa;
      const x = cx + Math.cos(a) * r, y = cy + Math.sin(a) * r;
      const idx = nodes.length;
      nodes.push({ title: item.title, text: item.text, group: g.label, color: g.color });
      edges += `<line x1="${hx.toFixed(1)}" y1="${hy.toFixed(1)}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="#e0e8e0" stroke-width="1"/>`;
      dots += `<circle class="mem-node" data-node="${idx}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${leafSize}" fill="${g.color}"><title>${esc(item.title)}</title></circle>`;
    });
    hubs += `<circle class="mem-hub" cx="${hx.toFixed(1)}" cy="${hy.toFixed(1)}" r="${leafSize * 1.7}" fill="#fff" stroke="${g.color}" stroke-width="2"/>`;
    // Label rides the clear band between the hub and its leaves, with a white
    // halo so it stays legible where it crosses a spoke.
    const lr = (hubR + leafRa) / 2;
    labels += `<text x="${(cx + Math.cos(a0) * lr).toFixed(1)}" y="${(cy + Math.sin(a0) * lr).toFixed(1)}" font-size="${size / 26}" fill="${g.color}" text-anchor="middle" stroke="#fff" stroke-width="3" paint-order="stroke">${g.label} ${g.items.length}</text>`;
  });
  const centre = `<circle cx="${cx}" cy="${cy}" r="${leafSize * 1.3}" fill="#17211d"/>`;
  return {
    svg: `<svg viewBox="0 0 ${size} ${size}" class="mem-graph">${edges}${dots}${hubs}${centre}${labels}</svg>`,
    nodes,
    hidden,
  };
}

function memoryNodeInfo(node) {
  if (!node) return `<p class="section-note">点击图谱节点查看该条记忆的完整内容。</p>`;
  return `<span class="chip" style="border-color:${node.color};color:${node.color}">${esc(node.group)}</span>
    <p class="mem-node-text">${esc(node.text)}</p>`;
}

function memoryListCard(title, count, rowsHTML, emptyNote) {
  return `<div class="card"><h3>${title} <span class="tag">${count}</span></h3>
    ${count ? `<div class="mem-list">${rowsHTML}</div>` : `<p class="section-note">${emptyNote}</p>`}</div>`;
}

function stepMemory() {
  const d = store.detail || {};
  const c = d.memory_counts || { long_term: 0, habits: 0, intentions: 0, schedule: 0 };
  const mem = d.memory || {};
  const total = c.long_term + c.habits + c.intentions + c.schedule;
  const groups = memoryGroups();
  store.memGraph = memoryGraphSVG(groups, 260, 10);
  const pick = store.memPick == null ? null : store.memGraph.nodes[store.memPick];

  const longRows = (mem.long_term || []).slice().reverse().map((item) =>
    `<div class="mem-row${item.rag ? " is-rag" : ""}"><span class="mem-idx">#${item.index}</span>
      <span class="mem-text">${esc(memoryBody(item.text) || item.text)}</span></div>`).join("");
  const habitRows = (mem.habits || []).map((h) =>
    `<div class="bar-row"><div class="bl"><b>${esc(h.activity || h.key)} <span class="tag">${PHASE_LABELS[h.phase] || esc(h.phase)}</span></b>
      <small>${esc(h.preferred_action || "—")}${h.last_updated_day == null ? "" : ` · 第 ${h.last_updated_day} 天更新`}</small></div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.round(clamp01(h.strength) * 100)}%"></div></div></div>`).join("");
  const intentRows = Object.keys(mem.intentions || {}).map((key) => {
    const value = mem.intentions[key];
    const list = (Array.isArray(value) ? value : [value]).filter(Boolean);
    if (!list.length) return "";
    return `<div class="mem-row"><span class="mem-idx">${esc(INTENT_LABELS[key] || key)}</span>
      <span class="mem-text">${list.map((v) => esc(String(v))).join("、")}</span></div>`;
  }).join("");
  const schedRows = (mem.schedule || []).map((s) =>
    `<div class="mem-row"><span class="mem-idx">${esc(s.time)}</span><span class="mem-text">${esc(s.activity)}</span></div>`).join("");

  return `
    <h2 class="section-title">记忆</h2>
    <p class="section-note">分层记忆：长期记忆 / 习惯 / 意图 / 日程，读自 output/memory，随仿真积累，也可在此手动补写。</p>
    <div class="cols side">
      <div class="card">
        <div class="stat-grid">
          <div class="stat"><div class="n">${c.long_term}</div><div class="l">长期记忆</div></div>
          <div class="stat"><div class="n">${c.habits}</div><div class="l">习惯</div></div>
          <div class="stat"><div class="n">${Object.keys(mem.intentions || {}).length || c.intentions}</div><div class="l">意图</div></div>
          <div class="stat"><div class="n">${c.schedule}</div><div class="l">日程</div></div>
        </div>
        <p class="section-note" style="margin-top:14px">${total ? "该居民已有记忆痕迹。" : "尚无记忆——运行仿真后此处填充，或在下方手动添加。"}</p>
      </div>
      <div class="card"><h3>记忆图谱
          <button type="button" id="memZoomBtn" class="mini-btn" title="放大查看">⤢ 放大</button></h3>
        <div class="viz-wrap" id="memGraphBox">${store.memGraph.svg}</div>
        ${store.memGraph.hidden ? `<p class="section-note">图中每类最多显示 10 个节点，另有 ${store.memGraph.hidden} 个在放大视图中查看。</p>` : ""}
        <div class="mem-node-info" id="memNodeInfo">${memoryNodeInfo(pick)}</div>
      </div>
    </div>
    <div class="card">
      <h3>手动添加记忆 / RAG</h3>
      ${field("类型", `<select id="memKind"><option value="memory">长期记忆</option><option value="rag">外部 RAG 知识</option></select>`)}
      <label class="field"><span>内容</span>
        <textarea id="memText" placeholder="例如：上个月在武林街道租房被中介多收了一笔费用，之后对中介很警惕。"></textarea></label>
      <div class="confirm-bar">
        <span class="confirm-hint">长期记忆直接写入 agent_${store.currentId == null ? "N" : store.currentId}.json；RAG 会加上 [额外信息 | 来源:manual] 前缀，并在向量库已建立时同步索引。</span>
        <button type="button" id="addMemBtn" class="button primary"${store.creating ? " disabled" : ""}>写入记忆</button>
      </div>
    </div>
    ${memoryListCard("长期记忆", (mem.long_term || []).length, longRows, "尚无长期记忆。")}
    ${memoryListCard("习惯", (mem.habits || []).length, habitRows, "尚无习惯——仿真中由重复行为固化。")}
    ${memoryListCard("意图", Object.keys(mem.intentions || {}).length, intentRows, "尚无意图档案。")}
    ${memoryListCard("日程", (mem.schedule || []).length, schedRows, "尚无日程。")}
    ${ragCard(d.rag)}`;
}

function openMemoryModal() {
  const built = memoryGraphSVG(memoryGroups(), 640, 30);
  store.memGraphBig = built;
  const box = document.createElement("div");
  box.className = "mem-modal";
  box.id = "memModal";
  box.innerHTML = `<div class="mem-modal-box">
      <div class="mem-modal-head"><h3>记忆图谱</h3>
        <button type="button" class="mini-btn" id="memModalClose" aria-label="关闭">✕</button></div>
      <div class="mem-modal-body">
        <div class="mem-modal-graph">${built.svg}</div>
        <div class="mem-modal-info" id="memModalInfo">${memoryNodeInfo(null)}</div>
      </div></div>`;
  box.addEventListener("click", (ev) => {
    if (ev.target === box || ev.target.closest("#memModalClose")) { closeMemoryModal(); return; }
    const dot = ev.target.closest("[data-node]");
    if (dot) $("#memModalInfo").innerHTML = memoryNodeInfo(built.nodes[Number(dot.dataset.node)]);
  });
  document.body.appendChild(box);
  document.addEventListener("keydown", memoryModalKeys);
}

function memoryModalKeys(ev) {
  if (ev.key === "Escape") closeMemoryModal();
}

function closeMemoryModal() {
  const box = $("#memModal");
  if (box) box.remove();
  document.removeEventListener("keydown", memoryModalKeys);
}

async function addMemory() {
  if (store.creating || store.currentId == null) { foot("请先保存居民再添加记忆", "err"); return; }
  const kind = $("#memKind").value;
  const text = ($("#memText").value || "").trim();
  if (!text) { foot("请输入记忆内容", "err"); return; }
  try {
    foot("写入记忆…");
    const res = await api(`/api/agents/${store.currentId}/memory`, {
      method: "POST", body: JSON.stringify({ kind, text }),
    });
    store.detail.memory = Object.assign({}, store.detail.memory, { long_term: res.long_term || [] });
    store.detail.rag = res.rag;
    store.detail.memory_counts = Object.assign({}, store.detail.memory_counts, { long_term: res.count });
    store.memPick = null;
    renderStep();
    foot(kind === "rag" ? "已写入外部 RAG 知识" : "已写入长期记忆", "ok");
  } catch (err) {
    foot("写入失败：" + err.message, "err");
  }
}

function ragCard(rag) {
  const items = (rag && rag.items) || [];
  const body = items.length
    ? items.slice(0, 8).map((t) => `<p class="rag-item">${esc(t.split("关键词:")[0].trim())}</p>`).join("")
    : `<p class="section-note">尚无外部注入知识——[额外信息] 记忆由 external_rag 引导或运行时检索写入。</p>`;
  return `<div class="card"><h3>外部 RAG 知识 <span class="tag">${(rag && rag.count) || 0} 条</span></h3>${body}</div>`;
}

const TIER_LABELS = { inner: "亲密", close: "挚友", acquaintance: "熟人", weak: "弱连接" };
const ROLE_LABELS = {
  mother: "母亲", father: "父亲", parent: "父母", sibling: "兄弟姐妹", grandparent: "祖辈", relative: "亲戚",
  spouse: "配偶", partner: "伴侣", child: "子女", best_friend: "挚友", close_friend: "好友", friend: "朋友",
  classmate: "同学", coworker: "同事", boss: "上司", subordinate: "下属", mentor: "导师", client: "客户",
  neighbor: "邻居", online_friend: "网友", acquaintance: "熟人", old_friend: "旧友", former_coworker: "前同事", ex: "前任",
};
const roleLabel = (r) => ROLE_LABELS[r] || r || "关系";

const TIER_RINGS = [
  { key: "inner", r: 34, cap: 5, c: "#13795b" },
  { key: "close", r: 58, cap: 15, c: "#385866" },
  { key: "acquaintance", r: 84, cap: 50, c: "#d6a81e" },
  { key: "weak", r: 110, cap: 150, c: "#cbd7cd" },
];

function cloneRelations(social) {
  return ((social && social.relations) || []).map((r) => ({
    id: r.id, name: r.name, role: r.role, kind: r.kind, tier: r.tier,
    closeness: clamp01(r.closeness), trust: clamp01(r.trust),
  }));
}

function relationRef(el) {
  const arr = store.socialDraft;
  return Array.isArray(arr) ? arr[Number(el.dataset.idx)] : null;
}

function dunbarSVG(relations) {
  const counts = { inner: 0, close: 0, acquaintance: 0, weak: 0 };
  relations.forEach((r) => { if (counts[r.tier] != null) counts[r.tier] += 1; });
  let rings = "", labels = "";
  TIER_RINGS.slice().reverse().forEach((t) => {
    rings += `<circle cx="130" cy="130" r="${t.r}" fill="none" stroke="${t.c}" stroke-width="1.4"/>`;
  });
  TIER_RINGS.forEach((t) => {
    labels += `<text x="130" y="${130 - t.r + 12}" font-size="9" fill="#5c6860" text-anchor="middle">${TIER_LABELS[t.key]} · ${counts[t.key]}/${t.cap}</text>`;
  });
  let people = `<circle cx="130" cy="130" r="6" fill="#17211d"/>`;
  TIER_RINGS.forEach((t) => {
    const arr = relations.filter((r) => r.tier === t.key).slice(0, 24);
    arr.forEach((r, j) => {
      const a = (j / Math.max(1, arr.length)) * Math.PI * 2;
      people += `<circle cx="${(130 + Math.cos(a) * t.r).toFixed(1)}" cy="${(130 + Math.sin(a) * t.r).toFixed(1)}" r="2.8" fill="${t.c}"><title>${esc(r.name)} · ${esc(roleLabel(r.role))}</title></circle>`;
    });
  });
  return `<svg viewBox="0 0 260 260">${rings}${people}${labels}</svg>`;
}

function relationEditorRow(r, idx) {
  const attrs = `data-idx="${idx}"`;
  const roleOptions = Object.keys(ROLE_LABELS).map((k) =>
    `<option value="${k}"${r.role === k ? " selected" : ""}>${ROLE_LABELS[k]}</option>`).join("");
  const unknownRole = r.role && !ROLE_LABELS[r.role]
    ? `<option value="${esc(r.role)}" selected>${esc(r.role)}</option>` : "";
  const tierOptions = TIER_RINGS.map((t) =>
    `<option value="${t.key}"${r.tier === t.key ? " selected" : ""}>${TIER_LABELS[t.key]}</option>`).join("");
  const bar = (field, label) => `<label class="goal-mini goal-prog"><span>${label} <b class="val">${r[field].toFixed(2)}</b></span>
    <input type="range" min="0" max="1" step="0.01" value="${r[field]}" data-rel-${field} ${attrs}></label>`;
  return `<div class="goal-edit">
    <div class="goal-edit-head">
      <input class="goal-title-input" data-rel-name ${attrs} value="${esc(r.name)}" placeholder="姓名">
      <button type="button" class="goal-remove" data-rel-remove ${attrs} title="删除此关系" aria-label="删除">✕</button>
    </div>
    <div class="goal-edit-controls">
      <label class="goal-mini"><span>关系</span><select data-rel-role ${attrs}>${unknownRole}${roleOptions}</select></label>
      <label class="goal-mini"><span>圈层</span><select data-rel-tier ${attrs}>${tierOptions}</select></label>
      ${bar("closeness", "亲密度")}
      ${bar("trust", "信任")}
    </div>
  </div>`;
}

/* ---------------------------------------------------------------------------
 * 家庭（step 5）
 *
 * Households are re-derived from (roster, config, seed) at the start of every
 * run, so an edit made here cannot be a mutation of the result — it would be
 * erased the next time the simulation started. What the panel writes is an
 * *override*: `data/family_overrides.json`, which the assigner consults while
 * assigning. That is why every save comes back with a fresh preview rather
 * than an "已保存" toast: the question worth answering is what this agent's
 * family will actually be next run, including the knock-on effects on whoever
 * they were pinned to.
 * ------------------------------------------------------------------------- */

const MARITAL_LABELS = { never: "未婚", married: "已婚", divorced: "离异", widowed: "丧偶" };
const HH_TYPE_LABELS = {
  single: "独居", shared: "合租", with_parents: "与父母同住", cohabit: "未婚同居",
  couple: "夫妻二人", nuclear: "核心家庭", single_parent: "单亲家庭", multigen: "三代同堂",
};
const ELDER_ROLE_LABELS = { mother: "母亲", father: "父亲", parent: "父母", grandparent: "祖辈" };

function blankFamilyDraft(override) {
  const src = override && typeof override === "object" ? override : {};
  const partner = src.partner;
  let partnerMode = "auto";
  if ("partner" in src) partnerMode = partner === null ? "none" : (partner.kind === "agent" ? "agent" : "ghost");
  return {
    marital_status: src.marital_status || "",
    partnerMode,
    partnerRole: (partner && partner.role) || "spouse",
    partnerAgentId: partner && partner.kind === "agent" ? Number(partner.agent_id) : null,
    partnerGhost: partner && partner.kind === "ghost"
      ? { name: partner.name || "", gender: partner.gender || "女", age: Number(partner.age) || 30 }
      : { name: "", gender: "女", age: 30 },
    children: Array.isArray(src.children) ? src.children.map(clonePerson) : null,
    elders: Array.isArray(src.elders) ? src.elders.map(clonePerson) : null,
    note: src.note || "",
  };
}

function clonePerson(p) {
  return {
    name: p.name || "", gender: p.gender || "男",
    age: Number(p.age) || 0, coresident: p.coresident !== false,
    role: p.role || "",
  };
}

/* Draft -> the wire shape `normalize_override` validates. The tri-state on
 * children/elders is load-bearing: `null` means "sample it", `[]` means
 * "pinned to none" — an operator saying this couple has no children. */
function familyDraftToOverride(d) {
  const out = {};
  if (d.marital_status) out.marital_status = d.marital_status;
  if (d.partnerMode === "none") out.partner = null;
  else if (d.partnerMode === "agent" && d.partnerAgentId != null) {
    out.partner = { kind: "agent", agent_id: Number(d.partnerAgentId), role: d.partnerRole };
  } else if (d.partnerMode === "ghost") {
    out.partner = {
      kind: "ghost", role: d.partnerRole, name: d.partnerGhost.name,
      gender: d.partnerGhost.gender, age: Number(d.partnerGhost.age) || 0, coresident: true,
    };
  }
  if (d.children) out.children = d.children;
  if (d.elders) out.elders = d.elders;
  if (d.note) out.note = d.note;
  return out;
}

async function loadFamilyPreview() {
  if (store.creating || store.currentId == null) { store.familyPreview = null; return; }
  try {
    const payload = await api(`/api/family/preview?agent_id=${store.currentId}`);
    store.familyPreview = payload;
    store.familyDraft = blankFamilyDraft(payload.override);
  } catch (err) {
    store.familyPreview = { error: err.message };
    store.familyDraft = blankFamilyDraft(null);
  }
}

function personRow(person, idx, kind) {
  const attrs = `data-fam-kind="${kind}" data-idx="${idx}"`;
  const genderOpts = ["男", "女"].map((g) =>
    `<option value="${g}"${person.gender === g ? " selected" : ""}>${g}</option>`).join("");
  const roleSelect = kind === "elders"
    ? `<label class="goal-mini"><span>身份</span><select data-fam-role ${attrs}>${
        Object.keys(ELDER_ROLE_LABELS).map((r) =>
          `<option value="${r}"${person.role === r ? " selected" : ""}>${ELDER_ROLE_LABELS[r]}</option>`).join("")
      }</select></label>`
    : "";
  return `<div class="goal-edit">
    <div class="goal-edit-head">
      <input class="goal-title-input" data-fam-name ${attrs} value="${esc(person.name)}" placeholder="姓名">
      <button type="button" class="goal-remove" data-fam-remove ${attrs} title="删除" aria-label="删除">✕</button>
    </div>
    <div class="goal-edit-controls">
      <label class="goal-mini"><span>性别</span><select data-fam-gender ${attrs}>${genderOpts}</select></label>
      <label class="goal-mini"><span>年龄</span><input type="number" min="0" max="120" data-fam-age ${attrs} value="${Number(person.age) || 0}"></label>
      ${roleSelect}
      <label class="goal-mini goal-check"><span>同住</span>
        <input type="checkbox" data-fam-coresident ${attrs}${person.coresident ? " checked" : ""}></label>
    </div>
  </div>`;
}

function personGroup(kind, title, hint) {
  const list = store.familyDraft[kind];
  const manual = Array.isArray(list);
  const body = manual
    ? `${list.map((p, i) => personRow(p, i, kind)).join("") || `<p class="section-note">已固定为「没有」。</p>`}
       <button type="button" class="goal-add" data-fam-add="${kind}">+ 新增</button>`
    : `<p class="section-note">${esc(hint)}</p>`;
  return `<div class="fam-group">
    <label class="fam-toggle">
      <input type="checkbox" data-fam-manual="${kind}"${manual ? " checked" : ""}>
      <b>${esc(title)}</b><span class="section-note">${manual ? "手动指定" : "自动生成"}</span>
    </label>
    ${body}
  </div>`;
}

function familyPartnerBlock(candidates) {
  const d = store.familyDraft;
  const modes = [
    ["auto", "自动"], ["none", "无伴侣"], ["agent", "仿真内居民"], ["ghost", "场外人物"],
  ].map(([v, label]) =>
    `<label class="fam-radio"><input type="radio" name="famPartnerMode" value="${v}"${
      d.partnerMode === v ? " checked" : ""}> ${label}</label>`).join("");
  const roleSel = `<label class="goal-mini"><span>关系</span><select data-fam-partner-role>
      <option value="spouse"${d.partnerRole === "spouse" ? " selected" : ""}>配偶</option>
      <option value="partner"${d.partnerRole === "partner" ? " selected" : ""}>同居伴侣</option>
    </select></label>`;
  let detail = "";
  if (d.partnerMode === "agent") {
    const opts = (candidates || []).map((c) =>
      `<option value="${c.agent_id}"${Number(d.partnerAgentId) === Number(c.agent_id) ? " selected" : ""}>${
        esc(c.name)} · ${c.age}岁 · ${esc(c.gender)}${c.residence ? " · " + esc(c.residence) : ""}</option>`).join("");
    detail = `<div class="goal-edit-controls">
      <label class="goal-mini"><span>选择居民</span><select data-fam-partner-agent>
        <option value="">— 请选择 —</option>${opts}</select></label>
      ${roleSel}
    </div>
    <p class="section-note">双向生效：对方的家庭也会随之改变，两人共享同一个住处；原本和对方配对的居民会自动退回场外配偶。</p>`;
  } else if (d.partnerMode === "ghost") {
    detail = `<div class="goal-edit-controls">
      <label class="goal-mini"><span>姓名</span><input data-fam-partner-name value="${esc(d.partnerGhost.name)}" placeholder="场外配偶姓名"></label>
      <label class="goal-mini"><span>性别</span><select data-fam-partner-gender>
        ${["男", "女"].map((g) => `<option value="${g}"${d.partnerGhost.gender === g ? " selected" : ""}>${g}</option>`).join("")}
      </select></label>
      <label class="goal-mini"><span>年龄</span><input type="number" min="0" max="120" data-fam-partner-age value="${Number(d.partnerGhost.age) || 0}"></label>
      ${roleSel}
    </div>`;
  } else if (d.partnerMode === "none") {
    detail = `<p class="section-note">固定为没有伴侣——即使婚姻状态抽样结果是已婚，也不会生成配偶。</p>`;
  } else {
    detail = `<p class="section-note">按婚姻状态与配对规则自动决定。</p>`;
  }
  return `<div class="fam-group"><b>伴侣</b>
    <div class="fam-radios">${modes}</div>${detail}</div>`;
}

function familyCard() {
  if (store.creating) {
    return `<div class="card"><h3>家庭</h3>
      <p class="section-note">新建居民保存后，才能编辑家庭。</p></div>`;
  }
  const preview = store.familyPreview;
  if (!preview) {
    return `<div class="card"><h3>家庭</h3><p class="section-note">加载中…</p></div>`;
  }
  if (preview.error) {
    return `<div class="card"><h3>家庭</h3>
      <p class="section-note">家庭预览不可用：${esc(preview.error)}</p></div>`;
  }
  const sel = preview.selected || {};
  const d = store.familyDraft;
  const statusOpts = [["", "自动（按年龄段抽样）"]].concat(
    Object.keys(MARITAL_LABELS).map((k) => [k, MARITAL_LABELS[k]])
  ).map(([v, label]) =>
    `<option value="${v}"${d.marital_status === v ? " selected" : ""}>${label}</option>`).join("");

  const tags = `<span class="tag">${esc(MARITAL_LABELS[sel.marital_status] || "?")}</span>
    <span class="tag">${esc(HH_TYPE_LABELS[sel.household_type] || sel.household_type || "?")}</span>
    <span class="tag${sel.pinned ? " tag-pinned" : ""}">${sel.pinned ? "已固定" : "自动生成"}</span>`;

  const duties = preview.duties || {};
  const dutyList = (arr, label) =>
    (arr && arr.length)
      ? `<li><b>${label}</b>：${arr.map(esc).join("；")}</li>`
      : `<li><b>${label}</b>：无</li>`;

  const warnings = (preview.warnings || []).length
    ? `<p class="fam-warn">${preview.warnings.map(esc).join("<br>")}</p>` : "";

  return `<div class="card">
    <h3>家庭 <span class="tag">${esc(sel.household_id || "")}</span></h3>
    <p class="section-note">家庭在每次运行开始时按「配置 → 家庭与户」重新生成。这里的修改保存为
      <code>data/family_overrides.json</code> 里的覆盖项，跨运行生效，并优先于抽样结果。</p>
    ${warnings}
    <div class="fam-head">${tags}</div>
    <p class="fam-brief">${esc(sel.brief || "（无家庭）")}</p>
    <ul class="fam-duties">${dutyList(duties.weekday, "工作日")}${dutyList(duties.weekend, "周末")}</ul>

    <div class="fam-group"><b>婚姻状态</b>
      <div class="goal-edit-controls">
        <label class="goal-mini"><span>状态</span><select data-fam-status>${statusOpts}</select></label>
      </div>
    </div>
    ${familyPartnerBlock(preview.candidates)}
    ${personGroup("children", "子女", "按生育率旋钮自动生成。勾选后可精确指定每个孩子。")}
    ${personGroup("elders", "同住长辈", "按共居规则自动生成。勾选后可精确指定同住的长辈。")}

    <div class="goals-save">
      <button type="button" id="resetFamilyBtn" class="button">恢复自动生成</button>
      <button type="button" id="saveFamilyBtn" class="button primary">保存并预览</button>
    </div>
  </div>`;
}

async function saveFamilyOverride(clear) {
  if (store.creating || store.currentId == null) return;
  try {
    foot(clear ? "恢复自动生成…" : "保存家庭设定…");
    const body = clear
      ? { agent_id: store.currentId, clear: true }
      : { agent_id: store.currentId, override: familyDraftToOverride(store.familyDraft) };
    const payload = await api("/api/family/override", { method: "POST", body: JSON.stringify(body) });
    store.familyPreview = payload;
    store.familyDraft = blankFamilyDraft(payload.override);
    renderStep();
    foot(clear ? "已恢复为自动生成，下次运行生效" : "家庭设定已保存，下次运行生效", "ok");
  } catch (err) {
    foot((clear ? "恢复失败：" : "保存失败：") + err.message, "err");
  }
}

function bindFamilyCard() {
  const body = $("#stepBody");
  if (!body || !store.familyDraft) return;
  const d = store.familyDraft;

  const status = body.querySelector("[data-fam-status]");
  if (status) status.addEventListener("change", () => { d.marital_status = status.value; });

  body.querySelectorAll('input[name="famPartnerMode"]').forEach((el) => {
    el.addEventListener("change", () => { d.partnerMode = el.value; renderStep(); });
  });
  const partnerAgent = body.querySelector("[data-fam-partner-agent]");
  if (partnerAgent) partnerAgent.addEventListener("change", () => {
    d.partnerAgentId = partnerAgent.value ? Number(partnerAgent.value) : null;
  });
  const partnerRole = body.querySelector("[data-fam-partner-role]");
  if (partnerRole) partnerRole.addEventListener("change", () => { d.partnerRole = partnerRole.value; });
  const gName = body.querySelector("[data-fam-partner-name]");
  if (gName) gName.addEventListener("input", () => { d.partnerGhost.name = gName.value; });
  const gGender = body.querySelector("[data-fam-partner-gender]");
  if (gGender) gGender.addEventListener("change", () => { d.partnerGhost.gender = gGender.value; });
  const gAge = body.querySelector("[data-fam-partner-age]");
  if (gAge) gAge.addEventListener("input", () => { d.partnerGhost.age = Number(gAge.value) || 0; });

  body.querySelectorAll("[data-fam-manual]").forEach((el) => {
    el.addEventListener("change", () => {
      const kind = el.dataset.famManual;
      d[kind] = el.checked ? (d[kind] || []) : null;
      renderStep();
    });
  });
  body.querySelectorAll("[data-fam-add]").forEach((el) => {
    el.addEventListener("click", () => {
      const kind = el.dataset.famAdd;
      d[kind] = d[kind] || [];
      d[kind].push(kind === "children"
        ? { name: "", gender: "男", age: 6, coresident: true, role: "child" }
        : { name: "", gender: "女", age: 68, coresident: true, role: "mother" });
      renderStep();
    });
  });
  const personRef = (el) => {
    const list = d[el.dataset.famKind];
    return Array.isArray(list) ? list[Number(el.dataset.idx)] : null;
  };
  body.querySelectorAll("[data-fam-name]").forEach((el) => {
    el.addEventListener("input", () => { const p = personRef(el); if (p) p.name = el.value; });
  });
  body.querySelectorAll("[data-fam-gender]").forEach((el) => {
    el.addEventListener("change", () => { const p = personRef(el); if (p) p.gender = el.value; });
  });
  body.querySelectorAll("[data-fam-age]").forEach((el) => {
    el.addEventListener("input", () => { const p = personRef(el); if (p) p.age = Number(el.value) || 0; });
  });
  body.querySelectorAll("[data-fam-role]").forEach((el) => {
    el.addEventListener("change", () => { const p = personRef(el); if (p) p.role = el.value; });
  });
  body.querySelectorAll("[data-fam-coresident]").forEach((el) => {
    el.addEventListener("change", () => { const p = personRef(el); if (p) p.coresident = el.checked; });
  });
  body.querySelectorAll("[data-fam-remove]").forEach((el) => {
    el.addEventListener("click", () => {
      const list = d[el.dataset.famKind];
      if (Array.isArray(list)) list.splice(Number(el.dataset.idx), 1);
      renderStep();
    });
  });

  const save = $("#saveFamilyBtn");
  if (save) save.addEventListener("click", () => saveFamilyOverride(false));
  const reset = $("#resetFamilyBtn");
  if (reset) reset.addEventListener("click", () => saveFamilyOverride(true));
}

function stepSocial() {
  const social = store.detail && store.detail.social;
  const relations = store.socialDraft || [];
  const note = store.creating
    ? "新建居民保存并运行仿真后生成关系边。"
    : (social
      ? `已加载 ${social.count} 条真实关系边（output/memory），可直接编辑。`
      : "尚无关系文件——在此新增的关系会创建 agent_" + store.currentId + "_relationships.json。");
  const editor = store.creating
    ? `<p class="section-note">新建模式下暂不能编辑关系。</p>`
    : `${relations.map(relationEditorRow).join("")}
       <button type="button" class="goal-add" id="addRelBtn">+ 新增关系</button>
       <div class="goals-save"><button type="button" id="saveRelBtn" class="button primary">保存关系</button></div>`;
  return `
    <h2 class="section-title">社交 · 关系</h2>
    <p class="section-note">Dunbar 分层社交圈（inner/close/acquaintance/weak）。${note}</p>
    <div class="cols side">
      <div class="card"><h3>关系分层</h3><div class="viz-wrap" id="dunbarViz">${dunbarSVG(relations)}</div></div>
      <div class="card"><h3>影响倾向</h3>${["voice_propensity", "platform_dependence"].map((key) => {
        const v = STATE_VARS.find((x) => x.key === key), val = store.draft.state[key];
        return `<div class="bar-row"><div class="bl"><b>${v.cn}</b><small>${v.lo} → ${v.hi}</small></div><div class="bar-track"><div class="bar-fill" style="width:${Math.round(val * 100)}%"></div></div></div>`;
      }).join("")}<p class="section-note" style="margin-top:10px">社交网络密度、同质性等在仿真中演化。</p></div>
    </div>
    <div class="card"><h3>关系与亲密度 <span class="tag">${relations.length}</span></h3>${editor}</div>
    ${familyCard()}`;
}

async function saveRelations() {
  if (store.creating || store.currentId == null || !store.socialDraft) return;
  const blank = store.socialDraft.find((r) => !String(r.name || "").trim());
  if (blank) { foot("请先填写每条关系的姓名", "err"); return; }
  try {
    foot("保存关系…");
    const saved = await api(`/api/agents/${store.currentId}/relationships`, {
      method: "POST",
      body: JSON.stringify({ relations: store.socialDraft, removed: store.socialRemoved }),
    });
    store.detail.social = saved;
    store.socialDraft = cloneRelations(saved);
    store.socialRemoved = [];
    renderStep();
    foot("关系已保存到 relationships.json", "ok");
  } catch (err) {
    foot("关系保存失败：" + err.message, "err");
  }
}

const GOAL_STATUS_LABELS = { active: "进行中", completed: "已完成", abandoned: "已放弃", paused: "已暂停" };
const GOAL_DOMAIN_LABELS = { career: "事业", family: "家庭", health: "健康", wealth: "财富", social: "社交", self: "自我" };
// Active-goal caps per tier — mirror DEFAULT_GOALS_CONFIG in gaworld/goals.py
// (POST /goals normalizes with defaults, so these must match to avoid surprise truncation).
const GOAL_LIMITS = { life_goals: 2, long_term_goals: 3, short_term_goals: 4 };
const GOAL_ID_PREFIX = { life_goals: "lg", long_term_goals: "ltg", short_term_goals: "stg" };
const GOAL_TIERS = [
  { key: "life_goals", label: "人生方向", domain: true, progress: false },
  { key: "long_term_goals", label: "长期目标", domain: false, progress: true },
  { key: "short_term_goals", label: "短期目标", domain: false, progress: true },
];

function cloneGoals(goals) {
  const src = goals && typeof goals === "object" ? goals : {};
  const out = JSON.parse(JSON.stringify(src));
  GOAL_TIERS.forEach(({ key }) => { if (!Array.isArray(out[key])) out[key] = []; });
  return out;
}

function goalRef(el) {
  const arr = store.goalsDraft && store.goalsDraft[el.dataset.tier];
  return Array.isArray(arr) ? arr[Number(el.dataset.idx)] : null;
}

function addGoal(tier) {
  if (!store.goalsDraft) return;
  const goal = { id: `${GOAL_ID_PREFIX[tier]}_${++store.goalSeq}`, title: "", status: "active" };
  if (tier === "life_goals") { goal.domain = "self"; goal.description = ""; }
  else { goal.parent = ""; goal.progress = 0; }
  (store.goalsDraft[tier] = store.goalsDraft[tier] || []).push(goal);
}

function goalRows(goals) {
  const tiers = ["life_goals", "long_term_goals", "short_term_goals"];
  const hasAny = goals && tiers.some((k) => (goals[k] || []).length);
  if (!hasAny) return `<p class="section-note">尚无目标档案——运行仿真后由 gaworld/goals.py 从 profile 引导生成，或经 dashboard 编辑写入。</p>`;
  const life = (goals.life_goals || []).filter((g) => g.status === "active");
  const lifeHtml = life.length ? `<p class="section-note">人生方向</p>${chips(life.map((g) => g.title))}` : "";
  const tier = (items, label) => {
    if (!(items || []).length) return "";
    const rows = items.map((g) => {
      const pct = Math.round(clamp01(g.progress || 0) * 100);
      const status = g.status && g.status !== "active" ? ` <span class="tag">${GOAL_STATUS_LABELS[g.status] || esc(g.status)}</span>` : "";
      const sub = [
        g.target_day != null ? `目标 Day ${g.target_day}` : (g.horizon_days != null ? `${g.horizon_days} 天视野` : ""),
        g.recent_note || "",
      ].filter(Boolean).join(" · ");
      return `<div class="bar-row"><div class="bl"><b>${esc(g.title)}${status}</b><small>${esc(sub)}</small></div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div></div>`;
    }).join("");
    return `<p class="section-note">${label}</p>${rows}`;
  };
  const lastReview = (goals.review_log || []).slice(-1)[0] || null;
  const reviewHtml = lastReview
    ? `<p class="section-note growth-change">最近回顾 · Day ${Number(lastReview.day) || 0}：${esc(lastReview.summary || "")}</p>`
    : "";
  return lifeHtml + tier(goals.long_term_goals, "长期目标") + tier(goals.short_term_goals, "短期目标") + reviewHtml;
}

function goalEditorRow(tier, idx, g, meta) {
  const attrs = `data-tier="${tier}" data-idx="${idx}"`;
  const statusSel = `<label class="goal-mini"><span>状态</span>
    <select data-goal-status ${attrs}>${Object.keys(GOAL_STATUS_LABELS).map((k) =>
      `<option value="${k}"${(g.status || "active") === k ? " selected" : ""}>${GOAL_STATUS_LABELS[k]}</option>`).join("")}</select></label>`;
  const domainSel = meta.domain
    ? `<label class="goal-mini"><span>领域</span>
        <select data-goal-domain ${attrs}>${Object.keys(GOAL_DOMAIN_LABELS).map((k) =>
          `<option value="${k}"${(g.domain || "self") === k ? " selected" : ""}>${GOAL_DOMAIN_LABELS[k]}</option>`).join("")}</select></label>`
    : "";
  const pct = Math.round(clamp01(g.progress || 0) * 100);
  const progress = meta.progress
    ? `<label class="goal-mini goal-prog"><span>进度 <b class="val">${pct}%</b></span>
        <input type="range" min="0" max="100" step="1" value="${pct}" data-goal-progress ${attrs}></label>`
    : "";
  return `<div class="goal-edit">
    <div class="goal-edit-head">
      <input class="goal-title-input" data-goal-title ${attrs} value="${esc(g.title)}" placeholder="目标标题">
      <button type="button" class="goal-remove" data-goal-remove ${attrs} title="删除此目标" aria-label="删除">✕</button>
    </div>
    <div class="goal-edit-controls">${domainSel}${progress}${statusSel}</div>
  </div>`;
}

function goalsEditorHtml(goals) {
  const tiers = GOAL_TIERS.map((meta) => {
    const items = goals[meta.key] || [];
    const rows = items.map((g, idx) => goalEditorRow(meta.key, idx, g, meta)).join("");
    const activeCount = items.filter((g) => (g.status || "active") === "active").length;
    const atLimit = activeCount >= GOAL_LIMITS[meta.key];
    const addBtn = `<button type="button" class="goal-add" data-goal-add data-tier="${meta.key}"${atLimit ? ` disabled title="进行中的${meta.label}最多 ${GOAL_LIMITS[meta.key]} 个"` : ""}>+ 新增${meta.label}</button>`;
    return `<div class="goal-tier"><p class="section-note">${meta.label}</p>${rows}${addBtn}</div>`;
  }).join("");
  const lastReview = (goals.review_log || []).slice(-1)[0] || null;
  const reviewHtml = lastReview
    ? `<p class="section-note growth-change">最近回顾 · Day ${Number(lastReview.day) || 0}：${esc(lastReview.summary || "")}</p>`
    : "";
  return `${tiers}${reviewHtml}<div class="goals-save"><button type="button" id="saveGoalsBtn" class="button primary">保存目标</button></div>`;
}

function stepBehavior() {
  const st = store.draft.state;
  const rows = BEHAVIOR_KEYS.map((key) => {
    const v = STATE_VARS.find((x) => x.key === key);
    return `<div class="slider-row" data-var="${key}">
      <div class="slabel"><span>${v.cn} <span class="en">${v.en}</span></span><span class="val">${st[key].toFixed(2)}</span></div>
      <input type="range" min="0" max="1" step="0.01" value="${st[key]}" data-state="${key}">
      <div class="poles"><span>${v.lo}</span><span>${v.hi}</span></div></div>`;
  }).join("");
  return `
    <h2 class="section-title">行为 · 目标</h2>
    <p class="section-note">驱动行为选择的状态维度：流动、表达、风险、平台绑定、政策敏感。</p>
    <div class="cols side">
      <div class="card"><h3>行为倾向</h3>${rows}</div>
      <div class="card"><h3>三层目标 <span class="tag">人生 · 长期 · 短期</span></h3>
        ${store.creating
          ? goalRows((store.detail || {}).goals)
          : goalsEditorHtml(store.goalsDraft || cloneGoals(null))}
        <p class="section-note">${store.creating
          ? "新建居民保存后，目标将由 gaworld/goals.py 从 profile 引导生成，可再回此编辑。"
          : "目标可在此直接编辑，「保存目标」写入 goals.json；仿真运行时会每日推进、每周回顾。"}</p>
      </div>
    </div>`;
}

/* ---------- finance (step 7) ---------- */
const FINANCE_ACCOUNTS = [
  { key: "checking", label: "活期 / 现金" },
  { key: "savings", label: "存款" },
  { key: "investment", label: "投资" },
  { key: "housing_fund", label: "公积金" },
];
const FINANCE_AMOUNTS = [
  { key: "gross_monthly_salary", label: "税前月薪" },
  { key: "net_monthly_salary", label: "税后月薪" },
  { key: "monthly_rent", label: "月租" },
  { key: "debt", label: "负债" },
];
const FINANCE_RATES = [
  { key: "engel_coefficient", label: "恩格尔系数" },
  { key: "savings_rate", label: "储蓄率" },
];
// Liquid accounts only — mirrors _total_balance in gaworld/economy/finance.py.
const FINANCE_LIQUID = ["checking", "savings", "investment"];

function cloneFinance(fin) {
  if (!fin) return null;
  const accounts = fin.accounts || {};
  const out = { accounts: {} };
  FINANCE_ACCOUNTS.forEach((a) => (out.accounts[a.key] = Number(accounts[a.key]) || 0));
  FINANCE_AMOUNTS.concat(FINANCE_RATES).forEach((f) => (out[f.key] = Number(fin[f.key]) || 0));
  return out;
}

function financeBalance(draft) {
  return FINANCE_LIQUID.reduce((sum, key) => sum + (Number(draft.accounts[key]) || 0), 0);
}

function financeCard() {
  const fin = store.detail && store.detail.finance_state;
  if (!fin) {
    return `<div class="card"><h3>财务</h3><p class="section-note">运行仿真后从 output/memory 的 economy 状态生成，届时可在此修改存款等。</p></div>`;
  }
  if (!fin.editable || !store.financeDraft) {
    return `<div class="card"><h3>财务快照（run 产出，只读）</h3><div class="review-list">
        <div><span class="k">余额</span><span class="v">${fin.balance}</span></div>
        <div><span class="k">净月薪</span><span class="v">${fin.net_monthly_salary}</span></div>
        <div><span class="k">恩格尔系数</span><span class="v">${fin.engel_coefficient}</span></div>
        <div><span class="k">储蓄率</span><span class="v">${fin.savings_rate}</span></div></div>
      <p class="section-note">该居民尚无 agent_${store.currentId}_economy.json 活状态，跑一次仿真后即可编辑。</p></div>`;
  }
  const d = store.financeDraft;
  const money = (list) => list.map((f) => `<label class="field"><span>${f.label}（${esc(fin.currency)}）</span>
    <input type="number" step="0.01" min="0" value="${(f.key in d ? d[f.key] : d.accounts[f.key])}" data-fin="${f.key}"></label>`).join("");
  const rates = FINANCE_RATES.map((f) => `<label class="field"><span>${f.label} <b class="val">${d[f.key].toFixed(2)}</b></span>
    <input type="range" min="0" max="1" step="0.01" value="${d[f.key]}" data-fin-rate="${f.key}"></label>`).join("");
  return `<div class="card">
    <h3>财务 <span class="tag">可编辑</span></h3>
    <p class="section-note">写入 agent_${store.currentId}_economy.json —— 仿真下次以有状态模式启动时读取。余额 = 活期 + 存款 + 投资（不含公积金）。</p>
    <div class="grid2">${money(FINANCE_ACCOUNTS)}</div>
    <div class="grid2">${money(FINANCE_AMOUNTS)}</div>
    <div class="grid2">${rates}</div>
    <div class="confirm-bar">
      <span class="confirm-hint">合计余额 <b id="finBalance">${financeBalance(d).toFixed(2)}</b> ${esc(fin.currency)}</span>
      <button type="button" id="saveFinBtn" class="button primary">保存财务</button>
    </div></div>`;
}

async function saveFinance() {
  if (store.creating || store.currentId == null || !store.financeDraft) return;
  try {
    foot("保存财务…");
    const saved = await api(`/api/agents/${store.currentId}/finance`, {
      method: "POST", body: JSON.stringify(store.financeDraft),
    });
    store.detail.finance_state = saved;
    store.financeDraft = cloneFinance(saved);
    renderStep();
    foot("财务已保存到 economy 状态", "ok");
  } catch (err) {
    foot("财务保存失败：" + err.message, "err");
  }
}

function stepReview() {
  const i = store.draft.identity, st = store.draft.state;
  const idRows = [["姓名", i.name], ["性别", i.gender], ["年龄", i.age], ["户籍", i.hukou], ["居住地", i.residence]]
    .map(([k, v]) => `<div><span class="k">${k}</span><span class="v">${esc(v)}</span></div>`).join("");
  const stRows = STATE_VARS.map((v) => `<div><span class="k">${v.cn}</span><span class="v">${st[v.key].toFixed(2)}</span></div>`).join("");
  const finCard = financeCard();
  return `
    <h2 class="section-title">复核 · 部署</h2>
    <p class="section-note">${store.creating ? "确认后创建新居民（写入 CSV + profile）。" : "确认后保存改动并可直接投入仿真。"}</p>
    ${agentCardBlock(store.detail)}
    <div class="cols two">
      <div class="card"><h3>身份</h3><div class="review-list">${idRows}</div></div>
      <div class="card"><h3>状态变量</h3><div class="review-list">${stRows}</div></div>
    </div>
    ${finCard}
    <div class="card">
      <h3>采访预览（可选）</h3>
      <label class="field"><span>问一个问题（调用 LLM，可能较慢）</span>
        <input id="interviewQ" placeholder="例如：你怎么看最近的落户政策？"></label>
      <button id="interviewBtn" class="button" ${store.creating ? "disabled" : ""}>开始采访</button>
      <div class="interview-out" id="interviewOut" hidden></div>
    </div>
    <div class="deploy-actions">
      <button id="saveBtn2" class="button primary">${store.creating ? "创建居民" : "保存改动"}</button>
      <button id="runBtn2" class="button steel" ${store.creating ? "disabled" : ""}>用此居民运行仿真</button>
    </div>`;
}

function agentCardBlock(detail) {
  if (!detail || !detail.agent_card) return "";
  const card = detail.agent_card;
  const oc = detail.openclaw || {};
  const cog = detail.cognition;
  const ocChip = oc.connected
    ? `<span class="chip ok">🦞 已连接 OpenClaw</span>`
    : `<span class="chip">🦞 未连接 OpenClaw</span>`;
  const ocLine = oc.connected
    ? `<small class="muted-line">${oc.is_openclaw_agent ? "外部 OpenClaw 智能体" : "与 OpenClaw 智能体互通"} · 集群 ${esc(oc.cluster || "—")} · 发出 ${oc.messages_sent} / 收到 ${oc.messages_received} 条消息</small>`
    : `<small class="muted-line">未在 relay 中检测到 OpenClaw 往来（scripts/openclaw_bridge.py 可接入）。</small>`;
  return `<div class="card"><h3>Agent Card <span class="tag">${esc(card.schema)}</span></h3>
    <div class="ac-head"><b>${esc(card.name)}</b> <span class="tag">#${esc(card.id)}</span>
      ${card.job_label ? `<span class="tag">${esc(card.job_label)}</span>` : ""}
      ${ocChip}${cog ? `<span class="chip">认知指数 ${cog.score}</span>` : ""}</div>
    <small class="muted-line">${esc(card.description)}</small>
    ${card.skills.length ? `<p class="section-note">技能</p>${chips(card.skills)}` : ""}
    ${card.interests.length ? `<p class="section-note">兴趣</p>${chips(card.interests)}` : ""}
    ${card.deliverables.length ? `<p class="section-note">可交付物</p>${chips(card.deliverables)}` : ""}
    ${ocLine}
    <small class="muted-line">API：${esc(card.endpoints.detail)}</small></div>`;
}

/* ---------- step event binding ---------- */
function bindStep() {
  $("#stepBody").querySelectorAll("[data-idt]").forEach((el) => {
    el.addEventListener("input", () => {
      const key = el.dataset.idt;
      store.draft.identity[key] = key === "age" ? Number(el.value) : el.value;
      renderSubject();
    });
  });
  const pEdit = $("#stepBody").querySelector("[data-profile-edit]");
  if (pEdit) pEdit.addEventListener("input", () => { store.profileEdit = pEdit.value; });
  const pBtn = $("#editProfileBtn");
  if (pBtn) pBtn.addEventListener("click", () => {
    store.profileEdit = store.draft.profile_text;
    store.profileEditing = true;
    renderStep();
  });
  const pCancel = $("#cancelProfileBtn");
  if (pCancel) pCancel.addEventListener("click", () => {
    store.profileEditing = false;
    renderStep();
  });
  const pOk = $("#confirmProfileBtn"); if (pOk) pOk.addEventListener("click", confirmProfile);
  $("#stepBody").querySelectorAll("[data-nar]").forEach((el) => {
    el.addEventListener("input", () => { store.draft.narrative[el.dataset.nar] = el.value; });
  });
  $("#stepBody").querySelectorAll("[data-state]").forEach((el) => {
    el.addEventListener("input", () => {
      const key = el.dataset.state;
      store.draft.state[key] = clamp01(el.value);
      const row = el.closest(".slider-row");
      if (row) row.querySelector(".val").textContent = store.draft.state[key].toFixed(2);
      const big = $("#bigRadar"); if (big) big.innerHTML = radarSVG(store.draft.state, true);
      renderSubject();
      markStateDirty();
    });
  });
  const cs = $("#confirmStateBtn"); if (cs) cs.addEventListener("click", confirmState);
  $("#stepBody").querySelectorAll("[data-goal-title]").forEach((el) => {
    el.addEventListener("input", () => { const g = goalRef(el); if (g) g.title = el.value; });
  });
  $("#stepBody").querySelectorAll("[data-goal-progress]").forEach((el) => {
    el.addEventListener("input", () => {
      const g = goalRef(el); if (!g) return;
      g.progress = clamp01(Number(el.value) / 100);
      const box = el.closest(".goal-prog"), val = box && box.querySelector(".val");
      if (val) val.textContent = Math.round(g.progress * 100) + "%";
    });
  });
  $("#stepBody").querySelectorAll("[data-goal-domain]").forEach((el) => {
    el.addEventListener("change", () => { const g = goalRef(el); if (g) g.domain = el.value; });
  });
  $("#stepBody").querySelectorAll("[data-goal-status]").forEach((el) => {
    el.addEventListener("change", () => { const g = goalRef(el); if (g) { g.status = el.value; renderStep(); } });
  });
  $("#stepBody").querySelectorAll("[data-goal-remove]").forEach((el) => {
    el.addEventListener("click", () => {
      const arr = store.goalsDraft && store.goalsDraft[el.dataset.tier];
      if (Array.isArray(arr)) { arr.splice(Number(el.dataset.idx), 1); renderStep(); }
    });
  });
  $("#stepBody").querySelectorAll("[data-goal-add]").forEach((el) => {
    el.addEventListener("click", () => { addGoal(el.dataset.tier); renderStep(); });
  });
  const sg = $("#saveGoalsBtn"); if (sg) sg.addEventListener("click", saveGoals);
  bindMemoryStep();
  bindSocialStep();
  bindFinanceStep();
  const iBtn = $("#interviewBtn"); if (iBtn) iBtn.addEventListener("click", runInterview);
  const s2 = $("#saveBtn2"); if (s2) s2.addEventListener("click", save);
  const r2 = $("#runBtn2"); if (r2) r2.addEventListener("click", runSim);
}

function bindMemoryStep() {
  const zoom = $("#memZoomBtn"); if (zoom) zoom.addEventListener("click", openMemoryModal);
  const add = $("#addMemBtn"); if (add) add.addEventListener("click", addMemory);
  const box = $("#memGraphBox");
  if (box) box.addEventListener("click", (ev) => {
    const dot = ev.target.closest("[data-node]");
    if (!dot) return;
    store.memPick = Number(dot.dataset.node);
    $("#memNodeInfo").innerHTML = memoryNodeInfo(store.memGraph.nodes[store.memPick]);
  });
}

function bindSocialStep() {
  // Step 5 can be reached before the (async) preview has landed — or after a
  // failed one. Kick it off lazily, guarded so a failure cannot loop.
  if (!store.creating && store.currentId != null && !store.familyPreview && !store.familyLoading) {
    store.familyLoading = true;
    loadFamilyPreview().finally(() => {
      store.familyLoading = false;
      if (store.step === 5) renderStep();
    });
  }
  bindFamilyCard();
  const redrawRings = () => {
    const viz = $("#dunbarViz");
    if (viz) viz.innerHTML = dunbarSVG(store.socialDraft || []);
  };
  $("#stepBody").querySelectorAll("[data-rel-name]").forEach((el) => {
    el.addEventListener("input", () => { const r = relationRef(el); if (r) { r.name = el.value; redrawRings(); } });
  });
  $("#stepBody").querySelectorAll("[data-rel-role]").forEach((el) => {
    el.addEventListener("change", () => { const r = relationRef(el); if (r) { r.role = el.value; redrawRings(); } });
  });
  $("#stepBody").querySelectorAll("[data-rel-tier]").forEach((el) => {
    el.addEventListener("change", () => { const r = relationRef(el); if (r) { r.tier = el.value; redrawRings(); } });
  });
  ["closeness", "trust"].forEach((fieldName) => {
    $("#stepBody").querySelectorAll(`[data-rel-${fieldName}]`).forEach((el) => {
      el.addEventListener("input", () => {
        const r = relationRef(el); if (!r) return;
        r[fieldName] = clamp01(el.value);
        const val = el.closest(".goal-prog").querySelector(".val");
        if (val) val.textContent = r[fieldName].toFixed(2);
      });
    });
  });
  $("#stepBody").querySelectorAll("[data-rel-remove]").forEach((el) => {
    el.addEventListener("click", () => {
      const idx = Number(el.dataset.idx);
      const removed = (store.socialDraft || []).splice(idx, 1)[0];
      if (removed && removed.id) store.socialRemoved.push(removed.id);
      renderStep();
    });
  });
  const addRel = $("#addRelBtn");
  if (addRel) addRel.addEventListener("click", () => {
    (store.socialDraft = store.socialDraft || []).push({
      id: "", name: "", role: "friend", kind: "ghost", tier: "acquaintance", closeness: 0.3, trust: 0.3,
    });
    renderStep();
  });
  const saveRel = $("#saveRelBtn"); if (saveRel) saveRel.addEventListener("click", saveRelations);
}

function bindFinanceStep() {
  const refreshBalance = () => {
    const box = $("#finBalance");
    if (box) box.textContent = financeBalance(store.financeDraft).toFixed(2);
  };
  $("#stepBody").querySelectorAll("[data-fin]").forEach((el) => {
    el.addEventListener("input", () => {
      const key = el.dataset.fin;
      const value = Math.max(0, Number(el.value) || 0);
      if (key in store.financeDraft.accounts) store.financeDraft.accounts[key] = value;
      else store.financeDraft[key] = value;
      refreshBalance();
    });
  });
  $("#stepBody").querySelectorAll("[data-fin-rate]").forEach((el) => {
    el.addEventListener("input", () => {
      const key = el.dataset.finRate;
      store.financeDraft[key] = clamp01(el.value);
      const val = el.closest(".field").querySelector(".val");
      if (val) val.textContent = store.financeDraft[key].toFixed(2);
    });
  });
  const saveFin = $("#saveFinBtn"); if (saveFin) saveFin.addEventListener("click", saveFinance);
}

/* ---------- actions ---------- */
/** Persist identity + state (and profile text). Returns true when it stuck. */
async function save() {
  if (!store.draft) return false;
  const i = store.draft.identity;
  try {
    foot("保存中…");
    if (store.creating) {
      const body = { name: i.name, gender: i.gender, age: i.age, hukou: i.hukou, residence: i.residence,
        state: store.draft.state, job: store.draft.narrative.job, personality: store.draft.narrative.personality };
      const res = await api("/api/agents", { method: "POST", body: JSON.stringify(body) });
      foot(`已创建居民 #${res.id} ${res.name}`, "ok");
      store.creating = false;
      await loadAgents();
      $("#agentSelect").value = String(res.id);
      await selectAgent(res.id);
      return true;
    }
    await api(`/api/agents/${store.currentId}/state`, { method: "POST", body: JSON.stringify({
      name: i.name, gender: i.gender, age: i.age, hukou: i.hukou, residence: i.residence, state: store.draft.state }) });
    if (store.detail && store.draft.profile_text && store.draft.profile_text !== store.detail.profile_text) {
      await api(`/api/agents/${store.currentId}/profile`, { method: "POST", body: JSON.stringify({ text: store.draft.profile_text }) });
    }
    $("#saveHint").textContent = "已保存 ✓";
    foot("已保存到 CSV / profile", "ok");
    // refresh options label in case name changed
    await loadAgents();
    $("#agentSelect").value = String(store.currentId);
    return true;
  } catch (err) {
    foot("保存失败：" + err.message, "err");
    return false;
  }
}

async function saveGoals() {
  if (store.creating || store.currentId == null || !store.goalsDraft) return;
  try {
    foot("保存目标…");
    const saved = await api(`/api/agents/${store.currentId}/goals`, {
      method: "POST", body: JSON.stringify(store.goalsDraft),
    });
    store.detail = store.detail || {};
    store.detail.goals = saved || {};
    store.goalsDraft = cloneGoals(store.detail.goals);
    renderStep();
    foot("目标已保存到 goals.json", "ok");
  } catch (err) {
    foot("目标保存失败：" + err.message, "err");
  }
}

async function runSim() {
  if (store.creating || store.currentId == null) { foot("请先保存居民再运行", "err"); return; }
  try {
    foot("提交运行…");
    await api("/api/run/start", { method: "POST", body: JSON.stringify({ config: { agent_ids: [store.currentId] } }) });
    foot(`已用居民 #${store.currentId} 启动仿真（在控制台查看日志）`, "ok");
  } catch (err) { foot("运行失败：" + err.message, "err"); }
}

async function runInterview() {
  const q = ($("#interviewQ") && $("#interviewQ").value || "").trim();
  const out = $("#interviewOut");
  if (!q) { foot("请输入采访问题", "err"); return; }
  out.hidden = false; out.textContent = "采访中（可能需要几十秒）…";
  try {
    const res = await api("/api/interview", { method: "POST", body: JSON.stringify({ agent_id: store.currentId, questions: [q] }) });
    out.textContent = (res.stdout || res.stderr || "无输出").trim();
  } catch (err) { out.textContent = "采访失败：" + err.message; }
}

/* ---------- wire up ---------- */
function init() {
  document.querySelectorAll(".step").forEach((b) => b.addEventListener("click", () => {
    store.step = Number(b.dataset.step); renderStep();
  }));
  $("#agentSelect").addEventListener("change", (e) => selectAgent(e.target.value).catch((err) => foot(err.message, "err")));
  $("#newAgentBtn").addEventListener("click", startCreate);
  $("#saveBtn").addEventListener("click", save);
  $("#runBtn").addEventListener("click", runSim);

  loadAgents()
    .then(() => store.currentId != null ? selectAgent(store.currentId) : renderStep())
    .catch((err) => foot("加载失败：" + err.message, "err"));
}

document.addEventListener("DOMContentLoaded", init);
