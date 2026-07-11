"""LocalPhysicalPlugin — local physical perception as a kernel plugin (K3g).

P0 of the physical-environment stack: refresh the city map's per-node state
each tick and give every agent a snapshot of its *current* surroundings
(crowding / open-closed / local weather) before it perceives.

- ``on_time_tick`` (observe): write the sim time into the map and recompute
  node occupancy from where agents actually are.
- ``perception.compose`` (collect, priority=30): build the snapshot, store
  it at ``agent["_local_physical"]`` (the dynamic-behavior interrupt engine
  reads it in the next stage), and — when ``inject_into_perception`` is on —
  contribute the "身边的物理环境：…" line. Priority 30 keeps the line ahead
  of the life-event (20) and intervention (10) contributions, preserving the
  pre-migration text order exactly.

Deliberately NOT here: the spatial-preference layer (P4 — aversion
recording, redirection, day-start decay). It is entangled with the
dynamic-behavior interrupt results and migrates together with that plugin.
"""

from __future__ import annotations

from gaworld.kernel import Plugin
from gaworld.logging_setup import get_logger

_LOG = get_logger("gaworld.world.plugin")


def _weather_state(env_system) -> str:
    """Best-effort read of the environment's current weather label."""
    try:
        state = env_system.export_runtime_state()
        if isinstance(state, dict):
            return str(state.get("weather_state", "") or "")
    except Exception:  # noqa: BLE001 — remote client may lack this method
        pass
    return str(getattr(env_system, "_weather_state", "") or "")


class LocalPhysicalPlugin(Plugin):
    id = "local_physical"

    def setup(self, ctx):
        # Domain imports stay out of kernel assembly; module refs kept so
        # tests can patch the module attributes.
        from gaworld.world import city_map as cm_impl
        from gaworld.world import local_physical as lp_impl

        self._cm = cm_impl
        self._lp = lp_impl
        cfg = ctx.config.get("local_physical", {}) or {}
        self._enabled = bool(cfg.get("enabled", True))
        self._inject = bool(cfg.get("inject_into_perception", True))
        self._busy_ratio = float(cfg.get("crowd_busy_ratio", 0.6))
        self._packed_ratio = float(cfg.get("crowd_packed_ratio", 0.9))
        self._anomaly_ratio = float(cfg.get("crowd_anomaly_ratio", 0.9))
        self._anomaly_jump = float(cfg.get("crowd_anomaly_jump", 0.25))
        ctx.bus.on("on_time_tick", self._refresh_map)
        ctx.bus.on("perception.compose", self._snapshot, priority=30)

    # -- hooks ---------------------------------------------------------------

    def _refresh_map(self, hook_ctx):
        if not self._enabled:
            return
        city_map = hook_ctx.get("city_map")
        if not city_map:
            return
        self._cm.set_sim_time(city_map, hook_ctx.get("time_str"))
        self._lp.update_occupancy_from_agents(city_map, hook_ctx.get("agents", []))

    def _snapshot(self, hook_ctx):
        agent = hook_ctx["agent"]
        if not self._enabled:
            agent["_local_physical"] = {}
            return None
        sim = hook_ctx["sim"]
        local_physical = self._lp.local_physical_state(
            sim.extras.get("city_map"),
            agent,
            time_str=hook_ctx.get("time_str"),
            weather_state=_weather_state(sim.extras.get("env_system")),
            busy_ratio=self._busy_ratio,
            packed_ratio=self._packed_ratio,
            anomaly_ratio=self._anomaly_ratio,
            anomaly_jump=self._anomaly_jump,
        )
        agent["_local_physical"] = local_physical
        if not self._inject:
            return None
        text = self._lp.physical_state_text(local_physical)
        if text:
            return f"身边的物理环境：{text}"
        return None
