"""VenueEventChannel — inject venue close/open, perceive, reroute a visit.

The agent submits a flat visit action. The environment does not choose the
destination or rewrite the schedule on the agent's behalf.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional

from city_map_system import distance_between, node_by_name, shortest_path
from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.life.venue")

Role = Literal["agent", "environment"]
ACTION_NAME = "update_visit"
ACTION_FIELDS = (
    "action",
    "destination",
    "slot_id",
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


def _minutes(hhmm: str) -> int:
    parts = str(hhmm or "").strip().split(":")
    return int(parts[0]) * 60 + int(parts[1])


def slots_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    try:
        a0, a1 = _minutes(left["start"]), _minutes(left["end"])
        b0, b1 = _minutes(right["start"]), _minutes(right["end"])
    except (KeyError, ValueError, TypeError, IndexError):
        return True
    return a0 < b1 and b0 < a1


@dataclass
class VisitAction:
    action: str
    destination: str
    slot_id: str
    adopted_state_version: str
    evidence_event_id: str
    task_id: str = ""
    agent_id: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "VisitAction":
        missing = [key for key in ACTION_FIELDS if key not in payload]
        if missing:
            raise ValueError(f"missing fields: {missing}")
        return cls(
            action=str(payload["action"]),
            destination=str(payload["destination"]),
            slot_id=str(payload["slot_id"]),
            adopted_state_version=str(payload["adopted_state_version"]),
            evidence_event_id=str(payload["evidence_event_id"]),
            task_id=str(payload.get("task_id", "")),
            agent_id=int(payload.get("agent_id", 0) or 0),
        )


class VenueEventChannel:
    """jsonl-audited venue status + schedule update channel."""

    def __init__(self, path: str, *, city_map: dict[str, Any] | None = None) -> None:
        self.path = path
        self.city_map = city_map or {}
        self._lock = threading.RLock()
        self._venues: dict[str, dict[str, dict[str, Any]]] = {}
        self._schedule: dict[str, list[dict[str, Any]]] = {}
        self._origin: dict[str, str] = {}
        self._required_type: dict[str, str] = {}
        self._slot_id: dict[str, str] = {}
        self._injected: dict[str, dict[str, Any]] = {}
        self._packaged: dict[str, dict[str, Any]] = {}
        self._inbox: dict[str, list[dict[str, Any]]] = {}
        self._adopted: dict[str, str] = {}
        self._actions: dict[str, VisitAction] = {}
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
                _LOG.warning("dropping malformed venue line in %s", self.path)
                continue
            self._replay(event)
            self._events.append(event)

    def _replay(self, event: dict[str, Any]) -> None:
        kind = event.get("event")
        task_id = str(event.get("task_id", ""))
        if kind == "venues_registered":
            self._venues[task_id] = dict(event.get("venues") or {})
            self._origin[task_id] = str(event.get("origin") or "")
            self._required_type[task_id] = str(event.get("required_type") or "")
            self._slot_id[task_id] = str(event.get("slot_id") or "")
        elif kind == "schedule_set":
            self._schedule[task_id] = [dict(item) for item in (event.get("slots") or [])]
        elif kind == "event_injected":
            self._injected[task_id] = dict(event.get("payload") or {})
            venue_id = str((event.get("payload") or {}).get("venue_id") or "")
            if venue_id and task_id in self._venues and venue_id in self._venues[task_id]:
                self._venues[task_id][venue_id]["status"] = (event.get("payload") or {}).get("status")
                self._venues[task_id][venue_id]["state_version"] = (event.get("payload") or {}).get("state_version")
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
                action = VisitAction.from_dict(event.get("action") or {})
            except (KeyError, ValueError, TypeError):
                return
            self._actions[task_id] = action
            self._apply_slot(task_id, action.slot_id, action.destination)

    def register_venues(
        self,
        task_id: str,
        venues: dict[str, dict[str, Any]],
        *,
        origin: str,
        required_type: str,
        slot_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            packed = {}
            for venue_id, spec in venues.items():
                packed[str(venue_id)] = {
                    "id": str(venue_id),
                    "type": str(spec.get("type") or required_type),
                    "status": str(spec.get("status") or "open"),
                    "state_version": str(spec.get("state_version") or "v1"),
                }
            self._venues[task_id] = packed
            self._origin[task_id] = origin
            self._required_type[task_id] = required_type
            self._slot_id[task_id] = slot_id
            self._append({
                "event": "venues_registered",
                "task_id": task_id,
                "venues": packed,
                "origin": origin,
                "required_type": required_type,
                "slot_id": slot_id,
            })
            return {"ok": True, "venues": packed}

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
        venue_id: str,
        status: str,
        state_version: str,
        slot_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            venues = self._venues.get(task_id)
            if not venues or venue_id not in venues:
                return self._deny("unknown_venue", task_id=task_id, venue_id=venue_id)
            self._seq += 1
            payload = {
                "event_id": f"venue-evt-{task_id}-{self._seq}",
                "venue_id": venue_id,
                "status": status,
                "state_version": state_version,
                "slot_id": slot_id,
            }
            venues[venue_id]["status"] = status
            venues[venue_id]["state_version"] = state_version
            self._injected[task_id] = payload
            self._append({"event": "event_injected", "task_id": task_id, "payload": payload})
            return {"ok": True, "payload": payload}

    def package_perception(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            injected = self._injected.get(task_id)
            if not injected:
                return self._deny("event_not_injected", task_id=task_id)
            notice = {
                "event_id": injected["event_id"],
                "venue_id": injected["venue_id"],
                "status": injected["status"],
                "state_version": injected["state_version"],
                "slot_id": injected["slot_id"],
                "kind": "venue_status",
            }
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
            venues = self._venues.get(task_id)
            if not injected or not venues:
                return self._deny("event_not_injected", task_id=task_id)
            notice = {
                "event_id": injected["event_id"],
                "venue_id": injected["venue_id"],
                "status": injected["status"],
                "state_version": injected["state_version"],
                "slot_id": injected["slot_id"],
                "kind": "current_venue_state",
                "direct": True,
                "venues": {vid: {"status": spec["status"], "type": spec["type"]} for vid, spec in venues.items()},
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
            if self._adopted.get(task_id) == event_id:
                return self._deny("event_already_adopted", task_id=task_id, event_id=event_id)
            inbox = self._inbox.get(task_id) or []
            match = next((item for item in inbox if item.get("event_id") == event_id), None)
            if match is None:
                return self._deny("event_not_delivered", task_id=task_id, event_id=event_id)
            incoming = str(match.get("state_version", ""))
            if current_version and _version_rank(incoming) < _version_rank(current_version):
                return self._deny("stale_state_used", task_id=task_id, incoming=incoming, current=current_version)
            self._adopted[task_id] = event_id
            self._append({
                "event": "event_adopted",
                "task_id": task_id,
                "event_id": event_id,
                "state_version": incoming,
            })
            return {"ok": True, "notice": dict(match)}

    def _apply_slot(self, task_id: str, slot_id: str, destination: str) -> None:
        slots = self._schedule.setdefault(task_id, [])
        for slot in slots:
            if slot.get("slot_id") == slot_id:
                slot["destination"] = destination
                return

    def submit_action(self, task_id: str, *, agent_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                action = VisitAction.from_dict({**payload, "task_id": task_id, "agent_id": agent_id})
            except (KeyError, ValueError, TypeError) as exc:
                return self._deny("fields_not_extractable", task_id=task_id, detail=str(exc))
            self._actions[task_id] = action
            self._apply_slot(task_id, action.slot_id, action.destination)
            self._append({"event": "action_submitted", "task_id": task_id, "action": action.to_dict()})
            return {"ok": True, "action": action.to_dict()}

    def reject_submit(self, task_id: str, role: Role) -> dict[str, Any]:
        with self._lock:
            if role == "agent":
                return self._deny("submit_requires_payload", task_id=task_id)
            return self._deny("unauthorized_action_submit", task_id=task_id, role=role)

    def rewrite_schedule(self, task_id: str, role: Role, slots: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            if role != "agent":
                return self._deny("environment_rewrote_schedule", task_id=task_id, role=role)
            return self.set_schedule(task_id, slots)

    def venue_of(self, task_id: str, venue_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            spec = (self._venues.get(task_id) or {}).get(venue_id)
            return dict(spec) if spec else None

    def schedule_of(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._schedule.get(task_id, [])]

    def slot_of(self, task_id: str, slot_id: str) -> Optional[dict[str, Any]]:
        for slot in self.schedule_of(task_id):
            if slot.get("slot_id") == slot_id:
                return slot
        return None

    def destination_open(self, task_id: str, destination: str) -> bool:
        spec = self.venue_of(task_id, destination)
        return bool(spec and spec.get("status") == "open")

    def type_match(self, task_id: str, destination: str) -> bool:
        spec = self.venue_of(task_id, destination)
        required = self._required_type.get(task_id)
        return bool(spec and required and spec.get("type") == required)

    def reachable(self, task_id: str, destination: str) -> bool:
        origin = self._origin.get(task_id)
        if not origin or not self.city_map:
            return False
        if node_by_name(self.city_map, destination) is None:
            return False
        path = shortest_path(self.city_map, origin, destination)
        if path:
            return True
        return distance_between(self.city_map, origin, destination) > 0

    def schedule_conflict(self, task_id: str) -> bool:
        slots = self.schedule_of(task_id)
        for i, left in enumerate(slots):
            for right in slots[i + 1 :]:
                if slots_overlap(left, right):
                    return True
        return False

    def old_schedule_overwritten(self, task_id: str, previous_destination: str, *, must_change: bool) -> bool:
        slot = self.slot_of(task_id, self._slot_id.get(task_id, ""))
        action = self._actions.get(task_id)
        if slot is None or action is None:
            return False
        if slot.get("destination") != action.destination:
            return False
        if not must_change:
            return True
        return slot.get("destination") != previous_destination

    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def event_names(self) -> list[str]:
        return [str(event.get("event")) for event in self.events()]

    def denials(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._denials)

    def injected_of(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            item = self._injected.get(task_id)
            return dict(item) if item else None

    def packaged_of(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            item = self._packaged.get(task_id)
            return dict(item) if item else None

    def action_of(self, task_id: str) -> Optional[VisitAction]:
        with self._lock:
            return self._actions.get(task_id)

    def adopted_of(self, task_id: str) -> Optional[str]:
        with self._lock:
            return self._adopted.get(task_id)

    def inbox_of(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._inbox.get(task_id, [])]


__all__ = ["ACTION_FIELDS", "ACTION_NAME", "VisitAction", "VenueEventChannel", "slots_overlap"]
