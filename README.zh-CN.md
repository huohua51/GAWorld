# GAWorld

[English](./README.md) | [中文](./README.zh-CN.md)

GAWorld 是一个面向城市社会行为实验的生成式多智能体仿真项目。
它把人物画像、长期记忆、社会影响、环境扰动、政策事件、经济状态、地图移动、轻量平台干预评估和 LLM 决策过程组合到一个可回放、可对照、可扩展的模拟流程中。

## 项目概览

GAWorld 的目标不是简单地“跑一群 Agent”，而是提供一个可控制的社会实验场。你可以：

- 让同一批智能体在不同事件或政策条件下运行
- 并行比较有事件和无事件的反事实场景
- 保留跨天记忆、习惯、意图和关系变化
- 检查轨迹、日志、访谈结果和记忆文件
- 在不增加外部 API 的情况下评估 PolicySim 风格的推荐 / 曝光干预
- 通过本地 dashboard 修改配置、人物 profile 并控制运行

适用场景包括：

- 城市治理和政策影响模拟
- Agent 记忆架构与行为一致性实验
- 社会行为与风险传播研究
- 复杂系统或智能体仿真的课程演示

## 核心流程

每个智能体会循环经历：

1. 感知
2. 计划
3. 日程 / 动作生成
4. 动作执行
5. 反思与记忆更新

随着天数推进，系统会持续累积：

- episode 记忆
- 长期总结
- 基于上下文的习惯
- 日级意图
- 关系变化
- 收支与资产变化

## 主要能力

- 从 CSV 状态种子和 Markdown profile 构建智能体
- 从社交媒体页面或提取文本创建新智能体
- 多后端 LLM 路由：Ollama、OpenAI 兼容、Anthropic 兼容
- 支持通过 CLI 或文件注入外部 RAG 信息
- 政策事件和环境事件模拟
- PolicySim 风格的推荐 / 曝光干预指标
- 真实个人经济仿真（个税、五险一金、恩格尔系数消费、投资理财、宏观经济周期）
- 真实位置系统：基于类别的空间匹配、出行成本计算、高峰时段和天气影响、通勤记忆
- 动态行为系统：情绪驱动的即兴行为、社交偶遇链、需求中断、环境事件连锁反应、承诺度感知的日程中断
- 城市地图生成与轨迹回放
- 可视化 trace 导出
- 单智能体采访 CLI
- 本地 dashboard：配置编辑、profile 编辑、运行控制、记忆查看、访谈
- 多机分布式 relay 通信模式

## 项目结构

- `generative_city_sim.py`：主仿真器和 CLI 入口
- `config.py`：运行配置
- `llm_providers.py`：模型 provider 封装和路由逻辑
- `environment.py`：环境事件系统
- `intervention_policy.py`：轻量推荐、曝光控制、立场和风险指标
- `human_realism.py`：真实感增强、习惯、意图、记忆整合
- `economy_module.py`：真实个人经济模块（个税、社保、恩格尔系数消费、投资、宏观周期）
- `dynamic_behavior.py`：动态行为系统（即兴行为、社交链、需求中断、环境响应、日程插入）
- `memory_store.py`：记忆持久化和向量库辅助
- `city_map_system.py`：地图图结构、路线、出行和 tile map
- `simulation_visualizer.py`：地图回放 trace 输出
- `dashboard_server.py`：本地 dashboard 后端
- `hangzhou_agents_state_init.csv`：智能体初始状态
- `hangzhou_profiles_with_names.md`：智能体画像
- `citymap.md`：城市地图数据
- `site/dashboard/`：dashboard 前端
- `site/simviz/`：轨迹回放页面
- `output/`：生成结果

## 快速开始

安装依赖：

```bash
pip install -r requirements.txt
```

运行仿真：

```bash
python generative_city_sim.py run
```

重置状态：

```bash
python generative_city_sim.py reset
```

启动 dashboard：

```bash
python generative_city_sim.py dashboard --port 8766
```

