import csv
import datetime
import json
import os
import re
import subprocess
import sys
import time
from copy import deepcopy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from config import CONFIG
from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.dashboard")


REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_ROOT = os.path.join(REPO_ROOT, "site", "dashboard")
DASHBOARD_CONFIG_PATH = os.path.join(REPO_ROOT, "dashboard_config.json")
PROFILE_PATH = os.path.join(REPO_ROOT, CONFIG.get("md_path", "hangzhou_profiles_with_names.md"))
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


def _read_csv_file(path, default=None):
    if not os.path.exists(path):
        return [] if default is None else default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except (OSError, csv.Error):
        return [] if default is None else default


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


def _economy_payload(agent_id):
    memory_dir = _effective_config().get("memory_dir", "output/memory")
    path = os.path.join(REPO_ROOT, memory_dir, f"agent_{agent_id}_economy.json")
    data = _read_json_file(path, {})
    if not data:
        return {"agent_id": int(agent_id), "error": "Economy data not found"}
    return {"agent_id": int(agent_id), "economy": data}


def _economy_history_payload(agent_id):
    cfg = _effective_config()
    output_dir = cfg.get("economy_output_dir", "output/economy")
    path = os.path.join(REPO_ROOT, output_dir, "agents", f"agent_{agent_id}_ledger.csv")
    rows = _read_csv_file(path)
    if not rows:
        return {"agent_id": int(agent_id), "history": []}
    for row in rows:
        for key in ("day", "income", "expense", "net", "balance"):
            if key in row:
                try:
                    row[key] = float(row[key]) if "." in str(row[key]) else int(row[key])
                except (ValueError, TypeError):
                    row[key] = 0 if key == "day" else 0.0
    return {"agent_id": int(agent_id), "history": rows}


def _batch_memory_state_payload(agent_ids):
    if not agent_ids:
        return {"agents": []}
    memory_dir = _effective_config().get("memory_dir", "output/memory")
    results = []
    _, sections = _profile_sections()
    name_map = {str(s["id"]): s["name"] for s in sections}
    for agent_id in agent_ids:
        path = os.path.join(REPO_ROOT, memory_dir, f"agent_{agent_id}.json")
        memory = _read_json_file(path, [])
        agent_state = None
        if isinstance(memory, list) and memory:
            last = memory[-1]
            agent_state = last.get("state") if isinstance(last, dict) else None
        results.append({
            "agent_id": int(agent_id),
            "name": name_map.get(str(agent_id), str(agent_id)),
            "state": agent_state if isinstance(agent_state, dict) else {},
        })
    return {"agents": results}


def _state_history_latest_payload():
    path = os.path.join(REPO_ROOT, "output", "state", "agent_state_history.csv")
    rows = _read_csv_file(path)
    if not rows:
        return {"agents": {}}
    latest = {}
    for row in rows:
        agent_id = row.get("agent_id")
        metric = row.get("metric")
        value = row.get("value")
        if not agent_id or not metric or value is None:
            continue
        agent_key = str(agent_id)
        if agent_key not in latest:
            latest[agent_key] = {}
        try:
            current = float(value)
        except (ValueError, TypeError):
            continue
        latest[agent_key][metric] = current
    return {"agents": latest}


def _performance_payload():
    cfg = _effective_config()
    agent_ids = cfg.get("agent_ids", [])
    sim_days = cfg.get("sim_days", 0)

    started_at = RUN_STATE.get("started_at")
    duration_seconds = None
    if started_at:
        try:
            start = datetime.datetime.strptime(started_at, "%Y-%m-%d %H:%M:%S")
            duration_seconds = (datetime.datetime.now() - start).total_seconds()
        except (ValueError, TypeError):
            pass

    log_path = RUN_STATE.get("log_path", RUN_LOG_PATH)
    log_size_bytes = 0
    log_line_count = 0
    if os.path.exists(log_path):
        log_size_bytes = os.path.getsize(log_path)
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                log_line_count = sum(1 for _ in f)
        except OSError:
            pass

    day_count = 0
    if os.path.exists(RUN_LOG_PATH):
        try:
            with open(RUN_LOG_PATH, "r", encoding="utf-8") as f:
                content = f.read()
            day_count = len(re.findall(r"Day \d+", content))
        except OSError:
            pass

    return {
        "agent_count": len(agent_ids),
        "sim_days": sim_days,
        "days_completed": day_count if day_count > 0 else None,
        "duration_seconds": duration_seconds,
        "log_size_bytes": log_size_bytes,
        "log_line_count": log_line_count,
        "started_at": started_at,
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
        if path == "/api/agents/memory/batch":
            ids_str = query.get("ids", [""])[0]
            agent_ids = [int(x.strip()) for x in ids_str.split(",") if x.strip()]
            return self._json_response(_batch_memory_state_payload(agent_ids))
        if path.startswith("/api/agents/") and path.endswith("/memory"):
            agent_id = path.split("/")[3]
            return self._json_response(_memory_payload(agent_id))
        if path == "/api/run/status":
            return self._json_response(_run_status())
        if path == "/api/run/performance":
            return self._json_response(_performance_payload())
        if path == "/api/trace/meta":
            return self._json_response(_latest_trace_meta())
        if path == "/api/state-history/latest":
            return self._json_response(_state_history_latest_payload())
        if path.startswith("/api/economy/") and path.endswith("/history"):
            agent_id = path.split("/")[3]
            return self._json_response(_economy_history_payload(agent_id))
        if path.startswith("/api/economy/") and len(path.split("/")) == 4:
            agent_id = path.split("/")[3]
            return self._json_response(_economy_payload(agent_id))
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
