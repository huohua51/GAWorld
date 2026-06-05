# 生活史型智能体 (Life-History Agent) 架构说明

> 生成日期：2026-05-24  
> 目标：让 Agent 成为一个有生活经历、稳定人格、情绪波动、关系记忆和有限理性的社会行动者

---

## 一、设计原则

1. **不完美理性**：Agent 不是完美理性人，有认知偏见、有限注意力和决策限制
2. **行为一致性**：记忆和人格跨时间连贯，但也会出现矛盾行为
3. **关系性**：与其他 Agent 的关系（信任、冲突、支持）影响行为
4. **情境性**：同一类型事件在不同情境下反应不同
5. **最小侵入**：不大规模重构现有系统，先用 mock 数据和 eval 脚本验证

---

## 二、六维评估体系

### 2.1 维度定义

| 维度 | 权重 | 满分 | 说明 |
|------|------|------|------|
| memory_score | 25% | 30 | 分层记忆 + 近因评分 + 召回准确率 |
| personality_score | 20% | 25 | 人格一致性 + 角色稳定性 + 背景覆盖 |
| affect_score | 20% | 20 | 情绪波动 + 情感记忆 + 表达多样性 |
| bounded_rationality_score | 15% | 15 | 决策多样性 + 不确定性表达 + 选项限制 |
| learning_score | 10% | 10 | 行为漂移检测 + 从错误学习 + 偏好适应 |
| relationship_score | 10% | 20 | 关系追踪 + 信任演变 + 冲突解决 |

### 2.2 评分公式

```
HumanScore = Σ(维度百分比 × 权重) × 100
```

### 2.3 评级标准

| 分数 | 评级 | 说明 |
|------|------|------|
| 90-100 | 优秀 | 接近真人 |
| 70-89 | 良好 | 明显人类特征 |
| 50-69 | 一般 | 部分人类特征 |
| <50 | 不足 | 明显机器感 |

---

## 三、核心数据结构

### 3.1 AgentProfile

```python
@dataclass
class AgentProfile:
    identity: Identity           # 身份：ID、姓名、职业
    life_history: LifeHistory    # 生活史：关键事件、转折点、未解决冲突
    values: Values              # 价值观：优先级排序、冲突倾向
    personality: PersonalityTraits  # 人格特质：Big5 + 矛盾特质
    communication: CommunicationStyle  # 表达风格：正式度、幽默、词汇偏好
```

### 3.2 AffectState

```python
@dataclass
class AffectState:
    valence: float              # 效价：消极-积极
    arousal: float              # 激活度：平静-激活
    primary_emotions: Dict[AffectType, float]  # 具体情绪强度
    stress: float               # 压力
    fatigue: float             # 疲劳
    confidence: float          # 自信
    motivation: float          # 动机
    attention: float            # 注意力
```

### 3.3 RelationshipMemory

```python
@dataclass
class RelationshipMemory:
    other_agent_id: int
    relationship_type: RelationshipType  # stranger/acquaintance/colleague/friend/conflict
    trust: float               # 信任度 0-1
    intimacy: float           # 亲密程度 0-1
    conflict_level: float     # 冲突程度 0-1
    interaction_history: List[InteractionRecord]  # 交互历史
```

### 3.4 GoalStack

```python
@dataclass
class GoalStack:
    long_term_goals: List[Goal]
    short_term_goals: List[Goal]
    hidden_goals: List[Goal]    # 隐藏目标
    avoidance_goals: List[Goal]  # 逃避目标
    conflicting_pairs: List[Tuple[str, str]]  # 冲突目标对
```

### 3.5 BoundedRationality

```python
@dataclass
class BoundedRationality:
    max_options_considered: int = 3  # 最多考虑选项数
    decision_time_limit: float = 2.0  # 决策时间限制
    uncertainty_threshold: float = 0.3  # 表达不确定性的阈值
    cognitive_biases: Dict[str, float]  # 认知偏见
```

---

## 四、Agent Runtime Loop

### 4.1 七阶段循环

```
perceive → retrieve_memory → appraise_event → update_affect → 
bounded_plan → act_or_speak → reflect → consolidate_memory
```

