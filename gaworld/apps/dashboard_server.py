import json
import os
import re
import subprocess
import sys
import time
from copy import deepcopy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gaworld.settings import CONFIG
from gaworld.events.life import add_life_event, list_life_event_templates, list_life_events
from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.dashboard")


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DASHBOARD_ROOT = os.path.join(REPO_ROOT, "site", "dashboard")
DASHBOARD_CONFIG_PATH = os.path.join(REPO_ROOT, "dashboard_config.json")
PROFILE_PATH = os.path.join(REPO_ROOT, CONFIG.get("md_path", "data/hangzhou_profiles_with_names.md"))
RUN_LOG_PATH = os.path.join(REPO_ROOT, "output", "dashboard", "simulation_run.log")
PROFILE_HEADER_RE = re.compile(r"^## Profile\s+(\d+)\s*[｜|]\s*(.+?)\s*$", re.MULTILINE)

RUN_STATE = {
    "process": None,
    "started_at": None,
    "log_path": RUN_LOG_PATH,
}


def _deep_update(base, patch):
    if not isinstance(base, dict) or not isinstance(patch, dict):
        return base
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _read_json_file(path, default=None):
    if not os.path.exists(path):
        return {} if default is None else default
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default
    return payload


def _atomic_write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _dashboard_config():
    payload = _read_json_file(DASHBOARD_CONFIG_PATH, {})
    return payload if isinstance(payload, dict) else {}


def _effective_config():
    cfg = deepcopy(CONFIG)
    _deep_update(cfg, _dashboard_config())
    return cfg


def _provider_names(cfg):
    providers = cfg.get("llm", {}).get("providers", {})
    return sorted(providers.keys())


def _config_summary():
    cfg = _effective_config()
    routing = cfg.get("llm", {}).get("routing", {})
    return {
        "agent_ids": cfg.get("agent_ids", []),
        "sim_days": cfg.get("sim_days"),
        "seconds_per_day": cfg.get("seconds_per_day"),
        "simulate_realtime": cfg.get("simulate_realtime"),
        "time_step_minutes": cfg.get("time_step_minutes"),
        "calendar": cfg.get("calendar", {}),
        "llm": {
            "providers": _provider_names(cfg),
            "routing": routing,
        },
        "visualization": cfg.get("visualization", {}),
        "dashboard_config": _dashboard_config(),
    }


def _sanitize_config_patch(payload):
    patch = {}
    for key in ("sim_days", "seconds_per_day"):
        if key in payload:
            patch[key] = max(1, int(payload[key]))
    if "agent_ids" in payload:
        ids = payload.get("agent_ids")
        if isinstance(ids, str):
            ids = [part.strip() for part in ids.split(",")]
        patch["agent_ids"] = [int(item) for item in ids if str(item).strip()]
    if "simulate_realtime" in payload:
        patch["simulate_realtime"] = bool(payload["simulate_realtime"])
    if "time_step_minutes" in payload:
        value = payload["time_step_minutes"]
        patch["time_step_minutes"] = None if value in ("", None, 0, "0") else value
    if isinstance(payload.get("calendar"), dict):
        patch["calendar"] = payload["calendar"]
    if isinstance(payload.get("llm"), dict):
        llm = payload["llm"]
        routing = llm.get("routing", {})
        if isinstance(routing, dict):
            patch.setdefault("llm", {})["routing"] = routing
    return patch


def _save_config_patch(payload):
    current = _dashboard_config()
    patch = _sanitize_config_patch(payload)
    _deep_update(current, patch)
    _atomic_write_json(DASHBOARD_CONFIG_PATH, current)
    return _config_summary()


def _profile_sections():
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return "", []
    matches = list(PROFILE_HEADER_RE.finditer(text))
    sections = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append({
            "id": int(match.group(1)),
            "name": match.group(2).strip(),
            "start": start,
            "end": end,
            "text": text[start:end].strip() + "\n",
        })
    return text, sections


def _agents_summary():
    _, sections = _profile_sections()
    configured = set(int(item) for item in _effective_config().get("agent_ids", []))
    return [
        {
            "id": section["id"],
            "name": section["name"],
            "configured": section["id"] in configured,
        }
        for section in sections
    ]


def _agent_profile(agent_id):
    _, sections = _profile_sections()
    for section in sections:
        if section["id"] == int(agent_id):
            return section
    return None


