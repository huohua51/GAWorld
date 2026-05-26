"""
LifeHistory Paired A/B Runtime Report

Compares two simulation runs (variant A: injection off, variant B: injection on)
by pairing step logs on (agent_id, day, time_str).

Usage:
    python eval/life_history_ab_report.py --variant-a run_A/20260525.jsonl.gz --variant-b run_B/20260525.jsonl.gz
    python eval/life_history_ab_report.py -a run_A/ -b run_B/   # auto-latest per date
"""

import argparse
import gzip
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def load_log(path):
    """Load a single gzipped or plain jsonl file."""
    logs = []
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            logs.append(json.loads(line))
    return logs


def load_logs_from_dir_or_file(path_str):
    """Load logs from a directory (pick latest by date) or exact file path."""
    p = Path(path_str)
    if p.is_file():
        return load_log(p)
    # Directory: find latest date folder
    dates = sorted([d.name for d in p.iterdir() if d.is_dir() and d.name.isdigit()], reverse=True)
    if not dates:
        return []
    latest_dir = p / dates[0]
    log_file = latest_dir / f"step_log_{dates[0]}.jsonl.gz"
    if log_file.exists():
        return load_log(log_file)
    return []


def pair_logs(logs_a, logs_b):
    """Pair logs from variant A and B by (agent_id, day, time_str).
    Only returns pairs where both A and B have a log entry."""
    b_index = {}
    for entry in logs_b:
        key = (entry["agent_id"], entry["day"], entry["time_str"])
        b_index[key] = entry

    pairs = []
    missing_b = 0
    for entry_a in logs_a:
        key = (entry_a["agent_id"], entry_a["day"], entry_a["time_str"])
        entry_b = b_index.get(key)
        if entry_b is None:
            missing_b += 1
            continue
        pairs.append((entry_a, entry_b))
    return pairs, missing_b


def compute_paired_diff(pairs):
    """Compute paired metrics between variant A and B."""
    total = len(pairs)
    action_changed = 0
    activity_changed = 0
    action_type_changed = 0
    lh_context_rates = {"A": 0, "B": 0}
    action_dist = {"A": defaultdict(int), "B": defaultdict(int)}
    driver_dist = {"A": defaultdict(int), "B": defaultdict(int)}
    rel_drift = []
    decision_drivers = {"A": defaultdict(int), "B": defaultdict(int)}

    for entry_a, entry_b in pairs:
        lh_context_rates["A"] += 1 if entry_a.get("life_history_context_present") else 0
        lh_context_rates["B"] += 1 if entry_b and entry_b.get("life_history_context_present") else 0

        act_a = entry_a.get("action")
        act_b = entry_b.get("action") if entry_b else None
        if act_a != act_b:
            action_changed += 1

        sched_a = entry_a.get("scheduled_activity")
        fin_a = entry_a.get("activity_final")
        fin_b = entry_b.get("activity_final") if entry_b else None
        if fin_a != fin_b:
            activity_changed += 1

        at_a = entry_a.get("action_type")
        at_b = entry_b.get("action_type") if entry_b else None
        if at_a != at_b:
            action_type_changed += 1

        if act_a:
            action_dist["A"][act_a] += 1
        if act_b:
            action_dist["B"][act_b] += 1

        d_a = entry_a.get("decision_driver")
        d_b = entry_b.get("decision_driver") if entry_b else None
        if d_a:
            decision_drivers["A"][d_a] += 1
        if d_b:
            decision_drivers["B"][d_b] += 1

        before = entry_a.get("relationships_before", {})
        after_a = entry_a.get("relationships_after", {})
        before_b = entry_b.get("relationships_before") if entry_b else {}
        after_b = entry_b.get("relationships_after") if entry_b else {}
        if before and after_a:
            drift_a = _relationship_drift(before, after_a)
        else:
            drift_a = 0
        if before_b and after_b:
            drift_b = _relationship_drift(before_b, after_b)
        else:
            drift_b = 0
        if drift_a or drift_b:
            rel_drift.append({"agent_id": entry_a["agent_id"], "drift_a": drift_a, "drift_b": drift_b})

    n_a = sum(action_dist["A"].values()) or 1
    n_b = sum(action_dist["B"].values()) or 1
    action_dist_norm = {
        "A": {k: round(v / n_a * 100, 1) for k, v in sorted(action_dist["A"].items(), key=lambda x: -x[1])},
        "B": {k: round(v / n_b * 100, 1) for k, v in sorted(action_dist["B"].items(), key=lambda x: -x[1])},
    }
    n_driver_a = sum(decision_drivers["A"].values()) or 1
    n_driver_b = sum(decision_drivers["B"].values()) or 1
    driver_dist_norm = {
        "A": {k: round(v / n_driver_a * 100, 1) for k, v in sorted(decision_drivers["A"].items(), key=lambda x: -x[1])},
        "B": {k: round(v / n_driver_b * 100, 1) for k, v in sorted(decision_drivers["B"].items(), key=lambda x: -x[1])},
    }

    return {
        "total_paired": total,
        "action_changed": action_changed,
        "action_changed_pct": round(action_changed / total * 100, 1) if total else 0,
        "activity_changed": activity_changed,
        "activity_changed_pct": round(activity_changed / total * 100, 1) if total else 0,
        "action_type_changed": action_type_changed,
        "action_type_changed_pct": round(action_type_changed / total * 100, 1) if total else 0,
        "lh_context_rate": {
            "A": round(lh_context_rates["A"] / total * 100, 1) if total else 0,
            "B": round(lh_context_rates["B"] / total * 100, 1) if total else 0,
        },
        "action_distribution": action_dist_norm,
        "decision_driver_distribution": driver_dist_norm,
        "relationship_drift": rel_drift,
    }


