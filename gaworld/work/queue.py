"""WorkQueue — jsonl-backed task queue with crash recovery.

Each line in the file is one of:
- ``{"event": "submit", "brief": {...}}``
- ``{"event": "claim",  "task_id": "...", "claimed_at": ...}``
- ``{"event": "result", "result": {...}}``

The current state of every task is folded by replaying lines on
load. This trades disk space for trivial corruption recovery — if
the file ends mid-write the last line is dropped and we keep going.

Thread-safety: a single ``threading.Lock`` guards file writes and
the in-memory state. The simulator's main thread submits; worker
threads claim and write results.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Iterable, Optional

from gaworld.logging_setup import get_logger
from gaworld.work.schemas import WorkBrief, WorkResult

_LOG = get_logger("gaworld.work.queue")


class WorkQueue:
    """jsonl-persisted queue for WorkBrief / WorkResult round-trips."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._briefs: dict[str, WorkBrief] = {}
        self._status: dict[str, str] = {}  # task_id -> pending|running|done|failed
        self._results: dict[str, WorkResult] = {}
        self._claimed_at: dict[str, float] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _ensure_dir(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def _append(self, event: dict[str, Any]) -> None:
        self._ensure_dir()
        line = json.dumps(event, ensure_ascii=False)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                _LOG.warning("dropping malformed queue line in %s", self.path)
                continue
            self._apply(event)

    def _apply(self, event: dict[str, Any]) -> None:
        kind = event.get("event")
        if kind == "submit":
            data = event.get("brief") or {}
            try:
                brief = WorkBrief.from_dict(data)
            except (KeyError, ValueError, TypeError):
                return
            self._briefs[brief.task_id] = brief
            self._status.setdefault(brief.task_id, "pending")
        elif kind == "claim":
            task_id = str(event.get("task_id", ""))
            if task_id and task_id in self._briefs:
                self._status[task_id] = "running"
                self._claimed_at[task_id] = float(event.get("claimed_at", 0.0))
        elif kind == "result":
            data = event.get("result") or {}
            try:
                result = WorkResult.from_dict(data)
            except (KeyError, ValueError, TypeError):
                return
            self._results[result.task_id] = result
            self._status[result.task_id] = "done" if result.status == "ok" else "failed"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def submit(self, brief: WorkBrief) -> None:
        with self._lock:
            self._briefs[brief.task_id] = brief
            self._status[brief.task_id] = "pending"
            self._append({"event": "submit", "brief": brief.to_dict()})

    def claim_next(self) -> Optional[WorkBrief]:
        with self._lock:
            for tid, status in self._status.items():
                if status != "pending":
                    continue
                self._status[tid] = "running"
                ts = time.time()
                self._claimed_at[tid] = ts
                self._append({"event": "claim", "task_id": tid, "claimed_at": ts})
                return self._briefs[tid]
            return None

    def record_result(self, result: WorkResult) -> None:
        with self._lock:
            self._results[result.task_id] = result
            self._status[result.task_id] = "done" if result.status == "ok" else "failed"
            self._append({"event": "result", "result": result.to_dict()})

    # --- introspection ---
    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for s in self._status.values() if s == "pending")

    def has_unfinished_for(self, agent_id: int) -> bool:
        with self._lock:
            for tid, brief in self._briefs.items():
                if brief.agent_id == agent_id and self._status.get(tid) in ("pending", "running"):
                    return True
            return False

    def drain_completed_for(self, agent_id: int, *, limit: int = 5) -> list[WorkResult]:
        """Return finished results for ``agent_id`` not yet drained.

        Drained results are removed from the in-memory pool so they aren't
        ingested twice. The jsonl on disk keeps the full audit trail.
        """

        with self._lock:
            ready: list[WorkResult] = []
            keys = list(self._results.keys())
            for tid in keys:
                if len(ready) >= limit:
                    break
                result = self._results[tid]
                if result.agent_id != agent_id:
                    continue
                ready.append(result)
                # Remove from results map but keep status so we don't reissue.
                del self._results[tid]
            return ready

    def all_briefs(self) -> Iterable[WorkBrief]:
        with self._lock:
            return list(self._briefs.values())

    def status_of(self, task_id: str) -> str:
        with self._lock:
            return self._status.get(task_id, "unknown")


__all__ = ["WorkQueue"]
