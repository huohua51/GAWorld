# GAWorld 功能特性总览

本表列出 GAWorld 的主要功能特性、作用，以及访问 / 启用方法。命令均在项目根目录执行。
配置项默认入口为 `config.py`（实际分层在 `gaworld/settings/`），可被 `dashboard_config.json` 与 `GAWORLD_CONFIG_OVERRIDES` 覆盖。

## 一、CLI 命令（直接可用）

| 功能特性 | 作用 | 访问方法 |
|---|---|---|
| 运行仿真 | 让一批智能体按天循环"生活"，产出日志、记忆、状态、经济等全部产物 | `python generative_city_sim.py run` |
| 重置 | 清除有状态产物，从 Day 1 重新开始（改记忆 schema 后必做） | `python generative_city_sim.py reset` |
| 智能体采访 | 基于某 agent 当前记忆与状态向其提问 | `python generative_city_sim.py interview --agent-id 31 --question "..."` / `--questions-file q.txt` |
| 从社交内容创建智能体 | 用社媒页面或文本生成新 agent 画像 | `python generative_city_sim.py create-agent-from-social --url "..."` / `--file ... --name "..."` |
| RAG 外部知识注入 | 向某 agent 注入外部信息以改变其认知 | `python generative_city_sim.py rag-add --agent-id 31 --text "..."` / `rag-import --file ...` |
| 事件对照实验 | 在"有事件 / 无事件"两分支并行仿真并出对比报告 | `python generative_city_sim.py compare-event --event-name "..." --sim-days 3 --seed 42` |
| 本地 Dashboard | 配置编辑、运行控制、记忆查看、访谈、日志查看 | `python generative_city_sim.py dashboard --port 8766` → `http://127.0.0.1:8766/dashboard` |
| Agent Studio | 单智能体 7 步可视化构建/查看：身份、九维状态（可编辑雷达）、技能、记忆、Dunbar 社交、行为、复核部署；写回 CSV+profile，可创建新 agent | 控制台工具栏「Agent Studio ↗」→ `http://127.0.0.1:8766/site/dashboard/studio.html` |
| 轨迹回放查看器 | 可视化回放智能体移动轨迹 | `python generative_city_sim.py serve-viz --port 8000` → `/site/simviz/index.html` |
| 分布式 relay | 多机协同仿真，各节点处理本地 agent 子集 | `python generative_city_sim.py serve-distributed --host 0.0.0.0 --port 8877` |
| 城市地图生成 | 用自然语言描述生成城市地图（节点 / 道路 / 地铁） | `python scripts/generate_citymap.py --description "..."` |

## 二、核心仿真特性（配置开关）

| 功能特性 | 作用 | 访问方法 |
|---|---|---|
| 多后端 LLM 路由 | Ollama / OpenAI 兼容 / Anthropic 兼容，可按任务分流模型 | `CONFIG["llm"]["routing"]["default"]` / `["tasks"]`；环境变量 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` 等 |
| 记忆系统 | 短期 / 情景 / 长期总结 / 关系记忆 + 向量召回，跨天保持一致性 | 自动运行；`CONFIG["memory"]`；产物 `output/memory/` |
| 经济仿真 | 个税 7 档累进 + 五险一金、恩格尔消费、四账户投资、宏观周期与冲击 | `CONFIG["economy"]`；产物 `output/economy/` |
| 位置系统与交通 | 类别空间匹配、真实出行成本、高峰 / 天气影响、通勤记忆、区域价格 | 自动运行（依赖 `data/citymap.md`）；`gaworld/world/city_map.py` |
| 动态行为系统 | 承诺度感知中断、情绪即兴行为、社交偶遇链、环境事件级联、需求中断与日程恢复 | `CONFIG["dynamic_behavior"]["enabled"]` |
| 兴趣爱好与技能成长 | 为每个 agent 派生成长画像，影响日程、动作权重与工作选择 | `CONFIG["interests"]["enabled"]`；产物 `output/memory/agent_<id>_growth.json` |
| 社交网络 | 关系衰减、Dunbar 分层、off-screen ghost 事件 | 自动运行；`gaworld/social/network.py`；产物 `output/network/` |
| 生命事件 | 生日、疾病、换工作等调度事件 | 自动运行；`gaworld/events/life.py` |
| 政策 / 环境事件 | 政策冲击与环境扰动注入仿真 | `CONFIG["policy_events"]`；`gaworld/env/system.py`；产物 `output/environment/timeline.jsonl` |
| PolicySim 干预评估 | 本地无网络评估推荐 / 曝光，记录立场 / 毒性 / 误信息 / 跨观点 / 奖励指标 | `CONFIG["intervention"]["enabled"]`；产物 `output/intervention/intervention_metrics.csv` |

## 三、新特性（v2）

| 功能特性 | 作用 | 访问方法 |
|---|---|---|
| 物理环境感知（P0） | 接通节点级占用 / 营业状态，感知前生成"身边物理环境"快照 | `CONFIG["environment"]["local_physical"]["enabled"]` |
| 异常一等公民（P2） | 给事件打 `anomaly` / `anomaly_score`，区分常态波动与突发异常 | `CONFIG["environment"]["anomaly"]["enabled"]` |
| 当日反应式重规划（P3） | 持续性异常时只重排受影响区间（改址 / 顺延 / 丢弃） | `CONFIG["environment"]["replan"]["enabled"]` |
| 结构化空间学习（P4） | 累积地点规避偏好并改址，可跨运行持久化 | `CONFIG["environment"]["spatial_preferences"]["enabled"]`（+ 顶层 `stateful=True`）；产物 `output/memory/agent_<id>_env_preferences.json` |
| 可复用 Skill 库 | 全局 / 私有 Markdown 技能，注入认知与工作 brief 影响行为 | `CONFIG["skills"]`；全局库 `data/skills/*.md`；`SkillRegistry().attach_to_agent(agent, "id")` |
| 经验 → Skill 自动提炼 | agent 从最近经历自总结私有技能 | `CONFIG["memory"]["skill_consolidation"]["enabled"]`（默认 OFF）；产物 `output/memory/agent_<id>_skills/*.md` |
| 真实工作任务系统 | agent 按职业 / 技能产出真实产物（HTML / Python / 文章 / 教案 / 研究笔记）并接单结算 | `CONFIG["real_work"]["enabled"]`；产物 `output/work/agent_<id>/<task_id>/` |

## 四、运维与调试

| 功能特性 | 作用 | 访问方法 |
|---|---|---|
| 日志模式 | 切换终端输出详略（simple ~4 行/tick，verbose 全字段） | `GAWORLD_LOG_MODE=simple\|verbose`（默认 simple） |
| 日志级别 | DEBUG 下显示每次 LLM 调用的 token 与延迟 | `GAWORLD_LOG_LEVEL=DEBUG` |
| 配置覆盖 | 不改源码即可覆盖基础配置 | `dashboard_config.json` / `GAWORLD_CONFIG_OVERRIDES` |
| 可复现性 | 固定随机种子复现实验 | `--seed`（CLI）/ `CONFIG["random_seed"]` |

---

## 相关文档

- [完整教程](TUTORIAL.v2.md)
- [物理环境感知与反应式重规划](physical_env_perception_changelog.md)
- [Skill 系统](SKILL_SYSTEM.md) · [真实工作系统使用](REAL_WORK_USAGE.md)
- [项目结构](PROJECT_STRUCTURE.md) · [中文 README](../README.zh-CN.md) · [English README](../README.md)
