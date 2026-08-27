"""TrustLedger — history-private trust formation and update.

The outcome history lives only with the TrustUpdater. The Dispatcher
may adopt a delivered trust state and submit an action. TrustUpdater
cannot submit. Dispatcher cannot read the history ledger.
Stale or duplicate trust messages are rejected. Adopting trust writes
GAWorld relationship_update so interpersonal trust is not a sidecar.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional

from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.comm.trust")

Role = Literal["observer", "trust_updater", "dispatcher", "environment"]
RoundName = Literal["formation", "update"]

ACTION_FIELDS = ("action", "value", "adopted_trust_version", "evidence_message_id", "round")
TRUST_FIELDS = ("trusted_person_id", "trusted_state", "trust_version")


def _version_rank(version: str | None) -> int:
    if not version:
        return -1
    text = str(version).strip().lower()
    if text.startswith("v") and text[1:].isdigit():
        return int(text[1:])
    return -1


def _apply_relationship(agent: dict[str, Any], trusted_id: str, untrusted_id: str) -> dict[str, Any]:
    from human_realism import relationship_update

    if trusted_id:
        relationship_update(agent, trusted_id, "positive", {})
    if untrusted_id and untrusted_id != trusted_id:
        relationship_update(agent, untrusted_id, "negative", {})
    return dict(agent.get("relationships") or {})


@dataclass
class TrustAction:
    action: str
    value: str
    adopted_trust_version: str
    evidence_message_id: str
    round: str
    task_id: str = ""
    dispatcher_id: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TrustAction":
        missing = [k for k in ACTION_FIELDS if k not in payload]
        if missing:
            raise ValueError(f"missing fields: {missing}")
        return cls(
            action=str(payload["action"]),
            value=str(payload["value"]),
            adopted_trust_version=str(payload["adopted_trust_version"]),
            evidence_message_id=str(payload["evidence_message_id"]),
            round=str(payload["round"]),
            task_id=str(payload.get("task_id", "")),
            dispatcher_id=int(payload.get("dispatcher_id", 0) or 0),
        )


class TrustLedger:
    """jsonl-audited trust ledger with private history isolation."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._history: dict[str, list[dict[str, Any]]] = {}
        self._private: dict[tuple[str, Role], dict[str, Any]] = {}
        self._current: dict[str, list[dict[str, Any]]] = {}
        self._current_inbox: dict[str, list[dict[str, Any]]] = {}
        self._trust: dict[str, dict[str, Any]] = {}
        self._inbox: dict[str, list[dict[str, Any]]] = {}
        self._adopted: dict[str, list[str]] = {}
        self._adopted_version: dict[str, str] = {}
        self._actions: dict[tuple[str, str], TrustAction] = {}
        self._agents: dict[str, dict[str, Any]] = {}
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
                _LOG.warning("dropping malformed trust line in %s", self.path)
                continue
            self._replay(event)
            self._events.append(event)

    def _replay(self, event: dict[str, Any]) -> None:
        kind = event.get("event")
        task_id = str(event.get("task_id", ""))
        if kind == "history_put":
            self._history[task_id] = [dict(item) for item in (event.get("rounds") or [])]
        elif kind == "outcome_appended":
            self._history.setdefault(task_id, []).append(dict(event.get("outcome") or {}))
        elif kind == "private_put":
            role = event.get("role")
            if role:
                self._private[(task_id, role)] = dict(event.get("payload") or {})
        elif kind == "current_sent":
            self._current.setdefault(task_id, []).append(dict(event.get("message") or {}))
        elif kind == "current_delivered":
            self._current_inbox.setdefault(task_id, []).append(dict(event.get("message") or {}))
        elif kind == "trust_emitted":
            self._trust[task_id] = dict(event.get("message") or {})
        elif kind == "trust_delivered":
            self._inbox.setdefault(task_id, []).append(dict(event.get("message") or {}))
        elif kind == "trust_adopted":
            self._adopted.setdefault(task_id, []).append(str(event.get("message_id", "")))
            if event.get("trust_version"):
                self._adopted_version[task_id] = str(event.get("trust_version"))
        elif kind == "action_submitted":
            try:
                action = TrustAction.from_dict(event.get("action") or {})
            except (KeyError, ValueError, TypeError):
                return
            self._actions[(task_id, action.round)] = action
        elif kind == "agent_bound":
            self._agents[task_id] = dict(event.get("agent") or {"relationships": {}, "current_day": 1})

    def bind_agent(self, task_id: str, agent: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            payload = dict(agent or {"relationships": {}, "current_day": 1})
            payload.setdefault("relationships", {})
            payload.setdefault("current_day", 1)
            self._agents[task_id] = payload
            self._append({"event": "agent_bound", "task_id": task_id, "agent": payload})
            return {"ok": True, "task_id": task_id}

    def relationships_of(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            agent = self._agents.get(task_id) or {}
            return json.loads(json.dumps(agent.get("relationships") or {}))

    def put_private(self, task_id: str, owner_role: Role, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if owner_role not in {"observer", "trust_updater", "dispatcher"}:
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

    def put_history(self, task_id: str, owner_role: Role, rounds: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            if owner_role != "trust_updater":
                return self._deny("unauthorized_history_write", task_id=task_id, role=owner_role)
            packed = [dict(item) for item in rounds]
            self._history[task_id] = packed
            self._append({"event": "history_put", "task_id": task_id, "rounds": packed})
            return {"ok": True, "n": len(packed)}

    def append_outcome(self, task_id: str, owner_role: Role, outcome: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if owner_role != "trust_updater":
                return self._deny("unauthorized_history_write", task_id=task_id, role=owner_role)
            row = dict(outcome)
            self._history.setdefault(task_id, []).append(row)
            self._append({"event": "outcome_appended", "task_id": task_id, "outcome": row})
            return {"ok": True, "n": len(self._history[task_id])}

    def read_history(self, task_id: str, reader_role: Role) -> dict[str, Any]:
        with self._lock:
            if reader_role != "trust_updater":
                return self._deny("unauthorized_history_read", task_id=task_id, role=reader_role)
            rounds = [dict(item) for item in self._history.get(task_id, [])]
            self._append({"event": "history_read", "task_id": task_id, "n": len(rounds)})
            return {"ok": True, "rounds": rounds}

    def send_current(self, task_id: str, *, observer_id: int, message: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            packed = {
                "message_id": str(message.get("message_id") or f"cur-msg-{task_id}-{self._seq}"),
                "person_id": str(message.get("person_id") or message.get("source_id") or ""),
                "reported_state": str(message.get("reported_state", "")),
                "observer_id": observer_id,
            }
            if not packed["person_id"] or not packed["reported_state"]:
                return self._deny("observation_not_created", task_id=task_id)
            self._current.setdefault(task_id, []).append(packed)
            self._append({"event": "current_sent", "task_id": task_id, "message": packed})
            return {"ok": True, "message": packed}

    def deliver_current(self, task_id: str, *, to_role: Role = "trust_updater") -> dict[str, Any]:
        with self._lock:
            if to_role not in {"trust_updater", "dispatcher"}:
                return self._deny("current_bad_recipient", task_id=task_id, role=to_role)
            items = [dict(item) for item in self._current.get(task_id, [])]
            if not items:
                return self._deny("current_signal_not_sent", task_id=task_id)
            if to_role == "trust_updater":
                self._current_inbox[task_id] = items
                for item in items:
                    self._append({"event": "current_delivered", "task_id": task_id, "message": item})
            else:
                self._append({"event": "current_to_dispatcher", "task_id": task_id, "messages": items})
            return {"ok": True, "messages": items}

    def read_current_inbox(self, task_id: str, reader_role: Role) -> dict[str, Any]:
        with self._lock:
            if reader_role != "trust_updater":
                return self._deny("unauthorized_current_inbox_read", task_id=task_id, role=reader_role)
            items = [dict(item) for item in self._current_inbox.get(task_id, [])]
            self._append({"event": "current_inbox_read", "task_id": task_id, "n": len(items)})
            return {"ok": True, "messages": items}

    def seed_focused(
        self,
        task_id: str,
        *,
        trusted_person_id: str,
        trusted_state: str,
        version: str,
        other_person_id: str = "",
        round_name: str = "formation",
    ) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            message = {
                "message_id": f"trust-msg-{task_id}-{self._seq}",
                "trusted_person_id": trusted_person_id,
                "trusted_state": trusted_state,
                "trust_version": version,
                "other_person_id": other_person_id,
                "evidence_count": 0,
                "updater_id": 0,
                "round": round_name,
                "focused": True,
            }
            self._trust[task_id] = message
            self._inbox.setdefault(task_id, []).append(dict(message))
            self._append({"event": "trust_emitted", "task_id": task_id, "message": message})
            self._append({"event": "trust_delivered", "task_id": task_id, "dropped": False, "message": message})
            return {"ok": True, "message": message}

    def emit_trust(self, task_id: str, *, updater_id: int, payload: dict[str, Any], round_name: str = "formation") -> dict[str, Any]:
        with self._lock:
            history = self._history.get(task_id) or []
            if not history:
                return self._deny("history_not_available", task_id=task_id)
            if not self._current_inbox.get(task_id):
                return self._deny("trust_not_requested", task_id=task_id)
            person = str(payload.get("trusted_person_id") or "")
            state = str(payload.get("trusted_state") or payload.get("state") or "")
            version = str(payload.get("trust_version") or payload.get("state_version") or payload.get("version") or "")
            if not person or not state or not version:
                return self._deny("trust_message_not_emitted", task_id=task_id, detail="missing fields")
            other = str(payload.get("other_person_id") or "")
            if not other:
                currents = self._current_inbox.get(task_id) or []
                other = next(
                    (str(item.get("person_id")) for item in currents if str(item.get("person_id")) != person),
                    "",
                )
            self._seq += 1
            message = {
                "message_id": f"trust-msg-{task_id}-{self._seq}",
                "trusted_person_id": person,
                "trusted_state": state,
                "trust_version": version,
                "other_person_id": other,
                "evidence_count": int(payload.get("evidence_count") or len(history)),
                "updater_id": updater_id,
                "round": round_name,
            }
            self._trust[task_id] = message
            self._append({"event": "trust_emitted", "task_id": task_id, "message": message})
            return {"ok": True, "message": message}

    def deliver_trust(self, task_id: str, *, drop: bool = False) -> dict[str, Any]:
        with self._lock:
            message = self._trust.get(task_id)
            if message is None:
                return self._deny("trust_message_not_emitted", task_id=task_id)
            record = {
                "event": "trust_dropped" if drop else "trust_delivered",
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

    def adopt_trust(self, task_id: str, message_id: str, *, current_version: str | None = None) -> dict[str, Any]:
        with self._lock:
            adopted = self._adopted.setdefault(task_id, [])
            if message_id in adopted:
                return self._deny("trust_already_adopted", task_id=task_id, message_id=message_id)
            inbox = self._inbox.get(task_id) or []
            match = next((item for item in inbox if item.get("message_id") == message_id), None)
            if match is None:
                return self._deny("trust_message_not_delivered", task_id=task_id, message_id=message_id)
            incoming = str(match.get("trust_version", ""))
            if current_version and _version_rank(incoming) < _version_rank(current_version):
                return self._deny(
                    "stale_trust_used",
                    task_id=task_id,
                    incoming=incoming,
                    current=current_version,
                )
            latest = self._adopted_version.get(task_id)
            if latest and _version_rank(incoming) < _version_rank(latest):
                return self._deny("stale_trust_used", task_id=task_id, incoming=incoming, current=latest)
            adopted.append(message_id)
            self._adopted_version[task_id] = incoming
            agent = self._agents.setdefault(task_id, {"relationships": {}, "current_day": 1})
            rel = _apply_relationship(
                agent,
                str(match.get("trusted_person_id") or ""),
                str(match.get("other_person_id") or ""),
            )
            self._append({
                "event": "trust_adopted",
                "task_id": task_id,
                "message_id": message_id,
                "trust_version": incoming,
                "relationships": rel,
            })
            return {"ok": True, "message": dict(match), "relationships": rel}

    def submit_action(self, task_id: str, *, dispatcher_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                action = TrustAction.from_dict({**payload, "task_id": task_id, "dispatcher_id": dispatcher_id})
            except (KeyError, ValueError, TypeError) as exc:
                return self._deny("target_action_incorrect", task_id=task_id, detail=str(exc))
            self._actions[(task_id, action.round)] = action
            self._append({"event": "action_submitted", "task_id": task_id, "action": action.to_dict()})
            return {"ok": True, "action": action.to_dict()}

    def submit_bound_action(
        self,
        task_id: str,
        *,
        dispatcher_id: int,
        message_id: str,
        selected_value: str,
        round_name: str,
    ) -> dict[str, Any]:
        """Submit a dispatcher choice bound to an adopted delivered trust message.

        The model chooses only the registered business value. The platform
        supplies the evidence message identifier, trust version, and action
        name from its own delivery/adoption state.
        """
        with self._lock:
            private = self._private.get((task_id, "dispatcher")) or {}
            action_name = str(private.get("action") or "")
            legal_values = {str(item) for item in (private.get("legal_values") or [])}
            if not action_name or not legal_values:
                return self._deny("dispatcher_contract_missing", task_id=task_id)
            value = str(selected_value or "")
            if value not in legal_values:
                return self._deny(
                    "selected_value_not_registered",
                    task_id=task_id,
                    selected_value=value,
                )
            inbox = self._inbox.get(task_id) or []
            message = next(
                (item for item in inbox if item.get("message_id") == message_id),
                None,
            )
            if message is None:
                return self._deny(
                    "trust_message_not_delivered",
                    task_id=task_id,
                    message_id=message_id,
                )
            if message_id not in (self._adopted.get(task_id) or []):
                return self._deny(
                    "trust_message_not_adopted",
                    task_id=task_id,
                    message_id=message_id,
                )
            message_round = str(message.get("round") or "")
            if str(round_name or "") != message_round:
                return self._deny(
                    "action_round_mismatch",
                    task_id=task_id,
                    expected=message_round,
                    observed=str(round_name or ""),
                )
            version = str(message.get("trust_version") or "")
            if version != self._adopted_version.get(task_id):
                return self._deny(
                    "stale_trust_used",
                    task_id=task_id,
                    incoming=version,
                    current=self._adopted_version.get(task_id),
                )
            payload = {
                "action": action_name,
                "value": value,
                "adopted_trust_version": version,
                "evidence_message_id": message_id,
                "round": message_round,
            }
            return self.submit_action(
                task_id,
                dispatcher_id=dispatcher_id,
                payload=payload,
            )

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

    def adopted_of(self, task_id: str) -> list[str]:
        with self._lock:
            return list(self._adopted.get(task_id) or [])

    def action_of(self, task_id: str, round_name: str) -> Optional[TrustAction]:
        with self._lock:
            return self._actions.get((task_id, round_name))

    def trust_of(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            item = self._trust.get(task_id)
            return dict(item) if item else None


__all__ = ["TrustAction", "TrustLedger"]
