"""
Life-History Agent 有限理性 (Bounded Rationality) 与 GAWorld 运行时的集成层

负责：
1. 将 GAWorld 的 agent state 同步到 BoundedRationality
2. 在 planning prompt 中注入有限理性约束
3. 表达不确定性、决策限制、认知偏见
"""

from typing import Dict, Any, List, Optional
from .lh_types import BoundedRationality, AgentRuntimeState


# =========================================================
# GAWorld 状态映射到有限理性
# =========================================================

def sync_bounded_rationality_from_agent(
    agent: Dict,
    bounded: BoundedRationality,
) -> None:
    """
    从 GAWorld agent state 同步有限理性参数

    GAWorld agent["state"] 包含:
    - stress: 压力水平 (0-1)
    - energy: 精力水平 (0-1)
    - self_control: 自控力 (0-1)
    - time_pressure: 时间压力 (0-1)
    - cognitive_load 隐式通过其他指标推断
    """
    state = agent.get("state", {})

    # 从 GAWorld state 推断认知负荷
    stress = float(state.get("stress", 0.5))
    fatigue = float(state.get("fatigue_debt", 0.2))
    time_pressure = float(state.get("time_pressure", 0.25))

    # 推断认知负荷 (高压力 + 高疲劳 + 高时间压力 = 高认知负荷)
    inferred_cognitive_load = min(1.0, 0.4 * stress + 0.3 * fatigue + 0.3 * time_pressure)

    # 根据认知负荷调整决策选项数量
    if inferred_cognitive_load > 0.7:
        bounded.max_options_considered = 2  # 高负荷时只考虑2个选项
        bounded.working_memory_limit = 5
    elif inferred_cognitive_load > 0.4:
        bounded.max_options_considered = 3
        bounded.working_memory_limit = 7
    else:
        bounded.max_options_considered = 4  # 低负荷可以多考虑
        bounded.working_memory_limit = 9

    # 根据自控力调整冲动控制
    self_control = float(state.get("self_control", 0.6))
    bounded.cognitive_biases["impulsivity_bias"] = 1.0 - self_control

    # 更新不确定性阈值 (高压力时阈值降低，更容易表达不确定)
    if stress > 0.7:
        bounded.uncertainty_threshold = 0.2  # 高压时更容易说"不确定"
    elif stress > 0.5:
        bounded.uncertainty_threshold = 0.3
    else:
        bounded.uncertainty_threshold = 0.4  # 正常时标准


def get_bounded_rationality_context(
    bounded: BoundedRationality,
    agent_state: Dict,
) -> str:
    """
    为 prompt 构建有限理性上下文字符串

    注入到 planning prompt 中，让 LLM 做出有限理性决策
    """
    parts = []

    # 决策选项限制
    max_opts = bounded.max_options_considered
    if max_opts <= 2:
        parts.append(f"你只能选择【{max_opts}个选项】中的一个，不要想太多。")
    else:
        parts.append(f"你最多考虑【{max_opts}个选项】，不要过度分析。")

    # 时间压力
    time_pressure = float(agent_state.get("time_pressure", 0.25))
    if time_pressure > 0.6:
        parts.append("时间紧迫，不要犹豫太久。")
    elif time_pressure < 0.2:
        parts.append("时间充裕，可以慢慢考虑。")

    # 精力状态
    energy = float(agent_state.get("energy", 0.75))
    if energy < 0.3:
        parts.append("你很累，只做最必要的事。")
    elif energy < 0.5:
        parts.append("你有些疲惫，选择最省力的方案。")

    # 不确定性表达
    stress = float(agent_state.get("stress", 0.5))
    confidence = 1.0 - stress  # 简单假设 stress 高时 confidence 低

    if bounded.should_express_doubt(confidence):
        phrases = bounded.get_uncertainty_phrases()
        import random
        phrase = random.choice(phrases)
        parts.append(f"如果不确定，你可以说：\"{phrase}\"")

    # 认知偏见提醒
    biases = bounded.cognitive_biases
    if biases.get("recency_bias", 0) > 0.6:
        parts.append("注意：你可能过度重视最近的经验，而忽略更早的教训。")
    if biases.get("confirmation_bias", 0) > 0.6:
        parts.append("注意：你可能只看到支持自己观点的信息。")
    if biases.get("impulsivity_bias", 0) > 0.5:
        parts.append("注意：你现在更冲动，避免草率决定。")

    return " ".join(parts) if parts else ""


def should_add_bounded_rationality_to_planning(
    agent_state: Dict,
    activity: str,
) -> bool:
    """
    判断当前是否应该在 planning 中添加有限理性约束

    条件：
    - 高压力 (stress > 0.5)
    - 低精力 (energy < 0.5)
    - 高时间压力 (time_pressure > 0.4)
    - 高疲劳 (fatigue_debt > 0.5)
    """
    state = agent_state or {}

    stress = float(state.get("stress", 0.5))
    energy = float(state.get("energy", 0.75))
    time_pressure = float(state.get("time_pressure", 0.25))
    fatigue = float(state.get("fatigue_debt", 0.2))

    # 任一条件满足就添加
    return (
        stress > 0.5 or
        energy < 0.5 or
        time_pressure > 0.4 or
        fatigue > 0.5
    )


def build_planning_prompt_with_bounded_rationality(
    base_prompt: str,
    bounded_context: str,
) -> str:
    """
    将有限理性上下文注入到 planning prompt

    在 prompt 末尾添加有限理性约束
    """
    if not bounded_context:
        return base_prompt

    # 在 "请输出 JSON" 之前插入有限理性上下文
    lines = base_prompt.split("\n")
    insert_idx = None

    for i, line in enumerate(lines):
        if "请输出 JSON" in line or "要求：" in line:
            insert_idx = i
            break

    if insert_idx is not None:
        bounded_section = f"\n⚠️ 决策约束：{bounded_context}\n"
        lines.insert(insert_idx, bounded_section)
        return "\n".join(lines)

    return base_prompt + f"\n\n⚠️ 决策约束：{bounded_context}"


# =========================================================
# 决策多样性：确保不完全理性
# =========================================================

def get_decision_diversity_hints(
    activity: str,
    recent_actions: List[str],
    bounded: BoundedRationality,
) -> str:
    """
    生成决策多样性提示，避免 Agent 总是选择相同动作

    当 recent_actions 中有重复时添加
    """
    if not recent_actions:
        return ""

    # 检查是否有重复
    action_counts: Dict[str, int] = {}
    for a in recent_actions[-10:]:
        action_counts[a] = action_counts.get(a, 0) + 1

    max_count = max(action_counts.values()) if action_counts else 0

    if max_count >= 3:
        most_common = max(action_counts.items(), key=lambda x: x[1])[0]
        return f"注意：你最近多次选择了「{most_common}」，这次可以考虑不同的方式。"

    return ""


# =========================================================
# 导出
# =========================================================

__all__ = [
    "sync_bounded_rationality_from_agent",
    "get_bounded_rationality_context",
    "should_add_bounded_rationality_to_planning",
    "build_planning_prompt_with_bounded_rationality",
    "get_decision_diversity_hints",
]