def _save_agent_profile(agent_id, profile_text):
    full_text, sections = _profile_sections()
    target = None
    for section in sections:
        if section["id"] == int(agent_id):
            target = section
            break
    if not target:
        raise ValueError(f"Profile {agent_id} not found")
    new_block = str(profile_text).strip() + "\n\n"
    updated = full_text[:target["start"]] + new_block + full_text[target["end"]:]
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        f.write(updated)
    return _agent_profile(agent_id)


def _tail_text(path, max_chars=12000):
    if not os.path.exists(path):
        return ""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.seek(max(0, size - max_chars))
        data = f.read()
    return data.decode("utf-8", errors="replace")


def _memory_payload(agent_id):
    memory_dir = _effective_config().get("memory_dir", "output/memory")
    base = os.path.join(REPO_ROOT, memory_dir)
    memory = _read_json_file(os.path.join(base, f"agent_{agent_id}.json"), [])
    schedule = _read_json_file(os.path.join(base, f"agent_{agent_id}_schedule.json"), {})
    habits = _read_json_file(os.path.join(base, f"agent_{agent_id}_habits.json"), {})
    intentions = _read_json_file(os.path.join(base, f"agent_{agent_id}_intentions.json"), {})
    episodes = _tail_text(os.path.join(base, f"agent_{agent_id}_episodes.jsonl"), max_chars=24000)
    log_text = _tail_text(os.path.join(REPO_ROOT, "output", "logs", f"agent_{agent_id}.log"), max_chars=24000)
    return {
        "memory": memory,
        "schedule": schedule,
        "habits": habits,
        "intentions": intentions,
        "episodes_tail": episodes,
        "log_tail": log_text,
    }


def _run_status():
    proc = RUN_STATE.get("process")
    running = bool(proc and proc.poll() is None)
    code = None if not proc else proc.poll()
    return {
        "running": running,
        "returncode": code,
        "started_at": RUN_STATE.get("started_at"),
        "log_path": RUN_STATE.get("log_path"),
        "log_tail": _tail_text(RUN_STATE.get("log_path", RUN_LOG_PATH), max_chars=16000),
    }


