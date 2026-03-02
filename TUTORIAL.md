# GAWorld 用户教程

本教程面向第一次使用 GAWorld 的用户，目标是让你在 10 分钟内完成一次可复现的仿真运行。

## 1. 准备环境

建议使用 Python 3.10+。

在项目根目录执行：

```bash
pip install -r requirements.txt
```

## 2. 配置 LLM（必须）

GAWorld 运行时需要至少一个可用的 LLM Provider。请先编辑 `config.py`，并选择一种方式：

1. 本地 Ollama（离线/本地模型）
2. OpenAI（云端）
3. Anthropic 兼容接口（云端或代理）

如果使用 OpenAI 或 Anthropic，请先设置环境变量：

```bash
export OPENAI_API_KEY="your_key_here"
# 或
export ANTHROPIC_API_KEY="your_key_here"
```

然后在 `config.py` 中让 `routing.default` 指向你已配置完成的 provider（例如 `openai_gpt` 或 `ollama_qwen`）。

## 3. 第一次运行仿真

```bash
python generative_city_sim.py run
```

运行后会在 `output/` 下生成日志、记忆和图表。

重点查看：

- `output/logs/`：运行日志
- `output/memory/`：Agent 记忆与状态
- `output/state/agent_state_history.csv`：状态时间序列
- `output/network/social_network.png`：社交网络图

## 4. 重置并重新开始

如果你改了关键配置（如记忆模型版本）或想从 Day 1 重新开始：

```bash
python generative_city_sim.py reset
```

再执行：

```bash
python generative_city_sim.py run
```

## 5. 访谈单个 Agent

直接提问：

```bash
python generative_city_sim.py interview --agent-id 31 --question "你今天为什么选择这个行动？"
```

批量问题（每行一个问题）：

```bash
python generative_city_sim.py interview --agent-id 31 --questions-file questions.txt
```

## 6. 注入外部信息（可选）

给某个 Agent 添加一条外部知识：

```bash
python generative_city_sim.py rag-add \
  --agent-id 31 \
  --text "周末更倾向于骑行和逛书店" \
  --timestamp "2026-02-18 09:30" \
  --source "manual"
```

从文件导入：

```bash
python generative_city_sim.py rag-import \
  --agent-id 31 \
  --file output/test_extra_info.txt \
  --source "profile_notes"
```

## 7. 事件对照实验（推荐）

在“有事件/无事件”两条分支并行运行并比较：

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

输出会写入 `output/comparisons/<时间戳_事件名>/`。

## 8. 生成新城市地图（可选）

```bash
python generate_citymap.py --description "a small city with about 1000 residents, in east china"
```

默认会更新 `citymap.md`。

## 9. 常见问题

1. 报错 API key 缺失  
请检查环境变量是否设置，且 `config.py` 使用了对应 provider。

2. 运行很慢  
在 `config.py` 中降低 `sim_days`、减少 `agent_ids`，或减少额外 LLM 调用配置。

3. 修改配置后行为异常  
先执行 `python generative_city_sim.py reset`，再重新运行。

## 10. 一条最短上手路径

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your_key_here"
python generative_city_sim.py run
```

如果你只想先验证流程可跑通，按上面 3 条命令执行即可。
