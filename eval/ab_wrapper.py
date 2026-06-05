#!/usr/bin/env python3
"""
A/B Wrapper: Run the same simulation with Group A (control) and Group B (experiment) configs.

Usage:
    python eval/ab_wrapper.py              # dry-run: print both configs
    python eval/ab_wrapper.py --run        # run both groups sequentially
    python eval/ab_wrapper.py --run --group B   # run only Group B

Config differences:
  Group A (control)   — features OFF: personal_twin, human_realism, dynamic_behavior
  Group B (experiment) — all features ON
"""
import copy
import json
import os
import sys
import time
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_CONFIG = REPO_ROOT / "dashboard_config.json"
OUTPUT_DIR = REPO_ROOT / "output"

# Shared base config (disables all I/O-heavy non-AB features)
_BASE = {
    "sim_days": 1,
    "seconds_per_day": 10,
    "stateful": False,
    "agent_ids": [1],
    "simulate_realtime": False,
    "distributed": {"enabled": False},
    "news": {"enabled": False, "info_seek": {"enabled": False}},
    "external_rag": {"bootstrap": {"enabled": False}},
    "external_environment_service": {"enabled": False},
    "intervention": {"enabled": False},
    "visualization": {"enabled": False},
    "life_events": {"enabled": False},
    "openclaw": {"enabled": False},
}

# ---- Group A: control (main-like) ----
CONFIG_A = copy.deepcopy(_BASE)
CONFIG_A.update({
    "personal_twin": {"enabled": False},
    "human_realism": {"enabled": False},
    "dynamic_behavior": {"enabled": False},
    "ab_experiment": {"enabled": False},
    "real_work": {"enabled": False},  # disable for speed; not part of AB hypothesis
    "economy": {
        "enabled": True,
        "currency": "CNY",
        "output_dir": "output/economy",
    },
    # LOG_MODE to normal (not simple)
    "log_mode": "normal",
})
# Also keep the original llm routing
CONFIG_A.setdefault("llm", {}).setdefault("routing", {}).update({
    "default": "minimax",
})

# ---- Group B: experiment (user's features ON) ----
CONFIG_B = copy.deepcopy(_BASE)
CONFIG_B.update({
    "personal_twin": {
        "enabled": True,
        "local_first": True,
        "private_memory_policy": "local_only",
        "share_social_summaries": True,
        "daily_self_update": True,
        "what_if_enabled": False,  # don't waste API on what-if during AB
    },
    "human_realism": {
        "enabled": True,
        "llm": {"max_extra_calls_per_agent_day": 2},
        "memory": {
            "max_episodes_per_agent": 2000,
            "daily_consolidation_top_k": 12,
            "salience_threshold": 0.35,
            "recall": {"window_days": 5, "top_k": 5},
            "review": {"enabled": True},
        },
        "behavior": {
            "enabled": True,
            "step_reminisce_chance": 0.05,
            "step_planning_overlay": True,
        },
    },
    "dynamic_behavior": {"enabled": True},
    "ab_experiment": {"enabled": False},  # keep off for clean AB test
    "real_work": {"enabled": False},  # disable for speed; not part of AB hypothesis
    "economy": {
        "enabled": True,
        "currency": "CNY",
        "output_dir": "output/economy",
    },
    # Simple log mode so output is readable
    "log_mode": "simple",
})
CONFIG_B.setdefault("llm", {}).setdefault("routing", {}).update({
    "default": "minimax",
})


def write_config(path, config):
    """Write config to dashboard_config.json, preserving llm.providers from existing."""
    existing = {}
    if path.exists():
        with open(path) as f:
            existing = json.load(f)

    # Keep LLM provider config (API keys, base URLs) from existing
    merged = copy.deepcopy(config)
    if "llm" in existing and "providers" in existing["llm"]:
        merged.setdefault("llm", {})
        merged["llm"]["providers"] = existing["llm"]["providers"]
    if "llm" in existing and "routing" in existing["llm"]:
        merged.setdefault("llm", {})
        merged["llm"]["routing"] = existing["llm"]["routing"]

    # Use MiniMax M2.7 via Anthropic API
    merged.setdefault("llm", {}).setdefault("providers", {})
    merged["llm"]["providers"]["minimax"] = {
        "type": "anthropic",
        "base_url": "https://api.minimaxi.com/anthropic",
        "model": "MiniMax-M2.7",
        "api_key_env": "MINIMAX_API_KEY",
        "api_key_envs": ["MINIMAX_API_KEY", "ANTHROPIC_AUTH_TOKEN"],
        "authorization_scheme": "bearer",
        "include_x_api_key": False,
        "timeout": 600,
        "max_tokens": 2048,
    }
    merged["llm"]["routing"] = {"default": "minimax", "tasks": {}}

    with open(path, "w") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"  Config written to {path}")


