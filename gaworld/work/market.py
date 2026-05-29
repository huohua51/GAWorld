"""JobMarket — mock job board agents can browse and accept.

State persistence
-----------------
- ``market.jsonl``: append-only log of submit / state-change events.
  Folded into the in-memory state on load. Crash-safe: a torn last
  line is dropped and we keep going.
- A sidecar dict ``daily_take_count`` tracks per-agent daily quotas
  to enforce ``max_taken_per_agent_per_day`` without scanning history.

Concurrency
-----------
The simulator is mostly single-threaded for market mutations (only
the main tick calls ``take``/``release``). A ``threading.RLock``
still guards in-memory state for safety. We do **not** rely on file
locks because the queue is process-local; multi-process is M4.
"""

from __future__ import annotations

import json
import math
import os
import random
import threading
import time
from typing import Any, Iterable, Optional

from gaworld.logging_setup import get_logger
from gaworld.work.schemas import (
    DELIVERABLES,
    AgentCapabilities,
    MarketJob,
)

_LOG = get_logger("gaworld.work.market")


# Skill aliases — tiny manual table to soften LLM-vs-seed terminology drift.
# Kept short on purpose; expand only when concrete misses are observed.
_SKILL_ALIASES: dict[str, str] = {
    "版式设计": "排版",
    "版式": "排版",
    "排版设计": "排版",
    "ui": "视觉设计",
    "ui 设计": "视觉设计",
    "视觉": "视觉设计",
    "调色": "色彩搭配",
    "配色": "色彩搭配",
    "数据分析": "数据处理",
    "data": "数据处理",
    "py": "python",
    "python 编程": "python",
    "新媒体写作": "新媒体",
    "公众号": "新媒体",
    "学术综述": "文献综述",
    "教学": "教学设计",
}


def _norm_skill(s: str) -> str:
    s = (s or "").strip().lower()
    if not s:
        return ""
    return _SKILL_ALIASES.get(s, s)


