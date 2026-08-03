"""Runtime bridge between the social interaction model and the main simulator."""

from __future__ import annotations

import json
import random
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import networkx as nx

from gaworld.social.decision import SocialContext, decide_interactions_for_slot, decide_message_diffusion
from gaworld.social.llm_events import generate_interaction
from gaworld.social.network import build_social_graph
from gaworld.social.schemas import AgentNode, SocialInteractionEvent


LlmFn = Callable[[str], str]


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _as_float(value: object, default: float = 0.5) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _time_to_minutes(time_str: str) -> int | None:
    parts = str(time_str or "").split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def _agent_value(agent: dict[str, Any], key: str, default: float = 0.5) -> float:
    state = agent.get("state", {})
    if isinstance(state, dict) and key in state:
        return _as_float(state.get(key), default)
    return _as_float(agent.get(key), default)


def _agent_to_node(agent: dict[str, Any]) -> AgentNode:
    age = _as_int(agent.get("age"), 30)
    stress = _agent_value(agent, "stress", 0.5)
    policy_sensitivity = _agent_value(agent, "policy_sensitivity", 0.5)
    platform_dependence = _agent_value(agent, "platform_dependence", 0.5)
    voice_propensity = _agent_value(agent, "voice_propensity", 0.4)
    city_identity = _agent_value(agent, "city_identity", 0.5)
    econ_security = _agent_value(agent, "econ_security", 0.5)
    susceptibility = _clip(0.25 + 0.35 * stress + 0.25 * platform_dependence + 0.15 * policy_sensitivity)
    credibility = _clip(0.25 + 0.35 * voice_propensity + 0.25 * city_identity + 0.15 * econ_security)
    return AgentNode(
        agent_id=_as_int(agent.get("id")),
        name=str(agent.get("name", agent.get("id", ""))),
        gender=str(agent.get("gender", "")),
        age=age,
        hukou=str(agent.get("hukou", "")),
        residence=str(agent.get("residence", "")),
        personality=str(agent.get("personality", "")),
        emotion=_agent_value(agent, "emotion", 0.5),
        energy=_agent_value(agent, "energy", 0.7),
        stress=stress,
        econ_security=econ_security,
        city_identity=city_identity,
        policy_sensitivity=policy_sensitivity,
        platform_dependence=platform_dependence,
        risk_preference=_agent_value(agent, "risk_preference", 0.5),
        voice_propensity=voice_propensity,
        mobility_intent=_agent_value(agent, "mobility_intent", 0.5),
        susceptibility=susceptibility,
        credibility=credibility,
    )


def build_social_graph_from_agents(
    agents: Iterable[dict[str, Any]],
    *,
    seed: int = 42,
    avg_degree: int = 6,
    weak_tie_probability: float = 0.10,
) -> nx.Graph:
    return build_social_graph(
        [_agent_to_node(agent) for agent in agents],
        seed=seed,
        avg_degree=avg_degree,
        weak_tie_probability=weak_tie_probability,
    )


RELATIONSHIP_SYNC_FIELDS = (
    "closeness",
    "trust",
    "obligation",
    "friction",
    "support",
    "influence",
    "weight",
    "relation_type",
)


def hydrate_graph_relationships_from_agents(graph: nx.Graph, agents: Iterable[dict[str, Any]]) -> None:
    """Overlay persisted agent relationship values onto graph edges.

    The social graph owns topology and default edge attributes. Persisted agent
    relationship values own cross-day history, so they should override default
    graph weights when present.
    """

    for agent in agents:
        source_id = _as_int(agent.get("id"))
        relationships = agent.get("relationships", {})
        if not isinstance(relationships, dict):
            continue
        for target_key, rel in relationships.items():
            if not isinstance(rel, dict):
                continue
            target_id = _as_int(target_key, -1)
            if not graph.has_edge(source_id, target_id):
                continue
            edge = graph.edges[source_id, target_id]
            for field in RELATIONSHIP_SYNC_FIELDS:
                if field in rel:
                    edge[field] = rel[field]


def sync_agent_relationships_from_graph(
    graph: nx.Graph,
    agents: Iterable[dict[str, Any]],
    *,
    preserve_existing: bool = True,
) -> None:
    """Make agent social_neighbors and relationships match the active graph."""

    agents_by_id = {_as_int(agent.get("id")): agent for agent in agents if isinstance(agent, dict)}
    for agent_id, agent in agents_by_id.items():
        if agent_id not in graph:
            agent["social_neighbors"] = []
            continue
        neighbors = sorted(int(n) for n in graph.neighbors(agent_id))
        agent["social_neighbors"] = neighbors
        relationships = agent.setdefault("relationships", {})
        if not isinstance(relationships, dict):
            relationships = {}
            agent["relationships"] = relationships
        for neighbor_id in neighbors:
            edge = graph.edges[agent_id, neighbor_id]
            key = str(neighbor_id)
            existing = relationships.get(key, {}) if preserve_existing else {}
            rel = dict(existing) if isinstance(existing, dict) else {}
            for field in RELATIONSHIP_SYNC_FIELDS:
                if preserve_existing and field in rel:
                    continue
                if field in edge:
                    rel[field] = edge[field]
            rel.setdefault("closeness", 0.5)
            rel.setdefault("trust", 0.5)
            rel.setdefault("obligation", 0.5)
            rel.setdefault("friction", 0.5)
            rel.setdefault("last_interaction_day", 0)
            relationships[key] = rel


