"""
生活史型智能体 Mock 数据
为 Agent 52 (郭林峰) 创建完整的 mock 数据
"""

from typing import Dict
from .lh_types import (
    AgentProfile, Identity, LifeHistory, Values, PersonalityTraits,
    CommunicationStyle, AffectState, RelationshipMemory, GoalStack, Goal,
    ReflectionEntry, BoundedRationality, AgentRuntimeState, AffectType
)


def create_agent_52_profile() -> AgentProfile:
    """创建郭林峰(Agent 52)的完整档案"""
    
    identity = Identity(
        agent_id=52,
        name="郭林峰",
        gender="男",
        age=25,
        hukou="外省",
        residence="西湖区·浙大校区",
        occupation="浙江大学社会工作硕士(2024级) + ZephyrNexus创业者",
        role_in_context="AI-HR研究者与创业者"
    )
    
    life_history = LifeHistory(
        key_events=[
            {
                "time": "2024-09",
                "event": "进入浙江大学社会工作硕士专业",
                "significance": 0.8,
                "emotional_tag": "anticipation",
                "unresolved": False
            },
            {
                "time": "2024-06",
                "event": "完成字节跳动第三段实习，获得AI+HR产品开发经验",
                "significance": 0.85,
                "emotional_tag": "pride",
                "unresolved": False
            },
            {
                "time": "2024-01",
                "event": "开始独立开发ZephyrNexus多智能体组织协同平台",
                "significance": 0.9,
                "emotional_tag": "anxiety_and_excitement",
                "unresolved": False
            },
            {
                "time": "2023-06",
                "event": "华中科技大学社会工作+金融双学位毕业，GPA 3.93/4.00",
                "significance": 0.75,
                "emotional_tag": "pride",
                "unresolved": False
            },
            {
                "time": "2022-12",
                "event": "获得省级优秀毕业生称号",
                "significance": 0.6,
                "emotional_tag": "pride",
                "unresolved": False
            },
        ],
        turning_points=[
            {
                "time": "2024-01",
                "before": "只是被动完成导师任务的研究生",
                "after": "独立发起ZephyrNexus项目的创业者",
                "narrative": "从那一刻起，我不再只是学术研究者，而是要把技术转化为真正的社会价值"
            },
            {
                "time": "2024-06",
                "before": "对AI在HR领域应用仅有理论认识",
                "after": "实际开发了多智能体HR助手bot(OpenClaw)",
                "narrative": "字节的实习让我明白，速度优先比完美更重要"
            }
        ],
        unresolved_conflicts=[
            {
                "topic": "学术研究 vs 创业实践的时间分配",
                "since": "2024-01",
                "tension": 0.7,
                "avoidance_level": 0.5
            },
            {
                "topic": "理性驱动 vs 社交情感需求",
                "since": "2023-09",
                "tension": 0.6,
                "avoidance_level": 0.3
            },
            {
                "topic": "ZephyrNexus的成功压力与自我期待",
                "since": "2024-01",
                "tension": 0.8,
                "avoidance_level": 0.4
            }
        ],
        self_narrative="我是一个理性驱动、极度结果导向的人。不用语言证明自己，用数字和结果证明自己。学术训练让我重视严谨，但字节实习让我学会速度优先。在「人+组织+商业」的交汇点创造价值是我最深的驱动力。",
        narrative_patterns=[
            "「清晰的目标，是掌控感的起点」",
            "「数据不会因情绪波动而失真」",
            "「模糊需求即风险，必须前置判断」",
            "「理性决策需锚定可测量结果」"
        ]
    )
    
    values = Values(
        explicit_priorities=[
            "效率 > 质量 > 成本",
            "组织效率 > 个人成就",
            "可量化成果 > 过程体验"
        ],
        implicit_biases={
            "wealth_pursuit_income_seek": 0.5,
            "social_harmony": 0.4,
            "autonomy": 0.6,
            "achievement": 0.8,
            "security": 0.5
        },
        value_conflicts=[
            {"left": "效率", "right": "质量", "typical_choice": "效率（短期内）"},
            {"left": "学术深度", "right": "创业速度", "typical_choice": "视情况而定"},
            {"left": "个人成就", "right": "团队协作", "typical_choice": "团队协作（但会保留个人判断）"}
        ]
    )
    
    personality = PersonalityTraits(
        openness=0.65,
        conscientiousness=0.85,
        extraversion=0.45,
        agreeableness=0.55,
        neuroticism=0.35,
        rationality=0.88,
        result_orientation=0.9,
        impulse_control=0.7,
        stress_response=0.6,
        social_autonomy=0.7,
        contradictions=[
            {"trait1": "完美主义", "trait2": "速度优先", "context_dependent": True},
            {"trait1": "极度理性", "trait2": "对不确定性的焦虑", "context_dependent": True},
            {"trait1": "结果导向", "trait2": "对「人」的价值敏感", "context_dependent": True}
        ]
    )
    
    communication = CommunicationStyle(
        formality_level=0.6,
        emotional_expressiveness=0.35,
        directness=0.75,
        humor_usage=0.25,
        language_patterns=[
            "用数据说话",
            "强调「可量化」「可验证」",
            "避免模糊描述",
            "喜欢用「节点」「追踪」「交付」等词汇"
        ],
        typical_phrases={
            "让我想想": 0.6,
            "设定可验证的交付节点": 0.8,
            "这个我不确定，但": 0.4,
            "推进最重要的一项任务": 0.7,
            "优先设定可验证的交付里程碑": 0.9
        }
    )
    
    return AgentProfile(
        identity=identity,
        life_history=life_history,
        values=values,
        personality=personality,
        communication=communication
    )


