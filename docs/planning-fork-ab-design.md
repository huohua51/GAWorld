# Planning Fork A/B Experiment Design

## Understanding Summary

**What:** Planning Layer Fork 实验：每次 LLM planning 调用同时生成 Variant A（无LH）和 Variant B（有LH+约束式注入），对比 action/reasoning/trace 差异。

**Why:** 当前 LH Context 文本注入 LLM 可完全忽略，A/B 无差异。需强制人格约束 + 统计显著性验证。

**Who:** GAWorld 研究人员/平台运营者

**Constraints:**
- 预算宽裕，token 成本不考虑
- 与现有 GAWorld 架构兼容
- 不改 LLM API 本身
- 统计显著性 p<0.05

**Non-goals:** 不改 LLM 模型，不做真实人类行为数据采集

## Decision Log

| # | 决定 | 替代方案 | 理由 |
|---|------|---------|------|
| D1 | Planning 层 fork | Action层fork | 更细粒度，捕获完整 reasoning chain |
| D2 | 全量对比 Action+Reasoning+Trace | 仅 Action 对比 | 用户选择①+②+③ |
| D3 | 每次 planning 都 fork | 间隔 N timestep fork | 宽裕预算，完整捕获 |
| D4 | 统计显著性 p<0.05 | Δ>10% | 用户选择统计显著性 |
| D5 | Multi-shot + JSON schema 约束 | 纯文本 prompt | 更强制人格输出结构化 |

## Architecture

```
Planning Layer Fork
├── Variant A (无 LH Context)
│   └── LLM Planning → plan_a / reasoning_a / trace_a
├── Variant B (LH Context + 约束式注入)
│   └── LLM Planning → plan_b / reasoning_b / trace_b
└── diff_engine.compare() → metrics
    ├── Action: Fleiss-Cohen κ
    ├── Reasoning: n-gram Jaccard
    └── Trace: 编辑距离 / p-value
```

## LH Context 注入方式（约束式）

Variant B prompt 结构：
1. **System prompt**: 强制人格设定（role enforcement）
2. **Few-shot examples**: 3-5个"人格→决策"示例
3. **Output format**: JSON schema 强制 plan 结构
4. **Chain-of-personality**: reasoning chain 中嵌入人格分析步骤

## Metrics

| 维度 | 指标 | 测量方式 | 阈值 |
|------|------|---------|------|
| Action | κ一致性 | Fleiss-Cohen κ | p<0.05 |
| Reasoning | 关键词重叠 | n-gram Jaccard | p<0.05 |
| Trace | 决策路径差异 | 编辑距离 | p<0.05 |
| 聚合 | 综合显著性 | McNemar test | p<0.05 |

## Assumptions

- 每次 planning 调用 LLM 时 fork，两个 variant 共享相同的观测/状态输入
- A/B 对比的是"相同 agent × 相同 timestep × 有/无 LH" 的差异
- 当前 LH Context 文本注入 LLM 可忽略，需强制结构化约束
- fork 需要状态快照（确保 A/B 输入完全一致）

## Open Questions（已确认）

| 问题 | 答案 |
|------|------|
| 注入粒度 | 每次 planning 调用 |
| 对比维度 | Action + Reasoning + Trace 全量 |
| 预算 | 宽裕（不计 token） |
| 成功标准 | p<0.05 |
| 注入方式 | Multi-shot + JSON schema + Chain-of-personality |