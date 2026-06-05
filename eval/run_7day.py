#!/usr/bin/env python3
"""Run 7-day single-agent simulation with qwen3:4b-instruct."""
import json, os, sys, time, subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.chdir(str(REPO))

CONFIG = {
    "sim_days": 7,
    "seconds_per_day": 3,
    "stateful": False,
    "agent_ids": [52],
    "simulate_realtime": False,
    "log_mode": "normal",
    "personal_twin": {"enabled": True, "local_first": True, "private_memory_policy": "local_only",
                       "share_social_summaries": True, "daily_self_update": True, "what_if_enabled": False},
    "human_realism": {"enabled": True, "llm": {"max_extra_calls_per_agent_day": 2},
                       "memory": {"max_episodes_per_agent": 5000, "daily_consolidation_top_k": 12,
                                  "salience_threshold": 0.35, "recall": {"window_days": 7, "top_k": 5},
                                  "review": {"enabled": True}},
                       "behavior": {"enabled": True, "step_reminisce_chance": 0.05, "step_planning_overlay": True}},
    "dynamic_behavior": {"enabled": True},
    "ab_experiment": {"enabled": False},
    "real_work": {"enabled": False},
    "economy": {"enabled": True, "currency": "CNY", "output_dir": "output/economy"},
    "distributed": {"enabled": False},
    "news": {"enabled": False},
    "intervention": {"enabled": False},
    "visualization": {"enabled": False},
    "life_events": {"enabled": False},
    "openclaw": {"enabled": False},
}

CONFIG.setdefault("llm", {}).setdefault("providers", {})
CONFIG["llm"]["providers"]["ollama_qwen"] = {
    "type": "ollama", "url": "http://localhost:11434/api/generate",
    "model": "qwen3:4b-instruct-2507-q4_K_M", "timeout": 600,
}
CONFIG["llm"]["routing"] = {"default": "ollama_qwen", "tasks": {"schedule": "ollama_qwen"}}

with open(REPO / "dashboard_config.json", "w") as f:
    json.dump(CONFIG, f, indent=2, ensure_ascii=False)
print("Config written.")

subprocess.run([sys.executable, "generative_city_sim.py", "reset"], capture_output=True)

env = os.environ.copy()
for key in list(env):
    if key.lower().endswith("_proxy") or "proxy" in key.lower():
        del env[key]
env.pop("ANTHROPIC_BASE_URL", None)

log_path = REPO / "output" / "run_7day.log"
log_path.parent.mkdir(exist_ok=True)

print("Starting 7-day run (郭林峰, qwen3:4b)...")
start = time.time()
proc = subprocess.run(
    [sys.executable, "generative_city_sim.py", "run"],
    cwd=str(REPO), env=env,
    stdout=open(log_path, "w"), stderr=subprocess.STDOUT,
    text=True, timeout=86400,
)
elapsed = time.time() - start
print(f"Finished in {elapsed:.0f}s, exit code={proc.returncode}")