| 阶段 | 输入 | 输出 | 说明 |
|------|------|------|------|
| perceive | 环境事件 | 感知文本 | 解析事件、识别类型、提取信息 |
| retrieve_memory | 感知 + 当前状态 | 相关记忆 | 短期记忆优先 + 近因评分 |
| appraise_event | 感知 + 记忆 | 评估结果 | 判断影响、情绪触发、目标关联 |
| update_affect | 评估结果 | 更新后状态 | 调整情绪、压力、疲劳 |
| bounded_plan | 评估 + 状态 | 行动计划 | 限制选项、表达不确定、选择行动 |
| act_or_speak | 计划 | 行为文本 | 执行动作、生成响应 |
| reflect | 行为 + 结果 | 反思条目 | 分析结果、更新信念、调整策略 |
| consolidate_memory | 全部 | 记忆更新 | 保存事件、更新权重、提取教训 |

### 4.2 有限理性约束

```python
def bounded_plan(self, perception, appraisal):
    # 1. 限制选项数量
    options = generate_options(max_count=self.state.bounded_rationality.max_options_considered)
    
    # 2. 考虑认知偏见
    options = apply_cognitive_biases(options, self.state.bounded_rationality.cognitive_biases)
    
    # 3. 评估不确定性
    if self.state.affect.should_express_uncertainty():
        plan["uncertainty_phrases"] = self.state.bounded_rationality.get_uncertainty_phrases()
    
    # 4. 选择（不一定是最优）
    plan["selected"] = choose_satisficing(options)  # 而非 optimize
```

---

## 五、文件结构

```
gaworld/core/life_history/
├── __init__.py           # 模块导出
├── lh_types.py           # 核心类型定义（624行）
└── mock_data.py          # Agent 52 mock数据（387行）

eval/
└── life_history_eval.py  # 评估脚本（340行）

docs/superpowers/specs/
├── 2026-05-24-life-history-agent-architecture.md  # 本文档
└── 2026-05-10-multiagent-humanlike-evaluation.md    # 原始评估文档
```

---

## 六、Agent 52 (郭林峰) 当前评估

### 6.1 六维得分

| 维度 | 得分 | 百分比 | 评级 |
|------|------|--------|------|
| 记忆系统 | 17/30 | 56.7% | ⚠️ 一般 |
| 人格角色 | 16/25 | 64.0% | ⚠️ 一般 |
| 情感层 | 9/20 | 45.0% | ❌ 不足 |
| 有限理性 | 5/15 | 33.3% | ❌ 不足 |
| 持续学习 | 3/10 | 30.0% | ❌ 不足 |
| 关系记忆 | 0/20 | 0.0% | ❌ 完全缺失 |

**总分**: 50/120  
**加权得分**: 44.0/100  
**评级**: 不足（明显机器感）

### 6.2 待改进优先级

| 优先级 | 维度 | 当前 | 目标 | 改进方式 |
|--------|------|------|------|----------|
| P0 | 关系记忆 | 0% | 20% | 添加 RelationshipMemory 到 Agent 状态 |
| P1 | 有限理性 | 33% | 55% | 添加 bounded_plan 约束 |
| P1 | 情感记忆 | 45% | 60% | 添加 emotional_event 记忆 |
| P2 | 记忆分层 | 57% | 70% | 实现 short_term/long_term 分离 |
| P3 | 学习系统 | 30% | 50% | 添加 behavior_drift 检测 |

---

## 七、下一步实现计划

### 阶段一：关系记忆（最简单）

**目标：** 添加 RelationshipMemory 到 Agent 状态

**文件：** `generative_city_sim.py` + `memory_store.py`

```python
# 在 Agent 状态中添加
agent["relationships"] = {}  # agent_id -> RelationshipMemory

# 在交互时更新
def update_relationship(agent, other_id, interaction_type, outcome):
    if other_id not in agent["relationships"]:
        agent["relationships"][other_id] = RelationshipMemory(other_agent_id=other_id)
    
    rm = agent["relationships"][other_id]
    rm.add_interaction(InteractionRecord(
        timestamp=time.time(),
        interaction_type=interaction_type,
        outcome=outcome
    ))
```

### 阶段二：有限理性

**目标：** 添加决策限制 + 不确定性表达

**文件：** `generative_city_sim.py` (planning 函数)