def create_agent_52_runtime_state(profile: AgentProfile) -> AgentRuntimeState:
    """创建郭林峰的运行时状态"""
    
    affect = AffectState(
        valence=0.72,
        arousal=0.58,
        primary_emotions={
            AffectType.HOPE: 0.6,
            AffectType.ANXIETY: 0.3,
            AffectType.PRIDE: 0.5
        },
        stress=0.58,
        fatigue=0.2,
        confidence=0.6,
        motivation=0.7,
        attention=0.75,
        energy=0.75,
        hunger=0.25,
        social_need=0.4,
        self_control=0.6,
        time_pressure=0.25,
        cognitive_load=0.4
    )
    
    goals = GoalStack(
        long_term_goals=[
            Goal(
                content="完成ZephyrNexus v1.0发布",
                goal_type="long_term",
                priority=0.9,
                created_at=1735689600,
                deadline=1747104000,  # 2025年
                source="self_set",
                importance_for_self_narrative=0.9
            ),
            Goal(
                content="硕士论文开题顺利通过",
                goal_type="long_term", 
                priority=0.8,
                created_at=1735689600,
                source="social_pressure",
                importance_for_self_narrative=0.7
            )
        ],
        short_term_goals=[
            Goal(
                content="完成AIHR项目关键节点交付",
                goal_type="short_term",
                priority=0.85,
                source="self_set"
            ),
            Goal(
                content="验证3个社区服务需求的可行性",
                goal_type="short_term",
                priority=0.6,
                source="self_set"
            )
        ],
        hidden_goals=[
            Goal(
                content="证明自己能同时做好研究和创业",
                goal_type="hidden",
                priority=0.7,
                is_explicit=False
            )
        ],
        avoidance_goals=[
            Goal(
                content="避免因为时间冲突而必须放弃其中一方",
                goal_type="avoidance",
                priority=0.65,
                is_explicit=False
            )
        ]
    )
    
    bounded = BoundedRationality(
        max_options_considered=3,
        decision_time_limit=2.0,
        uncertainty_threshold=0.3,
        cognitive_biases={
            "recency_bias": 0.7,
            "confirmation_bias": 0.6,
            "availability_heuristic": 0.5,
            "optimism_bias": 0.3
        },
        attention_bounded=True,
        working_memory_limit=7
    )
    
    # 创建与Agent 5(王思远)的关系
    relationship_with_5 = RelationshipMemory(
        other_agent_id=5,
        relationship_type=RelationshipType.COLLEAGUE,
        first_met="2024-09",
        trust=0.6,
        intimacy=0.35,
        pressure=0.3,
        conflict_level=0.1,
        expectations={
            "communication_frequency": 0.5,
            "mutual_support": 0.6
        }
    )
    
    state = AgentRuntimeState(
        agent_id=52,
        profile=profile,
        affect=affect,
        goals=goals,
        relationships={5: relationship_with_5},
        bounded_rationality=bounded
    )
    
    # 添加一些反思历史
    state.reflections = [
        ReflectionEntry(
            timestamp=1735689600,
            event_description="完成AIHR项目关键节点交付",
            emotional_response={"satisfaction": 0.7, "relief": 0.4},
            causal_explanation="internal/stable/global",
            belief_updates=[
                {"before": "我不能同时handle多个项目", "after": "我可以有效管理并行任务", "confidence": 0.7}
            ],
            strategy_adjustments=["下次遇到并行任务，优先设定明确里程碑"],
            behavior_change_tendency=0.3
        ),
        ReflectionEntry(
            timestamp=1735603200,
            event_description="晨跑时思考ZephyrNexus的方向调整",
            emotional_response={"clarity": 0.6, "determination": 0.5},
            causal_explanation="internal/unstable/specific",
            belief_updates=[],
            strategy_adjustments=["继续用跑步来整理思路"],
            behavior_change_tendency=0.1
        )
    ]
    
    return state


