"""LifeEventsPlugin — scheduled life events as a kernel plugin (K3e).

Life events are an event *producer*: the queue drains once per tick and the
results feed several downstream consumers (agent env events, perception
context, state effects, the env timeline, the visualizer). Each consumer
now rides its own dispatch point:

- ``on_day_start`` (observe): off-screen ghost-event injection (gated by
  ``human_realism.enabled`` + the same 0.18 daily dice as before).
- ``on_time_tick`` (observe, priority=10): drain due events once per tick
  into this plugin's shared state; mirror them into the env timeline JSONL
  (same ``scope: life_event`` records as the old inline block).
- ``env.events.compose`` (collect, per agent): filter the tick's due events
  for this agent, record them (stdout / daily log / agent log / memory),
  expose them as ``step["life_events"]``, and contribute their env-event
  form to ``agent_env_events``.
- ``perception.compose`` (collect, priority=20): the "人生事件：…" context
  line. Note a small ordering change vs. the inline code, documented in the
  CHANGELOG: the line now renders after the local-physical snippet instead
  of before it.
- ``state.effects`` (observe): apply each event's ``state_effects`` deltas,
  clipped to [0, 1].
"""

from __future__ import annotations

import json
import os

from gaworld.kernel import Plugin
from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.events.plugin")

# Probability per (agent, day) of an off-screen ghost reaching out.
GHOST_EVENT_DAILY_P = 0.18


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _append_jsonl(path, row) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        _LOG.warning("life-event timeline append failed: %s", exc)


