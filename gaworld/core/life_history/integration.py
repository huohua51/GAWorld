"""
Life-History Agent 与 GAWorld 运行时的集成层

负责：
1. 将 GAWorld 的 agent["relationships"] 同步到 AgentRuntimeState
2. 将 AgentRuntimeState 的关系上下文注入到 prompt
3. 在反思阶段更新关系记忆
"""

from typing import Dict, Any, Optional, List
from .lh_types import (
    AgentRuntimeState,
    RelationshipMemory,
    RelationshipType,
    InteractionRecord,
    AgentProfile,
    AffectState,
)


# =========================================================
# GAWorld 关系数据模型映射
# =========================================================

# GAWorld 使用: {closeness, trust, obligation, friction}
# Life-History 使用: {trust, intimacy, pressure, conflict_level}

def _map_closeness_to_intimacy(closeness: float) -> float:
    """closeness (0.5基准) -> intimacy"""
    return max(0, min(1, closeness - 0.2))


def _map_friction_to_conflict(friction: float) -> float:
    """friction (0.5基准) -> conflict_level"""
    return max(0, min(1, friction - 0.3))


def _map_obligation_to_pressure(obligation: float) -> float:
    """obligation (0.5基准) -> pressure"""
    return max(0, min(1, obligation - 0.3))


def sync_relationships_to_runtime(
    agent: Dict,
    runtime_state: AgentRuntimeState,
    other_agent_names: Dict[int, str],
    current_day: int,
) -> None:
    """
    将 GAWorld 的 agent["relationships"] 同步到 AgentRuntimeState

    GAWorld relationship format:
    {
        "1": {"closeness": 0.6, "trust": 0.7, "obligation": 0.5, "friction": 0.2, "last_interaction_day": 5},
        "2": {"closeness": 0.4, "trust": 0.3, "obligation": 0.6, "friction": 0.5, "last_interaction_day": 3},
        ...
    }

    Life-History RelationshipMemory:
    {
        other_agent_id: RelationshipMemory(
            trust=0.7, intimacy=0.4, pressure=0.2, conflict_level=0.1,
            relationship_type=RelationshipType.COLLEAGUE,
            interaction_history=[...],
        ),
        ...
    }
    """
    gaworld_rels = agent.get("relationships", {})

    for other_id_str, gw_rel in gaworld_rels.items():
        other_id = int(other_id_str)
        rel = runtime_state.get_relationship(other_id)

        # 映射 GAWorld -> Life-History
        rel.trust = gw_rel.get("trust", 0.5)
        rel.intimacy = _map_closeness_to_intimacy(gw_rel.get("closeness", 0.5))
        rel.pressure = _map_obligation_to_pressure(gw_rel.get("obligation", 0.5))
        rel.conflict_level = _map_friction_to_conflict(gw_rel.get("friction", 0.5))

        # 从名字映射关系类型 (如果知道名字的话)
        other_name = other_agent_names.get(other_id, "")
        if other_name:
            rel.first_met = rel.first_met or f"Day {gw_rel.get('last_interaction_day', current_day)}"

        # 添加交互记录 (如果有的话)
        last_day = gw_rel.get("last_interaction_day", 0)
        if last_day >= current_day - 1:  # 最近1天内有交互
            record = InteractionRecord(
                timestamp=float(current_day),
                interaction_type="social",
                content_summary=f"与 {other_name or other_id} 的最近互动",
                emotional_tone=_infer_emotion_from_relationship(rel),
                agent_id=other_id,
                outcome="neutral",
                trust_change=0.0,  # 已经体现在基础值里了
                intimacy_change=0.0,
            )
            rel.add_interaction(record)


def _infer_emotion_from_relationship(rel: RelationshipMemory) -> float:
    """从关系质量推断交互情绪"""
    # positive: high trust + high intimacy + low conflict
    # negative: low trust + high conflict
    score = (rel.trust - 0.5) + (rel.intimacy - 0.3) - (rel.conflict_level - 0.1)
    return max(-1, min(1, score / 3))


# =========================================================
# 从 AgentRuntimeState 构建关系上下文
# =========================================================

