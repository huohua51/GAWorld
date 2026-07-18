"""Goal hierarchy (life / long-term / short-term) for agents.

Data model, JSON persistence, LLM bootstrap with heuristic fallback,
daily progress application, weekly/event reviews, prompt formatting and
episode-salience matching.

Lifecycle is owned by :mod:`gaworld.goals_plugin`; read-side consumers
(intention/routine/diary/interview prompts, salience) stay inline in the
sim — the same interim coupling the interests module uses (see
``gaworld/interests_plugin.py`` module docstring).

Design doc: docs/superpowers/specs/2026-07-18-long-term-goals-design.md
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.goals")

LlmFn = Callable[[str], str]

DEFAULT_GOALS_CONFIG: dict[str, Any] = {
    "enabled": True,
    "review_interval_days": 7,
    "event_review_severity": 0.7,
    "max_life_goals": 2,
    "max_long_term": 3,
    "max_short_term": 4,
    "max_daily_progress_delta": 0.34,
    "review_log_keep": 12,
    "relevance_floor": 0.2,
    "relevance_cap": 0.9,
    "max_reviews_per_day": 20,
}

VALID_STATUS = {"active", "completed", "abandoned", "paused"}
VALID_DOMAINS = {"career", "family", "health", "wealth", "social", "self"}
_TIERS = ("life_goals", "long_term_goals", "short_term_goals")
_ID_PREFIX = {"life_goals": "lg", "long_term_goals": "ltg", "short_term_goals": "stg"}
# Inactive (completed/abandoned) goals kept per tier so files stay bounded.
_MAX_INACTIVE_KEPT = 8


def goals_config(config: dict | None = None) -> dict[str, Any]:
    cfg = dict(DEFAULT_GOALS_CONFIG)
    if isinstance(config, dict):
        cfg.update({k: v for k, v in config.items() if v is not None})
    return cfg


def _clamp(value: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return lo


# ---------------------------------------------------------------------
# Persistence — mirrors gaworld.memory.experience file conventions.
# ---------------------------------------------------------------------

def agent_goals_path(agent_id: Any, memory_dir: str) -> str:
    return os.path.join(memory_dir, f"agent_{int(agent_id)}_goals.json")


def load_agent_goals(agent_id: Any, memory_dir: str) -> dict[str, Any]:
    path = agent_goals_path(agent_id, memory_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        _LOG.warning("goals file unreadable for agent %s; will re-bootstrap", agent_id)
        return {}
    return payload if isinstance(payload, dict) else {}


def save_agent_goals(agent_id: Any, goals: dict[str, Any], memory_dir: str) -> None:
    if not isinstance(goals, dict):
        return
    os.makedirs(memory_dir, exist_ok=True)
    path = agent_goals_path(agent_id, memory_dir)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(goals, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------------
# Parsing & normalization
# ---------------------------------------------------------------------

def parse_goals_json(text: Any) -> dict[str, Any]:
    match = re.search(r"\{.*\}", str(text or ""), re.S)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _norm_goal(item: Any, tier: str, idx: int, day: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    title = str(item.get("title", "")).strip()
    if not title:
        return None
    goal: dict[str, Any] = {
        "id": str(item.get("id", "")).strip() or f"{_ID_PREFIX[tier]}{idx}",
        "title": title,
        "status": item.get("status") if item.get("status") in VALID_STATUS else "active",
    }
    if tier == "life_goals":
        goal["domain"] = item.get("domain") if item.get("domain") in VALID_DOMAINS else "self"
        goal["description"] = str(item.get("description", "")).strip()
        return goal
    goal["parent"] = str(item.get("parent", "")).strip()
    goal["progress"] = _clamp(item.get("progress", 0.0))
    try:
        goal["created_day"] = int(item.get("created_day", day) or day)
        goal["updated_day"] = int(item.get("updated_day", day) or day)
    except (TypeError, ValueError):
        goal["created_day"] = goal["updated_day"] = int(day)
    if tier == "long_term_goals":
        try:
            goal["horizon_days"] = max(30, int(item.get("horizon_days", 180) or 180))
        except (TypeError, ValueError):
            goal["horizon_days"] = 180
    else:
        try:
            goal["target_day"] = int(item.get("target_day", day + 14) or (day + 14))
        except (TypeError, ValueError):
            goal["target_day"] = int(day) + 14
        goal["recent_note"] = str(item.get("recent_note", "")).strip()
    return goal


def normalize_goals(payload: Any, *, config: dict | None = None, day: int = 0) -> dict[str, Any]:
    """Validate/clean a goals payload. Returns {} when nothing valid remains."""
    cfg = goals_config(config)
    if not isinstance(payload, dict):
        return {}
    limits = {
        "life_goals": int(cfg["max_life_goals"]),
        "long_term_goals": int(cfg["max_long_term"]),
        "short_term_goals": int(cfg["max_short_term"]),
    }
    out: dict[str, Any] = {}
    for tier in _TIERS:
        raw = payload.get(tier, [])
        cleaned = []
        for idx, item in enumerate(raw if isinstance(raw, list) else [], start=1):
            goal = _norm_goal(item, tier, idx, day)
            if goal is not None:
                cleaned.append(goal)
        active = [g for g in cleaned if g["status"] == "active"]
        inactive = [g for g in cleaned if g["status"] != "active"]
        out[tier] = active[: limits[tier]] + inactive[-_MAX_INACTIVE_KEPT:]
    if not any(out[tier] for tier in _TIERS):
        return {}
    life_ids = [g["id"] for g in out["life_goals"] if g["status"] == "active"]
    long_ids = [g["id"] for g in out["long_term_goals"] if g["status"] == "active"]
    for g in out["long_term_goals"]:
        if g.get("parent") not in life_ids and life_ids:
            g["parent"] = life_ids[0]
    for g in out["short_term_goals"]:
        if g.get("parent") not in long_ids and long_ids:
            g["parent"] = long_ids[0]
    try:
        out["last_review_day"] = int(payload.get("last_review_day", 0) or 0)
    except (TypeError, ValueError):
        out["last_review_day"] = 0
    out["needs_review"] = bool(payload.get("needs_review", False))
    log = payload.get("review_log", [])
    out["review_log"] = [
        x for x in (log if isinstance(log, list) else []) if isinstance(x, dict)
    ][-int(cfg["review_log_keep"]):]
    return out


# ---------------------------------------------------------------------
# Heuristic fallback — mirrors realism._fallback_intentions in spirit.
# ---------------------------------------------------------------------

def _fallback_goals(agent: dict, *, day: int = 0, config: dict | None = None) -> dict[str, Any]:
    job = str(agent.get("job", ""))
    state = agent.get("state", {}) if isinstance(agent.get("state"), dict) else {}
    econ = _clamp(state.get("econ_security", 0.5), 0.0, 1.0)
    if any(k in job for k in ("退休", "无业", "待业", "失业", "家庭主妇", "家庭主夫")):
        life = {"title": "健康安稳地生活，和家人朋友保持联结", "domain": "health"}
        long_term = {"title": "半年内保持规律作息和身体锻炼", "horizon_days": 180}
        short = {"title": "这两周保持每天散步或锻炼"}
    elif "学生" in job:
        life = {"title": "完成学业并找到自己热爱的方向", "domain": "self"}
        long_term = {"title": "本学期成绩稳步提升", "horizon_days": 120}
        short = {"title": "这两周跟上课程进度并按时完成作业"}
    elif econ < 0.45:
        life = {"title": "让家人过上经济安稳的生活", "domain": "wealth"}
        long_term = {"title": "一年内提高收入稳定性", "horizon_days": 365}
        short = {"title": "这两周控制开支并留意增收机会"}
    else:
        life = {"title": "在事业和生活之间找到平衡", "domain": "career"}
        long_term = {"title": "半年内在主业上有可见的进步", "horizon_days": 180}
        short = {"title": "这两周把手头的主要事务按时推进"}
    payload = {
        "life_goals": [{**life, "id": "lg1", "status": "active", "description": ""}],
        "long_term_goals": [
            {**long_term, "id": "ltg1", "parent": "lg1", "progress": 0.0, "status": "active"}
        ],
        "short_term_goals": [
            {**short, "id": "stg1", "parent": "ltg1", "progress": 0.0,
             "status": "active", "target_day": int(day) + 14}
        ],
    }
    return normalize_goals(payload, config=config, day=day)


# ---------------------------------------------------------------------
# Bootstrap (one LLM call per agent, once; heuristic fallback)
# ---------------------------------------------------------------------

def _build_bootstrap_prompt(agent: dict, cfg: dict) -> str:
    profile_text = "\n".join([
        f"姓名：{agent.get('name', '')}",
        f"年龄：{agent.get('age', '')}",
        f"职业：{agent.get('job', '')}",
        f"性格与情绪特征：{agent.get('personality', '')}",
        f"日常生活与习惯：{agent.get('daily_life', '')}",
        f"价值观与公共事务态度：{agent.get('values', '')}",
    ])
    return f"""
