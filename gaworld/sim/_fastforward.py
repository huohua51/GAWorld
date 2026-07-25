"""Long-horizon fast-forward day compression.

The normal main loop simulates a day at fine granularity: an intra-day
timeline of ticks, each running the full cognition pipeline (one LLM call
per agent per tick). That is the right fidelity for a handful of days, but
it makes long horizons (60, 600 days) intractable — both in wall-clock and
in LLM cost.

**Fast-forward mode** collapses a whole day into a single *daily brief* per
agent: one LLM call authors a short "what happened today" sketch plus a set
of approximate, clamped deltas (mood/state, goal progress, a memory line,
tomorrow's intentions, social signals). The main loop applies those deltas
so memory, goals, relationships and state still *evolve* day to day — just
at a coarse, approximate resolution — and the day's log is the brief rather
than a per-tick trace.

This module owns the reusable, side-effect-free pieces:

* :func:`long_run_config` / :func:`long_run_enabled` — read the config block;
* :func:`simulate_agent_day` — the one-call-per-agent digest (LLM fast path
  + deterministic fallback);
* :func:`apply_state_changes` — clamp and apply the approximate state deltas;
* :func:`render_day_brief_block` — the console/log "Day N 简报" block.

Orchestration that touches ``run_simulation`` locals (hooks, persistence,
diary/vector-DB writes) stays in the main loop, mirroring how the per-tick
pipeline stages are wired there.

LLM access goes through ``gaworld.llm.providers`` by module attribute (not a
``from`` import) so the test mock installer's ``call_llm`` reassignment is
honoured, matching :mod:`gaworld.sim._diary`.
"""

from __future__ import annotations

import json
import random as _random
from typing import Any, Callable

from gaworld.llm import providers as _llm_providers
from gaworld.logging_setup import get_logger
from gaworld.settings import CONFIG
from gaworld.sim._schedule import _compact_text

_LOG = get_logger("gaworld.sim.fastforward")

# State metrics the digest may nudge. Restricting to the human-meaningful
# dimensions keeps the LLM from inventing keys; everything else evolves
# through the existing day-end hooks (economy, growth, interests, decay).
LONG_RUN_STATE_KEYS: tuple[str, ...] = (
    "emotion",
    "stress",
    "econ_security",
    "city_identity",
    "policy_sensitivity",
    "platform_dependence",
    "mobility_intent",
)

_DEFAULT_MAX_DELTA = 0.15
_DEFAULT_BRIEF_MAX_CHARS = 240
_DEFAULT_RANDOMNESS = 0.3

# Randomness shaping. ``randomness`` r ∈ [0,1] scales two effects:
#   * burst events — per-agent-per-day chance of an unplanned event =
#     ``_BURST_BASE_CHANCE * r`` (so ~30% of agent-days at r=1);
#   * state volatility — daily zero-mean jitter of amplitude
#     ``_JITTER_SCALE * r`` per key, amplified ``_BURST_JITTER_MULT``× on a
#     burst day. At r=0 there are no bursts and no jitter — identical to the
#     deterministic fast-forward day.
_BURST_BASE_CHANCE = 0.30
_BURST_JITTER_MULT = 3.0
_JITTER_SCALE = 0.06
# The keys jitter perturbs (the human-meaningful, fast-moving ones).
_JITTER_STATE_KEYS: tuple[str, ...] = ("emotion", "stress", "econ_security", "city_identity")

