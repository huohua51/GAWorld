#!/usr/bin/env python3
"""
LifeHistory Injection A/B Experiment Runner

Runs two simulation instances sequentially using `python generative_city_sim.py run`:
  Variant A: injection_enabled=False (no profile context in planning)
  Variant B: injection_enabled=True  (profile context injected each step)

Both share the same agents, seeds, and sim_days with isolated memory/log dirs.
Logs are written to isolated scenario directories (run_a/ and run_b/).

Usage:
    python eval/run_mini_ab.py                          # defaults: agents=[52], days=1, seeds=[42]
    python eval/run_mini_ab.py --agents 52 --seeds 42 43  # multi-seed for statistical significance
    python eval/run_mini_ab.py --dry-run                # preview commands
    python eval/run_mini_ab.py --report-only            # generate report from last run

Output:
    output/life_history_ab/run_a/seed_{N}/life_history_logs/step_log_{date}.jsonl.gz
    output/life_history_ab/run_b/seed_{N}/life_history_logs/step_log_{date}.jsonl.gz
"""

import os
import sys
import subprocess
import argparse
import glob as _glob
import time
import statistics
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_step_log(base_dir):
    """Find step log in a variant directory tree."""
    logs = _glob.glob(os.path.join(base_dir, "**", "step_log_*.jsonl.gz"), recursive=True)
    return logs[0] if logs else None


def run_variant(variant_label, agent_ids, seed, sim_days, injection_enabled, dry_run=False):
    """Run a single variant of the simulation with given injection setting."""
    base_output = os.path.join(PROJECT_ROOT, "output", "life_history_ab", variant_label.lower(), f"seed_{seed}")
    lh_log_dir = os.path.join(base_output, "life_history_logs")
    os.makedirs(lh_log_dir, exist_ok=True)

    variant_memory_dir = os.path.join(base_output, "memory")
    variant_log_dir = os.path.join(base_output, "logs")
    variant_vector_db = os.path.join(base_output, "memory", "vector_db.sqlite")

    overrides = {
        "random_seed": int(seed),
        "sim_days": int(sim_days),
        "agent_ids": list(agent_ids),
        "life_history": {
            "enabled": True,
            "injection_enabled": injection_enabled,
            "instrument_agents": list(agent_ids),
            "log_output_dir": lh_log_dir,
        },
        "distributed": {"enabled": False},
        "memory_dir": variant_memory_dir,
        "log_dir": variant_log_dir,
        "vector_db_path": variant_vector_db,
        "stateful": False,
    }

    import json
    env = dict(os.environ)
    env["GAWORLD_CONFIG_OVERRIDES"] = json.dumps(overrides, ensure_ascii=False)

    cmd = [
        sys.executable,
        os.path.join(PROJECT_ROOT, "generative_city_sim.py"),
        "run",
    ]

    print(f"\n[{variant_label}] seed={seed} injection_enabled={injection_enabled}")
    print(f"  agents: {agent_ids}")
    print(f"  lh_log_dir: {lh_log_dir}")
    print(f"  cmd: {' '.join(cmd)}")

    if dry_run:
        print("  (dry run, skipping)")
        return base_output, None

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT, env=env, timeout=1800)
    if result.stdout:
        last = result.stdout.strip().split("\n")
        print(f"  stdout (last 3 lines): " + "\n".join(last[-3:]))
    if result.returncode != 0:
        print(f"  WARNING: returned {result.returncode}")
        if result.stderr:
            print(f"  stderr (last 300): {result.stderr[-300:]}")
        return base_output, None

    log = find_step_log(base_output)
    print(f"  step log: {log}")
    return base_output, log


