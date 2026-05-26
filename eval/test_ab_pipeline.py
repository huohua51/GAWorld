#!/usr/bin/env python3
"""
Synthetic A/B log generator + report test.

Generates fake step logs for variant A and B with known structure,
then runs the paired report to validate end-to-end pipeline.

Usage:
    python eval/test_ab_pipeline.py              # generate fake logs and run report
    python eval/test_ab_pipeline.py --pairs 5    # 5 paired steps per variant
"""

import argparse
import gzip
import json
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "life_history_ab")


def generate_synthetic_logs(n_steps=5, seed=42):
    """Generate synthetic paired logs for A and B variants."""
    import random
    random.seed(seed)

    date_str = datetime.now().strftime("%Y%m%d")
    run_a_dir = os.path.join(OUTPUT_DIR, "run_a")
    run_b_dir = os.path.join(OUTPUT_DIR, "run_b")
    os.makedirs(run_a_dir, exist_ok=True)
    os.makedirs(run_b_dir, exist_ok=True)

    log_file = f"step_log_{date_str}.jsonl.gz"
    path_a = os.path.join(run_a_dir, log_file)
    path_b = os.path.join(run_b_dir, log_file)

    activities = ["工作", "社交", "休息", "购物", "学习"]
    action_types = ["work", "social", "rest", "transaction", "movement"]
    drivers = ["时空约束", "人格角色驱动", "能量管理", "社交需求"]
    action_prefixes = ["执行", "进行", "开始", "继续", "完成"]

    def make_entry(i, lh_present, variant):
        act = random.choice(activities)
        at = random.choice(action_types)
        drv = random.choice(drivers)
        base_trust = 0.3 + (i * 0.1) + (0.1 if variant == "B" else 0.0)
        before_trust = round(base_trust, 3)
        after_trust = round(base_trust + 0.05 + random.uniform(0, 0.1), 3)
        before = {"11": {"trust": before_trust, "closeness": round(before_trust + 0.2, 3)}}
        after = {"11": {"trust": after_trust, "closeness": round(after_trust + 0.2, 3)}}

        return {
            "timestamp": datetime.now().isoformat(),
            "agent_id": 52,
            "agent_name": "郭林峰",
            "day": 1,
            "time_str": f"{8 + i:02d}:00",
            "scheduled_activity": act,
            "perception": f"今日感知：{act}相关的环境信息",
            "life_history_context_present": lh_present,
            "life_history_context": "人格角色：内敛理性型..." if lh_present else None,
            "plan": {"goal": f"{act}目标", "constraint": "时间约束", "urge": "完成任务", "plan": f"执行{act}", "expected_outcome": "达成"},
            "activity_final": act if random.random() > 0.2 else random.choice(activities),
            "action": f"{random.choice(action_prefixes)}{act}",
            "action_type": at,
            "decision_driver": drv,
            "commitment_level": random.choice(["high", "medium", "low"]),
            "relationships_before": before,
            "relationships_after": after,
            "changed": random.random() > 0.7,
            "change_reason": "临时调整" if random.random() > 0.7 else None,
            "social_partners": [11] if random.random() > 0.5 else [],
            "success": random.random() > 0.3,
        }

    # Variant A: lh_present=False for all steps
    entries_a = [make_entry(i, False, "A") for i in range(n_steps)]
    # Variant B: lh_present=True for all steps
    entries_b = [make_entry(i, True, "B") for i in range(n_steps)]

    with gzip.open(path_a, "wt") as f:
        for entry in entries_a:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    with gzip.open(path_b, "wt") as f:
        for entry in entries_b:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return path_a, path_b, date_str


def run_report(log_a, log_b, date_str, agent_id=52):
    """Run the paired A/B report."""
    import subprocess
    report_code = f"""
import sys
sys.path.insert(0, "{PROJECT_ROOT}")
from eval.life_history_ab_report import main as report_main
sys.argv = [
    "report",
    "-a", "{log_a}",
    "-b", "{log_b}",
    "--date", "{date_str}",
    "--agents", "{agent_id}",
]
report_main()
"""
    result = subprocess.run(
        [sys.executable, "-c", report_code],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    return result.stdout, result.stderr


def main():
    parser = argparse.ArgumentParser(description="Test A/B pipeline with synthetic logs")
    parser.add_argument("--pairs", type=int, default=5, help="Number of paired steps per variant (default: 5)")
    args = parser.parse_args()

    print("=" * 60)
    print("LifeHistory A/B Pipeline Test")
    print(f"  Paired steps: {args.pairs}")
    print("=" * 60)

    print("\n[Step 1] Generating synthetic logs...")
    log_a, log_b, date_str = generate_synthetic_logs(n_steps=args.pairs, seed=42)
    size_a = os.path.getsize(log_a)
    size_b = os.path.getsize(log_b)
    print(f"  Variant A: {log_a} ({size_a} bytes)")
    print(f"  Variant B: {log_b} ({size_b} bytes)")

    print("\n[Step 2] Running paired report...")
    stdout, stderr = run_report(log_a, log_b, date_str)
    print(stdout)
    if stderr:
        print(f"STDERR: {stderr[-200:]}")

    print("\n" + "=" * 60)
    print("Pipeline test complete. Review the report above:")
    print("- paired steps count should be <= total generated")
    print("- B variant should show higher LH context rate (100% vs 0%)")
    print("- action_changed / activity_changed show behavioral diff")
    print("- relationship drift shows per-variant baseline computation")
    print("=" * 60)


if __name__ == "__main__":
    main()