def create_mock_scores() -> Dict:
    """创建Agent 52的评估分数（基于当前实现）"""
    return {
        "memory_score": {
            "raw": 17,
            "max": 30,
            "percentage": 56.7,
            "sub_scores": {
                "recall_accuracy": 6,
                "consistency": 7,
                "recency_effect": 4
            }
        },
        "personality_score": {
            "raw": 16,
            "max": 25,
            "percentage": 64.0,
            "sub_scores": {
                "personality_consistency": 8,
                "role_stability": 5,
                "background_coverage": 3
            }
        },
        "affect_score": {
            "raw": 12,  # 已添加情感记忆集成层，待运行时调用
            "max": 20,
            "percentage": 60.0,
            "sub_scores": {
                "emotion_wave": 6,  # AffectState 已有情绪追踪
                "emotional_memory": 3,  # EmotionalMemory 已定义
                "expression_diversity": 3  # AffectType 已有12种情绪
            }
        },
        "bounded_rationality_score": {
            "raw": 8,  # 已完成集成层，待 GAWorld runtime 接入
            "max": 15,
            "percentage": 53.3,
            "sub_scores": {
                "decision_diversity": 4,  # 已添加 diversity hints 生成
                "uncertainty_expression": 2,  # 已添加 phrase selection
                "bounded_options": 2  # 已添加 max_options_considered 跟踪
            }
        },
        "learning_score": {
            "raw": 3,
            "max": 10,
            "percentage": 30.0,
            "sub_scores": {
                "behavior_drift_detection": 2,
                "learning_from_error": 1,
                "preference_adaptation": 0
            }
        },
        "relationship_score": {
            "raw": 4,  # 新增维度，已完成集成层，待 GAWorld runtime 接入
            "max": 20,
            "percentage": 20.0,
            "sub_scores": {
                "relationship_tracking": 2,  # 已定义 RelationshipMemory，但未在运行时调用
                "trust_evolution": 1,  # GAWorld 有 trust 更新，需映射
                "conflict_resolution": 1  # GAWorld 有 friction 更新，需映射
            }
        }
    }


# 导出所有mock创建函数
__all__ = [
    "create_agent_52_profile",
    "create_agent_52_runtime_state",
    "create_mock_scores"
]
