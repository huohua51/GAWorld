import atexit
import csv
import json
import os
import re
import subprocess
import sys
import threading
import time
from copy import deepcopy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gaworld.settings import CONFIG
from gaworld.events.life import add_life_event, list_life_event_templates, list_life_events
from gaworld.integrations.fos_prompt import generate_fos_prompt
from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.dashboard")


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DASHBOARD_ROOT = os.path.join(REPO_ROOT, "site", "dashboard")
DASHBOARD_CONFIG_PATH = os.path.join(REPO_ROOT, "dashboard_config.json")
PROFILE_PATH = os.path.join(REPO_ROOT, CONFIG.get("md_path", "data/hangzhou_profiles_with_names.md"))
STATE_CSV_PATH = os.path.join(REPO_ROOT, CONFIG.get("csv_path", "data/hangzhou_agents_state_init.csv"))
ECONOMY_SNAPSHOT_PATH = os.path.join(REPO_ROOT, "output", "economy", "wealth_snapshot.csv")
SKILLS_DIR = os.path.join(REPO_ROOT, CONFIG.get("skills", {}).get("global_dir", "data/skills"))
CAPABILITIES_CACHE_PATH = os.path.join(
    REPO_ROOT, CONFIG.get("real_work", {}).get("capabilities_cache", "output/work/capabilities.json")
)
RELAY_STATE_PATH = os.path.join(
    REPO_ROOT,
    CONFIG.get("distributed", {}).get("server", {}).get("state_path", "output/distributed/relay_state.json"),
)
RUN_LOG_PATH = os.path.join(REPO_ROOT, "output", "dashboard", "simulation_run.log")
PROFILE_HEADER_RE = re.compile(r"^## Profile\s+(\d+)\s*[｜|]\s*(.+?)\s*$", re.MULTILINE)

# The nine normalized [0,1] state variables that seed each agent. Order matters
# only for display; the CSV column order is preserved on write regardless.
STATE_VAR_KEYS = (
    "emotion",
    "stress",
    "econ_security",
    "city_identity",
    "policy_sensitivity",
    "platform_dependence",
    "risk_preference",
    "voice_propensity",
    "mobility_intent",
)

RUN_STATE = {
    "process": None,
    "started_at": None,
    "log_path": RUN_LOG_PATH,
}

_COLLABORATION_SERVICE = None
_COLLABORATION_LOCK = threading.Lock()


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


def _repo_path(value):
    path = Path(str(value))
    if path.is_absolute():
        return path.resolve()
    return (Path(REPO_ROOT) / path).resolve()


def _collaboration_config():
    config = _effective_config().get("collaboration", {})
    return config if isinstance(config, dict) else {}


def _get_collaboration_service():
    global _COLLABORATION_SERVICE
    with _COLLABORATION_LOCK:
        if _COLLABORATION_SERVICE is not None:
            return _COLLABORATION_SERVICE

        from gaworld.collaboration.service import CollaborationService
        from gaworld.llm.providers import call_llm
        from gaworld.memory.experience import append_agent_episode

        config = _effective_config()
        collaboration = config.get("collaboration", {})
        if not isinstance(collaboration, dict):
            collaboration = {}
        service = CollaborationService(
            config=collaboration,
            sessions_dir=_repo_path(
                collaboration.get(
                    "sessions_dir",
                    "output/collaboration/sessions",
                )
            ),
            memory_dir=_repo_path(
                config.get("memory_dir", "output/memory")
            ),
            agent_loader=lambda agent_id: _agent_detail(int(agent_id)),
            llm=call_llm,
            episode_writer=lambda agent_id, episode: append_agent_episode(
                agent_id,
                episode,
                cfg=config,
            ),
        )
        service.start()
        _COLLABORATION_SERVICE = service
        return service


def _reset_collaboration_service_for_tests():
    global _COLLABORATION_SERVICE
    with _COLLABORATION_LOCK:
        service = _COLLABORATION_SERVICE
        _COLLABORATION_SERVICE = None
    if service is not None:
        service.shutdown()