```python
def bounded_planning(agent, perception, max_options=3):
    # 1. 生成选项（限制数量）
    options = generate_capped_options(perception, max_count=max_options)
    
    # 2. 添加不确定性表达
    if agent["affect"].should_express_uncertainty():
        options.append({"type": "uncertainty", "phrases": UNCERTAINTY_PHRASES})
    
    # 3. satisficing 选择（而非 optimize）
    selected = choose_satisficing(options)
```

### 阶段三：情感记忆

**目标：** 添加情感事件记忆

**文件：** `memory_store.py`

```python
def add_emotional_memory(agent, event, emotion, intensity):
    entry = {
        "type": "emotional_event",
        "event": event,
        "emotion": emotion,
        "intensity": intensity,
        "timestamp": time.time()
    }
    agent["memory"].append(entry)
    agent["emotional_memory"].append(entry)
```

---

## 八、避免"AI腔"的策略

### 8.1 语言风格约束

| Agent类型 | 语言特征 | 示例 |
|-----------|----------|------|
| 理性驱动型 | 直接、数据导向 | "量化指标达标了" |
| 情感导向型 | 描述性、情绪化 | "感觉不太对" |
| 社交型 | 对话式、确认性 | "你觉得呢？" |
| 回避型 | 模糊、转移话题 | "先看看情况" |

### 8.2 矛盾行为生成

```python
# 同一 Agent 在不同情境下的矛盾行为
if agent.personality.has_contradiction("完美主义", "拖延倾向"):
    if agent.affect.stress > 0.7:
        # 高压时拖延倾向更明显
        action = "拖延"
    else:
        # 正常时完美主义主导
        action = "追求完美"
```

### 8.3 决策噪声

```python
# 有限理性：决策有噪声，不总是最优
def bounded_decision(options, noise_level=0.2):
    scores = [opt["score"] for opt in options]
    noise = np.random.normal(0, noise_level * np.std(scores))
    scores_with_noise = scores + noise
    return options[np.argmax(scores_with_noise)]
```

---

## 九、评估指标表

### 9.1 维度指标

| 维度 | 指标 | 计算方式 | 满分 |
|------|------|----------|------|
| 记忆 | 召回准确率 | 正确召回/总需求 | 10 |
| 记忆 | 记忆一致性 | 记忆与Profile一致率 | 10 |
| 记忆 | 近因效应 | 新记忆召回率/旧记忆 | 10 |
| 人格 | 人格一致性 | 行为符合人格描述率 | 12.5 |
| 人格 | 角色稳定性 | 同场景输出相似度 | 7.5 |
| 人格 | 背景覆盖 | 关键点被应用率 | 5 |
| 情感 | 情绪波动 | 波动合理性评分 | 8 |
| 情感 | 情感记忆 | 情感事件被记住率 | 6 |
| 情感 | 表达多样 | 不同情绪表达差异度 | 6 |
| 有限理性 | 决策多样 | 同场景不同决策率 | 6 |
| 有限理性 | 不确定表达 | 含"不确定"表达率 | 4.5 |
| 有限理性 | 选项限制 | 决策选项数量限制 | 4.5 |
| 学习 | 漂移检测 | 行为变化被检测率 | 5 |
| 学习 | 从错误学 | 错误后调整率 | 3 |
| 学习 | 偏好适应 | 偏好被反映率 | 2 |
| 关系 | 关系追踪 | 交互被记录率 | 8 |
| 关系 | 信任演变 | 信任变化被追踪率 | 6 |
| 关系 | 冲突解决 | 冲突被处理率 | 6 |

---

## 十、总结

### 10.1 当前状态

- **已实现：** 类型定义、mock数据、评估脚本
- **未实现：** 与现有系统的集成、实际功能

### 10.2 HumanScore

**当前**: 44/100（不足）  
**目标**: 70/100（良好）

### 10.3 核心价值

生活史型智能体的核心价值不是让 Agent 更会回答问题，而是：

1. **连续性**：记忆跨时间连贯
2. **矛盾性**：同一 Agent 有时自相矛盾
3. **关系性**：与他人的关系影响行为
4. **情境性**：同一事件在不同情境下反应不同

这些特征让 Agent 更像一个**社会行动者**，而非完美的问答机器。

---

*文档版本: 2026-05-24*
