# GAWorld 教程 v2

**面向第一次到进阶使用 GAWorld 的用户 | 更新日期：2026 年 6 月**

> 这是 GAWorld 的**完整教程**——已并入原 v1.0 完全教程的全部内容，单文件自包含。更简短的快速上手见 [`docs/TUTORIAL.md`](TUTORIAL.md)。
> 在既有特性详解（第 5 节）之外，本版补全了三块**新特性**（物理环境感知与反应式重规划、可复用 Skill 库、真实工作任务系统）与**分布式 relay 多机通信**。

---

## 目录

1. [GAWorld 是什么](#1-gaworld-是什么)
2. [安装与 LLM 配置](#2-安装与-llm-配置)
3. [5 分钟跑通第一次仿真](#3-5-分钟跑通第一次仿真)
4. [核心概念：智能体与仿真循环](#4-核心概念智能体与仿真循环)
5. [既有特性详解](#5-既有特性详解)
6. [新特性一：物理环境感知与反应式重规划](#6-新特性一物理环境感知与反应式重规划)
7. [新特性二：可复用 Skill 库](#7-新特性二可复用-skill-库)
8. [新特性三：真实工作任务系统](#8-新特性三真实工作任务系统)
9. [事件对照实验](#9-事件对照实验)
10. [访谈与 RAG 注入](#10-访谈与-rag-注入)
11. [分布式 relay：多机通信](#11-分布式-relay多机通信)
12. [Dashboard 使用指南](#12-dashboard-使用指南)
13. [配置与开关总表](#13-配置与开关总表)
14. [输出文件地图](#14-输出文件地图)
15. [常见问题](#15-常见问题)
16. [命令速查表](#16-命令速查表)

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
├── economy/        账本、财富快照、宏观状态
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

基于中国个人财务体系的四大子系统（配置见 `CONFIG["economy"]`，源文件 `gaworld/settings/economy.py`）：

- **个税与社保**：7 档累进税率（3%→45%）、月免征额 5000 元；五险一金按个人缴费率扣缴（养老 8% / 医疗 2% / 失业 0.5% / 公积金 8%）。
- **恩格尔系数消费**：低收入者食品支出占比高、储蓄率低，高收入者相反；8 大消费类目按收入弹性分配。
- **多账户投资**：活期 / 储蓄 / 投资 / 公积金四账户，保守 / 稳健 / 激进三种组合，月度收益按高斯分布模拟。
- **宏观经济周期**：扩张 → 峰值 → 收缩 → 谷底四阶段，行业景气独立波动，每日通胀累积。

个体随机触发的经济冲击事件：

| 事件 | 影响 |
|---|---|
| 裁员 | 收入削减 50–85%，恢复期 30–90 天 |
| 涨薪 / 晋升 | 收入提升，税率重算 |
| 大病医疗 | 社保报销 50–85%，影响情绪与支出 |
| 年终奖 | 第 13 个月工资 |

经济数据写入 `output/economy/`（`daily_ledger.csv`、`wealth_snapshot.csv`、`macro_state.json`、`agents/agent_<id>_*`）。

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
| Profile 编辑 | 改智能体画像 |
| 运行控制 | 启动 / 停止仿真 |
| 轨迹回放 | 可视化查看智能体移动轨迹 |
| 记忆查看 | 检查单个智能体的记忆内容 |
| 访谈执行 | 对智能体提问并查看回答 |
| 日志查看 | 实时查看运行日志 |

**配置覆盖**：Dashboard 的修改写入 `dashboard_config.json`，运行时**覆盖** `config.py` 的基础配置（`config.py` ← 基础，`dashboard_config.json` ← 覆盖）。想恢复原始值，删除 `dashboard_config.json` 即可。

---

## 13. 配置与开关总表

基础配置入口 `config.py`（实际分层在 `gaworld/settings/`）。常用字段：

| 配置 | 作用 |
|---|---|
| `agent_ids` / `sim_days` / `seconds_per_day` | 参与 agent、仿真天数、每日现实秒数 |
| `llm.routing.default` / `llm.routing.tasks` | 默认 provider / 按任务覆盖 |
| `economy` | 个税、社保、恩格尔消费、投资、宏观周期、冲击 |
| `interests` | 兴趣 / 技能成长（开关、上限、插入倾向、持久化） |
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
├── economy/     daily_ledger.csv、wealth_snapshot.csv、macro_state.json
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

## 相关文档

- [English README](../README.md) · [中文 README](../README.zh-CN.md)
- [简明上手教程](TUTORIAL.md)（本教程已并入原 v1.0 完全教程的全部内容）
- [物理环境感知与反应式重规划](physical_env_perception_changelog.md)
- [Skill 系统设计与使用](SKILL_SYSTEM.md)
- [真实工作系统 — 使用](REAL_WORK_USAGE.md) · [设计](REAL_WORK_DESIGN.md)
- [项目结构](PROJECT_STRUCTURE.md) · [仓库规范](../AGENTS.md) · [更新日志](../CHANGELOG.md)