def generate_report(log_a, log_b, date_str, agent_ids):
    """Run paired A/B report from two log files."""
    import gzip
    with gzip.open(log_a, "rt") as f:
        lines_a = [l for l in f if l.strip()]
    with gzip.open(log_b, "rt") as f:
        lines_b = [l for l in f if l.strip()]
    print(f"Variant A (injection off): {len(lines_a)} steps")
    print(f"Variant B (injection on):  {len(lines_b)} steps")

    # Build argv list: ["report", "-a", path, "-b", path, "--date", str, "--agents", "52", "11", ...]
    agents_arg = [str(a) for a in agent_ids]
    argv_parts = [
        "report", "-a", log_a, "-b", log_b,
        "--date", date_str, "--agents",
    ] + agents_arg

    import ast
    argv_repr = repr(argv_parts)
    report_code = f"""
import sys
sys.path.insert(0, "{PROJECT_ROOT}")
from eval.life_history_ab_report import main as report_main
sys.argv = {argv_repr}
report_main()
"""

    result = subprocess.run(
        [sys.executable, "-c", report_code],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    print(result.stdout)
    if result.stderr:
        print(f"STDERR: {result.stderr[-200:]}")


def run_and_collect(args):
    """Run A/B for all seeds, collect log paths."""
    results = []  # list of (seed, log_a, log_b)

    for seed in args.seeds:
        print("\n" + "=" * 60)
        print(f"Seed {seed}/{len(args.seeds)}")
        print("=" * 60)

        dir_a, log_a = run_variant(
            "A", agent_ids=args.agents, seed=seed, sim_days=args.sim_days,
            injection_enabled=False, dry_run=args.dry_run,
        )
        if args.dry_run:
            print("  (dry run, skipping B)")
            continue

        dir_b, log_b = run_variant(
            "B", agent_ids=args.agents, seed=seed, sim_days=args.sim_days,
            injection_enabled=True, dry_run=args.dry_run,
        )

        results.append((seed, log_a, log_b, dir_a, dir_b))

    return results


def main():
    parser = argparse.ArgumentParser(description="Run LifeHistory Injection A/B experiment")
    parser.add_argument("--agents", type=int, nargs="+", default=[52],
                        help="Agent IDs to instrument (default: 52)")
    parser.add_argument("--seeds", type=int, nargs="+", default=[42],
                        help="Random seeds (default: 42). Multiple seeds for statistical significance.")
    parser.add_argument("--sim-days", type=int, default=1, help="Simulation days (default: 1)")
    parser.add_argument("--dry-run", action="store_true", help="Show commands without executing")
    parser.add_argument("--report-only", action="store_true", help="Generate report from last run")
    parser.add_argument("--multi", action="store_true",
                        help="Aggregate multiple seeds into statistical report")
    args = parser.parse_args()

    date_str = datetime.now().strftime("%Y%m%d")
    agent_ids_str = ",".join(str(a) for a in args.agents)

    print("=" * 60)
    print("LifeHistory Injection A/B Experiment")
    print(f"  Agents: {args.agents}, Days: {args.sim_days}, Seeds: {args.seeds}")
    print("=" * 60)

    if args.report_only:
        def latest_seed_dir(variant):
            """Find latest run dir under variant, handles both new (seed_N) and legacy (flat) layouts."""
            base = os.path.join(PROJECT_ROOT, "output", "life_history_ab", variant)
            # Try new seed_N layout first
            seed_dirs = _glob.glob(os.path.join(base, "seed_*"))
            if seed_dirs:
                latest = sorted(seed_dirs, key=os.path.getmtime, reverse=True)[0]
                log = find_step_log(latest)
                if log:
                    return latest, log
            # Fall back to legacy flat layout (a/life_history_logs/step_log_*.jsonl.gz)
            flat_dir = os.path.join(base, "life_history_logs")
            if os.path.isdir(flat_dir):
                logs = _glob.glob(os.path.join(flat_dir, "step_log_*.jsonl.gz"))
                if logs:
                    return flat_dir, logs[0]
            return None, None

        dir_a, log_a = latest_seed_dir("a")
        dir_b, log_b = latest_seed_dir("b")
        if not log_a or not log_b:
            print("ERROR: Step logs not found.")
            print(f"  log_a: {log_a} (dir: {dir_a})")
            print(f"  log_b: {log_b} (dir: {dir_b})")
            return
        generate_report(log_a, log_b, date_str, args.agents)
        return

    # Run all seed experiments
    results = run_and_collect(args)

    if args.dry_run:
        return

    if not results:
        print("No results collected.")
        return

    # Generate per-seed reports
    print("\n" + "=" * 60)
    print("Per-Seed Reports")
    print("=" * 60)

    all_action_rates = []
    all_activity_rates = []
    all_at_rates = []

    for seed, log_a, log_b, dir_a, dir_b in results:
        print(f"\n--- Seed {seed} ---")
        if log_a and log_b:
            # Generate report via inline computation
            import gzip, json
            from collections import defaultdict

            def load_log(path):
                with gzip.open(path, "rt") as f:
                    return [json.loads(l) for l in f if l.strip()]

            logs_a = load_log(log_a)
            logs_b = load_log(log_b)

            b_index = {(e["agent_id"], e["day"], e["time_str"]): e for e in logs_b}
            pairs = [(e, b_index[(e["agent_id"], e["day"], e["time_str"])])
                     for e in logs_a if (e["agent_id"], e["day"], e["time_str"]) in b_index]

            total = len(pairs)
            action_changed = sum(1 for a, b in pairs if a.get("action") != b.get("action"))
            activity_changed = sum(1 for a, b in pairs if a.get("activity_final") != b.get("activity_final"))
            at_changed = sum(1 for a, b in pairs if a.get("action_type") != b.get("action_type"))

            action_rate = action_changed / total * 100 if total else 0
            activity_rate = activity_changed / total * 100 if total else 0
            at_rate = at_changed / total * 100 if total else 0

            all_action_rates.append(action_rate)
            all_activity_rates.append(activity_rate)
            all_at_rates.append(at_rate)

            print(f"  Paired steps: {total}")
            print(f"  Action changed: {action_changed}/{total} ({action_rate:.1f}%)")
            print(f"  Activity changed: {activity_changed}/{total} ({activity_rate:.1f}%)")
            print(f"  Action type changed: {at_changed}/{total} ({at_rate:.1f}%)")
        else:
            print(f"  log_a: {log_a}, log_b: {log_b} — skipping")

    # Statistical summary across seeds
    if len(args.seeds) > 1 and all_action_rates:
        print("\n" + "=" * 60)
        print("Statistical Summary (across seeds)")
        print("=" * 60)
        print(f"  Action changed rate:  {mean_std(all_action_rates)}")
        print(f"  Activity changed rate: {mean_std(all_activity_rates)}")
        print(f"  Action type changed rate: {mean_std(all_at_rates)}")

    # Generate report for the LAST seed (most recent)
    if results:
        last = results[-1]
        seed, log_a, log_b, dir_a, dir_b = last
        if log_a and log_b:
            print(f"\n--- Report for last seed ({seed}) ---")
            generate_report(log_a, log_b, date_str, args.agents)


def mean_std(values):
    if not values:
        return "N/A"
    if len(values) == 1:
        return f"{values[0]:.1f}%"
    return f"{statistics.mean(values):.1f}% ± {statistics.stdev(values):.1f}%"


if __name__ == "__main__":
    main()