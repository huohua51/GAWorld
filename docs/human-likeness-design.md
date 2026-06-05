# Human-Likeness Enhancement Plan

## Understanding Summary

**What:** 全维度 Human-Likeness 系统（行为/情感/社交/认知），支持 GAWorld 所有内置智能体每日持续运行。

**Why:** 验证 LH Context + 新机制对智能体行为真实性的影响，为后续人类对照实验奠基。

**Who:** 研究人员/平台运营者通过 dashboard 观测每日关系演化。

**Key constraints:**
- 30 min in-world time / 每日 run
- Stateful — 关系跨天携带
- 所有平台内置智能体参与
- 当前 A/B 框架兼容

**Non-goals:**
- 不做具身物理仿真
- 不接入真实人类行为数据（后续再做）

## Assumptions

| 项目 | 值 | 来源/理由 |
|------|---|----------|
| 关系衰减 | 5%/天无互动 | Stardew Valley参考，温和防止固化 |
| 时间步 | 30 min/步 | 平衡精度与LLM成本 |
| 社交触发率 | 20-30% | 真实社交基线 |
| 突变阈值 | closeness > 0.7 | 进入"密友模式"，变化加速 |
| 衰减因子 | 1%/天 | 线性衰减 |

## Decision Log

| # | 决定 | 替代方案 | 理由 |
|---|------|---------|------|
| 1 | 关系非线性阶段演化 | 线性增减（已有）→ 阶段模型 | 人类关系是突变的，非线性 |
| 2 | 情感状态机 | 基于关键词推断 → 状态机+事件触发 | 更系统化，可预测 |
| 3 | 30 min/步 | 15min(太贵) / 1hour(太粗) | 平衡 |
| 4 | 5%/天衰减 | 无衰减(GAs) / 10%/天(太激进) | 温和合理 |
| 5 | A+B+C+D 全量日志 | 只做指标 | 用户明确需求 |
| 6 | 指标+观察验证 | 纯指标 / 纯观察 | 用户选择混合 |

## Architecture

```
Daily Run (30 min in-world time)
├── Step Loop (30 min/step)
│   ├── Perception → Planning → Action → Reflection
│   ├── Co-location Encounter (same location → social trigger)
│   ├── Social Trigger (20-30% probability)
│   ├── Relationship Update + Emotion State Machine
│   └── Phase Transition Check (closeness > 0.7 threshold)
├── Memory System
│   ├── Episodic (with salience decay)
│   ├── Semantic (vector DB search)
│   └── Procedural (habits, context-key → action)
├── Decay Engine (daily, no interaction)
│   └── closeness -= 5%, trust -= 5%
└── Export Pipeline (A+B+C+D)
    ├── Step logs (JSONL.gz)
    ├── Network evolution (PNG + CSV)
    ├── Conversation records (Markdown)
    └── Anomaly detection (Alert log)
```

## Open Questions

| 问题 | 状态 |
|------|------|
| 衰减速率（5%/天） | ✅ 已设定 |
| 时间步（30 min） | ✅ 已设定 |
| 社交触发率（20-30%） | ✅ 已设定 |
| 突变阈值（0.7） | ✅ 已设定 |

## Implementation Phases

### Phase 1: Relationship Phase Model
- 修改 `relationship_update()` 加入阶段检测
- 阈值 0.7 触发阶段跃迁
- 验证：relationship_delta 显示"improving"比例提升

### Phase 2: Emotion State Machine
- 基于事件的情感状态转换
- 状态：愉悦/平静/焦虑/愤怒/悲伤
- 触发：interaction_signal + life_events

### Phase 3: Decay Engine
- 每日结束时调用
- 无 interaction 时 relationship 衰减 5%
- 更新 `save_agent_relationships()`

### Phase 4: Export Pipeline
- 步级日志：A step_log 已有
- 日/周曲线：CSV → matplotlib PNG
- 对话记录：reflection_text 聚合
- 异常检测：关系突变阈值报警