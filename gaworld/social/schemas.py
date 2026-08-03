"""Dataclasses for the GAWorld social-system prototype."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


RelationType = Literal["coworker", "neighbor", "same_generation", "same_hukou", "weak_tie"]
InteractionType = Literal["check_in", "share_news", "ask_help", "invite", "vent", "conflict"]
MotivationType = Literal[
    "event_triggered",
    "internal",
    "relationship_triggered",
    "encounter_triggered",
    "diffusion_triggered",
]


@dataclass(frozen=True)
class AgentNode:
    """A structured social-network view of one simulated resident."""

    agent_id: int
    name: str
    gender: str
    age: int
    hukou: str
    residence: str
    personality: str
    emotion: float
    energy: float
    stress: float
    econ_security: float
    city_identity: float
    policy_sensitivity: float
    platform_dependence: float
    risk_preference: float
    voice_propensity: float
    mobility_intent: float
    susceptibility: float
    credibility: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RelationshipEdge:
    """A relationship edge with social and diffusion-relevant attributes."""

    source_id: int
    target_id: int
    relation_type: RelationType
    weight: float
    closeness: float
    trust: float
    obligation: float
    friction: float
    support: float
    influence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SocialDecision:
    """A structured decision that one social interaction should happen."""

    day: int
    time: str
    source_id: int
    target_id: int
    motivation_type: MotivationType
    motivation: str
    interaction_type: InteractionType
    topic: str
    probability: float
    random_draw: float
    intensity: float
    reason: str
    motivation_reason: str
    trace: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SocialInteractionEvent:
    """A simulated social interaction with dialogue and state deltas."""

    event_id: str
    day: int
    time: str
    source_id: int
    target_id: int
    source_name: str
    target_name: str
    motivation_type: MotivationType
    motivation: str
    interaction_type: InteractionType
    topic: str
    message: str
    reply: str
    subjective_effect: str
    emotion_delta_source: float
    emotion_delta_target: float
    stress_delta_source: float
    stress_delta_target: float
    trust_delta: float
    closeness_delta: float
    friction_delta: float
    should_diffuse: bool
    decision_reason: str
    motivation_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