def _relationship_drift(before, after):
    """Compute number of relationships that changed between before and after."""
    changed = 0
    for pid in set(list(before.keys()) + list(after.keys())):
        bvals = before.get(str(pid), {})
        avals = after.get(str(pid), {})
        btrust = float(bvals.get("trust", 0) or 0)
        atrustr = float(avals.get("trust", 0) or 0)
        bclose = float(bvals.get("closeness", 0) or 0)
        aclose = float(avals.get("closeness", 0) or 0)
        if abs(btrust - atrustr) > 0.01 or abs(bclose - aclose) > 0.01:
            changed += 1
    return changed


def per_agent_paired_summary(pairs):
    """Per-agent breakdown of paired comparison."""
    by_agent = defaultdict(list)
    for entry_a, entry_b in pairs:
        by_agent[entry_a["agent_id"]].append((entry_a, entry_b))

    summaries = {}
    for agent_id, agent_pairs in sorted(by_agent.items()):
        agent_name = agent_pairs[0][0].get("agent_name", str(agent_id))
        metrics = compute_paired_diff(agent_pairs)
        summaries[agent_id] = {"agent_name": agent_name, "total_steps": len(agent_pairs), **metrics}
    return summaries


def generate_report(pairs, diff, summaries, date_str, missing_b=0):
    """Print the full paired A/B comparison report."""
    print(f"\n{'='*70}")
    print(f"LifeHistory Paired A/B Report — {date_str}")
    print(f"{'='*70}")
    print(f"Total paired steps: {diff['total_paired']}")
    if missing_b:
        print(f"NOTE: {missing_b} steps in variant A had no counterpart in variant B (skipped)")

    print(f"\n[LH Context Injection Rate]")
    print(f"  Variant A (off): {diff['lh_context_rate']['A']}%")
    print(f"  Variant B (on):  {diff['lh_context_rate']['B']}%")

    print(f"\n[Paired Differences — B vs A]")
    print(f"  Action changed:       {diff['action_changed']}/{diff['total_paired']} ({diff['action_changed_pct']}%)")
    print(f"  Activity changed:    {diff['activity_changed']}/{diff['total_paired']} ({diff['activity_changed_pct']}%)")
    print(f"  Action type changed: {diff['action_type_changed']}/{diff['total_paired']} ({diff['action_type_changed_pct']}%)")

    print(f"\n[Action Distribution — Variant A (off)]")
    for atype, pct in diff["action_distribution"]["A"].items():
        print(f"  {atype}: {pct}%")
    print(f"\n[Action Distribution — Variant B (on)]")
    for atype, pct in diff["action_distribution"]["B"].items():
        print(f"  {atype}: {pct}%")

    print(f"\n[Decision Driver Distribution — Variant A]")
    for driver, pct in diff["decision_driver_distribution"]["A"].items():
        print(f"  {driver}: {pct}%")
    print(f"\n[Decision Driver Distribution — Variant B]")
    for driver, pct in diff["decision_driver_distribution"]["B"].items():
        print(f"  {driver}: {pct}%")

    print(f"\n[Relationship Drift — Paired (B - A delta)]")
    total_drift_a = 0
    total_drift_b = 0
    for rd in diff["relationship_drift"]:
        total_drift_a += rd["drift_a"]
        total_drift_b += rd["drift_b"]
    print(f"  Variant A total changed relationships: {total_drift_a}")
    print(f"  Variant B total changed relationships: {total_drift_b}")
    if diff["relationship_drift"]:
        avg_a = round(total_drift_a / len(diff["relationship_drift"]), 2)
        avg_b = round(total_drift_b / len(diff["relationship_drift"]), 2)
        print(f"  Per-step avg: A={avg_a}, B={avg_b}")

    print(f"\n{'='*70}")
    print("Per-Agent Breakdown")
    print(f"{'='*70}")
    for agent_id, summary in summaries.items():
        print(f"\n[Agent {agent_id}: {summary['agent_name']}]")
        print(f"  Steps: {summary['total_steps']}")
        print(f"  Action changed: {summary['action_changed_pct']}%")
        print(f"  Activity changed: {summary['activity_changed_pct']}%")
        print(f"  Action type changed: {summary['action_type_changed_pct']}%")
        rel = summary["relationship_drift"]
        if rel:
            avg_a = round(sum(d["drift_a"] for d in rel) / len(rel), 2)
            avg_b = round(sum(d["drift_b"] for d in rel) / len(rel), 2)
            print(f"  Relationship drift avg: A={avg_a}, B={avg_b}")

    print(f"\n{'='*70}")
    print("Interpretation Guide")
    print(f"{'='*70}")
    print("""
• Action changed: % of steps where B chose a different action than A.
  Higher % means LH context is influencing action selection.
• Activity changed: % of steps where final activity differed between runs.
• Action type changed: % where the categorical type (movement/social/work/etc) differed.
• Relationship drift: Variant B should show more relationship change if
  LH-driven social interactions are modifying trust/closeness beyond baseline.
• Decision drivers: Watch for shift from "时空约束" toward "人格角色驱动"
  or other profile-influenced drivers in Variant B.
""")


