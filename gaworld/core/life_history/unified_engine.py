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

    # 子系统状态 - 持久化
    runtime_state: AgentRuntimeState = field(default_factory=None)
    profile: Any = field(default=None)  # AgentProfile from GAWorld

    # 子系统状态 - 工作内存
    emotional_memory: EmotionalMemory = field(default_factory=EmotionalMemory)
    learning_state: LearningState = field(default_factory=LearningState)
    bounded_rationality: BoundedRationality = field(default_factory=BoundedRationality)

    # 运行时数据
    other_agent_names: Dict[int, str] = field(default_factory=dict)
    _last_decay_day: Optional[int] = None

    # GAWorld agent 引用 (用于同步)
    _gaworld_agent: Optional[Dict] = None

    def __post_init__(self):
        # 确保运行时状态已初始化
        if self.runtime_state is None:
            from .lh_types import AgentRuntimeState, AgentProfile, GoalStack, AffectState
            from .mock_data import create_agent_52_profile
            # 用传入的 profile 或默认 profile
            profile = self.profile if self.profile is not None else create_agent_52_profile()
            self.profile = profile
            self.runtime_state = AgentRuntimeState(
                agent_id=self.agent_id,
                profile=profile,
                affect=AffectState(),
                goals=GoalStack(),
            )

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

        # 0. 同步 profile (如果 GAWorld 有 profile 数据)
        if agent.get("profile") and self.profile is None:
            self.profile = agent["profile"]
            self.runtime_state.profile = self.profile

        # 1. 同步有限理性参数
        sync_bounded_rationality_from_agent(agent, self.bounded_rationality)

        # 2. 同步关系记忆: GAWorld -> self.runtime_state
        self.other_agent_names = {
            aid: info.get("name", f"Agent {aid}")
            for aid, info in agents_by_id.items()
            if aid != self.agent_id
        }
        sync_relationships_to_runtime(
            agent,
            self.runtime_state,
            self.other_agent_names,
            current_day,
        )

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

        # 0. Profile 人格摘要 - 分层输出，每段独立、稳定进入 prompt
        if self.profile:
            p = self.profile
            # 身份/职业（固定不变，最重要）
            identity_line = f"你是{p.identity.name}，{p.identity.occupation}。"

            # 人格倾向（3-4个核心特质，约30字）
            traits = []
            if p.personality.rationality >= 0.75:
                traits.append("理性优先")
            if p.personality.result_orientation >= 0.75:
                traits.append("结果导向")
            if p.personality.extraversion >= 0.65:
                traits.append("外向活跃")
            elif p.personality.extraversion <= 0.35:
                traits.append("内敛沉稳")
            if p.personality.openness >= 0.7:
                traits.append("开放好奇")
            if p.personality.impulse_control >= 0.7:
                traits.append("自律克制")
            if p.personality.stress_response >= 0.6:
                traits.append("压力下易焦虑")
            elif p.personality.stress_response <= 0.4:
                traits.append("压力下沉稳")
            personality_line = f"人格：{'、'.join(traits[:4])}。" if traits else ""

            # 日常习惯（直接取 GAWorld agent 的 daily_life，约40字）
            daily_life = ""
            if self._gaworld_agent:
                raw_daily = self._gaworld_agent.get("daily_life", "")
                if raw_daily:
                    daily_life = f"日常：{raw_daily[:40]}"
            if not daily_life and p.life_history.self_narrative:
                # fallback: 从 self_narrative 提取"日常："以后的部分
                import re
                m = re.search(r'日常[：:](.+?)(?:。|$)', p.life_history.self_narrative)
                if m:
                    daily_life = f"日常：{m.group(1)[:40]}"
            daily_line = daily_life + "。" if daily_life and not daily_life.endswith("。") else daily_life

            # 沟通风格（2-3个维度，约20字）
            comm_parts = []
            if p.communication.formality_level >= 0.7:
                comm_parts.append("正式")
            elif p.communication.formality_level <= 0.4:
                comm_parts.append("随意")
            if p.communication.directness >= 0.75:
                comm_parts.append("直接")
            if p.communication.humor_usage >= 0.5:
                comm_parts.append("幽默")
            if p.communication.emotional_expressiveness >= 0.65:
                comm_parts.append("情感外露")
            communication_line = f"沟通：{'、'.join(comm_parts[:3])}。" if comm_parts else ""

            # 组装：分层输出，保证每段完整
            profile_lines = [identity_line]
            if personality_line:
                profile_lines.append(personality_line)
            if daily_line:
                profile_lines.append(daily_line)
            if communication_line:
                profile_lines.append(communication_line)

            parts.append(" ".join(profile_lines))

        # 1. 关系上下文 - 使用持久化的 runtime_state
        if self.runtime_state.relationships:
            rel_ctx = build_relationship_context(self.runtime_state, self.other_agent_names, top_k=2)
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

        # 3. 从反思更新关系 - 使用持久化的 runtime_state，写回 GAWorld
        if self._gaworld_agent and social_partners:
            update_relationships_from_reflection(
                self.runtime_state,
                reflection_text,
                social_partners,
                current_day,
            )
            # 同步回 GAWorld agent["relationships"]
            self._sync_relationships_to_gaworld()

    def _sync_relationships_to_gaworld(self) -> None:
        """将 runtime_state.relationships 同步回 GAWorld agent["relationships"]"""
        if not self._gaworld_agent:
            return

        gw_rels = self._gaworld_agent.setdefault("relationships", {})

        for other_id, rel_mem in self.runtime_state.relationships.items():
            key = str(other_id)
            gw_item = gw_rels.setdefault(key, {
                "closeness": 0.5,
                "trust": 0.5,
                "obligation": 0.5,
                "friction": 0.5,
                "last_interaction_day": 0,
            })
            # 从 RelationshipMemory 反向映射到 GAWorld 格式
            # intimacy -> closeness (反推)
            gw_item["closeness"] = min(1.0, rel_mem.intimacy + 0.2)
            gw_item["trust"] = rel_mem.trust
            # pressure -> obligation (反推)
            gw_item["obligation"] = min(1.0, rel_mem.pressure + 0.3)
            # conflict_level -> friction (反推)
            gw_item["friction"] = min(1.0, rel_mem.conflict_level + 0.3)
            # 更新最近互动时间（从 InteractionRecord 中获取最新时间）
            if rel_mem.interaction_history:
                latest_timestamp = max(
                    rec.timestamp for rec in rel_mem.interaction_history
                )
                gw_item["last_interaction_day"] = int(latest_timestamp)

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

def create_life_history_engine(agent_id: int, agent_name: str, profile: Any = None) -> LifeHistoryEngine:
    """创建 LifeHistoryEngine 实例

    Args:
        agent_id: Agent ID
        agent_name: Agent name
        profile: Optional AgentProfile from GAWorld. If not provided, uses default profile.
    """
    from .lh_types import AgentRuntimeState, GoalStack, AffectState
    from .mock_data import create_agent_52_profile

    actual_profile = profile if profile is not None else create_agent_52_profile()
    runtime_state = AgentRuntimeState(
        agent_id=agent_id,
        profile=actual_profile,
        affect=AffectState(),
        goals=GoalStack(),
    )

    return LifeHistoryEngine(
        agent_id=agent_id,
        agent_name=agent_name,
        profile=actual_profile,
        runtime_state=runtime_state,
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