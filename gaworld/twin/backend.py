"""Twin operations: authenticate, submit, snapshot, profile, trail.

All authorization lives here so the HTTP layer stays a routing shell. Every
operation takes a bearer token and resolves the agent id from it; no operation
accepts an agent id from the caller.
"""

from __future__ import annotations

import time

from gaworld.io.avatar import build_agent_avatar_svg
from gaworld.twin import binding, geo, store


ACTION_TAGS = (
    "commute",
    "work",
    "study",
    "meal",
    "shopping",
    "rest",
    "social",
    "exercise",
    "errand",
    "other",
)

_UNAUTHORIZED = {"ok": False, "status": 401, "error": "invalid token"}


def _unauthorized():
    return dict(_UNAUTHORIZED)


class TwinBackend:
    """Composes geo/store/binding into the operations the server exposes."""

    def __init__(
        self,
        root=store.DEFAULT_ROOT,
        bindings_path=binding.DEFAULT_PATH,
        city_map=None,
        snapshot_ttl_minutes=30,
        max_snap_km=geo.DEFAULT_MAX_SNAP_KM,
    ):
        self.root = root
        self.bindings_path = bindings_path
        self.city_map = city_map or {"nodes": {}}
        self.snapshot_ttl_minutes = float(snapshot_ttl_minutes)
        self.max_snap_km = float(max_snap_km)

    # -- auth ------------------------------------------------------------

    def _agent_for(self, token):
        return binding.resolve_token(token, path=self.bindings_path)

    def authenticate(self, code):
        """Exchange an invite code for a bearer token."""
        token = binding.redeem_code(code, path=self.bindings_path)
        if token is None:
            return {"ok": False, "status": 403, "error": "invalid or revoked code"}
        return {
            "ok": True,
            "token": token,
            "label": binding.label_for_token(token, path=self.bindings_path),
        }

    # -- write -----------------------------------------------------------

    def _enrich(self, raw):
        """Attach server-computed geo fields and normalize client input."""
        loc = raw.get("loc") or {}
        located = geo.locate(
            loc.get("lng"),
            loc.get("lat"),
            city_map=self.city_map,
            max_snap_km=self.max_snap_km,
        )
        tag = str(raw.get("action_tag") or "other")
        return {
            "report_id": str(raw.get("report_id") or ""),
            "ts": float(raw.get("ts") or 0),
            "tz_offset": int(raw.get("tz_offset") or 0),
            "loc": {
                "lat": float(loc.get("lat") or 0),
                "lng": float(loc.get("lng") or 0),
                "acc_m": float(loc.get("acc_m") or 0),
                "source": "manual" if loc.get("source") == "manual" else "gps",
            },
            "grid": located["grid"],
            "node_id": located["node_id"],
            "snap_km": located["snap_km"],
            "out_of_map": located["out_of_map"],
            "action_tag": tag if tag in ACTION_TAGS else "other",
            "note": str(raw.get("note") or ""),
        }

    def submit(self, token, reports):
        """Store a batch of reports against the token's bound agent."""
        agent_id = self._agent_for(token)
        if agent_id is None:
            return _unauthorized()
        if not isinstance(reports, list):
            return {"ok": False, "status": 400, "error": "body must be a JSON array"}

        enriched = []
        for raw in reports:
            if not isinstance(raw, dict):
                return {"ok": False, "status": 400, "error": "each report must be an object"}
            record = self._enrich(raw)
            if not record["report_id"]:
                return {"ok": False, "status": 400, "error": "report_id is required"}
            enriched.append(record)

        result = store.append_reports(agent_id, enriched, root=self.root)
        return {
            "ok": True,
            "status": 200,
            "accepted": result["accepted"],
            "duplicates": result["duplicates"],
        }

    # -- read ------------------------------------------------------------

    def snapshot(self, token, now_ts=None):
        """Latest report plus whether it is fresh enough to mirror."""
        agent_id = self._agent_for(token)
        if agent_id is None:
            return _unauthorized()
        record = store.read_snapshot(agent_id, root=self.root)
        now = time.time() if now_ts is None else float(now_ts)
        return {
            "ok": True,
            "status": 200,
            "agent_id": agent_id,
            "report": record,
            "fresh": store.is_fresh(record, now, self.snapshot_ttl_minutes),
            "ttl_minutes": self.snapshot_ttl_minutes,
        }

    def profile(self, token):
        """Agent identity and avatar for the phone's header card."""
        agent_id = self._agent_for(token)
        if agent_id is None:
            return _unauthorized()
        label = binding.label_for_token(token, path=self.bindings_path)
        agent = {"id": agent_id, "name": label or f"agent_{agent_id}"}
        return {
            "ok": True,
            "status": 200,
            "agent_id": agent_id,
            "label": label,
            "avatar_svg": build_agent_avatar_svg(agent, size=128),
            "action_tags": list(ACTION_TAGS),
        }

    def trail(self, token, since_ts=None):
        """Ordered trail points for the canvas replay."""
        agent_id = self._agent_for(token)
        if agent_id is None:
            return _unauthorized()
        reports = store.load_reports(agent_id, root=self.root, since_ts=since_ts)
        reports.sort(key=lambda item: float(item.get("ts", 0)))
        points = [
            {
                "report_id": item.get("report_id"),
                "ts": item.get("ts"),
                "grid": item.get("grid"),
                "node_id": item.get("node_id"),
                "out_of_map": item.get("out_of_map"),
                "action_tag": item.get("action_tag"),
            }
            for item in reports
        ]
        return {"ok": True, "status": 200, "agent_id": agent_id, "points": points}
