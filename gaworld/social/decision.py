"""Rule-based social interaction decisions for GAWorld.

This module is the "system decides structure" layer:
it decides who interacts, what the interaction type is, and why. LLM/text
generation is deliberately kept in ``llm_events.py``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable

import networkx as nx

from gaworld.social.motivation import infer_pair_motivation
from gaworld.social.schemas import InteractionType, SocialDecision


@dataclass(frozen=True)
class SocialContext:
    """Context for one simulated time slot."""

    day: int
    time: str
    public_topic: str = ""
    event_source: str = ""
    event_pressure: float = 0.0


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _topic_for_pair(graph: nx.Graph, source_id: int, target_id: int, context: SocialContext) -> str:
    if context.public_topic and _topic_relevance(graph, source_id, target_id, context) >= 0.45:
        return context.public_topic
    source = graph.nodes[source_id]
    target = graph.nodes[target_id]
    if float(source.get("platform_dependence", 0.0)) > 0.65 or float(target.get("platform_dependence", 0.0)) > 0.65:
        return "平台规则和近期收入压力"
    if float(source.get("stress", 0.5)) > 0.68 or float(target.get("stress", 0.5)) > 0.68:
        return "最近工作压力"
    if source.get("residence", "").split("·", 1)[0] == target.get("residence", "").split("·", 1)[0]:
        return "社区近况和日常安排"
    return "最近生活和工作状态"


def _topic_relevance(graph: nx.Graph, source_id: int, target_id: int, context: SocialContext) -> float:
    if not context.public_topic:
        return 0.35
    source = graph.nodes[source_id]
    target = graph.nodes[target_id]
    topic = context.public_topic
    if "平台" in topic or "派单" in topic:
        return max(
            float(source.get("platform_dependence", 0.4)),
            float(target.get("platform_dependence", 0.4)),
        )
    if "台风" in topic or "社区" in topic or "预警" in topic:
        return max(
            float(source.get("policy_sensitivity", 0.5)),
            float(target.get("policy_sensitivity", 0.5)),
            float(source.get("city_identity", 0.5)),
            float(target.get("city_identity", 0.5)),
        )
    return max(float(source.get("policy_sensitivity", 0.5)), float(target.get("policy_sensitivity", 0.5)))


def _interaction_type(graph: nx.Graph, source_id: int, target_id: int, context: SocialContext) -> InteractionType:
    edge = graph.edges[source_id, target_id]
    source = graph.nodes[source_id]
    target = graph.nodes[target_id]
    closeness = float(edge.get("closeness", 0.5))
    friction = float(edge.get("friction", 0.25))
    obligation = float(edge.get("obligation", 0.4))
    stress = max(float(source.get("stress", 0.5)), float(target.get("stress", 0.5)))
    if friction > 0.46:
        return "conflict"
    if context.public_topic and _topic_relevance(graph, source_id, target_id, context) >= 0.45:
        return "share_news"
    if stress > 0.72:
        return "vent"
    if obligation > 0.50:
        return "ask_help"
    if closeness > 0.66:
        return "invite"
    return "check_in"


def decide_pair_interaction(
    graph: nx.Graph,
    source_id: int,
    target_id: int,
    context: SocialContext,
    rng: random.Random,
) -> SocialDecision | None:
    """Decide whether one edge produces an interaction in this time slot."""

    edge = graph.edges[source_id, target_id]
    source = graph.nodes[source_id]
    target = graph.nodes[target_id]
    closeness = float(edge.get("closeness", 0.5))
    trust = float(edge.get("trust", 0.5))
    friction = float(edge.get("friction", 0.25))
    influence = float(edge.get("influence", 0.5))
    source_need = 0.35 + 0.35 * float(source.get("stress", 0.5)) + 0.25 * float(source.get("voice_propensity", 0.4))
    topic_relevance = _topic_relevance(graph, source_id, target_id, context)

    trace = {
        "base": 0.06,
        "closeness_bonus": 0.18 * closeness,
        "trust_bonus": 0.10 * trust,
        "source_need_bonus": 0.10 * source_need,
        "topic_pressure_bonus": 0.16 * context.event_pressure * topic_relevance,
        "friction_penalty": -0.13 * friction,
        "influence_bonus": 0.06 * influence,
    }
    probability = _clip(sum(trace.values()), 0.02, 0.78)
    draw = rng.random()
    if draw >= probability:
        return None

    motivation = infer_pair_motivation(graph, source_id, target_id, context)
    interaction_type = motivation.interaction_type
    topic = _topic_for_pair(graph, source_id, target_id, context)
    intensity = _clip(0.35 + 0.30 * closeness + 0.25 * context.event_pressure + 0.10 * influence)
    reason = (
        f"关系亲近度={closeness:.2f}，信任={trust:.2f}，摩擦={friction:.2f}，"
        f"话题压力={context.event_pressure:.2f}，动机={motivation.motivation}，因此触发 {interaction_type}。"
    )
    return SocialDecision(
        day=context.day,
        time=context.time,
        source_id=source_id,
        target_id=target_id,
        motivation_type=motivation.motivation_type,
        motivation=motivation.motivation,
        interaction_type=interaction_type,
        topic=topic,
        probability=probability,
        random_draw=draw,
        intensity=intensity,
        reason=reason,
        motivation_reason=motivation.reason,
        trace=trace,
    )


def decide_interactions_for_slot(
    graph: nx.Graph,
    context: SocialContext,
    rng: random.Random,
    *,
    max_events: int = 5,
) -> list[SocialDecision]:
    """Sample the graph and return interactions for one time slot."""

    edges = list(graph.edges())
    rng.shuffle(edges)
    decisions: list[SocialDecision] = []
    for source_id, target_id in edges:
        if rng.random() < 0.5:
            source_id, target_id = target_id, source_id
        decision = decide_pair_interaction(graph, source_id, target_id, context, rng)
        if decision is not None:
            decisions.append(decision)
        if len(decisions) >= max_events:
            break
    return decisions


def decide_message_diffusion(
    graph: nx.Graph,
    source_id: int,
    topic: str,
    context: SocialContext,
    rng: random.Random,
    *,
    already_seen: Iterable[int],
    max_targets: int = 2,
) -> list[SocialDecision]:
    """Choose follow-up neighbors who may receive a shared message."""

    seen = set(already_seen)
    candidates = [n for n in graph.neighbors(source_id) if n not in seen]
    scored = []
    for target_id in candidates:
        edge = graph.edges[source_id, target_id]
        score = (
            0.30 * float(edge.get("trust", 0.5))
            + 0.25 * float(edge.get("influence", 0.5))
            + 0.25 * float(graph.nodes[target_id].get("susceptibility", 0.5))
            - 0.15 * float(edge.get("friction", 0.25))
            + rng.uniform(0.0, 0.06)
        )
        scored.append((score, target_id))
    scored.sort(reverse=True)
    decisions: list[SocialDecision] = []
    for score, target_id in scored[:max_targets]:
        edge = graph.edges[source_id, target_id]
        probability = _clip(score, 0.05, 0.82)
        draw = rng.random()
        if draw >= probability:
            continue
        decisions.append(
            SocialDecision(
                day=context.day,
                time=context.time,
                source_id=source_id,
                target_id=target_id,
                motivation_type="diffusion_triggered",
                motivation="forward_message",
                interaction_type="share_news",
                topic=topic,
                probability=probability,
                random_draw=draw,
                intensity=_clip(0.45 + 0.35 * context.event_pressure + 0.15 * float(edge.get("influence", 0.5))),
                reason=f"消息继续扩散：target 易感性和边影响力较高，prob={probability:.2f}。",
                motivation_reason=f"上一轮关于「{topic}」的消息已触发扩散，系统选择高易感/高影响力邻居继续传播。",
                trace={"diffusion_score": score},
            )
        )
    return decisions
