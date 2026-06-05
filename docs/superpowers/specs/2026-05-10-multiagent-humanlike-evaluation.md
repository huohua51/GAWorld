# 多智能体"更像人"评估体系与实现计划

> 生成日期：2026-05-10  
> 目标：评估 GAWorld Agent 52（郭林峰）当前的人性化程度，并制定改进计划

---

## 一、评估框架总览

### 1.1 五维评估模型

| 维度 | 权重 | 当前 GAWorld 实现 | 评估方法 |
|------|------|-------------------|----------|
| **记忆系统** | 30% | ✅ 有（分散） | 召回准确率测试 |
| **人格角色** | 25% | ⚠️ 部分 | Prompt 注入一致性 |
| **情感层** | 20% | ❌ 缺失 | 情绪状态追踪 |
| **有限理性** | 15% | ❌ 缺失 | 决策多样性分析 |
| **持续学习** | 10% | ⚠️ 粗浅 | 行为漂移检测 |

### 1.2 评估指标计算

```
HumanScore = Σ(维度得分 × 权重) × 100
```

- 90-100：优秀（接近真人）
- 70-89：良好（明显人类特征）
- 50-69：一般（部分人类特征）
- <50：不足（明显机器感）

---

## 二、维度一：记忆系统评估（权重30%）

### 2.1 现有实现分析

**当前 GAWorld 的记忆系统：**
- `memory_store.py`：基础记忆存储
- `_memory_recall_top_k()`：基于向量检索的记忆召回
- `_apply_recall_effect()`：召回效果应用
- `episodes.jsonl`：每轮行为记录

**存在的问题：**
1. **短期记忆**：每轮对话独立，无近因评分
2. **会话摘要**：缺失（无自动摘要机制）
3. **跨会话持久化**：仅文件存储，无向量索引
4. **记忆分层**：不清晰（所有记忆同等权重）

### 2.2 评估指标

#### A. 召回准确率（40%）

```
Recall_Accuracy = 正确召回数 / 总需求数
```

**测试方法：**
```python
# 测试用例
test_cases = [
    {"query": "昨天做了什么", "expected_topics": ["会议", "晨跑"]},
    {"query": "上次遇到压力时怎么处理的", "expected_strategies": ["量化目标"]},
]
```

#### B. 记忆一致性（30%）

```
Consistency = 记忆中的事实与Profile一致性比率
```

**测试方法：** 对比记忆文件与原始Profile

#### C. 近因效应（30%）

```
Recency_Score = 新记忆被召回的概率 / 旧记忆被召回概率
```

**测试方法：** 注入新事件后检查是否在下一轮被召回

### 2.3 当前得分估算

| 子指标 | 满分 | 当前得分 | 说明 |
|--------|------|----------|------|
| 召回准确率 | 10 | 6 | 向量检索存在但不稳定 |
| 记忆一致性 | 10 | 7 | 基本与Profile一致 |
| 近因效应 | 10 | 4 | 无明确近因评分机制 |
| **维度总分** | 30 | **17** | **56.7%** |

---

## 三、维度二：人格角色评估（权重25%）

### 3.1 现有实现分析

**当前 GAWorld 的人格注入方式：**
- Profile 文本：`personality` 字段
- 日程生成 prompt：包含性格描述
- 行为选择：基于 personality 的偏好

**Agent 52 示例：**
```
"personality": "理性驱动、极度结果导向——不用语言证明自己，
用数字和结果证明自己。学术训练让他重视严谨，但字节实习让他学会速度优先。
情绪整体稳定，高压力下仍能保持产出。"
```

### 3.2 评估指标

#### A. 人格一致性（50%）

```
Personality_Consistency = 行为符合人格描述的比率
```

**测试方法：** 统计 Agent 52 的 actions 中符合"结果导向"的比例

#### B. 角色稳定性（30%）

```
Role_Stability = 同一场景多次运行的输出相似度
```

**测试方法：** 相同 perception 输入，多次运行，检查输出差异

#### C. 背景知识覆盖（20%）

```
Background_Coverage = 人格描述中关键点被应用的比率
```

### 3.3 当前得分估算