然后打开：

```text
http://127.0.0.1:8766/dashboard
```

单独启动轨迹回放页面：

```bash
python generative_city_sim.py serve-viz --port 8000
```

然后打开：

```text
http://127.0.0.1:8000/site/simviz/index.html
```

## CLI 用法

查看帮助：

```bash
python generative_city_sim.py --help
```

运行仿真：

```bash
python generative_city_sim.py run
```

重置仿真：

```bash
python generative_city_sim.py reset
```

采访单个智能体：

```bash
python generative_city_sim.py interview --agent-id 31 --question "你今天为什么这样行动？"
python generative_city_sim.py interview --agent-id 31 --questions-file questions.txt
```

从社交内容创建新智能体：

```bash
python generative_city_sim.py create-agent-from-social --url "https://weibo.com/..."
python generative_city_sim.py create-agent-from-social --file output/source_page.txt --name "新智能体"
```

添加外部 RAG 信息：

```bash
python generative_city_sim.py rag-add \
  --agent-id 31 \
  --text "周末更喜欢骑行和逛书店" \
  --timestamp "2026-02-18 09:30" \
  --source "manual"
```

导入外部 RAG 信息：

```bash
python generative_city_sim.py rag-import \
  --agent-id 31 \
  --file output/test_extra_info.txt \
  --source "profile_notes"
```

执行事件对照实验：

```bash
python generative_city_sim.py compare-event \
  --event-name "临时交通限行" \
  --event-description "主干道限行导致通勤时间上升并影响出行决策" \
  --event-day 2 \
  --event-time 09:00 \
  --sim-days 3 \
  --llm-provider minimax \
  --seed 42
```

对照报告会同时包含常规城市状态指标和干预指标，例如 `stance_score`、`toxicity_score`、
`misinformation_risk`、`cross_viewpoint_exposure`、`intervention_reward`。

生成城市地图：

```bash
python generate_citymap.py --description "a small city with about 1000 residents, in east china"
```

启动分布式 relay：

```bash
python generative_city_sim.py serve-distributed --host 0.0.0.0 --port 8877
```

## Dashboard

本地 dashboard 支持：

- 编辑运行参数
- 选择 LLM 路由
- 编辑 profile
- 启动 / 停止仿真
- 查看轨迹回放
- 查看单个智能体记忆
- 执行访谈
- 查看运行日志

dashboard 会把本地覆盖参数写入 `dashboard_config.json`。
这个文件会在运行时覆盖 `config.py` 中的基础配置。

## 配置说明

基础配置位于 `config.py`。

重点字段包括：

- `agent_ids`：参与仿真的智能体 ID
- `sim_days`：仿真天数
- `seconds_per_day`：每个模拟日对应的现实秒数
- `time_step_minutes`：可选固定时间步长
- `llm.providers`：模型 provider 列表
- `llm.routing.default`：默认 provider
- `llm.routing.tasks`：按任务覆盖 provider
- `memory_dir`、`log_dir`、`vector_db_path`：持久化路径
- `visualization.output_dir`：轨迹输出目录
- `economy`：个人财务配置（税率表、社保费率、恩格尔曲线、投资参数、宏观周期、冲击事件）
- `dynamic_behavior`：动态行为系统配置（启用开关）
- `intervention`：轻量推荐 / 曝光控制和干预评估配置
- `policy_events`：政策事件
- `distributed`：多机通信配置

### PolicySim 风格干预评估

`CONFIG["intervention"]` 默认开启一个确定性、无网络依赖的干预层。每个智能体 step 会从关系动态、
个性化内容和公共议题中构造小型 feed，经过本地曝光控制启发式处理后注入感知，并记录立场、毒性、
误信息、跨观点曝光和干预奖励指标。

该功能不执行 SFT/DPO 模型训练，也不会调用外部内容审核 API。

### 经济模块

`CONFIG["economy"]` 驱动一套基于中国经济体系的真实个人财务仿真。每个智能体拥有完整的财务画像，
通过四个相互关联的子系统随仿真时间演进：

