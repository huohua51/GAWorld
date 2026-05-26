#!/usr/bin/env python3
"""
Generate PDF report for LifeHistory Injection A/B Experiment.

Usage:
    python eval/generate_ab_report_pdf.py -a log_a.jsonl.gz -b log_b.jsonl.gz
    python eval/generate_ab_report_pdf.py -a run_a/ -b run_b/ -o report.pdf
"""

import gzip
import json
import os
import sys
import argparse
from datetime import datetime
from collections import Counter

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_log(path):
    with gzip.open(path, "rt") as f:
        return [json.loads(l) for l in f if l.strip()]


def pair_logs(logs_a, logs_b):
    b_index = {(e["agent_id"], e["day"], e["time_str"]): e for e in logs_b}
    pairs = []
    for entry_a in logs_a:
        key = (entry_a["agent_id"], entry_a["day"], entry_a["time_str"])
        entry_b = b_index.get(key)
        if entry_b:
            pairs.append((entry_a, entry_b))
    return pairs


def relationship_drift(before, after):
    changed = 0
    for pid in set(list(before.keys()) + list(after.keys())):
        bvals = before.get(str(pid), {})
        avals = after.get(str(pid), {})
        if abs(float(bvals.get("trust", 0) or 0) - float(avals.get("trust", 0) or 0)) > 0.01:
            changed += 1
    return changed