def build_relationship_context(
    runtime_state: AgentRuntimeState,
    other_agent_names: Dict[int, str],
    top_k: int = 3,
) -> str:
    """
    为 prompt 构建关系上下文字符串

    Returns:
        如 "与王思远的关系：信任度高，亲密程度中等，偶有摩擦"
    """
    if not runtime_state.relationships:
        return "最近没有与任何熟人互动。"

    # 按关系强度排序
    sorted_rels = sorted(
        runtime_state.relationships.items(),
        key=lambda x: x[1].trust + x[1].intimacy - x[1].conflict_level,
        reverse=True,
    )

    fragments = []
    for other_id, rel in sorted_rels[:top_k]:
        name = other_agent_names.get(other_id, f"Agent {other_id}")
        ctx = _describe_relationship(rel, name)
        fragments.append(ctx)

    return "；".join(fragments) if fragments else "最近没有与任何熟人互动。"


def _describe_relationship(rel: RelationshipMemory, name: str) -> str:
    """生成单条关系描述"""
    parts = [f"{name}"]

    # 信任描述
    if rel.trust >= 0.7:
        parts.append("信任度高")
    elif rel.trust <= 0.3:
        parts.append("信任度低")
    else:
        parts.append("信任度一般")

    # 亲密描述
    if rel.intimacy >= 0.5:
        parts.append("关系亲密")
    elif rel.intimacy >= 0.3:
        parts.append("关系普通")
    else:
        parts.append("关系疏远")

    # 冲突描述
    if rel.conflict_level >= 0.5:
        parts.append("冲突明显")
    elif rel.conflict_level >= 0.3:
        parts.append("偶有摩擦")
    else:
        parts.append("相处和谐")

    # 压力描述
    if rel.pressure >= 0.5:
        parts.append("感到压力")

    return "，".join(parts)


# =========================================================
# 从反思更新关系
# =========================================================

def update_relationships_from_reflection(
    runtime_state: AgentRuntimeState,
    reflection_text: str,
    social_partners: List[int],
    current_day: int,
) -> None:
    """
    从反思文本推断社交信号，更新关系

    从 reflection_text 中提取情感关键词来更新关系
    """
    text = str(reflection_text or "").lower()

    # 推断信号
    if any(k in text for k in ["满意", "开心", "顺利", "支持", "感谢", "信任"]):
        signal = "positive"
    elif any(k in text for k in ["冲突", "焦虑", "烦躁", "不满", "争执", "失望"]):
        signal = "negative"
    else:
        signal = "neutral"

    # 更新关系 - 仅通过 InteractionRecord，避免双重应用
    for other_id in social_partners:
        rel = runtime_state.get_relationship(other_id)

        # 记录交互（trust_change/intimacy_change 在 add_interaction 中应用）
        record = InteractionRecord(
            timestamp=float(current_day),
            interaction_type="reflection_update",
            content_summary=f"反思中提及",
            emotional_tone=1.0 if signal == "positive" else (-1.0 if signal == "negative" else 0.0),
            agent_id=other_id,
            outcome=signal,
            trust_change=0.02 if signal == "positive" else (-0.03 if signal == "negative" else 0),
            intimacy_change=0.03 if signal == "positive" else (-0.01 if signal == "negative" else 0.01),
        )
        rel.add_interaction(record)


# =========================================================
# 创建 AgentRuntimeState (从 GAWorld agent dict)
# =========================================================

def create_runtime_state_from_agent(
    agent: Dict,
    profile: AgentProfile,
    affect: AffectState,
    relationships: Optional[Dict[int, RelationshipMemory]] = None,
) -> AgentRuntimeState:
    """
    从 GAWorld agent dict 创建 AgentRuntimeState

    注意：这只是创建基础状态，实际的关系同步需要调用 sync_relationships_to_runtime
    """
    from .lh_types import GoalStack, BoundedRationality, ReflectionEntry

    state = AgentRuntimeState(
        agent_id=agent["id"],
        profile=profile,
        affect=affect,
        goals=GoalStack(),  # 从 GAWorld 的 agent["intentions"] 填充
        relationships=relationships or {},
        reflections=[],
        bounded_rationality=BoundedRationality(
            max_options_considered=3,
            decision_time_limit=2.0,
            uncertainty_threshold=0.3,
        ),
    )

    return state


# =========================================================
# 导出
# =========================================================

__all__ = [
    "sync_relationships_to_runtime",
    "build_relationship_context",
    "update_relationships_from_reflection",
    "create_runtime_state_from_agent",
]