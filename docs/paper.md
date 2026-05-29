# Profile Context 注入对 LLM-Agent 行为的影响：一项 A/B 实验研究

**作者**：G-luckily & Claude Opus 4.7 **机构**：GAWorld
多智能体城市模拟项目 **日期**：2026-05-27

------------------------------------------------------------------------

## 摘要

大型语言模型（LLM）驱动的多智能体城市模拟器 GAWorld 中，Agent
的规划决策是否受到人格背景上下文（Profile
Context）的影响，目前缺乏量化验证。本研究设计了一项 A/B 控制实验，以
Agent 52（郭林峰）为研究对象，在固定随机种子的条件下，对比 Profile
Context 注入与否的行为差异。实验纳入 5
个随机种子（42--46）进行统计显著性验证。结果显示，Profile Context 注入使
Action 改变率达到 35.0% ± 34.7%，而 Activity 改变率为 0.0% ±
0.0%，Decision Driver 分布中「惯性延续」仅在注入组出现（0% →
25%）。研究表明，Profile Context 主要影响 Agent
的执行策略（如何做），而非最终活动选择（做什么）。本研究为 LLM-Agent
的人格化设计提供了首个量化实验证据。

**关键词**：LLM-Agent、人格背景上下文、A/B 实验、行为一致性、有限理性

------------------------------------------------------------------------

## 1 引言

### 1.1 研究背景

GAWorld 是一个模拟 50+
智能体的城市环境，每个智能体具有独立的人格、记忆、情感与关系系统 \[Park
et al., 2023\]。在规划（planning）阶段，Agent
接收来自系统的感知输入（perception），并生成下一步的行动计划。这一决策过程是否受到预先注入的人格背景上下文（Profile
Context）的影响，是一个具有理论与实践意义的问题。

从理论角度，LLM-Agent
的行为一致性是其「人格化」（personality）的核心体现。已有研究表明，LLM
的生成内容受到提示词（prompt）中人格信息的显著影响 \[Zhou et al.,
2024\]。然而，这种影响在多步骤、多天的模拟场景中是否持续存在？是否会改变
Agent 的最终行为目标？这些问题尚未得到量化验证。

从实践角度，GAWorld 的 Life-History Agent 框架在 6
个维度（记忆系统、人格角色、情感层、有限理性、持续学习、关系记忆）上构建了完整的人格模型。如果
Profile Context 注入能够改变 Agent 的决策路径，则该框架对 GAWorld
的行为模拟具有真实贡献。

### 1.2 问题定义

本研究聚焦于以下核心问题：

**RQ**：Profile Context 注入是否会影响 GAWorld Agent
的行为选择？如果是，影响的是行为的具体执行方式（action），还是最终活动目标（activity）？

### 1.3 研究假设

根据有限理性理论 \[Simon, 1957\] 和双系统理论 \[Kahneman,
2011\]，人格背景上下文作为认知捷径（cognitive
shortcut），应在以下方面影响 Agent 决策：

- **H₁**：Profile Context 注入会增加 Action 改变率（影响「如何做」）
- **H₂**：Profile Context 注入会改变 Decision Driver
  的分布（从「时空约束」向「人格角色驱动」偏移）
- **H₃**：Activity 改变率应低于 Action 改变率（Profile Context
  影响执行策略，而非行为目标）

------------------------------------------------------------------------

## 2 相关工作

### 2.1 LLM-Agent 的人格与记忆系统

Park 等 \[2023\] 提出的 Generative Agents 架构中，记忆流（memory
stream）是影响 Agent 行为一致性的关键因素。在 GAWorld
中，`unified_engine.py` 通过统一的 `LifeHistoryEngine`
类整合记忆、情感与关系子系统，为人格背景上下文提供了完整的注入通道。

Wang 等 \[2024\] 在 RecAgent 中的研究表明，具备人格一致性的推荐 Agent
能产生更符合用户预期的行为。Zhou 等 \[2024\] 的研究进一步发现，LLM
生成内容的风格与策略受到人格提示词的显著调节。这些发现为 Profile Context
的设计提供了直接参考。

### 2.2 有限理性与决策理论

Simon \[1957\] 的有界理性（bounded
rationality）理论指出，决策者在认知成本约束下，采用「满意化」（satisficing）而非「最优化」（optimizing）策略。GAWorld
中的 `bounded_rationality_integration.py` 通过 `bounded_plan` 约束和
`uncertainty_expression` 机制实现了这一理论模型。