class LifeEventsPlugin(Plugin):
    id = "life_events"

    def setup(self, ctx):
        # Domain imports stay out of kernel assembly; resolved once here.
        import random

        from gaworld.events import life as impl
        from gaworld.memory.store import append_agent_log
        from gaworld.sim._diary import _append_memory_record
        from gaworld.social.network import generate_ghost_event

        self._impl = impl
        self._rng = random
        self._append_agent_log = append_agent_log
        self._append_memory_record = _append_memory_record
        self._generate_ghost_event = generate_ghost_event
        self._push_aftermath = impl.push_event_aftermath
        self._decay_aftermath_impl = impl.decay_event_aftermath
        self._apply_aftermath_pressure = impl.apply_aftermath_state_pressure
        life_cfg = (ctx.config.get("life_events", {}) or {}) if hasattr(ctx, "config") else {}
        self._severity_state_amplify = float(life_cfg.get("severity_state_amplify", 0.8))
        ctx.bus.on("on_day_start", self._inject_ghost_events)
        ctx.bus.on("on_day_start", self._decay_aftermath)
        ctx.bus.on("on_time_tick", self._drain_tick, priority=10)
        ctx.bus.on("env.events.compose", self._agent_events)
        ctx.bus.on("env.events.tick", self._tick_events)
        ctx.bus.on("perception.compose", self._life_context, priority=20)
        ctx.bus.on("state.effects", self._apply_state_effects)
        # K5: queue a life event from outside the simulation loop
        # (dashboard bridge, notebooks, tests). Audited by the Controller.
        ctx.controller.register_intervention("inject_life_event", self._inject_event)

    def _inject_event(self, ctx, event=None, **kwargs):
        payload = dict(event or kwargs)
        if not payload.get("title"):
            raise ValueError("inject_life_event requires a `title`")
        return self._impl.add_life_event(payload, ctx.config)

    # -- day start: ghost events ----------------------------------------------

    def _inject_ghost_events(self, hook_ctx):
        sim = hook_ctx["sim"]
        if not (sim.config.get("human_realism", {}) or {}).get("enabled", False):
            return
        day = hook_ctx.get("day")
        for agent in hook_ctx.get("agents", []):
            self._maybe_inject_ghost_event(sim, agent, day, "08:30")

    def _decay_aftermath(self, hook_ctx):
        """Advance event-aftermath decay one day and apply the lingering state
        pressure. Runs after daily planning has already read the (undecayed)
        residual, so the day right after a serious event feels its full weight."""
        sim = hook_ctx["sim"]
        day = hook_ctx.get("day")
        config = getattr(sim, "config", None)
        for agent in hook_ctx.get("agents", []):
            self._decay_aftermath_impl(agent, day, config)
            self._apply_aftermath_pressure(agent, config)

    def _maybe_inject_ghost_event(self, sim, agent, day, time_str):
        """Dice-gated off-screen ghost event; failures are swallowed —
        the sim must never block on this path."""
        try:
            if self._rng.random() > GHOST_EVENT_DAILY_P:
                return None
            ev = self._generate_ghost_event(
                agent,
                current_day=day,
                llm_call=lambda prompt, task=None, agent_id=None: sim.llm(
                    prompt, task=task, agent_id=agent_id
                ),
                rng=self._rng,
            )
            if not ev:
                return None
            agent_id = agent.get("id")
            payload = {
                "title": ev["title"],
                "description": ev["description"],
                "severity": ev.get("severity", 0.55),
                "impact_tags": ev.get("impact_tags", ["relationship", "off_screen"]),
                "state_effects": ev.get("state_effects", {}),
                "schedule_mode": "scheduled",
                "day": int(day),
                "time": str(time_str or "08:30"),
                "agent_ids": [int(agent_id)] if agent_id is not None else [],
                "template_key": ev.get("template_key", "ghost_event"),
                "created_by": "social_network",
            }
            return self._impl.add_life_event(payload, sim.config)
        except Exception as exc:  # noqa: BLE001 — parity with the old inline guard
            _LOG.warning("ghost event injection failed for %s: %s", agent.get("id"), exc)
            return None

    # -- tick: drain + timeline mirror ----------------------------------------

    def _drain_tick(self, hook_ctx):
        sim = hook_ctx["sim"]
        day = hook_ctx.get("day")
        time_str = hook_ctx.get("time_str")
        due = self._impl.drain_due_life_events(day, time_str, sim.config)
        sim.plugin_state(self.id)["due"] = due
        if due:
            path = hook_ctx.get("env_timeline_path")
            day_context = hook_ctx.get("day_context") or {}
            if path:
                _append_jsonl(
                    path,
                    {
                        "scope": "life_event",
                        "day": int(day),
                        "date": day_context.get("sim_date", ""),
                        "time": str(time_str),
                        "events": due,
                    },
                )

    def _tick_events(self, hook_ctx):
        """Tick-scope env-event contributions (visualizer frame merge)."""
        due = hook_ctx["sim"].plugin_state(self.id).get("due") or []
        return [self._as_env_event(event) for event in due]

    # -- per agent --------------------------------------------------------------

    def _agent_events(self, hook_ctx):
        sim = hook_ctx["sim"]
        agent = hook_ctx["agent"]
        due = sim.plugin_state(self.id).get("due") or []
        agent_life_events = self._impl.life_events_for_agent(due, agent["id"])
        sim.agent_ext(agent, self.id)["current"] = agent_life_events
        step = hook_ctx.get("step")
        if isinstance(step, dict):
            step["life_events"] = agent_life_events
        if not agent_life_events:
            return None
        self._record_for_agent(
            agent,
            agent_life_events,
            hook_ctx.get("day"),
            hook_ctx.get("time_str"),
            hook_ctx.get("daily_logs"),
        )
        # Part C: seed a decaying cross-day aftermath from serious events.
        for event in agent_life_events:
            self._push_aftermath(agent, event, hook_ctx.get("day"), sim.config)
        return [self._as_env_event(event) for event in agent_life_events]

    def _record_for_agent(self, agent, events, day, time_str, daily_logs):
        recorded_ids = agent.setdefault("_recorded_life_event_ids", set())
        for event in events or []:
            event_id = str(event.get("id", ""))
            if event_id and event_id in recorded_ids:
                continue
            if event_id:
                recorded_ids.add(event_id)
            text = (
                f"[LifeEvent Day {day} {time_str}] "
                f"{agent.get('name', agent.get('id', 'agent'))}: "
                f"{self._impl.format_life_event(event)}"
            )
            print(text)
            if daily_logs is not None:
                daily_logs[agent["id"]] += text + "\n"
            self._append_agent_log(agent, text + "\n")
            self._append_memory_record(
                agent,
                text,
                entry_type="life_event",
                day=day,
                time_str=time_str,
            )

    def _as_env_event(self, event):
        return {
            "type": "life_event",
            "topic": str(event.get("template_key", "custom") or "custom"),
            "name": str(event.get("title", "人生事件") or "人生事件"),
            "description": str(event.get("description", "") or ""),
            "severity": float(event.get("severity", 0.6) or 0.6),
            "scope": "agent",
            "impact_tags": list(event.get("impact_tags", []) or []),
            "life_event": True,
        }

    def _life_context(self, hook_ctx):
        sim = hook_ctx["sim"]
        agent = hook_ctx["agent"]
        events = sim.agent_ext(agent, self.id).get("current") or []
        lines = [self._impl.format_life_event(event) for event in events]
        lines = [line for line in lines if line]
        if not lines:
            return None
        return "人生事件：" + "；".join(lines)

    # -- state effects ------------------------------------------------------------

    def _severity_state_factor(self, event):
        """Scale a life event's state deltas by its severity.

        ``clip(1 + amplify * (severity - 0.5), 0.5, 1.8)``. An event with no
        severity (or a non-numeric one) yields factor 1.0, leaving the
        configured deltas untouched — the pre-severity behaviour.
        """
        raw = event.get("severity") if isinstance(event, dict) else None
        if raw is None:
            return 1.0
        try:
            severity = float(raw)
        except (TypeError, ValueError):
            return 1.0
        factor = 1.0 + self._severity_state_amplify * (severity - 0.5)
        return max(0.5, min(1.8, factor))

    def _apply_state_effects(self, hook_ctx):
        agent = hook_ctx["agent"]
        step = hook_ctx.get("step") or {}
        events = step.get("life_events") or []
        state = agent.setdefault("state", {})
        for event in events:
            effects = event.get("state_effects", {})
            if not isinstance(effects, dict):
                continue
            factor = self._severity_state_factor(event)
            for key, delta in effects.items():
                if key not in state:
                    continue
                try:
                    state[key] = _clip01(float(state.get(key, 0.5)) + float(delta) * factor)
                except (TypeError, ValueError):
                    continue
