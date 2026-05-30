from __future__ import annotations

import json
import os
from glob import glob


def metric_delta(rows, metric):
    for row in rows or []:
        if str(row.get("metric", "")) == str(metric):
            try:
                return float(row.get("delta_final", 0.0))
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _read_json(path, default):
    if not path or not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return default
    return data


def _read_text(path):
    if not path or not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _latest_diary_text(root_dir):
    pattern = os.path.join(root_dir, "diaries", f"agent_*", "day_*.md")
    matches = sorted(glob(pattern))
    return _read_text(matches[-1]) if matches else ""


def _schedule_shift_summary(baseline_dir, scenario_dir):
    base_files = sorted(glob(os.path.join(baseline_dir, "memory", "agent_*_schedule.json")))
    scenario_files = sorted(glob(os.path.join(scenario_dir, "memory", "agent_*_schedule.json")))
    if not base_files or not scenario_files:
        return "未找到可比较的日程缓存。"
    base = _read_json(base_files[0], [])
    scn = _read_json(scenario_files[0], [])
    changes = []
    for idx in range(min(len(base), len(scn))):
        b = base[idx] if isinstance(base[idx], dict) else {}
        s = scn[idx] if isinstance(scn[idx], dict) else {}
        if b.get("time") != s.get("time") or b.get("activity") != s.get("activity"):
            changes.append(
                f"{b.get('time', '?')} {b.get('activity', '')} -> {s.get('time', '?')} {s.get('activity', '')}"
            )
        if len(changes) >= 3:
            break
    return "；".join(changes) if changes else "两条轨迹的缓存日程没有出现显著偏移。"


def _memory_diff_summary(baseline_dir, scenario_dir):
    base_files = sorted(glob(os.path.join(baseline_dir, "memory", "agent_*.json")))
    scenario_files = sorted(glob(os.path.join(scenario_dir, "memory", "agent_*.json")))
    if not base_files or not scenario_files:
        return "未找到可比较的长期记忆文件。"
    base = _read_json(base_files[0], [])
    scn = _read_json(scenario_files[0], [])
    base_tail = [str(item) for item in base[-3:]]
    scn_tail = [str(item) for item in scn[-3:]]
    extra = [item for item in scn_tail if item not in base_tail]
    if extra:
        return "情景分支新增记忆：" + "；".join(extra[:2])
    return "两条轨迹的近期长期记忆差异不大。"


def _social_diff_summary(baseline_dir, scenario_dir):
    base_logs = sorted(glob(os.path.join(baseline_dir, "logs", "agent_*.log")))
    scn_logs = sorted(glob(os.path.join(scenario_dir, "logs", "agent_*.log")))
    if not base_logs or not scn_logs:
        return "未找到可比较的 agent 日志。"
    base_text = _read_text(base_logs[0])
    scn_text = _read_text(scn_logs[0])
    markers = ("DistributedOutbox", "DistributedInbox", "回复", "联系", "消息")
    base_count = sum(base_text.count(marker) for marker in markers)
    scn_count = sum(scn_text.count(marker) for marker in markers)
    delta = scn_count - base_count
    if delta > 0:
        return f"情景分支中的社交/消息相关行为更多（约 +{delta} 个线索命中）。"
    if delta < 0:
        return f"情景分支中的社交/消息相关行为更少（约 {delta} 个线索命中）。"
    return "两条轨迹的社交互动强度接近。"


def write_personal_what_if_report(output_root, question, agent_id, event_payload, rows, *, baseline_dir="", scenario_dir=""):
    os.makedirs(output_root, exist_ok=True)
    report_path = os.path.join(output_root, "personal_twin_recommendation.md")
    top = list(rows or [])[:5]
    stress_delta = metric_delta(rows, "stress")
    emotion_delta = metric_delta(rows, "emotion")
    econ_delta = metric_delta(rows, "econ_security")
    mobility_delta = metric_delta(rows, "mobility_intent")
    schedule_summary = _schedule_shift_summary(baseline_dir, scenario_dir) if baseline_dir and scenario_dir else "未提供日程差异输入。"
    memory_summary = _memory_diff_summary(baseline_dir, scenario_dir) if baseline_dir and scenario_dir else "未提供记忆差异输入。"
    social_summary = _social_diff_summary(baseline_dir, scenario_dir) if baseline_dir and scenario_dir else "未提供社交差异输入。"
    diary_diff = ""
    if baseline_dir and scenario_dir:
        base_diary = _latest_diary_text(baseline_dir)
        scenario_diary = _latest_diary_text(scenario_dir)
        if base_diary or scenario_diary:
            diary_diff = (
                "情景分支日记更强调："
                + (scenario_diary[:120].replace("\n", " ") if scenario_diary else "无明显差异")
            )
    lines = [
        "# 个人孪生 What-if 报告",
        "",
        f"- Agent ID: {int(agent_id)}",
        f"- 假设问题: {str(question).strip()}",
        f"- 情景标题: {event_payload.get('name', '')}",
        f"- 触发时间: Day {event_payload.get('day', '')} {event_payload.get('time', '')}",
        "",
        "## 结论摘要",
        "",
    ]
    summary_bits = []
    if stress_delta > 0.02:
        summary_bits.append("压力明显上升")
    elif stress_delta < -0.02:
        summary_bits.append("压力有所缓解")
    if emotion_delta > 0.02:
        summary_bits.append("整体情绪更积极")
    elif emotion_delta < -0.02:
        summary_bits.append("整体情绪更保守")
    if econ_delta > 0.02:
        summary_bits.append("经济安全感略有改善")
    elif econ_delta < -0.02:
        summary_bits.append("经济安全感承压")
    if mobility_delta > 0.02:
        summary_bits.append("流动意愿更强")
    elif mobility_delta < -0.02:
        summary_bits.append("流动意愿更保守")
    if not summary_bits:
        summary_bits.append("整体变化有限")
    lines.append("；".join(summary_bits) + "。")
    lines.append("")
    lines.append("## 关键指标")
    lines.append("")
    if top:
        for item in top:
            lines.append(
                f"- `{item['metric']}`: baseline={item['baseline_final']:.4f}, "
                f"scenario={item['event_final']:.4f}, delta={item['delta_final']:.4f}"
            )
    else:
        lines.append("- 没有生成可比较的状态指标。")
    lines.append("")
    lines.append("## 行为与记忆差异")
    lines.append("")
    lines.append(f"- 日程偏移：{schedule_summary}")
    lines.append(f"- 长期记忆差异：{memory_summary}")
    lines.append(f"- 社交互动变化：{social_summary}")
    if diary_diff:
        lines.append(f"- 日记侧重点差异：{diary_diff}")
    lines.append("")
    lines.append("## 建议")
    lines.append("")
    if stress_delta > 0.04 and econ_delta < 0:
        lines.append("- 这个假设更像高压试探，适合先做一次小范围、低成本验证。")
    elif emotion_delta > 0 and stress_delta <= 0.03:
        lines.append("- 这个情景有一定正反馈，适合先做一个短周期试运行。")
    else:
        lines.append("- 先盯住变化最大的两三个指标，再决定要不要把这条情景转成真实行动。")
    lines.append("")
    lines.append("## 输出目录")
    lines.append("")
    lines.append("- `baseline/`：基线场景")
    lines.append("- `scenario/`：假设情景")
    lines.append("- `comparison_summary.md`：常规对照报告")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return report_path