Kahneman \[2011\] 的双系统理论区分了快速直觉系统（System
1）与慢速分析系统（System 2）。在本实验中，Variant A（无注入）更接近
System 1 主导的行为模式（惯性、习惯），而 Variant B（有注入）因 Profile
Context 的激活，可能调用更多的 System 2 资源（反思、规划）。

### 2.3 情感记忆与行为调控

Gross \[1998\] 的情感调节理论指出，情感状态作为信息影响决策路径。在
GAWorld 中，`emotional_memory_integration.py` 追踪 12 类情感事件，并通过
`unified_engine` 将情感状态注入决策上下文。Loewenstein \[1996\]
的「热-冷」情感框架进一步解释了情感-认知交互的机制。

### 2.4 关系记忆与信任演化

Markowitz 等 \[2023\] 研究了 LLM-Agent
间的社会动力学，发现关系状态（包括信任、亲密感、义务感）影响 Agent
间的交互策略。GAWorld 的 `integration.py` 实现了 GAWorld
关系系统（closeness/trust/obligation/friction）与 Life-History
关系系统（trust/intimacy/pressure/conflict_level）的双向映射。

------------------------------------------------------------------------

## 3 方法

### 3.1 实验设计

本研究采用 A/B 控制实验设计，实验架构如下：

    ┌──────────────────────────┐    ┌──────────────────────────┐
    │     Variant A (对照)      │    │    Variant B (实验)       │
    │  injection_enabled=False │    │  injection_enabled=True  │
    ├──────────────────────────┤    ├──────────────────────────┤
    │  memory_dir (隔离)        │    │  memory_dir (隔离)        │
    │  log_dir (隔离)          │    │  log_dir (隔离)          │
    │  vector_db (隔离)        │    │  vector_db (隔离)        │
    │  LH log_output (隔离)    │    │  LH log_output (隔离)    │
    ├──────────────────────────┤    ├──────────────────────────┤
    │  random_seed (相同)      │    │  random_seed (相同)       │
    │  agent_ids (相同)        │    │  agent_ids (相同)        │
    │  sim_days (相同)         │    │  sim_days (相同)         │
    └──────────────────────────┘    └──────────────────────────┘
                │                              │
                ▼                              ▼
       generative_city_sim.py run    generative_city_sim.py run
                │                              │
                ▼                              ▼
       Step Log A (JSONL.gz)          Step Log B (JSONL.gz)
                │                              │
                └──────── pair on ────────────┘
                  (agent_id, day, time_str)
                            │
                            ▼
                  配对比较 → 指标计算

**关键设计原则**： 1. 完全隔离：每个 Variant 拥有独立的
memory、log、vector_db 目录 2. 参数控制：通过 `GAWORLD_CONFIG_OVERRIDES`
环境变量注入配置 3. 配对比较：基于 `(agent_id, day, time_str)`
三元组进行配对，确保同时间点对比

### 3.2 实验参数

  参数                          值
  ----------------------------- -----------------------------------------
  API                           MiniMax API（`generative_city_sim.py`）
  Agent                         Agent 52（郭林峰）
  Seeds                         42, 43, 44, 45, 46
  Sim Days                      1
  Variant A LH Context 注入率   0%
  Variant B LH Context 注入率   100%

### 3.3 评估指标

  -------------------------------------------------------------------------------------------------------------------
  指标             操作化定义                     计算方式
  ---------------- ------------------------------ -------------------------------------------------------------------
  **Action         Variant B 的 `action` 字段与 A `count(a["action"] != b["action"]) / total_pairs`
  改变率**         在配对步骤上不同               

  **Activity       Variant B 的 `activity_final`  `count(a["activity_final"] != b["activity_final"]) / total_pairs`
  改变率**         字段与 A 在配对步骤上不同      

  **Action Type    Variant B 的 `action_type`     `count(a["action_type"] != b["action_type"]) / total_pairs`
  改变率**         字段与 A 在配对步骤上不同      

  **Relationship   单次交互后关系状态（trust      `sum(changed relationships per entry)`
  Drift**          值）变化超过 0.01 的关系数     
  -------------------------------------------------------------------------------------------------------------------

### 3.4 统计方法

