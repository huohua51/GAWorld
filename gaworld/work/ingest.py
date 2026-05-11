"""Ingest — bridge from completed WorkResult back into agent state.

Each tick, the simulator calls :func:`absorb_completed_for(agent, ...)`
to drain results, settle market jobs, and write a memory line.

The state effects are intentionally tiny: a small ``emotion`` /
``econ_security`` nudge so reflection sees something concrete. We do
**not** rewrite the action distribution or schedule — those are
owned by the existing simulator layer.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from gaworld.logging_setup import get_logger
from gaworld.work.market import JobMarket
from gaworld.work.queue import WorkQueue
from gaworld.work.schemas import WorkBrief, WorkResult

_LOG = get_logger("gaworld.work.ingest")


def _clip(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _bump_state(agent: dict[str, Any], key: str, delta: float) -> None:
    state = agent.setdefault("state", {})
    if not isinstance(state, dict):
        return
    try:
        cur = float(state.get(key, 0.5) or 0.5)
    except (TypeError, ValueError):
        cur = 0.5
    state[key] = _clip(cur + float(delta))


def _append_memory(agent: dict[str, Any], entry: dict[str, Any]) -> None:
    mem = agent.setdefault("memory", [])
    if isinstance(mem, list):
        mem.append(entry)


def absorb_completed_for(
    agent: dict[str, Any],
    *,
    queue: WorkQueue,
    market: Optional[JobMarket],
    sim_day: int,
    sim_time: str,
    limit: int = 5,
) -> list[WorkResult]:
    """Drain finished results for ``agent`` and apply their effects.

    Returns the list of consumed :class:`WorkResult` so the caller can
    log / hand them to ``reflection``.
    """

    agent_id = int(agent.get("id", 0) or 0)
    if not agent_id:
        return []
    results = queue.drain_completed_for(agent_id, limit=limit)
    if not results:
        return []

    briefs_by_id: dict[str, WorkBrief] = {b.task_id: b for b in queue.all_briefs()}
    for result in results:
        brief = briefs_by_id.get(result.task_id)
        market_job = None
        if market is not None:
            market_job = market.find_by_task(result.task_id)
        _apply_effects(agent, result, brief, market_job, market, sim_day=sim_day, sim_time=sim_time)
    return results


def _apply_effects(
    agent: dict[str, Any],
    result: WorkResult,
    brief: Optional[WorkBrief],
    market_job,
    market: Optional[JobMarket],
    *,
    sim_day: int,
    sim_time: str,
) -> None:
    success = result.status == "ok"
    title = brief.chosen_action if brief is not None else result.task_id
    artifact = result.artifact_paths[0] if result.artifact_paths else ""

    # Default mood/security nudges.
    if success:
        _bump_state(agent, "emotion", 0.04)
    else:
        _bump_state(agent, "emotion", -0.05)
        _bump_state(agent, "stress", 0.03)

    # Market-specific settlement.
    settlement_text = ""
    if market_job is not None and market is not None:
        market.settle(market_job.job_id, success=success)
        if success:
            reward = float(getattr(market_job, "reward_econ", 0.0) or 0.0)
            _bump_state(agent, "econ_security", reward * 0.5)
            settlement_text = f"，结算{getattr(market_job, 'reward_text', '')}"
        else:
            settlement_text = "，订单未能交付"

    if success:
        text = f"完成{title}{settlement_text}（产物：{artifact}）"
    else:
        text = f"未能交付{title}{settlement_text}（{result.error or '未知原因'}）"

    _append_memory(agent, {
        "day": sim_day,
        "time": sim_time,
        "kind": "work_result",
        "text": text,
        "task_id": result.task_id,
        "status": result.status,
        "artifact": artifact,
        "market_job_id": getattr(market_job, "job_id", None) if market_job else None,
    })


def summarise_for_outcome(results: Iterable[WorkResult]) -> str:
    """Compact one-liner for the simulator's ``outcome`` slot."""

    items = list(results)
    if not items:
        return ""
    parts = []
    for r in items[:3]:
        if r.status == "ok":
            head = r.summary or r.task_id
        else:
            head = f"失败:{r.error or r.task_id}"
        parts.append(head[:40])
    return " | ".join(parts)


__all__ = ["absorb_completed_for", "summarise_for_outcome"]