_BURST_PROMPT_HINT = (
    "【突发】今天发生了一件计划外的事（可好可坏，如意外开销/机会/冲突/健康/人际变故等）。"
    "请在简报里自然地体现这件事，并让相关状态出现明显（但合理）的波动。"
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def long_run_config(config: dict | None = None) -> dict[str, Any]:
    cfg = config if isinstance(config, dict) else CONFIG
    block = cfg.get("long_run", {}) if isinstance(cfg, dict) else {}
    return block if isinstance(block, dict) else {}


def long_run_enabled(config: dict | None = None) -> bool:
    return bool(long_run_config(config).get("enabled", False))


def _brief_max_chars(cfg: dict[str, Any]) -> int:
    try:
        return max(40, int(cfg.get("brief_max_chars", _DEFAULT_BRIEF_MAX_CHARS)))
    except (TypeError, ValueError):
        return _DEFAULT_BRIEF_MAX_CHARS


def _max_delta(cfg: dict[str, Any]) -> float:
    try:
        return max(0.0, min(1.0, float(cfg.get("max_state_delta", _DEFAULT_MAX_DELTA))))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_DELTA


def randomness_level(config: dict | None = None) -> float:
    """Long-run randomness r ∈ [0,1]; higher → more bursts + bigger swings."""
    cfg = long_run_config(config)
    try:
        return max(0.0, min(1.0, float(cfg.get("randomness", _DEFAULT_RANDOMNESS))))
    except (TypeError, ValueError):
        return _DEFAULT_RANDOMNESS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _schedule_text(base_schedule: Any, max_items: int = 8) -> str:
    """Compact one-line rendering of an agent's planned (base) schedule."""
    if not base_schedule:
        return "（无固定安排）"
    parts: list[str] = []
    for slot in list(base_schedule)[:max_items]:
        try:
            t, act = slot
        except (TypeError, ValueError):
            continue
        parts.append(f"{t} {act}")
    return "；".join(parts) if parts else "（无固定安排）"


def _recent_memory_text(agent: dict[str, Any], max_items: int = 3) -> str:
    memory = agent.get("memory", []) or []
    lines = [str(m).strip() for m in memory[-max_items:] if str(m or "").strip()]
    return " / ".join(lines) if lines else "（暂无近期记忆）"


def _state_summary(agent: dict[str, Any]) -> str:
    state = agent.get("state", {}) or {}
    keys = ("emotion", "stress", "econ_security", "city_identity")
    parts = [
        f"{k}={float(state[k]):.2f}"
        for k in keys
        if isinstance(state.get(k), (int, float))
    ]
    return "，".join(parts) if parts else "（无）"


def _neighbor_text(
    agent: dict[str, Any], agents_by_id: dict[Any, dict[str, Any]], max_items: int = 5
) -> str:
    neighbors = agent.get("social_neighbors", []) or []
    names = []
    for nid in list(neighbors)[:max_items]:
        name = (agents_by_id.get(nid) or {}).get("name", str(nid))
        names.append(f"{name}(#{nid})")
    return "、".join(names) if names else "（几乎没有熟人往来）"


def _env_text(env_events: Any, env_context: str) -> str:
    ctx = str(env_context or "").strip()
    if ctx:
        return _compact_text(ctx, max_chars=200)
    if isinstance(env_events, (list, tuple)) and env_events:
        bits = []
        for ev in list(env_events)[:3]:
            if isinstance(ev, dict):
                bits.append(str(ev.get("title") or ev.get("summary") or "").strip())
            else:
                bits.append(str(ev).strip())
        joined = "；".join(b for b in bits if b)
        if joined:
            return _compact_text(joined, max_chars=200)
    return "整体平稳，无特别事件"


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        raw = raw.strip("`")
        if "\n" in raw:
            raw = raw.split("\n", 1)[1]
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(raw[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ---------------------------------------------------------------------------
# Digest normalisation
# ---------------------------------------------------------------------------

def _normalize_digest(
    parsed: dict[str, Any], *, max_delta: float, brief_max_chars: int
) -> dict[str, Any]:
    brief = _compact_text(str(parsed.get("brief", "")).strip(), max_chars=brief_max_chars)
    memory = _compact_text(str(parsed.get("memory", "")).strip(), max_chars=60)

    changes: dict[str, float] = {}
    raw_changes = parsed.get("state_changes", {})
    if isinstance(raw_changes, dict):
        for key, value in raw_changes.items():
            if key not in LONG_RUN_STATE_KEYS:
                continue
            try:
                delta = float(value)
            except (TypeError, ValueError):
                continue
            changes[key] = max(-max_delta, min(max_delta, delta))

    goal_progress = parsed.get("goal_progress", [])
    if not isinstance(goal_progress, list):
        goal_progress = []

    social: list[dict[str, Any]] = []
    raw_social = parsed.get("social", [])
    if isinstance(raw_social, list):
        for item in raw_social:
            if not isinstance(item, dict):
                continue
            neighbor = item.get("neighbor")
            signal = str(item.get("signal", "neutral")).strip().lower()
            if signal not in ("positive", "negative", "neutral"):
                signal = "neutral"
            if neighbor is not None:
                social.append({"neighbor": neighbor, "signal": signal})

    intentions = parsed.get("intentions", {})
    if not isinstance(intentions, dict):
        intentions = {}

    return {
        "brief": brief,
        "memory": memory,
        "state_changes": changes,
        "goal_progress": goal_progress,
        "social": social,
        "intentions": intentions,
    }


def _fallback_digest(
    agent: dict[str, Any],
    *,
    day: int,
    base_schedule: Any,
    brief_max_chars: int,
    burst: bool = False,
) -> dict[str, Any]:
    """Deterministic brief when the LLM is disabled or the call fails."""
    plan = _schedule_text(base_schedule, max_items=4)
    if burst:
        brief = _compact_text(
            f"原计划（{plan}）被一件计划外的突发事打断，这一天过得比平时起伏。",
            max_chars=brief_max_chars,
        )
        memory = f"[Day {day}] 计划外的一件事打乱了节奏。"
    else:
        brief = _compact_text(
            f"按计划推进了这一天（{plan}），整体节奏平稳，没有特别的波动。",
            max_chars=brief_max_chars,
        )
        memory = f"[Day {day}] 平稳的一天，按常规节奏推进。"
    return {
        "brief": brief,
        "memory": memory,
        "state_changes": {},
        "goal_progress": [],
        "social": [],
        "intentions": {},
        "burst": burst,
    }


# ---------------------------------------------------------------------------
# Public: one-call-per-agent daily digest
# ---------------------------------------------------------------------------

_DIGEST_PROMPT = """你是生成式城市模拟中的“单日快进整合器”。请为下面这个人物，把一整天压缩成一份简短的日简报，并给出这一天的近似变化。不要逐时刻展开，只写这一天的概貌。

人物：{name}（id={agent_id}）
日期：Day {day} {day_desc}
今天的计划（作息骨架，供参考，可偏离）：{schedule}
最近的记忆：{recent_memory}
当前状态（0-1）：{state_summary}
人生与阶段目标（带[编号]）：{goals}
熟人：{neighbors}
外部环境：{env}
{burst_hint}
请只输出 JSON（不要额外解释）：
{{
  "brief": "≤{brief_chars}字，这一天的速写：主要做了什么、若有关键事件、心情与感受",
  "memory": "≤30字，今天最值得记住的一条经验或感受",
  "state_changes": {{"emotion": 0.0, "stress": 0.0, "econ_security": 0.0, "city_identity": 0.0}},
  "goal_progress": [{{"id": "stg1", "progress": 0.5, "note": "≤15字推进说明"}}],
  "social": [{{"neighbor": 3, "signal": "positive"}}],
  "intentions": {{"priorities": ["..."], "avoidances": ["..."]}}
}}

要求：
- state_changes 是相对“今天”的增量（-{max_delta}~{max_delta} 之间的小幅变化），只填确有变化的键；键只能取 {state_keys}。
- goal_progress 仅包含今天确有推进或受挫的目标，id 用目标里的[编号]，没有则给 []。
- social 仅列今天真正互动过的熟人及其大致基调（positive/negative/neutral），没有则给 []。
- 基于给定信息，克制、不要编造夸张的大事。仅输出 JSON。
"""


def simulate_agent_day(
    agent: dict[str, Any],
    *,
    day: int,
    day_desc: str,
    base_schedule: Any,
    goals_context: str = "无",
    env_events: Any = None,
    env_context: str = "",
    agents_by_id: dict[Any, dict[str, Any]] | None = None,
    config: dict | None = None,
    llm_fn: Callable[..., str] | None = None,
    rng: "_random.Random | None" = None,
) -> dict[str, Any]:
    """Compress one day for one agent into a normalized digest dict.

    Returns keys: ``brief``, ``memory``, ``state_changes`` (clamped deltas
    over :data:`LONG_RUN_STATE_KEYS`), ``goal_progress``, ``social``,
    ``intentions``, ``burst`` (whether a randomness-driven sudden event
    fired today). Falls back to a deterministic brief on any LLM failure or
    when ``llm_fn`` is None / ``long_run.brief_llm`` is False.

    ``rng`` (a ``random.Random``) makes the burst roll injectable for tests;
    it defaults to the module RNG so runs honour the global ``random_seed``.
    """
    cfg = long_run_config(config)
    brief_max_chars = _brief_max_chars(cfg)
    max_delta = _max_delta(cfg)
    randomness = randomness_level(config)  # takes the full config, not the unwrapped block
    _rng = rng or _random
    burst = bool(randomness > 0.0 and _rng.random() < _BURST_BASE_CHANCE * randomness)
    use_llm = bool(cfg.get("brief_llm", True)) and llm_fn is not None

    if not use_llm:
        return _fallback_digest(
            agent, day=day, base_schedule=base_schedule,
            brief_max_chars=brief_max_chars, burst=burst,
        )

    prompt = _DIGEST_PROMPT.format(
        name=agent.get("name", agent.get("id")),
        agent_id=agent.get("id"),
        day=int(day),
        day_desc=str(day_desc or "").strip(),
        schedule=_schedule_text(base_schedule),
        recent_memory=_recent_memory_text(agent),
        state_summary=_state_summary(agent),
        goals=str(goals_context or "无"),
        neighbors=_neighbor_text(agent, agents_by_id or {}),
        env=_env_text(env_events, env_context),
        burst_hint=(_BURST_PROMPT_HINT if burst else ""),
        brief_chars=brief_max_chars,
        max_delta=max_delta,
        state_keys="、".join(LONG_RUN_STATE_KEYS),
    )
    try:
        resp = llm_fn(prompt, task="fast_forward_day", agent_id=agent.get("id"))
    except Exception as exc:  # noqa: BLE001 - never let a fast-forward day crash the run
        _LOG.warning("fast_forward_day LLM call failed for agent %s: %s", agent.get("id"), exc)
        resp = ""
    parsed = _parse_json_object(resp)
    if not parsed or not str(parsed.get("brief", "")).strip():
        return _fallback_digest(
            agent, day=day, base_schedule=base_schedule,
            brief_max_chars=brief_max_chars, burst=burst,
        )
    digest = _normalize_digest(parsed, max_delta=max_delta, brief_max_chars=brief_max_chars)
    digest["burst"] = burst
    return digest


# ---------------------------------------------------------------------------
# Public: apply approximate state deltas
# ---------------------------------------------------------------------------

def apply_state_changes(
    agent: dict[str, Any], state_changes: dict[str, float], *, max_delta: float | None = None
) -> dict[str, float]:
    """Apply clamped per-day state deltas in place; return the applied set.

    Only keys already present on the agent's state are touched, and each
    resulting value is clamped to ``[0, 1]``. A ``None`` ``max_delta`` reads
    the configured cap.
    """
    if not isinstance(state_changes, dict):
        return {}
    cap = _max_delta(long_run_config()) if max_delta is None else max(0.0, float(max_delta))
    state = agent.setdefault("state", {})
    applied: dict[str, float] = {}
    for key, delta in state_changes.items():
        if key not in LONG_RUN_STATE_KEYS or not isinstance(state.get(key), (int, float)):
            continue
        try:
            step = max(-cap, min(cap, float(delta)))
        except (TypeError, ValueError):
            continue
        if step == 0.0:
            continue
        state[key] = _clamp01(float(state[key]) + step)
        applied[key] = step
    return applied


def apply_random_jitter(
    agent: dict[str, Any],
    *,
    randomness: float,
    burst: bool = False,
    rng: "_random.Random | None" = None,
) -> dict[str, float]:
    """Add zero-mean stochastic jitter to a few state keys, in place.

    Amplitude scales with ``randomness`` (× :data:`_BURST_JITTER_MULT` on a
    burst day). At ``randomness <= 0`` this is a no-op, so a fast-forward day
    with randomness off stays fully deterministic. Returns the applied
    per-key deltas; every touched value is clamped to ``[0, 1]``.
    """
    try:
        r = max(0.0, min(1.0, float(randomness)))
    except (TypeError, ValueError):
        return {}
    if r <= 0.0:
        return {}
    _rng = rng or _random
    amp = _JITTER_SCALE * r * (_BURST_JITTER_MULT if burst else 1.0)
    state = agent.setdefault("state", {})
    applied: dict[str, float] = {}
    for key in _JITTER_STATE_KEYS:
        if not isinstance(state.get(key), (int, float)):
            continue
        step = _rng.uniform(-amp, amp)
        if step == 0.0:
            continue
        state[key] = _clamp01(float(state[key]) + step)
        applied[key] = step
    return applied


# ---------------------------------------------------------------------------
# Public: render the day's brief block for console / logs
# ---------------------------------------------------------------------------

def render_day_brief_block(
    day: int, day_desc: str, agent_briefs: list[tuple[str, str]], world_line: str = ""
) -> str:
    """Build the ``Day N 简报`` block: one line per agent + optional world note."""
    header = f"\n========== Day {int(day)} 简报 ({str(day_desc).strip()}) =========="
    lines = [header]
    if str(world_line or "").strip():
        lines.append(f"🌆 {str(world_line).strip()}")
    for name, brief in agent_briefs:
        text = str(brief or "").strip() or "（这一天平稳度过）"
        lines.append(f"• {name}：{text}")
    lines.append("=" * len(header.strip()))
    return "\n".join(lines)


__all__ = [
    "LONG_RUN_STATE_KEYS",
    "long_run_config",
    "long_run_enabled",
    "randomness_level",
    "simulate_agent_day",
    "apply_state_changes",
    "apply_random_jitter",
    "render_day_brief_block",
]