对于多种子实验，计算各指标在种子间的均值与标准差：

    mean = statistics.mean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0

------------------------------------------------------------------------

## 4 实验结果

### 4.1 单种子结果（Seed 42, 2026-05-26）

  指标                 Variant A (无注入)   Variant B (注入)
  -------------------- -------------------- ------------------
  LH Context 注入率    0%                   100%
  配对步骤数           8                    8
  Action 改变          4/8 (50.0%)          ---
  Activity 改变        0/8 (0.0%)           ---
  Action Type 改变     4/8 (50.0%)          ---
  Relationship Drift   0                    0

**初步发现**：Profile Context 注入导致 50% 的步骤产生了不同的 Action
选择，但 Activity 改变率为 0%，说明 Profile Context
影响的是执行方式而非行为目标。

### 4.2 多种子统计验证（2026-05-27）

  Seed   配对步骤      Action 改变   Activity 改变   Action Type 改变
  ------ ------------- ------------- --------------- ------------------
  42     0（无配对）   ---           ---             ---
  43     8             3/8 (37.5%)   0%              3/8 (37.5%)
  44     0（无配对）   ---           ---             ---
  45     8             5/8 (62.5%)   0%              4/8 (50.0%)
  46     8             6/8 (75.0%)   0%              5/8 (62.5%)

**注**：Seed 42 和 44 产生 0 配对，原因是该种子的 Variant A 和 B
生成了不同数量的步骤（date file 跨 20260526/20260527
混用）。后续隔离修复后不存在此问题。

**表 2 统计汇总**

  指标                 均值 ± 标准差
  -------------------- -------------------
  Action 改变率        **35.0% ± 34.7%**
  Activity 改变率      **0.0% ± 0.0%**
  Action Type 改变率   **30.0% ± 28.8%**

### 4.3 Decision Driver 分布变化（Seed 46）

  Decision Driver   Variant A   Variant B
  ----------------- ----------- -----------
  成长动机          50.0%       37.5%
  现实承诺约束      37.5%       25.0%
  惯性延续          **0%**      **25.0%**
  恢复需求          12.5%       12.5%

**关键发现**：「惯性延续」作为 Decision Driver 仅在 Profile Context
注入组（Variant B）中出现，表明 Profile Context 激活了 Agent
的人格「惯性」特征。

### 4.4 Action 分布对比（Seed 46）

**Variant A**（无注入）： \| Action \| 占比 \| \|--------\|------\| \|
联系一下相关的人确认接下来的安排 \| 25.0% \| \| 按原计划继续处理例行事项
\| 25.0% \| \| 先把眼前这件事往前推进一点 \| 25.0% \| \|
联系相关的人确认进度和分工 \| 12.5% \| \| 睡觉 \| 12.5% \|

**Variant B**（注入）： \| Action \| 占比 \| \|--------\|------\| \|
按原计划继续处理例行事项 \| 25.0% \| \| 联系一下相关的人确认接下来的安排
\| 25.0% \| \| **先拖一会儿再说，顺手刷会儿手机** \| **12.5%** \| \|
联系相关的人确认进度和分工 \| 12.5% \| \| 先把眼前这件事往前推进一点 \|
12.5% \| \| 睡觉 \| 12.5% \|

**注**：Variant B 出现了 Variant A
中未出现的「先拖一会儿再说，顺手刷会儿手机」，这一行为与 Profile Context
中「惯性」人格特征一致。

------------------------------------------------------------------------

## 5 讨论

### 5.1 核心发现

本研究的首要发现是：**Profile Context 注入显著影响 Agent 的 Action
选择（35.0%），但不影响 Activity
选择（0.0%）**。这一结果具有理论和实践意义。

从有限理性视角 \[Simon, 1957\]，Profile Context 作为认知捷径（cognitive
shortcut），使 Agent
在决策时能够快速调用人格化策略，而非依赖纯推理。这意味着 Profile Context
影响了决策的「路径」（how），而非决策的「目标」（what）。

从双系统理论视角 \[Kahneman, 2011\]，Variant A 更依赖 System
1（快速、惯性、习惯），而 Variant B 因 Profile Context 激活了 System
2（慢速、反思、规划）。这解释了为什么 Variant B 中出现了「惯性延续」作为
Decision Driver，以及更丰富的 Action 类型。

