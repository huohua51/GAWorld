"""
生活史型智能体 (Life-History Agent) 核心类型定义

目标：让 Agent 成为一个有生活经历、稳定人格、情绪波动、
关系记忆和有限理性的社会行动者，而非完美理性人。

Human-like 特征：
- 连续性：记忆跨时间连贯
- 矛盾性：有时自相矛盾的选择
- 关系性：与他人的关系影响行为
- 情境性：同一类型事件在不同情境下反应不同
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import time
import uuid


# =========================================================
# 1. AgentProfile - 身份、生活史、价值观、人格特质、表达风格
# =========================================================

@dataclass
class Identity:
    """身份层：我是谁"""
    agent_id: int
    name: str
    gender: str
    age: int
    hukou: str  # 户籍类型：本地/外省/外国
    residence: str  # 居住地
    occupation: str  # 职业身份
    role_in_context: str  # 在仿真场景中的角色

@dataclass
class LifeHistory:
    """生活史：关键经历、转折点、未解决冲突、自我叙事"""
    key_events: List[Dict] = field(default_factory=list)
    # 每项: {"time": "2024-03", "event": "...", "significance": 0.8, "emotional_tag": "proud", "unresolved": False}
    
    turning_points: List[Dict] = field(default_factory=list)
    # 每项: {"time": "...", "before": "...", "after": "...", "narrative": "..."}
    
    unresolved_conflicts: List[Dict] = field(default_factory=list)
    # 每项: {"topic": "...", "since": "...", "tension": 0.7, "avoidance_level": 0.5}
    
    self_narrative: str = ""  # 自我叙事："我是一个...的人"
    
    narrative_patterns: List[str] = field(default_factory=list)
    # 叙事模式：如"我总是..."、"我从来不会..."、"如果...就说明..."

@dataclass
class Values:
    """价值观：优先级排序 + 冲突时的决策倾向"""
    explicit_priorities: List[str] = field(default_factory=list)
    # ["效率 > 质量 > 成本", "人际关系 > 个人成就"]
    
    implicit_biases: Dict[str, float] = field(default_factory=dict)
    # {"wealth_pursuit": 0.7, "social_harmony": 0.5, "autonomy": 0.6}
    
    value_conflicts: List[Dict] = field(default_factory=list)
    # [{"left": "效率", "right": "质量", "typical_choice": "效率"}]

@dataclass
class PersonalityTraits:
    """人格特质：五因素模型 + 独特维度"""
    # Big Five
    openness: float = 0.5  # 开放性
    conscientiousness: float = 0.5  # 尽责性
    extraversion: float = 0.5  # 外向性
    agreeableness: float = 0.5  # 宜人性
    neuroticism: float = 0.5  # 神经质
    
    # 独特维度
    rationality: float = 0.7  # 理性程度 (vs 感性)
    result_orientation: float = 0.8  # 结果导向 (vs 过程导向)
    impulse_control: float = 0.6  # 冲动控制
    stress_response: float = 0.5  # 压力响应风格
    social_autonomy: float = 0.5  # 社交自主性 (vs 群体依赖)
    
    # 矛盾特质 (同一个体内部)
    contradictions: List[Dict] = field(default_factory=list)
    # [{"trait1": "完美主义", "trait2": "拖延倾向", "context_dependent": True}]

@dataclass
class CommunicationStyle:
    """表达风格：说话方式、词汇偏好、情绪表达"""
    formality_level: float = 0.5  # 正式程度 0-1
    emotional_expressiveness: float = 0.5  # 情绪表达程度
    directness: float = 0.6  # 直接程度
    humor_usage: float = 0.3  # 幽默使用频率
    
    language_patterns: List[str] = field(default_factory=list)
    # ["用数据说话", "喜欢用...的句式", "不说..."]
    
    typical_phrases: Dict[str, float] = field(default_factory=dict)
    # {"让我想想": 0.7, "不确定": 0.3, "肯定没问题": 0.2}

@dataclass
class AgentProfile:
    """完整的人格档案"""
    identity: Identity
    life_history: LifeHistory = field(default_factory=LifeHistory)
    values: Values = field(default_factory=Values)
    personality: PersonalityTraits = field(default_factory=PersonalityTraits)
    communication: CommunicationStyle = field(default_factory=CommunicationStyle)
    
    # 用于prompt注入
    def build_personality_prompt(self) -> str:
        return f"""
