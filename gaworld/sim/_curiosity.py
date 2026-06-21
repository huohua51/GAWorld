"""Contextual curiosity / knowledge-seeking helpers.

Three concerns, isolated from the news/HTTP plumbing in ``_news.py``:

1. ``assemble_curiosity_context`` — pure: pack the agent's current
   activity, recent events, emotional state, and growth focus into a
   compact dict.
2. ``should_seek_knowledge`` — cheap heuristic gate (no LLM), budget-aware.
3. ``propose_contextual_keywords`` — LLM, called only after the gate
   passes; falls back to the existing template query builder.

LLM access uses module-attribute dispatch (``_llm_providers.call_llm``)
so the test mock installer's ``providers.call_llm = mock`` reassignment
is picked up.
"""

from __future__ import annotations

import json
import random
from typing import Any

from gaworld.llm import providers as _llm_providers
from gaworld.sim._schedule import _extract_json_array_block
from gaworld.sim._utils import _sanitize_extra_text


def assemble_curiosity_context(
    agent: dict[str, Any],
    *,
    scheduled_activity: str = "",
    recent_events: list[str] | None = None,
    day: int | None = None,
    time_str: str | None = None,
) -> dict[str, Any]:
    """Pack the four signal groups into a compact context dict (pure)."""
    state = agent.get("state", {}) if isinstance(agent, dict) else {}
    try:
        from gaworld.interests import growth_focus
        focus = growth_focus(agent.get("growth_profile"), limit=3)
    except Exception:  # pragma: no cover - defensive
        focus = []
    return {
        "activity": str(scheduled_activity or "").strip(),
        "recent_events": [str(e).strip() for e in (recent_events or []) if str(e).strip()],
        "state": {
            "stress": float(state.get("stress", 0.5)),
            "econ_security": float(state.get("econ_security", 0.5)),
        },
        "growth_focus": focus,
        "day": day,
        "time_str": time_str,
    }


def should_seek_knowledge(
    agent: dict[str, Any],
    context: dict[str, Any],
    *,
    budget_left: int,
    config: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Cheap heuristic gate. Returns ``(trigger?, reason)``.

    A hard condition must hold first (fresh event / high stress / high
    estimated curiosity / salient growth focus); then a single
    ``trigger_chance_on_event`` dice roll smooths the frequency.
    """
    cfg = (config or {}).get("event_driven", {}) or {}
    if not cfg.get("enabled", True):
        return False, ""
    if budget_left <= 0:
        return False, ""

    stress_threshold = float(cfg.get("stress_threshold", 0.6))
    curiosity_threshold = float(cfg.get("curiosity_threshold", 0.6))

    reason = ""
    if context.get("recent_events"):
        reason = "event"
    elif float(context.get("state", {}).get("stress", 0.5)) >= stress_threshold:
        reason = "stress"
    elif _curiosity_score(agent) >= curiosity_threshold:
        reason = "curiosity"
    elif context.get("growth_focus"):
        reason = "growth"
    if not reason:
        return False, ""

    chance = float(cfg.get("trigger_chance_on_event", 0.5))
    if random.random() > chance:
        return False, ""
    return True, reason


def _curiosity_score(agent: dict[str, Any]) -> float:
    """Reuse the existing curiosity estimator from the news module."""
    from gaworld.sim._news import _estimate_curiosity
    return _estimate_curiosity(agent)
