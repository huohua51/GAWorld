"""
Life-History Agent 情感记忆 (Emotional Memory) 集成层

负责：
1. 记录情感事件 (emotional_event)
2. 情感记忆衰减 (emotional_event decay)
3. 从过去情感事件触发反应
4. 与 GAWorld 状态同步
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time


class EmotionalEventType(Enum):
    """情感事件类型"""
    SUCCESS = "success"          # 成功/成就感
    FAILURE = "failure"          # 失败/挫折
    SOCIAL_SUPPORT = "social_support"   # 社交支持
    SOCIAL_CONFLICT = "social_conflict"  # 社交冲突
    ACHIEVEMENT = "achievement"  # 成就事件
    LOSS = "loss"                # 失去/丧失
    THREAT = "threat"            # 威胁/危险
    RELIEF = "relief"            # 缓解/释然
    HOPE = "hope"                # 希望/期待
    FEAR = "fear"                # 恐惧/担忧
    JOY = "joy"                  # 快乐/愉悦
    SADNESS = "sadness"          # 悲伤/失落


@dataclass
class EmotionalEvent:
    """情感事件：带有持久影响的单次情感体验"""
    timestamp: float
    event_type: EmotionalEventType
    intensity: float  # 0-1

    # 事件描述
    trigger: str  # 触发源，如 "完成ZephyrNexus关键功能"
    description: str  # 自然语言描述

    # 情感反应
    emotion_before: str  # 事件前的情绪
    emotion_after: str   # 事件后的情绪

    # 衰减
    decay_rate: float = 0.95  # 每次衰减率
    current_intensity: float = 1.0  # 当前强度 (会随时间衰减)

    # 关联
    related_agents: List[int] = field(default_factory=list)  # 涉及的 agent id
    related_goals: List[str] = field(default_factory=list)  # 相关的 goal id

    def decay(self) -> None:
        """衰减情感记忆强度"""
        self.current_intensity *= self.decay_rate
        if self.current_intensity < 0.1:
            self.current_intensity = 0.0

    def is_active(self) -> bool:
        """情感事件是否还有效"""
        return self.current_intensity > 0.1


@dataclass
class EmotionalMemory:
    """情感记忆：追踪重要的情感事件及其衰减"""
    events: List[EmotionalEvent] = field(default_factory=list)
    max_events: int = 50  # 最多保留事件数

    def add_event(self, event: EmotionalEvent) -> None:
        """添加情感事件"""
        self.events.append(event)
        # 保持最近 max_events 条
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]

    def decay_all(self) -> None:
        """对所有事件进行衰减"""
        for event in self.events:
            event.decay()
        # 清理不活跃的事件
        self.events = [e for e in self.events if e.is_active()]

    def get_recent_events(self, days: int = 7, min_intensity: float = 0.2) -> List[EmotionalEvent]:
        """获取最近 N 天的高强度情感事件"""
        cutoff = time.time() - days * 86400
        return [
            e for e in self.events
            if e.timestamp > cutoff and e.current_intensity >= min_intensity
        ]

    def get_events_by_type(self, event_type: EmotionalEventType) -> List[EmotionalEvent]:
        """按类型筛选情感事件"""
        return [e for e in self.events if e.event_type == event_type]

    def get_emotional_summary(self) -> str:
        """生成情感记忆摘要 (用于 prompt)"""
        recent = self.get_recent_events(days=3)
        if not recent:
            return "最近没有强烈的情感事件。"

        # 按 intensity 排序
        recent.sort(key=lambda e: e.current_intensity, reverse=True)

        parts = []
        for event in recent[:3]:
            intensity_label = "强烈" if event.current_intensity > 0.7 else "中等" if event.current_intensity > 0.4 else "轻微"
            parts.append(f"{intensity_label}的{event.event_type.value}感({event.description})")

        return "；".join(parts)


# =========================================================
# GAWorld 状态同步
# =========================================================

def infer_emotional_event_from_gaworld(
    agent_id: int,
    activity: str,
    plan_text: str,
    action: str,
    outcome: str,
    reflection_text: str,
    state_before: Dict,
    state_after: Dict,
    social_partners: List[int],
    current_day: int,
) -> Optional[EmotionalEvent]:
    """
    从 GAWorld 的事件流中推断情感事件

    Returns:
        EmotionalEvent 如果检测到强烈的情感变化，否则 None
    """
    emotion_before = float(state_before.get("emotion", 0.5))
    emotion_after = float(state_after.get("emotion", 0.5))
    stress_before = float(state_before.get("stress", 0.5))
    stress_after = float(state_after.get("stress", 0.5))

    emotion_delta = emotion_after - emotion_before
    stress_delta = stress_after - stress_before

    # 检测显著的正向变化
    if emotion_delta > 0.2 or stress_delta < -0.2:
        event_type = EmotionalEventType.SUCCESS if "完成" in outcome or "成功" in outcome else EmotionalEventType.JOY
        description = outcome[:50] if outcome else activity
        intensity = min(1.0, abs(emotion_delta) + abs(stress_delta))

        return EmotionalEvent(
            timestamp=float(current_day * 86400),  # 简化：用天作为时间戳
            event_type=event_type,
            intensity=intensity,
            trigger=activity,
            description=description,
            emotion_before=f"情绪值{emotion_before:.2f}",
            emotion_after=f"情绪值{emotion_after:.2f}",
            related_agents=social_partners,
        )

    # 检测显著的负向变化
    if emotion_delta < -0.2 or stress_delta > 0.2:
        event_type = EmotionalEventType.FAILURE if "失败" in outcome or "挫折" in outcome else EmotionalEventType.SADNESS
        description = outcome[:50] if outcome else activity
        intensity = min(1.0, abs(emotion_delta) + abs(stress_delta))

        return EmotionalEvent(
            timestamp=float(current_day * 86400),
            event_type=event_type,
            intensity=intensity,
            trigger=activity,
            description=description,
            emotion_before=f"情绪值{emotion_before:.2f}",
            emotion_after=f"情绪值{emotion_after:.2f}",
            related_agents=social_partners,
        )

    return None


def get_emotional_context_from_memory(
    emotional_memory: EmotionalMemory,
    current_activity: str,
    current_stress: float,
) -> str:
    """
    从情感记忆构建上下文，注入到 prompt

    根据当前活动和压力水平，查找相关的情感记忆
    """
    recent = emotional_memory.get_recent_events(days=7, min_intensity=0.3)

    if not recent:
        return ""

    # 检查是否有与当前活动相关的情感记忆
    related = []
    for event in recent:
        if (event.current_intensity > 0.5 and
            (current_activity in event.description or
             event.trigger in current_activity)):
            related.append(event)

    if not related:
        return ""

    # 生成情感上下文
    parts = ["情感记忆提醒："]
    for event in related[:2]:
        if event.event_type in [EmotionalEventType.SUCCESS, EmotionalEventType.ACHIEVEMENT, EmotionalEventType.JOY]:
            parts.append(f"你之前因{event.description}感到成功，这段经历现在给你信心；")
        elif event.event_type in [EmotionalEventType.FAILURE, EmotionalEventType.LOSS]:
            parts.append(f"你之前在{event.description}中受挫，这让你对类似情境有些顾虑；")
        elif event.event_type == EmotionalEventType.SOCIAL_CONFLICT:
            parts.append(f"你之前与某人的互动不愉快，这影响了你的社交情绪；")

    return "".join(parts)


# =========================================================
# 情感记忆衰减调度
# =========================================================

def decay_emotional_memory_if_needed(
    emotional_memory: EmotionalMemory,
    last_decay_day: Optional[int],
    current_day: int,
    decay_interval: int = 1,
) -> bool:
    """
    检查是否需要对情感记忆进行衰减

    Returns:
        True 如果执行了衰减
    """
    if last_decay_day is None:
        return False

    if current_day - last_decay_day >= decay_interval:
        emotional_memory.decay_all()
        return True

    return False


# =========================================================
# 导出
# =========================================================

__all__ = [
    "EmotionalEventType",
    "EmotionalEvent",
    "EmotionalMemory",
    "infer_emotional_event_from_gaworld",
    "get_emotional_context_from_memory",
    "decay_emotional_memory_if_needed",
]