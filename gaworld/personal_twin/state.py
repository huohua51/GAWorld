from __future__ import annotations

from typing import Any


def _compact_text(value: Any, max_chars: int = 160) -> str:
    text = " ".join(str(value or "").split()).strip()
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars].rstrip()
    return text


def build_initial_twin_state(agent: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    twin_cfg = config if isinstance(config, dict) else {}
    tags = list((agent.get("public_profile", {}) or {}).get("tags", []))[:3]
    return {
        "mode": "personal_twin" if twin_cfg.get("enabled", False) else "native_agent",
        "private_memory_policy": str(twin_cfg.get("private_memory_policy", "local_only")),
        "local_first": bool(twin_cfg.get("local_first", False)),
        "share_social_summaries": bool(twin_cfg.get("share_social_summaries", False)),
        "what_if_enabled": bool(twin_cfg.get("what_if_enabled", False)),
        "layers": {
            "private": {
                "memory_scope": "local_memory_rag_diary",
                "data_sources": ["memory", "rag", "diary", "logs", "behavior_trace"],
                "status": "local_only",
            },
            "shared": {
                "memory_scope": "social_summary_public_profile_public_state",
                "data_sources": ["public_profile", "public_state", "social_summary"],
                "status": "shareable",
            },
            "central": {
                "memory_scope": "directory_messages_edges_tick",
                "data_sources": ["directory", "message_route", "social_edges", "tick_state"],
                "status": "relay_visible",
            },
        },
        "current_public_status": _compact_text((agent.get("public_profile", {}) or {}).get("status", ""), 80),
        "public_summary": _compact_text((agent.get("public_profile", {}) or {}).get("summary", ""), 180),
        "today_summary": "",
        "tomorrow_focus": _compact_text((agent.get("public_profile", {}) or {}).get("focus", ""), 80),
        "privacy_note": "Private memory stays local; only public social summaries are shared.",
        "source_note": "Profile, memory, diaries, and local context are maintained on the local device.",
        "public_tags": tags,
        "daily_analysis": {},
    }


def build_daily_twin_analysis(
    agent: dict[str, Any],
    *,
    day: int,
    day_memory: str = "",
    diary_text: str = "",
    intentions_text: str = "",
) -> dict[str, Any]:
    state = agent.get("state", {}) if isinstance(agent.get("state"), dict) else {}
    stress = float(state.get("stress", 0.5) or 0.5)
    emotion = float(state.get("emotion", 0.5) or 0.5)
    econ = float(state.get("econ_security", 0.5) or 0.5)
    preferences = []
    habits = agent.get("habits", {}) if isinstance(agent.get("habits"), dict) else {}
    if habits:
        preferences.append("habits are becoming more stable around repeated contexts")
    if "通勤" in str(day_memory) or "通勤" in str(diary_text):
        preferences.append("commuting remains a stable anchor in daily decision making")
    if "面试" in str(day_memory) or "面试" in str(diary_text):
        preferences.append("career exploration is becoming more important than routine execution")
    if not preferences:
        preferences.append("daily preferences remain relatively stable")
    if stress >= 0.65:
        trend = "stress remains high and should be treated as a meaningful signal"
    elif stress <= 0.35:
        trend = "stress stays manageable"
    else:
        trend = "stress is present but not dominant"
    if emotion >= 0.65:
        mood = "emotion is generally positive"
    elif emotion <= 0.35:
        mood = "emotion is noticeably lower and more guarded"
    else:
        mood = "emotion stays mixed but functional"
    if econ >= 0.6:
        future = "the twin is likely to plan with more freedom and experimentation"
    elif econ <= 0.4:
        future = "economic caution is likely to shape the next day's planning"
    else:
        future = "future planning remains moderately constrained"
    behavior = []
    if "工作" in str(diary_text) or "工作" in str(day_memory):
        behavior.append("work remains a central organizing behavior")
    if "个人时间" in str(diary_text):
        behavior.append("personal time is still used as a recovery window")
    if not behavior:
        behavior.append("behavior is still dominated by routine execution")
    return {
        "day": int(day),
        "preference_shift": "; ".join(preferences),
        "behavior_pattern": "; ".join(behavior),
        "emotion_stress_trend": f"{trend}; {mood}",
        "future_plan_impact": future,
        "memory_signal": _compact_text(day_memory or diary_text, 180),
        "intent_signal": _compact_text(intentions_text, 120),
    }


def apply_daily_twin_update(
    agent: dict[str, Any],
    config: dict[str, Any],
    *,
    day: int,
    day_memory: str = "",
    diary_text: str = "",
    intentions_text: str = "",
) -> tuple[dict[str, Any], str]:
    twin_state = dict(agent.get("twin_status", {}) or {})
    if not twin_state:
        twin_state = build_initial_twin_state(agent, config)
    analysis = build_daily_twin_analysis(
        agent,
        day=day,
        day_memory=day_memory,
        diary_text=diary_text,
        intentions_text=intentions_text,
    )
    public_summary = _compact_text(
        day_memory
        or analysis.get("behavior_pattern", "")
        or diary_text,
        180,
    )
    public_status = _compact_text(
        analysis.get("emotion_stress_trend", "") or day_memory,
        80,
    )
    public_focus = _compact_text(
        analysis.get("future_plan_impact", "") or intentions_text,
        80,
    )
    agent["public_profile"] = {
        "summary": f"Day {int(day)}: {public_summary}" if public_summary else f"Day {int(day)}: local twin update completed.",
        "status": public_status,
        "focus": public_focus,
        "tags": list((agent.get("public_profile", {}) or {}).get("tags", []))[:3],
    }
    twin_state["current_public_status"] = public_status
    twin_state["public_summary"] = agent["public_profile"]["summary"]
    twin_state["today_summary"] = _compact_text(day_memory or diary_text, 180)
    twin_state["tomorrow_focus"] = public_focus
    twin_state["last_public_summary_day"] = int(day)
    twin_state["daily_analysis"] = analysis
    agent["twin_status"] = twin_state
    return twin_state, agent["public_profile"]["summary"]
