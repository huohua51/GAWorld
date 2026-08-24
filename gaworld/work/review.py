"""ReviewChannel — permissioned Reviewer—Executor message path.

v2 criteria live in the Reviewer's private context. The Executor can
only see a delivered, structured review. Reviewer cannot write
artifacts. Stale or duplicate reviews are rejected, not re-executed.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.work.review")

Decision = Literal["approve", "revise"]
Role = Literal["executor", "reviewer", "environment"]

REVIEW_FIELDS = (
    "decision",
    "reviewed_spec_version",
    "required_spec_version",
    "criterion_id",
    "evidence",
    "required_change",
)


@dataclass
class ReviewAction:
    decision: str
    reviewed_spec_version: str
    required_spec_version: str
    criterion_id: str
    evidence: str
    required_change: dict[str, Any] = field(default_factory=dict)
    task_id: str = ""
    reviewer_id: int = 0
    review_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReviewAction":
        missing = [k for k in REVIEW_FIELDS if k not in payload]
        if missing:
            raise ValueError(f"missing fields: {missing}")
        decision = str(payload["decision"])
        if decision not in {"approve", "revise"}:
            raise ValueError(f"invalid decision: {decision}")
        change = payload.get("required_change") or {}
        if not isinstance(change, dict):
            raise ValueError("required_change must be an object")
        return cls(
            decision=decision,
            reviewed_spec_version=str(payload["reviewed_spec_version"]),
            required_spec_version=str(payload["required_spec_version"]),
            criterion_id=str(payload["criterion_id"]),
            evidence=str(payload["evidence"]),
            required_change=dict(change),
            task_id=str(payload.get("task_id", "")),
            reviewer_id=int(payload.get("reviewer_id", 0) or 0),
            review_id=str(payload.get("review_id", "")),
        )


def _version_rank(version: str | None) -> int:
    if not version:
        return -1
    text = str(version).strip().lower()
    if text.startswith("v") and text[1:].isdigit():
        return int(text[1:])
    return -1


class ReviewChannel:
    """jsonl-audited review mailbox with role isolation."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._private: dict[str, dict[str, Any]] = {}
        self._drafts: dict[str, dict[str, Any]] = {}
        self._inbox: dict[str, list[dict[str, Any]]] = {}
        self._emitted: dict[str, ReviewAction] = {}
        self._delivered: dict[str, dict[str, Any]] = {}
        self._adopted: dict[str, str] = {}
        self._writes: list[dict[str, Any]] = []
        self._denials: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._seq = 0
        self._load()

    def _ensure_dir(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def _append(self, event: dict[str, Any]) -> None:
        event = {"ts": time.time(), **event}
        self._events.append(event)
        self._ensure_dir()
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _deny(self, reason: str, **extra: Any) -> dict[str, Any]:
        payload = {"ok": False, "reason": reason, **extra}
        self._denials.append(payload)
        self._append({"event": "denied", **payload})
        return payload

    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError:
            return
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                _LOG.warning("dropping malformed review line in %s", self.path)
                continue
            self._replay(event)
            self._events.append(event)

    def _replay(self, event: dict[str, Any]) -> None:
        kind = event.get("event")
        task_id = str(event.get("task_id", ""))
        if kind == "private_put":
            self._private[task_id] = dict(event.get("payload") or {})
        elif kind == "draft_submitted":
            self._drafts[task_id] = {
                "path": event.get("path"),
                "spec_version": event.get("spec_version"),
                "executor_id": event.get("executor_id"),
            }
        elif kind == "review_emitted":
            try:
                action = ReviewAction.from_dict(event.get("action") or {})
            except (KeyError, ValueError, TypeError):
                return
            self._emitted[task_id] = action
        elif kind == "review_delivered":
            self._delivered[task_id] = dict(event)
            inbox = self._inbox.setdefault(task_id, [])
            inbox.append(event.get("action") or {})
        elif kind == "review_adopted":
            self._adopted[task_id] = str(event.get("review_id", ""))
        elif kind == "artifact_write":
            self._writes.append(dict(event))

    # ------------------------------------------------------------------
    # Private context
    # ------------------------------------------------------------------
    def put_private(self, task_id: str, owner_role: Role, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if owner_role != "reviewer":
                return self._deny("private_owner_must_be_reviewer", task_id=task_id, role=owner_role)
            self._private[task_id] = dict(payload)
            self._append({"event": "private_put", "task_id": task_id, "role": owner_role, "payload": dict(payload)})
            return {"ok": True, "task_id": task_id}

    def read_private(self, task_id: str, reader_role: Role) -> dict[str, Any]:
        with self._lock:
            if reader_role != "reviewer":
                return self._deny("unauthorized_private_read", task_id=task_id, role=reader_role)
            payload = self._private.get(task_id)
            if payload is None:
                return self._deny("private_context_missing", task_id=task_id, role=reader_role)
            self._append({"event": "private_read", "task_id": task_id, "role": reader_role})
            return {"ok": True, "payload": dict(payload)}

    # ------------------------------------------------------------------
    # Artifact ACL
    # ------------------------------------------------------------------
    def write_artifact(
        self,
        *,
        task_id: str,
        role: Role,
        kind: str,
        path: str,
        content: str,
    ) -> dict[str, Any]:
        with self._lock:
            if role != "executor":
                return self._deny(
                    "unauthorized_artifact_write",
                    task_id=task_id,
                    role=role,
                    kind=kind,
                    path=path,
                )
            if kind not in {"draft", "final"}:
                return self._deny("unknown_artifact_kind", task_id=task_id, kind=kind)
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content if content.endswith("\n") else content + "\n")
            record = {
                "event": "artifact_write",
                "ok": True,
                "task_id": task_id,
                "role": role,
                "kind": kind,
                "path": path,
            }
            self._writes.append(record)
            self._append(record)
            return {"ok": True, "path": path, "kind": kind}

    # ------------------------------------------------------------------
    # Draft + review
    # ------------------------------------------------------------------
    def submit_draft(self, task_id: str, *, executor_id: int, path: str, spec_version: str) -> dict[str, Any]:
        with self._lock:
            if not path or not os.path.isfile(path):
                return self._deny("draft_not_created", task_id=task_id, path=path)
            self._drafts[task_id] = {
                "path": path,
                "spec_version": spec_version,
                "executor_id": executor_id,
            }
            self._append({
                "event": "draft_submitted",
                "task_id": task_id,
                "executor_id": executor_id,
                "path": path,
                "spec_version": spec_version,
            })
            return {"ok": True, "task_id": task_id, "path": path}

    def request_review(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            draft = self._drafts.get(task_id)
            if not draft:
                return self._deny("review_not_requested", task_id=task_id, detail="no draft")
            if task_id not in self._private:
                return self._deny("review_private_context_missing", task_id=task_id)
            self._append({
                "event": "review_requested",
                "task_id": task_id,
                "draft_path": draft["path"],
                "draft_spec_version": draft["spec_version"],
            })
            return {"ok": True, "task_id": task_id, "draft": dict(draft)}

    def emit_review(self, task_id: str, *, reviewer_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if task_id not in self._drafts:
                return self._deny("review_not_requested", task_id=task_id)
            try:
                action = ReviewAction.from_dict({**payload, "task_id": task_id, "reviewer_id": reviewer_id})
            except (KeyError, ValueError, TypeError) as exc:
                return self._deny("review_contract_invalid", task_id=task_id, detail=str(exc))
            self._seq += 1
            action.review_id = f"{task_id}_r{self._seq}"
            self._emitted[task_id] = action
            self._append({
                "event": "review_emitted",
                "task_id": task_id,
                "reviewer_id": reviewer_id,
                "action": action.to_dict(),
            })
            return {"ok": True, "action": action.to_dict()}

    def deliver_review(self, task_id: str, *, drop: bool = False) -> dict[str, Any]:
        with self._lock:
            action = self._emitted.get(task_id)
            if action is None:
                return self._deny("review_not_emitted", task_id=task_id)
            record = {
                "event": "review_dropped" if drop else "review_delivered",
                "task_id": task_id,
                "review_id": action.review_id,
                "dropped": drop,
                "action": action.to_dict(),
            }
            self._delivered[task_id] = record
            if not drop:
                self._inbox.setdefault(task_id, []).append(action.to_dict())
            self._append(record)
            return {"ok": True, "dropped": drop, "review_id": action.review_id}

    def read_inbox(self, task_id: str, reader_role: Role) -> dict[str, Any]:
        with self._lock:
            if reader_role != "executor":
                return self._deny("unauthorized_inbox_read", task_id=task_id, role=reader_role)
            items = [dict(item) for item in self._inbox.get(task_id, [])]
            self._append({"event": "inbox_read", "task_id": task_id, "role": reader_role, "n": len(items)})
            return {"ok": True, "reviews": items}

    def adopt_review(self, task_id: str, review_id: str, *, current_spec_version: str) -> dict[str, Any]:
        with self._lock:
            if self._adopted.get(task_id) == review_id:
                return self._deny("review_already_adopted", task_id=task_id, review_id=review_id)
            action = self._emitted.get(task_id)
            if action is None or action.review_id != review_id:
                return self._deny("unknown_review", task_id=task_id, review_id=review_id)
            inbox = self._inbox.get(task_id) or []
            if not any(item.get("review_id") == review_id for item in inbox):
                return self._deny("review_not_delivered", task_id=task_id, review_id=review_id)
            if _version_rank(action.required_spec_version) < _version_rank(current_spec_version):
                return self._deny(
                    "stale_review",
                    task_id=task_id,
                    review_id=review_id,
                    required=action.required_spec_version,
                    current=current_spec_version,
                )
            self._adopted[task_id] = review_id
            self._append({
                "event": "review_adopted",
                "task_id": task_id,
                "review_id": review_id,
                "required_spec_version": action.required_spec_version,
            })
            return {"ok": True, "action": action.to_dict()}

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def event_names(self) -> list[str]:
        return [str(event.get("event")) for event in self.events()]

    def denials(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._denials)

    def writes(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._writes)

    def draft_of(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            draft = self._drafts.get(task_id)
            return dict(draft) if draft else None

    def emitted_of(self, task_id: str) -> Optional[ReviewAction]:
        with self._lock:
            return self._emitted.get(task_id)

    def delivered_of(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            item = self._delivered.get(task_id)
            return dict(item) if item else None


__all__ = ["ReviewAction", "ReviewChannel"]
