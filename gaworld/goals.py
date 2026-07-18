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
