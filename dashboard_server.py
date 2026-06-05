import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from copy import deepcopy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from urllib.parse import parse_qs, unquote, urlparse

from config import CONFIG
from life_events import add_life_event, list_life_event_templates, list_life_events
from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.dashboard")


REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_ROOT = os.path.join(REPO_ROOT, "site", "dashboard")
DASHBOARD_CONFIG_PATH = os.path.join(REPO_ROOT, "dashboard_config.json")
PROFILE_PATH = os.path.join(REPO_ROOT, CONFIG.get("md_path", "hangzhou_profiles_with_names.md"))
RUN_LOG_PATH = os.path.join(REPO_ROOT, "output", "dashboard", "simulation_run.log")
TODO_BOARD_PATH = os.path.join(REPO_ROOT, "output", "dashboard", "todo_board.json")
TEST_LOG_DIR = os.path.join(REPO_ROOT, "output", "test-logs")
TEST_LATEST_LOG_PATH = os.path.join(TEST_LOG_DIR, "latest.log")
PROFILE_HEADER_RE = re.compile(r"^## Profile\s+(\d+)\s*[｜|]\s*(.+?)\s*$", re.MULTILINE)
PYTEST_SUMMARY_RE = re.compile(
    r"(?P<passed>\d+)\s+passed(?:,\s+(?P<skipped>\d+)\s+skipped)?(?:,\s+(?P<failed>\d+)\s+failed)?",
    re.IGNORECASE,
)
TODO_LOCK = threading.RLock()

RUN_STATE = {
    "process": None,
    "started_at": None,
    "log_path": RUN_LOG_PATH,
}


def _simulator_env(extra=None):
    env = os.environ.copy()
    pythonpath_items = [REPO_ROOT]
    existing_pythonpath = str(env.get("PYTHONPATH", "")).strip()
    if existing_pythonpath:
        pythonpath_items.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_items)
    env.setdefault("MPLCONFIGDIR", "/private/tmp")
    env.setdefault("XDG_CACHE_HOME", "/private/tmp")
    if isinstance(extra, dict):
        for key, value in extra.items():
            env[str(key)] = str(value)
    return env


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


def _todo_board_payload():
    with TODO_LOCK:
        payload = _read_json_file(TODO_BOARD_PATH, {"items": []})
        if isinstance(payload, list):
            payload = {"items": payload}
        if not isinstance(payload, dict):
            payload = {"items": []}
        items = payload.get("items", [])
        return {"items": items if isinstance(items, list) else []}


def _save_todo_board(items):
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    with TODO_LOCK:
        payload = {
            "items": items,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        _atomic_write_json(TODO_BOARD_PATH, payload)
        return {"ok": True, **payload}


def _normalize_todo_item(payload, existing=None):
    item = dict(existing or {})
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if not item.get("id"):
        item["id"] = str(uuid.uuid4())
        item["createdAt"] = now
    for key in ("title", "proposer", "details", "priority", "status", "owner"):
        if key in payload:
            item[key] = str(payload.get(key, "")).strip()
    item.setdefault("priority", "medium")
    item.setdefault("status", "pending")
    item.setdefault("owner", "")
    item.setdefault("createdAt", now)
    item["updatedAt"] = now
    if not item.get("title") or not item.get("proposer") or not item.get("details"):
        raise ValueError("title, proposer and details are required")
    return item


def _create_todo_item(payload):
    with TODO_LOCK:
        board = _todo_board_payload()
        item = _normalize_todo_item(payload)
        board["items"].insert(0, item)
        return _save_todo_board(board["items"])


def _update_todo_item(payload):
    item_id = str(payload.get("id", "")).strip()
    if not item_id:
        raise ValueError("id is required")
    with TODO_LOCK:
        board = _todo_board_payload()
        for index, item in enumerate(board["items"]):
            if str(item.get("id")) == item_id:
                board["items"][index] = _normalize_todo_item(payload, existing=item)
                return _save_todo_board(board["items"])
    raise ValueError(f"todo item {item_id} not found")


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


def _test_status_payload():
    log_path = TEST_LATEST_LOG_PATH
    resolved_path = os.path.realpath(log_path) if os.path.exists(log_path) else ""
    log_tail = _tail_text(log_path, max_chars=24000)
    summary = {
        "passed": 0,
        "skipped": 0,
        "failed": 0,
        "status": "unknown",
        "line": "",
    }
    for line in reversed(log_tail.splitlines()):
        if " passed" in line and "===" in line:
            match = PYTEST_SUMMARY_RE.search(line)
            if match:
                summary = {
                    "passed": int(match.group("passed") or 0),
                    "skipped": int(match.group("skipped") or 0),
                    "failed": int(match.group("failed") or 0),
                    "status": "passing" if int(match.group("failed") or 0) == 0 else "failing",
                    "line": line.strip("= ").strip(),
                }
                break
        if " failed" in line and "===" in line:
            summary["status"] = "failing"
            summary["line"] = line.strip("= ").strip()
            break
    latest_mtime = os.path.getmtime(log_path) if os.path.exists(log_path) else 0
    return {
        "service": "gaworld-test-loop.service",
        "branch": os.environ.get("TEST_BRANCH", "tf"),
        "log_path": log_path,
        "resolved_log_path": resolved_path,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(latest_mtime)) if latest_mtime else "",
        "summary": summary,
        "log_tail": log_tail,
    }