**个税与五险一金**

每个智能体有一个基于职业和能力推导的税前月薪。模块计算个人社保缴纳（养老 8%、医疗 2%、失业
0.5%、住房公积金 8%），缴费基数下限 4,462 元、上限 36,000 元。个人所得税使用中国 7 档累进
税率表（3%–45%），月免征额 5,000 元，支持专项附加扣除配置。完整的 `税前 → 社保扣除 → 个税
→ 到手工资` 流水线在初始化时运行，并在月结时根据薪资变化自动重算。

**恩格尔系数消费模型**

消费预算不再使用固定随机区间，而是根据收入水平查询恩格尔系数曲线：低收入者食品支出占消费的
~48%、储蓄率 ~5%；高收入者食品占 ~15%、储蓄率 ~40%。八大消费类目（食品、住房、交通、服装、
休闲、教育、医疗、杂项）按收入弹性系数加权分配——必需品（食品 0.5、医疗 0.6）随收入增长慢，
奢侈品（休闲 1.5、服装 1.2）增长快。月预算在薪资变动时自动重新计算。

**多账户体系与投资理财**

每个智能体持有四个账户：活期、储蓄、投资和公积金。风险偏好映射到三种投资组合——保守型
（定期存款 70% / 基金 25% / 股票 5%）、稳健型（40/40/20）、激进型（15/35/50）。每月按
高斯分布模拟各资产类别的投资收益（定期存款年化 ~2.5%、基金 ~6%±8%、股票 ~8%±22%）。超出
缓冲阈值的活期余额自动转入储蓄和投资账户。

**宏观经济周期与冲击事件**

仿真级别维护一个四阶段宏观周期——扩张、峰值、收缩、谷底——每个阶段持续 60–180 天。不同阶段
对收入、支出、裁员风险和加薪概率施加不同倍率。行业景气度（科技、金融、医疗、教育、服务、贸易）
独立波动。通胀按日累积，侵蚀购买力。个体层面有随机经济冲击事件：裁员（收入削减 50–85%，恢复期
30–90 天）、涨薪/晋升、大病医疗（社保报销 50–85%）、年终奖（第13个月工资）。

经济模块的输出包括 `output/economy/daily_ledger.csv`、每智能体账本、财富快照和
`macro_state.json`。

### 位置系统

`city_map_system.py` 提供了一套真实的空间层，用于智能体的移动决策。系统使用基于类别的
空间匹配来解析智能体在任意活动下应前往的地点，而不依赖硬编码的地点名称。

**出行成本计算**

每种交通方式都有基于中国城市公共交通的费率结构：公交固定票价（2 元）、地铁按距离计费
（起步 2 元 + 超过 4 公里后每公里 0.45 元）、出租车起步价加里程费（起步 13 元 + 超过
3 公里后每公里 2.5 元）、私家车按油耗和停车费计算。高峰时段检测（7:00–9:00、
17:00–19:00）对出行时间施加 1.45 倍乘数，出租车加收 1.3 倍附加费。出行成本从智能体
经济模块的交通支出类目中扣除。

**天气感知的出行方式选择**

当存在天气状况时，交通方式选择器会使用天气调整权重重新评估。在雨雪天气下，步行、自行车、
电动车等露天出行方式受到大幅惩罚，智能体会转向公交、地铁、出租车等有遮蔽的替代方式。

**基于类别的地点解析**

活动和职业通过关键词词典映射到地点类别（教育、医疗、商业、休闲、交通等）。空间解析器
从智能体当前位置出发，查找最近的匹配节点，并结合时间段偏好、智能体画像和习惯偏好进行
加权选择。这替代了之前硬编码地点名称列表的方式，使系统可以适配任意城市地图。

**通勤记忆**

智能体追踪常去地点、偏好交通方式和通勤路线统计（平均出行时间、出行次数）。这些数据
随仿真天数积累，并反馈到位置决策中——智能体会形成习惯性的出行模式，偏好熟悉的地点。