def initialize_agent_social_state(
    agents: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
) -> nx.Graph:
    """Build the canonical social graph and sync it into agent dictionaries."""

    cfg = config or {}
    graph = build_social_graph_from_agents(
        agents,
        seed=int(cfg.get("network_seed", 42)),
        avg_degree=int(cfg.get("avg_degree", 6)),
        weak_tie_probability=float(cfg.get("weak_tie_probability", 0.12)),
    )
    hydrate_graph_relationships_from_agents(graph, agents)
    sync_agent_relationships_from_graph(graph, agents, preserve_existing=True)
    return graph


def sync_graph_node_state(graph: nx.Graph, agents: Iterable[dict[str, Any]]) -> None:
    for agent in agents:
        agent_id = _as_int(agent.get("id"))
        if agent_id not in graph:
            continue
        node = _agent_to_node(agent)
        graph.nodes[agent_id].update(node.to_dict())


def _event_description(event: SocialInteractionEvent, perspective_id: int) -> str:
    if perspective_id == event.source_id:
        return (
            f"{event.time} 你和{event.target_name}聊到「{event.topic}」。"
            f"你说：{event.message} 对方回应：{event.reply} "
            f"主观影响：{event.subjective_effect}"
        )
    return (
        f"{event.time} {event.source_name}找你聊到「{event.topic}」。"
        f"对方说：{event.message} 你回应：{event.reply} "
        f"主观影响：{event.subjective_effect}"
    )


def _append_pending_context(agent: dict[str, Any], event: SocialInteractionEvent, partner_id: int) -> None:
    pending = agent.setdefault("_pending_social_interactions", [])
    if not isinstance(pending, list):
        pending = []
        agent["_pending_social_interactions"] = pending
    pending.append(
        {
            "partner_id": partner_id,
            "event_id": event.event_id,
            "interaction_type": event.interaction_type,
            "topic": event.topic,
            "text": _event_description(event, _as_int(agent.get("id"))),
        }
    )
    del pending[:-4]


def _apply_state_delta(agent: dict[str, Any], emotion_delta: float, stress_delta: float) -> None:
    state = agent.setdefault("state", {})
    state["emotion"] = _clip(_as_float(state.get("emotion"), 0.5) + emotion_delta)
    state["stress"] = _clip(_as_float(state.get("stress"), 0.5) + stress_delta)
    if "social_need" in state:
        state["social_need"] = _clip(_as_float(state.get("social_need"), 0.4) - 0.04)


def _apply_relationship_delta(
    agent: dict[str, Any],
    partner_id: int,
    event: SocialInteractionEvent,
    day: int,
) -> None:
    relationships = agent.setdefault("relationships", {})
    if not isinstance(relationships, dict):
        relationships = {}
        agent["relationships"] = relationships
    rel = relationships.setdefault(str(partner_id), {})
    if not isinstance(rel, dict):
        rel = {}
        relationships[str(partner_id)] = rel
    rel["trust"] = _clip(_as_float(rel.get("trust"), 0.5) + event.trust_delta)
    rel["closeness"] = _clip(_as_float(rel.get("closeness"), 0.5) + event.closeness_delta)
    rel["friction"] = _clip(_as_float(rel.get("friction"), 0.5) + event.friction_delta)
    rel.setdefault("obligation", 0.5)
    rel["last_interaction_day"] = int(day)


