#!/usr/bin/env python3
"""
Relationship Drift Analysis — Multi-agent A/B Experiment

Loads step logs and network snapshots from Variant A (injection off) and
Variant B (injection on), then computes:

A. Step logs: action/decision_driver/relationship_delta per step
B. Network evolution: PNG + CSV for relationship curves
C. Conversation records: Markdown of agent reflections/interactions
D. Anomaly detection: Alert log for unusual relationship changes

Usage:
    python eval/relationship_drift_analysis.py \\
        --variant-a output/life_history_ab/a/seed_42 \\
        --variant-b output/life_history_ab/b/seed_42 \\
        --output output/life_history_ab/report/
"""

import argparse
import gzip
import json
import os
import statistics
import glob as _glob
from collections import defaultdict
from datetime import datetime


def load_step_logs(base_dir):
    """Load all step logs from a variant directory."""
    logs = []
    pattern = os.path.join(base_dir, "**", "step_log_*.jsonl.gz")
    for fp in _glob.glob(pattern, recursive=True):
        opener = gzip.open if fp.endswith(".gz") else open
        with opener(fp, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    logs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return logs


def load_network_snapshots(base_dir):
    """Load all daily network snapshots from a variant directory."""
    snap_dir = os.path.join(base_dir, "network_snapshots")
    if not os.path.isdir(snap_dir):
        return []
    snaps = []
    for fp in sorted(_glob.glob(os.path.join(snap_dir, "day_*.json"))):
        with open(fp, "r", encoding="utf-8") as f:
            snaps.append(json.load(f))
    return snaps


def compute_direction_stats(logs):
    direction_counts = {"improving": 0, "deteriorating": 0, "stable": 0}
    for log in logs:
        rd = log.get("relationship_delta", {})
        direction = rd.get("direction", "stable")
        direction_counts[direction] = direction_counts.get(direction, 0) + 1
    total = len(logs) or 1
    return {k: round(v / total * 100, 1) for k, v in direction_counts.items()}


def compute_stability_stats(logs):
    by_agent = defaultdict(list)
    for log in logs:
        rd = log.get("relationship_delta", {})
        stability = rd.get("stability_score", 1.0)
        by_agent[log["agent_id"]].append(stability)

    agent_stability = {}
    for aid, scores in by_agent.items():
        if scores:
            agent_stability[aid] = round(statistics.mean(scores), 4)

    all_scores = [s for scores in by_agent.values() for s in scores]
    variant_stability = round(statistics.mean(all_scores), 4) if all_scores else 1.0
    return agent_stability, variant_stability


def compute_trust_closeness_delta(logs):
    trust_deltas = []
    closeness_deltas = []
    for log in logs:
        rd = log.get("relationship_delta", {})
        trust_deltas.append(rd.get("trust_change", 0.0))
        closeness_deltas.append(rd.get("closeness_change", 0.0))
    n = len(trust_deltas) or 1
    return {
        "trust_change": round(sum(trust_deltas) / n, 4),
        "closeness_change": round(sum(closeness_deltas) / n, 4),
    }


def compute_network_metrics(snapshots):
    if not snapshots:
        return None
    metrics = []
    for snap in snapshots:
        day = snap.get("day", 0)
        nodes = snap.get("nodes", [])
        edges = snap.get("edges", [])
        degree_dist = snap.get("degree_distribution", {})

        if not nodes:
            continue

        degrees = list(degree_dist.values())
        avg_degree = round(sum(degrees) / len(degrees), 3) if degrees else 0

        trusts = [n.get("trust", 0.5) for n in nodes]
        closeness_vals = [n.get("closeness", 0.5) for n in nodes]

        metrics.append({
            "day": day,
            "avg_degree": avg_degree,
            "avg_trust": round(statistics.mean(trusts), 4) if trusts else 0.5,
            "avg_closeness": round(statistics.mean(closeness_vals), 4) if closeness_vals else 0.5,
            "node_count": len(nodes),
            "edge_count": len(edges),
        })
    return metrics


# ---- B: Network Evolution Charts ----
def plot_network_evolution(snapshots_a, snapshots_b, output_dir):
    """Generate PNG + CSV for relationship network evolution."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("  [warn] matplotlib not installed, skipping PNG export")
        return

    if not snapshots_a and not snapshots_b:
        print("  [warn] No snapshots for PNG export")
        return

    os.makedirs(output_dir, exist_ok=True)

    days_a = compute_network_metrics(snapshots_a) or []
    days_b = compute_network_metrics(snapshots_b) or []

    all_days = sorted(set([m["day"] for m in days_a] + [m["day"] for m in days_b]))

    trust_a = [next((m["avg_trust"] for m in days_a if m["day"] == d), None) for d in all_days]
    trust_b = [next((m["avg_trust"] for m in days_b if m["day"] == d), None) for d in all_days]
    close_a = [next((m["avg_closeness"] for m in days_a if m["day"] == d), None) for d in all_days]
    close_b = [next((m["avg_closeness"] for m in days_b if m["day"] == d), None) for d in all_days]
    degree_a = [next((m["avg_degree"] for m in days_a if m["day"] == d), None) for d in all_days]
    degree_b = [next((m["avg_degree"] for m in days_b if m["day"] == d), None) for d in all_days]

    # CSV
    csv_path = os.path.join(output_dir, "network_evolution.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("day,variant,avg_trust,avg_closeness,avg_degree\n")
        for d, ta, tb, ca, cb, da, db in zip(all_days, trust_a, trust_b, close_a, close_b, degree_a, degree_b):
            f.write(f"{d},A,{ta or ''},{ca or ''},{da or ''}\n")
            f.write(f"{d},B,{tb or ''},{cb or ''},{db or ''}\n")
    print(f"  [export] CSV: {csv_path}")

    # PNG
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    fig.suptitle("Network Evolution: Variant A (off) vs Variant B (on)")

    # Trust
    ax = axes[0]
    ax.plot(all_days, trust_a, 'b-o', label='A (off)')
    ax.plot(all_days, trust_b, 'r-o', label='B (on)')
    ax.set_xlabel("Day")
    ax.set_ylabel("Avg Trust")
    ax.set_title("Trust")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Closeness
    ax = axes[1]
    ax.plot(all_days, close_a, 'b-o', label='A (off)')
    ax.plot(all_days, close_b, 'r-o', label='B (on)')
    ax.set_xlabel("Day")
    ax.set_ylabel("Avg Closeness")
    ax.set_title("Closeness")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Degree
    ax = axes[2]
    ax.plot(all_days, degree_a, 'b-o', label='A (off)')
    ax.plot(all_days, degree_b, 'r-o', label='B (on)')
    ax.set_xlabel("Day")
    ax.set_ylabel("Avg Degree")
    ax.set_title("Network Density")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    png_path = os.path.join(output_dir, "network_evolution.png")
    plt.savefig(png_path, dpi=150)
    plt.close()
    print(f"  [export] PNG: {png_path}")


# ---- C: Conversation Records ----
def export_conversations(logs_a, logs_b, output_dir):
    """Export reflection/conversation records as Markdown."""
    os.makedirs(output_dir, exist_ok=True)

    for variant, logs in [("A", logs_a), ("B", logs_b)]:
        md_path = os.path.join(output_dir, f"conversations_{variant}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# Variant {variant} — Conversation Records\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")

            by_agent = defaultdict(list)
            for log in logs:
                by_agent[log.get("agent_id", "?")].append(log)

            for aid in sorted(by_agent.keys()):
                agent_logs = sorted(by_agent[aid], key=lambda x: (x.get("day", 0), x.get("time_str", "")))
                f.write(f"## Agent {aid}\n\n")
                for log in agent_logs:
                    refl = str(log.get("reflection") or "")
                    action = str(log.get("action") or "")
                    plan = str(log.get("plan") or "")
                    rd = log.get("relationship_delta", {})
                    time_str = log.get("time_str", "?")
                    day = log.get("day", 0)

                    if refl or action or plan:
                        f.write(f"### Day {day} @ {time_str}\n")
                        if plan:
                            f.write(f"**Plan:** {plan[:200]}\n\n")
                        if action:
                            f.write(f"**Action:** {action[:200]}\n\n")
                        if refl:
                            f.write(f"**Reflection:** {refl[:500]}\n\n")
                        if rd:
                            f.write(f"**Relationship delta:** trust={rd.get('trust_change', 0):.4f}, "
                                    f"closeness={rd.get('closeness_change', 0):.4f}, "
                                    f"direction={rd.get('direction', 'stable')}\n\n")
                        f.write("---\n\n")
        print(f"  [export] Conversations: {md_path}")


# ---- D: Anomaly Detection ----
def detect_anomalies(logs_a, logs_b, output_dir):
    """Detect unusual relationship changes and save alert log."""
    os.makedirs(output_dir, exist_ok=True)

    alerts = []

    for variant, logs in [("A", logs_a), ("B", logs_b)]:
        for log in logs:
            rd = log.get("relationship_delta", {})
            tc = abs(rd.get("trust_change", 0))
            cc = abs(rd.get("closeness_change", 0))

            # Anomaly: relationship change > 0.2 in single step (unusual)
            if tc > 0.2 or cc > 0.2:
                alerts.append({
                    "variant": variant,
                    "agent_id": log.get("agent_id"),
                    "day": log.get("day"),
                    "time_str": log.get("time_str"),
                    "trust_change": rd.get("trust_change"),
                    "closeness_change": rd.get("closeness_change"),
                    "direction": rd.get("direction"),
                    "severity": "HIGH" if tc > 0.3 or cc > 0.3 else "MEDIUM",
                    "reason": f"Large single-step relationship delta: trust={tc:.3f}, closeness={cc:.3f}",
                })

    alert_path = os.path.join(output_dir, "anomaly_alerts.jsonl")
    with open(alert_path, "w", encoding="utf-8") as f:
        for a in sorted(alerts, key=lambda x: (x["variant"], x["day"], x["time_str"])):
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    print(f"  [export] Alerts: {alert_path} ({len(alerts)} anomalies)")


def compare_variants(variant_a_logs, variant_b_logs, snapshots_a, snapshots_b, output_dir=None):
    """Generate A vs B comparison report."""
    print("\n" + "=" * 70)
    print("Relationship Drift A/B Comparison Report")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    print(f"\n[Data Summary]")
    print(f"  Variant A (injection off): {len(variant_a_logs)} step logs, {len(snapshots_a)} network snapshots")
    print(f"  Variant B (injection on):  {len(variant_b_logs)} step logs, {len(snapshots_b)} network snapshots")

    # Direction analysis
    dir_a = compute_direction_stats(variant_a_logs)
    dir_b = compute_direction_stats(variant_b_logs)
    print(f"\n[1] Direction Analysis (% of steps)")
    print(f"  {'Direction':<15} {'Variant A (off)':<20} {'Variant B (on)':<20} {'Δ (B-A)'}")
    print(f"  {'-'*15} {'-'*20} {'-'*20} {'-'*8}")
    for direction in ["improving", "stable", "deteriorating"]:
        delta = round(dir_b.get(direction, 0) - dir_a.get(direction, 0), 1)
        print(f"  {direction:<15} {dir_a.get(direction, 0):>8.1f}%         {dir_b.get(direction, 0):>8.1f}%         {delta:+.1f}%")

    # Stability
    stab_a_agent, stab_a_variant = compute_stability_stats(variant_a_logs)
    stab_b_agent, stab_b_variant = compute_stability_stats(variant_b_logs)
    print(f"\n[2] Stability Score (1.0 = perfect stability)")
    print(f"  Variant A: {stab_a_variant:.4f}")
    print(f"  Variant B: {stab_b_variant:.4f}")
    print(f"  Δ (B-A): {stab_b_variant - stab_a_variant:+.4f}")
    if stab_a_agent and stab_b_agent:
        common_agents = set(stab_a_agent.keys()) & set(stab_b_agent.keys())
        print(f"\n  Per-agent stability:")
        for aid in sorted(common_agents):
            delta = stab_b_agent[aid] - stab_a_agent[aid]
            print(f"    Agent {aid}: A={stab_a_agent[aid]:.3f}, B={stab_b_agent[aid]:.3f}, Δ={delta:+.3f}")

    # Trust/closeness delta
    tc_a = compute_trust_closeness_delta(variant_a_logs)
    tc_b = compute_trust_closeness_delta(variant_b_logs)
    print(f"\n[3] Average Trust / Closeness Change per Step")
    print(f"  {'Metric':<20} {'Variant A':<15} {'Variant B':<15} {'Δ (B-A)'}")
    print(f"  {'-'*20} {'-'*15} {'-'*15} {'-'*10}")
    for key in ["trust_change", "closeness_change"]:
        delta = tc_b[key] - tc_a[key]
        print(f"  {key:<20} {tc_a[key]:<15.4f} {tc_b[key]:<15.4f} {delta:+.4f}")

    # Network structure
    net_a = compute_network_metrics(snapshots_a)
    net_b = compute_network_metrics(snapshots_b)
    print(f"\n[4] Network Structure")
    if net_a and net_b:
        days = min(len(net_a), len(net_b))
        print(f"  {'Day':<6} {'Variant':<10} {'AvgDegree':<12} {'AvgTrust':<12} {'AvgCloseness':<12} {'Nodes':<8} {'Edges':<8}")
        print(f"  {'-'*6} {'-'*10} {'-'*12} {'-'*12} {'-'*12} {'-'*8} {'-'*8}")
        for i in range(days):
            for label, net in [("A", net_a), ("B", net_b)]:
                m = net[i] if i < len(net) else {}
                print(f"  {m.get('day', i+1):<6} {label:<10} {m.get('avg_degree', 0):<12.3f} "
                      f"{m.get('avg_trust', 0):<12.4f} {m.get('avg_closeness', 0):<12.4f} "
                      f"{m.get('node_count', 0):<8} {m.get('edge_count', 0):<8}")
            print()
    else:
        print(f"  No network snapshots found.")

    # Human baseline
    print(f"\n[5] Human Baseline Comparison")
    print(f"  Human social networks typically exhibit:")
    print(f"    - Stability score: 0.70-0.90")
    print(f"    - Direction: >70% of daily changes are 'stable' or 'gradual'")
    print(f"    - Trust/closeness delta: small per-step changes (|delta| < 0.05)")
    print()
    print(f"  Observed values:")
    print(f"    Variant A — Stability: {stab_a_variant:.3f}, Direction stable%: {dir_a.get('stable', 0):.1f}%")
    print(f"    Variant B — Stability: {stab_b_variant:.3f}, Direction stable%: {dir_b.get('stable', 0):.1f}%")

    if stab_b_variant >= 0.70 and dir_b.get("stable", 0) >= 70:
        print(f"  ✅ Variant B is WITHIN human baseline range")
    elif stab_a_variant >= 0.70 and dir_a.get("stable", 0) >= 70:
        print(f"  ⚠️  Neither variant matches baseline well; Variant A is closer")
    else:
        print(f"  ⚠️  Both variants differ from human baseline")

    # B: Network evolution charts
    if output_dir:
        print(f"\n[B] Network Evolution PNG + CSV:")
        plot_network_evolution(snapshots_a, snapshots_b, output_dir)

        # C: Conversations
        print(f"\n[C] Conversation Records:")
        export_conversations(variant_a_logs, variant_b_logs, output_dir)

        # D: Anomaly detection
        print(f"\n[D] Anomaly Detection:")
        detect_anomalies(variant_a_logs, variant_b_logs, output_dir)

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Relationship Drift A/B Analysis")
    parser.add_argument("--variant-a", required=True, help="Path to Variant A run directory")
    parser.add_argument("--variant-b", required=True, help="Path to Variant B run directory")
    parser.add_argument("--output", help="Output directory for PNG/CSV/MD/JSONL (default: print to stdout)")
    args = parser.parse_args()

    logs_a = load_step_logs(args.variant_a)
    logs_b = load_step_logs(args.variant_b)
    snaps_a = load_network_snapshots(args.variant_a)
    snaps_b = load_network_snapshots(args.variant_b)

    if not logs_a or not logs_b:
        print("ERROR: No step logs found for one or both variants")
        return

    import io, sys
    if args.output:
        os.makedirs(args.output, exist_ok=True)
        report_path = os.path.join(args.output, "report.txt")

        buffer = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buffer
        try:
            compare_variants(logs_a, logs_b, snaps_a, snaps_b, output_dir=args.output)
        finally:
            sys.stdout = old_stdout

        report = buffer.getvalue()
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Report saved to: {report_path}")
    else:
        compare_variants(logs_a, logs_b, snaps_a, snaps_b, output_dir=None)


if __name__ == "__main__":
    main()
