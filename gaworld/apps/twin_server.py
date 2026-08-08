"""Public-facing HTTP server for the mobile digital twin.

Deliberately a SEPARATE process from ``dashboard_server``. The dashboard
accepts unauthenticated POSTs to ``/api/config`` (writes global config) and
``/api/run/start`` (spawns simulation subprocesses); exposing that process
publicly would hand config-write and process-spawn capability to anyone who
scans the port. This server exposes five authenticated endpoints and the
mobile static bundle, and nothing else.

Routing and authentication only — all behaviour lives in
:class:`gaworld.twin.backend.TwinBackend`.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gaworld.settings import CONFIG
from gaworld.twin.backend import TwinBackend


REPO_ROOT = str(Path(__file__).resolve().parents[2])
MAX_BODY_BYTES = 1_000_000


def make_handler(backend):
    """Build a request handler class bound to ``backend``."""

    class TwinHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=REPO_ROOT, **kwargs)

        # -- helpers ----------------------------------------------------

        def _json(self, payload, status=200):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _reply(self, result):
            """Send a backend result, using its own status field."""
            status = int(result.get("status", 200 if result.get("ok") else 400))
            self._json(result, status=status)

        def _token(self):
            header = self.headers.get("Authorization", "")
            if header.startswith("Bearer "):
                return header[len("Bearer "):].strip()
            return ""

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return None
            if length > MAX_BODY_BYTES:
                raise ValueError("request body too large")
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def log_message(self, fmt, *args):
            # Default logging writes the full request line to stderr. This
            # server is internet-facing, so keep tokens out of the logs.
            return

        # -- routing ----------------------------------------------------

        def do_GET(self):
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            query = parse_qs(parsed.query)

            if path == "/api/twin/snapshot":
                return self._reply(backend.snapshot(self._token()))
            if path == "/api/twin/profile":
                return self._reply(backend.profile(self._token()))
            if path == "/api/twin/trail":
                since = query.get("since_ts", [None])[0]
                return self._reply(
                    backend.trail(self._token(), since_ts=float(since) if since else None)
                )
            if path.startswith("/api/"):
                return self._json({"error": "not found"}, status=404)

            if path in ("/", "/m", "/m/"):
                self.path = "/site/mobile/index.html"
            return super().do_GET()

        def do_POST(self):
            parsed = urlparse(self.path)
            path = unquote(parsed.path)

            try:
                body = self._body()
            except (ValueError, json.JSONDecodeError) as exc:
                return self._json({"ok": False, "error": str(exc)}, status=400)

            if path == "/api/twin/auth":
                code = (body or {}).get("code", "") if isinstance(body, dict) else ""
                return self._reply(backend.authenticate(code))
            if path == "/api/twin/report":
                return self._reply(backend.submit(self._token(), body))
            return self._json({"error": "not found"}, status=404)

    return TwinHandler


def build_backend(config=None):
    """Build a backend from CONFIG, loading the city map for node snapping."""
    cfg = dict((config or CONFIG).get("twin") or {})
    city_map = None
    try:
        from gaworld.world.city_map import load_city_map_cached

        map_path = os.path.join(REPO_ROOT, (config or CONFIG).get("map_path", "data/citymap.md"))
        city_map = load_city_map_cached(map_path)
    except Exception:
        # Without a map every fix is reported out of map, which is the correct
        # conservative behaviour: better than snapping to a fabricated node.
        city_map = {"nodes": {}}
    return TwinBackend(
        root=cfg.get("root", "output/twin"),
        bindings_path=cfg.get("bindings_path", "data/twin_bindings.json"),
        city_map=city_map,
        snapshot_ttl_minutes=cfg.get("snapshot_ttl_minutes", 30),
        max_snap_km=cfg.get("max_snap_km", 3.0),
    )


def run_server(host="127.0.0.1", port=8767, backend=None):
    backend = backend or build_backend()
    server = ThreadingHTTPServer((host, int(port)), make_handler(backend))
    print(f"GAWorld twin server: http://{host}:{int(port)}/")
    print("Expose it over HTTPS (Cloudflare Tunnel); Geolocation needs TLS.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Serve the GAWorld mobile twin API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--issue-code", type=int, metavar="AGENT_ID",
                        help="print a new invite code for AGENT_ID and exit")
    parser.add_argument("--label", default="", help="display label for --issue-code")
    args = parser.parse_args()

    if args.issue_code is not None:
        from gaworld.twin import binding

        cfg = CONFIG.get("twin") or {}
        code = binding.issue_code(
            agent_id=args.issue_code,
            label=args.label,
            path=cfg.get("bindings_path", "data/twin_bindings.json"),
        )
        print(code)
    else:
        run_server(host=args.host, port=args.port)
