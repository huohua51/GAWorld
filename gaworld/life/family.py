"""FamilyCareChannel — inject a registered care event, deliver it, submit care.

The agent submits a flat care action. The environment does not assign the
caregiver, rewrite the conflict slot, or post household expenses.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional

from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.life.family")

Role = Literal["agent", "environment"]
NONE = "NONE"
ACTIONS = ("keep_schedule", "provide_care")
SCHEDULE_DECISIONS = ("keep", "cancel", "reschedule")
ACTION_FIELDS = (
    "action",
    "caregiver_id",
    "patient_id",
    "event_id",
    "slot_id",
    "schedule_decision",
    "expense_amount",
    "adopted_state_version",
    "evidence_event_id",
)


def _version_rank(version: str | None) -> int:
    if not version:
        return -1
    text = str(version).strip().lower()
    if text.startswith("v") and text[1:].isdigit():
        return int(text[1:])
    return -1


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("expense_amount cannot be bool")
    return int(value)


@dataclass
class CareAction:
    action: str
    caregiver_id: str
    patient_id: str
    event_id: str
    slot_id: str
    schedule_decision: str
    expense_amount: int
    adopted_state_version: str
    evidence_event_id: str
    task_id: str = ""
    agent_id: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CareAction":
        missing = [key for key in ACTION_FIELDS if key not in payload]
        if missing:
            raise ValueError(f"missing fields: {missing}")
        return cls(
            action=str(payload["action"]),
            caregiver_id=str(payload["caregiver_id"]),
            patient_id=str(payload["patient_id"]),
            event_id=str(payload["event_id"]),
            slot_id=str(payload["slot_id"]),
            schedule_decision=str(payload["schedule_decision"]),
            expense_amount=_as_int(payload["expense_amount"]),
            adopted_state_version=str(payload["adopted_state_version"]),
            evidence_event_id=str(payload["evidence_event_id"]),
            task_id=str(payload.get("task_id", "")),
            agent_id=int(payload.get("agent_id", 0) or 0),
        )


class FamilyCareChannel:
    """jsonl-audited household care event + schedule/expense channel."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._household: dict[str, dict[str, Any]] = {}
        self._schedule: dict[str, list[dict[str, Any]]] = {}
        self._injected: dict[str, dict[str, Any]] = {}
        self._packaged: dict[str, dict[str, Any]] = {}
        self._inbox: dict[str, list[dict[str, Any]]] = {}
        self._adopted: dict[str, str] = {}
        self._actions: dict[str, CareAction] = {}
        self._expenses: dict[str, list[dict[str, Any]]] = {}
        self._responsibility: dict[str, str] = {}
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
                _LOG.warning("dropping malformed family line in %s", self.path)
                continue
            self._replay(event)
            self._events.append(event)

    def _replay(self, event: dict[str, Any]) -> None:
        kind = event.get("event")
        task_id = str(event.get("task_id", ""))
        if kind == "household_registered":
            self._household[task_id] = dict(event.get("household") or {})
        elif kind == "schedule_set":
            self._schedule[task_id] = [dict(item) for item in (event.get("slots") or [])]
        elif kind == "care_event_injected":
            self._injected[task_id] = dict(event.get("payload") or {})
        elif kind == "perception_packaged":
            self._packaged[task_id] = dict(event.get("notice") or {})
        elif kind == "perception_delivered":
            self._inbox.setdefault(task_id, []).append(dict(event.get("notice") or {}))
        elif kind == "current_state_seeded":
            self._inbox.setdefault(task_id, []).append(dict(event.get("notice") or {}))
        elif kind == "event_adopted":
            self._adopted[task_id] = str(event.get("event_id", ""))
        elif kind == "action_submitted":
            try:
                action = CareAction.from_dict(event.get("action") or {})
            except (KeyError, ValueError, TypeError):
                return
            self._actions[task_id] = action
            self._apply_action(task_id, action)

    def register_household(self, task_id: str, household: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            packed = dict(household)
            packed.setdefault("requires_care", False)
            self._household[task_id] = packed
            self._append({"event": "household_registered", "task_id": task_id, "household": packed})
            return {"ok": True, "household": packed}

    def set_schedule(self, task_id: str, slots: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            copied = [dict(item) for item in slots]
            self._schedule[task_id] = copied
            self._append({"event": "schedule_set", "task_id": task_id, "slots": copied})
            return {"ok": True, "slots": copied}

    def inject_event(
        self,
        task_id: str,
        *,
        requires_care: bool,
        state_version: str,
        patient_id: str,
        caregiver_id: str,
        slot_id: str,
        expense_amount: int,
    ) -> dict[str, Any]:
        with self._lock:
            household = self._household.get(task_id)
            if not household:
                return self._deny("household_not_registered", task_id=task_id)
            self._seq += 1
            payload = {
                "event_id": f"care-evt-{task_id}-{self._seq}",
                "requires_care": bool(requires_care),
                "state_version": state_version,
                "patient_id": patient_id,
                "legal_caregiver_id": caregiver_id,
                "slot_id": slot_id,
                "expense_amount": int(expense_amount),
                "kind": "care_needed" if requires_care else "household_idle",
            }
            household["requires_care"] = bool(requires_care)
            self._injected[task_id] = payload
            self._append({"event": "care_event_injected", "task_id": task_id, "payload": payload})
            return {"ok": True, "payload": payload}

    def package_perception(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            injected = self._injected.get(task_id)
            if not injected:
                return self._deny("care_event_not_injected", task_id=task_id)
            notice = dict(injected)
            notice["kind"] = "family_event"
            self._packaged[task_id] = notice
            self._append({"event": "perception_packaged", "task_id": task_id, "notice": notice})
            return {"ok": True, "notice": notice}

    def deliver_perception(self, task_id: str, *, drop: bool = False) -> dict[str, Any]:
        with self._lock:
            notice = self._packaged.get(task_id)
            if notice is None:
                return self._deny("perception_not_packaged", task_id=task_id)
            if drop:
                self._append({
                    "event": "perception_dropped",
                    "task_id": task_id,
                    "dropped": True,
                    "notice": notice,
                })
                return {"ok": True, "dropped": True, "event_id": notice["event_id"]}
            self._inbox.setdefault(task_id, []).append(dict(notice))
            self._append({"event": "perception_delivered", "task_id": task_id, "dropped": False, "notice": notice})
            return {"ok": True, "dropped": False, "event_id": notice["event_id"]}

    def seed_direct(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            injected = self._injected.get(task_id)
            household = self._household.get(task_id)
            if not injected or not household:
                return self._deny("care_event_not_injected", task_id=task_id)
            notice = dict(injected)
            notice["direct"] = True
            notice["kind"] = "current_household_state"
            notice["household"] = {
                "legal_caregiver_id": household.get("legal_caregiver_id"),
                "patient_id": household.get("patient_id"),
                "conflict_slot_id": household.get("conflict_slot_id"),
                "registered_expense": household.get("registered_expense"),
                "requires_care": injected.get("requires_care"),
            }
            self._inbox.setdefault(task_id, []).append(dict(notice))
            self._append({"event": "current_state_seeded", "task_id": task_id, "notice": notice})
            return {"ok": True, "notice": notice}

    def read_perception(self, task_id: str, reader_role: Role) -> dict[str, Any]:
        with self._lock:
            if reader_role != "agent":
                return self._deny("unauthorized_perception_read", task_id=task_id, role=reader_role)
            items = [dict(item) for item in self._inbox.get(task_id, [])]
            self._append({"event": "perception_read", "task_id": task_id, "n": len(items)})
            return {"ok": True, "notices": items}

    def adopt_event(self, task_id: str, event_id: str, *, current_version: str | None = None) -> dict[str, Any]:
        with self._lock:
            if event_id in {None, "", NONE}:
                return self._deny("care_event_not_delivered", task_id=task_id, event_id=event_id)
            if self._adopted.get(task_id) == event_id:
                return self._deny("event_already_adopted", task_id=task_id, event_id=event_id)
            inbox = self._inbox.get(task_id) or []
            match = next((item for item in inbox if item.get("event_id") == event_id), None)
            if match is None:
                return self._deny("care_event_not_delivered", task_id=task_id, event_id=event_id)
            incoming = str(match.get("state_version", ""))
            if current_version and _version_rank(incoming) < _version_rank(current_version):
                return self._deny("stale_family_state_used", task_id=task_id, incoming=incoming, current=current_version)
            self._adopted[task_id] = event_id
            self._append({
                "event": "event_adopted",
                "task_id": task_id,
                "event_id": event_id,
                "state_version": incoming,
            })
            return {"ok": True, "notice": dict(match)}

    def _slot(self, task_id: str, slot_id: str) -> Optional[dict[str, Any]]:
        for slot in self._schedule.get(task_id, []):
            if slot.get("slot_id") == slot_id:
                return slot
        return None

    def _apply_action(self, task_id: str, action: CareAction) -> None:
        slot = self._slot(task_id, action.slot_id)
        if slot is not None:
            slot["schedule_decision"] = action.schedule_decision
            if action.schedule_decision == "keep":
                slot["status"] = slot.get("status") or "planned"
            elif action.schedule_decision == "cancel":
                slot["status"] = "cancelled"
            elif action.schedule_decision == "reschedule":
                slot["status"] = "rescheduled"
        if action.action == "provide_care" and action.caregiver_id not in {NONE, ""}:
            self._responsibility[task_id] = action.caregiver_id
        if int(action.expense_amount) > 0:
            self._expenses.setdefault(task_id, []).append({
                "amount": int(action.expense_amount),
                "event_id": action.event_id,
                "evidence_event_id": action.evidence_event_id,
            })

    def submit_action(self, task_id: str, *, agent_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                action = CareAction.from_dict({**payload, "task_id": task_id, "agent_id": agent_id})
            except (KeyError, ValueError, TypeError) as exc:
                return self._deny("fields_not_extractable", task_id=task_id, detail=str(exc))
            household = self._household.get(task_id) or {}
            legal = str(household.get("legal_caregiver_id") or "")
            if action.action == "provide_care" and legal and action.caregiver_id not in {legal, NONE, str(household.get("distractor_id") or "")}:
                return self._deny("wrong_caregiver_selected", task_id=task_id, caregiver_id=action.caregiver_id)
            self._actions[task_id] = action
            self._apply_action(task_id, action)
            self._append({"event": "action_submitted", "task_id": task_id, "action": action.to_dict()})
            return {"ok": True, "action": action.to_dict()}

    def reject_submit(self, task_id: str, role: Role) -> dict[str, Any]:
        with self._lock:
            if role == "agent":
                return self._deny("submit_requires_payload", task_id=task_id)
            return self._deny("environment_assigned_caregiver", task_id=task_id, role=role)

    def assign_caregiver(self, task_id: str, role: Role, caregiver_id: str) -> dict[str, Any]:
        with self._lock:
            if role != "agent":
                return self._deny("environment_assigned_caregiver", task_id=task_id, role=role, caregiver_id=caregiver_id)
            self._responsibility[task_id] = caregiver_id
            return {"ok": True, "caregiver_id": caregiver_id}

    def household_of(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._household.get(task_id) or {})

    def schedule_of(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._schedule.get(task_id, [])]

    def slot_of(self, task_id: str, slot_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            slot = self._slot(task_id, slot_id)
            return dict(slot) if slot else None

    def expenses_of(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._expenses.get(task_id, [])]

    def responsibility_of(self, task_id: str) -> Optional[str]:
        with self._lock:
            return self._responsibility.get(task_id)

    def action_of(self, task_id: str) -> Optional[CareAction]:
        with self._lock:
            return self._actions.get(task_id)

    def injected_of(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            item = self._injected.get(task_id)
            return dict(item) if item else None

    def adopted_of(self, task_id: str) -> Optional[str]:
        with self._lock:
            return self._adopted.get(task_id)

    def inbox_of(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._inbox.get(task_id, [])]

    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def event_names(self) -> list[str]:
        return [str(event.get("event")) for event in self.events()]

    def denials(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._denials)


__all__ = ["ACTION_FIELDS", "ACTIONS", "CareAction", "FamilyCareChannel", "NONE", "SCHEDULE_DECISIONS"]