def _public_collaboration_session(payload):
    result = deepcopy(payload)
    result.pop("artifact_base_url", None)

    repo_root = Path(REPO_ROOT).resolve()
    collaboration = _collaboration_config()
    sessions_dir = _repo_path(
        collaboration.get(
            "sessions_dir",
            "output/collaboration/sessions",
        )
    )
    session_id = str(result.get("id") or "")
    safe_session_id = bool(
        session_id
        and session_id not in {".", ".."}
        and "/" not in session_id
        and "\\" not in session_id
        and all(
            ord(character) >= 32 and ord(character) != 127
            for character in session_id
        )
    )
    session_root = sessions_dir
    session_root_is_safe = False
    if safe_session_id:
        session_root = (sessions_dir / session_id).resolve()
        try:
            session_root.relative_to(sessions_dir)
        except ValueError:
            pass
        else:
            session_root_is_safe = True

    artifacts_root = (session_root / "artifacts").resolve()
    if session_root_is_safe:
        try:
            public_artifacts_root = artifacts_root.relative_to(repo_root)
        except ValueError:
            pass
        else:
            result["artifact_base_url"] = (
                "/" + public_artifacts_root.as_posix().rstrip("/") + "/"
            )

    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list):
        return result

    public_artifacts = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        public_artifacts.append(artifact)
        artifact.pop("url", None)
        raw_path = str(artifact.get("path") or "")
        relative = Path(raw_path)
        if not raw_path or relative.is_absolute() or not session_root_is_safe:
            artifact.pop("path", None)
            continue
        resolved = (session_root / relative).resolve()
        try:
            resolved.relative_to(session_root)
        except ValueError:
            artifact.pop("path", None)
            continue
        try:
            public_path = resolved.relative_to(repo_root)
        except ValueError:
            continue
        artifact["url"] = "/" + public_path.as_posix()
    result["artifacts"] = public_artifacts
    return result


def _collaboration_agent_ids(payload):
    values = payload.get("agent_ids")
    if not isinstance(values, list):
        raise ValueError("agent_ids must be an array of integers")
    agent_ids = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("agent_ids must be an array of integers")
        agent_ids.append(value)
    return agent_ids


def _collaboration_integer(
    payload,
    field,
    *,
    default=None,
    allow_none=False,
):
    value = payload.get(field, default)
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{field} must be an integer")
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{field} must be an integer")
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an integer") from exc


def _collaboration_roles(payload):
    roles = payload.get("role_overrides")
    if roles is None:
        return None
    if not isinstance(roles, dict):
        raise ValueError("role_overrides must be an object")
    normalized = {}
    for agent_id, role in roles.items():
        if (
            isinstance(agent_id, bool)
            or not isinstance(agent_id, (int, str))
            or not isinstance(role, str)
        ):
            raise ValueError(
                "role_overrides must map agent ids to role strings"
            )
        try:
            normalized[str(int(agent_id))] = role
        except ValueError as exc:
            raise ValueError(
                "role_overrides must map agent ids to role strings"
            ) from exc
    return normalized