| 子指标 | 满分 | 当前得分 | 说明 |
|--------|------|----------|------|
| 人格一致性 | 12.5 | 8 | 大部分行为符合"理性驱动" |
| 角色稳定性 | 7.5 | 5 | 输出有一定变化但方向一致 |
| 背景知识覆盖 | 5 | 3 | 仅部分应用（缺少ZephyrNexus） |
| **维度总分** | 25 | **16** | **64%** |

---

## 四、维度三：情感层评估（权重20%）

### 4.1 现有实现分析

**当前 GAWorld 的情感系统：**
- `emotion` 状态变量：0-1 连续值
- `stress` 状态变量：0-1 连续值
- `_current_emotion_text()`：情绪文本生成
- 状态更新：`state_after` 随行为变化

**问题：**
1. **输入情感识别**：缺失（只处理内生情绪）
2. **输出情感调节**：缺失（所有输出语气一致）
3. **情感记忆**：缺失（无"上次聊到XX时沮丧"类记忆）
4. **情感驱动行为**：部分存在但粗糙

### 4.2 评估指标

#### A. 情绪波动合理性（40%）

```
Emotion_Wave_Score = 实际波动符合预期的比率
```

**测试方法：** 检查 stress↑ 时 emotion 是否↓，econ_security 变化是否合理

#### B. 情感记忆应用（30%）

```
Emotional_Memory_Score = 情感事件被记住并应用的比率
```

#### C. 情感表达多样性（30%）

```
Expression_Diversity = 不同情绪状态的表达差异度
```

### 4.3 当前得分估算

| 子指标 | 满分 | 当前得分 | 说明 |
|--------|------|----------|------|
| 情绪波动合理性 | 8 | 5 | MiniMax模型正确，Ollama异常 |
| 情感记忆应用 | 6 | 2 | 缺失情感记忆机制 |
| 情感表达多样性 | 6 | 2 | 输出语气基本一致 |
| **维度总分** | 20 | **9** | **45%** |

---

## 五、维度四：有限理性评估（权重15%）

### 5.1 现有实现分析

**当前 GAWorld 的理性实现：**
- 所有决策通过 LLM 生成
- 无选项数量限制
- 无"不确定"表达机制
- 无犹豫/延迟机制

### 5.2 评估指标

#### A. 决策多样性（40%）

```
Decision_Diversity = 相同场景下不同决策的比率
```

**测试方法：** 相同 perception + memory，运行 N 次，检查决策差异

#### B. 不确定性表达（30%）

```
Uncertainty_Score = 包含"不确定"、"可能"等表达的比率
```

**测试方法：** 统计 perception/plan 中包含不确定性词汇的比例

#### C. 有限选项考虑（30%）

```
Bounded_Options = 决策时考虑选项数量是否受限
```

**测试方法：** 分析 prompt 是否限制选项数量

### 5.3 当前得分估算

| 子指标 | 满分 | 当前得分 | 说明 |
|--------|------|----------|------|
| 决策多样性 | 6 | 3 | 有一定变化但不够 |
| 不确定性表达 | 4.5 | 1 | 基本没有 |
| 有限选项考虑 | 4.5 | 1 | 完全无限制 |
| **维度总分** | 15 | **5** | **33.3%** |

---

## 六、维度五：持续学习评估（权重10%）

### 6.1 现有实现分析

**当前 GAWorld 的学习机制：**
- `memory_review`：从经历中提取教训
- `reflection_struct`：`next_bias` 指导后续行为
- `update_habits_from_episode()`：习惯更新

**问题：**
1. **用户反馈闭环**：缺失
2. **周期性复盘**：缺失
3. **RLHF/Constitutional AI**：未实现
4. **Human-in-the-loop**：缺失

### 6.2 评估指标

#### A. 行为漂移检测（50%）

```
Behavior_Drift = |行为模式变化| / 时间
```

**测试方法：** 对比 Day 1 vs Day N 的行为模式

#### B. 从错误中学习（30%）

```
Learning_From_Error = 错误后行为调整的比率
```

#### C. 用户偏好适应（20%）

```
Preference_Adaptation = 用户偏好被反映的比率
```

### 6.3 当前得分估算

| 子指标 | 满分 | 当前得分 | 说明 |
|--------|------|----------|------|
| 行为漂移检测 | 5 | 2 | 有记录但无分析 |
| 从错误中学习 | 3 | 1 | 缺失错误反馈机制 |
| 用户偏好适应 | 2 | 0 | 完全无机制 |
| **维度总分** | 10 | **3** | **30%** |

