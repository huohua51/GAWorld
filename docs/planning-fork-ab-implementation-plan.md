# Planning Fork A/B 实验实现计划

## 目标
在 Planning Layer 实现 fork：每次 LLM planning 调用同时生成 Variant A（无 LH）和 Variant B（LH+约束式注入），对比 action/reasoning/trace 差异。

## 文件结构

```
gaworld/work/
├── ab_fork_engine.py     # A/B fork 核心引擎（新增）
├── metrics.py             # 统计指标计算（新增）
└── router.py              # 已有 WorkRouter，扩展支持 fork
```

```
generative_city_sim.py     # 修改 planning() 函数支持 fork 模式
llm_providers.py           # 扩展 call_llm 支持 A/B 变体
```

## 实现任务

### Task 1: ab_fork_engine.py — A/B Fork 核心引擎

**文件**: `gaworld/work/ab_fork_engine.py`

核心功能：
```python
class ABForkEngine:
    def plan_with_fork(agent, perception_text, recall_context, decision_refs, config)
    # - 构建 Variant A prompt（无 LH Context）
    # - 构建 Variant B prompt（LH Context + 约束式注入）
    # - 并行调用 call_llm 两次（Variant A 和 B）
    # - 调用 metrics 模块比较结果
    # - 返回 (result_a, result_b, metrics_diff)
```

LH Context 约束式注入（Variant B）：
1. **System prompt**: 强制人格设定（"你是一个固执/冲动/…的人"）
2. **Few-shot examples**: 3-5个"人格→决策"示例
3. **Output format**: JSON schema 约束 `{"goal": str, "constraint": str, "urge": str, "plan": str, "expected_outcome": str}`
4. **Chain-of-personality**: reasoning chain 嵌入人格分析步骤

### Task 2: metrics.py — 统计指标计算

**文件**: `gaworld/work/metrics.py`

指标计算：
| 维度 | 指标 | 实现 |
|------|------|------|
| Action | Fleiss-Cohen κ | 编码 action 一致性 |
| Reasoning | n-gram Jaccard | 编码 reasoning 关键词重叠 |
| Trace | 编辑距离 | Levenshtein distance + p-value |
| 聚合 | McNemar test | 2×2 table significance |

统计显著性阈值：`p < 0.05`

### Task 3: generative_city_sim.py — 集成 Fork

**修改**: `planning()` 函数（约 line 5069）

```python
def planning(agent, perception_text, recall_context=None, decision_refs=None):
    # 原逻辑保留，添加 fork 模式支持
    if CONFIG.get("ab_experiment", {}).get("enabled"):
        return ab_fork_engine.plan_with_fork(...)
    # 原逻辑继续
```

### Task 4: llm_providers.py — A/B 调用支持

**修改**: `call_llm` 支持 variant 参数

```python
def call_llm(prompt, task="", agent_id=None, variant=None):
    # variant: "A" (无LH) | "B" (LH+约束) | None (默认)
```

### Task 5: 配置文件扩展

**修改**: `config.py`

```python
AB_EXPERIMENT_CONFIG = {
    "enabled": False,
    "sample_rate": 1.0,  # 0.0-1.0, fork 比例
    "metrics_threshold": 0.05,  # p-value 阈值
    "variant_b": {
        "use_fewshot": True,
        "use_json_schema": True,
        "use_chain_of_personality": True,
        "personality_examples": 3,  # few-shot 示例数量
    }
}
```

### Task 6: 测试

**文件**: `tests/test_ab_fork_engine.py`（新增）

覆盖：
- `test_fork_engine_returns_both_variants` — 确认返回 A/B 双结果
- `test_metrics_calculation` — 统计指标计算正确性
- `test_variant_b_has_personality_constraints` — Variant B 包含人格约束
- `test_edit_distance_significance` — p-value 计算

---

## 命令

```bash
# 运行模拟（启用 A/B 实验）
python generative_city_sim.py run --ab-experiment

# 运行测试
python -m pytest tests/test_ab_fork_engine.py -v

# Lint
ruff check gaworld/work/ab_fork_engine.py gaworld/work/metrics.py
```

## 预期输出

A/B 实验结果输出到 `output/planning_fork/`:
- `YYYY-MM-DD-run-{n}/variants/{agent_id}/{step}.json` — A/B 双版本原始输出
- `YYYY-MM-DD-run-{n}/metrics/{agent_id}/{step}.json` — 指标计算结果
- `YYYY-MM-DD-run-{n}/significance_summary.json` — 聚合显著性摘要