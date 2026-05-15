# GAWorld 用户完全教程

**版本：v1.0 | 更新日期：2026年5月**

---

## 目录

1. [项目概述](#1-项目概述)
2. [安装与环境配置](#2-安装与环境配置)
3. [5分钟快速开始](#3-5分钟快速开始)
4. [项目结构详解](#4-项目结构详解)
5. [核心概念：智能体与仿真循环](#5-核心概念智能体与仿真循环)
6. [主要特性：记忆系统](#6-主要特性记忆系统)
7. [主要特性：经济仿真模块](#7-主要特性经济仿真模块)
8. [主要特性：位置系统与交通](#8-主要特性位置系统与交通)
9. [主要特性：动态行为系统](#9-主要特性动态行为系统)
10. [主要特性：干预评估](#10-主要特性干预评估)
11. [Dashboard使用指南](#11-dashboard使用指南)
12. [高级功能：事件对照实验](#12-高级功能事件对照实验)
13. [高级功能：智能体采访](#13-高级功能智能体采访)
14. [高级功能：RAG外部知识注入](#14-高级功能rag外部知识注入)
15. [配置文件详解](#15-配置文件详解)
16. [输出文件说明](#16-输出文件说明)
17. [常见问题与解决方案](#17-常见问题与解决方案)
18. [进阶资源](#18-进阶资源)

---

## 1. 项目概述

### 1.1 什么是 GAWorld

GAWorld（Generative Agent World）是一个**面向城市社会行为实验的生成式多智能体仿真系统**。它将人物画像、长期记忆、社会影响、环境扰动、政策事件、经济状态、地图移动和 LLM 决策过程组合到一个可回放、可对照、可扩展的模拟流程中。

> 简单来说：GAWorld 让50个（甚至更多）虚拟居民在你的电脑上"生活"几天，每个人都有工作、社交、财务状况和情绪变化，你可以通过实验观察社会现象。

### 1.2 能做什么

| 场景 | 说明 |
|------|------|
| 城市政策模拟 | 测试交通限行、补贴政策对居民行为的影响 |
| 社会行为研究 | 观察信息传播、情绪感染、社交网络的演变 |
| 智能体记忆实验 | 验证长期记忆、习惯养成对行为一致性的影响 |
| AI教育演示 | 展示多智能体系统如何涌现复杂社会现象 |
| 游戏化应用 | 构建具有真实社会行为的沙盒世界 |

### 1.3 核心能力一览

```
┌─────────────────────────────────────────────────────┐
│                    GAWorld 核心能力                  │
├─────────────────────────────────────────────────────┤
│  🧠 记忆系统     跨天累积 episodic + 长期总结        │
│  💰 经济仿真     个税/社保/投资/宏观周期             │
│  📍 位置系统     类别匹配/出行成本/通勤记忆          │
│  🎭 动态行为     情绪驱动/社交偶遇/需求中断          │
│  📊 干预评估     推荐曝光/立场/毒性/误信息风险       │
│  🔬 事件对照     有/无事件双分支并行对比             │
│  🎤 智能体采访   CLI 实时访谈任意智能体               │
│  📚 RAG注入      外部知识注入改变智能体认知           │
│  🖥️ Dashboard   可视化配置/运行控制/记忆查看       │
└─────────────────────────────────────────────────────┘
```

### 1.4 技术架构

```
用户输入/配置
     ↓
┌──────────────────────────────────┐
│    generative_city_sim.py        │  ← 主仿真器 + CLI
├──────────────────────────────────┤
│  LLM路由层 (llm_providers.py)     │  ← Ollama / OpenAI / Anthropic
├──────────────────────────────────┤
│  核心仿真引擎                     │
│  ├── memory_store.py   记忆存储   │
│  ├── economy_module.py 经济仿真   │
│  ├── city_map_system.py 位置系统  │
│  ├── dynamic_behavior.py 动态行为 │
│  ├── intervention_policy.py 干预   │
│  └── environment.py 环境事件      │
├──────────────────────────────────┤
│  输出层                           │
│  ├── logs/ 日志                   │
│  ├── memory/ 记忆文件             │
│  ├── visualization/ 轨迹回放      │
│  └── economy/ 经济数据            │
└──────────────────────────────────┘
```

---

## 2. 安装与环境配置

### 2.1 环境要求

| 项目 | 要求 |
|------|------|
| Python 版本 | ≥ 3.11（推荐 3.11 / 3.12） |
| 操作系统 | macOS / Linux / Windows |
| 内存 | 推荐 16GB 以上 |
| 网络 | 需要访问 LLM API（除非使用本地 Ollama） |

### 2.2 安装步骤

**Step 1：克隆项目**

```bash
cd /Users/cw/dev/GAWorld
```

**Step 2：安装依赖**

```bash
pip install -r requirements.txt
```

**Step 3：验证安装**

```bash
python generative_city_sim.py --help
```

如果看到帮助信息，说明安装成功。

### 2.3 LLM Provider 配置（必须）

GAWorld 运行时需要至少一个 LLM Provider。打开 `config.py` 并选择以下方式之一：

#### 方式一：使用 OpenAI（云端）

```bash
export OPENAI_API_KEY="your_key_here"
```

然后在 `config.py` 中确保 `llm.routing.default` 指向 `openai_gpt`。

#### 方式二：使用 Anthropic（云端）

```bash
export ANTHROPIC_API_KEY="your_key_here"
```

#### 方式三：使用本地 Ollama（离线）

```bash
# 安装 Ollama
brew install ollama        # macOS
# 或参考 https://ollai.cn

# 下载模型
ollama pull qwen2.5

# 启动 Ollama 服务（默认 port 11434）
ollama serve
```

然后在 `config.py` 中让 `llm.routing.default` 指向 `ollama_qwen`。

### 2.4 配置检查清单

```
✅ Python ≥ 3.11 已安装
✅ pip install -r requirements.txt 执行成功
✅ LLM API Key 已设置（环境变量）或 Ollama 已启动
✅ config.py 中 routing.default 指向正确的 provider
```

---

## 3. 5分钟快速开始

### 3.1 最短上手路径

只需3条命令即可完成第一次仿真：

```bash
# 1. 安装（如已完成可跳过）
pip install -r requirements.txt

# 2. 设置 API Key
export OPENAI_API_KEY="your_key_here"

# 3. 运行仿真
python generative_city_sim.py run
```

### 3.2 首次运行输出解读

运行后会看到类似输出：

```
=== Day 1 ===
── [李泽宇 @ 09:30] 上午工作 ──
Loc: 互联网公司
Act: 推进最重要的一项任务
Refl: 感受：情绪有一点波动；教训：下次要更早判断状态和代价...

── [周婉清 @ 10:15] 设计工作 ──
Loc: 滨江·创意园
Act: 整理设计稿，准备提交
Refl: 项目进度良好，对下一步充满信心...
...
```

每行代表：
- `[姓名 @ 时间]` 当前时间和智能体
- `Loc:` 当前所在地点
- `Act:` 当前执行的动作
- `Refl:` 反思（感受、教训、后续倾向）

### 3.3 仿真结束后看什么

运行完成后，查看 `output/` 目录：

```
output/
├── logs/                  ← 运行日志
├── memory/                ← 智能体记忆
├── state/                 ← CSV 格式状态变化
├── intervention/          ← 干预评估指标
├── network/              ← 社交网络图
├── visualization/        ← 轨迹回放文件
└── economy/              ← 经济数据
```

### 3.4 重置并重新开始

如果想从第一天重新开始（清除所有记忆）：

```bash
python generative_city_sim.py reset
python generative_city_sim.py run
```

---

## 4. 项目结构详解

### 4.1 目录结构

```
GAWorld/
├── generative_city_sim.py    ← 主仿真器 + CLI 入口（最重要的文件）
├── config.py                 ← 运行配置（兼容层，实际配置在 gaworld/settings/）
├── llm_providers.py          ← LLM provider 封装和路由
│
├── gaworld/                  ← 新包结构（代码库核心）
│   ├── settings/            ← 配置模块
│   │   ├── runtime.py        ← 仿真天数、路径、并发等
│   │   ├── llm.py            ← 模型路由
│   │   ├── economy.py        ← 经济配置
│   │   ├── behavior.py       ← 行为/干预/动态配置
│   │   └── overrides.py     ← dashboard 配置覆盖
│   ├── core/                 ← 核心抽象（Agent、Config 类型）
│   ├── io/                   ← IO 工具（HTTP guards、网页抓取）
│   └── apps/                 ← 应用入口（dashboard server）
│
├── data/                     ← 种子数据（不动）
│   ├── hangzhou_agents_state_init.csv   ← 50个智能体初始状态
│   ├── hangzhou_profiles_with_names.md  ← 50个智能体详细画像
│   └── citymap.md           ← 城市地图数据
│
├── site/                     ← 前端页面
│   ├── dashboard/           ← Dashboard（配置/运行控制）
│   └── simviz/              ← 轨迹回放查看器
│
├── scripts/                  ← 开发工具
├── docs/                     ← 文档
├── output/                   ← 生成结果（仿真后产生）
└── tests/                     ← 单元测试
```

### 4.2 关键文件说明

| 文件 | 作用 | 日常使用频率 |
|------|------|-------------|
| `generative_city_sim.py` | 仿真入口+CLI | **每天** |
| `config.py` | 运行参数 | 改配置时 |
| `llm_providers.py` | 模型调用 | 改路由时 |
| `data/*.csv` | 种子状态 | 改智能体时 |
| `site/dashboard/` | Web UI | 常用 |

### 4.3 数据文件格式

**智能体状态 CSV（hangzhou_agents_state_init.csv）**

```
id,name,gender,age,...,emotion,stress,econ_security,city_identity
1,李泽宇,男,24,...,0.58,0.62,0.50,0.48
2,周婉清,女,26,...,0.62,0.60,0.55,0.60
...
```

**城市地图（citymap.md）**

```
@node: North Block | kind=hub | district=North | category=residential | x=2.8 | y=3.2
@road: North Block -> Central Block | type=collector
@metro: M1 | color=#8f5bd8 | stops=North Block>Central Block>Riverside Bus Station...
```

---

## 5. 核心概念：智能体与仿真循环

### 5.1 什么是智能体（Agent）

GAWorld 中的每个智能体代表一个虚拟城市居民，拥有：

```
智能体 = 基本信息 + 状态变量 + 记忆 + 财务 + 关系网络
```

**基本信息**：姓名、年龄、职业、收入、居住地

**状态变量**（归一化到 [0, 1]）：

| 变量 | 含义 | 0→1 语义 |
|------|------|---------|
| emotion | 情绪 | 极度消极 → 高度积极 |
| stress | 压力 | 无压力 → 极高压力 |
| econ_security | 经济安全 | 极不安全 → 极度安全 |
| city_identity | 城市认同 | 强烈疏离 → 强烈认同 |

**增强变量**：

| 变量 | 含义 |
|------|------|
| policy_sensitivity | 对政策的敏感程度 |
| platform_dependence | 对平台（工作）的依赖程度 |
| risk_preference | 风险偏好 |
| voice_propensity | 公共表达倾向 |
| mobility_intent | 流动/迁移意愿 |

### 5.2 智能体循环（Core Loop）

每个智能体每天重复以下5步：

```
┌─────────────────────────────────────────┐
│           智能体每日循环                  │
│                                         │
│   ① 感知  → ② 计划  → ③ 日程生成        │
│       ↑                              ↓
│   ⑤ 反思  ← ④ 动作执行                  │
└─────────────────────────────────────────┘
```

**① 感知（Perception）**
收集当前时间、地点、天气、最近记忆、待办事项、社交信息

**② 计划（Planning）**
根据感知内容制定今日意图（growth_focus、social_plans 等）

**③ 日程/动作生成（Routine Generation）**
调用 LLM 生成一天的时间表，包括工作、交通、用餐、休闲等

**④ 动作执行（Action Execution）**
按时间顺序执行日程中的动作，更新位置和财务

**⑤ 反思与记忆更新（Reflection & Memory）**
记录 episode，更新长期记忆、习惯、关系

### 5.3 跨天累积的数据

随着仿真天数增加，系统会累积：

```
天数1 → 天数2 → 天数3 → ...
  ↓        ↓        ↓
记忆碎片   习惯形成   关系变化
意图跨天   技能成长   财务积累
```

---

## 6. 主要特性：记忆系统

### 6.1 记忆类型

GAWorld 实现了多层记忆架构：

```
┌────────────────────────────────────────────┐
│              记忆层次                       │
├────────────────────────────────────────────┤
│ 📝 短期记忆 (Short-term)                    │
│    - 当前 episode（正在发生的事件）          │
│    - 当天活动日志                           │
├────────────────────────────────────────────┤
│ 📚 情景记忆 (Episodic Memory)               │
│    - 每个行为决策的背景和结果               │
│    - 存储在 output/memory/agent_<id>.jsonl  │
├────────────────────────────────────────────┤
│ 🧠 长期总结 (Long-term Summary)             │
│    - 智能体对自身的认知和目标总结           │
│    - 跨天数保持一致性                       │
├────────────────────────────────────────────┤
│ 🔗 关系记忆 (Relationship Memory)          │
│    - 与其他智能体的关系变化                 │
│    - 社交互动历史                           │
└────────────────────────────────────────────┘
```

### 6.2 记忆存储位置

| 文件 | 内容 |
|------|------|
| `output/memory/agent_<id>.json` | 智能体完整记忆状态 |
| `output/memory/agent_<id>_episodes.jsonl` | 逐事件记录（每行动一条） |
| `output/memory/agent_<id>_growth.json` | 兴趣/技能成长进度 |
| `output/memory/growth_profiles.json` | 全局兴趣画像缓存 |
| `output/memory/vector_db.sqlite` | 向量数据库（语义搜索用） |

### 6.3 记忆召回机制

在每个感知阶段，智能体会检索相关记忆：

```
当前情境 → 向量检索 → 召回最相关的历史记忆 → 注入感知
```

例如：当智能体"陈一航"面临考试压力时，系统会检索：
- 过去考试的表现和反馈
- 应对压力的习惯策略
- 导师/同学的互动记录

---

## 7. 主要特性：经济仿真模块

### 7.1 经济模块架构

经济模块驱动一套基于真实中国经济体系的个人财务仿真：

```
┌──────────────────────────────────────────────────┐
│              经济仿真四大子系统                    │
├──────────────────────────────────────────────────┤
│ 💵 个税与社保                                     │
│    - 7档累进税率（3%→45%）                      │
│    - 五险一金（养老8%/医疗2%/失业0.5%/公积金8%）│
│    - 月免征额 5,000 元                           │
├──────────────────────────────────────────────────┤
│ 🛒 恩格尔系数消费模型                             │
│    - 低收入者：食品支出 ~48%，储蓄率 ~5%         │
│    - 高收入者：食品支出 ~15%，储蓄率 ~40%        │
│    - 8大消费类目按收入弹性分配                    │
├──────────────────────────────────────────────────┤
│ 🏦 多账户投资体系                                │
│    - 活期/储蓄/投资/公积金 四账户               │
│    - 保守型/稳健型/激进型 三种投资组合           │
│    - 月度投资收益模拟（ Gaussian 分布）          │
├──────────────────────────────────────────────────┤
│ 📈 宏观经济周期                                   │
│    - 四阶段：扩张→峰值→收缩→谷底                │
│    - 行业景气度独立波动                          │
│    - 每日通胀累积                               │
└──────────────────────────────────────────────────┘
```

### 7.2 经济状态输出

每次仿真后，经济数据写入以下文件：

| 文件 | 内容 |
|------|------|
| `output/economy/daily_ledger.csv` | 全局每日账本 |
| `output/economy/wealth_snapshot.csv` | 财富快照 |
| `output/economy/macro_state.json` | 宏观经济状态 |
| `output/economy/agents/agent_<id>_ledger.csv` | 单智能体流水 |
| `output/economy/agents/agent_<id>_snapshot.json` | 单智能体财富详情 |

### 7.3 经济冲击事件

个体层面随机触发：

| 事件 | 影响 |
|------|------|
| 裁员 | 收入削减 50–85%，恢复期 30–90 天 |
| 涨薪/晋升 | 收入提升，税率重算 |
| 大病医疗 | 社保报销 50–85%，影响情绪和支出 |
| 年终奖 | 第13个月工资 |

---

## 8. 主要特性：位置系统与交通

### 8.1 基于类别的空间匹配

GAWorld 使用**类别匹配**而非硬编码地点名称来决定智能体的移动：

```
活动类型 → 地点类别 → 地图节点 → 最佳选择
```

| 活动 | 映射到类别 |
|------|-----------|
| 工作 | industry / commerce / government |
| 上学 | education |
| 就医 | medical |
| 购物 | commerce |
| 休闲 | leisure |
| 通勤 | transit |

### 8.2 出行成本计算

每种交通方式有真实费率结构：

| 方式 | 费率结构 |
|------|---------|
| 公交 | 固定 2 元 |
| 地铁 | 起步 2 元 + 超过4公里后 0.45元/公里 |
| 出租车 | 起步 13 元 + 超过3公里后 2.5元/公里 |
| 私家车 | 油耗 + 停车费 |

**高峰时段附加**：
- 时间：7:00–9:00 / 17:00–19:00
- 效果：出行时间 × 1.45，出租车附加 × 1.3

### 8.3 天气感知模式

当天气状况激活时：
- 雨/雪天气：露天方式（步行/自行车/电动车）被惩罚
- 智能体自动切换到有遮蔽方式（公交/地铁/出租车）

### 8.4 通勤记忆

智能体追踪：
- 常去地点（高频目的地）
- 偏好交通方式
- 通勤路线统计（平均时间、出行次数）

这些数据反馈到位置决策中，形成习惯性出行模式。

---

## 9. 主要特性：动态行为系统

### 9.1 系统概述

`dynamic_behavior.py` 让智能体的行为更像真实人类，通过在 LLM 决策之前注入上下文感知的日程变更：

```
┌──────────────────────────────────────────────────┐
│         动态行为系统六大引擎                       │
├──────────────────────────────────────────────────┤
│ 🎯 中断引擎    基于承诺度评估是否打断当前活动     │
│ 😊 情绪引擎    情绪驱动的即兴行为池               │
│ 🍽️ 需求引擎    饥饿/疲劳/时间压力产生中断       │
│ 📩 社交引擎    消息触发和社交偶遇链               │
│ 🌤️ 环境引擎    天气/交通/新闻事件的级联反应     │
│ 📋 日程引擎    中断后的活动插入与恢复             │
└──────────────────────────────────────────────────┘
```

### 9.2 承诺度感知机制

每种活动有一个承诺度等级：

| 活动类型 | 承诺度 |
|---------|--------|
| 考试 / 手术 | 0.95 |
| 工作 / 上课 | 0.70 |
| 社交约会 | 0.50 |
| 休闲活动 | 0.20 |
| 刷手机 | 0.15 |

中断候选必须克服：**承诺度壁垒 + 性格阈值（自控力 + 风险偏好）**

### 9.3 情绪驱动的即兴行为

智能体情绪分为6类：

| 情绪 | 即兴行为例 |
|------|-----------|
| 开心 | 发朋友圈、与朋友分享 |
| 压力 | 独自散步、刷搞笑视频 |
| 疲倦 | 小憩、喝咖啡提神 |
| 无聊 | 刷社交媒体、找朋友聊天 |
| 焦虑 | 整理房间、规划未来 |
| 孤独 | 主动联系朋友、发动态 |

### 9.4 环境事件级联

```
下雨
  ├─ 打车排队 → 心情烦躁
  └─ 路面湿滑 → 可能摔倒 → 医疗支出

交通拥堵
  ├─ 可能迟到 → 工作压力
  └─ 心情变差

促销活动
  └─ 可能触发购物冲动
```

---

## 10. 主要特性：干预评估

### 10.1 什么是干预评估

`intervention_policy.py` 实现了一套 PolicySim 风格的推荐与曝光评估系统：

```
┌──────────────────────────────────────────────────┐
│              干预评估工作流                        │
├──────────────────────────────────────────────────┤
│ Step 1: 构造 Feed                                │
│   - 关系推荐（来自社交网络）                     │
│   - 个性化推荐（基于历史兴趣）                    │
│   - 公共议题（新闻/政策）                        │
├──────────────────────────────────────────────────┤
│ Step 2: 曝光控制启发式                           │
│   - 相似立场过滤                                 │
│   - 多样性促进                                   │
├──────────────────────────────────────────────────┤
│ Step 3: 评估指标记录                             │
│   - stance_score（立场得分）                     │
│   - toxicity_score（毒性得分）                   │
│   - misinformation_risk（误信息风险）            │
│   - cross_viewpoint_exposure（跨观点曝光）       │
│   - intervention_reward（干预奖励）              │
└──────────────────────────────────────────────────┘
```

### 10.2 关键特性

- **无需额外 API**：所有计算在本地完成，不调用外部内容审核
- **不涉及模型训练**：仅评估，不 SFT/DPO
- **按时间序列记录**：每个 step 都有指标快照

### 10.3 输出文件

```
output/intervention/intervention_metrics.csv
```

包含每日每智能体的5项干预指标。

---

## 11. Dashboard使用指南

### 11.1 启动 Dashboard

```bash
python generative_city_sim.py dashboard --port 8766
```

然后在浏览器打开：

```
http://127.0.0.1:8766/dashboard
```

### 11.2 Dashboard 功能一览

```
┌──────────────────────────────────────────────────┐
│              Dashboard 功能面板                   │
├──────────────────────────────────────────────────┤
│ ⚙️ 配置编辑    修改仿真参数（天数、LLM路由等）   │
│ 📝 Profile编辑  修改智能体画像                   │
│ ▶️ 运行控制    启动/停止仿真                     │
│ 📊 轨迹回放    可视化查看智能体移动轨迹          │
│ 🧠 记忆查看    检查单个智能体的记忆内容          │
│ 🎤 访谈执行    对智能体提问并查看回答            │
│ 📋 日志查看    实时查看运行日志                  │
└──────────────────────────────────────────────────┘
```

### 11.3 配置覆盖机制

Dashboard 的修改会写入 `dashboard_config.json`，该文件在运行时覆盖 `config.py` 中的基础配置。

```
config.py ← 基础配置
  ↓ 覆盖
dashboard_config.json ← Dashboard 修改
```

---

## 12. 高级功能：事件对照实验

### 12.1 功能说明

事件对照实验是 GAWorld 的核心高级功能之一。它能在**有事件**和**无事件**两条分支下并行运行仿真，并生成详细的对比报告。

### 12.2 使用方法

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

### 12.3 参数说明

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `--event-name` | 事件名称 | 临时交通限行 |
| `--event-description` | 事件描述 | 主干道限行导致... |
| `--event-day` | 事件发生在第几天 | 2 |
| `--event-time` | 事件发生时间 | 09:00 |
| `--sim-days` | 仿真总天数 | 3 |
| `--llm-provider` | 使用的模型 | openai_gpt |
| `--seed` | 随机种子（保证可复现） | 42 |

### 12.4 输出文件

对照实验结果写入 `output/comparisons/<时间戳_事件名>/`：

```
output/comparisons/20260514_临时交通限行/
├── comparison_summary.md           ← 指标摘要（最重要的文件）
├── comparison_metrics.csv          ← 所有指标明细
├── with_event/                     ← 有事件分支
│   ├── logs/
│   ├── memory/
│   ├── state/
│   └── intervention/
└── without_event/                   ← 无事件分支（对照）
    ├── logs/
    ├── memory/
    ├── state/
    └── intervention/
```

### 12.5 解读对照报告

`comparison_summary.md` 包含：

**常规状态指标**：
- 情绪平均值变化
- 压力水平变化
- 经济安全感变化
- 出行成本变化

**干预评估指标**：
- stance_score 的差异
- toxicity_score 的差异
- misinformation_risk 的变化
- cross_viewpoint_exposure 的变化

---

## 13. 高级功能：智能体采访

### 13.1 基本用法

直接对单个智能体提问：

```bash
python generative_city_sim.py interview \
  --agent-id 31 \
  --question "你今天为什么选择这个行动？"
```

### 13.2 批量问题

每行一个问题：

```bash
python generative_city_sim.py interview \
  --agent-id 31 \
  --questions-file questions.txt
```

`questions.txt` 示例：

```
你今天为什么选择这个行动？
你对目前的收入满意吗？
最近有什么烦恼？
```

### 13.3 采访问答示例

```
$ python generative_city_sim.py interview --agent-id 31 --question "你今天为什么选择这个行动？"

[智能体 31 李泽宇]
Q: 你今天为什么选择这个行动？
A: 今天上午主要是在推进项目进度。作为算法工程师，我需要在今天完成核心功能的开发，
   以保证下周评审能够顺利进行。同时最近组里气氛比较紧张，大家都担心绩效考核的结果...
```

---

## 14. 高级功能：RAG外部知识注入

### 14.1 功能说明

RAG（Retrieval-Augmented Generation）允许你在仿真过程中向智能体注入外部知识，改变其认知和行为。

### 14.2 单条注入

```bash
python generative_city_sim.py rag-add \
  --agent-id 31 \
  --text "周末更倾向于骑行和逛书店" \
  --timestamp "2026-02-18 09:30" \
  --source "manual"
```

### 14.3 文件导入

```bash
python generative_city_sim.py rag-import \
  --agent-id 31 \
  --file output/test_extra_info.txt \
  --source "profile_notes"
```

### 14.4 使用场景

| 场景 | 注入内容 |
|------|---------|
| 个性化偏好 | "周末喜欢去图书馆" |
| 事件影响 | "刚看完一部感人的电影" |
| 社交信息 | "刚和朋友吵架" |
| 政策了解 | "知道明天有暴雨警报" |

---

## 15. 配置文件详解

### 15.1 配置文件位置

GAWorld 使用分层的配置系统：

```
gaworld/settings/          ← 实际配置模块（推荐新代码使用）
      ├── runtime.py        ← 仿真天数、路径、并发
      ├── llm.py            ← 模型路由
      ├── economy.py        ← 经济参数
      ├── behavior.py       ← 行为/干预/动态
      └── overrides.py      ← Dashboard 覆盖

config.py                  ← 兼容入口（老代码用这个）
```

### 15.2 关键配置项

**基础运行参数**（在 `config.py` 或 `gaworld/settings/runtime.py`）：

```python
{
    "agent_ids": [1, 2, 3, ..., 50],   # 运行的智能体 ID
    "sim_days": 3,                       # 仿真天数
    "seconds_per_day": 86400,            # 每模拟天对应的现实秒数
}
```

**LLM 路由**（在 `llm_providers.py` 中定义）：

```python
{
    "providers": {
        "openai_gpt": {...},
        "ollama_qwen": {...},
        "anthropic_claude": {...},
    },
    "routing": {
        "default": "openai_gpt",
        "tasks": {
            "planning": "anthropic_claude",
            "reflection": "ollama_qwen",
        }
    }
}
```

**经济模块**：

```python
{
    "economy": {
        "tax": {
            "brackets": [             # 7档累进税率
                {"rate": 0.03, "floor": 0, "cap": 3000},
                {"rate": 0.10, "floor": 3000, "cap": 12000},
                ...
            ],
            "monthly_exemption": 5000  # 月免征额
        },
        "social_insurance": {
            "pension_rate": 0.08,      # 养老 8%
            "medical_rate": 0.02,      # 医疗 2%
            "housing_fund_rate": 0.08   # 公积金 8%
        },
        "spending": {...},
        "investment": {...},
        "macro": {...}
    }
}
```

**兴趣爱好系统**：

```python
{
    "interests": {
        "enabled": True,               # 启用兴趣爱好系统
        "max_items": 5,               # 成长项上限
        "insert_tendency": 0.5,       # 日程插入倾向
    }
}
```

**动态行为系统**：

```python
{
    "dynamic_behavior": {
        "enabled": True                # 启用动态行为
    }
}
```

**干预评估**：

```python
{
    "intervention": {
        "enabled": True,               # 启用干预评估
        "feed_sources": ["relational", "personalized", "headline"]
    }
}
```

### 15.3 日志模式配置

GAWorld 支持两种日志模式：

| 模式 | 环境变量 | 输出量 |
|------|----------|--------|
| `simple`（默认） | 默认 | ~4行/tick（标题+地点+动作+反思） |
| `verbose` | `GAWORLD_LOG_MODE=verbose` | 完整字段（感知/计划/记忆等） |

```bash
# 默认简单模式
python generative_city_sim.py run

# 详细模式
GAWORLD_LOG_MODE=verbose python generative_city_sim.py run

# DEBUG 级别（包含 token 计数和延迟）
GAWORLD_LOG_LEVEL=DEBUG python generative_city_sim.py run
```

---

## 16. 输出文件说明

### 16.1 完整输出目录树

```
output/
├── logs/
│   ├── run.log                  ← 完整运行日志
│   └── agent_<id>.log          ← 单智能体日志
│
├── memory/
│   ├── agent_<id>.json          ← 完整记忆状态
│   ├── agent_<id>_episodes.jsonl ← 逐事件记录
│   ├── agent_<id>_growth.json   ← 成长进度
│   ├── growth_profiles.json    ← 全局兴趣画像
│   └── vector_db.sqlite         ← 向量数据库
│
├── state/
│   └── agent_state_history.csv  ← 状态时间序列
│
├── intervention/
│   └── intervention_metrics.csv ← 干预评估指标
│
├── network/
│   └── social_network.png       ← 社交网络可视化
│
├── visualization/
│   ├── simulation_trace.json   ← 轨迹数据
│   └── latest_frame.json       ← 最新帧
│
├── economy/
│   ├── daily_ledger.csv         ← 全局每日账本
│   ├── wealth_snapshot.csv      ← 财富快照
│   ├── macro_state.json         ← 宏观经济状态
│   └── agents/
│       ├── agent_<id>_ledger.csv
│       └── agent_<id>_snapshot.json
│
├── environment/
│   └── timeline.jsonl           ← 环境事件时间线
│
└── comparisons/
    └── <event_name>/
        ├── comparison_summary.md
        └── comparison_metrics.csv
```

### 16.2 状态变量说明

`agent_state_history.csv` 包含以下列：

| 列名 | 说明 |
|------|------|
| day | 仿真天数 |
| time | 时间（HH:MM） |
| agent_id | 智能体 ID |
| emotion | 情绪值 |
| stress | 压力值 |
| econ_security | 经济安全值 |
| city_identity | 城市认同值 |
| location | 当前地点 |
| activity | 当前活动 |
| daily_travel_cost | 当日累计出行成本 |

### 16.3 干预指标说明

`intervention_metrics.csv` 包含以下列：

| 列名 | 说明 | 理想值 |
|------|------|--------|
| stance_score | 政治/社会立场得分 | 稳定 |
| toxicity_score | 内容毒性得分 | 低 |
| misinformation_risk | 误信息风险 | 低 |
| cross_viewpoint_exposure | 跨观点曝光度 | 适中 |
| intervention_reward | 干预奖励 | 高 |

---

## 17. 常见问题与解决方案

### 17.1 安装和依赖问题

**Q: 报错 `ModuleNotFoundError: No module named 'xxx'`**

```bash
pip install -r requirements.txt
```

确保在项目根目录执行。

---

**Q: Python 版本不兼容**

GAWorld 需要 Python ≥ 3.11。

```bash
python --version
# 如果 < 3.11，升级 Python
brew install python@3.11   # macOS
```

---

### 17.2 LLM 相关问题

**Q: 报错 `API key 缺失`**

1. 检查环境变量是否设置：
```bash
echo $OPENAI_API_KEY    # Linux/macOS
echo %OPENAI_API_KEY%   # Windows
```

2. 检查 `config.py` 中 `llm.routing.default` 是否指向已配置的 provider。

---

**Q: 运行很慢**

1. 减少仿真天数：`sim_days` 调小
2. 减少智能体数量：只选部分 `agent_ids`
3. 关闭干预评估：`CONFIG["intervention"]["enabled"] = False`
4. 关闭动态行为：`CONFIG["dynamic_behavior"]["enabled"] = False`
5. 使用更快的模型（GPT-4o 比 GPT-4 便宜且更快）

---

### 17.3 配置相关问题

**Q: 修改配置后行为异常**

仿真有状态记忆。修改关键配置后需要重置：

```bash
python generative_city_sim.py reset
python generative_city_sim.py run
```

---

**Q: Dashboard 配置覆盖了 config.py**

删除 `dashboard_config.json` 即可恢复使用 `config.py` 的原始值。

---

### 17.4 输出相关问题

**Q: 找不到输出文件**

检查 `config.py` 中 `memory_dir` 和 `log_dir` 的路径是否正确。默认在 `output/` 目录下。

---

**Q: 记忆文件格式乱码**

记忆文件是 JSON 格式。用以下命令格式化查看：

```bash
cat output/memory/agent_31.json | python -m json.tool
```

---

## 18. 进阶资源

### 18.1 进阶学习路径

```
第1阶段：基础使用
  ↓ 学会基本运行、查看输出、理解仿真循环
第2阶段：配置调优
  ↓ 根据研究需求调整经济参数、干预设置、行为开关
第3阶段：对照实验
  ↓ 掌握事件对照实验设计和报告解读
第4阶段：定制开发
  ↓ 修改源码、添加新智能体类型、新事件类型
第5阶段：集成应用
  ↓ 与外部系统集成、大规模仿真、发布分享
```

### 18.2 相关文档

| 文档 | 内容 |
|------|------|
| `README.md` | 英文项目说明 |
| `README.zh-CN.md` | 中文项目说明 |
| `docs/TUTORIAL.md` | 简明教程 |
| `docs/PROJECT_STRUCTURE.md` | 项目结构详解 |
| `AGENTS.md` | 仓库规范和贡献指南 |
| `CHANGELOG.md` | 完整更新历史 |

### 18.3 命令速查表

```bash
# 基本操作
python generative_city_sim.py run              # 运行仿真
python generative_city_sim.py reset            # 重置
python generative_city_sim.py --help           # 查看帮助

# Dashboard
python generative_city_sim.py dashboard --port 8766

# 轨迹回放
python generative_city_sim.py serve-viz --port 8000

# 采访
python generative_city_sim.py interview --agent-id 31 --question "..."

# 事件对照
python generative_city_sim.py compare-event --event-name "..." --sim-days 3

# RAG 注入
python generative_city_sim.py rag-add --agent-id 31 --text "..."

# 城市地图生成
python scripts/generate_citymap.py --description "..."
```

### 18.4 社区和支持

- 项目主页：https://github.com/your_username/GAWorld
- 问题反馈：https://github.com/your_username/GAWorld/issues
- 文档更新：欢迎提交 PR 完善教程

---

**祝你玩得开心！** 🚀

> GAWorld 让每个人都能成为城市社会行为的"实验科学家"。