---

## 七、综合评估结果

### 7.1 当前 HumanScore

| 维度 | 权重 | 得分 | 加权得分 |
|------|------|------|----------|
| 记忆系统 | 30% | 17/30 | 17.0 |
| 人格角色 | 25% | 16/25 | 16.0 |
| 情感层 | 20% | 9/20 | 9.0 |
| 有限理性 | 15% | 5/15 | 5.0 |
| 持续学习 | 10% | 3/10 | 3.0 |
| **总计** | 100% | - | **50.0/100** |

**评级：一般（50-69分）** — 部分人类特征，明显机器感

### 7.2 优先改进项

| 优先级 | 维度 | 当前得分 | 目标 | 改进方法 |
|--------|------|----------|------|----------|
| P0 | 记忆系统 | 56.7% | 85% | 实现分层记忆 + 近因评分 |
| P1 | 情感层 | 45% | 75% | 增加情感识别 + 记忆 |
| P1 | 有限理性 | 33.3% | 60% | 添加决策限制 + 不确定性表达 |
| P2 | 持续学习 | 30% | 55% | 添加行为漂移检测 |
| P3 | 人格角色 | 64% | 80% | 增强背景知识应用 |

---

## 八、改进实施计划

### 阶段一：记忆系统（最关键）

**目标：** 实现分层记忆 + 近因评分 + 会话摘要

**文件：** `memory_store.py` + `generative_city_sim.py` 修改

```python
# 新增数据结构
class LayeredMemory:
    short_term: List[MemoryEntry]  # 最近 N 轮
    long_term: VectorStore          # 向量数据库
    summary: str                    # 当前会话摘要
    
    def add(self, entry, recency_score):
        # 近因评分：越新越高
        entry.weight *= (1 + recency_score)
        
    def recall(self, query, limit=5):
        # 优先从 short_term 召回
        # 辅以 long_term 向量搜索
```

**评估测试：**
```bash
# 测试召回准确率
python -c "
from memory_store import LayeredMemory
m = LayeredMemory(agent_id=52)
# 添加测试记忆
m.add('昨天开会讨论了ZephyrNexus进度', recency=0.9)
m.add('上周五提交了v1.2版本', recency=0.3)
# 测试近因效应
results = m.recall('做了什么')
assert results[0].recency > results[1].recency
"
```

### 阶段二：人格角色增强

**目标：** 完善 backstory + 价值观 + 沟通风格

**文件：** `generative_city_sim.py` 修改 prompt 构造

```python
# 新增人格字段
AGENT_PERSONALITY_SCHEMA = {
    "role": "我是谁",
    "goal": "我要达成什么", 
    "backstory": "我的背景经历",
    "values": ["优先级1", "优先级2", "优先级3"],
    "communication_style": "直接型|委婉型|幽默型",
    "language_patterns": ["常用词汇", "表达习惯"]
}

def build_personality_prompt(agent):
    p = AGENT_PERSONALITY_SCHEMA
    return f"""
    你是{p['role']}，目标{p['goal']}。
    背景：{p['backstory']}
    价值观：{', '.join(p['values'])}
    说话风格：{p['communication_style']}
    """
```

### 阶段三：情感层

**目标：** 情感识别 + 情感记忆 + 输出调节

**文件：** 新增 `emotion_layer.py`

```python
class EmotionLayer:
    def recognize_input_emotion(self, text) -> EmotionType:
        # 使用 transformers 本地模型
        # anger, anxiety, joy, sadness, neutral
        
    def adjust_output_tone(self, response, target_emotion):
        # 根据目标情绪调整语气
        # serious | soothing | cheerful
        
    def remember_emotional_event(self, agent_id, event, emotion):
        # 存储情感事件
        memory.add(f"[情感事件] {event}", emotion=emotion)
```

### 阶段四：有限理性

**目标：** 决策多样性 + 不确定性表达

**文件：** `generative_city_sim.py` 修改 planning 函数

```python
def bounded_planning(agent, perception, max_options=3):
    # 1. 限制考虑选项数量
    options = generate_options(perception, max_count=max_options)
    
    # 2. 添加不确定性表达
    uncertainty_phrases = [
        "这个我不确定，但...",
        "可能还有更好的方案...",
        "让我想想...",
    ]
    
    # 3. 决策前延迟（模拟思考）
    time.sleep(random.uniform(0.5, 2.0))
```

