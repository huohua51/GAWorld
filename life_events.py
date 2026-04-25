import json
import os
import re
import time
import uuid
from contextlib import contextmanager

from config import CONFIG


DEFAULT_LIFE_EVENT_CONFIG = {
    "enabled": True,
    "event_dir": "output/life_events",
    "events_file": "events.json",
}

LIFE_EVENT_TEMPLATES = [
    {
        "key": "illness",
        "title": "突然生病",
        "description": "身体突然不适，出现发热、乏力或疼痛，需要重新安排当天计划。",
        "severity": 0.70,
        "impact_tags": ["health", "stress", "routine"],
        "state_effects": {
            "emotion": -0.08,
            "stress": 0.14,
            "fatigue_debt": 0.12,
            "self_control": -0.06,
        },
    },
    {
        "key": "lottery",
        "title": "意外中奖",
        "description": "意外中了一笔奖金，短期内对金钱、风险和未来计划产生强烈影响。",
        "severity": 0.80,
        "impact_tags": ["money", "emotion", "risk"],
        "state_effects": {
            "emotion": 0.16,
            "stress": -0.08,
            "econ_security": 0.18,
            "risk_preference": 0.08,
        },
    },
    {
        "key": "framed",
        "title": "被人陷害",
        "description": "被卷入一场误会或恶意指控，需要解释、求助或处理声誉风险。",
        "severity": 0.86,
        "impact_tags": ["conflict", "trust", "stress"],
        "state_effects": {
            "emotion": -0.14,
            "stress": 0.18,
            "voice_propensity": 0.10,
            "self_control": -0.08,
        },
    },
    {
        "key": "promotion",
        "title": "升职机会",
        "description": "获得一个重要的升职、项目负责或职业跃迁机会，需要投入更多精力。",
        "severity": 0.64,
        "impact_tags": ["career", "time_pressure", "emotion"],
        "state_effects": {
            "emotion": 0.08,
            "stress": 0.07,
            "econ_security": 0.08,
            "time_pressure": 0.12,
        },
    },
    {
        "key": "family_emergency",
        "title": "家中急事",
        "description": "家人突然需要帮助，当前安排被迫让位给家庭责任。",
        "severity": 0.75,
        "impact_tags": ["family", "obligation", "routine"],
        "state_effects": {
            "emotion": -0.05,
            "stress": 0.16,
            "time_pressure": 0.12,
            "social_need": 0.08,
        },
    },
    {
        "key": "relationship_break",
        "title": "关系破裂",
        "description": "与重要朋友、伴侣或同事发生严重冲突，信任感和日常节奏受到冲击。",
        "severity": 0.78,
        "impact_tags": ["relationship", "conflict", "emotion"],
        "state_effects": {
            "emotion": -0.16,
            "stress": 0.14,
            "social_need": 0.10,
            "self_control": -0.06,
        },
    },
]

_TEMPLATES_BY_KEY = {item["key"]: item for item in LIFE_EVENT_TEMPLATES}

STATE_EFFECT_KEYS = {
    "emotion",
    "stress",
    "econ_security",
    "city_identity",
    "policy_sensitivity",
    "platform_dependence",
    "risk_preference",
    "voice_propensity",
    "mobility_intent",
    "energy",
    "hunger",
    "social_need",
    "fatigue_debt",
    "self_control",
    "time_pressure",
    "stance_score",
    "toxicity_score",
    "misinformation_risk",
    "cross_viewpoint_exposure",
    "intervention_reward",
}


def life_event_config(config=None):
    cfg = dict(DEFAULT_LIFE_EVENT_CONFIG)
    raw = (config or CONFIG).get("life_events", {})
    if isinstance(raw, dict):
        cfg.update(raw)
    return cfg


def life_event_dir(config=None):
    return str(life_event_config(config).get("event_dir") or "output/life_events")


def life_event_path(config=None):
    cfg = life_event_config(config)
    events_file = str(cfg.get("events_file") or "events.json")
    if os.path.isabs(events_file):
        return events_file
    return os.path.join(str(cfg.get("event_dir") or "output/life_events"), events_file)


def life_event_lock_path(config=None):
    return os.path.join(life_event_dir(config), "events.lock")


def _now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def _event_lock(config=None):
    lock_path = life_event_lock_path(config)
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        try:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        try:
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass


def _read_events_unlocked(config=None):
    path = life_event_path(config)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(payload, dict):
        payload = payload.get("events", [])
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _write_events_unlocked(events, config=None):
    path = life_event_path(config)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"events": events}, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _coerce_agent_ids(value):
    if value in (None, "", "all", "*"):
        return []
    if isinstance(value, str):
        value = re.split(r"[,，\s]+", value.strip())
    elif not isinstance(value, (list, tuple, set)):
        value = [value]
    out = []
    seen = set()
    for raw in value:
        if raw in (None, ""):
            continue
        try:
            agent_id = int(raw)
        except (TypeError, ValueError):
            continue
        if agent_id <= 0 or agent_id in seen:
            continue
        seen.add(agent_id)
        out.append(agent_id)
    return out


def _clean_time(value):
    text = str(value or "").strip()
    if re.match(r"^\d{1,2}:\d{2}$", text):
        hh, mm = text.split(":")
        hh_i = int(hh)
        mm_i = int(mm)
        if 0 <= hh_i <= 23 and 0 <= mm_i <= 59:
            return f"{hh_i:02d}:{mm_i:02d}"
    return ""


