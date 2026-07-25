# GAWorld 教程 v2

**面向第一次到进阶使用 GAWorld 的用户 | 更新日期：2026 年 6 月**

> 这是 GAWorld 的**完整教程**——已并入原 v1.0 完全教程的全部内容，单文件自包含。更简短的快速上手见 [`docs/TUTORIAL.md`](TUTORIAL.md)。
> 在既有特性详解（第 5 节）之外，本版补全了三块**新特性**（物理环境感知与反应式重规划、可复用 Skill 库、真实工作任务系统）与**分布式 relay 多机通信**。

---

## 目录

1. [GAWorld 是什么](#1-gaworld-是什么)
2. [安装与 LLM 配置](#2-安装与-llm-配置)
3. [5 分钟跑通第一次仿真](#3-5-分钟跑通第一次仿真)
    - [3.1 长时段快进（Fast-forward）：跑 10 / 60 / 600 天](#31-长时段快进fast-forward跑-10--60--600-天)
4. [核心概念：智能体与仿真循环](#4-核心概念智能体与仿真循环)
5. [既有特性详解](#5-既有特性详解)
6. [新特性一：物理环境感知与反应式重规划](#6-新特性一物理环境感知与反应式重规划)
7. [新特性二：可复用 Skill 库](#7-新特性二可复用-skill-库)
8. [新特性三：真实工作任务系统](#8-新特性三真实工作任务系统)
9. [事件对照实验](#9-事件对照实验)
10. [访谈与 RAG 注入](#10-访谈与-rag-注入)
11. [分布式 relay：多机通信](#11-分布式-relay多机通信)
12. [Dashboard 使用指南](#12-dashboard-使用指南)
    - [12.1 Agent Studio（单智能体构建/查看器）](#121-agent-studio单智能体构建查看器)
13. [配置与开关总表](#13-配置与开关总表)
14. [输出文件地图](#14-输出文件地图)
15. [常见问题](#15-常见问题)
16. [命令速查表](#16-命令速查表)
17. [微内核插件架构：扩展 GAWorld](#17-微内核插件架构扩展-gaworld)

---

## 1. GAWorld 是什么

GAWorld（Generative Agent World）是一个**面向城市社会行为实验的生成式多智能体仿真系统**。它把人物画像、长期记忆、社会影响、环境扰动、政策事件、经济状态、地图移动、轻量平台干预评估和 LLM 决策组合成一个**可回放、可对照、可扩展**的模拟流程。

一句话：让一批虚拟城市居民在你的电脑上"生活"若干天——每个人都有工作、社交、财务、情绪、习惯和记忆——然后你通过实验观察社会现象。

适用场景：

| 场景 | 说明 |
|------|------|
| 城市政策模拟 | 交通限行、住房补贴、医疗改革等政策对居民行为的影响 |
| 社会行为研究 | 信息/误信息传播、情绪感染、极化、社交网络演化 |
| 智能体记忆实验 | 长期记忆、习惯养成对行为一致性的影响 |
| AI / 复杂系统教学 | 演示多智能体如何涌现复杂社会现象 |

`docs/proposals/` 下已有一批成型的实验方案与论文（记忆一致性、误信息传播、极化、宏观经济、网络演化、出行行为等），可作为设计参考。

---

## 2. 安装与 LLM 配置

### 2.1 环境要求

| 项目 | 要求 |
|------|------|
| Python | **推荐 ≥ 3.11**（3.10 可跑主流程，但完整测试套件依赖 3.11 的少数特性） |
| 操作系统 | macOS / Linux / Windows |
| 内存 | 推荐 16GB 以上 |
| 网络 | 访问云端 LLM API；用本地 Ollama 可离线 |

### 2.2 安装

```bash
pip install -r requirements.txt
python generative_city_sim.py --help   # 看到帮助即安装成功
```

### 2.3 配置 LLM（必须）

GAWorld 运行需要至少一个可用的 LLM Provider，三选一：

**① OpenAI 兼容（云端）**

```bash
export OPENAI_API_KEY="your_key_here"
```

**② Anthropic 兼容（云端 / 代理）**

```bash
export ANTHROPIC_API_KEY="your_key_here"
# 中国区 Minimax 的 Anthropic 兼容接口：
export ANTHROPIC_BASE_URL="https://api.minimaxi.com/anthropic"
export MINIMAX_API_KEY="your_key_here"   # 或 ANTHROPIC_AUTH_TOKEN
```

**③ 本地 Ollama（离线）**

```bash
brew install ollama        # macOS
ollama pull qwen2.5
ollama serve               # 默认 port 11434
```

然后在 `config.py` 中让 `llm.routing.default` 指向你已配置好的 provider（如 `openai_gpt` / `ollama_qwen`）。也可以用 `llm.routing.tasks` 给不同任务（planning / reflection 等）指定不同模型。

---

## 3. 5 分钟跑通第一次仿真

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your_key_here"
python generative_city_sim.py run
```

运行时终端输出（默认 `simple` 模式，约每 tick 4 行）：

```
── [李泽宇 @ 09:30] 上午工作 ──
Loc: 互联网公司
Act: 推进最重要的一项任务
Refl: 感受：情绪有一点波动；教训：下次要更早判断状态和代价；后续倾向：更偏向省力或稳妥
```

想看完整字段（感知 / 计划 / 记忆召回 / 需求状态）切换详细模式：

```bash
GAWORLD_LOG_MODE=verbose python generative_city_sim.py run
GAWORLD_LOG_LEVEL=DEBUG  python generative_city_sim.py run   # 含 token 计数与延迟
```

跑完后看 `output/`：

```
output/
├── logs/           运行日志（run.log 为完整结构化日志）
├── memory/         智能体记忆、成长进度、向量库
├── state/          状态时间序列 CSV
├── economy/        账本、财富快照、宏观状态、部门池与守恒审计
├── environment/    环境事件时间线
├── intervention/   PolicySim 风格干预指标
├── network/        社交网络图
├── work/           真实工作产物（启用后）
└── visualization/  轨迹回放数据
```

改了关键配置（尤其是记忆 schema 相关）或想从 Day 1 重来：

```bash
python generative_city_sim.py reset && python generative_city_sim.py run
```

### 3.1 长时段快进（Fast-forward）：跑 10 / 60 / 600 天

默认的精细模式每天要跑一遍**日内时刻循环**（每个 tick 每个 agent 一次认知
LLM 调用，约每 agent 每天数十次），几十上百天就跑不动了。**长时段快进模式**
把一整天压缩成**每个智能体一条「日简报」**（每 agent 每天仅 1 次 LLM 调用），
跳过日内时刻循环——实现一种「快进 + 近似」的效果，适合观察**长期**演化。

```bash
# 快进跑 600 天：每天每个 agent 生成一条日简报
python generative_city_sim.py run --sim-days 600 --fast-forward
```

- **输出不再按具体时刻**，而是每天一个 `Day N 简报` 块：每个 agent 一行 +
  当天世界事件提示。
- **状态仍会「近似推进」并持久化**：情绪/压力等状态按夹逼后的小幅增量更新，
  目标进度、关系亲密度、记忆与日记都照常写入，日终的成长/兴趣/经济钩子也照跑
  ——只是分辨率更粗。所以跑完 600 天后，智能体是被真实塑造过的。
- 关掉 `--fast-forward` 即回到逐时刻的精细模式（默认）。

调参（`config.py` / `dashboard_config.json` 的 `long_run` 段）：

| 字段 | 默认 | 作用 |
|---|---|---|
| `long_run.enabled` | `false` | 快进总开关（等价于 `--fast-forward`） |
| `long_run.brief_llm` | `true` | 用 LLM 写简报；置 `false` 则**零 LLM** 走确定性简报 |
| `long_run.randomness` | `0.3` | **随机性 0–1**：越高，快进期间**突发事件**越频繁、智能体**状态波动**越大；`0` = 完全确定（无突发、无抖动） |
| `long_run.max_state_delta` | `0.15` | 单日近似状态增量的夹逼上限 |
| `long_run.brief_max_chars` | `240` | 每条日简报的软长度上限 |

**随机性怎么起作用**：每个智能体每天按 `≈0.3×randomness` 的概率掷出一次
**突发事件**（意外开销/机会/冲突/健康/人际变故……），命中时简报里会自然带出这件
事、状态也随之明显波动（日志中以 `⚡` 标记）；此外每天都会给情绪/压力等状态叠加
一层幅度随 `randomness` 增大的零均值抖动（突发日抖动更大）。设 `random_seed` 可复现。

> Dashboard 上也能一键开启：工具栏勾选「长时段快进」、拖动「随机性」滑杆即可（见第 12 节）。

---

## 4. 核心概念：智能体与仿真循环

每个智能体 = **基本信息 + 状态变量 + 记忆 + 财务 + 关系网络**。

状态变量（归一化到 [0,1]）：

| 变量 | 含义 | 0 → 1 |
|------|------|-------|
| emotion | 情绪 | 极消极 → 高度积极 |
| stress | 压力 | 无 → 极高 |
| econ_security | 经济安全 | 极不安全 → 极安全 |
| city_identity | 城市认同 | 强烈疏离 → 强烈认同 |

外加 `policy_sensitivity`、`platform_dependence`、`risk_preference`、`voice_propensity`、`mobility_intent` 等增强变量。

每个智能体每个时间步循环 5 步：

```
① 感知 → ② 计划 → ③ 日程/动作生成 → ④ 动作执行 → ⑤ 反思与记忆更新
                                                        ↓（回到 ①）
```

随天数推进累积：episode 记忆、长期总结、情境习惯、日级意图、关系变化、收支与资产变化、技能成长、地点偏好。

> **新特性接入点**：本版三块新特性都"挂"在这个循环上——物理感知发生在 ①感知之前、Skill 在 ①感知与工作 brief 处注入、真实工作在 ④动作执行时按职业触发。下面分别讲。

---

## 5. 既有特性详解

下面这些特性在更早的教程里就已存在，本节把要点、配置开关与文件位置整理在一处（原 v1.0 教程的完整说明已并入此节）。

### 5.1 记忆系统

多层记忆架构：

- **短期记忆**：当前 episode 与当天活动日志。
- **情景记忆（Episodic）**：每个行为决策的背景与结果，逐条写入 `output/memory/agent_<id>_episodes.jsonl`。
- **长期总结（Long-term）**：智能体对自身的认知与目标总结，跨天保持一致。
- **关系记忆**：与其他智能体的关系变化与社交互动历史。

| 文件 | 内容 |
|---|---|
| `agent_<id>.json` | 完整记忆状态 |
| `agent_<id>_episodes.jsonl` | 逐事件记录 |
| `agent_<id>_growth.json` | 兴趣 / 技能成长进度 |
| `growth_profiles.json` | 全局兴趣画像缓存 |
| `vector_db.sqlite` | 向量数据库（语义检索） |

**召回机制**：每个感知阶段按"当前情境 → 向量检索 → 召回最相关历史 → 注入感知"工作，让行为带上记忆一致性。

### 5.2 经济仿真

基于中国个人财务体系的闭环货币系统（配置见 `CONFIG["economy"]`，源文件 `gaworld/settings/economy.py`，实现 `gaworld/economy/finance.py`）：

- **个税与社保（真实代扣）**：7 档累进税率（3%→45%）、月免征额 5000 元；五险一金按个人缴费率扣缴（养老 8% / 医疗 2% / 失业 0.5% / 公积金 8%）。月末按**实收**工资从活期账户真实代扣，税款入政府部门池，公积金（个人 + 单位配缴）入公积金账户。
- **恩格尔系数消费**：低收入者食品支出占比高、储蓄率低，高收入者相反；8 大消费类目按收入弹性分配。
- **多账户投资 + 共同市场因子**：活期 / 储蓄 / 投资 / 公积金四账户，保守 / 稳健 / 激进三种组合。月度收益 = 全市场共同因子（每月抽取一次，所有 agent 共享，股灾会同时打击所有人）+ 个体特质噪声，系统性占比由 `investment.market_correlation`（默认 0.7）控制。
- **宏观经济周期**：扩张 → 峰值 → 收缩 → 谷底四阶段，行业景气独立波动，每日通胀累积。

**货币守恒与部门池**：所有资金流动都有对手方 —— 企业池（发工资、收消费）、政府池（收税、付医保报销）、银行池（结算投资盈亏、放贷）。初始化后系统货币总量守恒到分，每日审计写入 `conservation_audit.csv`（|drift| ≤ 0.01 元），GAWorld-Bench Track A 将其作为硬门槛。部门池允许为负（企业池为负 = 家庭部门净储蓄的镜像）。

**现金约束、信贷与熟人借贷**：支出按 活期 → 储蓄提取 → 银行信用额度（默认 2 倍月净薪、年息 18%、月度复利、盈余自动还款）→ 截断 的顺序融资；流动性低于 1 个月开销时按收入弹性削减非必需消费（奢侈类砍得更狠）。消费被截断的 agent 进入 distress 状态：stress 上升，日终可按 closeness×trust 向社交网络上有盈余的好友无息借款（`friend_debts` 双边记账，月结时优先于银行债务偿还）。

**支付路由到 agent**：本地消费的 `routing.merchant_labor_share`（默认 35%）经企业池转付给工作地点匹配的服务业 / 商贸 agent；房租路由给房东类 agent（职业关键词匹配），无房东则留在企业池。货币因此在 agent 之间循环，财富分布可以内生涌现。

个体随机触发的经济冲击事件：

| 事件 | 影响 |
|---|---|
| 裁员 | 收入削减 50–85%（月度税基同步下调），恢复期 30–90 天 |
| 涨薪 / 晋升 | 收入提升，税率重算 |
| 大病医疗 | 社保报销 50–85%（政府池支付），影响情绪与支出 |
| 年终奖 | 第 13 个月工资（企业池支付，奖金税入政府池） |

经济模块使用独立随机流（由 `random_seed` 派生），其它模块增删随机调用不影响经济轨迹的可复现性。

经济数据写入 `output/economy/`（`daily_ledger.csv` 含 `debt` 列、`wealth_snapshot.csv`、`macro_state.json`、`sectors.json`、`conservation_audit.csv`、`agents/agent_<id>_*`）。

### 5.3 位置系统与交通

用**类别匹配**而非硬编码地点决定移动："活动类型 → 地点类别 → 地图节点 → 最佳选择"。

| 活动 | 地点类别 |
|---|---|
| 工作 | industry / commerce / government |
| 上学 | education |
| 就医 | medical |
| 购物 | commerce |
| 休闲 | leisure |
| 通勤 | transit |

**真实出行成本**：公交固定 2 元；地铁起步 2 元 + 超 4 公里 0.45 元/公里；出租起步 13 元 + 超 3 公里 2.5 元/公里；私家车计油耗 + 停车费。**高峰**（7–9 / 17–19 点）出行时间 ×1.45、出租附加 ×1.3。**天气**：雨雪天惩罚露天方式，自动改走有遮蔽方式。**通勤记忆**：累积常去地点、偏好方式与路线统计，反馈为习惯性出行。

### 5.4 动态行为系统

开关 `CONFIG["dynamic_behavior"]["enabled"]`。在 LLM 决策前注入上下文感知的日程变更，六大引擎：中断 / 情绪 / 需求 / 社交 / 环境 / 日程。

- **承诺度感知中断**：每种活动有承诺度（考试 / 手术 0.95、工作 / 上课 0.70、社交 0.50、休闲 0.20、刷手机 0.15）；中断候选须克服"承诺度壁垒 + 性格阈值（自控力 + 风险偏好）"。
- **情绪驱动即兴**：开心 / 压力 / 疲倦 / 无聊 / 焦虑 / 孤独各有即兴行为池（发动态、独自散步、小憩、找朋友聊天…）。
- **环境事件级联**：如"下雨 → 打车排队 → 烦躁"、"拥堵 → 迟到 → 工作压力"、"促销 → 购物冲动"。
- 另含需求中断（饥饿 / 疲劳 / 时间压力）、社交偶遇链，以及中断后的日程插入与恢复。

> 第 6 节的"物理环境感知与反应式重规划"是动态行为系统的进一步增强——把节点级拥挤 / 营业状态也接入中断与重规划。

### 5.5 兴趣爱好与技能成长

开关 `CONFIG["interests"]["enabled"]`。为每个智能体派生 `growth_profile`（兴趣、计划发展的技能、练习进度），影响日程、动作权重与工作选择；进度落在 `output/memory/agent_<id>_growth.json`，全局画像缓存于 `growth_profiles.json`。

成长动力学（v2，纯规则、零额外 LLM 调用，设计文档见 `docs/proposals/2026-07-04-personal-growth-v2.md`）：

- **幂律学习**：练习收益随水平递减；连续练习（streak）有动量加成；水平上穿 0.35 / 0.60 / 0.85 时向 episode 的 `growth_progress` 写入里程碑事件（入门/熟练/精通）。
- **发展四阶段**：按 Hidi & Renninger 模型从水平 + 累计练习量派生"触发期 → 维持期 → 浮现期 → 成熟期"，进入 prompt 上下文。
- **日终遗忘衰减**（`interests.decay`：`grace_days` / `daily_rate` / `floor`）：超过宽限期未练则掉水平，保持率随累计练习量提高、且阶段感知（触发期 ×1.5、成熟期 ×0.5），断练归零 streak。
- **兴趣集演化**（`interests.evolution`：`retire_after_days` / `adopt_chance` / `max_new_per_day`）：停滞的触发期条目会被放下（至少保留 1 项）；可从当日社交对象处习得新兴趣（社交传染），仿真日志中以 🌱 行提示。

### 5.6 干预评估

PolicySim 风格的推荐与曝光评估，**本地完成、无额外 API、不训练模型**。每步构造 Feed（关系推荐 / 个性化推荐 / 公共议题）→ 曝光控制启发式（相似立场过滤 + 多样性促进）→ 记录五项指标：`stance_score`、`toxicity_score`、`misinformation_risk`、`cross_viewpoint_exposure`、`intervention_reward`，写入 `output/intervention/intervention_metrics.csv`。

---

## 6. 新特性一：物理环境感知与反应式重规划

> 模块：`gaworld/world/local_physical.py`、`gaworld/memory/spatial_preferences.py`。
> 设计原则：**全部配置门控、纯规则（无新增 LLM 调用）、向后兼容**——缺数据时每一层自动空转。所有开关在 `CONFIG["environment"]`。
> 完整设计与参数表：[`docs/physical_env_perception_changelog.md`](physical_env_perception_changelog.md)。

它把城市地图里早已定义却从未被调用的节点级 `occupancy`（占用）与 `is_open`（营业）状态接入认知循环，让智能体真正感知并反应**当下身边**的物理环境。分五层（P0–P4）：

### P0 — 局部物理感知

每个 tick 从"谁在哪"重算节点占用，并写入仿真时间使营业判断生效。每个智能体感知前生成当前位置快照（**拥挤度 / 是否营业 / 当地天气 / 异常标记**），可选地以"身边的物理环境：…"片段注入感知上下文。

### P1 — 结构化事件反应

动态行为分类器优先读结构化信号（`type` / `topic` / `impact_tags`）而非关键词猜测，并把 `impact_tags`（mobility、stress、public_service…）作为中断优先级加成。局部物理状态也转为中断候选：拥挤 → "换个不那么挤的地方"；关门 → "改去其他开门的地方"（不可恢复，必须换地点）。

### P2 — 异常作为一等公民

`env/system.py` 给每个事件打 `anomaly` / `anomaly_score`，代表对常态的偏离——日常天气、小波动不算；极端 / 突发 / 应急 / 高严重度才算。异常会提升中断优先级、可强制不可恢复反应、情绪影响更强。局部"人流骤增"（占用率高且较上一 tick 跳变大）会涌现为 `crowd_anomaly` 中断。

### P3 — 当日重规划

`sim/_schedule.py` 的 `replan_affected_interval` 只重排**受影响的连续区间**（改址 / 顺延 / 丢弃），窗口外不动。当胜出中断是持续性异常时，把窗口内被打断的后续活动顺延到窗口之后，而不是只修补当前单步。

### P4 — 结构化空间学习（可持久化）

`spatial_preferences.py` 把**地点绑定**的异常经历（拥挤、关门，不含全城宏观异常）累积为该地点的规避分，按时段加权、按天衰减。规避分超阈值后，`redirect_for_aversion` 把智能体引导到同类、规避更低的替代地点。偏好按 agent 持久化到 `output/memory/agent_<id>_env_preferences.json`（仅 `stateful=True` 时），跨运行保留。

### 怎么开关 / 调参

四个独立开关，把任一块 `enabled` 设为 `False` 即回退该层：

```python
from gaworld.settings import CONFIG
env = CONFIG["environment"]
env["local_physical"]["enabled"]       # P0/P2 涌现异常
env["anomaly"]["enabled"]              # P2 检测
env["replan"]["enabled"]              # P3 区间重排
env["spatial_preferences"]["enabled"]  # P4 学习 + 持久化（还需顶层 stateful=True）
```

常用阈值（默认值）：`local_physical.crowd_busy_ratio=0.6` / `crowd_packed_ratio=0.9`、`anomaly.severity_threshold=0.65`、`replan.window_minutes=120`、`spatial_preferences.avoid_threshold=1.5` / `half_life_days=7.0`。

### 怎么观察它生效

1. 用 `verbose` 日志看感知里是否出现"身边的物理环境"片段；
2. 跑一个会造成拥挤 / 关门 / 突发的场景（见第 9 节 `compare-event`），看日志里有没有"换地方 / 顺延"类中断与重规划记录；
3. `stateful=True` 多跑几天，检查 `output/memory/agent_<id>_env_preferences.json` 里规避分是否累积、是否触发改址。

---

## 7. 新特性二：可复用 Skill 库

> 模块：`gaworld/skills/`。完整设计与 API：[`docs/SKILL_SYSTEM.md`](SKILL_SYSTEM.md)。

与"兴趣 / 技能成长"并行，Skill 库给智能体一批**可复用、可重排版的小技能**，思路接近 Claude Code 的 Skill。每条 Skill 是一个 **Markdown + YAML frontmatter** 文件（`name` / `description` / `triggers` / 正文），两种来源：

- **全局库** `data/skills/*.md`：手写，所有 agent 都能挂载（仓库已自带 `poster-layout-grid.md`、`structured-code-review.md`）；
- **私有库** `output/memory/agent_<id>_skills/*.md`：agent 从自己最近经历**自动提炼**得到。

运行时 Skill 会自动注入到 `perception` 提示词与工作 brief 的 `【可用技能】` 块里，影响认知与工作产物。

### 7.1 加一个全局技能

在 `data/skills/` 新建 `your-skill.md`：

```markdown
---
name: 海报网格排版
description: 用三栏网格 + 单一主色，快速给宣传海报定排版
triggers: [海报, 排版, 设计, poster]
source: global
---

1. 先选一个主色（占面积 ≥ 60%），再选 1 个对比色和 1 个中性色。
2. 把版面切成上 / 中 / 下三带，标题在上、主图在中、信息在下。
3. 留白边距 ≥ 8%；字号梯度按 4:2:1。
```

`skill_id` 就是文件名去掉 `.md`（支持中文）。重启仿真或 `registry.reload()` 后即可被发现。

### 7.2 挂载到某个 agent

```python
from gaworld.skills import SkillRegistry
SkillRegistry().attach_to_agent(agent, "your-skill")   # 全局技能挂到 agent
```

私有技能不需要挂载，`list_for_agent` 会自动算上；同 id 时**私有优先于全局**。

### 7.3 打开"从经历自动提炼私有技能"

默认**关闭**。打开：

```python
CONFIG["memory"]["skill_consolidation"]["enabled"] = True
# every_days=5 每 5 个仿真日跑一次；lookback_days=5；min_episodes=4
```

之后 `run_daily_memory_lifecycle` 会按周期给每个 agent 调一次提炼，写到其私有目录（同名覆盖、越改越准）。

### 7.4 注入开关

```python
CONFIG["skills"]["inject_into_cognition"]   # perception 提示词附 skill 列表（默认 ON）
CONFIG["skills"]["inject_into_work_brief"]  # 工作 brief 附【可用技能】（默认 ON）
CONFIG["skills"]["max_per_prompt"]          # cognition 注入上限（默认 4）
```

关掉开关或没有 skill 时，提示词不变——这是向后兼容的关键。

---

## 8. 新特性三：真实工作任务系统

> 模块：`gaworld/work/`。使用细节：[`docs/REAL_WORK_USAGE.md`](REAL_WORK_USAGE.md)；设计：[`docs/REAL_WORK_DESIGN.md`](REAL_WORK_DESIGN.md)。

让居民根据**职业 / 技能 / 兴趣**去做**真实**的工作，并能在一个 mock 工作机会市场上浏览、接单、结算。产物是真文件：

| deliverable | 产物 | 典型职业 |
|---|---|---|
| `html_landing` | `index.html` | 设计师 |
| `poster_svg` | `poster.svg` | 设计师 |
| `py_script` / `py_test` | `main.py` / `test_main.py` | 程序员 |
| `md_article` | `article.md` | 新媒体 |
| `lesson_plan` | `lesson_plan.md` | 教师 |
| `research_note` | `research_note.md` | 研究者 |

### 8.1 启用

通过配置门控（`gaworld/settings/integrations.py` 的 `real_work` 块）：

```python
CONFIG["real_work"]["enabled"] = True
CONFIG["real_work"]["market"]["enabled"] = True
```

也可用 `dashboard_config.json` / `GAWORLD_CONFIG_OVERRIDES` 等覆盖机制。启用后正常 `python generative_city_sim.py run`，会看到日志：

```
INFO gaworld.work.runtime derived capabilities for N agents (cache=output/work/capabilities.json)
INFO gaworld.work.worker  WorkerPool started (workers=2, timeout=600s)
```

### 8.2 产物在哪

```
output/work/
├── capabilities.json     职业 → 能力 映射缓存（LLM 派生）
├── queue.jsonl           任务队列事件日志
├── market.jsonl          市场事件日志
└── agent_<id>/<task_id>/ 该 agent 该任务的真实产物
```

`agent_<id>` 对应种子 CSV 里的 id，便于溯源。

### 8.3 与其它系统联动

- **兴趣 / 技能成长**：`growth_profile` 里计划发展的技能 / 兴趣会并入能力匹配面（不改 schema）；
- **Skill 库**：router 投递 brief 时用 `chosen_action + activity` 文本匹配 agent 持有的 Skill，最多取 3 个追加到 brief 末尾——**adapter 无需改动**，Skill 指导会自然进入工作上下文。

### 8.4 常用旋钮（`CONFIG["real_work"]`）

| 项 | 默认 | 作用 |
|---|---|---|
| `max_concurrent_tasks` | 2 | 后台并发的 LLM adapter 数（调高更快但更贵） |
| `task_timeout_seconds` | 600 | 单 adapter 超时（本地 ollama 慢可调到 1200） |
| `market.max_taken_per_agent_per_day` | 2 | 每 agent 每仿真日最多接单数 |
| `market.browse_probability_base` | 0.15 | 浏览市场基础概率 |
| `market.expire_after_sim_days` | 5 | 过期阈值 |

扩展任务池：往 `gaworld/work/market_seed.json` 加条目；写自定义 adapter 见 `REAL_WORK_USAGE.md` §6。

> **复现性提醒**：adapter 内不要碰全局 `random`，需要随机用 `random.Random(seed)` 局部实例，否则在 `max_concurrent_tasks > 1` 时会破坏 `random_seed` 复现性。

---

## 9. 事件对照实验

GAWorld 的招牌高级功能：在**有事件 / 无事件**两条分支并行跑并出对比报告。

```bash
python generative_city_sim.py compare-event \
  --event-name "临时交通限行" \
  --event-description "主干道限行导致通勤时间上升并影响出行决策" \
  --event-day 2 \
  --event-time 09:00 \
  --sim-days 3 \
  --llm-provider openai_gpt \
  --seed 42
```

结果写入 `output/comparisons/<时间戳_事件名>/`：

```
comparison_summary.md     ← 指标摘要（最重要）
comparison_metrics.csv    ← baseline / event / delta 全明细
with_event/    ...        ← 有事件分支（logs / memory / state / intervention）
without_event/ ...        ← 无事件分支（对照）
```

报告同时含常规状态指标（情绪 / 压力 / 经济安全 / 出行成本变化）与干预指标（stance / toxicity / misinformation / cross_viewpoint 差异）。`--seed` 保证可复现。

> 这是观察**新特性是否生效**的好入口：选一个会造成拥挤 / 关门 / 应急的事件，对比两分支的重规划与地点规避行为差异。

---

## 10. 访谈与 RAG 注入

**访谈单个智能体**（基于其当前记忆与状态回答）：

```bash
python generative_city_sim.py interview --agent-id 31 --question "你今天为什么选择这个行动？"
python generative_city_sim.py interview --agent-id 31 --questions-file questions.txt
```

**注入外部知识**（改变认知）：

```bash
python generative_city_sim.py rag-add --agent-id 31 \
  --text "周末更倾向于骑行和逛书店" --timestamp "2026-02-18 09:30" --source "manual"

python generative_city_sim.py rag-import --agent-id 31 \
  --file output/test_extra_info.txt --source "profile_notes"
```

**从社交内容创建新智能体**：

```bash
python generative_city_sim.py create-agent-from-social --url "https://weibo.com/..."
python generative_city_sim.py create-agent-from-social --file output/source_page.txt --name "新智能体"
```

---

## 11. 分布式 relay：多机通信

> 模块：relay 客户端 `gaworld/distributed/comm.py`（`DistributedRelayClient`）、relay 服务器 `gaworld/apps/distributed_comm_server.py`。
> 设计原则：**配置门控、连不上自动降级（`fail_fast=False` 时静默空转）、向后兼容**——不开启或单机运行完全不受影响。所有开关在 `CONFIG["distributed"]`。

当一次实验的智能体规模超过单机算力，或你想把不同人群放到不同机器上跑时，可以开启**分布式模式**：用一台 relay 服务器做"集合点"，每台机器（node）只跑自己负责的那部分智能体，跨机器的智能体之间通过 relay 交换消息（收件箱 / 跨机通信）。收到的远端消息会以「跨机器通信消息：…」片段注入对方的**感知上下文**，从而影响其后续 LLM 决策——这是一种规则化的轻量通信，发送侧不额外消耗 LLM。

### 11.1 架构

```
        ┌───────────────── relay 服务器 (HTTP, :8877) ─────────────────┐
        │     目录登记 · 消息收发 · 状态持久化 relay_state.json          │
        └────────▲──────────────────────────────────────▲──────────────┘
                 │ register / poll / send                │
        ┌────────┴────────┐                     ┌────────┴────────┐
        │  Node A (机器1)  │  ←──— 跨机消息 ——──→ │  Node B (机器2)  │
        │ local_agent_ids │                     │ local_agent_ids │
        │   = [1, 2, 3]   │                     │   = [4, 5, 6]   │
        └─────────────────┘                     └─────────────────┘
```

- **relay 服务器**：独立 HTTP 服务，默认 `0.0.0.0:8877`，把目录与消息持久化到 `output/distributed/relay_state.json`（最多保留 `max_messages` 条，默认 20000）。主要端点：`/health`、`/register`、`/directory`、`/message/send`、`/message/poll`、`/snapshot`。
- **relay 客户端**：每个仿真进程按 `CONFIG["distributed"]` 建一个 `DistributedRelayClient`，挂在仿真循环上——启动时 `register_agents` 登记本机智能体并换回**全集群目录**；每个 tick `poll_messages` 拉取发给本机智能体的来信（每人每步最多 `max_inbound_per_step` 条）；每个智能体动作后以 `send_probability` 概率 `send_agent_messages`，向某个远端智能体投递一条由其活动/反思/结果模板化而成的更新（每步最多 `max_outbound_per_step` 条）。
- **cluster（集群）**：逻辑分组，只有**同一 cluster** 的智能体能互相看见与通信；`node_id` 标识机器（留空自动用 `主机名-pid`）。
- **智能体分区**：每台机器用 `local_agent_ids` 指定自己负责的子集（开启分布式且非空时**覆盖**顶层 `agent_ids`）；远端对端默认从 relay 目录自动发现，也可用 `peer_agent_ids` 显式钉死。

> 同一台 relay 服务器也是 OpenClaw 外部智能体接入的后端（额外带 token 鉴权与 tick 时钟同步），那部分见 [`docs/OPENCLAW_INTEGRATION.md`](OPENCLAW_INTEGRATION.md)。

### 11.2 配置（`CONFIG["distributed"]`）

| 字段 | 默认 | 作用 |
|---|---|---|
| `enabled` | `True` | 本机是否参与分布式通信 |
| `cluster` | `"default"` | 集群名，**所有机器必须写一致** |
| `node_id` | `""` | 机器标识；留空自动 `主机名-pid` |
| `local_agent_ids` | `[]` | 本机负责的智能体子集；开启分布式且非空时覆盖 `agent_ids` |
| `peer_agent_ids` | `[]` | 显式远端对端；为空则从 relay 目录发现 |
| `send_probability` | `0.18` | 每次动作向远端发消息的概率 |
| `max_outbound_per_step` | `1` | 每步最多外发条数（设 `0` 则只收不发） |
| `max_inbound_per_step` | `3` | 每个智能体每步最多注入的来信条数 |
| `message_max_chars` | `160` | 单条消息截断长度 |
| `fail_fast` | `False` | relay 出错时抛异常，还是静默降级 |
| `relay.base_url` | `http://127.0.0.1:8877` | 客户端连接的 relay 地址 |
| `relay.timeout` | `3` | HTTP 超时（秒） |
| `server.host` / `server.port` | `0.0.0.0` / `8877` | `serve-distributed` 默认绑定 |
| `server.state_path` | `output/distributed/relay_state.json` | 服务器状态持久化路径 |
| `server.max_messages` | `20000` | relay 最多保留的消息条数 |

### 11.3 两台机器跑起来

**① 在其中一台（或单独一台）启动 relay 服务器：**

```bash
python generative_city_sim.py serve-distributed --host 0.0.0.0 --port 8877
# 看到 [distributed-relay] listening on http://0.0.0.0:8877 即成功
```

**② 在每个 node 上配置**（改 `config.py`，或用 dashboard / `GAWORLD_CONFIG_OVERRIDES` 覆盖）：

```python
CONFIG["distributed"]["enabled"]           = True
CONFIG["distributed"]["cluster"]           = "myexp"        # 所有机器写同一个
CONFIG["distributed"]["relay"]["base_url"] = "http://<relay-ip>:8877"  # 远端机器填 relay 的可达 IP
# 每台机器分到不重叠的子集：
CONFIG["distributed"]["local_agent_ids"]   = [1, 2, 3]      # Node A
# CONFIG["distributed"]["local_agent_ids"] = [4, 5, 6]      # Node B
```

**③ 每个 node 各自正常运行：**

```bash
python generative_city_sim.py run
```

Node A 的智能体触发外发时，消息按 `to_agent` 投到 relay；Node B 的智能体在下一次 poll 时收到，并在感知里看到「跨机器通信消息：…」。

> **想先在单机验证？** 启动 relay 后开两个终端，各自 `enabled=True`、`base_url=http://127.0.0.1:8877`、`local_agent_ids` 设成两个不重叠子集，即可在一台机器上模拟两个 node。

### 11.4 怎么观察它生效

```bash
curl http://<relay-ip>:8877/health                      # {"ok": true}
curl http://<relay-ip>:8877/snapshot                    # 集群数 / 已登记智能体数 / 消息总数
curl "http://<relay-ip>:8877/directory?cluster=myexp"   # 看到各机器登记的全部智能体
```

再配合 `GAWORLD_LOG_MODE=verbose` 跑，感知上下文里应出现「跨机器通信消息」片段；`output/distributed/relay_state.json` 里的消息数也会随运行增长。

### 11.5 常见坑

- **互相看不见** → 多半是 `cluster` 名不一致，或 `base_url` 还停在默认的 `127.0.0.1`（远端机器必须填 relay 的可达 IP，并在防火墙放行该端口）。
- **智能体重复** → 各机器的 `local_agent_ids` **不要重叠**，每个智能体只应活在一台机器上。
- **完全没有跨机消息** → 确认 relay 已启动且各 node `enabled=True`；调试期把 `fail_fast` 设为 `True`，连接问题会直接抛错而不是静默降级。
- **只想收不想发**（如某台机器只作观察）→ 把 `max_outbound_per_step` 设为 `0`。

---

## 12. Dashboard 使用指南

GAWorld 自带一个本地 Dashboard，用网页做配置、运行控制、记忆查看与访谈，适合不想敲命令行的场景。

启动：

```bash
python generative_city_sim.py dashboard --port 8766
# 浏览器打开 http://127.0.0.1:8766/dashboard
```

功能面板：

| 面板 | 作用 |
|---|---|
| 配置编辑 | 改仿真参数（天数、LLM 路由等） |
| 长时段快进 | 工具栏勾选「长时段快进」→ 每天一条日简报的快进模式；旁边「随机性」滑杆控制突发事件频率与状态波动幅度（配合较大的仿真天数，见 [3.1](#31-长时段快进fast-forward跑-10--60--600-天)） |
| Profile 编辑 | 改智能体画像 |
| 运行控制 | 启动 / 停止仿真 |
| 轨迹回放 | 可视化查看智能体移动轨迹 |
| 记忆查看 | 检查单个智能体的记忆内容 |
| 访谈执行 | 对智能体提问并查看回答 |
| 日志查看 | 实时查看运行日志 |

**配置覆盖**：Dashboard 的修改写入 `dashboard_config.json`，运行时**覆盖** `config.py` 的基础配置（`config.py` ← 基础，`dashboard_config.json` ← 覆盖）。想恢复原始值，删除 `dashboard_config.json` 即可。

### 12.1 Agent Studio（单智能体构建/查看器）

控制台工具栏点 **「Agent Studio ↗」**，或直接打开
`http://127.0.0.1:8766/site/dashboard/studio.html`。它聚焦**一个**智能体，
分七步展示与编辑，字段全部对应 GAWorld 的真实种子模型：

| 步骤 | 内容 | 数据来源 |
|---|---|---|
| 1 身份 | 姓名、性别、年龄、户籍、居住地、叙事 profile | 状态 CSV + profile MD |
| 2 状态 · 性格 | 九个 `[0,1]` 状态变量（滑块 + 可编辑雷达） | 状态 CSV |
| 3 能力 · 技能 | 全局技能库 | `data/skills` |
| 4 记忆 | 情节/习惯/意图/日程计数 + 记忆图谱 | `output/memory` |
| 5 社交 · 关系 | 真实 Dunbar 分层（inner/close/acquaintance/weak）+ 亲密度排序 | `output/memory/*_relationships.json` |
| 6 行为 · 目标 | 驱动行为的状态拨盘 | 状态 CSV |
| 7 复核 · 部署 | 摘要、可选采访、保存、用此居民运行仿真 | — |

**写回规则**：状态变量与身份写入状态 CSV
（`data/hangzhou_agents_state_init.csv`）并**同步**进 profile MD 的
`**核心状态变量**` 与 `**研究增强变量初始化**` 两处（CSV 为权威源，避免漂移）；
叙事编辑写 profile 块；「创建」追加一行 CSV + 一个 profile 块（复用导入-agent 的
格式，保留 BOM）。社交与财务面板读运行产物，未跑仿真时优雅降级为占位。

**后端 API**（`gaworld/apps/dashboard_server.py`）：
`GET /api/agents/{id}/state`、`GET /api/agents/{id}/detail`、`GET /api/skills`、
`POST /api/agents/{id}/state`、`POST /api/agents`（创建）。测试见
`tests/test_dashboard_studio.py`。

---

## 13. 配置与开关总表

基础配置入口 `config.py`（实际分层在 `gaworld/settings/`）。常用字段：

| 配置 | 作用 |
|---|---|
| `agent_ids` / `sim_days` / `seconds_per_day` | 参与 agent、仿真天数、每日现实秒数 |
| `long_run` | **新**：长时段快进（每天一条日简报、跳过日内时刻循环；`--fast-forward` 等价；`long_run.randomness` 控制突发事件与波动，见 [3.1](#31-长时段快进fast-forward跑-10--60--600-天)） |
| `llm.routing.default` / `llm.routing.tasks` | 默认 provider / 按任务覆盖 |
| `economy` | 个税、社保、恩格尔消费、投资、宏观周期、冲击、部门池守恒、信贷（`credit`）、agent 间路由（`routing`）、熟人借贷（`friend_loans`） |
| `interests` | 兴趣 / 技能成长（开关、上限、插入倾向、持久化、日终衰减 `decay`、兴趣集演化 `evolution`） |
| `dynamic_behavior` | 动态行为系统开关 |
| `environment.local_physical` / `.anomaly` / `.replan` / `.spatial_preferences` | **新**：物理感知与反应式重规划 |
| `skills` | **新**：Skill 库（全局目录、注入开关、单提示上限） |
| `memory.skill_consolidation` | **新**：经验 → Skill 提炼（默认 OFF） |
| `real_work` | **新**：真实工作任务系统 |
| `intervention` | PolicySim 风格干预评估 |
| `policy_events` / `distributed` | 政策事件 / 多机通信（relay，详见第 11 节） |

日志模式：`GAWORLD_LOG_MODE=simple|verbose`，`GAWORLD_LOG_LEVEL=DEBUG` 看 token / 延迟。

> Dashboard 的修改写入 `dashboard_config.json`，运行时覆盖 `config.py`；模型路由不符预期时同时检查这两处。

---

## 14. 输出文件地图

```
output/
├── logs/        run.log（完整）、agent_<id>.log
├── memory/      agent_<id>.json、agent_<id>_episodes.jsonl
│                agent_<id>_growth.json、growth_profiles.json
│                agent_<id>_env_preferences.json   ← 新：地点规避偏好
│                agent_<id>_skills/*.md            ← 新：私有 Skill
│                vector_db.sqlite
├── economy/     daily_ledger.csv（含 debt 列）、wealth_snapshot.csv、macro_state.json
│                sectors.json、conservation_audit.csv    ← 新：部门池 + 每日守恒审计
│                agents/agent_<id>_ledger.csv、agent_<id>_snapshot.json
├── environment/ timeline.jsonl
├── intervention/intervention_metrics.csv
├── network/     social_network.png
├── visualization/ simulation_trace.json、latest_frame.json
├── work/        capabilities.json、queue.jsonl、market.jsonl、agent_<id>/<task_id>/  ← 新
└── comparisons/ <事件名>/comparison_summary.md、comparison_metrics.csv
```

---

## 15. 常见问题

**Q: 报错 API key 缺失** — 检查环境变量是否设置，且 `config.py` 的 `llm.routing.default` 指向已配置的 provider。

**Q: 运行很慢** — 调小 `sim_days`、减少 `agent_ids`、关闭 `intervention` / `dynamic_behavior`、用更快的模型；启用了 `real_work` 可调低 `max_concurrent_tasks` 或先关掉它。

**Q: 改了配置后行为异常** — 仿真有状态记忆，先 `reset` 再 `run`。

**Q: 新特性看起来没生效** —
1. 物理感知：确认 `CONFIG["environment"]["local_physical"]["enabled"]=True`，用 `verbose` 看感知里有没有"身边的物理环境"；P4 还需顶层 `stateful=True` 才会落盘。
2. Skill 注入：确认 `CONFIG["skills"]["inject_into_*"]=True` 且该 agent 真的持有 / 已挂载 Skill。
3. 真实工作：确认 `CONFIG["real_work"]["enabled"]=True` 且看到 `WorkerPool started`；agent 接不到单多半是市场里没有匹配其 `job_label` 的 job 或当日配额用完。

**Q: 自动提炼私有 Skill 不产文件** — 默认 OFF，需要 `CONFIG["memory"]["skill_consolidation"]["enabled"]=True`；且最近 episodes 不足 `min_episodes`（默认 4）会跳过。

**Q: Dashboard 改了配置后想恢复原值** — Dashboard 的修改写在 `dashboard_config.json` 并在运行时覆盖 `config.py`；删除该文件即可回到 `config.py` 的原始配置。

**Q: 记忆文件看起来是乱码** — 它是 JSON 格式，用 `cat output/memory/agent_31.json | python -m json.tool` 格式化查看。

**Q: Python 完整测试套件报错** — 部分用例依赖 Python ≥ 3.11，建议在 3.11+ 跑 `pytest tests`。

---

## 16. 命令速查表

```bash
# 基本
python generative_city_sim.py run                  # 运行仿真
python generative_city_sim.py run --sim-days 600 --fast-forward  # 长时段快进：每天一条日简报
python generative_city_sim.py reset                # 重置（从 Day 1）
python generative_city_sim.py --help               # 帮助

# 服务
python generative_city_sim.py dashboard --port 8766
python generative_city_sim.py serve-viz --port 8000
python generative_city_sim.py serve-distributed --host 0.0.0.0 --port 8877

# 访谈 / RAG / 创建
python generative_city_sim.py interview --agent-id 31 --question "..."
python generative_city_sim.py rag-add --agent-id 31 --text "..."
python generative_city_sim.py rag-import --agent-id 31 --file ...
python generative_city_sim.py create-agent-from-social --url "..."

# 实验 / 地图
python generative_city_sim.py compare-event --event-name "..." --sim-days 3 --seed 42
python scripts/generate_citymap.py --description "..."

# 日志模式
GAWORLD_LOG_MODE=verbose python generative_city_sim.py run
GAWORLD_LOG_LEVEL=DEBUG  python generative_city_sim.py run
```

---

## 17. 微内核插件架构：扩展 GAWorld

自 2026-07 起，GAWorld 的所有子系统（干预、技能、兴趣成长、人生事件、
经济、物理感知、真实工作、动态行为、空间偏好）都运行在统一的微内核
插件接口上。这意味着三类以前需要改源码的操作，现在都是配置：

### 17.1 认知消融实验：改管线顺序

每个 agent step 是 12 个命名阶段的序列。想做"没有反思的 agent 会怎样"
这类消融实验，只需在配置里省略对应阶段：

```python
CONFIG["pipeline"]["agent_step"] = [
    "prepare", "perceive", "interrupts", "plan", "adjust_activity",
    "move", "select_action",              # 省略 "reflect" = 消融反思
    "update_state", "broadcast", "memorize", "record",
]
```

也可以在任意位置插入自定义阶段（`"my_pkg.stages:deliberate"` 形式的
导入路径），阶段签名为 `fn(agent, step, ctx)`。注意 `prepare` 与
`record` 是结构性阶段（钩子发射与日志落盘在其中），消融目标应是中间
的认知阶段。

### 17.2 编写插件：不改核心加子系统

一个最小插件——让 agent 在感知中听到谣言：

```python
# my_pkg/rumor.py
from gaworld.kernel import Plugin

class RumorPlugin(Plugin):
    id = "rumor"
    def setup(self, ctx):
        ctx.bus.on("perception.compose", self.inject)
    def inject(self, hook_ctx):
        return ["有人跟你提起：城东要修新地铁线（真实性存疑）"]
```

启用方式二选一：

```python
# 配置声明（路径可导入即可）
CONFIG["plugins"] = [{"class": "my_pkg.rumor:RumorPlugin"}]
```

```toml
# 或 pip 包的 entry point（安装即自动装配）
[project.entry-points."gaworld.plugins"]
rumor = "my_pkg.rumor:RumorPlugin"
```

事件目录（感知注入、中断征集、动作过滤、状态效果、episode 组装等
21 个事件）、三种钩子语义（observe / collect / filter）、状态与数据
所有权约定，见[插件作者指南](PLUGIN_AUTHORING.md)。内置的 9 个插件
本身就是最好的参考实现。

### 17.3 运行时干预：模拟跑着的时候改世界

`Controller.intervene` 提供可审计的运行时干预（每次调用都记录到
`output/records/controller.intervention.jsonl`）：

```python
sim.controller.intervene("set_agent_state", sim, agent_id=31, key="stress", value=0.8)
sim.controller.intervene("update_config", sim, path="economy.credit.apr", value=0.15)
sim.controller.intervene("inject_life_event", sim, event={"title": "老友来电", "day": 2, "time": "19:00", "agent_ids": [31]})
sim.controller.intervene("remove_agent", sim, agent_id=7)   # 下个日边界生效
```

在插件钩子、测试或 notebook 里都能调用（`sim` 即钩子上下文里的
`hook_ctx["sim"]`）。

### 17.4 动作校验

move 动作会经过 Controller 校验链：`location_exists`（默认开，拦截
幻觉地点）与 `venue_open`（默认关——硬拦关门场所会改变模拟动力学，
需要时 `CONFIG["controller"]["validators"]["venue_open"] = True` 开启）。
被拒绝的动作会审计落盘，且理由会出现在该 agent 下一个时间步的感知里
（"刚才的行动受阻：……"），agent 可以对此做出反应。

---

## 相关文档

- [English README](../README.md) · [中文 README](../README.zh-CN.md)
- [简明上手教程](TUTORIAL.md)（本教程已并入原 v1.0 完全教程的全部内容）
- [插件作者指南](PLUGIN_AUTHORING.md) · [微内核架构设计](proposals/2026-07-11-microkernel-plugin-architecture.md)
- [物理环境感知与反应式重规划](physical_env_perception_changelog.md)
- [Skill 系统设计与使用](SKILL_SYSTEM.md)
- [真实工作系统 — 使用](REAL_WORK_USAGE.md) · [设计](REAL_WORK_DESIGN.md)
- [项目结构](PROJECT_STRUCTURE.md) · [仓库规范](../AGENTS.md) · [更新日志](../CHANGELOG.md)
