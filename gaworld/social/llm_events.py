"""LLM-facing social interaction generation.

The main simulator can run this module with a deterministic mock generator or a
configured LLM provider. In both cases the output contract is the same:
dialogue text plus bounded emotion, stress, and relationship deltas.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

import networkx as nx

from gaworld.social.schemas import SocialDecision, SocialInteractionEvent


def _stable_id(decision: SocialDecision) -> str:
    raw = f"{decision.day}-{decision.time}-{decision.source_id}-{decision.target_id}-{decision.topic}"
    return "se_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _clip(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _mock_dialogue(graph: nx.Graph, decision: SocialDecision) -> dict[str, Any]:
    source = graph.nodes[decision.source_id]
    target = graph.nodes[decision.target_id]
    source_name = str(source.get("name", decision.source_id))
    target_name = str(target.get("name", decision.target_id))
    topic = decision.topic
    kind = decision.interaction_type
    edge = graph.edges[decision.source_id, decision.target_id]
    trust = float(edge.get("trust", 0.5))
    friction = float(edge.get("friction", 0.25))
    closeness = float(edge.get("closeness", 0.5))

    if kind == "share_news":
        message = f"{target_name}，我刚听到关于「{topic}」的消息，感觉这事可能会影响我们这两天的安排。"
        reply = "我也有点担心，但你提醒得及时，我先看看身边人怎么说。"
        emotion_target = -0.035 - 0.025 * decision.intensity
        stress_target = 0.030 + 0.025 * decision.intensity
        trust_delta = 0.012 + 0.025 * trust
        should_diffuse = decision.intensity > 0.55
    elif kind == "vent":
        message = f"最近因为「{topic}」有点绷不住，想找你说两句。"
        reply = "我懂，你先别一个人扛着。要不我们一起想想怎么处理。"
        emotion_target = 0.018 + 0.020 * closeness
        stress_target = -0.025 - 0.020 * closeness
        trust_delta = 0.020 + 0.020 * closeness
        should_diffuse = False
    elif kind == "ask_help":
        message = f"我这边碰到点和「{topic}」有关的事，想问问你有没有经验。"
        reply = "可以，我把我知道的情况跟你说一下，能帮就帮。"
        emotion_target = 0.010 + 0.018 * trust
        stress_target = -0.010
        trust_delta = 0.018 + 0.025 * trust
        should_diffuse = False
    elif kind == "invite":
        message = f"今天聊到「{topic}」，要不要晚点一起吃个饭或者散步？"
        reply = "可以，正好也想换个环境聊聊。"
        emotion_target = 0.025 + 0.025 * closeness
        stress_target = -0.020
        trust_delta = 0.012
        should_diffuse = False
    elif kind == "conflict":
        message = f"关于「{topic}」这件事，我觉得你之前的说法让我有点不舒服。"
        reply = "我不是那个意思，但我也觉得你有点误会我了。"
        emotion_target = -0.035
        stress_target = 0.035 + 0.020 * friction
        trust_delta = -0.015
        should_diffuse = False
    else:
        message = f"最近怎么样？我刚好想到你，想问问「{topic}」这方面还顺不顺。"
        reply = "还行，有些小压力，不过有人问一句感觉好一点。"
        emotion_target = 0.010 + 0.015 * closeness
        stress_target = -0.008
        trust_delta = 0.010
        should_diffuse = False

    source_stress_delta = 0.006 if kind in {"share_news", "conflict"} else -0.006
    source_emotion_delta = -0.010 if kind == "conflict" else 0.006
    friction_delta = 0.020 if kind == "conflict" else (-0.006 if trust_delta > 0 else 0.0)
    closeness_delta = 0.010 if kind in {"check_in", "invite", "vent", "ask_help"} else 0.004
    subjective = (
        f"{target_name}听完后对「{topic}」有了更明确的感受。"
        f"这次互动让两人的信任变化 {trust_delta:+.3f}，摩擦变化 {friction_delta:+.3f}。"
    )
    return {
        "message": message,
        "reply": reply,
        "subjective_effect": subjective,
        "emotion_delta_source": source_emotion_delta,
        "emotion_delta_target": emotion_target,
        "stress_delta_source": source_stress_delta,
        "stress_delta_target": stress_target,
        "trust_delta": trust_delta,
        "closeness_delta": closeness_delta,
        "friction_delta": friction_delta,
        "should_diffuse": should_diffuse,
    }


def _prompt(graph: nx.Graph, decision: SocialDecision) -> str:
    source = graph.nodes[decision.source_id]
    target = graph.nodes[decision.target_id]
    edge = graph.edges[decision.source_id, decision.target_id]
    payload = {
        "source": source,
        "target": target,
        "relationship": dict(edge),
        "decision": decision.to_dict(),
    }
    return (
        "你是 GAWorld 社交互动生成器。根据输入生成一次自然的中文社交互动。"
        "只输出一个合法 JSON 对象，不要 Markdown，不要解释。字段包括 message, reply, subjective_effect, emotion_delta_source, "
        "emotion_delta_target, stress_delta_source, stress_delta_target, trust_delta, "
        "closeness_delta, friction_delta, should_diffuse。\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def _parse_llm_json(raw: str) -> dict[str, Any]:
    """Parse JSON even when a model wraps it in fences or extra text."""

    text = raw.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM social interaction payload must be a JSON object.")
    return payload


def generate_interaction(
    graph: nx.Graph,
    decision: SocialDecision,
    *,
    llm_fn: Callable[[str], str] | None = None,
) -> SocialInteractionEvent:
    """Generate dialogue and deltas for a decided social interaction."""

    source = graph.nodes[decision.source_id]
    target = graph.nodes[decision.target_id]
    if llm_fn is None:
        payload = _mock_dialogue(graph, decision)
    else:
        raw = llm_fn(_prompt(graph, decision))
        try:
            payload = _parse_llm_json(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            payload = _mock_dialogue(graph, decision)

    return SocialInteractionEvent(
        event_id=_stable_id(decision),
        day=decision.day,
        time=decision.time,
        source_id=decision.source_id,
        target_id=decision.target_id,
        source_name=str(source.get("name", decision.source_id)),
        target_name=str(target.get("name", decision.target_id)),
        motivation_type=decision.motivation_type,
        motivation=decision.motivation,
        interaction_type=decision.interaction_type,
        topic=decision.topic,
        message=str(payload.get("message", "")),
        reply=str(payload.get("reply", "")),
        subjective_effect=str(payload.get("subjective_effect", "")),
        emotion_delta_source=_clip(_safe_float(payload.get("emotion_delta_source")), -0.12, 0.12),
        emotion_delta_target=_clip(_safe_float(payload.get("emotion_delta_target")), -0.12, 0.12),
        stress_delta_source=_clip(_safe_float(payload.get("stress_delta_source")), -0.12, 0.12),
        stress_delta_target=_clip(_safe_float(payload.get("stress_delta_target")), -0.12, 0.12),
        trust_delta=_clip(_safe_float(payload.get("trust_delta")), -0.08, 0.08),
        closeness_delta=_clip(_safe_float(payload.get("closeness_delta")), -0.08, 0.08),
        friction_delta=_clip(_safe_float(payload.get("friction_delta")), -0.08, 0.08),
        should_diffuse=bool(payload.get("should_diffuse", False)),
        decision_reason=decision.reason,
        motivation_reason=decision.motivation_reason,
    )
