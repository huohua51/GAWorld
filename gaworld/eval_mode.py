"""Opt-in evaluation contract for GAWorld.

Default ``run`` stays a city simulator. When ``eval_mode.enabled`` is true,
the environment must not silently rewrite agent actions, invent diaries, or
paste one prose blob onto every interview question.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Mapping


DEFAULT_EVAL_MODE = {
    "enabled": False,
    "disable_dynamic_behavior": True,
    "disable_routine_change": True,
    "disable_diary_fallback": True,
    "strict_interview_json": True,
    "write_run_manifest": True,
    "unique_intervention_paths": [],
}

EPS = 1e-12


def eval_mode_block(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    block = dict(DEFAULT_EVAL_MODE)
    raw = (config or {}).get("eval_mode")
    if isinstance(raw, dict):
        block.update(raw)
    return block


def eval_mode_enabled(config: Mapping[str, Any] | None = None) -> bool:
    return bool(eval_mode_block(config).get("enabled"))


def interview_fallback_allowed(config: Mapping[str, Any] | None = None) -> bool:
    block = eval_mode_block(config)
    if not block.get("enabled"):
        return True
    return not bool(block.get("strict_interview_json", True))


def diary_fallback_allowed(config: Mapping[str, Any] | None = None) -> bool:
    block = eval_mode_block(config)
    if not block.get("enabled"):
        return True
    return not bool(block.get("disable_diary_fallback", True))


def routine_change_allowed(config: Mapping[str, Any] | None = None) -> bool:
    block = eval_mode_block(config)
    if not block.get("enabled"):
        return True
    return not bool(block.get("disable_routine_change", True))


def apply_eval_mode_runtime(config: dict[str, Any]) -> dict[str, Any]:
    """Freeze rewrite flags on a live CONFIG dict. No-op when disabled."""

    block = eval_mode_block(config)
    applied: dict[str, Any] = {"applied": False, "enabled": bool(block.get("enabled")), "changes": []}
    if not block.get("enabled"):
        return applied
    applied["applied"] = True
    if block.get("disable_dynamic_behavior", True):
        dyn = config.setdefault("dynamic_behavior", {})
        if isinstance(dyn, dict):
            dyn["enabled"] = False
            applied["changes"].append("dynamic_behavior.enabled=False")
    if block.get("disable_routine_change", True):
        rc = config.setdefault("routine_change", {})
        if isinstance(rc, dict):
            rc["enabled"] = False
            applied["changes"].append("routine_change.enabled=False")
    config["eval_mode"] = block
    return applied


def unique_intervention_audit(
    rows: list[Mapping[str, Any]],
    registered_paths: list[str] | set[str],
    eps: float = EPS,
) -> dict[str, Any]:
    registered = {str(item) for item in registered_paths}
    leaked = []
    registered_deltas: dict[str, float] = {}
    for row in rows:
        metric = str(row.get("metric", ""))
        delta = float(row.get("delta_final", 0.0) or 0.0)
        if metric in registered:
            registered_deltas[metric] = delta
        elif abs(delta) > eps:
            leaked.append({"metric": metric, "delta_final": delta})
    return {
        "registered_paths": sorted(registered),
        "unique_path_ok": not leaked,
        "leaked_metrics": leaked,
        "registered_deltas": registered_deltas,
        "measurement_valid": bool(registered) and not leaked,
    }


def parse_structured_action(text: str) -> dict[str, Any] | None:
    """Extract ``target_action`` from a model JSON object or array item."""

    if not text or not str(text).strip():
        return None
    raw = str(text).strip()
    blob = raw
    if "```" in raw:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            blob = raw[start : end + 1]
    try:
        payload = json.loads(blob)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    if isinstance(payload, list) and payload:
        payload = payload[0]
    if not isinstance(payload, dict):
        return None
    action = payload.get("target_action")
    if isinstance(action, dict):
        return action
    if "action" in payload and "payload" in payload:
        return {"action": payload.get("action"), "payload": payload.get("payload")}
    return None


def write_run_manifest(path: str, config: Mapping[str, Any], extra: Mapping[str, Any] | None = None) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    block = eval_mode_block(config)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eval_mode": block,
        "dynamic_behavior_enabled": bool((config.get("dynamic_behavior") or {}).get("enabled", False)),
        "routine_change_enabled": bool((config.get("routine_change") or {}).get("enabled", False)),
        "agent_ids": list(config.get("agent_ids") or []),
        "sim_days": config.get("sim_days"),
        "random_seed": config.get("random_seed"),
        "extra": dict(extra or {}),
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path