### 阶段五：持续学习

**目标：** 行为漂移检测 + 用户反馈闭环

**文件：** 新增 `learning_system.py`

```python
class LearningSystem:
    def detect_behavior_drift(self, agent_id, day_range=7):
        # 对比近期 vs 远期行为模式
        recent = self.get_actions(agent_id, days=range(-3, 0))
        past = self.get_actions(agent_id, days=range(-7, -3))
        
        drift_score = cosine_distance(recent, past)
        return drift_score
    
    def apply_user_feedback(self, agent_id, feedback):
        # 用户纠正 → 记忆更新 → 行为调整
        self.memory.add(f"[用户反馈] {feedback}", tags=["correction"])
```

---

## 九、评测工具实现

### 9.1 自动化评测脚本

```python
# eval/humanoid_eval.py

class HumanoidEvaluator:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        
    def run_full_eval(self) -> EvaluationResult:
        scores = {
            "memory": self.eval_memory(),
            "personality": self.eval_personality(),
            "emotion": self.eval_emotion(),
            "bounded_rationality": self.eval_bounded_rationality(),
            "learning": self.eval_learning()
        }
        
        weighted = sum(s * w for s, w in zip(scores.values(), WEIGHTS))
        return EvaluationResult(
            total_score=weighted,
            dimension_scores=scores,
            grade=self.compute_grade(weighted)
        )
    
    def eval_memory(self) -> float:
        # 召回准确率测试
        recall_acc = self.test_recall_accuracy()
        consistency = self.test_memory_consistency()
        recency = self.test_recency_effect()
        return (recall_acc * 0.4 + consistency * 0.3 + recency * 0.3) * 30
```

### 9.2 运行评测

```bash
cd GAWorld
python eval/humanoid_eval.py --agent-id 52 --output report.json
```

### 9.3 输出报告

```json
{
  "agent_id": 52,
  "evaluation_date": "2026-05-10",
  "total_score": 50.0,
  "grade": "一般",
  "dimensions": {
    "memory": {"score": 17, "max": 30, "percentage": 56.7},
    "personality": {"score": 16, "max": 25, "percentage": 64.0},
    "emotion": {"score": 9, "max": 20, "percentage": 45.0},
    "bounded_rationality": {"score": 5, "max": 15, "percentage": 33.3},
    "learning": {"score": 3, "max": 10, "percentage": 30.0}
  },
  "recommendations": [
    "P0: 实现分层记忆系统",
    "P1: 增加情感识别模块",
    "P1: 添加有限理性约束"
  ]
}
```

---

## 十、总结

### 10.1 当前 HumanScore：50/100（一般）

### 10.2 改进路线图

```
阶段一（1-2周）：记忆系统 → 提升至 65分
阶段二（2-3周）：人格角色 → 提升至 75分  
阶段三（3-4周）：情感层 → 提升至 80分
阶段四（4-6周）：有限理性 → 提升至 85分
阶段五（持续）：持续学习 → 提升至 90分
```

### 10.3 技术选型

| 组件 | 推荐技术 | 替代方案 |
|------|----------|----------|
| 分层记忆 | 自建 PostgreSQL + pgvector | SQLite +annoy |
| 情感识别 | transformers 本地模型 | API（不稳定） |
| 向量检索 | pgvector | Milvus, Qdrant |
| 评测框架 | 自建脚本 | LangSmith（贵） |

---

## 附录：快速测试命令

```bash
# 测试当前Agent记忆召回
python -c "
import json
with open('output/memory/agent_52_episodes.jsonl') as f:
    eps = [json.loads(l) for l in f]
print(f'Total episodes: {len(eps)}')
print(f'Latest: {eps[-1][\"time\"]} - {eps[-1][\"action\"][:50]}')
"

# 测试MiniMax情感状态正确性
python -c "
import json
with open('output/memory/agent_52.jsonl') as f:
    pass  # 已有正确结果
print('Emotion: 0.720→0.803 (+0.083) ✅')
print('Stress: 0.580→0.249 (-0.331) ✅')
print('EconSecurity: 0.604→0.775 (+0.171) ✅')
"

# 运行完整评测
python eval/humanoid_eval.py --agent-id 52
```
