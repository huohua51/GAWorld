"""Daily relationship reflection for GAWorld social interactions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any

from gaworld.social.schemas import SocialInteractionEvent


MemoryWriter = Callable[[int, str, str, int | None, str | None], None]
LogWriter = Callable[[dict[str, Any], str], None]
MemorySaver = Callable[[dict[str, Any]], None]


def _default_vector_writer(agent_id: int, entry_type: str, text: str, day: int | None, time_str: str | None) -> None:
    from memory_store import vector_db_add_entry

    vector_db_add_entry(agent_id, entry_type, text, sim_day=day, sim_time=time_str)


def _default_log_writer(agent: dict[str, Any], text: str) -> None:
    from memory_store import append_agent_log

    append_agent_log(agent, text)


def _default_memory_saver(agent: dict[str, Any]) -> None:
    from memory_store import save_agent_memory

    save_agent_memory(agent)


def _event_for_agent(event: SocialInteractionEvent, agent_id: int) -> dict[str, Any]:
    partner_id = event.target_id if int(agent_id) == int(event.source_id) else event.source_id
    partner_name = event.target_name if int(agent_id) == int(event.source_id) else event.source_name
    emotion_delta = event.emotion_delta_source if int(agent_id) == int(event.source_id) else event.emotion_delta_target
    stress_delta = event.stress_delta_source if int(agent_id) == int(event.source_id) else event.stress_delta_target
    return {
        "partner_id": int(partner_id),
        "partner_name": partner_name,
        "interaction_type": event.interaction_type,
        "topic": event.topic,
        "emotion_delta": float(emotion_delta),
        "stress_delta": float(stress_delta),
        "trust_delta": float(event.trust_delta),
        "closeness_delta": float(event.closeness_delta),
        "friction_delta": float(event.friction_delta),
    }


def relationship_reflection_text(agent: dict[str, Any], day: int, events: Iterable[SocialInteractionEvent]) -> str:
    """Build a deterministic daily relationship reflection for one agent."""

    agent_id = int(agent.get("id", 0))
    rows = [_event_for_agent(event, agent_id) for event in events if agent_id in {event.source_id, event.target_id}]
    if not rows:
        return ""

    by_partner: dict[int, dict[str, Any]] = defaultdict(
        lambda: {
            "partner_name": "",
            "count": 0,
            "trust_delta": 0.0,
            "closeness_delta": 0.0,
            "friction_delta": 0.0,
            "topics": [],
            "types": [],
        }
    )
    for row in rows:
        item = by_partner[int(row["partner_id"])]
        item["partner_name"] = row["partner_name"]
        item["count"] += 1
        item["trust_delta"] += float(row["trust_delta"])
        item["closeness_delta"] += float(row["closeness_delta"])
        item["friction_delta"] += float(row["friction_delta"])
        item["topics"].append(str(row["topic"]))
        item["types"].append(str(row["interaction_type"]))

    closest = max(by_partner.values(), key=lambda item: (float(item["closeness_delta"]), int(item["count"])))
    tense = max(by_partner.values(), key=lambda item: float(item["friction_delta"]))
    helpful = max(by_partner.values(), key=lambda item: float(item["trust_delta"]))

    lines = [
        f"[RelationshipReflection Day {day}]",
        f"今天我一共经历了 {len(rows)} 次社交互动，涉及 {len(by_partner)} 个熟人。",
        (
            f"关系更近的人：{closest['partner_name']}，互动 {closest['count']} 次，"
            f"亲近度变化 {float(closest['closeness_delta']):+.3f}。"
        ),
        (
            f"信任变化最明显的人：{helpful['partner_name']}，"
            f"信任变化 {float(helpful['trust_delta']):+.3f}。"
        ),
    ]
    if float(tense["friction_delta"]) > 0:
        lines.append(f"需要留意的摩擦：{tense['partner_name']}，摩擦变化 {float(tense['friction_delta']):+.3f}。")
        lines.append(f"明天倾向：如果再遇到{tense['partner_name']}，先降低语气强度，避免把小摩擦扩大。")
    else:
        lines.append("今天没有明显升级的关系摩擦。")
        lines.append(f"明天倾向：可以优先和{helpful['partner_name']}保持联系，延续今天形成的支持感。")
    return "\n".join(lines)


def _persist_reflection(
    agent: dict[str, Any],
    text: str,
    *,
    day: int,
    vector_writer: MemoryWriter,
    log_writer: LogWriter,
    memory_saver: MemorySaver,
) -> None:
    memory = agent.setdefault("memory", [])
    if isinstance(memory, list) and text not in memory:
        memory.append(text)
        memory_saver(agent)
    agent["_social_relationship_reflection"] = text
    vector_writer(int(agent.get("id", 0)), "social_reflection", text, int(day), "end_of_day")
    log_writer(agent, text + "\n")


def write_relationship_reflections(
    events: Iterable[SocialInteractionEvent],
    agents: Iterable[dict[str, Any]],
    *,
    day: int,
    vector_writer: MemoryWriter | None = None,
    log_writer: LogWriter | None = None,
    memory_saver: MemorySaver | None = None,
) -> list[dict[str, Any]]:
    """Persist daily relationship reflections for agents involved in social events."""

    event_list = list(events)
    vector_writer = vector_writer or _default_vector_writer
    log_writer = log_writer or _default_log_writer
    memory_saver = memory_saver or _default_memory_saver
    records: list[dict[str, Any]] = []
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        text = relationship_reflection_text(agent, int(day), event_list)
        if not text:
            continue
        _persist_reflection(
            agent,
            text,
            day=int(day),
            vector_writer=vector_writer,
            log_writer=log_writer,
            memory_saver=memory_saver,
        )
        records.append({"agent_id": int(agent.get("id", 0)), "day": int(day), "text": text})
    return records
