#!/usr/bin/env python3
"""Run 7 days for agent 52 (郭林峰), then 7 days for agent 1 (李泽宇). No reset between."""
import json, os, sys, time, subprocess, shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.chdir(str(REPO))

BASE = {
    "sim_days": 7, "seconds_per_day": 3, "stateful": False,
    "simulate_realtime": False, "log_mode": "normal",
    "personal_twin": {"enabled": True, "local_first": True, "private_memory_policy": "local_only",
                       "share_social_summaries": True, "daily_self_update": True, "what_if_enabled": False},
    "human_realism": {"enabled": True, "llm": {"max_extra_calls_per_agent_day": 2},
                       "memory": {"max_episodes_per_agent": 5000, "daily_consolidation_top_k": 12,
                                  "salience_threshold": 0.35, "recall": {"window_days": 7, "top_k": 5},
                                  "review": {"enabled": True}},
                       "behavior": {"enabled": True, "step_reminisce_chance": 0.05, "step_planning_overlay": True}},
    "dynamic_behavior": {"enabled": True}, "ab_experiment": {"enabled": False}, "real_work": {"enabled": False},
    "economy": {"enabled": True, "currency": "CNY", "output_dir": "output/economy"},
    "distributed": {"enabled": False}, "news": {"enabled": False}, "intervention": {"enabled": False},
    "visualization": {"enabled": False}, "life_events": {"enabled": False}, "openclaw": {"enabled": False},
    "llm": {"providers": {"ollama_qwen": {"type": "ollama", "url": "http://localhost:11434/api/generate",
                                          "model": "qwen3:4b-instruct-2507-q4_K_M", "timeout": 600}},
            "routing": {"default": "ollama_qwen", "tasks": {"schedule": "ollama_qwen"}}}
}

env = os.environ.copy()
for k in list(env):
    if k.lower().endswith("_proxy") or "proxy" in k.lower(): del env[k]
env.pop("ANTHROPIC_BASE_URL", None)

def run_for(agent_id, label):
    cfg = dict(BASE)
    cfg["agent_ids"] = [agent_id]
    with open(REPO / "dashboard_config.json", "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    log_path = REPO / "output" / f"run_7day_{agent_id}.log"
    log_path.parent.mkdir(exist_ok=True)
    print(f"Starting 7-day run for {label} (agent {agent_id})...")
    start = time.time()
    proc = subprocess.run([sys.executable, "generative_city_sim.py", "run"],
        cwd=str(REPO), env=env, stdout=open(log_path, "w"), stderr=subprocess.STDOUT,
        text=True, timeout=86400)
    elapsed = time.time() - start
    print(f"Finished: {elapsed:.0f}s exit={proc.returncode}")

# Run 郭林峰 first
run_for(52, "郭林峰")
# Backup 郭林峰 data
import shutil
src52 = REPO / "output" / "diaries" / "agent_52"
bak52 = REPO / "output" / "diaries_backup" / "agent_52"
if src52.exists():
    shutil.copytree(src52, bak52, dirs_exist_ok=True)
    print(f"✅ Backed up 郭林峰 data to {bak52}")

# Run 李泽宇
run_for(1, "李泽宇")
src1 = REPO / "output" / "diaries" / "agent_1"
bak1 = REPO / "output" / "diaries_backup" / "agent_1"
if src1.exists():
    shutil.copytree(src1, bak1, dirs_exist_ok=True)
    print(f"✅ Backed up 李泽宇 data to {bak1}")

# Restore both from backup to diaries
if bak52.exists():
    shutil.copytree(bak52, src52, dirs_exist_ok=True)
if bak1.exists():
    shutil.copytree(bak1, src1, dirs_exist_ok=True)
print(f"Both 7-day runs complete! Diaries in: output/diaries/")
