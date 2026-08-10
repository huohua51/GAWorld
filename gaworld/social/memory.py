"""Social memory helpers for GAWorld.

This module turns structured social interaction events into agent-facing
memories. The goal is deliberately modest: important interactions should be
available to later perception/planning, not only to the output timeline.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from gaworld.social.schemas import SocialInteractionEvent


MemoryWriter = Callable[[int, str, str, int | None, str | None], None]
LogWriter = Callable[[dict[str, Any], str], None]
MemorySaver = Callable[[dict[str, Any]], None]


_BASE_SALIENCE = {
    "check_in": 0.28,
    "invite": 0.55,
    "ask_help": 0.68,
    "vent": 0.70,
    "share_news": 0.72,
    "conflict": 0.88,
}


def social_event_salience(event: SocialInteractionEvent) -> float:
    """Return an importance score for deciding whether to persist an event."""

    base = _BASE_SALIENCE.get(event.interaction_type, 0.40)
    delta = (
        abs(float(event.emotion_delta_source))
        + abs(float(event.emotion_delta_target))
        + abs(float(event.stress_delta_source))
        + abs(float(event.stress_delta_target))
        + 1.5 * abs(float(event.trust_delta))
        + 1.5 * abs(float(event.friction_delta))
    )
    if event.should_diffuse:
        base += 0.08
    return max(0.0, min(1.0, base + delta))


def _partner_name(event: SocialInteractionEvent, perspective_id: int) -> str:
    return event.target_name if int(perspective_id) == int(event.source_id) else event.source_name


def _speaker_line(event: SocialInteractionEvent, perspective_id: int) -> str:
    if int(perspective_id) == int(event.source_id):
        return f"我说：{event.message} 对方回应：{event.reply}"
    return f"对方说：{event.message} 我回应：{event.reply}"


def format_social_memory(event: SocialInteractionEvent, perspective_id: int) -> str:
    """Format a social event as one agent's subjective memory."""

    partner = _partner_name(event, perspective_id)
    salience = social_event_salience(event)
    trust_direction = "上升" if event.trust_delta > 0 else ("下降" if event.trust_delta < 0 else "基本不变")
    friction_direction = "上升" if event.friction_delta > 0 else ("下降" if event.friction_delta < 0 else "基本不变")
    return (
        f"[SocialMemory Day {event.day} {event.time}] "
        f"我和{partner}发生了一次{event.interaction_type}，话题是「{event.topic}」。"
        f"{_speaker_line(event, perspective_id)}。"
        f"主观影响：{event.subjective_effect} "
        f"这次互动后，我对这段关系的信任{trust_direction}，摩擦{friction_direction}。"
        f"salience={salience:.2f}"
    )


def _default_vector_writer(agent_id: int, entry_type: str, text: str, day: int | None, time_str: str | None) -> None:
    from memory_store import vector_db_add_entry

    vector_db_add_entry(agent_id, entry_type, text, sim_day=day, sim_time=time_str)


def _default_log_writer(agent: dict[str, Any], text: str) -> None:
    from memory_store import append_agent_log

    append_agent_log(agent, text)


def _default_memory_saver(agent: dict[str, Any]) -> None:
    from memory_store import save_agent_memory

    save_agent_memory(agent)


def _remember(
    agent: dict[str, Any],
    text: str,
    *,
    day: int,
    time_str: str,
    vector_writer: MemoryWriter,
    log_writer: LogWriter,
    memory_saver: MemorySaver,
) -> None:
    memory = agent.setdefault("memory", [])
    if isinstance(memory, list) and text not in memory:
        memory.append(text)
        memory_saver(agent)
    recent = agent.setdefault("_recent_social_memories", [])
    if not isinstance(recent, list):
        recent = []
        agent["_recent_social_memories"] = recent
    recent.append(text)
    del recent[:-6]
    vector_writer(int(agent.get("id", 0)), "social_memory", text, int(day), str(time_str))
    log_writer(agent, text + "\n")


def write_social_memories(
    events: Iterable[SocialInteractionEvent],
    agents: Iterable[dict[str, Any]],
    *,
    min_salience: float = 0.50,
    vector_writer: MemoryWriter | None = None,
    log_writer: LogWriter | None = None,
    memory_saver: MemorySaver | None = None,
) -> list[dict[str, Any]]:
    """Persist salient social events into each involved agent's memory."""

    agents_by_id = {int(agent.get("id", 0)): agent for agent in agents if isinstance(agent, dict)}
    vector_writer = vector_writer or _default_vector_writer
    log_writer = log_writer or _default_log_writer
    memory_saver = memory_saver or _default_memory_saver
    records: list[dict[str, Any]] = []
    for event in events:
        salience = social_event_salience(event)
        if salience < min_salience:
            continue
        for agent_id in (event.source_id, event.target_id):
            agent = agents_by_id.get(int(agent_id))
            if agent is None:
                continue
            text = format_social_memory(event, int(agent_id))
            _remember(
                agent,
                text,
                day=event.day,
                time_str=event.time,
                vector_writer=vector_writer,
                log_writer=log_writer,
                memory_saver=memory_saver,
            )
            records.append(
                {
                    "agent_id": int(agent_id),
                    "event_id": event.event_id,
                    "salience": salience,
                    "text": text,
                }
            )
    return records