class SocialInteractionRuntime:
    """Runs social interactions inside the main simulation tick loop."""

    def __init__(
        self,
        config: dict[str, Any],
        agents: list[dict[str, Any]],
        *,
        llm_fn: LlmFn | None = None,
    ) -> None:
        self.config = config
        self.enabled = bool(config.get("enabled", True))
        self.rng = random.Random(int(config.get("seed", 20260602)))
        self.max_events_per_tick = int(config.get("max_events_per_tick", 2))
        self.max_diffusion_targets = int(config.get("max_diffusion_targets", 1))
        self.llm_mode = str(config.get("llm", "mock")).lower()
        self.llm_fn = llm_fn if self.llm_mode not in {"", "mock", "none"} else None
        self.graph = initialize_agent_social_state(agents, config)
        self.pair_cooldown_minutes = int(config.get("pair_cooldown_minutes", 180))
        self.agent_daily_budget = int(config.get("agent_daily_budget", 6))
        self.agent_daily_budget_extrovert_bonus = int(config.get("agent_daily_budget_extrovert_bonus", 2))
        self.agent_daily_budget_low_energy_penalty = int(config.get("agent_daily_budget_low_energy_penalty", 2))
        self.hard_block_keywords = tuple(
            config.get(
                "hard_block_activity_keywords",
                ["睡", "考试", "手术", "面试", "高考", "住院", "急诊"],
            )
        )
        self.soft_block_keywords = tuple(
            config.get(
                "soft_block_activity_keywords",
                ["深度工作", "专注", "会议", "上课", "通勤", "赶路", "汇报"],
            )
        )
        self.social_activity_keywords = tuple(
            config.get(
                "social_activity_keywords",
                ["吃饭", "午餐", "晚餐", "咖啡", "散步", "休息", "聊天", "聚会", "社区"],
            )
        )
        self._pair_last_seen: dict[tuple[int, int], int] = {}
        self._agent_day_counts: dict[tuple[int, int], int] = {}

    def neighbors_for(self, agent_id: int) -> list[int]:
        if agent_id not in self.graph:
            return []
        return list(self.graph.neighbors(agent_id))

    def tick(
        self,
        *,
        day: int,
        time_str: str,
        agents: list[dict[str, Any]],
        env_events: list[dict[str, Any]] | None = None,
        policy_desc: str | None = None,
        agent_activities: dict[int, str] | None = None,
    ) -> list[SocialInteractionEvent]:
        if not self.enabled or self.graph.number_of_edges() == 0:
            return []
        sync_graph_node_state(self.graph, agents)
        context = SocialContext(
            day=day,
            time=time_str,
            public_topic=self._public_topic(env_events=env_events, policy_desc=policy_desc),
            event_source=self._event_source(env_events=env_events, policy_desc=policy_desc),
            event_pressure=self._event_pressure(env_events=env_events, policy_desc=policy_desc),
        )
        events: list[SocialInteractionEvent] = []
        seen_by_topic: dict[str, set[int]] = {}
        for decision in decide_interactions_for_slot(
            self.graph,
            context,
            self.rng,
            max_events=self.max_events_per_tick,
        ):
            if not self._decision_allowed(decision.source_id, decision.target_id, day, time_str, agent_activities):
                continue
            event = generate_interaction(self.graph, decision, llm_fn=self.llm_fn)
            self._apply_event(event, agents, day)
            self._record_decision(decision.source_id, decision.target_id, day, time_str)
            events.append(event)
            seen = seen_by_topic.setdefault(event.topic, {event.source_id, event.target_id})
            seen.update({event.source_id, event.target_id})
            if event.should_diffuse and self.max_diffusion_targets > 0:
                for follow_up in decide_message_diffusion(
                    self.graph,
                    event.target_id,
                    event.topic,
                    context,
                    self.rng,
                    already_seen=seen,
                    max_targets=self.max_diffusion_targets,
                ):
                    if not self._decision_allowed(
                        follow_up.source_id,
                        follow_up.target_id,
                        day,
                        time_str,
                        agent_activities,
                    ):
                        continue
                    follow_event = generate_interaction(self.graph, follow_up, llm_fn=self.llm_fn)
                    self._apply_event(follow_event, agents, day)
                    self._record_decision(follow_up.source_id, follow_up.target_id, day, time_str)
                    events.append(follow_event)
                    seen.update({follow_event.source_id, follow_event.target_id})
        return events

    def _decision_allowed(
        self,
        source_id: int,
        target_id: int,
        day: int,
        time_str: str,
        agent_activities: dict[int, str] | None,
    ) -> bool:
        if self._pair_in_cooldown(source_id, target_id, day, time_str):
            return False
        if self._over_daily_budget(source_id, day) or self._over_daily_budget(target_id, day):
            return False
        source_activity = str((agent_activities or {}).get(source_id, ""))
        target_activity = str((agent_activities or {}).get(target_id, ""))
        factor = min(self._activity_factor(source_activity), self._activity_factor(target_activity))
        if factor <= 0:
            return False
        if factor < 1.0 and self.rng.random() > factor:
            return False
        return True

    def _pair_in_cooldown(self, source_id: int, target_id: int, day: int, time_str: str) -> bool:
        if self.pair_cooldown_minutes <= 0:
            return False
        minutes = _time_to_minutes(time_str)
        if minutes is None:
            return False
        absolute = int(day) * 1440 + minutes
        pair = tuple(sorted((int(source_id), int(target_id))))
        last = self._pair_last_seen.get(pair)
        return last is not None and absolute - last < self.pair_cooldown_minutes

    def _agent_budget_for(self, agent_id: int) -> int:
        node = self.graph.nodes[agent_id] if agent_id in self.graph else {}
        budget = self.agent_daily_budget
        personality_blob = str(node.get("personality", ""))
        if any(k in personality_blob for k in ["外向", "活泼", "社交", "开朗"]):
            budget += self.agent_daily_budget_extrovert_bonus
        if float(node.get("energy", 0.6)) < 0.30 or float(node.get("stress", 0.5)) > 0.78:
            budget -= self.agent_daily_budget_low_energy_penalty
        return max(1, budget)

    def _over_daily_budget(self, agent_id: int, day: int) -> bool:
        return self._agent_day_counts.get((int(day), int(agent_id)), 0) >= self._agent_budget_for(agent_id)

    def _activity_factor(self, activity: str) -> float:
        text = str(activity or "")
        if any(keyword in text for keyword in self.hard_block_keywords):
            return 0.0
        if any(keyword in text for keyword in self.social_activity_keywords):
            return 1.0
        if any(keyword in text for keyword in self.soft_block_keywords):
            return 0.35
        return 0.75

    def _record_decision(self, source_id: int, target_id: int, day: int, time_str: str) -> None:
        minutes = _time_to_minutes(time_str)
        if minutes is not None:
            self._pair_last_seen[tuple(sorted((int(source_id), int(target_id))))] = int(day) * 1440 + minutes
        self._agent_day_counts[(int(day), int(source_id))] = self._agent_day_counts.get((int(day), int(source_id)), 0) + 1
        self._agent_day_counts[(int(day), int(target_id))] = self._agent_day_counts.get((int(day), int(target_id)), 0) + 1

    def _public_topic(self, *, env_events: list[dict[str, Any]] | None, policy_desc: str | None) -> str:
        if policy_desc:
            return str(policy_desc)
        for event in env_events or []:
            if not isinstance(event, dict):
                continue
            text = str(event.get("description") or event.get("name") or "").strip()
            if text:
                return text
        return ""

    def _event_source(self, *, env_events: list[dict[str, Any]] | None, policy_desc: str | None) -> str:
        if policy_desc:
            return "policy"
        for event in env_events or []:
            if isinstance(event, dict) and (event.get("description") or event.get("name")):
                return str(event.get("type") or event.get("source") or "environment")
        return ""

    def _event_pressure(self, *, env_events: list[dict[str, Any]] | None, policy_desc: str | None) -> float:
        pressure = 0.18
        if policy_desc:
            pressure += 0.35
        pressure += min(0.35, 0.12 * len(env_events or []))
        return _clip(pressure, 0.05, 0.85)

    def _apply_event(self, event: SocialInteractionEvent, agents: list[dict[str, Any]], day: int) -> None:
        agents_by_id = {_as_int(agent.get("id")): agent for agent in agents}
        source = agents_by_id.get(event.source_id)
        target = agents_by_id.get(event.target_id)
        if source is None or target is None:
            return
        if self.graph.has_edge(event.source_id, event.target_id):
            edge = self.graph.edges[event.source_id, event.target_id]
            edge["trust"] = _clip(_as_float(edge.get("trust"), 0.5) + event.trust_delta)
            edge["closeness"] = _clip(_as_float(edge.get("closeness"), 0.5) + event.closeness_delta)
            edge["friction"] = _clip(_as_float(edge.get("friction"), 0.25) + event.friction_delta)
            edge["weight"] = _clip(_as_float(edge.get("weight"), 0.5) + 0.5 * event.trust_delta + 0.4 * event.closeness_delta - 0.4 * event.friction_delta)

        _apply_state_delta(source, event.emotion_delta_source, event.stress_delta_source)
        _apply_state_delta(target, event.emotion_delta_target, event.stress_delta_target)
        _apply_relationship_delta(source, event.target_id, event, day)
        _apply_relationship_delta(target, event.source_id, event, day)
        if self.graph.has_edge(event.source_id, event.target_id):
            sync_agent_relationships_from_graph(self.graph, [source, target], preserve_existing=True)
        _append_pending_context(source, event, event.target_id)
        _append_pending_context(target, event, event.source_id)


def write_social_events_jsonl(events: Iterable[SocialInteractionEvent], path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")


def format_social_event_log(event: SocialInteractionEvent) -> str:
    return (
        f"[SocialInteraction Day {event.day} {event.time}] "
        f"{event.source_name} -> {event.target_name} "
        f"{event.interaction_type}「{event.topic}」｜"
        f"motivation={event.motivation_type}/{event.motivation}｜"
        f"{event.source_name}: {event.message}｜"
        f"{event.target_name}: {event.reply}｜"
        f"{event.subjective_effect}\n"
    )
