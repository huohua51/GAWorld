"""Platform-owned plan identifiers. Agents submit assignments only."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlanRegistry:
    spec_version: str = "spec-001"
    _spec_seq: int = 1
    _seq: int = 0
    _plans: dict[str, dict[str, Any]] = field(default_factory=dict)

    def revise_spec(self) -> str:
        """Advance the authoritative specification version.

        Existing plan records remain available as audit evidence, but can no
        longer be confirmed against the newly revised specification.
        """
        self._spec_seq += 1
        self.spec_version = f"spec-{self._spec_seq:03d}"
        return self.spec_version

    def stamp(self, assignments: dict[str, str]) -> dict[str, Any]:
        self._seq += 1
        plan_id = f"plan-{self._seq:03d}"
        record = {
            "plan_id": plan_id,
            "spec_version": self.spec_version,
            "assignments": {str(key): str(value) for key, value in assignments.items()},
        }
        self._plans[plan_id] = record
        return dict(record)

    def get(self, plan_id: str) -> dict[str, Any] | None:
        found = self._plans.get(str(plan_id or ""))
        return dict(found) if found else None

    def confirm(self, *, agent_id: str, slot: str, plan_id: str) -> dict[str, Any]:
        plan = self.get(plan_id)
        if not plan:
            return {"ok": False, "reason": "unknown_plan_id"}
        if plan["spec_version"] != self.spec_version:
            return {
                "ok": False,
                "reason": "stale_plan_spec",
                "plan_id": plan["plan_id"],
                "plan_spec_version": plan["spec_version"],
                "current_spec_version": self.spec_version,
            }
        expected = str((plan.get("assignments") or {}).get(agent_id) or "")
        if expected != str(slot or ""):
            return {"ok": False, "reason": "slot_mismatch", "plan_id": plan["plan_id"]}
        return {
            "ok": True,
            "plan_id": plan["plan_id"],
            "spec_version": plan["spec_version"],
            "agent_id": agent_id,
            "slot": expected,
        }