你是城市生活模拟器的“人生规划推导器”。请根据角色资料推导其目标体系。
角色资料：
{profile_text}
当前状态：{json.dumps(agent.get('state', {}), ensure_ascii=False)}
只输出 JSON：
{{
  "life_goals": [{{"title":"...","domain":"career|family|health|wealth|social|self","description":"一句话"}}],
  "long_term_goals": [{{"title":"...","parent_index":1,"horizon_days":365}}],
  "short_term_goals": [{{"title":"...","parent_index":1,"target_day_offset":14}}]
}}
要求：
1) life_goals 1-{cfg['max_life_goals']} 个：方向性的人生追求，符合年龄、职业与价值观。
2) long_term_goals 1-{cfg['max_long_term']} 个：数月尺度、可评估进度；parent_index 指向所属人生目标序号（从1开始）。
3) short_term_goals 2-{cfg['max_short_term']} 个：1-2 周尺度、能直接落到日常安排；parent_index 指向所属长期目标序号。
4) 目标要具体、贴近角色真实生活，不要空洞口号；全部中文短语。
5) 仅输出 JSON，不要其他文字。
"""


def _coerce_bootstrap_payload(payload: dict, *, day: int, config: dict) -> dict[str, Any]:
    life, long_term, short = [], [], []
    for idx, item in enumerate(payload.get("life_goals", []) or [], start=1):
        if isinstance(item, dict):
            life.append({**item, "id": f"lg{idx}", "status": "active"})
    for idx, item in enumerate(payload.get("long_term_goals", []) or [], start=1):
        if not isinstance(item, dict):
            continue
        try:
            parent = int(item.get("parent_index", 1) or 1)
        except (TypeError, ValueError):
            parent = 1
        long_term.append({**item, "id": f"ltg{idx}", "parent": f"lg{parent}",
                          "progress": 0.0, "status": "active"})
    for idx, item in enumerate(payload.get("short_term_goals", []) or [], start=1):
        if not isinstance(item, dict):
            continue
        try:
            parent = int(item.get("parent_index", 1) or 1)
        except (TypeError, ValueError):
            parent = 1
        try:
            offset = int(item.get("target_day_offset", 14) or 14)
        except (TypeError, ValueError):
            offset = 14
        short.append({**item, "id": f"stg{idx}", "parent": f"ltg{parent}",
                      "progress": 0.0, "status": "active",
                      "target_day": int(day) + max(3, offset)})
    return normalize_goals(
        {"life_goals": life, "long_term_goals": long_term, "short_term_goals": short},
        config=config,
        day=day,
    )


def derive_goals(agent: dict, *, llm: LlmFn, day: int = 0, config: dict | None = None) -> dict[str, Any]:
    cfg = goals_config(config)
    try:
        raw = llm(_build_bootstrap_prompt(agent, cfg))
    except Exception as exc:  # noqa: BLE001 - any LLM failure must fall back, never crash the sim
        _LOG.warning("goals bootstrap LLM call failed for agent %s: %s", agent.get("id"), exc)
        raw = ""
    payload = parse_goals_json(raw)
    goals = _coerce_bootstrap_payload(payload, day=day, config=cfg) if payload else {}
    if not goals or not goals.get("short_term_goals"):
        goals = _fallback_goals(agent, day=day, config=cfg)
    return goals


def bootstrap_goals(agents: list, *, llm: LlmFn, memory_dir: str,
                    stateful: bool = True, config: dict | None = None, day: int = 0) -> None:
    """Attach ``agent["goals"]`` for every agent; stored file wins over LLM."""
    cfg = goals_config(config)
    for agent in agents:
        try:
            agent_id = int(agent.get("id", 0) or 0)
        except (TypeError, ValueError):
            continue
        if not agent_id:
            continue
        stored = load_agent_goals(agent_id, memory_dir) if stateful else {}
        goals = normalize_goals(stored, config=cfg, day=day) if stored else {}
        if not goals:
            goals = derive_goals(agent, llm=llm, day=day, config=cfg)
            if stateful:
                save_agent_goals(agent_id, goals, memory_dir)
        agent["goals"] = goals


# ---------------------------------------------------------------------
# Prompt formatting & episode-salience matching (read side, no LLM)
# ---------------------------------------------------------------------

def format_goals_context(goals: Any, *, max_items: int = 8) -> str:
    """Compact goals block for prompts. Short-term/long-term goals carry
    ``[id]`` markers so consolidate_day's ``goal_progress`` can reference them."""
    if not isinstance(goals, dict) or not any(goals.get(t) for t in _TIERS):
        return "无"
    lines: list[str] = []
    life = [g for g in goals.get("life_goals", []) if g.get("status") == "active"]
    if life:
        lines.append("人生方向：" + "；".join(str(g.get("title", "")) for g in life))
    for g in goals.get("long_term_goals", []):
        if g.get("status") != "active":
            continue
        lines.append(
            f"- 长期[{g.get('id')}]：{g.get('title')}（进度 {_clamp(g.get('progress', 0.0)):.0%}）"
        )
    for g in goals.get("short_term_goals", []):
        if g.get("status") != "active":
            continue
        note = f"；最近：{g['recent_note']}" if g.get("recent_note") else ""
        lines.append(
            f"- 短期[{g.get('id')}]：{g.get('title')}"
            f"（进度 {_clamp(g.get('progress', 0.0)):.0%}，目标 Day {g.get('target_day', '?')}{note}）"
        )
    return "\n".join(lines[: max(1, max_items)]) if lines else "无"