def _clean_day(value):
    if value in (None, ""):
        return None
    try:
        day = int(value)
    except (TypeError, ValueError):
        return None
    return day if day > 0 else None


def _clean_state_effects(value):
    if not isinstance(value, dict):
        return {}
    effects = {}
    for key, raw in value.items():
        key = str(key).strip()
        if key not in STATE_EFFECT_KEYS:
            continue
        try:
            effects[key] = max(-0.35, min(0.35, float(raw)))
        except (TypeError, ValueError):
            continue
    return effects


def _clean_tags(value):
    if isinstance(value, str):
        value = re.split(r"[,，\s]+", value)
    if not isinstance(value, (list, tuple, set)):
        return []
    out = []
    seen = set()
    for raw in value:
        tag = str(raw or "").strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        out.append(tag[:32])
    return out


def normalize_life_event(payload, current_frame=None):
    payload = payload if isinstance(payload, dict) else {}
    template_key = str(payload.get("template_key") or payload.get("template") or "").strip()
    template = _TEMPLATES_BY_KEY.get(template_key, {})
    title = str(payload.get("title") or template.get("title") or "人生事件").strip()
    description = str(payload.get("description") or template.get("description") or title).strip()
    if not description:
        raise ValueError("事件描述不能为空")
    severity = payload.get("severity", template.get("severity", 0.6))
    try:
        severity = max(0.0, min(1.0, float(severity)))
    except (TypeError, ValueError):
        severity = 0.6

    schedule_mode = str(payload.get("schedule_mode") or payload.get("mode") or "").strip().lower()
    if schedule_mode not in {"immediate", "scheduled"}:
        schedule_mode = "scheduled" if payload.get("day") or payload.get("time") else "immediate"
    day = _clean_day(payload.get("day"))
    event_time = _clean_time(payload.get("time"))
    if schedule_mode == "scheduled" and day is None and isinstance(current_frame, dict):
        day = _clean_day(current_frame.get("day"))
        event_time = event_time or _clean_time(current_frame.get("time"))
    if schedule_mode == "scheduled" and day is None:
        schedule_mode = "immediate"

    state_effects = dict(template.get("state_effects", {}))
    state_effects.update(_clean_state_effects(payload.get("state_effects")))
    return {
        "id": str(payload.get("id") or uuid.uuid4()),
        "status": "pending",
        "template_key": template_key or "custom",
        "title": title[:80],
        "description": description[:1200],
        "severity": severity,
        "scope": "agent",
        "agent_ids": _coerce_agent_ids(payload.get("agent_ids", payload.get("agent_id"))),
        "schedule_mode": schedule_mode,
        "day": day,
        "time": event_time,
        "impact_tags": _clean_tags(payload.get("impact_tags", template.get("impact_tags", []))),
        "state_effects": _clean_state_effects(state_effects),
        "created_at": str(payload.get("created_at") or _now_text()),
        "created_by": str(payload.get("created_by") or "dashboard")[:80],
        "triggered_at": "",
    }


def list_life_event_templates():
    return [dict(item) for item in LIFE_EVENT_TEMPLATES]


def list_life_events(config=None, include_consumed=True):
    with _event_lock(config):
        events = _read_events_unlocked(config)
    if include_consumed:
        return events
    return [item for item in events if item.get("status", "pending") == "pending"]


def add_life_event(payload, config=None, current_frame=None):
    event = normalize_life_event(payload, current_frame=current_frame)
    with _event_lock(config):
        events = _read_events_unlocked(config)
        events.append(event)
        _write_events_unlocked(events, config)
    return event


def _time_to_minutes(value):
    cleaned = _clean_time(value)
    if not cleaned:
        return None
    hh, mm = cleaned.split(":")
    return int(hh) * 60 + int(mm)


def _event_is_due(event, day, time_str):
    if event.get("status", "pending") != "pending":
        return False
    if event.get("schedule_mode") == "immediate":
        return True
    event_day = _clean_day(event.get("day"))
    if event_day is None:
        return True
    if event_day < int(day):
        return True
    if event_day > int(day):
        return False
    event_minutes = _time_to_minutes(event.get("time"))
    current_minutes = _time_to_minutes(time_str)
    if event_minutes is None or current_minutes is None:
        return True
    return event_minutes <= current_minutes


def drain_due_life_events(day, time_str, config=None):
    due = []
    with _event_lock(config):
        events = _read_events_unlocked(config)
        for event in events:
            if _event_is_due(event, day, time_str):
                event["status"] = "consumed"
                event["triggered_day"] = int(day)
                event["triggered_time"] = str(time_str)
                event["triggered_at"] = _now_text()
                due.append(dict(event))
        if due:
            _write_events_unlocked(events, config)
    return due


def life_events_for_agent(events, agent_id):
    agent_id = int(agent_id)
    selected = []
    for event in events or []:
        ids = _coerce_agent_ids(event.get("agent_ids"))
        if not ids or agent_id in ids:
            selected.append(event)
    return selected


def format_life_event(event):
    title = str(event.get("title") or "人生事件").strip()
    desc = str(event.get("description") or "").strip()
    severity = float(event.get("severity", 0.0) or 0.0)
    tags = ", ".join(_clean_tags(event.get("impact_tags")))
    tag_text = f" tags={tags}" if tags else ""
    return f"{title}({severity:.2f})：{desc}{tag_text}".strip()
