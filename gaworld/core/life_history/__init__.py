"""
生活史型智能体 (Life-History Agent) 模块

集成层: gaworld.core.life_history.integration
- sync_relationships_to_runtime: 将 GAWorld relationships 同步到 AgentRuntimeState
- build_relationship_context: 为 prompt 构建关系上下文字符串
- update_relationships_from_reflection: 从反思更新关系
"""

from .lh_types import (
    AgentProfile,
    Identity,
    LifeHistory,
    Values,
    PersonalityTraits,
    CommunicationStyle,
    AffectState,
    AffectType,
    RelationshipMemory,
    RelationshipType,
    InteractionRecord,
    GoalStack,
    Goal,
    GoalType,
    ReflectionEntry,
    BoundedRationality,
    AgentRuntimeState,
    AgentRuntimeLoop,
)

from .mock_data import (
    create_agent_52_profile,
    create_agent_52_runtime_state,
    create_mock_scores,
)

from .integration import (
    sync_relationships_to_runtime,
    build_relationship_context,
    update_relationships_from_reflection,
    create_runtime_state_from_agent,
)

__all__ = [
    "AgentProfile",
    "Identity",
    "LifeHistory",
    "Values",
    "PersonalityTraits",
    "CommunicationStyle",
    "AffectState",
    "AffectType",
    "RelationshipMemory",
    "RelationshipType",
    "InteractionRecord",
    "GoalStack",
    "Goal",
    "GoalType",
    "ReflectionEntry",
    "BoundedRationality",
    "AgentRuntimeState",
    "AgentRuntimeLoop",
    "create_agent_52_profile",
    "create_agent_52_runtime_state",
    "create_mock_scores",
    "sync_relationships_to_runtime",
    "build_relationship_context",
    "update_relationships_from_reflection",
    "create_runtime_state_from_agent",
]
