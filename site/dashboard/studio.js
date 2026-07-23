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
  $("#saveHint").textContent = "已加载 · 自动回填";
  renderSubject();
  renderStep();
}

function startCreate() {
  store.creating = true;
  store.currentId = null;
  store.detail = null;
  store.draft = blankDraft();
  store.goalsDraft = null;
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
    : `<div class="card"><h3>叙事 Profile（Markdown）</h3>
        <label class="field"><span>保存后写回 profile 文件</span>
        <textarea data-idt="profile_text" style="min-height:220px">${esc(store.draft.profile_text)}</textarea></label></div>`;
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
    <p class="section-note">九个归一化 [0,1] 状态变量——GAWorld 的“性格与内在状态”。拖动即时更新雷达。</p>
    <div class="cols side">
      <div class="card">${rows}</div>
      <div class="card"><h3>状态雷达</h3><div class="viz-wrap" id="bigRadar">${radarSVG(st, true)}</div></div>
    </div>`;
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

function stepMemory() {
  const c = (store.detail && store.detail.memory_counts) || { long_term: 0, habits: 0, intentions: 0, schedule: 0 };
  const total = c.long_term + c.habits + c.intentions + c.schedule;
  // dot cloud whose density reflects memory volume
  const n = Math.min(240, 40 + total * 4);
  let dots = "";
  let seed = (store.currentId || 7) * 97 + 13;
  const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
  for (let k = 0; k < n; k++) {
    const a = rnd() * Math.PI * 2, r = Math.sqrt(rnd()) * 96;
    dots += `<circle cx="${(120 + Math.cos(a) * r).toFixed(1)}" cy="${(120 + Math.sin(a) * r).toFixed(1)}" r="${(0.8 + rnd() * 1.6).toFixed(1)}" fill="#385866" opacity="${(0.25 + rnd() * 0.55).toFixed(2)}"/>`;
  }
  return `
    <h2 class="section-title">记忆</h2>
    <p class="section-note">分层记忆：情节 / 语义 / 程序。计数来自 output/memory，随仿真积累。</p>
    <div class="cols side">
      <div class="card">
        <div class="stat-grid">
          <div class="stat"><div class="n">${c.long_term}</div><div class="l">长期记忆</div></div>
          <div class="stat"><div class="n">${c.habits}</div><div class="l">习惯</div></div>
          <div class="stat"><div class="n">${c.intentions}</div><div class="l">意图</div></div>
          <div class="stat"><div class="n">${c.schedule}</div><div class="l">日程</div></div>
        </div>
        <p class="section-note" style="margin-top:14px">${total ? "该居民已有记忆痕迹。" : "尚无记忆——运行仿真后此处填充。"}</p>
      </div>
      <div class="card"><h3>记忆图谱</h3><div class="viz-wrap"><svg viewBox="0 0 240 240">${dots}</svg></div></div>
    </div>
    ${ragCard(store.detail && store.detail.rag)}`;
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

function stepSocial() {
  const social = store.detail && store.detail.social;
  const tiers = [
    { key: "inner", r: 34, cap: 5, c: "#13795b" },
    { key: "close", r: 58, cap: 15, c: "#385866" },
    { key: "acquaintance", r: 84, cap: 50, c: "#d6a81e" },
    { key: "weak", r: 110, cap: 150, c: "#cbd7cd" },
  ];
  const counts = (social && social.tier_counts) || {};
  let rings = "", labels = "";
  tiers.slice().reverse().forEach((t) => { rings += `<circle cx="130" cy="130" r="${t.r}" fill="none" stroke="${t.c}" stroke-width="1.4"/>`; });
  tiers.forEach((t) => {
    const label = social ? `${TIER_LABELS[t.key]} · ${counts[t.key] || 0}/${t.cap}` : `${TIER_LABELS[t.key]} · ${t.cap}`;
    labels += `<text x="130" y="${130 - t.r + 12}" font-size="9" fill="#5c6860" text-anchor="middle">${label}</text>`;
  });
  let people = `<circle cx="130" cy="130" r="6" fill="#17211d"/>`;
  if (social) {
    // place real ties on their tier ring, evenly spaced
    const byTier = {}; tiers.forEach((t) => (byTier[t.key] = []));
    social.relations.forEach((r) => { if (byTier[r.tier]) byTier[r.tier].push(r); });
    tiers.forEach((t) => {
      const arr = byTier[t.key].slice(0, 24);
      arr.forEach((r, j) => {
        const a = (j / Math.max(1, arr.length)) * Math.PI * 2;
        people += `<circle cx="${(130 + Math.cos(a) * t.r).toFixed(1)}" cy="${(130 + Math.sin(a) * t.r).toFixed(1)}" r="2.8" fill="${t.c}"><title>${esc(r.name)} · ${esc(roleLabel(r.role))}</title></circle>`;
      });
    });
  } else {
    let seed = (store.currentId || 3) * 51 + 7;
    const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
    tiers.forEach((t, ti) => { const k = [4, 6, 8, 10][ti]; for (let j = 0; j < k; j++) { const a = rnd() * Math.PI * 2; people += `<circle cx="${(130 + Math.cos(a) * t.r).toFixed(1)}" cy="${(130 + Math.sin(a) * t.r).toFixed(1)}" r="2.6" fill="${t.c}" opacity="0.5"/>`; } });
  }
  const note = social
    ? `已加载 ${social.count} 条真实关系边（output/memory）。`
    : `真实关系边在仿真运行后生成——下方为占位示意。`;
  const rightCard = social && social.relations.length
    ? `<div class="card"><h3>亲密度排序 <span class="tag">${social.count}</span></h3>${
        social.relations.slice(0, 12).map((r) => `
          <div class="bar-row"><div class="bl"><b>${esc(r.name)}</b><small>${esc(roleLabel(r.role))} · ${TIER_LABELS[r.tier] || r.tier}${r.kind === "ghost" ? " · 场外" : ""}</small></div>
          <div class="bar-track"><div class="bar-fill" style="width:${Math.round(r.closeness * 100)}%"></div></div></div>`).join("")
      }</div>`
    : `<div class="card"><h3>影响倾向</h3>${["voice_propensity", "platform_dependence"].map((key) => {
        const v = STATE_VARS.find((x) => x.key === key), val = store.draft.state[key];
        return `<div class="bar-row"><div class="bl"><b>${v.cn}</b><small>${v.lo} → ${v.hi}</small></div><div class="bar-track"><div class="bar-fill" style="width:${Math.round(val * 100)}%"></div></div></div>`;
      }).join("")}<p class="section-note" style="margin-top:10px">社交网络密度、同质性等在仿真中演化。</p></div>`;
  return `
    <h2 class="section-title">社交 · 关系</h2>
    <p class="section-note">Dunbar 分层社交圈（inner/close/acquaintance/weak）。${note}</p>
    <div class="cols side">
      <div class="card"><h3>关系分层</h3><div class="viz-wrap"><svg viewBox="0 0 260 260">${rings}${people}${labels}</svg></div></div>
      ${rightCard}
    </div>`;
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

function stepReview() {
  const i = store.draft.identity, st = store.draft.state;
  const fin = store.detail && store.detail.finance;
  const idRows = [["姓名", i.name], ["性别", i.gender], ["年龄", i.age], ["户籍", i.hukou], ["居住地", i.residence]]
    .map(([k, v]) => `<div><span class="k">${k}</span><span class="v">${esc(v)}</span></div>`).join("");
  const stRows = STATE_VARS.map((v) => `<div><span class="k">${v.cn}</span><span class="v">${st[v.key].toFixed(2)}</span></div>`).join("");
  const finCard = fin
    ? `<div class="card"><h3>财务快照（仿真产出）</h3><div class="review-list">
        <div><span class="k">余额</span><span class="v">${esc(fin.balance)}</span></div>
        <div><span class="k">净月薪</span><span class="v">${esc(fin.net_monthly_salary)}</span></div>
        <div><span class="k">恩格尔系数</span><span class="v">${esc(fin.engel_coefficient)}</span></div>
        <div><span class="k">储蓄率</span><span class="v">${esc(fin.savings_rate)}</span></div></div></div>`
    : `<div class="card"><h3>财务快照</h3><p class="section-note">运行仿真后从 output/economy 生成。</p></div>`;
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
      if (key === "profile_text") { store.draft.profile_text = el.value; return; }
      store.draft.identity[key] = key === "age" ? Number(el.value) : el.value;
      renderSubject();
    });
  });
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
    });
  });
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
  const iBtn = $("#interviewBtn"); if (iBtn) iBtn.addEventListener("click", runInterview);
  const s2 = $("#saveBtn2"); if (s2) s2.addEventListener("click", save);
  const r2 = $("#runBtn2"); if (r2) r2.addEventListener("click", runSim);
}

/* ---------- actions ---------- */
async function save() {
  if (!store.draft) return;
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
      return;
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
  } catch (err) {
    foot("保存失败：" + err.message, "err");
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
