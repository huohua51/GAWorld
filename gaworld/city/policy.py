"""Audited policy activation and resident-action channel.

The environment may register and activate a policy, but only an explicit
resident action can change resident state.  This keeps policy exposure,
behavioural response and system outcome as separate traceable stages.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PolicyEvent:
    """A versioned external event with an auditable target population."""

    policy_id: str
    policy_version: str
    effective_step: int
    condition: str
    target_groups: tuple[str, ...]
    signal: dict[str, Any]

    def __post_init__(self) -> None:
        if self.condition not in {"real_policy", "placebo_policy"}:
            raise ValueError("condition must be real_policy or placebo_policy")
        if not self.policy_id or not self.policy_version:
            raise ValueError("policy_id and policy_version are required")
        if self.effective_step < 0:
            raise ValueError("effective_step must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["target_groups"] = list(self.target_groups)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PolicyEvent:
        return cls(
            policy_id=str(payload["policy_id"]),
            policy_version=str(payload["policy_version"]),
            effective_step=int(payload["effective_step"]),
            condition=str(payload["condition"]),
            target_groups=tuple(str(item) for item in payload.get("target_groups") or []),
            signal=dict(payload.get("signal") or {}),
        )


class UrbanPolicyChannel:
    """Persist policy timing, perception, resident action and state effects."""

    def __init__(
        self,
        path: str,
        residents: list[Mapping[str, Any]],
        action_effects: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._action_effects = {str(action): dict(effects) for action, effects in action_effects.items()}
        self._action_effects.setdefault("keep_current", {})
        self._baseline: dict[str, dict[str, Any]] = {}
        self._state: dict[str, dict[str, Any]] = {}
        self._groups: dict[str, str] = {}
        self._policies: dict[str, PolicyEvent] = {}
        self._active: set[str] = set()
        self._perceived: set[tuple[str, str]] = set()
        self._actions: dict[str, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []
        self._denials: list[dict[str, Any]] = []
        self._step = 0
        self._seq = 0
        if self.path and os.path.exists(self.path) and os.path.getsize(self.path) > 0:
            self._load()
        else:
            self._register_population(residents)

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

    def _register_population(self, residents: list[Mapping[str, Any]]) -> None:
        normalized: list[dict[str, Any]] = []
        for resident in residents:
            agent_id = str(resident.get("agent_id") or "")
            group = str(resident.get("group") or "")
            state = dict(resident.get("state") or {})
            if not agent_id or not group or not state:
                raise ValueError("each resident requires agent_id, group and non-empty state")
            if agent_id in self._state:
                raise ValueError(f"duplicate resident: {agent_id}")
            self._baseline[agent_id] = dict(state)
            self._state[agent_id] = dict(state)
            self._groups[agent_id] = group
            normalized.append({"agent_id": agent_id, "group": group, "state": state})
        if not normalized:
            raise ValueError("at least one resident is required")
        self._append({"event": "population_registered", "residents": normalized})

    def _load(self) -> None:
        with open(self.path, encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        for row in rows:
            self._replay(row)
            self._events.append(row)
            self._seq = max(self._seq, int(row.get("seq") or 0))

    def _replay(self, event: Mapping[str, Any]) -> None:
        kind = str(event.get("event") or "")
        if kind == "population_registered":
            for resident in event.get("residents") or []:
                agent_id = str(resident["agent_id"])
                state = dict(resident["state"])
                self._baseline[agent_id] = dict(state)
                self._state[agent_id] = dict(state)
                self._groups[agent_id] = str(resident["group"])
        elif kind == "policy_registered":
            policy = PolicyEvent.from_dict(dict(event.get("policy") or {}))
            self._policies[policy.policy_id] = policy
        elif kind == "clock_advanced":
            self._step = int(event.get("step") or 0)
        elif kind == "policy_activated":
            self._active.add(str(event.get("policy_id") or ""))
        elif kind == "policy_perceived":
            self._perceived.add((str(event.get("policy_id") or ""), str(event.get("agent_id") or "")))
        elif kind == "resident_action_submitted":
            agent_id = str(event.get("agent_id") or "")
            self._state[agent_id] = dict(event.get("state_after") or {})
            self._actions[agent_id] = dict(event.get("action_record") or {})

    def register_policy(self, policy: PolicyEvent) -> dict[str, Any]:
        with self._lock:
            if policy.policy_id in self._policies:
                return self._deny("policy_already_registered", policy_id=policy.policy_id)
            self._policies[policy.policy_id] = policy
            self._append({"event": "policy_registered", "policy": policy.to_dict()})
            return {"ok": True, "policy": policy.to_dict()}

    def advance_to(self, step: int) -> dict[str, Any]:
        with self._lock:
            if step < self._step:
                return self._deny("clock_cannot_reverse", current_step=self._step, requested=step)
            self._step = int(step)
            self._append({"event": "clock_advanced", "step": self._step})
            activated: list[str] = []
            for policy in self._policies.values():
                if policy.policy_id not in self._active and policy.effective_step <= self._step:
                    self._active.add(policy.policy_id)
                    activated.append(policy.policy_id)
                    self._append(
                        {
                            "event": "policy_activated",
                            "policy_id": policy.policy_id,
                            "policy_version": policy.policy_version,
                            "step": self._step,
                        }
                    )
            return {"ok": True, "step": self._step, "activated": activated}

    def perceive(self, policy_id: str, agent_id: str) -> dict[str, Any]:
        with self._lock:
            if agent_id not in self._state:
                return self._deny("resident_not_registered", agent_id=agent_id)
            if policy_id not in self._active:
                return self._deny("policy_not_active", policy_id=policy_id, agent_id=agent_id)
            policy = self._policies[policy_id]
            eligible = self._groups[agent_id] in set(policy.target_groups)
            self._perceived.add((policy_id, agent_id))
            self._append(
                {
                    "event": "policy_perceived",
                    "policy_id": policy_id,
                    "agent_id": agent_id,
                    "eligible": eligible,
                }
            )
            return {
                "ok": True,
                "policy_id": policy_id,
                "signal": dict(policy.signal),
                "eligible": eligible,
            }

    def submit_action(self, agent_id: str, action: str, *, evidence_policy_id: str | None) -> dict[str, Any]:
        with self._lock:
            if agent_id not in self._state:
                return self._deny("resident_not_registered", agent_id=agent_id)
            if action not in self._action_effects:
                return self._deny("action_not_registered", agent_id=agent_id, action=action)
            if action != "keep_current":
                evidence_key = (str(evidence_policy_id or ""), agent_id)
                if evidence_key not in self._perceived:
                    return self._deny(
                        "action_evidence_not_perceived",
                        agent_id=agent_id,
                        policy_id=evidence_policy_id,
                    )
            before = dict(self._state[agent_id])
            after = dict(before)
            after.update(self._action_effects[action])
            action_id = f"policy-action-{agent_id}-{self._seq + 1}"
            record = {
                "action_id": action_id,
                "agent_id": agent_id,
                "action": action,
                "evidence_policy_id": evidence_policy_id,
                "changed_fields": sorted(field for field in after if before.get(field) != after.get(field)),
            }
            self._state[agent_id] = after
            self._actions[agent_id] = record
            self._append(
                {
                    "event": "resident_action_submitted",
                    "agent_id": agent_id,
                    "action_record": record,
                    "state_before": before,
                    "state_after": after,
                }
            )
            return {"ok": True, "action": dict(record), "state": dict(after)}

    def is_targeted(self, policy_id: str, agent_id: str) -> bool:
        policy = self._policies.get(policy_id)
        return bool(policy and self._groups.get(agent_id) in set(policy.target_groups))

    def policy_active(self, policy_id: str) -> bool:
        return policy_id in self._active

    def baseline_of(self, agent_id: str) -> dict[str, Any]:
        return dict(self._baseline[agent_id])

    def state_of(self, agent_id: str) -> dict[str, Any]:
        return dict(self._state[agent_id])

    def action_of(self, agent_id: str) -> dict[str, Any] | None:
        action = self._actions.get(agent_id)
        return dict(action) if action else None

    def resident_ids(self) -> list[str]:
        return list(self._state)

    def event_names(self) -> list[str]:
        return [str(event.get("event") or "") for event in self._events]

    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def denials(self) -> list[dict[str, Any]]:
        return list(self._denials)


__all__ = ["PolicyEvent", "UrbanPolicyChannel"]
