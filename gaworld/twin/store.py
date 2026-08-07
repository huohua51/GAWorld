"""Append-only report storage for the mobile digital twin.

``reports.jsonl`` is the single source of truth. Every downstream consumer —
the mirror stage, the perception-injection stage, and the offline calibration
script — derives from it and none of them write to it.

``snapshot.json`` is a derived cache of the newest report by timestamp, kept so
the mirror stage and the phone can read current state without scanning the full
log. It is regenerated on every append, never edited independently.
"""

from __future__ import annotations

import json
import os
import threading


DEFAULT_ROOT = "output/twin"

# One lock for the whole subsystem. The server is threaded, and at this scale
# (a handful of users) per-agent locks would add contention bookkeeping for no
# measurable gain.
_LOCK = threading.RLock()


def agent_dir(agent_id, root=DEFAULT_ROOT):
    return os.path.join(str(root), f"agent_{int(agent_id)}")


def _reports_path(agent_id, root=DEFAULT_ROOT):
    return os.path.join(agent_dir(agent_id, root=root), "reports.jsonl")


def _snapshot_path(agent_id, root=DEFAULT_ROOT):
    return os.path.join(agent_dir(agent_id, root=root), "snapshot.json")


def load_reports(agent_id, root=DEFAULT_ROOT, since_ts=None):
    """Return stored reports in file order, optionally newer than ``since_ts``."""
    path = _reports_path(agent_id, root=root)
    if not os.path.exists(path):
        return []
    reports = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # A truncated write (killed process, full disk) must not make
                # every later read fail. Skip the line and keep going.
                continue
            if since_ts is not None and float(record.get("ts", 0)) <= float(since_ts):
                continue
            reports.append(record)
    return reports


def append_reports(agent_id, reports, root=DEFAULT_ROOT):
    """Append reports, skipping any ``report_id`` already stored.

    Returns ``{"accepted": int, "duplicates": int}``.
    """
    with _LOCK:
        existing = {
            str(item.get("report_id"))
            for item in load_reports(agent_id, root=root)
            if item.get("report_id")
        }
        directory = agent_dir(agent_id, root=root)
        os.makedirs(directory, exist_ok=True)

        accepted = []
        duplicates = 0
        for record in reports or []:
            report_id = str(record.get("report_id") or "")
            if not report_id or report_id in existing:
                duplicates += 1
                continue
            existing.add(report_id)
            accepted.append(record)

        if accepted:
            with open(_reports_path(agent_id, root=root), "a", encoding="utf-8") as handle:
                for record in accepted:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            _refresh_snapshot(agent_id, root=root)

        return {"accepted": len(accepted), "duplicates": duplicates}


def _refresh_snapshot(agent_id, root=DEFAULT_ROOT):
    """Rewrite snapshot.json as the newest stored report by timestamp."""
    reports = load_reports(agent_id, root=root)
    if not reports:
        return
    newest = max(reports, key=lambda item: float(item.get("ts", 0)))
    directory = agent_dir(agent_id, root=root)
    os.makedirs(directory, exist_ok=True)
    with open(_snapshot_path(agent_id, root=root), "w", encoding="utf-8") as handle:
        json.dump(newest, handle, ensure_ascii=False, indent=2)


def read_snapshot(agent_id, root=DEFAULT_ROOT):
    """Return the newest report, or ``None`` when the agent has never reported."""
    path = _snapshot_path(agent_id, root=root)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def is_fresh(snapshot, now_ts, ttl_minutes):
    """Whether a snapshot is recent enough for the mirror channel to apply."""
    if not snapshot:
        return False
    try:
        age_seconds = float(now_ts) - float(snapshot.get("ts", 0))
    except (TypeError, ValueError):
        return False
    return 0 <= age_seconds <= float(ttl_minutes) * 60
