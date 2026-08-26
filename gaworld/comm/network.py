"""Audited multi-hop information propagation over a registered topology."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any


def _edge(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((str(left), str(right))))


@dataclass(frozen=True)
class PropagationMessage:
    message_id: str
    source_id: str
    state_version: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NetworkPropagationChannel:
    """Persist delivery, acceptance, topology interventions and final actions."""

    def __init__(self, path: str, edges: Iterable[tuple[str, str]]) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._edges = {_edge(left, right) for left, right in edges}
        self._removed_edges: set[tuple[str, str]] = set()
        self._messages: dict[str, PropagationMessage] = {}
        self._received: dict[tuple[str, str], dict[str, Any]] = {}
        self._accepted: set[tuple[str, str]] = set()
        self._actions: dict[str, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []
        self._denials: list[dict[str, Any]] = []
        self._seq = 0
        self._load()

    def _ensure_dir(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def _append(self, event: dict[str, Any]) -> None:
        self._seq += 1
        record = {"seq": self._seq, "ts": time.time(), **event}
        self._events.append(record)
        self._ensure_dir()
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _deny(self, reason: str, **extra: Any) -> dict[str, Any]:
        payload = {"ok": False, "reason": reason, **extra}
        self._denials.append(payload)
        self._append({"event": "denied", **payload})
        return payload

    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle if line.strip()]
        except (OSError, json.JSONDecodeError):
            return
        for row in rows:
            self._replay(row)
            self._events.append(row)
            self._seq = max(self._seq, int(row.get("seq") or 0))

    def _replay(self, event: dict[str, Any]) -> None:
        kind = event.get("event")
        message_id = str(event.get("message_id") or "")
        if kind == "message_injected":
            message = PropagationMessage(**dict(event.get("message") or {}))
            self._messages[message.message_id] = message
            self._received[(message.message_id, message.source_id)] = {
                "node_id": message.source_id,
                "sender_id": None,
                "depth": 0,
            }
            self._accepted.add((message.message_id, message.source_id))
        elif kind == "edge_removed":
            self._removed_edges.add(_edge(str(event.get("left")), str(event.get("right"))))
        elif kind == "message_delivered":
            receiver = str(event.get("receiver_id") or "")
            self._received[(message_id, receiver)] = {
                "node_id": receiver,
                "sender_id": str(event.get("sender_id") or ""),
                "depth": int(event.get("depth") or 0),
            }
        elif kind == "message_accepted":
            self._accepted.add((message_id, str(event.get("node_id") or "")))
        elif kind == "message_rejected":
            self._accepted.discard((message_id, str(event.get("node_id") or "")))
        elif kind == "action_submitted":
            self._actions[str(event.get("node_id") or "")] = dict(event.get("action") or {})

    def inject(
        self,
        *,
        message_id: str,
        source_id: str,
        state_version: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            if not message_id or not source_id or not state_version:
                return self._deny("message_fields_missing", message_id=message_id, source_id=source_id)
            if message_id in self._messages:
                return self._deny("message_already_exists", message_id=message_id)
            message = PropagationMessage(message_id, source_id, state_version, dict(payload))
            self._messages[message_id] = message
            self._received[(message_id, source_id)] = {
                "node_id": source_id,
                "sender_id": None,
                "depth": 0,
            }
            self._accepted.add((message_id, source_id))
            self._append(
                {"event": "message_injected", "message_id": message_id, "message": message.to_dict()}
            )
            return {"ok": True, "message": message.to_dict()}

    def remove_edge(self, left: str, right: str, *, intervention_id: str) -> dict[str, Any]:
        with self._lock:
            edge = _edge(left, right)
            if edge not in self._edges:
                return self._deny("edge_not_registered", left=left, right=right)
            self._removed_edges.add(edge)
            self._append(
                {
                    "event": "edge_removed",
                    "left": left,
                    "right": right,
                    "intervention_id": intervention_id,
                }
            )
            return {"ok": True, "edge": list(edge), "intervention_id": intervention_id}

    def edge_active(self, left: str, right: str) -> bool:
        edge = _edge(left, right)
        return edge in self._edges and edge not in self._removed_edges

    def deliver(
        self, message_id: str, sender_id: str, receiver_id: str, *, drop: bool = False
    ) -> dict[str, Any]:
        with self._lock:
            if message_id not in self._messages:
                return self._deny("message_not_injected", message_id=message_id)
            if not self.edge_active(sender_id, receiver_id):
                return self._deny(
                    "edge_unavailable",
                    message_id=message_id,
                    sender_id=sender_id,
                    receiver_id=receiver_id,
                )
            sender_key = (message_id, sender_id)
            if sender_key not in self._received:
                return self._deny("sender_has_not_received", message_id=message_id, sender_id=sender_id)
            if sender_key not in self._accepted:
                return self._deny("sender_has_not_accepted", message_id=message_id, sender_id=sender_id)
            receiver_key = (message_id, receiver_id)
            if receiver_key in self._received:
                return self._deny("duplicate_delivery", message_id=message_id, receiver_id=receiver_id)
            depth = int(self._received[sender_key]["depth"]) + 1
            if drop:
                self._append(
                    {
                        "event": "message_dropped",
                        "message_id": message_id,
                        "sender_id": sender_id,
                        "receiver_id": receiver_id,
                        "depth": depth,
                    }
                )
                return {"ok": True, "dropped": True, "depth": depth}
            receipt = {"node_id": receiver_id, "sender_id": sender_id, "depth": depth}
            self._received[receiver_key] = receipt
            self._append(
                {
                    "event": "message_delivered",
                    "message_id": message_id,
                    "sender_id": sender_id,
                    "receiver_id": receiver_id,
                    "depth": depth,
                }
            )
            return {"ok": True, "dropped": False, "receipt": dict(receipt)}

    def accept(self, message_id: str, node_id: str, *, accepted: bool = True) -> dict[str, Any]:
        with self._lock:
            key = (message_id, node_id)
            if key not in self._received:
                return self._deny("message_not_received", message_id=message_id, node_id=node_id)
            event = "message_accepted" if accepted else "message_rejected"
            if accepted:
                self._accepted.add(key)
            else:
                self._accepted.discard(key)
            self._append({"event": event, "message_id": message_id, "node_id": node_id})
            return {"ok": True, "accepted": accepted}

    def submit_action(self, node_id: str, action: str, *, message_id: str | None) -> dict[str, Any]:
        with self._lock:
            if message_id:
                key = (message_id, node_id)
                if key not in self._received or key not in self._accepted:
                    return self._deny(
                        "action_evidence_not_adopted",
                        node_id=node_id,
                        message_id=message_id,
                    )
            elif action != "keep_current":
                return self._deny("action_evidence_missing", node_id=node_id, action=action)
            action_id = f"network-action-{node_id}-{self._seq + 1}"
            payload = {
                "action_id": action_id,
                "node_id": node_id,
                "action": action,
                "evidence_message_id": message_id,
            }
            self._actions[node_id] = payload
            self._append({"event": "action_submitted", "node_id": node_id, "action": payload})
            return {"ok": True, "action": dict(payload)}

    def received_by(self, message_id: str, node_id: str) -> bool:
        return (message_id, node_id) in self._received

    def accepted_by(self, message_id: str, node_id: str) -> bool:
        return (message_id, node_id) in self._accepted

    def path_to(self, message_id: str, node_id: str) -> list[str]:
        key = (message_id, node_id)
        if key not in self._received:
            return []
        path = [node_id]
        current = self._received[key]
        while current.get("sender_id"):
            sender = str(current["sender_id"])
            path.append(sender)
            current = self._received.get((message_id, sender), {})
        return list(reversed(path))

    def action_of(self, node_id: str) -> dict[str, Any] | None:
        action = self._actions.get(node_id)
        return dict(action) if action else None

    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def event_names(self) -> list[str]:
        return [str(event.get("event") or "") for event in self._events]

    def denials(self) -> list[dict[str, Any]]:
        return list(self._denials)


__all__ = ["NetworkPropagationChannel", "PropagationMessage"]
