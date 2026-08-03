"""Social motivation inference.

The main simulator already creates policy, environment, and life events. This
module does not create new world events. It translates existing context into
agent-level social motives: why this agent would contact this person now.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx

from gaworld.social.schemas import InteractionType, MotivationType


@dataclass(frozen=True)
class SocialMotivation:
    motivation_type: MotivationType
    motivation: str
    interaction_type: InteractionType
    reason: str


def _as_float(value: object, default: float = 0.5) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _topic_relevance(graph: nx.Graph, source_id: int, target_id: int, topic: str) -> float:
    if not topic:
        return 0.0
    source = graph.nodes[source_id]
    target = graph.nodes[target_id]
    if "平台" in topic or "派单" in topic or "收入" in topic:
        return max(
            _as_float(source.get("platform_dependence"), 0.4),
            _as_float(target.get("platform_dependence"), 0.4),
        )
    if "台风" in topic or "预警" in topic or "社区" in topic or "通知" in topic:
        return max(
            _as_float(source.get("policy_sensitivity"), 0.5),
            _as_float(target.get("policy_sensitivity"), 0.5),
            _as_float(source.get("city_identity"), 0.5),
            _as_float(target.get("city_identity"), 0.5),
        )
    return max(
        _as_float(source.get("policy_sensitivity"), 0.5),
        _as_float(target.get("policy_sensitivity"), 0.5),
    )


def infer_pair_motivation(
    graph: nx.Graph,
    source_id: int,
    target_id: int,
    context: Any,
) -> SocialMotivation:
    """Infer why a source agent would interact with a target now."""

    edge = graph.edges[source_id, target_id]
    source = graph.nodes[source_id]
    closeness = _as_float(edge.get("closeness"), 0.5)
    trust = _as_float(edge.get("trust"), 0.5)
    friction = _as_float(edge.get("friction"), 0.25)
    obligation = _as_float(edge.get("obligation"), 0.4)
    source_stress = _as_float(source.get("stress"), 0.5)
    public_topic = str(getattr(context, "public_topic", "") or "")
    event_source = str(getattr(context, "event_source", "") or "")
    relevance = _topic_relevance(graph, source_id, target_id, public_topic)

    if public_topic and relevance >= 0.45:
        if event_source == "policy":
            motivation = "confirm_policy_news"
        elif "平台" in public_topic or "派单" in public_topic or "收入" in public_topic:
            motivation = "confirm_platform_news"
        elif "台风" in public_topic or "预警" in public_topic:
            motivation = "warn_or_coordinate"
        else:
            motivation = "share_event_info"
        return SocialMotivation(
            motivation_type="event_triggered",
            motivation=motivation,
            interaction_type="share_news",
            reason=(
                f"主系统事件「{public_topic}」与双方相关度={relevance:.2f}，"
                f"source 因此找可信/相关对象确认或分享信息。"
            ),
        )

    if friction > 0.46:
        return SocialMotivation(
            motivation_type="relationship_triggered",
            motivation="address_tension",
            interaction_type="conflict",
            reason=f"两人关系摩擦={friction:.2f} 较高，互动由关系紧张触发。",
        )

    if source_stress > 0.72 and trust >= 0.45:
        return SocialMotivation(
            motivation_type="internal",
            motivation="vent_stress",
            interaction_type="vent",
            reason=f"source 压力={source_stress:.2f} 较高，且对 target 信任={trust:.2f}，因此倾诉。",
        )

    if obligation > 0.50:
        return SocialMotivation(
            motivation_type="relationship_triggered",
            motivation="ask_or_repay_favor",
            interaction_type="ask_help",
            reason=f"两人存在人情/责任压力={obligation:.2f}，因此触发求助或回应。",
        )

    if closeness > 0.66:
        return SocialMotivation(
            motivation_type="relationship_triggered",
            motivation="maintain_close_tie",
            interaction_type="invite",
            reason=f"两人亲近度={closeness:.2f} 较高，因此主动维持关系。",
        )

    return SocialMotivation(
        motivation_type="relationship_triggered",
        motivation="maintain_weak_tie",
        interaction_type="check_in",
        reason=f"两人有基础关系，亲近度={closeness:.2f}，因此进行低强度寒暄。",
    )