def _collaboration_text(payload, field, *, default=""):
    value = payload.get(field, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value


atexit.register(_reset_collaboration_service_for_tests)


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


# ---------------------------------------------------------------------------
# Agent state (CSV seed) read / write, skills, finance, and agent creation.
# The CSV is the machine-readable seed the simulator loads; the Markdown
# profile is the narrative twin. Studio edits go to the CSV for state vars and
# to the profile block for narrative, mirroring how imported agents are stored.
# ---------------------------------------------------------------------------

def _read_state_rows():
    if not os.path.exists(STATE_CSV_PATH):
        return [], []
    with open(STATE_CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def _row_id(row):
    try:
        return int(float(row.get("id")))
    except (TypeError, ValueError):
        return None


def _num(value, default=0.5):
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return default


def _state_row_to_payload(row):
    try:
        age = int(float(row.get("age")))
    except (TypeError, ValueError):
        age = None
    return {
        "id": _row_id(row),
        "name": (row.get("name") or "").strip(),
        "gender": (row.get("gender") or "").strip(),
        "age": age,
        "hukou": (row.get("hukou") or "").strip(),
        "residence": (row.get("residence") or "").strip(),
        "state": {key: _num(row.get(key)) for key in STATE_VAR_KEYS},
    }


def _agent_state(agent_id):
    _, rows = _read_state_rows()
    for row in rows:
        if _row_id(row) == int(agent_id):
            return _state_row_to_payload(row)
    return None


def _atomic_write_state(fieldnames, rows):
    tmp_path = STATE_CSV_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    os.replace(tmp_path, STATE_CSV_PATH)


def _save_agent_state(agent_id, payload):
    fieldnames, rows = _read_state_rows()
    if not fieldnames:
        raise ValueError("State CSV is missing or empty")
    target = next((row for row in rows if _row_id(row) == int(agent_id)), None)
    if target is None:
        raise ValueError(f"Agent {agent_id} not found in state CSV")
    for key in ("name", "gender", "hukou", "residence"):
        if payload.get(key) not in (None, ""):
            target[key] = str(payload[key])
    if payload.get("age") not in (None, ""):
        target["age"] = str(int(payload["age"]))
    incoming = payload.get("state") or {}
    for key in STATE_VAR_KEYS:
        if incoming.get(key) is not None:
            target[key] = round(max(0.0, min(1.0, float(incoming[key]))), 4)
    _atomic_write_state(fieldnames, rows)
    result = _agent_state(agent_id)
    try:
        _sync_profile_state_lines(agent_id, result["state"])
    except Exception:  # noqa: BLE001 - narrative sync is best-effort, never blocks the CSV write
        _LOG.exception("profile state sync failed for agent %s", agent_id)
    return result


def _sync_profile_state_lines(agent_id, state):
    """Mirror the CSV state onto the profile Markdown so the two don't drift.

    The CSV is authoritative. This rewrites only the two structured lines a
    profile block carries — the ``**研究增强变量初始化**`` bullets and the
    ``**核心状态变量**`` summary — leaving all narrative prose untouched. If a
    profile lacks those lines, nothing is changed.
    """
    section = _agent_profile(agent_id)
    if not section:
        return
    text = section["text"]
    core = (
        f"**核心状态变量**：emotion {state['emotion']:.2f}｜stress {state['stress']:.2f}｜"
        f"econ_security {state['econ_security']:.2f}｜city_identity {state['city_identity']:.2f}"
    )
    new_text = re.sub(r"\*\*核心状态变量\*\*：.*", core, text)
    for key in ("policy_sensitivity", "platform_dependence", "risk_preference", "voice_propensity", "mobility_intent"):
        new_text = re.sub(rf"^- {key}：.*$", f"- {key}：{state[key]:.2f}", new_text, flags=re.MULTILINE)
    if new_text != text:
        _save_agent_profile(agent_id, new_text)


def _social_snapshot(agent_id):
    memory_dir = _effective_config().get("memory_dir", "output/memory")
    path = os.path.join(REPO_ROOT, memory_dir, f"agent_{agent_id}_relationships.json")
    rels = _read_json_file(path, {})
    if not isinstance(rels, dict) or not rels:
        return None
    tier_counts = {"inner": 0, "close": 0, "acquaintance": 0, "weak": 0}
    relations = []
    for key, item in rels.items():
        if not isinstance(item, dict):
            continue
        tier = item.get("dunbar_tier") or ""
        if tier in tier_counts:
            tier_counts[tier] += 1
        profile = item.get("profile") if isinstance(item.get("profile"), dict) else {}
        relations.append({
            "id": key,
            "name": profile.get("name") or str(key),
            "role": item.get("role") or "",
            "kind": item.get("kind") or "agent",
            "tier": tier,
            "closeness": _num(item.get("closeness"), 0.0),
            "trust": _num(item.get("trust"), 0.0),
        })
    relations.sort(key=lambda r: r["closeness"], reverse=True)
    return {"count": len(relations), "tier_counts": tier_counts, "relations": relations[:40]}


def _scan_skill_dir(directory):
    items = []
    if os.path.isdir(directory):
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".md"):
                continue
            title = name[:-3]
            try:
                with open(os.path.join(directory, name), "r", encoding="utf-8") as f:
                    for line in f:
                        stripped = line.strip()
                        if stripped.startswith("#"):
                            title = stripped.lstrip("#").strip() or title
                            break
            except OSError:
                pass
            items.append({"file": name, "title": title})
    return items


def _skills_library():
    return _scan_skill_dir(SKILLS_DIR)


def _private_skills(agent_id):
    # Mirrors SkillRegistry._private_dir: {memory_dir}/agent_{id}_skills
    memory_dir = _effective_config().get("memory_dir", "output/memory")
    return _scan_skill_dir(os.path.join(REPO_ROOT, memory_dir, f"agent_{int(agent_id)}_skills"))


def _capabilities_snapshot(agent_id):
    data = _read_json_file(CAPABILITIES_CACHE_PATH, {})
    if not isinstance(data, dict):
        return None
    entry = data.get(str(int(agent_id)))
    return entry if isinstance(entry, dict) else None


def _rag_snapshot(memory_items):
    # External-RAG memories are tagged with the [额外信息…] prefix (gaworld/sim/_rag.py).
    items = []
    for item in memory_items if isinstance(memory_items, list) else []:
        text = str(item).strip()
        if text.startswith("[额外信息"):
            items.append(text[:300])
    return {"count": len(items), "items": items[:20]}


def _growth_snapshot(agent_id):
    from gaworld.interests import load_agent_growth_profile

    memory_dir = os.path.join(REPO_ROOT, _effective_config().get("memory_dir", "output/memory"))
    profile = load_agent_growth_profile(int(agent_id), memory_dir)
    return profile or None


def _openclaw_snapshot(agent_id):
    cfg = CONFIG.get("openclaw", {}) or {}
    state = _read_json_file(RELAY_STATE_PATH, {})
    directory = state.get("directory") if isinstance(state, dict) else {}
    directory = directory if isinstance(directory, dict) else {}

    entry = None
    openclaw_ids = set()
    for cluster, cluster_map in directory.items():
        if not isinstance(cluster_map, dict):
            continue
        for aid, item in cluster_map.items():
            if not isinstance(item, dict):
                continue
            if item.get("agent_type") == "openclaw":
                openclaw_ids.add(str(aid))
            if str(aid) == str(int(agent_id)) and entry is None:
                entry = {**item, "cluster": cluster}

    sent = received = 0
    messages = state.get("messages") if isinstance(state, dict) else []
    for msg in messages if isinstance(messages, list) else []:
        if not isinstance(msg, dict):
            continue
        frm, to = str(msg.get("from_agent")), str(msg.get("to_agent"))
        if frm == str(int(agent_id)) and to in openclaw_ids:
            sent += 1
        elif to == str(int(agent_id)) and frm in openclaw_ids:
            received += 1

    is_openclaw = bool(entry and entry.get("agent_type") == "openclaw")
    return {
        "enabled": bool(cfg.get("enabled")),
        "registered": entry is not None,
        "is_openclaw_agent": is_openclaw,
        "cluster": entry.get("cluster") if entry else None,
        "node_id": entry.get("node_id") if entry else None,
        "messages_sent": sent,
        "messages_received": received,
        "connected": is_openclaw or (sent + received) > 0,
    }


def _cognition_snapshot(capabilities, growth, memory_counts, rag):
    """Derived cognitive index — NOT a measured IQ.

    Transparent composite of what the simulation actually tracks:
    skill breadth, deliverable capacity, growth levels, memory volume,
    and external (RAG) knowledge, mapped onto a familiar 60–140 scale.
    """
    caps = capabilities or {}
    growth_items = (growth or {}).get("items", []) or []
    avg_level = (
        sum(_num(item.get("level"), 0.0) for item in growth_items) / len(growth_items)
        if growth_items else 0.0
    )
    memory_total = sum(v for v in memory_counts.values() if isinstance(v, (int, float)))
    components = {
        "skill_breadth": min(1.0, len(caps.get("skills") or []) / 6.0),
        "deliverable_capacity": min(1.0, len(caps.get("deliverables") or []) / 4.0),
        "growth_level": avg_level,
        "memory_volume": min(1.0, memory_total / 200.0),
        "external_knowledge": min(1.0, rag.get("count", 0) / 10.0),
    }
    weights = {
        "skill_breadth": 0.25,
        "deliverable_capacity": 0.15,
        "growth_level": 0.25,
        "memory_volume": 0.2,
        "external_knowledge": 0.15,
    }
    score01 = sum(components[key] * weights[key] for key in weights)
    return {
        "score": round(60 + score01 * 80),
        "score01": round(score01, 4),
        "components": {key: round(value, 4) for key, value in components.items()},
    }


def _agent_card(identity, capabilities, private_skills, growth, openclaw):
    caps = capabilities or {}
    skills = list(caps.get("skills") or [])
    for skill in private_skills:
        if skill["title"] not in skills:
            skills.append(skill["title"])
    interests = list(caps.get("interests") or [])
    for item in (growth or {}).get("items", []) or []:
        name = item.get("name")
        if name and name not in interests:
            interests.append(name)
    return {
        "schema": "gaworld.agent-card/v1",
        "id": identity["id"],
        "name": identity["name"],
        "description": " · ".join(
            str(part) for part in (identity.get("gender"), f"{identity.get('age')}岁", identity.get("residence")) if part
        ),
        "job_label": caps.get("job_label") or "",
        "skills": skills,
        "interests": interests,
        "deliverables": list(caps.get("deliverables") or []),
        "adapters": list(caps.get("adapter_priority") or []),
        "openclaw_connected": bool(openclaw.get("connected")),
        "endpoints": {
            "detail": f"/api/agents/{identity['id']}/detail",
            "interview": "/api/interview",
        },
    }


def _finance_snapshot(agent_id):
    if not os.path.exists(ECONOMY_SNAPSHOT_PATH):
        return None
    try:
        with open(ECONOMY_SNAPSHOT_PATH, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                try:
                    if int(float(row.get("agent_id"))) == int(agent_id):
                        return dict(row)
                except (TypeError, ValueError):
                    continue
    except OSError:
        return None
    return None


def _agent_detail(agent_id):
    state = _agent_state(agent_id)
    if state is None:
        return None
    profile = _agent_profile(agent_id) or {}
    memory = _memory_payload(agent_id)

    def _count(value):
        return len(value) if isinstance(value, (list, dict)) else 0

    identity = {
        "id": state["id"],
        "name": state["name"],
        "gender": state["gender"],
        "age": state["age"],
        "hukou": state["hukou"],
        "residence": state["residence"],
    }
    memory_counts = {
        "long_term": _count(memory.get("memory")),
        "habits": _count(memory.get("habits")),
        "intentions": _count(memory.get("intentions")),
        "schedule": _count(memory.get("schedule")),
    }
    capabilities = _capabilities_snapshot(agent_id)
    private_skills = _private_skills(agent_id)
    growth = _growth_snapshot(agent_id)
    rag = _rag_snapshot(memory.get("memory"))
    openclaw = _openclaw_snapshot(agent_id)
    return {
        "identity": identity,
        "state": state["state"],
        "profile_text": profile.get("text", ""),
        "memory_counts": memory_counts,
        "finance": _finance_snapshot(agent_id),
        "social": _social_snapshot(agent_id),
        "skills": _skills_library(),
        "private_skills": private_skills,
        "capabilities": capabilities,
        "growth": growth,
        "goals": memory.get("goals", {}),
        "rag": rag,
        "openclaw": openclaw,
        "cognition": _cognition_snapshot(capabilities, growth, memory_counts, rag),
        "agent_card": _agent_card(identity, capabilities, private_skills, growth, openclaw),
    }


def _next_agent_id():
    _, rows = _read_state_rows()
    ids = [rid for rid in (_row_id(row) for row in rows) if rid is not None]
    _, sections = _profile_sections()
    ids.extend(section["id"] for section in sections)
    return (max(ids) + 1) if ids else 1


def _create_agent(payload):
    from gaworld.sim.agents_loader import _clip_state_value, _format_imported_profile_block

    agent_id = _next_agent_id()
    state_in = payload.get("state") or {}
    defaults = {
        "emotion": 0.55,
        "stress": 0.5,
        "econ_security": 0.5,
        "city_identity": 0.5,
        "policy_sensitivity": 0.5,
        "platform_dependence": 0.5,
        "risk_preference": 0.5,
        "voice_propensity": 0.5,
        "mobility_intent": 0.5,
    }
    state = {key: _clip_state_value(state_in.get(key), defaults[key]) for key in STATE_VAR_KEYS}
    profile_payload = {
        "name": str(payload.get("name") or f"新智能体{agent_id}"),
        "gender": str(payload.get("gender") or "未知"),
        "age": int(payload.get("age") or 30),
        "hukou": str(payload.get("hukou") or "未知"),
        "residence": str(payload.get("residence") or "杭州"),
        "job": str(payload.get("job") or "待补充"),
        "personality": str(payload.get("personality") or "待补充"),
        "daily_life": str(payload.get("daily_life") or "待补充"),
        "values": str(payload.get("values") or "待补充"),
        "education_income": str(payload.get("education_income") or "待补充"),
        "social_network": str(payload.get("social_network") or "待补充"),
        "state": state,
    }
    fieldnames, rows = _read_state_rows()
    if not fieldnames:
        raise ValueError("State CSV is missing or empty")
    new_row = {
        "id": agent_id,
        "name": profile_payload["name"],
        "gender": profile_payload["gender"],
        "age": profile_payload["age"],
        "hukou": profile_payload["hukou"],
        "residence": profile_payload["residence"],
    }
    new_row.update({key: state[key] for key in STATE_VAR_KEYS})
    rows.append({key: new_row.get(key, "") for key in fieldnames})
    _atomic_write_state(fieldnames, rows)

    with open(PROFILE_PATH, "a", encoding="utf-8") as f:
        f.write(_format_imported_profile_block(agent_id, profile_payload))

    return {"id": agent_id, "name": profile_payload["name"], "state": _agent_state(agent_id)}


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
    goals = _read_json_file(os.path.join(base, f"agent_{agent_id}_goals.json"), {})
    episodes = _tail_text(os.path.join(base, f"agent_{agent_id}_episodes.jsonl"), max_chars=24000)
    log_text = _tail_text(os.path.join(REPO_ROOT, "output", "logs", f"agent_{agent_id}.log"), max_chars=24000)
    return {
        "memory": memory,
        "schedule": schedule,
        "habits": habits,
        "intentions": intentions,
        "goals": goals,
        "episodes_tail": episodes,
        "log_tail": log_text,
    }


def _agent_goals_payload(agent_id):
    memory_dir = _effective_config().get("memory_dir", "output/memory")
    base = os.path.join(REPO_ROOT, memory_dir)
    return _read_json_file(os.path.join(base, f"agent_{int(agent_id)}_goals.json"), {})


def _save_agent_goals_payload(agent_id, payload):
    from gaworld.goals import normalize_goals

    if not isinstance(payload, dict):
        raise ValueError("goals payload must be a JSON object")
    normalized = normalize_goals(payload, day=int(payload.get("last_review_day", 0) or 0))
    if not normalized:
        raise ValueError("goals payload has no valid goals")
    memory_dir = _effective_config().get("memory_dir", "output/memory")
    base = os.path.join(REPO_ROOT, memory_dir)
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, f"agent_{int(agent_id)}_goals.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    return normalized
    return normalized


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


def _resolve_output_dir(output_dir: str | None) -> str:
    """Resolve the output directory path.

    If ``output_dir`` is empty or None, default to ``output/`` under REPO_ROOT.
    If it's a relative path, resolve it against REPO_ROOT.
    """
    if not output_dir:
        return os.path.join(REPO_ROOT, "output")
    p = Path(output_dir)
    if p.is_absolute():
        return str(p)
    return os.path.join(REPO_ROOT, output_dir)


def _fos_export(payload: dict) -> dict:
    """Handle ``POST /api/fos-export``.

    Reads simulation output from the provided (or default) output directory,
    calls GAWorld's LLM for analysis, and returns a FOS-ready prompt.
    """
    raw_dir = payload.get("output_dir") or ""
    hint = payload.get("hint") or None
    english = bool(payload.get("english", False))

    resolved = _resolve_output_dir(raw_dir)
    result = generate_fos_prompt(
        output_dir=Path(resolved),
        hint=hint,
        english=english,
    )
    return {
        "prompt": result.get("prompt"),
        "summary": result.get("summary"),
        "error": result.get("error"),
    }


class DashboardHandler(SimpleHTTPRequestHandler):
    server_version = "GAWorldDashboard/0.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=REPO_ROOT, **kwargs)

    def end_headers(self):
        # The dashboard JS/CSS and trace JSON change between runs; without
        # this, browsers serve stale assets from memory cache indefinitely.
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

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
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _handle_api_get(self, path, query):
        if path == "/api/config":
            return self._json_response(_config_summary())
        if path == "/api/agents":
            return self._json_response({"agents": _agents_summary()})
        if path == "/api/skills":
            return self._json_response({"skills": _skills_library()})
        if path.startswith("/api/agents/") and path.endswith("/profile"):
            agent_id = path.split("/")[3]
            profile = _agent_profile(agent_id)
            if not profile:
                return self._json_response({"error": "Profile not found"}, status=404)
            return self._json_response(profile)
        if path.startswith("/api/agents/") and path.endswith("/state"):
            agent_id = path.split("/")[3]
            state = _agent_state(agent_id)
            if state is None:
                return self._json_response({"error": "Agent not found"}, status=404)
            return self._json_response(state)
        if path.startswith("/api/agents/") and path.endswith("/detail"):
            agent_id = path.split("/")[3]
            detail = _agent_detail(agent_id)
            if detail is None:
                return self._json_response({"error": "Agent not found"}, status=404)
            return self._json_response(detail)
        if path.startswith("/api/agents/") and path.endswith("/memory"):
            agent_id = path.split("/")[3]
            return self._json_response(_memory_payload(agent_id))
        if path.startswith("/api/agents/") and path.endswith("/goals"):
            agent_id = path.split("/")[3]
            return self._json_response(_agent_goals_payload(agent_id))
        if path == "/api/run/status":
            return self._json_response(_run_status())
        if path == "/api/trace/meta":
            return self._json_response(_latest_trace_meta())
        if path == "/api/life-events":
            return self._json_response(_life_events_payload())
        if path == "/api/collaboration/sessions":
            service = _get_collaboration_service()
            kind = (query.get("kind") or [""])[0]
            status = (query.get("status") or [""])[0]
            sessions = service.list_sessions(
                kind=kind,
                status=status,
            )
            return self._json_response(
                {
                    "sessions": [
                        _public_collaboration_session(item)
                        for item in sessions
                    ],
                    "health": service.health(),
                }
            )
        parts = path.strip("/").split("/")
        if (
            len(parts) == 4
            and parts[:3] == ["api", "collaboration", "sessions"]
        ):
            session = _get_collaboration_service().get_session(parts[3])
            return self._json_response(
                _public_collaboration_session(session)
            )
        if (
            len(parts) == 5
            and parts[:3] == ["api", "collaboration", "sessions"]
            and parts[4] == "events"
        ):
            after = int((query.get("after") or [0])[0])
            events = _get_collaboration_service().events(
                parts[3],
                after=after,
            )
            return self._json_response({"events": events})
        return self._json_response({"error": "Unknown endpoint"}, status=404)

    def _handle_api_post(self, path):
        payload = self._read_json_body()
        if path == "/api/config":
            return self._json_response(_save_config_patch(payload))
        if path == "/api/agents":
            return self._json_response(_create_agent(payload))
        if path.startswith("/api/agents/") and path.endswith("/profile"):
            agent_id = path.split("/")[3]
            return self._json_response(_save_agent_profile(agent_id, payload.get("text", "")))
        if path.startswith("/api/agents/") and path.endswith("/state"):
            agent_id = path.split("/")[3]
            return self._json_response(_save_agent_state(agent_id, payload))
        if path.startswith("/api/agents/") and path.endswith("/goals"):
            agent_id = path.split("/")[3]
            try:
                saved = _save_agent_goals_payload(agent_id, payload)
            except ValueError as exc:
                return self._json_response({"error": str(exc)}, status=400)
            return self._json_response(saved)
        if path == "/api/run/start":
            return self._json_response(_start_simulation(payload))
        if path == "/api/run/stop":
            return self._json_response(_stop_simulation())
        if path == "/api/interview":
            return self._json_response(_interview_agent(payload))
        if path == "/api/life-events":
            return self._json_response(_add_life_event(payload))
        if path == "/api/fos-export":
            return self._json_response(_fos_export(payload))
        if path == "/api/relationships/friends":
            return self._json_response(
                _get_collaboration_service().make_friends(
                    _collaboration_agent_ids(payload)
                )
            )
        if path == "/api/collaboration/sessions":
            service = _get_collaboration_service()
            kind = _collaboration_text(payload, "kind")
            agent_ids = _collaboration_agent_ids(payload)
            if kind == "discussion":
                session = service.create_discussion(
                    agent_ids,
                    topic=_collaboration_text(payload, "topic"),
                    max_rounds=_collaboration_integer(
                        payload,
                        "max_rounds",
                        default=6,
                    ),
                )
            elif kind == "cooperation":
                session = service.create_cooperation(
                    agent_ids,
                    task=_collaboration_text(payload, "task"),
                    leader_id=_collaboration_integer(
                        payload,
                        "leader_id",
                        allow_none=True,
                    ),
                    role_overrides=_collaboration_roles(payload),
                )
            else:
                raise ValueError(
                    "kind must be discussion or cooperation"
                )
            return self._json_response(
                _public_collaboration_session(session.to_dict())
            )
        parts = path.strip("/").split("/")
        if (
            len(parts) == 5
            and parts[:3] == ["api", "collaboration", "sessions"]
            and parts[4] in {"pause", "resume", "cancel"}
        ):
            service = _get_collaboration_service()
            result = getattr(service, parts[4])(parts[3])
            return self._json_response(
                _public_collaboration_session(result)
            )
        return self._json_response({"error": "Unknown endpoint"}, status=404)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path.startswith("/api/"):
            try:
                return self._handle_api_get(path, parse_qs(parsed.query))
            except (ValueError, KeyError) as exc:
                return self._json_response(
                    {"error": str(exc)},
                    status=400,
                )
            except Exception as exc:
                # HTTP boundary: log the full traceback and surface a 500.
                _LOG.exception("GET %s failed: %s", path, exc)
                return self._json_response({"error": str(exc)}, status=500)
        if path in ("/", "/console", "/console/"):
            self.path = "/site/console/index.html"
        elif path in ("/dashboard", "/dashboard/"):
            self.path = "/site/dashboard/index.html"
        return super().do_GET()

    def do_HEAD(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path in ("/", "/console", "/console/"):
            self.path = "/site/console/index.html"
        elif path in ("/dashboard", "/dashboard/"):
            self.path = "/site/dashboard/index.html"
        return super().do_HEAD()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if not path.startswith("/api/"):
            return self._json_response({"error": "POST is only supported under /api"}, status=404)
        try:
            return self._handle_api_post(path)
        except (ValueError, KeyError) as exc:
            return self._json_response(
                {"error": str(exc)},
                status=400,
            )
        except Exception as exc:
            # HTTP boundary: log the full traceback and surface a 500.
            _LOG.exception("POST %s failed: %s", path, exc)
            return self._json_response({"error": str(exc)}, status=500)


def run_server(host="127.0.0.1", port=8766):
    server = ThreadingHTTPServer((host, int(port)), DashboardHandler)
    url = f"http://{host}:{int(port)}/"
    print(f"GAWorld console: {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _stop_simulation()
        _reset_collaboration_service_for_tests()
        server.server_close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Serve the GAWorld local dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)