def _norm_skill_set(items: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for s in items or []:
        n = _norm_skill(str(s))
        if n:
            out.add(n)
    return out


class JobAlreadyTaken(Exception):
    """Raised when ``take`` is called on a non-open job."""


class JobMarket:
    """In-memory job board with jsonl persistence."""

    def __init__(
        self,
        store_path: str,
        seed_path: str,
        *,
        expire_after_sim_days: int = 5,
        auto_replenish: bool = True,
        replenish_threshold: int = 5,
    ) -> None:
        self.store_path = store_path
        self.seed_path = seed_path
        self.expire_after_sim_days = expire_after_sim_days
        self.auto_replenish = auto_replenish
        self.replenish_threshold = replenish_threshold
        self._lock = threading.RLock()
        self._jobs: dict[str, MarketJob] = {}
        self._daily_take_count: dict[tuple[int, int], int] = {}  # (day, agent_id) -> count
        self._load_store()
        if not self._jobs:
            self.replenish_from_seed(posted_sim_day=0)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _ensure_dir(self) -> None:
        directory = os.path.dirname(self.store_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def _append_event(self, event: dict[str, Any]) -> None:
        self._ensure_dir()
        with open(self.store_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _load_store(self) -> None:
        if not self.store_path or not os.path.exists(self.store_path):
            return
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
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
                _LOG.warning("dropping malformed market line in %s", self.store_path)
                continue
            self._apply_event(event)

    def _apply_event(self, event: dict[str, Any]) -> None:
        kind = event.get("event")
        if kind == "post":
            data = event.get("job") or {}
            try:
                job = MarketJob.from_dict(data)
            except (KeyError, ValueError, TypeError):
                return
            self._jobs[job.job_id] = job
        elif kind == "update":
            job_id = str(event.get("job_id", ""))
            patch = event.get("patch") or {}
            if not job_id or job_id not in self._jobs:
                return
            current = self._jobs[job_id].to_dict()
            current.update({k: v for k, v in patch.items() if k != "job_id"})
            try:
                self._jobs[job_id] = MarketJob.from_dict(current)
            except (KeyError, ValueError, TypeError):
                return

    # ------------------------------------------------------------------
    # Seed replenishment
    # ------------------------------------------------------------------
    def replenish_from_seed(self, *, posted_sim_day: int) -> int:
        """Load seed file and post jobs not already present.

        Each seed entry's ``deadline_sim_day`` is computed as
        ``posted_sim_day + deadline_window_days`` so that re-runs from
        a different start day don't ship pre-expired jobs.
        """

        if not self.seed_path or not os.path.exists(self.seed_path):
            return 0
        try:
            with open(self.seed_path, "r", encoding="utf-8") as f:
                seed = json.load(f)
        except (OSError, json.JSONDecodeError):
            _LOG.warning("seed file unreadable: %s", self.seed_path)
            return 0
        if not isinstance(seed, list):
            return 0

        added = 0
        with self._lock:
            for entry in seed:
                if not isinstance(entry, dict):
                    continue
                base_id = str(entry.get("job_id", "")).strip()
                if not base_id:
                    continue
                # If the original ID exists, use a day-suffixed variant on
                # subsequent replenishments so we don't collide.
                target_id = base_id if base_id not in self._jobs else f"{base_id}_d{posted_sim_day}"
                if target_id in self._jobs:
                    continue
                window = int(entry.get("deadline_window_days", 4) or 4)
                # Skip seed entries with deliverables outside our enum so
                # we never post unroutable jobs.
                deliverable = str(entry.get("deliverable", "")).strip()
                if deliverable and deliverable not in DELIVERABLES:
                    continue
                job = MarketJob(
                    job_id=target_id,
                    title=str(entry.get("title", "")),
                    description=str(entry.get("description", "")),
                    deliverable=deliverable,
                    required_skills=list(entry.get("required_skills") or []),
                    required_job_labels=list(entry.get("required_job_labels") or []),
                    reward_econ=float(entry.get("reward_econ", 0.0) or 0.0),
                    reward_text=str(entry.get("reward_text", "")),
                    posted_sim_day=int(posted_sim_day),
                    deadline_sim_day=int(posted_sim_day + window),
                    status="open",
                    source_tag=str(entry.get("source_tag", "mock_seed")),
                )
                self._jobs[target_id] = job
                self._append_event({"event": "post", "job": job.to_dict()})
                added += 1
        return added

    # ------------------------------------------------------------------
    # Daily lifecycle
    # ------------------------------------------------------------------
    def tick_day(self, sim_day: int) -> None:
        """Expire stale jobs; auto-replenish if pool below threshold."""

        with self._lock:
            for job_id, job in list(self._jobs.items()):
                if job.status in ("done", "failed", "expired"):
                    continue
                if job.deadline_sim_day and sim_day > job.deadline_sim_day:
                    self._update_status(job_id, "expired")
            if self.auto_replenish:
                open_count = sum(1 for j in self._jobs.values() if j.status == "open")
                if open_count < self.replenish_threshold:
                    self.replenish_from_seed(posted_sim_day=sim_day)

    # ------------------------------------------------------------------
    # Browse / Take / Release
    # ------------------------------------------------------------------
    def browse(
        self,
        capabilities: AgentCapabilities,
        *,
        sim_day: int,
        top_k: int = 5,
    ) -> list[tuple[MarketJob, float]]:
        """Return up to ``top_k`` open jobs visible to this agent, scored desc."""

        with self._lock:
            agent_skills = _norm_skill_set(capabilities.skills)
            agent_interests = _norm_skill_set(capabilities.interests)
            label = capabilities.job_label
            scored: list[tuple[MarketJob, float]] = []
            for job in self._jobs.values():
                if job.status != "open":
                    continue
                if job.deadline_sim_day and sim_day > job.deadline_sim_day:
                    continue
                if job.required_job_labels and label not in job.required_job_labels:
                    continue
                req_skills = _norm_skill_set(job.required_skills)
                if req_skills:
                    overlap = len(req_skills & agent_skills) / max(1, len(req_skills))
                else:
                    overlap = 0.5  # no skill demand → neutral
                interest_overlap = (
                    len(req_skills & agent_interests) / max(1, len(req_skills))
                    if req_skills else 0.0
                )
                window = max(1, job.deadline_sim_day - job.posted_sim_day)
                remaining = max(0, job.deadline_sim_day - sim_day)
                urgency = 1.0 - (remaining / window)
                score = (
                    0.5 * overlap
                    + 0.2 * interest_overlap
                    + 0.2 * float(job.reward_econ)
                    + 0.1 * (1.0 - urgency)
                )
                scored.append((job, score))
            scored.sort(key=lambda pair: pair[1], reverse=True)
            return scored[:top_k]

    def take(
        self,
        job_id: str,
        agent_id: int,
        *,
        sim_time: str,
        sim_day: int,
        max_taken_per_agent_per_day: int,
    ) -> MarketJob:
        """Lock a job to ``agent_id``. Raises ``JobAlreadyTaken`` if not open."""

        with self._lock:
            quota_key = (int(sim_day), int(agent_id))
            if self._daily_take_count.get(quota_key, 0) >= max_taken_per_agent_per_day:
                raise JobAlreadyTaken(f"agent {agent_id} hit daily quota")
            job = self._jobs.get(job_id)
            if job is None or job.status != "open":
                raise JobAlreadyTaken(f"job {job_id} not open")
            patch = {
                "status": "taken",
                "taken_by_agent_id": int(agent_id),
                "taken_at_sim_time": sim_time,
            }
            self._apply_patch(job_id, patch)
            self._daily_take_count[quota_key] = self._daily_take_count.get(quota_key, 0) + 1
            return self._jobs[job_id]

    def link_task(self, job_id: str, task_id: str) -> None:
        with self._lock:
            self._apply_patch(job_id, {"linked_task_id": task_id})

    def settle(self, job_id: str, *, success: bool) -> Optional[MarketJob]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            self._apply_patch(job_id, {"status": "done" if success else "failed"})
            return self._jobs[job_id]

    def release(self, job_id: str) -> None:
        """Return a taken-but-not-linked job to the open pool."""

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "taken":
                return
            self._apply_patch(
                job_id,
                {"status": "open", "taken_by_agent_id": None, "taken_at_sim_time": None,
                 "linked_task_id": None},
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _apply_patch(self, job_id: str, patch: dict[str, Any]) -> None:
        if job_id not in self._jobs:
            return
        current = self._jobs[job_id].to_dict()
        current.update(patch)
        try:
            self._jobs[job_id] = MarketJob.from_dict(current)
        except (KeyError, ValueError, TypeError):
            return
        self._append_event({"event": "update", "job_id": job_id, "patch": patch})

    def _update_status(self, job_id: str, status: str) -> None:
        self._apply_patch(job_id, {"status": status})

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    def find_by_task(self, task_id: str) -> Optional[MarketJob]:
        with self._lock:
            for job in self._jobs.values():
                if job.linked_task_id == task_id:
                    return job
            return None

    def status_counts(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {}
            for job in self._jobs.values():
                counts[job.status] = counts.get(job.status, 0) + 1
            return counts

    def daily_take_for(self, sim_day: int, agent_id: int) -> int:
        with self._lock:
            return self._daily_take_count.get((int(sim_day), int(agent_id)), 0)

    def all_jobs(self) -> list[MarketJob]:
        with self._lock:
            return list(self._jobs.values())


# ---------------------------------------------------------------------------
# Decision helpers (pure functions, no LLM)
# ---------------------------------------------------------------------------

def browse_probability(
    state: dict[str, float],
    *,
    base: float,
) -> float:
    platform_dependence = float(state.get("platform_dependence", 0.5) or 0.5)
    econ_security = float(state.get("econ_security", 0.5) or 0.5)
    energy = float(state.get("energy", 0.7) or 0.7)
    p = (
        base
        + 0.20 * platform_dependence
        + 0.15 * (1.0 - econ_security)
        - 0.10 * (1.0 - energy)
    )
    return max(0.0, min(0.6, p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def accept_probability(
    score: float,
    state: dict[str, float],
) -> float:
    risk_pref = float(state.get("risk_preference", 0.5) or 0.5)
    stress = float(state.get("stress", 0.5) or 0.5)
    x = score * 2.0 + 0.4 * (risk_pref - 0.5) - 0.5 * (stress - 0.5)
    return _sigmoid(x)


def deterministic_random(agent_id: int, sim_day: int, salt: str = "") -> random.Random:
    """Return a per-(agent, day) Random instance — does NOT touch globals."""

    seed_str = f"{agent_id}|{sim_day}|{salt}"
    seed = int.from_bytes(seed_str.encode("utf-8"), "big") & 0x7FFFFFFF
    return random.Random(seed)


__all__ = [
    "JobAlreadyTaken",
    "JobMarket",
    "accept_probability",
    "browse_probability",
    "deterministic_random",
]
