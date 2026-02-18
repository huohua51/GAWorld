# 事件影响对比报告

- 事件名称：全程戒严
- 事件时间：Day 1 09:00
- 事件描述：因为学生闹事 政府宣布全城戒严

## 关键差异（按终值绝对差排序）

- `mobility_intent`: baseline=0.3876, event=0.0670, Δ=-0.3206，流动意愿下降（Δ=0.3206）
- `energy`: baseline=0.8375, event=0.9575, Δ=0.1200，energy上升（Δ=0.1200）
- `platform_dependence`: baseline=0.2367, event=0.2558, Δ=0.0191，platform_dependence上升（Δ=0.0191）
- `policy_sensitivity`: baseline=0.0162, event=0.0114, Δ=-0.0049，policy_sensitivity下降（Δ=0.0049）
- `city_identity`: baseline=0.0000, event=0.0000, Δ=0.0000，几乎无变化

## 估计结论

事件对系统的主要影响表现为：流动意愿下降（Δ=0.3206）；energy上升（Δ=0.1200）；platform_dependence上升（Δ=0.0191）。

- 指标明细：`output/comparisons/20260218_010956_全程戒严/comparison_metrics.csv`