def _goal_terms(text: Any) -> list[str]:
    tokens = [t for t in re.split(r"[，。；、！？\s/（）()\[\]]+", str(text or "")) if len(t) >= 2]
    terms = list(tokens)
    # Unsegmented CJK tokens (e.g. a whole goal title) rarely appear verbatim
    # in episode text; add character bigrams so keyword overlap still works.
    for tok in tokens:
        if len(tok) > 2 and re.search(r"[一-鿿]", tok):
            terms.extend(tok[i:i + 2] for i in range(len(tok) - 1))
    return terms


def match_goal_relevance(goals: Any, *texts: Any, config: dict | None = None) -> float:
    """Keyword overlap between active goals and episode text → salience input.

    Returns ``relevance_floor`` (unrelated) .. ``relevance_cap`` (strong
    short-term match). No LLM — same spirit as interests.match_growth_items.
    """
    cfg = goals_config(config)
    floor = float(cfg["relevance_floor"])
    cap = float(cfg["relevance_cap"])
    if not isinstance(goals, dict):
        return floor
    blob = " ".join(str(t or "") for t in texts)
    if not blob.strip():
        return floor
    best = floor
    for tier, weight in (("short_term_goals", 1.0), ("long_term_goals", 0.75), ("life_goals", 0.55)):
        for g in goals.get(tier, []):
            if g.get("status") != "active":
                continue
            terms = _goal_terms(g.get("title")) + _goal_terms(g.get("recent_note"))
            hits = sum(1 for t in terms if t and t in blob)
            if not hits:
                continue
            ratio = min(1.0, hits / max(1, min(len(terms), 3)))
            best = max(best, floor + (cap - floor) * weight * ratio)
    return min(cap, best)