# New MiniMax API key provided by user
MINIMAX_KEY = "sk-cp-HnZC_G--iW6W6nO1YHfyR2StK4S46RaI3LuXd5P5wVH7-M6tirA4Hg1MRzRi7EMAuwMqlz3W-NqZ1_llw57g6maDj44nTuKFiRYvVJnTTj22sIb8P5fLsNk"


def run_simulation(label, output_log):
    """Run generative_city_sim.py run and pipe output to a log file."""
    cmd = [sys.executable, "generative_city_sim.py", "run"]
    env = os.environ.copy()
    # Strip proxy vars inherited from Claude Code (route directly, not through local proxy)
    for key in list(env):
        if key.lower().endswith("_proxy"):
            del env[key]
    # Force correct MiniMax base URL (strip inherited env override)
    env.pop("ANTHROPIC_BASE_URL", None)
    # Inject the MiniMax API key into the subprocess environment
    env["ANTHROPIC_AUTH_TOKEN"] = MINIMAX_KEY
    env["MINIMAX_API_KEY"] = MINIMAX_KEY
    env["MINIMAX_AUTHORIZATION_SCHEME"] = "bearer"
    env["PYTHONUNBUFFERED"] = "1"  # flush stdout immediately
    print(f"  Running: {' '.join(cmd)}")
    print(f"  Log: {output_log}")

    start = time.time()
    with open(output_log, "w") as log_f:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=3600,  # 1 hour max per group
        )
    elapsed = time.time() - start
    print(f"  Finished in {elapsed:.0f}s, exit code={proc.returncode}")
    return proc.returncode == 0


def main():
    dry_run = "--run" not in sys.argv
    run_group = None
    if "--group" in sys.argv:
        idx = sys.argv.index("--group")
        if idx + 1 < len(sys.argv):
            run_group = sys.argv[idx + 1].upper()

    os.chdir(str(REPO_ROOT))

    import shutil
    sim_output_dir = REPO_ROOT / "output"
    ab_output_dir = REPO_ROOT / "output_ab"
    ab_output_dir.mkdir(exist_ok=True)

    # --- Group A ---
    if not run_group or run_group == "A":
        group_a_dir = ab_output_dir / "group_a"
        if group_a_dir.exists():
            shutil.rmtree(group_a_dir)

        print("=" * 60)
        print("GROUP A (control) — features OFF")
        print("=" * 60)
        for k, v in sorted(CONFIG_A.items()):
            if isinstance(v, dict):
                print(f"  {k}: ...")
            else:
                print(f"  {k}: {v}")
        if not dry_run:
            write_config(DASHBOARD_CONFIG, CONFIG_A)
            # Clean sim output before run
            if sim_output_dir.exists():
                shutil.rmtree(sim_output_dir)
            ok = run_simulation("A", REPO_ROOT / "output_ab" / "ab_run_a.log")
            # Move output to group_a directory
            if sim_output_dir.exists():
                shutil.copytree(sim_output_dir, group_a_dir, dirs_exist_ok=True)
                print(f"  Copied output to {group_a_dir}")
            if not ok:
                print("!! Group A failed")
        else:
            print("  (dry-run, not executed)")

    # --- Group B ---
    if not run_group or run_group == "B":
        group_b_dir = ab_output_dir / "group_b"
        if group_b_dir.exists():
            shutil.rmtree(group_b_dir)

        print()
        print("=" * 60)
        print("GROUP B (experiment) — all features ON")
        print("=" * 60)
        for k, v in sorted(CONFIG_B.items()):
            if isinstance(v, dict):
                print(f"  {k}: ...")
            else:
                print(f"  {k}: {v}")
        if not dry_run:
            write_config(DASHBOARD_CONFIG, CONFIG_B)
            if sim_output_dir.exists():
                shutil.rmtree(sim_output_dir)
            ok = run_simulation("B", REPO_ROOT / "output_ab" / "ab_run_b.log")
            if sim_output_dir.exists():
                shutil.copytree(sim_output_dir, group_b_dir, dirs_exist_ok=True)
                print(f"  Copied output to {group_b_dir}")
            if not ok:
                print("!! Group B failed")
        else:
            print("  (dry-run, not executed)")

    print()
    print("Done.")


if __name__ == "__main__":
    main()
