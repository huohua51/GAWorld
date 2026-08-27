"""Joint assignment channel: evidence in, agent proposes, environment never repairs.

The platform may report which constraint was violated. It must not tell
the agent which slot to take, and it must not rewrite the plan.
``actual_final_conflict_free`` is a scorer/world fact, never an agent hint.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from gaworld.logging_setup import get_logger
from gaworld.work.plan_registry import PlanRegistry

_LOG = get_logger("gaworld.work.coordination")

AGENT_ROLES = ("agent_a", "agent_b", "coordinator", "agent")
FORBIDDEN_AGENT_KEYS = (
    "suggested_slot",
    "suggested_assignment",
    "corrected_assignments",
    "oracle",
    "required_slot",
    "earliest_idle",
    "actual_final_conflict_free",
    "initial",
    "expected",
    "observed",
)
PRIORITY_VIOLATION = "priority_preservation_violation"


def occupancy_table(assignments: dict[str, str]) -> dict[str, list[str]]:
    table: dict[str, list[str]] = {}
    for agent_id, slot in (assignments or {}).items():
        table.setdefault(str(slot), []).append(str(agent_id))
    return table


def actual_final_conflict_free(assignments: dict[str, str]) -> bool:
    """Scorer fact: no two agents share a slot. Not an agent-facing hint."""
    return all(len(agents) <= 1 for agents in occupancy_table(assignments).values())


def duplicate_claims(assignments: dict[str, str], *, resource: str) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for slot, agents in occupancy_table(assignments).items():
        if len(agents) > 1:
            violations.append(
                {
                    "type": "duplicate_resource_claim",
                    "resource": resource,
                    "slot": slot,
                    "agents": list(agents),
                }
            )
    return violations


def _agent_label(agent_id: str) -> str:
    raw = str(agent_id or "")
    if raw in {"agent_a", "A", "a"}:
        return "A"
    if raw in {"agent_b", "B", "b"}:
        return "B"
    return raw


def _sanitize_violation(item: dict[str, Any]) -> dict[str, Any]:
    vtype = str(item.get("type") or item.get("violation") or "")
    if vtype in {PRIORITY_VIOLATION, "priority_not_preserved"}:
        return {
            "violation": PRIORITY_VIOLATION,
            "type": PRIORITY_VIOLATION,
            "agent": _agent_label(str(item.get("agent") or "")),
            "keep_protected_assignment": True,
            "forbid_duplicate_claim": True,
        }
    if vtype == "private_infeasible":
        return {"type": "private_infeasible", "agent": _agent_label(str(item.get("agent") or ""))}
    if vtype == "not_earliest_feasible_idle":
        return {"type": "not_earliest_feasible_idle", "agent": _agent_label(str(item.get("agent") or ""))}
    if vtype == "duplicate_resource_claim":
        return {
            "type": "duplicate_resource_claim",
            "resource": item.get("resource"),
            "slot": item.get("slot"),
            "agents": list(item.get("agents") or []),
        }
    return {key: copy.deepcopy(value) for key, value in item.items() if key not in FORBIDDEN_AGENT_KEYS}


def _public_violations(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized = [_sanitize_violation(item) for item in items]
    priority = [item for item in sanitized if item.get("violation") == PRIORITY_VIOLATION]
    if priority:
        return priority
    return sanitized


@dataclass
class JointAssignmentChannel:
    """Save initial claims, return violations, accept a re-proposal. Never auto-fix."""

    resource_id: str
    slots: list[str]
    priority: list[str]
    feasible: dict[str, list[str]]
    max_retries: int = 1
    path: str | Path | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    _initial: dict[str, str] | None = None
    _proposal: dict[str, str] | None = None
    _protected: dict[str, str] | None = None
    _attempts: int = 0
    _denials: list[dict[str, Any]] = field(default_factory=list)
    unregistered_modification: int = 0
    registry: PlanRegistry = field(default_factory=PlanRegistry)
    _plan_id: str | None = None

    def _append(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        if not self.path:
            return
        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _deny(self, reason: str, **extra: Any) -> dict[str, Any]:
        payload = {"ok": False, "reason": reason, **extra}
        self._denials.append(payload)
        self._append({"event": "denied", **payload})
        return payload

    def save_initial(self, assignments: dict[str, str]) -> dict[str, Any]:
        body = {str(key): str(value) for key, value in assignments.items()}
        if len(body) < 2:
            return self._deny("initial_incomplete", assignments=body)
        self._initial = body
        self._proposal = copy.deepcopy(body)
        self._append({"event": "initial_saved", "assignments": copy.deepcopy(body)})
        return {"ok": True, "initial_assignments": copy.deepcopy(body)}

    def inspect_violations(self, assignments: dict[str, str] | None = None) -> dict[str, Any]:
        plan = assignments if assignments is not None else self._proposal or self._initial
        if not plan:
            return self._deny("initial_not_saved")
        violations = _public_violations(duplicate_claims(plan, resource=self.resource_id))
        payload = {"ok": True, "violations": violations}
        self._append({"event": "violations_inspected", "violations": copy.deepcopy(violations)})
        return payload

    def register_protection(self, *, agent: str, slot: str) -> dict[str, Any]:
        """Revise registered priority/protection. Does not rewrite the current proposal."""
        if self._initial is None:
            return self._deny("initial_not_saved")
        agent_id = str(agent or "")
        if agent_id in {"A", "a"}:
            agent_id = "agent_a"
        elif agent_id in {"B", "b"}:
            agent_id = "agent_b"
        if agent_id not in {"agent_a", "agent_b"}:
            return self._deny("invalid_protected_agent", agent=agent)
        protected_slot = str(slot or "")
        if protected_slot not in set(self.slots):
            return self._deny("invalid_protected_slot", slot=protected_slot)
        self.priority = [agent_id] + [item for item in self.priority if item != agent_id]
        self._protected = {agent_id: protected_slot}
        spec_version = self.registry.revise_spec()
        self._plan_id = None
        self._append(
            {
                "event": "protection_registered",
                "agent": agent_id,
                "slot": protected_slot,
                "spec_version": spec_version,
            }
        )
        return {
            "ok": True,
            "protected_agent": _agent_label(agent_id),
            "spec_version": spec_version,
        }

    def inspect_registered_constraints(self, assignments: dict[str, str] | None = None) -> dict[str, Any]:
        plan = assignments if assignments is not None else self._proposal or self._initial
        if not plan:
            return self._deny("initial_not_saved")
        violations = _public_violations(self._constraint_violations(plan))
        payload = {"ok": True, "violations": violations}
        self._append({"event": "registered_constraints_inspected", "violations": copy.deepcopy(violations)})
        return payload

    def _earliest_idle(self, agent_id: str, occupied: set[str]) -> str:
        for slot in self.feasible.get(agent_id) or []:
            if slot not in occupied:
                return slot
        return ""

    def _constraint_violations(self, assignments: dict[str, str]) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        found.extend(duplicate_claims(assignments, resource=self.resource_id))
        for agent_id, slot in assignments.items():
            allowed = self.feasible.get(agent_id) or []
            if slot and slot not in allowed:
                found.append({"type": "private_infeasible", "agent": agent_id})
        high = self.priority[0] if self.priority else ""
        if self._protected:
            for agent_id, slot in self._protected.items():
                if assignments.get(agent_id) != slot:
                    found.append({"type": PRIORITY_VIOLATION, "agent": agent_id})
        elif self._initial and high in self._initial and high in assignments:
            initial_slot = self._initial[high]
            observed = assignments[high]
            if initial_slot in (self.feasible.get(high) or []) and observed != initial_slot:
                found.append({"type": PRIORITY_VIOLATION, "agent": high})
        if not self.priority:
            return found
        occupied: set[str] = set()
        for agent_id in self.priority:
            slot = assignments.get(agent_id)
            if not slot:
                continue
            if agent_id != high:
                expected = self._earliest_idle(agent_id, occupied)
                if expected and slot != expected:
                    found.append({"type": "not_earliest_feasible_idle", "agent": agent_id})
            occupied.add(slot)
        return found

    def propose_joint_assignment(self, role: str, assignments: dict[str, str]) -> dict[str, Any]:
        if role not in AGENT_ROLES:
            self.unregistered_modification += 1
            return self._deny("unauthorized_proposal", role=role)
        if self._initial is None:
            return self._deny("initial_not_saved")
        if self._attempts >= self.max_retries + 1:
            return self._deny("retry_exhausted")
        body = {str(key): str(value) for key, value in assignments.items()}
        if "agent_a" not in body or "agent_b" not in body:
            return self._deny("assignments_incomplete", assignments=body)
        if "plan_version" in body or "spec_version" in body or "plan_id" in body:
            return self._deny("agent_must_not_issue_plan_id", assignments=body)
        self._attempts += 1
        self._proposal = copy.deepcopy(body)
        violations = _public_violations(self._constraint_violations(body))
        accepted = not violations
        retries_remaining = max(0, self.max_retries + 1 - self._attempts)
        if accepted:
            retries_remaining = 0
            stamped = self.registry.stamp(body)
            self._plan_id = stamped["plan_id"]
        else:
            stamped = None
            self._plan_id = None
        agent_payload = {
            "ok": True,
            "accepted": accepted,
            "violations": violations,
            "observed_assignments": copy.deepcopy(body),
            "retries_remaining": retries_remaining,
            "spec_version": self.registry.spec_version,
        }
        if stamped:
            agent_payload["plan_id"] = stamped["plan_id"]
        self._append(
            {
                "event": "proposal",
                "role": role,
                "attempt": self._attempts,
                "accepted": accepted,
                "assignments": copy.deepcopy(body),
                "violations": copy.deepcopy(violations),
                "plan_id": stamped["plan_id"] if stamped else None,
                "spec_version": self.registry.spec_version,
            }
        )
        return agent_payload

    def confirm_assignment(self, *, agent_id: str, slot: str, plan_id: str | None = None) -> dict[str, Any]:
        bound = plan_id or self._plan_id
        if not bound:
            return self._deny("plan_not_stamped")
        result = self.registry.confirm(agent_id=agent_id, slot=slot, plan_id=bound)
        self._append({"event": "confirm", **result, "agent_id": agent_id, "slot": slot})
        return result

    def write_assignment(self, *, role: str, assignments: dict[str, str]) -> dict[str, Any]:
        self.unregistered_modification += 1
        return self._deny("unauthorized_assignment_write", role=role)

    def world_state(self) -> dict[str, Any]:
        plan = dict(self._proposal or self._initial or {})
        return {
            "initial_assignments": copy.deepcopy(self._initial or {}),
            "assignments": copy.deepcopy(plan),
            "occupancy": occupancy_table(plan),
            "actual_final_conflict_free": actual_final_conflict_free(plan),
            "attempts": self._attempts,
            "unregistered_modification": self.unregistered_modification,
            "plan_id": self._plan_id,
            "spec_version": self.registry.spec_version if self._plan_id else None,
        }

    def agent_visible(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {key: copy.deepcopy(value) for key, value in payload.items() if key not in FORBIDDEN_AGENT_KEYS}

    def denials(self) -> list[dict[str, Any]]:
        return list(self._denials)
