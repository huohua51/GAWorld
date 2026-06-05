#!/usr/bin/env python3
"""Run N-day simulation with Ollama phi4-mini (for main branch comparison)."""
import json, os, sys, time, subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.chdir(str(REPO))

# Minimal config for main branch (no personal_twin/human_realism/dynamic_behavior)
CONFIG = {
    "sim_days": 3,
    "seconds_per_day": 3,
    "stateful": False,
    "agent_ids": [1],
    "simulate_realtime": False,
    "log_mode": "normal",
    "economy": {"enabled": True, "currency": "CNY", "output_dir": "output/economy"},
    "distributed": {"enabled": False},
    "news": {"enabled": False},
    "intervention": {"enabled": False},
    "visualization": {"enabled": False},
    "life_events": {"enabled": False},
    "openclaw": {"enabled": False},
}

# Set Ollama phi4-mini as the LLM provider
CONFIG.setdefault("llm", {}).setdefault("providers", {})
CONFIG["llm"]["providers"]["ollama_local"] = {
    "type": "ollama",
    "url": "http://localhost:11434/api/generate",
    "model": "phi4-mini",
    "timeout": 600,
}
CONFIG["llm"]["routing"] = {"default": "ollama_local", "tasks": {"schedule": "ollama_local"}}

dash_path = REPO / "dashboard_config.json"
with open(dash_path, "w") as f:
    json.dump(CONFIG, f, indent=2, ensure_ascii=False)
print("Config written.")

# Reset
subprocess.run([sys.executable, "generative_city_sim.py", "reset"], capture_output=True)

# Build env (strip proxy vars)
env = os.environ.copy()
for key in list(env):
    if key.lower().endswith("_proxy") or "proxy" in key.lower():
        del env[key]
env.pop("ANTHROPIC_BASE_URL", None)

log_path = REPO / "output" / "run_main.log"
log_path.parent.mkdir(exist_ok=True)

print(f"Starting 3-day run (main branch, agent 1)...")
start = time.time()
proc = subprocess.run(
    [sys.executable, "generative_city_sim.py", "run"],
    cwd=str(REPO), env=env,
    stdout=open(log_path, "w"), stderr=subprocess.STDOUT,
    text=True, timeout=86400,
)
elapsed = time.time() - start
print(f"Finished in {elapsed:.0f}s, exit code={proc.returncode}")