**区域价格水平**

不同区域类别带有价格水平乘数（商业区 1.35 倍、工业区 0.80 倍、教育区 0.85 倍等），
影响智能体在该区域内的消费行为。

### 动态行为系统

`dynamic_behavior.py` 通过注入上下文感知的日程变更，让智能体的每日行程更接近真实人类。该系统
通过 `CONFIG["dynamic_behavior"]["enabled"]` 开关控制，每个智能体每个时间步执行一次，在
LLM 调用之前完成决策。

**承诺度感知的中断机制**

每种活动都有一个承诺度等级（考试/手术 0.95、工作 0.70、刷手机 0.15）。中断候选必须克服承诺度
壁垒和性格阈值（自控力、风险偏好）才能改变已安排的活动。即使净优先级为正的中断也会经过随机接受
门控，避免行为过于机械。

**情绪驱动的即兴行为**

智能体的情绪状态被分类为六种情绪类别（开心、压力、疲倦、无聊、焦虑、孤独）。每种情绪映射到一组
场景化的即兴行为池——压力大的智能体可能想独自散步，无聊的智能体可能拿起手机刷社交媒体。时段过滤
器阻止不合理的行为（深夜不会想去购物），性格缩放调节概率（外向型有更多社交冲动）。

**社交偶遇链**

当多个智能体处于同一地点时，系统根据关系亲密度和社交需求计算偶遇概率。亲密好友可能互相邀约吃饭
（感知午餐/晚餐时段），普通熟人交换简短寒暄，陌生人之间可能发生行为传染——跟着别人排队买奶茶、
围观街头事件。

**环境事件连锁反应**

天气、交通、商业、新闻和紧急事件被分类并转换为中断候选，优先级根据性格差异化调整（谨慎型对天气
+30% 敏感度，好奇型对商业活动 +40% 兴趣）。主事件可以触发连锁反应：下雨→打车排队+路面湿滑，
暴风→交通延误+快递延迟，交通拥堵→可能迟到+心情变差。连锁事件按概率触发并累积情绪效果。

**需求中断**

生理需求（饥饿、疲劳）和任务压力生成中断候选。饥饿中断在用餐时段获得额外加成。低能量触发休息
冲动。高时间压力推动智能体处理紧急事务。

**日程插入与恢复**

当中断胜出时，系统可以将新活动插入到日程中并支持恢复——被中断的活动在插入活动结束后自动恢复，
前提是日程中有足够的时间空隙。

### LLM 后端

项目支持：

- `ollama`
- OpenAI 兼容接口
- Anthropic 兼容接口

对于中国区 Minimax 的 Anthropic 兼容接口，当前支持：

- `ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic`
- `MINIMAX_API_KEY` 或 `ANTHROPIC_AUTH_TOKEN`

## 输出文件

主要输出位于 `output/`，包括：

- `output/logs/agent_<id>.log`
- `output/memory/agent_<id>.json`
- `output/memory/agent_<id>_episodes.jsonl`
- `output/memory/vector_db.sqlite`
- `output/economy/daily_ledger.csv`、`wealth_snapshot.csv`、`macro_state.json`
- `output/economy/agents/agent_<id>_ledger.csv`、`agent_<id>_snapshot.json`
- `output/environment/timeline.jsonl`
- `output/intervention/intervention_metrics.csv`
- `output/visualization/simulation_trace.json`
- `output/visualization/latest_frame.json`
- `output/network/`
- `output/state/`

## 说明

- `dashboard_config.json` 会覆盖 `config.py`
- `stateful` 模式下会复用之前运行留下的记忆和日程
- 如果改了记忆 schema 相关配置，需要先执行 `reset`
- 如果运行时模型路由和预期不一致，同时检查 `config.py` 和 `dashboard_config.json`

## 更多文档

- [English README](./README.md)
- [用户教程](./TUTORIAL.md)
- [仓库规范](./AGENTS.md)
