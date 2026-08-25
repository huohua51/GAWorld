"""Workflow checkpoint and successor handoff.

The environment records step events and world mutations. It never completes
remaining steps, never overwrites completed work, and never tells a worker
which remaining outputs to produce.
Checkpoint versions are stamped by the platform.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.work.continuity")

WORKER_ROLES = ("worker_a", "worker_b")
ALL_ROLES = ("worker_a", "worker_b", "coordinator", "environment")
CHECKPOINT_VERSION = "ckpt-001"
FORBIDDEN_HANDOFF_KEYS = (
    "oracle",
    "expected",
    "remaining_outputs",
    "suggested_output",
    "correct_resume",
    "hidden_test",
)


def canonical_hash(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def next_step(step_ids: list[str], completed: list[str]) -> str:
    done = set(completed)
    for step_id in step_ids:
        if step_id not in done:
            return step_id
    return ""


@dataclass
class WorkflowCheckpointChannel:
    """Save → transmit → read. World mutations come only from worker execute_step."""

    step_ids: list[str]
    path: str | Path | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    _private: dict[str, dict[str, Any]] = field(default_factory=dict)
    _steps: dict[str, dict[str, Any]] = field(default_factory=dict)
    _completed: list[str] = field(default_factory=list)
    _duplicates: list[dict[str, Any]] = field(default_factory=list)
    _checkpoint: dict[str, Any] | None = None
    _checkpoint_inbox: dict[str, dict[str, Any]] = field(default_factory=dict)
    _handoff: dict[str, Any] | None = None
    _handoff_inbox: dict[str, dict[str, Any]] = field(default_factory=dict)
    _unavailable: set[str] = field(default_factory=set)
    _denials: list[dict[str, Any]] = field(default_factory=list)
    interrupt_event_index: int | None = None
    resume_event_index: int | None = None
    checkpoint_dropped_for: set[str] = field(default_factory=set)
    handoff_dropped_for: set[str] = field(default_factory=set)

    def _append(self, event: dict[str, Any]) -> None:
        body = dict(event)
        body["index"] = len(self.events)
        self.events.append(body)
        if not self.path:
            return
        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(body, ensure_ascii=False) + "\n")

    def _deny(self, reason: str, **extra: Any) -> dict[str, Any]:
        payload = {"ok": False, "reason": reason, **extra}
        self._denials.append(payload)
        self._append({"event": "denied", **payload})
        return payload

    def put_private(self, owner: str, payload: dict[str, Any]) -> dict[str, Any]:
        if owner not in WORKER_ROLES:
            return self._deny("private_owner_must_be_worker", role=owner)
        body = copy.deepcopy(payload)
        self._private[owner] = body
        self._append({"event": "private_put", "role": owner})
        return {"ok": True, "role": owner}

    def read_private(self, reader: str, owner: str) -> dict[str, Any]:
        if reader != owner:
            return self._deny("unauthorized_private_read", role=reader, owner=owner)
        payload = self._private.get(owner)
        if payload is None:
            return self._deny("private_context_missing", role=reader, owner=owner)
        self._append({"event": "private_read", "role": reader, "owner": owner})
        return {"ok": True, "payload": copy.deepcopy(payload)}

    def mark_unavailable(self, worker: str) -> dict[str, Any]:
        if worker not in WORKER_ROLES:
            return self._deny("invalid_worker", role=worker)
        self._unavailable.add(worker)
        self.interrupt_event_index = len(self.events)
        self._append({"event": "worker_unavailable", "role": worker})
        return {"ok": True, "role": worker}

    def execute_step(self, *, role: str, step_id: str, output: dict[str, Any]) -> dict[str, Any]:
        if role == "environment":
            return self._deny("environment_fallback", role=role, step_id=step_id)
        if role == "coordinator":
            return self._deny("coordinator_cannot_execute", role=role, step_id=step_id)
        if role not in WORKER_ROLES:
            return self._deny("unauthorized_world_write", role=role)
        if role in self._unavailable:
            return self._deny("worker_unavailable", role=role, step_id=step_id)
        if step_id not in self.step_ids:
            return self._deny("unknown_step", role=role, step_id=step_id)
        if step_id in self._completed:
            record = {"role": role, "step_id": step_id, "output": copy.deepcopy(output)}
            self._duplicates.append(record)
            self._append({"event": "duplicate_action", **record})
            return {"ok": False, "reason": "duplicate_action", "duplicate": True, "step_id": step_id}
        expected = next_step(self.step_ids, self._completed)
        if step_id != expected:
            self._append({"event": "resume_from_wrong_step", "role": role, "step_id": step_id, "expected": expected})
            return {"ok": False, "reason": "resume_from_wrong_step", "step_id": step_id, "expected": expected}
        stored = copy.deepcopy(output)
        self._steps[step_id] = {
            "status": "completed",
            "actor": role,
            "output": stored,
            "event_index": len(self.events),
        }
        self._completed.append(step_id)
        if self.interrupt_event_index is not None and self.resume_event_index is None and role == "worker_b":
            self.resume_event_index = len(self.events)
        self._append({"event": "step_completed", "role": role, "step_id": step_id, "output": stored})
        return {"ok": True, "step_id": step_id, "actor": role}

    def emit_checkpoint(self, *, role: str, completed_steps: list[str], outputs: dict[str, Any]) -> dict[str, Any]:
        if role not in WORKER_ROLES:
            return self._deny("unauthorized_checkpoint", role=role)
        if role in self._unavailable:
            return self._deny("worker_unavailable", role=role)
        observed = list(self._completed)
        if list(completed_steps) != observed:
            return self._deny("checkpoint_mismatch", role=role, completed_steps=list(completed_steps), observed=observed)
        body = {
            "checkpoint_version": CHECKPOINT_VERSION,
            "completed_steps": list(observed),
            "outputs": copy.deepcopy(outputs) if outputs else {sid: copy.deepcopy(self._steps[sid]["output"]) for sid in observed},
            "world_digest": canonical_hash({sid: self._steps[sid]["output"] for sid in observed}),
        }
        self._checkpoint = body
        self._append({"event": "checkpoint_emitted", "role": role, "hash": canonical_hash(body), "payload": copy.deepcopy(body)})
        return {"ok": True, "checkpoint": copy.deepcopy(body)}

    def deliver_checkpoint(self, reader: str, *, drop: bool = False) -> dict[str, Any]:
        if self._checkpoint is None:
            return self._deny("checkpoint_not_created")
        digest = canonical_hash(self._checkpoint)
        if drop:
            self.checkpoint_dropped_for.add(reader)
            self._append({"event": "checkpoint_dropped", "reader": reader, "hash": digest})
            return {"ok": True, "dropped": True, "hash": digest}
        self._checkpoint_inbox[reader] = copy.deepcopy(self._checkpoint)
        self._append({"event": "checkpoint_delivered", "reader": reader, "hash": digest})
        return {"ok": True, "dropped": False, "hash": digest}

    def read_checkpoint(self, reader: str) -> dict[str, Any]:
        body = self._checkpoint_inbox.get(reader)
        if body is None:
            return self._deny("checkpoint_not_delivered", role=reader)
        self._append({"event": "checkpoint_read", "role": reader, "version": body.get("checkpoint_version")})
        return {"ok": True, "checkpoint": copy.deepcopy(body)}

    def emit_handoff(self, *, role: str, successor: str, checkpoint_version: str, resume_step: str) -> dict[str, Any]:
        if role != "coordinator":
            return self._deny("unauthorized_handoff", role=role)
        if successor not in WORKER_ROLES:
            return self._deny("invalid_successor", successor=successor)
        body = {
            "successor": successor,
            "checkpoint_version": str(checkpoint_version or ""),
            "resume_step": str(resume_step or ""),
        }
        self._handoff = body
        self._append({"event": "handoff_emitted", "payload": copy.deepcopy(body)})
        return {"ok": True, "handoff": copy.deepcopy(body)}

    def deliver_handoff(self, reader: str, *, drop: bool = False) -> dict[str, Any]:
        if self._handoff is None:
            return self._deny("handoff_not_emitted")
        digest = canonical_hash(self._handoff)
        if drop:
            self.handoff_dropped_for.add(reader)
            self._append({"event": "handoff_dropped", "reader": reader, "hash": digest})
            return {"ok": True, "dropped": True, "hash": digest}
        self._handoff_inbox[reader] = copy.deepcopy(self._handoff)
        self._append({"event": "handoff_delivered", "reader": reader, "hash": digest})
        return {"ok": True, "dropped": False, "hash": digest}

    def read_handoff(self, reader: str) -> dict[str, Any]:
        body = self._handoff_inbox.get(reader)
        if body is None:
            return self._deny("handoff_not_delivered", role=reader)
        self._append({"event": "handoff_read", "role": reader})
        return {"ok": True, "handoff": copy.deepcopy(body)}

    def write_world(self, *, role: str, path: Path, content: str) -> dict[str, Any]:
        if role == "environment":
            return self._deny("environment_fallback", role=role, path=str(path))
        if role not in WORKER_ROLES:
            return self._deny("unauthorized_world_write", role=role, path=str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
        self._append({"event": "world_write", "role": role, "path": str(path)})
        return {"ok": True, "path": str(path)}

    def world_state(self) -> dict[str, Any]:
        return {
            "steps": copy.deepcopy(self._steps),
            "completed_steps": list(self._completed),
            "duplicates": copy.deepcopy(self._duplicates),
            "checkpoint": copy.deepcopy(self._checkpoint),
            "unavailable": sorted(self._unavailable),
        }

    def denials(self) -> list[dict[str, Any]]:
        return list(self._denials)

    def recovery_latency(self) -> int | None:
        if self.interrupt_event_index is None or self.resume_event_index is None:
            return None
        return int(self.resume_event_index - self.interrupt_event_index)

    def checkpoint_created(self) -> bool:
        return self._checkpoint is not None and self._checkpoint.get("checkpoint_version") == CHECKPOINT_VERSION

    def completed_work_preserved(self) -> bool:
        return not any(item.get("overwritten") for item in self._duplicates) and all(
            self._steps[sid]["status"] == "completed" for sid in self._completed
        )