def _memory_payload(agent_id):
    memory_dir = _effective_config().get("memory_dir", "output/memory")
    base = os.path.join(REPO_ROOT, memory_dir)
    memory = _read_json_file(os.path.join(base, f"agent_{agent_id}.json"), [])
    schedule = _read_json_file(os.path.join(base, f"agent_{agent_id}_schedule.json"), {})
    habits = _read_json_file(os.path.join(base, f"agent_{agent_id}_habits.json"), {})
    intentions = _read_json_file(os.path.join(base, f"agent_{agent_id}_intentions.json"), {})
    twin_state = _read_json_file(os.path.join(base, f"agent_{agent_id}_twin_state.json"), {})
    episodes = _tail_text(os.path.join(base, f"agent_{agent_id}_episodes.jsonl"), max_chars=24000)
    log_text = _tail_text(os.path.join(REPO_ROOT, "output", "logs", f"agent_{agent_id}.log"), max_chars=24000)
    return {
        "memory": memory,
        "schedule": schedule,
        "habits": habits,
        "intentions": intentions,
        "twin_state": twin_state,
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
    env = _simulator_env({"PYTHONUNBUFFERED": "1"})
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
        env=_simulator_env(),
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


def _run_personal_what_if(payload):
    agent_id = int(payload.get("agent_id"))
    question = str(payload.get("question", "")).strip()
    if agent_id <= 0 or not question:
        raise ValueError("agent_id and question are required")
    command = [
        sys.executable,
        os.path.join(REPO_ROOT, "generative_city_sim.py"),
        "personal-what-if",
        "--agent-id",
        str(agent_id),
        "--question",
        question,
    ]
    if payload.get("scenario_title"):
        command.extend(["--scenario-title", str(payload["scenario_title"]).strip()])
    if payload.get("event_day") is not None:
        command.extend(["--event-day", str(int(payload.get("event_day", 1)))])
    if payload.get("event_time"):
        command.extend(["--event-time", str(payload.get("event_time")).strip()])
    if payload.get("sim_days") is not None:
        command.extend(["--sim-days", str(int(payload.get("sim_days", 2)))])
    if payload.get("llm_provider"):
        command.extend(["--llm-provider", str(payload.get("llm_provider")).strip()])
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=_simulator_env(),
        capture_output=True,
        text=True,
        timeout=int(payload.get("timeout", 1800)),
    )
    output = {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    for line in result.stdout.splitlines():
        if line.startswith("输出目录:"):
            output["output_root"] = line.split(":", 1)[1].strip()
        elif line.startswith("个人报告:"):
            output["personal_report"] = line.split(":", 1)[1].strip()
        elif line.startswith("通用报告:"):
            output["comparison_report"] = line.split(":", 1)[1].strip()
    return output


def _distributed_social_payload():
    cfg = _effective_config()
    distributed_cfg = cfg.get("distributed", {}) if isinstance(cfg.get("distributed"), dict) else {}
    relay_cfg = distributed_cfg.get("relay", {}) if isinstance(distributed_cfg.get("relay"), dict) else {}
    base_url = str(relay_cfg.get("base_url", "http://127.0.0.1:8877")).rstrip("/")
    cluster = str(distributed_cfg.get("cluster", "default")).strip() or "default"
    personal_twin_cfg = cfg.get("personal_twin", {}) if isinstance(cfg.get("personal_twin"), dict) else {}
    result = {
        "enabled": bool(distributed_cfg.get("enabled", False)),
        "cluster": cluster,
        "relay_base_url": base_url,
        "personal_twin": {
            "enabled": bool(personal_twin_cfg.get("enabled", False)),
            "local_first": bool(personal_twin_cfg.get("local_first", False)),
            "share_social_summaries": bool(personal_twin_cfg.get("share_social_summaries", False)),
            "what_if_enabled": bool(personal_twin_cfg.get("what_if_enabled", False)),
        },
    }
    if not result["enabled"]:
        result["snapshot"] = {}
        result["error"] = "distributed mode disabled"
        return result
    url = f"{base_url}/social/snapshot?cluster={cluster}&limit=18"
    try:
        with urlopen(url, timeout=2.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result["snapshot"] = payload if isinstance(payload, dict) else {}
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        result["snapshot"] = {}
        result["error"] = str(exc)
    return result


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

    def _read_form_body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw, keep_blank_values=True)
        return {key: values[0] if values else "" for key, values in parsed.items()}

    def _redirect(self, location, status=303):
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

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
        if path == "/api/todos":
            return self._json_response(_todo_board_payload())
        if path == "/api/tests/status":
            return self._json_response(_test_status_payload())
        if path == "/api/distributed/social":
            return self._json_response(_distributed_social_payload())
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
        if path == "/api/todos":
            return self._json_response(_save_todo_board(payload.get("items", [])))
        if path == "/api/todos/create":
            return self._json_response(_create_todo_item(payload))
        if path == "/api/todos/update":
            return self._json_response(_update_todo_item(payload))
        if path == "/api/todos/clear":
            return self._json_response(_save_todo_board([]))
        if path == "/api/personal-what-if":
            return self._json_response(_run_personal_what_if(payload))
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
        elif path in ("/board", "/board/", "/todo", "/todo/"):
            self.path = "/todo_board.html"
        elif path in ("/tests", "/tests/"):
            self.path = "/site/tests/index.html"
        return super().do_GET()

    def do_HEAD(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path in ("/", "/dashboard", "/dashboard/"):
            self.path = "/site/dashboard/index.html"
        elif path in ("/board", "/board/", "/todo", "/todo/"):
            self.path = "/todo_board.html"
        elif path in ("/tests", "/tests/"):
            self.path = "/site/tests/index.html"
        return super().do_HEAD()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/todos/create-form":
            try:
                _create_todo_item(self._read_form_body())
                return self._redirect("/board")
            except Exception as exc:
                _LOG.exception("POST %s failed: %s", path, exc)
                return self._json_response({"error": str(exc)}, status=400)
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