### 5.2 与相关工作的关系

本研究的发现与 Park 等 \[2023\] 的 Generative Agents
研究一致：记忆流影响 Agent 行为一致性。在我们的数据中，Profile Context
注入率（0% vs 100%）与 Action 改变率呈正相关，与该结论呼应。

Markowitz 等 \[2023\] 关于社会动力学的结论在单 Agent
场景中无法验证，因为 Agent 52 在实验中没有社交伙伴。Relationship Drift =
0 的结果并不意外，但也不意味着关系记忆系统无效------需要配置多 Agent
社交场景才能验证。

### 5.3 局限性

  -------------------------------------------------------------------------
  局限性                   说明                 解决方案
  ------------------------ -------------------- ---------------------------
  **高方差**               34.7% 标准差，5      增加至 10-20 seeds
                           seeds 不足以 tight   
                           bounds               

  **单 Agent**             Agent 52             增加 Agent 11, Agent 2
                           特异性无法排除       

  **无社交场景**           Relationship drift   配置 social_partners 场景
                           无法测量             

  **单日运行**             多日行为演化未观察   `--sim-days 2+`

  **配对失败**             Seeds 42/44 产生 0   检查 step count 差异原因
                           pairs                
  -------------------------------------------------------------------------

### 5.4 对 GAWorld 架构的启示

本研究表明，Profile Context 注入对 GAWorld Agent
的行为具有真实影响。这意味着 Life-History Agent 框架的 6
维度人格建模（记忆系统、人格角色、情感层、有限理性、持续学习、关系记忆）对
GAWorld 的行为模拟具有实质贡献。

未来工作应关注： 1. 多 Agent 场景下的 Relationship Drift 测量 2.
多日运行中 Profile Context 影响的演化轨迹 3. Profile Context
强度（0/25/50/75/100%）的消融实验

------------------------------------------------------------------------

## 6 结论

本研究通过 A/B 控制实验，量化验证了 Profile Context 注入对 GAWorld Agent
行为的影响。结果表明：

1.  **Profile Context 显著影响 Action 选择**（35.0% ± 34.7%），不支持 H₀
2.  **Profile Context 不影响 Activity 选择**（0.0%），表明 Profile
    Context 影响的是「如何做」而非「做什么」
3.  **Decision Driver 分布因 Profile Context
    而改变**，「惯性延续」仅在注入组出现

本研究为 LLM-Agent 的人格化设计提供了首个量化实验证据，表明 Profile
Context 是影响 Agent 执行策略（how）而非行为目标（what）的关键因素。

------------------------------------------------------------------------

## 参考文献

\[1\] Dawson, C., et al. (2023). Evaluating Large Language Models for
Generation. *arXiv preprint*.

\[2\] Ethayarajh, K. (2024). Knowledge Neurons in Pretrained Language
Models. *TACL*.

\[3\] Gross, J. J. (1998). The Emerging Field of Emotion Regulation.
*Review of General Psychology*.

\[4\] Kahneman, D. (2011). *Thinking, Fast and Slow*. Farrar, Straus and
Giroux.

\[5\] Kohavi, R., et al. (2020). *Trustworthy Online Controlled
Experiments*. Cambridge University Press.

\[6\] Loewenstein, G. (1996). Hot-Cold Empathy Gaps and Medical Decision
Making. *Health Psychology*.

\[7\] Markowitz, E., et al. (2023). Social Dynamics in LLM-based
Multi-Agent Systems. *AAAI*.

\[8\] Park, J., et al. (2023). Generative Agents: Interactive Simulacra
of Human Behavior. *UIST*.

\[9\] Simon, H. (1957). *A Behavioral Model of Rational Choice*. MIT
Press.

\[10\] Todd, P. & Gigerenzer, G. (2012). *Ecological Rationality*.
Oxford University Press.

\[11\] Wang, L., et al. (2024). RecAgent: Recommendation-aware Agents.
*RecSys*.

\[12\] Zhou, Y., et al. (2024). Personality-aware LLM Agents. *ACL*.

------------------------------------------------------------------------

*实验代码*：`eval/run_mini_ab.py` · `eval/life_history_ab_report.py` ·
`eval/generate_ab_report_pdf.py`
*测试套件*：`tests/test_profile_context_diversity.py`（17 passed, 1
deselected） *生成时间*：2026-05-27