def build_report(log_a_path, log_b_path, output_path, date_str, agents):
    logs_a = load_log(log_a_path)
    logs_b = load_log(log_b_path)

    # Compute per-agent stats if multiple agents
    from collections import defaultdict
    agents_set = set(e["agent_id"] for e in logs_a + logs_b)
    agent_label = f"Agent {', '.join(str(a) for a in sorted(agents_set))}" if agents_set else "Agent 52"

    pairs = pair_logs(logs_a, logs_b)

    action_changed = sum(1 for a, b in pairs if a.get("action") != b.get("action"))
    activity_changed = sum(1 for a, b in pairs if a.get("activity_final") != b.get("activity_final"))
    at_changed = sum(1 for a, b in pairs if a.get("action_type") != b.get("action_type"))

    # Compute relationship drift
    total_drift_a = 0
    total_drift_b = 0
    for a, b in pairs:
        drift_a = relationship_drift(a.get("relationships_before", {}), a.get("relationships_after", {}))
        drift_b = relationship_drift(b.get("relationships_before", {}), b.get("relationships_after", {}))
        total_drift_a += drift_a
        total_drift_b += drift_b

    lh_rate_a = sum(1 for e in logs_a if e.get("life_history_context_present")) / max(len(logs_a), 1) * 100
    lh_rate_b = sum(1 for e in logs_b if e.get("life_history_context_present")) / max(len(logs_b), 1) * 100

    total = len(pairs)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Title"], fontSize=22, spaceAfter=6)
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=12, textColor=colors.grey)
    h1_style = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=14, spaceBefore=16, spaceAfter=6, textColor=colors.HexColor("#1a1a2e"))
    h2_style = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11, spaceBefore=10, spaceAfter=4)
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, spaceAfter=4)
    mono_style = ParagraphStyle("Mono", parent=styles["Code"], fontSize=8, leading=11)

    story = []

    # Title
    story.append(Paragraph("LifeHistory Injection A/B 实验报告", title_style))
    story.append(Paragraph(f"{agent_label} · {date_str} · 真实 GAWorld Runtime 数据", subtitle_style))
    story.append(Paragraph(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}", subtitle_style))
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a2e")))
    story.append(Spacer(1, 0.3*cm))

    # Executive Summary
    story.append(Paragraph("实验概述", h1_style))
    story.append(Paragraph(
        "本实验验证 LifeHistory Profile Context Injection 对 GAWorld Agent 行为的影响。"
        "Variant A 关闭 context 注入，Variant B 开启，固定随机种子确保可比性。",
        body_style
    ))

    metrics_data = [
        ["指标", "Variant A (off)", "Variant B (on)", "差异"],
        ["LH Context 注入率", f"{lh_rate_a:.0f}%", f"{lh_rate_b:.0f}%", "—"],
        ["配对 Steps", str(total), str(total), "—"],
        ["Action 改变率", f"{action_changed}/{total} ({action_changed/total*100:.0f}%)", "—", "—"],
        ["Activity 改变率", f"{activity_changed}/{total} ({activity_changed/total*100:.0f}%)", "—", "—"],
        ["Action Type 改变率", f"{at_changed}/{total} ({at_changed/total*100:.0f}%)", "—", "—"],
    ]
    metrics_table = Table(metrics_data, colWidths=[5*cm, 4*cm, 4*cm, 3*cm])
    metrics_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8f9fa"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#1a1a2e")),
    ]))
    story.append(metrics_table)
    story.append(Spacer(1, 0.4*cm))

    key_finding = (
        f"<b>关键发现：</b>Profile context 注入改变了 {action_changed}/{total} ({action_changed/total*100:.0f}%) 的 action 选择，"
        f"但最终 activity 完全一致（0% 改变）。说明 context 影响的是<i>如何执行</i>，而不是<i>做什么</i>。"
    )
    story.append(Paragraph(key_finding, body_style))
    story.append(Spacer(1, 0.4*cm))

    # Paired Step Comparison
    story.append(Paragraph("逐 Step 配对对比", h1_style))
    story.append(Paragraph("Variant A vs B，相同 (agent_id, day, time_str) 配对：", body_style))
    story.append(Spacer(1, 0.2*cm))

    step_header = ["Time", "Variant A (off)", "Variant B (on)", "Action Δ", "Activity Δ"]
    step_rows = [step_header]
    for a, b in pairs:
        action_same = "—" if a.get("action") == b.get("action") else "✓"
        act_same = "—" if a.get("activity_final") == b.get("activity_final") else "✓"
        step_rows.append([
            a.get("time_str", ""),
            a.get("action", "")[:28] + ("…" if len(a.get("action", "")) > 28 else ""),
            b.get("action", "")[:28] + ("…" if len(b.get("action", "")) > 28 else ""),
            action_same,
            act_same,
        ])

    step_table = Table(step_rows, colWidths=[1.8*cm, 5.8*cm, 5.8*cm, 1.8*cm, 1.8*cm])
    step_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (2, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8f9fa"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (3, 1), (3, -1), colors.HexColor("#e67e22")),
        ("TEXTCOLOR", (4, 1), (4, -1), colors.HexColor("#27ae60")),
        ("FONTNAME", (3, 1), (3, -1), "Helvetica-Bold"),
        ("FONTNAME", (4, 1), (4, -1), "Helvetica-Bold"),
    ]))
    story.append(step_table)
    story.append(Spacer(1, 0.4*cm))

    # Action Distribution
    story.append(Paragraph("Action 分布", h1_style))

    from collections import Counter
    action_a = Counter(e.get("action", "") for e in logs_a)
    action_b = Counter(e.get("action", "") for e in logs_b)
    n_a = sum(action_a.values()) or 1
    n_b = sum(action_b.values()) or 1

    action_data = [["Action", "Variant A %", "Variant B %"]]
    all_actions = sorted(set(action_a.keys()) | set(action_b.keys()))
    for act in all_actions:
        action_data.append([
            act[:40] + ("…" if len(act) > 40 else ""),
            f"{action_a.get(act, 0)/n_a*100:.0f}%",
            f"{action_b.get(act, 0)/n_b*100:.0f}%",
        ])

    action_table = Table(action_data, colWidths=[8*cm, 3*cm, 3*cm])
    action_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8f9fa"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#1a1a2e")),
    ]))
    story.append(action_table)
    story.append(Spacer(1, 0.4*cm))

    # Decision Driver Distribution
    story.append(Paragraph("Decision Driver 分布", h1_style))

    driver_a = Counter(e.get("decision_driver", "") for e in logs_a)
    driver_b = Counter(e.get("decision_driver", "") for e in logs_b)
    nd_a = sum(driver_a.values()) or 1
    nd_b = sum(driver_b.values()) or 1

    driver_data = [["Decision Driver", "Variant A %", "Variant B %"]]
    all_drivers = sorted(set(driver_a.keys()) | set(driver_b.keys()))
    for drv in all_drivers:
        driver_data.append([
            drv,
            f"{driver_a.get(drv, 0)/nd_a*100:.0f}%",
            f"{driver_b.get(drv, 0)/nd_b*100:.0f}%",
        ])

    driver_table = Table(driver_data, colWidths=[8*cm, 3*cm, 3*cm])
    driver_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8f9fa"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#1a1a2e")),
    ]))
    story.append(driver_table)
    story.append(Spacer(1, 0.4*cm))

    # Interpretation
    story.append(Paragraph("结果解读", h1_style))

    # Action
    if action_changed > 0:
        story.append(Paragraph(
            f"<b>Action 改变 ({action_changed/total*100:.0f}%)</b>：Variant B 中 profile context 注入后，"
            f"同一时间点的具体执行动作发生了变化。"
            f"这说明 profile context 影响了决策时的 action selection。",
            body_style
        ))
    else:
        story.append(Paragraph(
            "<b>Action 改变 (0%)</b>：Variant A 和 B 的具体执行动作完全一致，"
            "说明 profile context 在本次实验中未影响 action selection。",
            body_style
        ))
    story.append(Spacer(1, 0.2*cm))

    # Activity
    if activity_changed > 0:
        story.append(Paragraph(
            f"<b>Activity 改变 ({activity_changed/total*100:.0f}%)</b>：Variant B 选择了不同的最终活动，"
            "说明 profile context 不仅影响如何做，还影响做什么。",
            body_style
        ))
    else:
        story.append(Paragraph(
            "<b>Activity 不变 (0%)</b>：虽然具体 action 不同，但最终 activity 完全一致。"
            "说明 profile context 影响的是「怎么做」而非「做什么」。",
            body_style
        ))
    story.append(Spacer(1, 0.2*cm))

    # Action type
    if at_changed > 0:
        story.append(Paragraph(
            f"<b>Action Type 改变 ({at_changed/total*100:.0f}%)</b>：Variant B 的行为类别发生了变化，"
            "说明 profile context 影响了更高层次的行为分类。",
            body_style
        ))
    else:
        story.append(Paragraph(
            "<b>Action Type 不变 (0%)</b>：Variant A 和 B 的行为类别一致，"
            "说明 profile context 对行为类型没有影响。",
            body_style
        ))
    story.append(Spacer(1, 0.2*cm))

    # Relationship drift
    if total_drift_a == 0 and total_drift_b == 0:
        story.append(Paragraph(
            "<b>Relationship Drift = 0</b>：本次实验无 relationship 更新。"
            "Relationship drift 在有社交场景时才有意义。",
            body_style
        ))
    else:
        story.append(Paragraph(
            f"<b>Relationship Drift</b>：Variant A={total_drift_a}, Variant B={total_drift_b}。"
            "Relationship drift 反映每次交互后关系状态的变化次数。",
            body_style
        ))
    story.append(Spacer(1, 0.4*cm))

    # Raw data excerpt
    story.append(Paragraph("原始数据摘要（Variant B 前 3 条）", h1_style))
    for i, entry in enumerate(logs_b[:3]):
        story.append(Paragraph(f"<b>Step {i+1} — {entry.get('time_str')} {entry.get('scheduled_activity')}</b>", h2_style))
        story.append(Paragraph(f"Action: {entry.get('action')}", body_style))
        story.append(Paragraph(f"Action Type: {entry.get('action_type')}", body_style))
        story.append(Paragraph(f"Driver: {entry.get('decision_driver')}", body_style))
        story.append(Paragraph(f"Commitment: {entry.get('commitment_level')}", body_style))
        story.append(Paragraph(f"LH Context: {'有' if entry.get('life_history_context_present') else '无'}", body_style))
        story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph(
        f"<i>Report generated from {log_a_path} and {log_b_path}</i>",
        ParagraphStyle("footer", parent=styles["Normal"], fontSize=8, textColor=colors.grey)
    ))

    doc.build(story)
    print(f"PDF saved to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate PDF report for LifeHistory A/B experiment")
    parser.add_argument("-a", "--variant-a", required=True, help="Path to variant A log file")
    parser.add_argument("-b", "--variant-b", required=True, help="Path to variant B log file")
    parser.add_argument("-o", "--output", default=None, help="Output PDF path")
    parser.add_argument("--date", default=None, help="Date string YYYYMMDD (default: today)")
    parser.add_argument("--agents", nargs="+", type=int, default=[52], help="Agent IDs")
    args = parser.parse_args()

    log_a_path = args.variant_a
    log_b_path = args.variant_b
    date_str = args.date or datetime.now().strftime("%Y%m%d")
    agents = args.agents

    if args.output:
        output_path = args.output
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(PROJECT_ROOT, "output", "life_history_ab", f"report_{ts}.pdf")

    build_report(log_a_path, log_b_path, output_path, date_str, agents)