def main():
    parser = argparse.ArgumentParser(description="LifeHistory Paired A/B Report")
    parser.add_argument("-a", "--variant-a", required=True, help="Path to variant A log file or directory")
    parser.add_argument("-b", "--variant-b", required=True, help="Path to variant B log file or directory")
    parser.add_argument("--date", help="Date string YYYYMMDD (default: today)")
    parser.add_argument("--agents", nargs="*", type=int, help="Filter by agent IDs")
    args = parser.parse_args()

    # Load logs
    logs_a = load_logs_from_dir_or_file(args.variant_a)
    logs_b = load_logs_from_dir_or_file(args.variant_b)

    if not logs_a:
        print(f"ERROR: No logs found for variant A: {args.variant_a}")
        return
    if not logs_b:
        print(f"ERROR: No logs found for variant B: {args.variant_b}")
        return

    # Filter by agents if specified
    if args.agents:
        logs_a = [l for l in logs_a if l.get("agent_id") in args.agents]
        logs_b = [l for l in logs_b if l.get("agent_id") in args.agents]

    date_str = args.date or datetime.now().strftime("%Y%m%d")
    pairs, missing_b = pair_logs(logs_a, logs_b)
    if not pairs:
        print("ERROR: No complete pairs found between variant A and B.")
        return
    diff = compute_paired_diff(pairs)
    summaries = per_agent_paired_summary(pairs)
    generate_report(pairs, diff, summaries, date_str, missing_b=missing_b)


if __name__ == "__main__":
    main()