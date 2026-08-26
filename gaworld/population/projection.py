"""Audited individual, cohort and fast-forward population projection.

The cohort modes preserve registered first and second moments for affine
state transitions.  They do not claim to preserve unregistered properties
such as network topology or individual trajectories.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

MODES = {"individual", "cohort", "fast_forward"}


def _fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class TransitionSpec:
    """Registered affine transition for one longitudinal population metric."""

    metric: str
    persistence: float
    subgroup_drift: dict[str, float]
    shocks: dict[int, float]

    def __post_init__(self) -> None:
        if not self.metric:
            raise ValueError("metric is required")
        if not math.isfinite(self.persistence) or self.persistence < 0:
            raise ValueError("persistence must be finite and non-negative")
        if not self.subgroup_drift:
            raise ValueError("subgroup_drift is required")
        if any(int(day) <= 0 for day in self.shocks):
            raise ValueError("shock days must be positive")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shocks"] = {int(day): float(value) for day, value in self.shocks.items()}
        return payload

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


class PopulationProjectionEngine:
    """Project a fixed population with auditable approximation and checkpoints."""

    def __init__(
        self,
        path: str,
        members: list[Mapping[str, Any]],
        spec: TransitionSpec,
        mode: str,
        *,
        _initialize_trace: bool = True,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown projection mode: {mode}")
        self.path = path
        self.spec = spec
        self.mode = mode
        self._initial_members = self._normalize_members(members)
        self._population_fingerprint = _fingerprint(self._initial_members)
        self._member_state = {
            member["agent_id"]: {
                "subgroup": member["subgroup"],
                "value": float(member["value"]),
            }
            for member in self._initial_members
        }
        self._group_state = self._aggregate(self._initial_members)
        self._day = 0
        self._operations = 0
        self._events: list[dict[str, Any]] = []
        self._seq = 0
        if _initialize_trace:
            self._append(
                {
                    "event": "population_registered",
                    "population_fingerprint": self._population_fingerprint,
                    "members": self._initial_members,
                }
            )
            self._append(
                {
                    "event": "projection_started",
                    "mode": self.mode,
                    "spec": self.spec.to_dict(),
                    "spec_fingerprint": self.spec.fingerprint(),
                }
            )

    @staticmethod
    def _normalize_members(members: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for member in members:
            agent_id = str(member.get("agent_id") or "")
            subgroup = str(member.get("subgroup") or "")
            try:
                value = float(member["value"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("each member requires a numeric value") from exc
            if not agent_id or not subgroup or not math.isfinite(value):
                raise ValueError("each member requires agent_id, subgroup and finite value")
            if agent_id in seen:
                raise ValueError(f"duplicate member: {agent_id}")
            seen.add(agent_id)
            normalized.append({"agent_id": agent_id, "subgroup": subgroup, "value": value})
        if not normalized:
            raise ValueError("at least one population member is required")
        return sorted(normalized, key=lambda item: item["agent_id"])

    @staticmethod
    def _aggregate(members: list[Mapping[str, Any]]) -> dict[str, dict[str, float | int]]:
        values: dict[str, list[float]] = {}
        for member in members:
            values.setdefault(str(member["subgroup"]), []).append(float(member["value"]))
        groups: dict[str, dict[str, float | int]] = {}
        for subgroup, subgroup_values in values.items():
            count = len(subgroup_values)
            mean = sum(subgroup_values) / count
            variance = sum((value - mean) ** 2 for value in subgroup_values) / count
            groups[subgroup] = {"count": count, "mean": mean, "variance": variance}
        return groups

    def _ensure_dir(self, target: str) -> None:
        directory = os.path.dirname(target)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def _append(self, event: dict[str, Any]) -> None:
        self._seq += 1
        record = {"seq": self._seq, "ts": time.time(), **event}
        self._events.append(record)
        self._ensure_dir(self.path)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _increment(self, subgroup: str, day: int) -> float:
        if subgroup not in self.spec.subgroup_drift:
            raise ValueError(f"missing drift for subgroup: {subgroup}")
        return float(self.spec.subgroup_drift[subgroup]) + float(self.spec.shocks.get(day, 0.0))

    def _advance_individual(self, target_day: int) -> None:
        for day in range(self._day + 1, target_day + 1):
            for state in self._member_state.values():
                state["value"] = self.spec.persistence * float(state["value"]) + self._increment(
                    str(state["subgroup"]), day
                )
                self._operations += 1
            self._append({"event": "individual_day_completed", "day": day})

    def _advance_cohort(self, target_day: int) -> None:
        for day in range(self._day + 1, target_day + 1):
            for subgroup, state in self._group_state.items():
                state["mean"] = self.spec.persistence * float(state["mean"]) + self._increment(subgroup, day)
                state["variance"] = self.spec.persistence**2 * float(state["variance"])
                self._operations += 1
            self._append({"event": "cohort_day_completed", "day": day})

    def _apply_affine_segment(
        self, subgroup: str, state: dict[str, float | int], days: int, increment: float
    ) -> None:
        if days <= 0:
            return
        factor = self.spec.persistence**days
        if math.isclose(self.spec.persistence, 1.0):
            mean = float(state["mean"]) + increment * days
        else:
            mean = factor * float(state["mean"]) + increment * (
                (1.0 - factor) / (1.0 - self.spec.persistence)
            )
        state["mean"] = mean
        state["variance"] = factor**2 * float(state["variance"])
        self._operations += 1
        self._append(
            {
                "event": "fast_forward_segment",
                "subgroup": subgroup,
                "days": days,
                "increment": increment,
            }
        )

    def _advance_fast(self, target_day: int) -> None:
        shock_days = sorted(day for day in self.spec.shocks if self._day < day <= target_day)
        for subgroup, state in self._group_state.items():
            cursor = self._day
            drift = float(self.spec.subgroup_drift[subgroup])
            for shock_day in shock_days:
                self._apply_affine_segment(subgroup, state, shock_day - cursor - 1, drift)
                self._apply_affine_segment(
                    subgroup,
                    state,
                    1,
                    drift + float(self.spec.shocks[shock_day]),
                )
                cursor = shock_day
            self._apply_affine_segment(subgroup, state, target_day - cursor, drift)

    def advance_to(self, target_day: int) -> dict[str, Any]:
        if target_day < self._day:
            raise ValueError("projection day cannot move backwards")
        if self.mode == "individual":
            self._advance_individual(target_day)
        elif self.mode == "cohort":
            self._advance_cohort(target_day)
        else:
            self._advance_fast(target_day)
        self._day = int(target_day)
        self._append(
            {
                "event": "projection_advanced",
                "day": self._day,
                "mode": self.mode,
                "operations": self._operations,
            }
        )
        return self.summary()

    def _current_groups(self) -> dict[str, dict[str, float | int]]:
        if self.mode != "individual":
            return {subgroup: dict(state) for subgroup, state in self._group_state.items()}
        members = [
            {
                "agent_id": agent_id,
                "subgroup": state["subgroup"],
                "value": state["value"],
            }
            for agent_id, state in self._member_state.items()
        ]
        return self._aggregate(members)

    def summary(self) -> dict[str, Any]:
        groups = self._current_groups()
        count = sum(int(state["count"]) for state in groups.values())
        overall_mean = sum(int(state["count"]) * float(state["mean"]) for state in groups.values()) / count
        second_moment = (
            sum(
                int(state["count"]) * (float(state["variance"]) + float(state["mean"]) ** 2)
                for state in groups.values()
            )
            / count
        )
        return {
            "mode": self.mode,
            "day": self._day,
            "metric": self.spec.metric,
            "population_count": count,
            "overall_mean": overall_mean,
            "overall_variance": max(0.0, second_moment - overall_mean**2),
            "subgroups": groups,
            "operation_units": self._operations,
            "population_fingerprint": self._population_fingerprint,
            "spec_fingerprint": self.spec.fingerprint(),
        }

    def save_checkpoint(self, checkpoint_path: str) -> str:
        payload = {
            "checkpoint_version": 1,
            "mode": self.mode,
            "day": self._day,
            "operation_units": self._operations,
            "population_fingerprint": self._population_fingerprint,
            "spec_fingerprint": self.spec.fingerprint(),
            "member_state": self._member_state if self.mode == "individual" else None,
            "group_state": self._group_state if self.mode != "individual" else None,
        }
        self._ensure_dir(checkpoint_path)
        with open(checkpoint_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        self._append(
            {
                "event": "checkpoint_written",
                "checkpoint_path": checkpoint_path,
                "day": self._day,
            }
        )
        return checkpoint_path

    @classmethod
    def resume_from_checkpoint(
        cls,
        path: str,
        checkpoint_path: str,
        members: list[Mapping[str, Any]],
        spec: TransitionSpec,
        mode: str,
    ) -> PopulationProjectionEngine:
        with open(checkpoint_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        engine = cls(path, members, spec, mode, _initialize_trace=False)
        engine._load_trace_metadata()
        if payload.get("checkpoint_version") != 1:
            raise ValueError("unsupported checkpoint version")
        if payload.get("mode") != mode:
            raise ValueError("checkpoint mode mismatch")
        if payload.get("population_fingerprint") != engine._population_fingerprint:
            raise ValueError("checkpoint population mismatch")
        if payload.get("spec_fingerprint") != spec.fingerprint():
            raise ValueError("checkpoint transition mismatch")
        engine._day = int(payload["day"])
        engine._operations = int(payload["operation_units"])
        if mode == "individual":
            engine._member_state = {
                str(agent_id): {
                    "subgroup": str(state["subgroup"]),
                    "value": float(state["value"]),
                }
                for agent_id, state in dict(payload.get("member_state") or {}).items()
            }
        else:
            engine._group_state = {
                str(subgroup): {
                    "count": int(state["count"]),
                    "mean": float(state["mean"]),
                    "variance": float(state["variance"]),
                }
                for subgroup, state in dict(payload.get("group_state") or {}).items()
            }
        engine._append(
            {
                "event": "checkpoint_loaded",
                "checkpoint_path": checkpoint_path,
                "day": engine._day,
            }
        )
        return engine

    def _load_trace_metadata(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        with open(self.path, encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        self._events = rows
        self._seq = max((int(row.get("seq") or 0) for row in rows), default=0)

    def finish(self, expected_day: int) -> dict[str, Any]:
        completed = self._day == expected_day
        summary = self.summary()
        self._append(
            {
                "event": "projection_completed",
                "day": self._day,
                "expected_day": expected_day,
                "completed": completed,
                "summary": summary,
            }
        )
        return {"ok": completed, "summary": summary}

    def event_names(self) -> list[str]:
        return [str(event.get("event") or "") for event in self._events]

    def events(self) -> list[dict[str, Any]]:
        return list(self._events)


__all__ = ["MODES", "PopulationProjectionEngine", "TransitionSpec"]
