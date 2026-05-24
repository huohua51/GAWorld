"""
Life-History Agent 统一引擎 (Phase 5: Life History Integration)

整合所有集成层，提供统一的运行时接口：
- 关系记忆 (RelationshipMemory)
- 有限理性 (BoundedRationality)
- 情感记忆 (EmotionalMemory)
- 持续学习 (LearningState)

用于注入到 GAWorld 的 planning/action prompts 中
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from .lh_types import AgentRuntimeState, AffectState, BoundedRationality
from .integration import (
    sync_relationships_to_runtime,
    build_relationship_context,
    update_relationships_from_reflection,
)
from .bounded_rationality_integration import (
    sync_bounded_rationality_from_agent,
    get_bounded_rationality_context,
    should_add_bounded_rationality_to_planning,
    build_planning_prompt_with_bounded_rationality,
    get_decision_diversity_hints,
)
from .emotional_memory_integration import (
    EmotionalMemory,
    EmotionalEvent,
    infer_emotional_event_from_gaworld,
    get_emotional_context_from_memory,
    decay_emotional_memory_if_needed,
)
from .learning_integration import (
    LearningState,
    BehaviorSample,
    detect_behavior_drift,
    learn_from_outcome,
    update_preference_from_behavior,
    build_learning_context,
)


@dataclass
class LifeHistoryEngine:
    """
    生活史Agent统一引擎

    在 GAWorld 的 agent step 中使用：
    1. 每个 step 开始时：同步 GAWorld state → LifeHistoryEngine
    2. planning/action 前：构建上下文注入 prompt
    3. step 结束后：记录事件，更新状态
    """
    agent_id: int
    agent_name: str

    # 子系统状态
    emotional_memory: EmotionalMemory = field(default_factory=EmotionalMemory)
    learning_state: LearningState = field(default_factory=LearningState)
    bounded_rationality: BoundedRationality = field(default_factory=BoundedRationality)

    # 运行时数据
    other_agent_names: Dict[int, str] = field(default_factory=dict)
    _last_decay_day: Optional[int] = None

    # GAWorld agent 引用 (用于同步)
    _gaworld_agent: Optional[Dict] = None

    def sync_from_gaworld(
        self,
        agent: Dict,
        agents_by_id: Dict[int, Dict],
        current_day: int,
    ) -> None:
        """
        从 GAWorld agent 同步状态到引擎

        在 step 开始时调用
        """
        self._gaworld_agent = agent

        # 1. 同步有限理性参数
        sync_bounded_rationality_from_agent(agent, self.bounded_rationality)

        # 2. 同步关系记忆 (如果有 runtime_state)
        # 注: 这里只是记录 agent 引用，实际关系数据在 agent["relationships"]
        self.other_agent_names = {
            aid: info.get("name", f"Agent {aid}")
            for aid, info in agents_by_id.items()
            if aid != self.agent_id
        }

        # 3. 衰减情感记忆
        if decay_emotional_memory_if_needed(
            self.emotional_memory,
            self._last_decay_day,
            current_day,
        ):
            self._last_decay_day = current_day

    def build_planning_context(
        self,
        activity: str,
        perception_text: str,
    ) -> str:
        """
        为 planning 构建完整上下文

        整合关系、有限理性、情感记忆、学习等所有上下文
        返回注入到 prompt 的字符串
        """
        parts = []

        # 1. 关系上下文
        if self._gaworld_agent:
            # 创建临时 runtime_state 用于 build_relationship_context
            from .lh_types import AgentRuntimeState, AgentProfile
            from .mock_data import create_agent_52_profile

            # 如果没有 profile，创建一个空的
            profile = create_agent_52_profile()
            runtime_state = AgentRuntimeState(
                agent_id=self.agent_id,
                profile=profile,
            )
            sync_relationships_to_runtime(
                self._gaworld_agent,
                runtime_state,
                self.other_agent_names,
                current_day=0,  # 不更新交互记录
            )
            rel_ctx = build_relationship_context(runtime_state, self.other_agent_names, top_k=2)
            if rel_ctx and rel_ctx != "最近没有与任何熟人互动。":
                parts.append(f"关系状态：{rel_ctx}")

        # 2. 有限理性约束
        if self._gaworld_agent:
            agent_state = self._gaworld_agent.get("state", {})
            if should_add_bounded_rationality_to_planning(agent_state, activity):
                bounded_ctx = get_bounded_rationality_context(self.bounded_rationality, agent_state)
                if bounded_ctx:
                    parts.append(bounded_ctx)

                # 决策多样性警告
                recent_actions = [
                    e.get("action", "")
                    for e in self._gaworld_agent.get("episodes", [])[-10:]
                ]
                div_hint = get_decision_diversity_hints(activity, recent_actions, self.bounded_rationality)
                if div_hint:
                    parts.append(div_hint)

        # 3. 情感记忆上下文
        if self._gaworld_agent:
            agent_state = self._gaworld_agent.get("state", {})
            stress = float(agent_state.get("stress", 0.5))
            emo_ctx = get_emotional_context_from_memory(self.emotional_memory, activity, stress)
            if emo_ctx:
                parts.append(emo_ctx)

        # 4. 学习上下文
        learning_ctx = build_learning_context(
            self.learning_state,
            current_situation=perception_text[:100],
            current_activity=activity,
        )
        if learning_ctx:
            parts.append(learning_ctx)

        return " ".join(parts) if parts else ""

    def record_step_outcome(
        self,
        activity: str,
        plan_text: str,
        action: str,
        outcome: str,
        reflection_text: str,
        state_before: Dict,
        state_after: Dict,
        social_partners: List[int],
        current_day: int,
        success: bool = True,
    ) -> None:
        """
        记录 step 结果，用于更新各子系统状态

        在 step 结束后调用
        """
        # 1. 推断并记录情感事件
        emotional_event = infer_emotional_event_from_gaworld(
            self.agent_id,
            activity,
            plan_text,
            action,
            outcome,
            reflection_text,
            state_before,
            state_after,
            social_partners,
            current_day,
        )
        if emotional_event:
            self.emotional_memory.add_event(emotional_event)

        # 2. 记录行为样本并学习
        sample = BehaviorSample(
            timestamp=float(current_day * 86400),
            activity=activity,
            action=action,
            goal=plan_text[:50] if plan_text else activity,
            outcome=outcome,
            success=success,
            emotion_delta=(
                float(state_after.get("emotion", 0.5)) -
                float(state_before.get("emotion", 0.5))
            ),
        )
        self.learning_state.add_behavior(sample)

        # 从结果学习
        learn_from_outcome(
            self.learning_state,
            situation=activity,
            action=action,
            outcome=outcome,
            success=success,
            emotion_delta=sample.emotion_delta,
        )

        # 更新活动偏好
        satisfaction = float(state_after.get("emotion", 0.5))
        update_preference_from_behavior(
            self.learning_state,
            activity,
            success=success,
            satisfaction=satisfaction,
        )

        # 3. 从反思更新关系 (如果 GAWorld agent 可用)
        if self._gaworld_agent:
            from .integration import update_relationships_from_reflection
            runtime_state = AgentRuntimeState(
                agent_id=self.agent_id,
                profile=create_agent_52_profile() if hasattr(__import__, 'create_agent_52_profile') else None,
            )
            update_relationships_from_reflection(
                runtime_state,
                reflection_text,
                social_partners,
                current_day,
            )

    def get_memory_summary(self) -> str:
        """获取记忆摘要（用于日志）"""
        parts = []

        # 情感记忆摘要
        emo_summary = self.emotional_memory.get_emotional_summary()
        if emo_summary and emo_summary != "最近没有强烈的情感事件。":
            parts.append(f"情感记忆：{emo_summary}")

        # 学习状态摘要
        recent_drifts = self.learning_state.recent_drifts[-3:]
        if recent_drifts:
            drift_desc = "、".join([
                f"{d.drift_type}({d.to_action or d.from_action})"
                for d in recent_drifts
            ])
            parts.append(f"行为漂移：{drift_desc}")

        return "；".join(parts) if parts else ""


# =========================================================
# 便捷工厂函数
# =========================================================

def create_life_history_engine(agent_id: int, agent_name: str) -> LifeHistoryEngine:
    """创建 LifeHistoryEngine 实例"""
    return LifeHistoryEngine(
        agent_id=agent_id,
        agent_name=agent_name,
        emotional_memory=EmotionalMemory(),
        learning_state=LearningState(),
        bounded_rationality=BoundedRationality(
            max_options_considered=3,
            decision_time_limit=2.0,
            uncertainty_threshold=0.3,
            cognitive_biases={
                "recency_bias": 0.5,
                "confirmation_bias": 0.5,
                "availability_heuristic": 0.4,
            },
        ),
    )


# =========================================================
# 导出
# =========================================================

__all__ = [
    "LifeHistoryEngine",
    "create_life_history_engine",
]