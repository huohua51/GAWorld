# GAWorld

[English](./README.md) | [中文](./README.zh-CN.md)

GAWorld 是一个面向城市社会行为实验的生成式多智能体仿真项目。
它把人物画像、长期记忆、社会影响、环境扰动、政策事件、经济状态、地图移动和 LLM 决策过程组合到一个可回放、可对照、可扩展的模拟流程中。

## 项目概览

GAWorld 的目标不是简单地“跑一群 Agent”，而是提供一个可控制的社会实验场。你可以：

- 让同一批智能体在不同事件或政策条件下运行
- 并行比较有事件和无事件的反事实场景
- 保留跨天记忆、习惯、意图和关系变化
- 检查轨迹、日志、访谈结果和记忆文件
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
- 经济 / 财富模块
- 基于位置和出行的动作决策
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
- `human_realism.py`：真实感增强、习惯、意图、记忆整合
- `economy_module.py`：经济 / 财富模块
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
- `policy_events`：政策事件
- `distributed`：多机通信配置

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
- `output/economy/`
- `output/environment/timeline.jsonl`
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
