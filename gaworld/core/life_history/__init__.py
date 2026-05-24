"""
生活史型智能体 (Life-History Agent) 模块

集成层:
- gaworld.core.life_history.integration: 关系记忆集成
- gaworld.core.life_history.bounded_rationality_integration: 有限理性集成
- gaworld.core.life_history.emotional_memory_integration: 情感记忆集成
- gaworld.core.life_history.learning_integration: 持续学习集成
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

from .bounded_rationality_integration import (
    sync_bounded_rationality_from_agent,
    get_bounded_rationality_context,
    should_add_bounded_rationality_to_planning,
    build_planning_prompt_with_bounded_rationality,
    get_decision_diversity_hints,
)

from .emotional_memory_integration import (
    EmotionalEventType,
    EmotionalEvent,
    EmotionalMemory,
    infer_emotional_event_from_gaworld,
    get_emotional_context_from_memory,
    decay_emotional_memory_if_needed,
)

from .learning_integration import (
    LearningSignal,
    BehaviorSample,
    BehaviorDrift,
    LearnedStrategy,
    LearningState,
    detect_behavior_drift,
    get_drift_warning_message,
    learn_from_outcome,
    get_strategy_reminder,
    update_preference_from_behavior,
    get_activity_preference_hint,
    build_learning_context,
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
    # integration
    "sync_relationships_to_runtime",
    "build_relationship_context",
    "update_relationships_from_reflection",
    "create_runtime_state_from_agent",
    # bounded rationality
    "sync_bounded_rationality_from_agent",
    "get_bounded_rationality_context",
    "should_add_bounded_rationality_to_planning",
    "build_planning_prompt_with_bounded_rationality",
    "get_decision_diversity_hints",
    # emotional memory
    "EmotionalEventType",
    "EmotionalEvent",
    "EmotionalMemory",
    "infer_emotional_event_from_gaworld",
    "get_emotional_context_from_memory",
    "decay_emotional_memory_if_needed",
    # learning
    "LearningSignal",
    "BehaviorSample",
    "BehaviorDrift",
    "LearnedStrategy",
    "LearningState",
    "detect_behavior_drift",
    "get_drift_warning_message",
    "learn_from_outcome",
    "get_strategy_reminder",
    "update_preference_from_behavior",
    "get_activity_preference_hint",
    "build_learning_context",
]