def _start_simulation(payload):
    proc = RUN_STATE.get("process")
    if proc and proc.poll() is None:
        raise RuntimeError("Simulation is already running")
    if isinstance(payload.get("config"), dict):
        _save_config_patch(payload["config"])
    os.makedirs(os.path.dirname(RUN_LOG_PATH), exist_ok=True)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    if payload.get("reset"):
        with open(RUN_LOG_PATH, "w", encoding="utf-8") as log_file:
            log_file.write(f"[dashboard] reset at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            reset = subprocess.run(
                [sys.executable, os.path.join(REPO_ROOT, "generative_city_sim.py"), "reset"],
                cwd=REPO_ROOT,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if reset.returncode != 0:
                raise RuntimeError("Reset failed; check dashboard run log")
    log_mode = "a" if payload.get("reset") else "w"
    log_file = open(RUN_LOG_PATH, log_mode, encoding="utf-8")
    log_file.write(f"\n[dashboard] run at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    log_file.flush()
    proc = subprocess.Popen(
        [sys.executable, os.path.join(REPO_ROOT, "generative_city_sim.py"), "run"],
        cwd=REPO_ROOT,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    RUN_STATE["process"] = proc
    RUN_STATE["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    RUN_STATE["log_path"] = RUN_LOG_PATH
    return _run_status()


def _stop_simulation():
    proc = RUN_STATE.get("process")
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    return _run_status()


def _interview_agent(payload):
    agent_id = int(payload.get("agent_id"))
    questions = payload.get("questions") or []
    if isinstance(questions, str):
        questions = [questions]
    questions = [str(item).strip() for item in questions if str(item).strip()]
    if not questions:
        raise ValueError("At least one question is required")
    command = [sys.executable, os.path.join(REPO_ROOT, "generative_city_sim.py"), "interview", "--agent-id", str(agent_id)]
    for question in questions:
        command.extend(["--question", question])
    if payload.get("context"):
        command.extend(["--context", str(payload["context"])])
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=int(payload.get("timeout", 300)),
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _latest_trace_meta():
    trace_path = os.path.join(REPO_ROOT, "output", "visualization", "simulation_trace.json")
    latest_path = os.path.join(REPO_ROOT, "output", "visualization", "latest_frame.json")
    trace = _read_json_file(trace_path, {})
    latest = _read_json_file(latest_path, {})
    return {
        "trace_meta": trace.get("meta", {}) if isinstance(trace, dict) else {},
        "latest": latest,
    }


def _current_trace_frame():
    latest = _latest_trace_meta().get("latest", {})
    if isinstance(latest, dict) and isinstance(latest.get("frame"), dict):
        return latest["frame"]
    return {}


def _metrics_state():
    """Return personal state history from output/state/agent_state_history.csv."""
    import csv
    state_path = os.path.join(REPO_ROOT, "output", "state", "agent_state_history.csv")
    if not os.path.exists(state_path):
        return {"agents": [], "metrics": [], "data": []}
    rows = []
    agents = set()
    metrics = set()
    with open(state_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "agent_id": int(row["agent_id"]),
                "step": int(row["step"]),
                "metric": row["metric"],
                "value": float(row["value"]),
            })
            agents.add(int(row["agent_id"]))
            metrics.add(row["metric"])
    return {
        "agents": sorted(agents),
        "metrics": sorted(metrics),
        "data": rows,
    }


def _metrics_economy_daily():
    """Return daily ledger from output/economy/daily_ledger.csv."""
    import csv
    ledger_path = os.path.join(REPO_ROOT, "output", "economy", "daily_ledger.csv")
    if not os.path.exists(ledger_path):
        return {"agents": [], "columns": [], "data": []}
    rows = []
    agents = set()
    columns = []
    with open(ledger_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        for row in reader:
            rows.append({k: float(v) if k not in ("day", "agent_id", "macro_phase") else v for k, v in row.items()})
            agents.add(int(row["agent_id"]))
    return {
        "agents": sorted(agents),
        "columns": columns,
        "data": rows,
    }


def _metrics_economy_wealth():
    """Return wealth snapshot from output/economy/wealth_snapshot.csv."""
    import csv
    path = os.path.join(REPO_ROOT, "output", "economy", "wealth_snapshot.csv")
    if not os.path.exists(path):
        return {"columns": [], "data": []}
    rows = []
    columns = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        for row in reader:
            r = {}
            for k, v in row.items():
                if k in ("agent_id",):
                    r[k] = int(v)
                elif k in ("currency", "portfolio_type"):
                    r[k] = v
                else:
                    try:
                        r[k] = float(v)
                    except (ValueError, TypeError):
                        r[k] = v
            rows.append(r)
    return {"columns": columns, "data": rows}


def _metrics_macro():
    """Return macro economic state from output/economy/macro_state.json."""
    macro_path = os.path.join(REPO_ROOT, "output", "economy", "macro_state.json")
    return _read_json_file(macro_path, {})


def _metrics_intervention():
    """Return intervention metrics from output/intervention/intervention_metrics.csv."""
    import csv
    path = os.path.join(REPO_ROOT, "output", "intervention", "intervention_metrics.csv")
    if not os.path.exists(path):
        return {"agents": [], "columns": [], "data": []}
    rows = []
    agents = set()
    columns = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        for row in reader:
            r = {}
            for k, v in row.items():
                if k in ("day", "time", "agent_id"):
                    r[k] = int(v) if k != "time" else v
                else:
                    try:
                        r[k] = float(v)
                    except (ValueError, TypeError):
                        r[k] = v
            rows.append(r)
            if r.get("agent_id") is not None:
                agents.add(int(r["agent_id"]))
    return {"agents": sorted(agents), "columns": columns, "data": rows}


def _metrics_location(agent_id):
    """Return agent location data from output/memory/agent_i_locations.json."""
    loc_path = os.path.join(REPO_ROOT, "output", "memory", f"agent_{agent_id}_locations.json")
    return _read_json_file(loc_path, {})


def _metrics_episodes(agent_id):
    """Return the most recent episodes for an agent (for time mapping)."""
    ep_path = os.path.join(REPO_ROOT, "output", "memory", f"agent_{agent_id}_episodes.jsonl")
    if not os.path.exists(ep_path):
        return []
    # Read last N lines
    lines = _tail_text(ep_path, max_chars=60000).strip().split("\n")
    episodes = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            episodes.append({
                "day": obj.get("day"),
                "time": obj.get("time"),
                "step": obj.get("step"),
            })
        except json.JSONDecodeError:
            continue
    return episodes


def _metrics_step_time_map(agent_id):
    """Return ordered [{step, day, time}] for an agent, used to label x-axes with day boundaries.

    Combines data from two sources to ensure complete coverage:
      1. agent_i_episodes.jsonl - one record per step (the most reliable per-step mapping)
      2. simulation_trace.json frames - provides the (date, weekday) string per day, used as a fallback
    """
    # Primary: episodes.jsonl
    ep_path = os.path.join(REPO_ROOT, "output", "memory", f"agent_{agent_id}_episodes.jsonl")
    rows = []
    if os.path.exists(ep_path):
        with open(ep_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                step = obj.get("step")
                day = obj.get("day")
                time_str = obj.get("time")
                # If step is not in the record, use the row index
                if step is None:
                    step = len(rows)
                rows.append({
                    "step": int(step),
                    "day": int(day) if day is not None else None,
                    "time": time_str,
                })
    rows.sort(key=lambda r: r["step"])

    # Secondary: derive day info from state history when episodes lack a step index
    state_path = os.path.join(REPO_ROOT, "output", "state", "agent_state_history.csv")
    if rows and state_path and os.path.exists(state_path):
        # Build per-step day map from episodes
        steps_with_day = {r["step"]: r["day"] for r in rows if r.get("day") is not None}
        if steps_with_day:
            # Find the first/last step we know about
            known_steps = sorted(steps_with_day.keys())
            last_day = steps_with_day[known_steps[-1]]
            # Append future steps with same day
            max_step_seen = max((r["step"] for r in rows), default=0)
            return [
                r if r.get("day") is not None else {**r, "day": last_day}
                for r in rows
            ]

    return rows


def _metrics_relationships(agent_id):
    """Return personal social relationship data from output/memory/agent_i_relationships.json."""
    rel_path = os.path.join(REPO_ROOT, "output", "memory", f"agent_{agent_id}_relationships.json")
    payload = _read_json_file(rel_path, {})
    is_demo = False
    if not payload or not isinstance(payload, dict) or len(payload) == 0:
        is_demo = True
        payload = _demo_relationships(agent_id)
    return {
        "agent_id": agent_id,
        "relationships": payload,
        "is_demo": is_demo,
    }


def _demo_relationships(agent_id):
    """Fallback demo relationships used when the file is empty/missing."""
    return {
        f"g_demo_{i}": {
            "closeness": round(0.5 + (i % 3) * 0.1, 2),
            "trust": round(0.5 + (i % 4) * 0.08, 2),
            "obligation": 0.4,
            "friction": 0.1,
            "role": ["friend", "coworker", "neighbor"][i % 3],
            "kind": "ghost",
            "tie_origin": "demo_seed",
            "dunbar_tier": ["inner", "close", "acquaintance"][i % 3],
            "channels": ["chat"],
            "last_interaction_day": 1,
        }
        for i in range(5)
    }


def _metrics_social_network():
    """Build a force-directed graph dataset from all agents' relationship files.

    Nodes = each agent (id, name, label)
    Edges = in-sim relationships + ghost relationships (shown as ghost nodes)
    Returns the full graph data plus an is_demo flag if any file was empty.
    """
    profile_text, profile_sections = _profile_sections()
    agent_meta = {sec["id"]: sec["name"] for sec in profile_sections}
    nodes = []
    edges = []
    seen_agents = set()
    seen_ghosts = set()
    is_demo = False

    # Discover agents from relationship files
    memory_dir = os.path.join(REPO_ROOT, "output", "memory")
    rel_files = []
    if os.path.isdir(memory_dir):
        for name in sorted(os.listdir(memory_dir)):
            m = re.match(r"agent_(\d+)_relationships\.json$", name)
            if m:
                rel_files.append((int(m.group(1)), os.path.join(memory_dir, name)))

    if not rel_files:
        # Fallback: synthesize from profile sections
        for sec in profile_sections:
            aid = int(sec["id"])
            if aid in seen_agents:
                continue
            seen_agents.add(aid)
            nodes.append({
                "id": f"a{aid}", "agent_id": aid, "name": sec["name"],
                "kind": "agent", "tier": "inner", "value": 1.0,
            })
        # No edges
        return {"nodes": nodes, "edges": edges, "is_demo": True}

    for aid, rel_path in rel_files:
        if aid in seen_agents:
            continue
        seen_agents.add(aid)
        nodes.append({
            "id": f"a{aid}",
            "agent_id": aid,
            "name": agent_meta.get(aid, f"Agent {aid}"),
            "kind": "agent",
            "tier": "inner",
            "value": 1.0,
        })

    for aid, rel_path in rel_files:
        data = _read_json_file(rel_path, {})
        if not data:
            is_demo = True
            data = _demo_relationships(aid)
        else:
            # If file is mostly populated we keep is_demo as False
            pass
        for other_key, info in data.items():
            if not isinstance(info, dict):
                continue
            closeness = float(info.get("closeness", 0.5))
            trust = float(info.get("trust", 0.5))
            friction = float(info.get("friction", 0.0))
            role = info.get("role", "unknown")
            tier = info.get("dunbar_tier", "acquaintance")
            kind = info.get("kind", "ghost")
            profile = info.get("profile") or {}
            node_name = profile.get("name") or other_key

            target_id = other_key
            if kind == "agent":
                # In-sim link: ensure target agent node exists
                try:
                    target_agent_id = int(other_key)
                except (TypeError, ValueError):
                    continue
                target_id = f"a{target_agent_id}"
                if target_agent_id not in seen_agents:
                    seen_agents.add(target_agent_id)
                    nodes.append({
                        "id": target_id,
                        "agent_id": target_agent_id,
                        "name": agent_meta.get(target_agent_id, f"Agent {target_agent_id}"),
                        "kind": "agent",
                        "tier": "inner",
                        "value": 1.0,
                    })
            else:
                # Ghost node
                target_id = f"g_{aid}_{other_key}"
                if target_id not in seen_ghosts:
                    seen_ghosts.add(target_id)
                    nodes.append({
                        "id": target_id,
                        "name": node_name,
                        "kind": "ghost",
                        "tier": tier,
                        "role": role,
                        "value": 0.4 + closeness * 0.6,
                    })

            edges.append({
                "source": f"a{aid}",
                "target": target_id,
                "role": role,
                "tier": tier,
                "closeness": closeness,
                "trust": trust,
                "friction": friction,
                "value": round(0.5 + closeness * 1.5, 2),
                "kind": kind,
            })

    return {"nodes": nodes, "edges": edges, "is_demo": is_demo}


def _metrics_work_market():
    """Return parsed job postings from output/work/market.jsonl."""
    path = os.path.join(REPO_ROOT, "output", "work", "market.jsonl")
    if not os.path.exists(path):
        return {"jobs": [], "is_demo": True}
    jobs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            job = obj.get("job") if isinstance(obj, dict) else None
            if isinstance(job, dict):
                jobs.append(job)
    is_demo = not bool(jobs)
    return {"jobs": jobs, "is_demo": is_demo}


def _metrics_location_history(agent_id):
    """Build per-day per-step location timeline from simulation_trace.json.

    Returns:
      {
        "agent_id": int,
        "days": [
          {"day": int, "date": "2026-05-28", "weekday": "周四",
           "items": [
             {"time": "00:14", "location": "...", "activity": "...",
              "transport_mode": "bike", "distance_km": 0.85,
              "next_time": "07:32", "next_location": "..."}
           ]}
        ],
        "is_demo": False
      }
    """
    trace_path = os.path.join(REPO_ROOT, "output", "visualization", "simulation_trace.json")
    payload = _read_json_file(trace_path, {})
    frames = payload.get("frames", []) if isinstance(payload, dict) else []
    is_demo = not bool(frames)
    by_day = {}
    for frame in frames:
        day = frame.get("day")
        date = frame.get("date") or ""
        weekday = frame.get("weekday") or ""
        time_str = frame.get("time") or ""
        for a in frame.get("agents", []):
            try:
                if int(a.get("agent_id", 0)) != int(agent_id):
                    continue
            except (TypeError, ValueError):
                continue
            travel = a.get("travel", {}) or {}
            entry = {
                "time": time_str,
                "location": a.get("resolved_location") or a.get("location") or "—",
                "scheduled_activity": a.get("scheduled_activity") or "",
                "activity": a.get("activity") or "",
                "action": (a.get("action") or "")[:80],
                "transport_mode": travel.get("mode", "") or "—",
                "distance_km": float(travel.get("distance_km", 0) or 0),
                "travel_minutes": int(travel.get("minutes", 0) or 0),
                "travel_progress": float(travel.get("progress", 1.0) or 0),
                "in_transit": travel.get("status", "") == "in_transit",
            }
            by_day.setdefault(day, {"day": day, "date": date, "weekday": weekday, "items": []})
            by_day[day]["items"].append(entry)
    # Sort each day and compute next_time / next_location
    days_out = []
    for day_key in sorted(by_day.keys()):
        d = by_day[day_key]
        d["items"].sort(key=lambda x: x["time"])
        for i, it in enumerate(d["items"]):
            if i + 1 < len(d["items"]):
                it["next_time"] = d["items"][i + 1]["time"]
                it["next_location"] = d["items"][i + 1]["location"]
            else:
                it["next_time"] = ""
                it["next_location"] = ""
        days_out.append(d)
    return {"agent_id": agent_id, "days": days_out, "is_demo": is_demo}


def _metrics_daily_timeline(agent_id):
    """Combined daily timeline merging schedule.json + simulation_trace.json actuals.

    For each day, returns:
      - schedule: planned schedule items (from agent_i_schedule.json)
      - actual: actual items from simulation_trace.json
    """
    base = os.path.join(REPO_ROOT, "output", "memory")
    schedule_path = os.path.join(base, f"agent_{agent_id}_schedule.json")
    schedule = _read_json_file(schedule_path, [])
    if not isinstance(schedule, list):
        schedule = []
    history = _metrics_location_history(agent_id)
    return {
        "agent_id": agent_id,
        "schedule": schedule,
        "days": history.get("days", []),
        "is_demo": history.get("is_demo", False),
    }


def _metrics_activity_summary():
    """Aggregate activity, location, and transport signals from simulation_trace.json."""
    trace_path = os.path.join(REPO_ROOT, "output", "visualization", "simulation_trace.json")
    payload = _read_json_file(trace_path, {})
    frames = payload.get("frames", []) if isinstance(payload, dict) else []
    activity_counts = {}
    location_counts = {}
    transport_counts = {}
    distance_by_agent = {}
    days = set()
    agents = {}
    for frame in frames:
        if frame.get("day") is not None:
            days.add(int(frame["day"]))
        for agent in frame.get("agents", []):
            try:
                agent_id = int(agent.get("agent_id"))
            except (TypeError, ValueError):
                continue
            agents[agent_id] = agent.get("name") or f"Agent {agent_id}"
            activity = agent.get("activity") or "unknown"
            location = agent.get("resolved_location") or agent.get("location") or "unknown"
            travel = agent.get("travel", {}) or {}
            mode = travel.get("mode") or "none"
            distance = float(travel.get("distance_km", 0) or 0)
            activity_counts[activity] = activity_counts.get(activity, 0) + 1
            location_counts[location] = location_counts.get(location, 0) + 1
            transport_counts[mode] = transport_counts.get(mode, 0) + 1
            distance_by_agent[agent_id] = round(distance_by_agent.get(agent_id, 0.0) + distance, 4)

    def top_items(mapping, limit=12):
        return [
            {"name": str(name), "value": value}
            for name, value in sorted(mapping.items(), key=lambda item: item[1], reverse=True)[:limit]
        ]

    return {
        "frame_count": len(frames),
        "day_count": len(days),
        "agent_count": len(agents),
        "activity_counts": top_items(activity_counts),
        "location_counts": top_items(location_counts),
        "transport_counts": top_items(transport_counts),
        "distance_by_agent": [
            {"agent_id": agent_id, "name": agents.get(agent_id, f"Agent {agent_id}"), "value": value}
            for agent_id, value in sorted(distance_by_agent.items())
        ],
        "is_demo": not bool(frames),
    }


def _life_events_payload():
    return {
        "templates": list_life_event_templates(),
        "events": list_life_events(CONFIG, include_consumed=True),
    }


def _add_life_event(payload):
    event = add_life_event(payload, CONFIG, current_frame=_current_trace_frame())
    return {
        "event": event,
        "events": list_life_events(CONFIG, include_consumed=True),
    }


class DashboardHandler(SimpleHTTPRequestHandler):
    server_version = "GAWorldDashboard/0.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=REPO_ROOT, **kwargs)

    def _json_response(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw.strip() else {}

    def _handle_api_get(self, path, query):
        if path == "/api/config":
            return self._json_response(_config_summary())
        if path == "/api/agents":
            return self._json_response({"agents": _agents_summary()})
        if path.startswith("/api/agents/") and path.endswith("/profile"):
            agent_id = path.split("/")[3]
            profile = _agent_profile(agent_id)
            if not profile:
                return self._json_response({"error": "Profile not found"}, status=404)
            return self._json_response(profile)
        if path.startswith("/api/agents/") and path.endswith("/memory"):
            agent_id = path.split("/")[3]
            return self._json_response(_memory_payload(agent_id))
        if path == "/api/run/status":
            return self._json_response(_run_status())
        if path == "/api/trace/meta":
            return self._json_response(_latest_trace_meta())
        if path == "/api/life-events":
            return self._json_response(_life_events_payload())
        if path == "/api/metrics/state":
            return self._json_response(_metrics_state())
        if path == "/api/metrics/economy/daily":
            return self._json_response(_metrics_economy_daily())
        if path == "/api/metrics/economy/wealth":
            return self._json_response(_metrics_economy_wealth())
        if path == "/api/metrics/macro":
            return self._json_response(_metrics_macro())
        if path == "/api/metrics/intervention":
            return self._json_response(_metrics_intervention())
        if path.startswith("/api/metrics/locations/"):
            agent_id = path.split("/")[-1]
            return self._json_response(_metrics_location(agent_id))
        if path.startswith("/api/metrics/episodes/"):
            agent_id = path.split("/")[-1]
            return self._json_response(_metrics_episodes(agent_id))
        if path.startswith("/api/metrics/step-time-map/"):
            agent_id = path.split("/")[-1]
            return self._json_response(_metrics_step_time_map(agent_id))
        if path.startswith("/api/metrics/relationships/"):
            agent_id = path.split("/")[-1]
            return self._json_response(_metrics_relationships(agent_id))
        if path == "/api/metrics/social-network":
            return self._json_response(_metrics_social_network())
        if path == "/api/metrics/work-market":
            return self._json_response(_metrics_work_market())
        if path.startswith("/api/metrics/location-history/"):
            agent_id = path.split("/")[-1]
            return self._json_response(_metrics_location_history(agent_id))
        if path.startswith("/api/metrics/daily-timeline/"):
            agent_id = path.split("/")[-1]
            return self._json_response(_metrics_daily_timeline(agent_id))
        if path == "/api/metrics/activity-summary":
            return self._json_response(_metrics_activity_summary())
        return self._json_response({"error": "Unknown endpoint"}, status=404)

    def _handle_api_post(self, path):
        payload = self._read_json_body()
        if path == "/api/config":
            return self._json_response(_save_config_patch(payload))
        if path.startswith("/api/agents/") and path.endswith("/profile"):
            agent_id = path.split("/")[3]
            return self._json_response(_save_agent_profile(agent_id, payload.get("text", "")))
        if path == "/api/run/start":
            return self._json_response(_start_simulation(payload))
        if path == "/api/run/stop":
            return self._json_response(_stop_simulation())
        if path == "/api/interview":
            return self._json_response(_interview_agent(payload))
        if path == "/api/life-events":
            return self._json_response(_add_life_event(payload))
        return self._json_response({"error": "Unknown endpoint"}, status=404)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path.startswith("/api/"):
            try:
                return self._handle_api_get(path, parse_qs(parsed.query))
            except Exception as exc:
                # HTTP boundary: log the full traceback and surface a 500.
                _LOG.exception("GET %s failed: %s", path, exc)
                return self._json_response({"error": str(exc)}, status=500)
        if path in ("/", "/dashboard", "/dashboard/"):
            self.path = "/site/dashboard/index.html"
        return super().do_GET()

    def do_HEAD(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path in ("/", "/dashboard", "/dashboard/"):
            self.path = "/site/dashboard/index.html"
        return super().do_HEAD()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if not path.startswith("/api/"):
            return self._json_response({"error": "POST is only supported under /api"}, status=404)
        try:
            return self._handle_api_post(path)
        except Exception as exc:
            # HTTP boundary: log the full traceback and surface a 500.
            _LOG.exception("POST %s failed: %s", path, exc)
            return self._json_response({"error": str(exc)}, status=500)


def run_server(host="127.0.0.1", port=8766):
    server = ThreadingHTTPServer((host, int(port)), DashboardHandler)
    url = f"http://{host}:{int(port)}/dashboard"
    print(f"GAWorld dashboard: {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _stop_simulation()
        server.server_close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Serve the GAWorld local dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)
