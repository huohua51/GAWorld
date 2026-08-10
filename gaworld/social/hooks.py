"""Hook-based integration for social interactions in the main simulator."""

from __future__ import annotations

import os
from typing import Any

from llm_providers import call_llm

from gaworld.social.analytics import (
    format_console_event,
    write_dashboard,
    write_daily_summary,
    write_relationship_changes,
    write_social_timeline,
)
from gaworld.social.memory import write_social_memories
from gaworld.social.reflection import write_relationship_reflections
from gaworld.social.runtime import (
    SocialInteractionRuntime,
    format_social_event_log,
    write_social_events_jsonl,
)


STATE_KEY = "gaworld.social.runtime"


def _cfg(context: dict[str, Any]) -> dict[str, Any]:
    config = context.get("config", {})
    if not isinstance(config, dict):
        return {}
    social_cfg = config.get("social_interactions", {})
    return social_cfg if isinstance(social_cfg, dict) else {}


def _state(context: dict[str, Any]) -> dict[str, Any]:
    extension_state = context.setdefault("extension_state", {})
    if not isinstance(extension_state, dict):
        return {}
    return extension_state.setdefault(STATE_KEY, {})


def _llm_fn_for(cfg: dict[str, Any]):
    mode = str(cfg.get("llm", "mock")).strip().lower()
    if mode in {"", "mock", "none", "false", "off"}:
        return None
    if mode == "minimax" and not os.getenv("MINIMAX_API_KEY"):
        raise RuntimeError("social_interactions.llm=minimax requires MINIMAX_API_KEY")
    return lambda prompt: call_llm(prompt, task="social_interaction")


def _activity_for_time(schedule: object, time_str: str) -> str:
    if not isinstance(schedule, list):
        return ""
    current = ""
    for item in schedule:
        if isinstance(item, dict):
            t = str(item.get("time", ""))
            activity = str(item.get("activity", ""))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            t = str(item[0])
            activity = str(item[1])
        else:
            continue
        if t <= time_str:
            current = activity
        else:
            break
    return current


def _agent_activities(context: dict[str, Any]) -> dict[int, str]:
    schedule_map = context.get("schedule_map", {})
    time_str = str(context.get("time_str", ""))
    if not isinstance(schedule_map, dict) or not time_str:
        return {}
    activities: dict[int, str] = {}
    for raw_id, schedule in schedule_map.items():
        try:
            agent_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        activity = _activity_for_time(schedule, time_str)
        if activity:
            activities[agent_id] = activity
    return activities


def on_simulation_start(context: dict[str, Any]) -> None:
    cfg = _cfg(context)
    if not bool(cfg.get("enabled", False)):
        return
    agents = context.get("agents", [])
    if not isinstance(agents, list) or not agents:
        return
    runtime = SocialInteractionRuntime(cfg, agents, llm_fn=_llm_fn_for(cfg))
    state = _state(context)
    state["runtime"] = runtime
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_id = int(agent.get("id", 0))
        agent["social_neighbors"] = runtime.neighbors_for(agent_id)


def on_time_tick(context: dict[str, Any]) -> None:
    cfg = _cfg(context)
    if not bool(cfg.get("enabled", False)):
        return
    state = _state(context)
    runtime = state.get("runtime")
    agents = context.get("agents", [])
    if runtime is None or not isinstance(agents, list):
        return
    policy = context.get("policy")
    policy_desc = None
    if isinstance(policy, dict):
        policy_desc = policy.get("description") or policy.get("name")
    elif policy:
        policy_desc = str(policy)
    events = runtime.tick(
        day=int(context.get("day", 0)),
        time_str=str(context.get("time_str", "")),
        agents=agents,
        env_events=context.get("env_events", []),
        policy_desc=policy_desc,
        agent_activities=_agent_activities(context),
    )
    if not events:
        return
    state["last_events"] = events
    all_events = state.setdefault("events", [])
    if isinstance(all_events, list):
        all_events.extend(events)
    output_jsonl = cfg.get("output_jsonl")
    if output_jsonl:
        write_social_events_jsonl(events, str(output_jsonl))
    if bool(cfg.get("print_events", False)):
        for event in events:
            print(format_console_event(event))
    memory_records = write_social_memories(
        events,
        agents,
        min_salience=float(cfg.get("memory_salience_threshold", 0.50)),
    )
    if memory_records:
        state["last_memory_records"] = memory_records
    daily_logs = context.get("daily_logs")
    if isinstance(daily_logs, dict):
        for event in events:
            line = format_social_event_log(event)
            daily_logs[event.source_id] = daily_logs.get(event.source_id, "") + line
            daily_logs[event.target_id] = daily_logs.get(event.target_id, "") + line


def on_agent_pre_step(context: dict[str, Any]) -> None:
    agent = context.get("agent")
    step = context.get("step")
    if not isinstance(agent, dict) or not isinstance(step, dict):
        return
    pending = agent.pop("_pending_social_interactions", [])
    if not isinstance(pending, list) or not pending:
        return
    fragments = []
    partners = []
    for item in pending[-4:]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if text:
            fragments.append(text)
        try:
            partners.append(int(item.get("partner_id")))
        except (TypeError, ValueError):
            pass
    if not fragments:
        return
    prior_context = str(step.get("social_context", "")).strip()
    interaction_context = "；".join(fragments)
    step["social_context"] = f"{prior_context}；{interaction_context}" if prior_context else interaction_context
    if partners:
        existing = list(agent.get("_recent_social_partners", []) or [])
        agent["_recent_social_partners"] = list(dict.fromkeys(existing + partners))
    step["social_interaction_trigger"] = True


def on_day_end(context: dict[str, Any]) -> None:
    cfg = _cfg(context)
    if not bool(cfg.get("enabled", False)):
        return
    state = _state(context)
    events = state.get("events", [])
    if not isinstance(events, list):
        return
    day = int(context.get("day", 0))
    day_events = [event for event in events if getattr(event, "day", None) == day]
    if cfg.get("summary_md"):
        write_daily_summary(day_events, str(cfg["summary_md"]))
    if cfg.get("timeline_md"):
        write_social_timeline(day_events, str(cfg["timeline_md"]))
    if cfg.get("relationship_changes_csv"):
        write_relationship_changes(day_events, str(cfg["relationship_changes_csv"]))
    if cfg.get("dashboard_html"):
        write_dashboard(day_events, str(cfg["dashboard_html"]))
    agents = context.get("agents", [])
    if isinstance(agents, list):
        reflections = write_relationship_reflections(day_events, agents, day=day)
        if reflections:
            state["last_relationship_reflections"] = reflections