你是{self.identity.name}，{self.identity.occupation}。
{self.life_history.self_narrative}
性格特征：{self.personality}
说话风格：{self.communication}
价值观：{', '.join(self.values.explicit_priorities)}
"""

    @classmethod
    def from_gaworld_agent(cls, agent: Dict, gender: str = "", hukou: str = "") -> "AgentProfile":
        """
        从 GAWorld 扁平 agent dict 构造 AgentProfile

        用于 build_agent() 中，为每个智能体构建独立的生活史人格档案，
        而不是共用 Agent 52 的 profile。
        """
        identity = Identity(
            agent_id=agent.get("id", 0),
            name=agent.get("name", f"Agent {agent.get('id', '?')}"),
            gender=gender,
            age=int(agent.get("age", 25)),
            hukou=hukou,
            residence=agent.get("living", agent.get("residence", "")),
            occupation=agent.get("job", agent.get("work_style", "")),
            role_in_context=agent.get("job", ""),
        )

        # 从 personality/daily_life 文本推断生活史
        personality_text = agent.get("personality", "")
        job_text = agent.get("job", "")
        values_text = agent.get("values", "")

        # 启发式：从文本关键词推断人格特质（0.0-1.0）
        openness = _infer_trait(personality_text, ["好奇", "开放", "创意", "艺术"], 0.5)
        conscientiousness = _infer_trait(personality_text, ["严谨", "负责", "自律", "计划"], 0.65)
        extraversion = _infer_trait(personality_text, ["外向", "活跃", "社交", "健谈"], 0.45)
        agreeableness = _infer_trait(personality_text, ["友善", "随和", "合作", "信任"], 0.55)
        neuroticism = _infer_trait(personality_text, ["敏感", "焦虑", "情绪化", "神经质"], 0.35)
        rationality = _infer_trait(personality_text, ["理性", "冷静", "逻辑", "务实"], 0.7)
        result_orientation = _infer_trait(personality_text, ["结果导向", "效率", "成就"], 0.7)
        impulse_control = _infer_trait(personality_text, ["自律", "克制", "稳重"], 0.6)

        personality_traits = PersonalityTraits(
            openness=openness,
            conscientiousness=conscientiousness,
            extraversion=extraversion,
            agreeableness=agreeableness,
            neuroticism=neuroticism,
            rationality=rationality,
            result_orientation=result_orientation,
            impulse_control=impulse_control,
        )

        # 从 values 文本提取优先级
        explicit_priorities = [values_text] if values_text else []
        implicit_biases = {
            "achievement": result_orientation,
            "autonomy": _infer_trait(personality_text, ["自主", "独立", "自由"], 0.5),
            "security": _infer_trait(values_text, ["稳定", "安全", "保障"], 0.5),
            "social_harmony": agreeableness,
        }

        values = Values(
            explicit_priorities=explicit_priorities,
            implicit_biases=implicit_biases,
        )

        # 从 daily_life 推断沟通风格
        daily_life_text = agent.get("daily_life", "")
        formality = _infer_trait(job_text, ["研究", "学术", "医生", "律师", "教师"], 0.6, inverse=True)
        directness = _infer_trait(personality_text, ["直接", "果断", "干脆"], 0.65)
        emotional_expr = _infer_trait(personality_text, ["感性", "情绪化", "表达"], 0.4, inverse=True)
        humor = _infer_trait(personality_text, ["幽默", "风趣", "调侃"], 0.3)

        communication = CommunicationStyle(
            formality_level=formality,
            emotional_expressiveness=emotional_expr,
            directness=directness,
            humor_usage=humor,
        )

        # 生活史：从 job 和 personality 文本构建关键事件摘要
        life_history = LifeHistory(
            self_narrative=f"{identity.name}，{identity.occupation}。{personality_text}",
            narrative_patterns=[],
        )

        return cls(
            identity=identity,
            life_history=life_history,
            values=values,
            personality=personality_traits,
            communication=communication,
        )


def _infer_trait(text: str, keywords: List[str], default: float, inverse: bool = False) -> float:
    """从文本关键词启发式推断特质值"""
    if not text:
        return default
    count = sum(1 for kw in keywords if kw in text)
    if count == 0:
        return default
    # 线性映射：1个关键词命中 => default+0.15, 2+ => default+0.25, 3+ => default+0.35
    delta = min(0.35, 0.1 + count * 0.1)
    value = default + delta
    if inverse:
        value = 1.0 - min(1.0, value)
    return round(min(1.0, max(0.0, value)), 2)


# =========================================================
# 2. AffectState - 情绪、压力、疲劳、自信、动机、注意力
# =========================================================

class AffectType(Enum):
    JOY = "joy"
    PRIDE = "pride"
    RELIEF = "relief"
    HOPE = "hope"
    ANXIETY = "anxiety"
    FEAR = "fear"
    SADNESS = "sadness"
    ANGER = "anger"
    DISGUST = "disgust"
    SHAME = "shame"
    REGRET = "regret"
    ENVY = "envy"
    NEUTRAL = "neutral"

@dataclass
class AffectState:
    """情感状态：多维度情绪追踪"""
    # 基础情绪维度 (0-1)
    valence: float = 0.5  # 效价：消极-积极
    arousal: float = 0.5  # 激活度：平静-激活
    
    # 具体情绪强度
    primary_emotions: Dict[AffectType, float] = field(default_factory=dict)
    # {AffectType.JOY: 0.6, AffectType.ANXIETY: 0.3}
    
    # 功能状态
    stress: float = 0.5  # 主观压力
    fatigue: float = 0.3  # 疲劳程度
    confidence: float = 0.6  # 自信程度
    motivation: float = 0.7  # 动机强度
    attention: float = 0.8  # 注意力集中度
    
    # 身体状态
    energy: float = 0.7  # 精力水平
    hunger: float = 0.3  # 饥饿程度
    social_need: float = 0.4  # 社交需求
    
    # 元认知
    self_control: float = 0.6  # 自我控制力
    time_pressure: float = 0.2  # 时间紧迫感
    cognitive_load: float = 0.4  # 认知负荷
    
    # 情绪波动追踪
    emotion_history: List[Dict] = field(default_factory=list)
    # [{"timestamp": 1234567890, "emotion": "anxiety", "intensity": 0.6, "trigger": "..."}]
    
    def get_dominant_emotion(self) -> Tuple[AffectType, float]:
        """获取当前主导情绪"""
        if not self.primary_emotions:
            return AffectType.NEUTRAL, 0.5
        return max(self.primary_emotions.items(), key=lambda x: x[1])
    
    def should_express_uncertainty(self) -> bool:
        """根据状态判断是否应该表达不确定性"""
        # 低自信 + 高认知负荷 = 应该表达不确定
        return self.confidence < 0.5 or self.cognitive_load > 0.7
    
    def is_under_stress(self) -> bool:
        return self.stress > 0.7 or self.fatigue > 0.7


# =========================================================
# 3. RelationshipMemory - 与其他Agent的关系记录
# =========================================================

class RelationshipType(Enum):
    STRANGER = "stranger"
    ACQUAINTANCE = "acquaintance"
    COLLEAGUE = "colleague"
    FRIEND = "friend"
    CLOSE_FRIEND = "close_friend"
    FAMILY = "family"
    ROMANTIC = "romantic"
    CONFLICT = "conflict"

@dataclass
class InteractionRecord:
    """单次交互记录"""
    timestamp: float
    interaction_type: str  # "chat", "collaboration", "conflict", "support"
    content_summary: str
    emotional_tone: float  # -1 (negative) to 1 (positive)
    agent_id: int  # 对方
    outcome: str  # "positive", "negative", "neutral"
    trust_change: float = 0.0  # 本次交互对信任的影响
    intimacy_change: float = 0.0  # 本次交互对亲密的影响

@dataclass
class RelationshipMemory:
    """与其他Agent的关系记忆"""
    other_agent_id: int
    
    # 关系基本属性
    relationship_type: RelationshipType = RelationshipType.STRANGER
    first_met: Optional[str] = None
    
    # 关系质量维度 (0-1)
    trust: float = 0.5  # 信任度
    intimacy: float = 0.3  # 亲密程度
    pressure: float = 0.2  # 压力程度 (来自对方)
    conflict_level: float = 0.1  # 冲突程度
    support_provided: float = 0.3  # 支持程度
    competition_level: float = 0.2  # 竞争程度
    
    # 未解决的议题
    unresolved_issues: List[Dict] = field(default_factory=list)
    # [{"topic": "...", "since": "...", "tension": 0.6}]
    
    # 交互历史摘要
    interaction_history: List[InteractionRecord] = field(default_factory=list)
    # 最近10次交互的摘要
    
    # 关系期望
    expectations: Dict[str, float] = field(default_factory=dict)
    # {"communication_frequency": 0.5, "mutual_support": 0.6}
    
    def add_interaction(self, record: InteractionRecord):
        self.interaction_history.append(record)
        # 保持最近20条
        if len(self.interaction_history) > 20:
            self.interaction_history = self.interaction_history[-20:]
        
        # 更新关系质量
        self.trust = max(0, min(1, self.trust + record.trust_change))
        self.intimacy = max(0, min(1, self.intimacy + record.intimacy_change))
        
        if record.outcome == "negative":
            self.conflict_level = min(1, self.conflict_level + 0.1)
    
    def get_relationship_summary(self) -> str:
        return f"{self.relationship_type.value}: trust={self.trust:.2f}, intimacy={self.intimacy:.2f}, conflict={self.conflict_level:.2f}"


# =========================================================
# 4. GoalStack - 目标栈：多层次目标管理
# =========================================================

class GoalType(Enum):
    LONG_TERM = "long_term"  # 长期愿景
    SHORT_TERM = "short_term"  # 当前任务
    HIDDEN = "hidden"  # 隐藏目标
    AVOIDANCE = "avoidance"  # 逃避目标
    CONFLICTING = "conflicting"  # 冲突目标

@dataclass
class Goal:
    """单个目标"""
    goal_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: str = ""
    goal_type: GoalType = GoalType.SHORT_TERM
    
    priority: float = 0.5  # 优先级 0-1
    progress: float = 0.0  # 完成度 0-1
    
    created_at: float = field(default_factory=time.time)
    deadline: Optional[float] = None
    
    # 目标属性
    is_explicit: bool = True  # 是否明确知道
    is_acknowledged: bool = True  # 是否承认
    is_active: bool = True  # 是否活跃
    
    # 冲突标注
    conflicts_with: Optional[str] = None  # 冲突目标ID
    
    # 元数据
    source: str = ""  # "self_set", "social_pressure", "system"
    importance_for_self_narrative: float = 0.5  # 对自我叙事的重要程度
    
    def __str__(self):
        return f"[{self.goal_type.value}] {self.content[:30]}... (p={self.priority:.2f})"

@dataclass
class GoalStack:
    """目标栈：管理多层目标"""
    long_term_goals: List[Goal] = field(default_factory=list)
    short_term_goals: List[Goal] = field(default_factory=list)
    hidden_goals: List[Goal] = field(default_factory=list)
    avoidance_goals: List[Goal] = field(default_factory=list)
    conflicting_pairs: List[Tuple[str, str]] = field(default_factory=list)
    
    active_goal_id: Optional[str] = None
    
    def get_active_goal(self) -> Optional[Goal]:
        if self.active_goal_id:
            for g in self.all_goals():
                if g.goal_id == self.active_goal_id:
                    return g
        # 否则返回优先级最高的
        return max(self.all_goals(), key=lambda g: g.priority, default=None)
    
    def all_goals(self) -> List[Goal]:
        return self.long_term_goals + self.short_term_goals + self.hidden_goals + self.avoidance_goals
    
    def add_goal(self, goal: Goal):
        if goal.goal_type == GoalType.LONG_TERM:
            self.long_term_goals.append(goal)
        elif goal.goal_type == GoalType.SHORT_TERM:
            self.short_term_goals.append(goal)
        elif goal.goal_type == GoalType.HIDDEN:
            self.hidden_goals.append(goal)
        elif goal.goal_type == GoalType.AVOIDANCE:
            self.avoidance_goals.append(goal)
        
        if goal.conflicts_with:
            self.conflicting_pairs.append((goal.goal_id, goal.conflicts_with))
        
        # 设置为活跃
        self.active_goal_id = goal.goal_id
    
    def get_conflicting_goals(self, goal_id: str) -> List[Goal]:
        conflicting_ids = [other_id for (a, b) in self.conflicting_pairs 
                         for other_id in (a, b) if a == goal_id or b == goal_id]
        return [g for g in self.all_goals() if g.goal_id in conflicting_ids]


# =========================================================
# 5. ReflectionEntry - 事件后的反思记录
# =========================================================

@dataclass
class ReflectionEntry:
    """反思条目：事件后的情绪反应、解释、自我信念更新和未来策略"""
    reflection_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    # 事件信息
    timestamp: float = field(default_factory=time.time)
    event_description: str = ""
    
    # 情绪反应
    emotional_response: Dict[str, float] = field(default_factory=dict)
    # {"frustration": 0.7, "determination": 0.4}
    
    # 解释风格
    causal_explanation: str = ""
    # "external attribution" vs "internal attribution"
    # "stable cause" vs "unstable cause"  
    # "global cause" vs "specific cause"
    
    # 自我信念更新
    belief_updates: List[Dict] = field(default_factory=list)
    # [{"before": "...", "after": "...", "confidence": 0.6}]
    
    # 策略调整
    strategy_adjustments: List[str] = field(default_factory=list)
    # ["下次遇到类似情况应该..."]
    
    # 反思深度
    depth_score: float = 0.5  # 反思深度 0-1
    
    # 对后续行为的影响
    behavior_change_tendency: float = 0.0  # -1 (avoid) to 1 (repeat)
    
    def get_summary(self) -> str:
        return f"[{time.strftime('%m-%d %H:%M', time.localtime(self.timestamp))}] {self.event_description[:50]}... -> {list(self.emotional_response.keys())[0] if self.emotional_response else 'neutral'}"


# =========================================================
# 6. BoundedRationality - 有限理性约束
# =========================================================

@dataclass
class BoundedRationality:
    """有限理性：约束决策过程"""
    max_options_considered: int = 3  # 最多考虑选项数
    decision_time_limit: float = 2.0  # 决策时间限制(秒)
    
    uncertainty_threshold: float = 0.3  # 表达不确定性的阈值
    
    # 认知偏见
    cognitive_biases: Dict[str, float] = field(default_factory=dict)
    # {"recency_bias": 0.7, "confirmation_bias": 0.6, "availability_heuristic": 0.5}
    
    # 有限注意力的表现
    attention_bounded: bool = True
    working_memory_limit: int = 7  # Miller's 7 ± 2
    
    def should_express_doubt(self, confidence: float) -> bool:
        """判断是否应该表达怀疑"""
        return confidence < (1 - self.uncertainty_threshold)
    
    def get_uncertainty_phrases(self) -> List[str]:
        """获取不确定性表达短语"""
        return [
            "这个我不确定，但...",
            "可能还有更好的方案...",
            "让我想想...",
            "我有点拿不准...",
            "也许可以这样...",
        ]


# =========================================================
# 7. AgentRuntimeState - Agent运行时状态整合
# =========================================================

@dataclass
class AgentRuntimeState:
    """Agent运行时状态：整合所有子系统"""
    agent_id: int
    
    # 子系统状态
    profile: AgentProfile
    affect: AffectState = field(default_factory=AffectState)
    goals: GoalStack = field(default_factory=GoalStack)
    
    # 关系记忆
    relationships: Dict[int, RelationshipMemory] = field(default_factory=dict)
    # other_agent_id -> RelationshipMemory
    
    # 反思历史
    reflections: List[ReflectionEntry] = field(default_factory=list)
    
    # 有限理性
    bounded_rationality: BoundedRationality = field(default_factory=BoundedRationality)
    
    def add_reflection(self, entry: ReflectionEntry):
        self.reflections.append(entry)
        # 保持最近50条
        if len(self.reflections) > 50:
            self.reflections = self.reflections[-50:]
    
    def get_relationship(self, other_id: int) -> RelationshipMemory:
        if other_id not in self.relationships:
            self.relationships[other_id] = RelationshipMemory(other_agent_id=other_id)
        return self.relationships[other_id]
    
    def build_runtime_context(self) -> Dict:
        """构建运行时上下文，用于prompt注入"""
        dominant_emotion, intensity = self.affect.get_dominant_emotion()
        
        return {
            "agent_id": self.agent_id,
            "name": self.profile.identity.name,
            "current_emotion": dominant_emotion.value,
            "emotion_intensity": intensity,
            "stress_level": self.affect.stress,
            "fatigue_level": self.affect.fatigue,
            "confidence": self.affect.confidence,
            "active_goal": str(self.goals.get_active_goal()) if self.goals.get_active_goal() else "None",
            "relationship_summary": {
                other_id: rm.get_relationship_summary() 
                for other_id, rm in self.relationships.items()
            },
            "recent_reflections": [r.get_summary() for r in self.reflections[-3:]],
            "should_express_uncertainty": self.affect.should_express_uncertainty(),
            "is_under_stress": self.affect.is_under_stress(),
        }


# =========================================================
# 8. AgentRuntimeLoop - 生活史Agent的运行时循环
# =========================================================

class AgentRuntimeLoop:
    """
    生活史Agent的运行时循环：
    perceive → retrieve_memory → appraise_event → update_affect → 
    bounded_plan → act_or_speak → reflect → consolidate_memory
    """
    
    def __init__(self, state: AgentRuntimeState):
        self.state = state
    
    def perceive(self, event: Dict) -> Dict:
        """
        感知阶段：解析环境事件
        - 识别事件类型
        - 提取相关信息
        - 生成感知文本
        """
        event_type = event.get("type", "unknown")
        perception = {
            "event": event,
            "perceived_as": event_type,
            "relevance_to_goals": self._assess_goal_relevance(event),
            "social_cue": self._extract_social_cue(event),
        }
        return perception
    
    def retrieve_memory(self, perception: Dict) -> List[str]:
        """
        记忆召回阶段：
        - 短期记忆优先
        - 近因评分
        - 情境匹配
        """
        # 返回相关记忆片段
        memories = []
        # TODO: 实现实际召回逻辑
        return memories
    
    def appraise_event(self, perception: Dict, memories: List[str]) -> Dict:
        """
        事件评估：
        - 判断对自身的影响
        - 识别情绪触发点
        - 评估与现有目标的关系
        """
        appraisal = {
            "impact": "neutral",  # positive / negative / neutral
            "emotion_triggered": None,
            "goal_relevance": 0.5,
            "control_assessment": 0.5,  # 能控程度
            "coping_possible": True,
        }
        return appraisal
    
    def update_affect(self, appraisal: Dict) -> AffectState:
        """
        更新情感状态：
        - 根据评估结果调整情绪
        - 更新压力、疲劳等
        """
        # 更新逻辑
        return self.state.affect
    
    def bounded_plan(self, perception: Dict, appraisal: Dict) -> Dict:
        """
        有限理性规划：
        - 限制选项数量
        - 考虑不确定性
        - 生成可行计划
        """
        # 生成最多max_options_considered个选项
        plan = {
            "options": [],
            "selected": None,
            "uncertainty_expressed": False,
            "reasoning": "",
        }
        
        # 如果应该表达不确定性
        if self.state.bounded_rationality.should_express_doubt(
            self.state.affect.confidence
        ):
            plan["uncertainty_expressed"] = True
        
        return plan
    
    def act_or_speak(self, plan: Dict) -> str:
        """
        执行或说话：
        - 根据计划执行动作
        - 生成行为文本
        """
        action = plan.get("selected", {}).get("action", "")
        return action
    
    def reflect(self, action: str, outcome: Dict) -> ReflectionEntry:
        """
        反思阶段：
        - 分析行为结果
        - 更新自我信念
        - 调整未来策略
        """
        reflection = ReflectionEntry(
            event_description=action,
            emotional_response={"result_satisfaction": outcome.get("satisfaction", 0.5)},
        )
        
        self.state.add_reflection(reflection)
        return reflection
    
    def consolidate_memory(self, perception: Dict, action: str, reflection: ReflectionEntry):
        """
        记忆整合：
        - 保存事件
        - 更新重要性评分
        - 提取教训
        """
        # 整合逻辑
        pass


# =========================================================
# 导出
# =========================================================

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
]
