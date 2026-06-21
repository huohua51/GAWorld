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
