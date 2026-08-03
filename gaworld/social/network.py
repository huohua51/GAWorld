"""Network construction for the GAWorld social-system prototype."""

from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Iterable

import networkx as nx

from gaworld.social.schemas import AgentNode, RelationshipEdge


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


def _age_band(age: int) -> int:
    return int(age // 10 * 10)


def _district(residence: str) -> str:
    return str(residence or "").split("·", 1)[0].strip()


def _clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def load_seed_agents(csv_path: str | Path) -> list[AgentNode]:
    """Load seeded Hangzhou agents from ``hangzhou_agents_state_init.csv``.

    The social prototype derives two diffusion attributes:
    - susceptibility: how easily an agent is emotionally affected by neighbors
    - credibility: how likely others are to treat the agent as influential
    """

    agents: list[AgentNode] = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            age = _as_int(row.get("age"), 30)
            stress = _as_float(row.get("stress"), 0.5)
            policy_sensitivity = _as_float(row.get("policy_sensitivity"), 0.5)
            platform_dependence = _as_float(row.get("platform_dependence"), 0.5)
            voice_propensity = _as_float(row.get("voice_propensity"), 0.4)
            city_identity = _as_float(row.get("city_identity"), 0.5)
            econ_security = _as_float(row.get("econ_security"), 0.5)
            susceptibility = _clip(0.25 + 0.35 * stress + 0.25 * platform_dependence + 0.15 * policy_sensitivity)
            credibility = _clip(0.25 + 0.35 * voice_propensity + 0.25 * city_identity + 0.15 * econ_security)
            agents.append(
                AgentNode(
                    agent_id=_as_int(row.get("id")),
                    name=str(row.get("name", "")),
                    gender=str(row.get("gender", "")),
                    age=age,
                    hukou=str(row.get("hukou", "")),
                    residence=str(row.get("residence", "")),
                    personality=str(row.get("personality", "")),
                    emotion=_as_float(row.get("emotion"), 0.5),
                    energy=_as_float(row.get("energy"), 0.7),
                    stress=stress,
                    econ_security=econ_security,
                    city_identity=city_identity,
                    policy_sensitivity=policy_sensitivity,
                    platform_dependence=platform_dependence,
                    risk_preference=_as_float(row.get("risk_preference"), 0.5),
                    voice_propensity=voice_propensity,
                    mobility_intent=_as_float(row.get("mobility_intent"), 0.5),
                    susceptibility=susceptibility,
                    credibility=credibility,
                )
            )
    return agents


def _edge_from_pair(a: AgentNode, b: AgentNode, rng: random.Random) -> RelationshipEdge:
    same_district = _district(a.residence) and _district(a.residence) == _district(b.residence)
    same_generation = abs(a.age - b.age) <= 8
    same_hukou = a.hukou == b.hukou and bool(a.hukou)

    if same_district:
        relation_type = "neighbor"
    elif same_generation:
        relation_type = "same_generation"
    elif same_hukou:
        relation_type = "same_hukou"
    else:
        relation_type = "weak_tie"

    closeness = 0.25
    closeness += 0.22 if same_district else 0.0
    closeness += 0.18 if same_generation else 0.0
    closeness += 0.10 if same_hukou else 0.0
    closeness += rng.uniform(-0.05, 0.08)
    closeness = _clip(closeness)

    trust = _clip(0.35 + 0.25 * ((a.city_identity + b.city_identity) / 2.0) + rng.uniform(-0.06, 0.06))
    friction = _clip(0.22 + 0.20 * abs(a.risk_preference - b.risk_preference) + rng.uniform(-0.04, 0.08))
    obligation = _clip(0.22 + 0.18 * closeness + (0.10 if same_district else 0.0) + rng.uniform(-0.04, 0.05))
    support = _clip(0.25 + 0.45 * closeness + 0.20 * trust - 0.20 * friction)
    influence = _clip(0.20 + 0.35 * closeness + 0.25 * trust + 0.20 * ((a.credibility + b.credibility) / 2.0))
    weight = _clip(0.15 + 0.35 * closeness + 0.25 * trust + 0.20 * support - 0.20 * friction)

    return RelationshipEdge(
        source_id=a.agent_id,
        target_id=b.agent_id,
        relation_type=relation_type,  # type: ignore[arg-type]
        weight=weight,
        closeness=closeness,
        trust=trust,
        obligation=obligation,
        friction=friction,
        support=support,
        influence=influence,
    )


def build_social_graph(
    agents: Iterable[AgentNode],
    *,
    seed: int = 42,
    avg_degree: int = 6,
    weak_tie_probability: float = 0.10,
) -> nx.Graph:
    """Build a small-world-ish social graph from demographic similarity.

    This is a stronger baseline than the legacy random neighbor list: it creates
    repeated users, local clusters, weak ties, and weighted relationship edges.
    """

    rng = random.Random(seed)
    agent_list = list(agents)
    by_id = {a.agent_id: a for a in agent_list}
    graph = nx.Graph()
    for agent in agent_list:
        graph.add_node(agent.agent_id, **agent.to_dict())

    for agent in agent_list:
        candidates = [other for other in agent_list if other.agent_id != agent.agent_id]
        scored: list[tuple[float, AgentNode]] = []
        for other in candidates:
            score = 0.0
            score += 0.35 if _district(agent.residence) == _district(other.residence) else 0.0
            score += 0.25 if abs(agent.age - other.age) <= 8 else 0.0
            score += 0.15 if agent.hukou == other.hukou else 0.0
            score += 0.15 * (1.0 - abs(agent.platform_dependence - other.platform_dependence))
            score += 0.10 * (1.0 - abs(agent.risk_preference - other.risk_preference))
            score += rng.uniform(0.0, 0.08)
            scored.append((score, other))
        scored.sort(key=lambda item: item[0], reverse=True)
        for _, other in scored[: max(1, avg_degree // 2)]:
            if graph.has_edge(agent.agent_id, other.agent_id):
                continue
            edge = _edge_from_pair(agent, other, rng)
            graph.add_edge(agent.agent_id, other.agent_id, **edge.to_dict())

    ids = [a.agent_id for a in agent_list]
    for source_id in ids:
        if rng.random() >= weak_tie_probability:
            continue
        target_id = rng.choice([i for i in ids if i != source_id])
        if graph.has_edge(source_id, target_id):
            continue
        edge = _edge_from_pair(by_id[source_id], by_id[target_id], rng)
        graph.add_edge(source_id, target_id, **edge.to_dict())

    return graph
