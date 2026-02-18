# 事件影响对比报告

- 事件名称：临时交通限行
- 事件时间：Day 2 09:00
- 事件描述：主干道限行导致通勤时间上升并影响出行决策

## 关键差异（按终值绝对差排序）

- `mobility_intent`: baseline=0.0000, event=0.3368, Δ=0.3368，流动意愿上升（Δ=0.3368）
- `platform_dependence`: baseline=0.1126, event=0.3186, Δ=0.2060，platform_dependence上升（Δ=0.2060）
- `city_identity`: baseline=0.0000, event=0.0207, Δ=0.0207，城市认同上升（Δ=0.0207）
- `hunger`: baseline=0.9914, event=1.0000, Δ=0.0086，hunger上升（Δ=0.0086）
- `energy`: baseline=0.9945, event=1.0000, Δ=0.0055，energy上升（Δ=0.0055）

## 估计结论

事件对系统的主要影响表现为：流动意愿上升（Δ=0.3368）；platform_dependence上升（Δ=0.2060）；城市认同上升（Δ=0.0207）。

- 指标明细：`output/comparisons/20260215_230937_临时交通限行/comparison_metrics.csv`
