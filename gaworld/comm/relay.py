"""RelayChannel — Observer → Verifier → Dispatcher with role isolation.

The trust table lives only in the Verifier private context. The
Dispatcher may adopt a delivered verified message and submit an action.
Verifier cannot submit. Dispatcher cannot read the trust table.
Stale or duplicate verified messages are rejected.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional

from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.comm.relay")

Role = Literal["observer", "verifier", "dispatcher", "environment"]

ACTION_FIELDS = ("action", "value", "adopted_state_version", "evidence_message_id")


def _version_rank(version: str | None) -> int:
    if not version:
        return -1
    text = str(version).strip().lower()
    if text.startswith("v") and text[1:].isdigit():
        return int(text[1:])
    return -1


@dataclass
class RelayAction:
    action: str
    value: str
    adopted_state_version: str
    evidence_message_id: str
    task_id: str = ""
    dispatcher_id: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RelayAction":
        missing = [k for k in ACTION_FIELDS if k not in payload]
        if missing:
            raise ValueError(f"missing fields: {missing}")
        return cls(
            action=str(payload["action"]),
            value=str(payload["value"]),
            adopted_state_version=str(payload["adopted_state_version"]),
            evidence_message_id=str(payload["evidence_message_id"]),
            task_id=str(payload.get("task_id", "")),
            dispatcher_id=int(payload.get("dispatcher_id", 0) or 0),
        )


class RelayChannel:
    """jsonl-audited information relay with private trust isolation."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._private: dict[tuple[str, Role], dict[str, Any]] = {}
        self._raw: dict[str, list[dict[str, Any]]] = {}
        self._verified: dict[str, dict[str, Any]] = {}
        self._inbox: dict[str, list[dict[str, Any]]] = {}
        self._raw_inbox: dict[str, list[dict[str, Any]]] = {}
        self._adopted: dict[str, str] = {}
        self._actions: dict[str, RelayAction] = {}
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
                _LOG.warning("dropping malformed relay line in %s", self.path)
                continue
            self._replay(event)
            self._events.append(event)

    def _replay(self, event: dict[str, Any]) -> None:
        kind = event.get("event")
        task_id = str(event.get("task_id", ""))
        if kind == "private_put":
            role = event.get("role")
            if role:
                self._private[(task_id, role)] = dict(event.get("payload") or {})
        elif kind == "raw_sent":
            self._raw.setdefault(task_id, []).append(dict(event.get("message") or {}))
        elif kind == "raw_delivered":
            self._raw_inbox.setdefault(task_id, []).append(dict(event.get("message") or {}))
        elif kind == "verified_emitted":
            self._verified[task_id] = dict(event.get("message") or {})
        elif kind == "verified_delivered":
            self._inbox.setdefault(task_id, []).append(dict(event.get("message") or {}))
        elif kind == "verified_adopted":
            self._adopted[task_id] = str(event.get("message_id", ""))
        elif kind == "action_submitted":
            try:
                self._actions[task_id] = RelayAction.from_dict(event.get("action") or {})
            except (KeyError, ValueError, TypeError):
                return

    def put_private(self, task_id: str, owner_role: Role, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if owner_role not in {"observer", "verifier", "dispatcher"}:
                return self._deny("invalid_private_owner", task_id=task_id, role=owner_role)
            self._private[(task_id, owner_role)] = dict(payload)
            self._append({"event": "private_put", "task_id": task_id, "role": owner_role, "payload": dict(payload)})
            return {"ok": True, "task_id": task_id, "role": owner_role}

    def read_private(self, task_id: str, reader_role: Role, owner_role: Role) -> dict[str, Any]:
        with self._lock:
            if reader_role != owner_role:
                return self._deny(
                    "unauthorized_private_read",
                    task_id=task_id,
                    role=reader_role,
                    owner=owner_role,
                )
            payload = self._private.get((task_id, owner_role))
            if payload is None:
                return self._deny("private_context_missing", task_id=task_id, role=reader_role)
            self._append({"event": "private_read", "task_id": task_id, "role": reader_role, "owner": owner_role})
            return {"ok": True, "payload": dict(payload)}

    def send_raw(self, task_id: str, *, observer_id: int, message: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            packed = {
                "message_id": str(message.get("message_id") or f"raw-msg-{task_id}-{self._seq}"),
                "source_id": str(message.get("source_id", "")),
                "reported_state": str(message.get("reported_state", "")),
                "observer_id": observer_id,
            }
            if not packed["source_id"] or not packed["reported_state"]:
                return self._deny("observation_not_created", task_id=task_id)
            self._raw.setdefault(task_id, []).append(packed)
            self._append({"event": "raw_sent", "task_id": task_id, "message": packed})
            return {"ok": True, "message": packed}

    def deliver_raw(self, task_id: str, *, to_role: Role = "verifier") -> dict[str, Any]:
        with self._lock:
            if to_role != "verifier":
                return self._deny("raw_only_to_verifier", task_id=task_id, role=to_role)
            items = [dict(item) for item in self._raw.get(task_id, [])]
            if not items:
                return self._deny("raw_signal_not_sent", task_id=task_id)
            self._raw_inbox[task_id] = items
            for item in items:
                self._append({"event": "raw_delivered", "task_id": task_id, "message": item})
            return {"ok": True, "messages": items}

    def read_raw_inbox(self, task_id: str, reader_role: Role) -> dict[str, Any]:
        with self._lock:
            if reader_role != "verifier":
                return self._deny("unauthorized_raw_inbox_read", task_id=task_id, role=reader_role)
            items = [dict(item) for item in self._raw_inbox.get(task_id, [])]
            self._append({"event": "raw_inbox_read", "task_id": task_id, "n": len(items)})
            return {"ok": True, "messages": items}

    def seed_focused(self, task_id: str, *, state: str, version: str, source_id: str = "focused") -> dict[str, Any]:
        """Ceiling track: environment places the final verified state in the inbox."""
        with self._lock:
            self._seq += 1
            message = {
                "message_id": f"verified-msg-{task_id}-{self._seq}",
                "verified_state": state,
                "source_id": source_id,
                "state_version": version,
                "verifier_id": 0,
                "focused": True,
            }
            self._verified[task_id] = message
            self._inbox.setdefault(task_id, []).append(dict(message))
            self._append({"event": "verified_emitted", "task_id": task_id, "message": message})
            self._append({"event": "verified_delivered", "task_id": task_id, "dropped": False, "message": message})
            return {"ok": True, "message": message}

    def emit_verified(self, task_id: str, *, verifier_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if not self._raw_inbox.get(task_id):
                return self._deny("verification_not_requested", task_id=task_id)
            state = str(payload.get("verified_state") or payload.get("state") or "")
            source_id = str(payload.get("source_id") or "")
            version = str(payload.get("state_version") or payload.get("version") or "")
            if not state or not source_id or not version:
                return self._deny("verified_message_not_emitted", task_id=task_id, detail="missing fields")
            trusted = (self._private.get((task_id, "verifier")) or {}).get("trusted_source_id")
            if trusted and source_id != trusted:
                return self._deny("wrong_source_verified", task_id=task_id, source_id=source_id, trusted=trusted)
            self._seq += 1
            message = {
                "message_id": f"verified-msg-{task_id}-{self._seq}",
                "verified_state": state,
                "source_id": source_id,
                "state_version": version,
                "verifier_id": verifier_id,
            }
            self._verified[task_id] = message
            self._append({"event": "verified_emitted", "task_id": task_id, "message": message})
            return {"ok": True, "message": message}

    def deliver_verified(self, task_id: str, *, drop: bool = False) -> dict[str, Any]:
        with self._lock:
            message = self._verified.get(task_id)
            if message is None:
                return self._deny("verified_message_not_emitted", task_id=task_id)
            record = {
                "event": "verified_dropped" if drop else "verified_delivered",
                "task_id": task_id,
                "dropped": drop,
                "message": message,
            }
            if not drop:
                self._inbox.setdefault(task_id, []).append(dict(message))
            self._append(record)
            return {"ok": True, "dropped": drop, "message_id": message["message_id"]}

    def read_inbox(self, task_id: str, reader_role: Role) -> dict[str, Any]:
        with self._lock:
            if reader_role != "dispatcher":
                return self._deny("unauthorized_inbox_read", task_id=task_id, role=reader_role)
            items = [dict(item) for item in self._inbox.get(task_id, [])]
            self._append({"event": "inbox_read", "task_id": task_id, "n": len(items)})
            return {"ok": True, "messages": items}

    def deliver_raw_to_dispatcher(self, task_id: str) -> dict[str, Any]:
        """No-verification track: dispatcher sees conflicting raw signals only."""
        with self._lock:
            items = [dict(item) for item in self._raw.get(task_id, [])]
            if not items:
                return self._deny("raw_signal_not_sent", task_id=task_id)
            self._append({"event": "raw_to_dispatcher", "task_id": task_id, "messages": items})
            return {"ok": True, "messages": items}

    def adopt_verified(self, task_id: str, message_id: str, *, current_version: str | None = None) -> dict[str, Any]:
        with self._lock:
            if self._adopted.get(task_id) == message_id:
                return self._deny("verified_already_adopted", task_id=task_id, message_id=message_id)
            inbox = self._inbox.get(task_id) or []
            match = next((item for item in inbox if item.get("message_id") == message_id), None)
            if match is None:
                return self._deny("verified_message_not_delivered", task_id=task_id, message_id=message_id)
            incoming = str(match.get("state_version", ""))
            if current_version and _version_rank(incoming) < _version_rank(current_version):
                return self._deny(
                    "stale_state_used",
                    task_id=task_id,
                    incoming=incoming,
                    current=current_version,
                )
            if self._adopted.get(task_id) and _version_rank(incoming) < _version_rank(
                str((self._verified.get(task_id) or {}).get("state_version", ""))
            ):
                return self._deny("stale_state_used", task_id=task_id, incoming=incoming)
            self._adopted[task_id] = message_id
            self._append({
                "event": "verified_adopted",
                "task_id": task_id,
                "message_id": message_id,
                "state_version": incoming,
            })
            return {"ok": True, "message": dict(match)}

    def submit_action(self, task_id: str, *, dispatcher_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                action = RelayAction.from_dict({**payload, "task_id": task_id, "dispatcher_id": dispatcher_id})
            except (KeyError, ValueError, TypeError) as exc:
                return self._deny("target_action_incorrect", task_id=task_id, detail=str(exc))
            self._actions[task_id] = action
            self._append({"event": "action_submitted", "task_id": task_id, "action": action.to_dict()})
            return {"ok": True, "action": action.to_dict()}

    def reject_submit(self, task_id: str, role: Role) -> dict[str, Any]:
        with self._lock:
            if role == "dispatcher":
                return self._deny("submit_requires_payload", task_id=task_id)
            return self._deny("unauthorized_action_submit", task_id=task_id, role=role)

    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def event_names(self) -> list[str]:
        return [str(event.get("event")) for event in self.events()]

    def denials(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._denials)

    def adopted_of(self, task_id: str) -> Optional[str]:
        with self._lock:
            return self._adopted.get(task_id)

    def action_of(self, task_id: str) -> Optional[RelayAction]:
        with self._lock:
            return self._actions.get(task_id)

    def verified_of(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            item = self._verified.get(task_id)
            return dict(item) if item else None


__all__ = ["RelayAction", "RelayChannel"]
