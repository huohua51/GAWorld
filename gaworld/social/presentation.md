# GAWorld 社交系统

## 1. 研究问题

我负责的是 GAWorld 里的社交系统。现在的研究问题可以概括为：

> 如何在生成式人工社会中，让智能体不仅各自行动，还能基于关系、情绪和环境事件产生社交互动，并模拟对话、信息传播、情绪变化和关系演化？

研究四个问题：

1. 谁和谁有关系？
2. 他们为什么互动？
3. 他们具体怎么交流？
4. 交流之后，情绪、压力和关系怎么变化？

---

## 2. 当前已经做了什么

我新增了一个独立模块：

```text
gaworld/social/
```

主要文件：

| 文件 | 作用 |
|---|---|
| `schemas.py` | 定义社交节点、关系边、扩散事件、互动事件 |
| `network.py` | 根据 agent 属性生成社交关系网络 |
| `decision.py` | 决定谁和谁互动、互动类型、话题和触发概率 |
| `llm_events.py` | 生成对话、主观感受和状态变化；当前是 mock LLM，后续接 MiniMax |
| `interaction_demo.py` | 最新社交互动仿真 demo |
| `demo.py` | 旧版社交图和情绪扩散 demo |

最新 demo 运行命令：

```bash
python -m gaworld.social.interaction_demo
```

输出目录：

```text
gaworld/social/results_interactions/
```

当前 demo 已经能模拟：

- 一天内 agent 之间发生多次社交互动
- agent 之间具体说了什么
- 消息是否继续传播
- emotion / stress 如何变化
- trust / closeness / friction 如何变化
- 互动前后社交图如何变化

---

## 3. 当前结果

当前 demo 跑出来的摘要：

```text
agent_count: 51
relationship_count: 112
interaction_count: 25
diffused_message_count: 13
mode: mock_llm_dialogue
```

也就是说：

- 读取了 51 个居民 agent。
- 生成了 112 条社交关系。
- 在一天内模拟了 25 次社交互动。
- 其中 13 次属于消息分享或继续传播。
- 当前对话生成使用 mock LLM，后续会替换为 MiniMax。

---

## 4. 展示一：社交互动时间线

最重要的展示文件是：

```text
gaworld/social/results_interactions/social_timeline.md
```

这个文件展示一天内大家怎么互动。

每条互动包括：

- 时间
- 谁和谁互动
- 互动类型
- 话题
- 系统为什么触发这次互动
- 双方具体说了什么
- 主观影响
- 情绪和压力变化
- 关系变化
- 消息是否继续传播

示例结构：

```text
Day 1 08:30｜许曼婷 → 许知夏
类型：share_news
话题：平台派单规则变化

许曼婷：许知夏，我刚听到关于「平台派单规则变化」的消息，感觉这事可能会影响我们这两天的安排。
许知夏：我也有点担心，但你提醒得及时，我先看看身边人怎么说。

状态变化：
许知夏 emotion 下降
许知夏 stress 上升
两人 trust 上升
消息继续传播
```

---

## 6. 互动类型分布

这张图展示一天内发生了哪些类型的互动。

当前支持的互动类型包括：

| 类型 | 含义 |
|---|---|
| `share_news` | 分享消息、公共事件、平台规则变化等 |
| `check_in` | 日常问候 |
| `vent` | 倾诉压力 |
| `ask_help` | 求助 |
| `invite` | 约饭、散步、见面 |
| `conflict` | 冲突或摩擦 |

现场可以这样讲：

> 这个图说明社交系统不只是传播情绪，还能区分不同类型的社交互动。不同互动类型会带来不同的情绪变化和关系变化。

---

## 7. 展示四：关系变化和状态变化

两个结构化结果文件：

```text
gaworld/social/results_interactions/relationship_changes.csv
gaworld/social/results_interactions/agent_state_changes.csv
```

`relationship_changes.csv` 记录：

- trust 前后变化
- closeness 前后变化
- friction 前后变化

`agent_state_changes.csv` 记录：

- emotion 前后变化
- stress 前后变化

## 

当前有理论支撑的方向：

- **Homophily**：相似的人更容易形成关系。
- **Geographic proximity**：地理接近增加互动机会。
- **Weak ties**：弱关系有助于跨圈层传播。
- **Emotional contagion**：情绪会通过社交网络传播。
- **Independent Cascade / Threshold Model**：信息和情绪可以用扩散模型描述。
- **Source credibility**：可信来源更容易影响他人。

当前没有直接论文支撑的是具体数字：

```text
同居住区 +0.35
年龄差 <= 8 岁 +0.25
户籍相同 +0.15
susceptibility 公式里的具体系数
credibility 公式里的具体系数
```

这些目前是工程原型参数，后续需要用真实数据、消融实验或参数搜索校准。

汇报时可以说：

> 当前版本的机制方向来自社会网络和情绪传播理论，但具体权重还是原型阶段的启发式设定。下一步需要通过实验校准。

---

## 12. 下一步研究计划

1. **加入 profile 和记忆**
   - 对话生成时读取 agent profile。
   - 重要互动写入长期记忆。
2. **消息传播**
   - 模拟政策、谣言、应急通知、平台规则等信息扩散。
3. **关系演化**
   - 长期记录 trust / closeness / friction。
   - 形成朋友、疏远、冲突、支持网络。

## 

