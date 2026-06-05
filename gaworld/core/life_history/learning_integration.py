"""
Life-History Agent 持续学习 (Learning) 集成层

负责：
1. 行为漂移检测 (behavior drift detection)
2. 从错误/成功中学习 (learning from events)
3. 用户偏好适应 (preference adaptation)
4. 策略调整 (strategy adjustment)
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time


class LearningSignal(Enum):
    """学习信号类型"""
    SUCCESS = "success"           # 行动成功达成目标
    FAILURE = "failure"           # 行动未能达成目标
    EXPECTATION_VIOLATION = "expectation_violation"  # 结果与预期不符
    REWARD = "reward"             # 获得正面奖励
    PUNISHMENT = "punishment"     # 获得负面反馈
    NOVELTY = "novelty"           # 遇到新情况
    REPETITION = "repetition"     # 重复同一个动作


@dataclass
class BehaviorSample:
    """行为样本：单次行为的记录"""
    timestamp: float
    activity: str
    action: str
    goal: str
    outcome: str
    success: bool
    reward: float = 0.0
    emotion_delta: float = 0.0  # 情绪变化


@dataclass
class BehaviorDrift:
    """行为漂移记录"""
    detected_at: float
    from_action: str
    to_action: str
    drift_type: str  # "increase", "decrease", "shift"
    magnitude: float  # 0-1, 漂移程度


@dataclass
class LearnedStrategy:
    """学到的策略"""
    situation: str  # 情境描述
    action: str     # 采取的行动
    outcome: str    # 结果
    success: bool   # 是否成功
    confidence: float = 0.5  # 策略置信度
    times_used: int = 1
    last_used: float = 0

    def update_confidence(self, success: bool) -> None:
        """更新策略置信度"""
        if success:
            self.confidence = min(1.0, self.confidence + 0.1)
        else:
            self.confidence = max(0.0, self.confidence - 0.15)
        self.times_used += 1
        self.last_used = time.time()


@dataclass
class LearningState:
    """学习状态：追踪行为模式和策略"""
    # 行为历史
    behavior_history: List[BehaviorSample] = field(default_factory=list)
    max_history: int = 100

    # 行为漂移检测
    recent_drifts: List[BehaviorDrift] = field(default_factory=list)
    drift_detection_window: int = 20  # 检测窗口大小

    # 学到的策略
    learned_strategies: List[LearnedStrategy] = field(default_factory=list)

    # 偏好追踪
    activity_preferences: Dict[str, float] = field(default_factory=dict)  # activity -> preference score

    def add_behavior(self, sample: BehaviorSample) -> None:
        """添加行为样本"""
        self.behavior_history.append(sample)
        if len(self.behavior_history) > self.max_history:
            self.behavior_history = self.behavior_history[-self.max_history:]

    def get_recent_behaviors(self, window: int = 10) -> List[BehaviorSample]:
        """获取最近 N 次行为"""
        return self.behavior_history[-window:]


# =========================================================
# 行为漂移检测
# =========================================================

def detect_behavior_drift(learning_state: LearningState) -> Optional[BehaviorDrift]:
    """
    检测行为漂移

    通过比较最近 N 次行为和之前 M 次行为的 action 分布，
    检测是否有显著的行为模式变化

    Returns:
        BehaviorDrift 如果检测到漂移，否则 None
    """
    history = learning_state.get_recent_behaviors(learning_state.drift_detection_window)
    if len(history) < 10:
        return None

    # 分割为最近一半和之前一半
    mid = len(history) // 2
    recent_half = history[mid:]
    older_half = history[:mid]

    # 统计 action 分布
    recent_actions = [b.action for b in recent_half]
    older_actions = [b.action for b in older_half]

    # 计算每个 action 的频率
    recent_freq: Dict[str, float] = {}
    for a in recent_actions:
        recent_freq[a] = recent_freq.get(a, 0) + 1
    for a in recent_freq:
        recent_freq[a] /= len(recent_actions)

    older_freq: Dict[str, float] = {}
    for a in older_actions:
        older_freq[a] = older_freq.get(a, 0) + 1
    for a in older_freq:
        older_freq[a] /= len(older_actions)

    # 找最大变化
    max_drift = 0.0
    drift_action = ""
    drift_direction = "increase"

    for action, recent_p in recent_freq.items():
        older_p = older_freq.get(action, 0)
        delta = recent_p - older_p
        if abs(delta) > max_drift:
            max_drift = abs(delta)
            drift_action = action
            drift_direction = "increase" if delta > 0 else "decrease"

    # 检测全新的 action (之前没见过的)
    for action, recent_p in recent_freq.items():
        if action not in older_freq and recent_p > 0.2:
            return BehaviorDrift(
                detected_at=time.time(),
                from_action="",
                to_action=action,
                drift_type="shift",
                magnitude=recent_p,
            )

    # 如果变化超过阈值 (20%)，报告漂移
    if max_drift > 0.2:
        return BehaviorDrift(
            detected_at=time.time(),
            from_action=drift_action if drift_direction == "decrease" else "",
            to_action=drift_action if drift_direction == "increase" else "",
            drift_type=drift_direction,
            magnitude=max_drift,
        )

    return None


def get_drift_warning_message(drift: BehaviorDrift) -> str:
    """生成行为漂移警告消息"""
    if drift.drift_type == "shift":
        return f"注意：你最近开始尝试「{drift.to_action}」，这是一个新方向。"
    elif drift.drift_type == "increase":
        return f"注意：你最近更频繁地选择「{drift.to_action}」，可能形成了习惯。"
    elif drift.drift_type == "decrease":
        return f"注意：你最近减少了「{drift.from_action}」，可能需要反思原因。"
    return ""


# =========================================================
# 从经验中学习
# =========================================================

def learn_from_outcome(
    learning_state: LearningState,
    situation: str,
    action: str,
    outcome: str,
    success: bool,
    emotion_delta: float = 0.0,
) -> Optional[LearnedStrategy]:
    """
    从行动结果中学习

    如果是已知情境，更新策略置信度
    如果是新情境，创建新策略
    """
    # 查找是否已有类似策略
    existing = None
    for strategy in learning_state.learned_strategies:
        if strategy.situation == situation and strategy.action == action:
            existing = strategy
            break

    if existing:
        existing.update_confidence(success)
        return None  # 没有新策略，只是更新了现有策略
    else:
        # 创建新策略
        new_strategy = LearnedStrategy(
            situation=situation,
            action=action,
            outcome=outcome,
            success=success,
            confidence=0.6 if success else 0.3,
            last_used=time.time(),
        )
        learning_state.learned_strategies.append(new_strategy)
        return new_strategy


def get_strategy_reminder(
    learning_state: LearningState,
    current_situation: str,
) -> str:
    """
    获取策略提醒

    根据当前情境，查找类似情境的策略经验
    """
    # 查找相关的成功策略
    relevant_strategies = [
        s for s in learning_state.learned_strategies
        if s.situation in current_situation or current_situation in s.situation
    ]

    if not relevant_strategies:
        return ""

    # 按置信度排序
    relevant_strategies.sort(key=lambda s: s.confidence, reverse=True)

    # 取最高置信度的
    best = relevant_strategies[0]

    if best.confidence < 0.4:
        return ""  # 置信度太低，不提供建议

    if best.success:
        return f"你之前在类似情况下采取「{best.action}」成功了，可以参考。"
    else:
        return f"注意：之前类似情况用「{best.action}」效果不好，换个方式试试。"


# =========================================================
# 偏好适应
# =========================================================

def update_preference_from_behavior(
    learning_state: LearningState,
    activity: str,
    success: bool,
    satisfaction: float = 0.5,
) -> None:
    """
    从行为中更新活动偏好

    成功的活动增加偏好，失败的活动降低偏好
    """
    current = learning_state.activity_preferences.get(activity, 0.5)

    if success:
        # 成功：+0.05 (上限 1.0)
        new_pref = min(1.0, current + 0.05 * satisfaction)
    else:
        # 失败：-0.08 (下限 0.0)
        new_pref = max(0.0, current - 0.08 * (1 - satisfaction))

    learning_state.activity_preferences[activity] = new_pref


def get_activity_preference_hint(
    learning_state: LearningState,
    current_activity: str,
) -> str:
    """
    获取活动偏好提示
    """
    pref = learning_state.activity_preferences.get(current_activity, 0.5)

    if pref >= 0.7:
        return f"你对这个活动很擅长/喜欢 ({pref:.0%})"
    elif pref <= 0.3:
        return f"你对这类活动不太感兴趣 ({pref:.0%})"
    return ""


# =========================================================
# 综合学习上下文
# =========================================================

def build_learning_context(
    learning_state: LearningState,
    current_situation: str = "",
    current_activity: str = "",
) -> str:
    """
    构建综合学习上下文字符串

    整合行为漂移、策略提醒、偏好提示
    """
    parts = []

    # 1. 行为漂移检测
    drift = detect_behavior_drift(learning_state)
    if drift:
        warning = get_drift_warning_message(drift)
        if warning:
            parts.append(warning)

    # 2. 策略提醒
    strategy_hint = get_strategy_reminder(learning_state, current_situation)
    if strategy_hint:
        parts.append(strategy_hint)

    # 3. 偏好提示
    pref_hint = get_activity_preference_hint(learning_state, current_activity)
    if pref_hint:
        parts.append(pref_hint)

    return " ".join(parts) if parts else ""


# =========================================================
# 导出
# =========================================================

__all__ = [
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