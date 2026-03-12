import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from config import CONFIG


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _normalize_text(value, max_chars=280):
    text = str(value or "").strip()
    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return text


def _safe_dict(value):
    return value if isinstance(value, dict) else {}


class DistributedRelayBackend:
    def __init__(self, state_path="", max_messages=20000):
        self.state_path = state_path
        self.max_messages = max(100, _to_int(max_messages, 20000))
        self.lock = threading.RLock()
        self.next_message_id = 1
        self.messages = []
        self.directory = {}
        self._load()

    def _persist(self):
        if not self.state_path:
            return
        directory = os.path.dirname(self.state_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        payload = {
            "next_message_id": int(self.next_message_id),
            "messages": self.messages,
            "directory": self.directory,
            "max_messages": int(self.max_messages),
            "updated_at": time.time(),
        }
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not self.state_path or not os.path.exists(self.state_path):
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        self.next_message_id = max(1, _to_int(payload.get("next_message_id", 1), 1))
        raw_messages = payload.get("messages", [])
        self.messages = raw_messages if isinstance(raw_messages, list) else []
        raw_dir = payload.get("directory", {})
        self.directory = raw_dir if isinstance(raw_dir, dict) else {}
        if self.messages:
            max_id = max(_to_int(msg.get("id"), 0) for msg in self.messages if isinstance(msg, dict))
            self.next_message_id = max(self.next_message_id, max_id + 1)

    def register_agents(self, cluster, node_id, agents):
        cluster = str(cluster or "default")
        node_id = str(node_id or "node")
        now = time.time()
        with self.lock:
            cluster_map = self.directory.setdefault(cluster, {})
            count = 0
            for item in agents if isinstance(agents, list) else []:
                if not isinstance(item, dict):
                    continue
                aid = _to_int(item.get("id"), 0)
                if aid <= 0:
                    continue
                cluster_map[str(aid)] = {
                    "agent_id": aid,
                    "name": _normalize_text(item.get("name", ""), max_chars=64),
                    "node_id": node_id,
                    "updated_at": now,
                }
                count += 1
            self._persist()
            agents_list = list(cluster_map.values())
        agents_list.sort(key=lambda x: _to_int(x.get("agent_id"), 0))
        return {"ok": True, "registered": count, "directory": agents_list}

    def get_directory(self, cluster):
        cluster = str(cluster or "default")
        with self.lock:
            cluster_map = _safe_dict(self.directory.get(cluster))
            agents_list = list(cluster_map.values())
        agents_list.sort(key=lambda x: _to_int(x.get("agent_id"), 0))
        return {"ok": True, "cluster": cluster, "agents": agents_list}

    def send_message(self, cluster, node_id, message):
        cluster = str(cluster or "default")
        node_id = str(node_id or "node")
        payload = _safe_dict(message)
        from_agent = _to_int(payload.get("from_agent"), 0)
        to_agent = _to_int(payload.get("to_agent"), 0)
        text = _normalize_text(payload.get("text", ""), max_chars=400)
        if from_agent <= 0 or to_agent <= 0 or not text:
            return {"ok": False, "error": "invalid message payload"}
        msg = {
            "id": 0,
            "cluster": cluster,
            "node_id": node_id,
            "from_agent": from_agent,
            "from_name": _normalize_text(payload.get("from_name", ""), max_chars=64),
            "to_agent": to_agent,
            "kind": _normalize_text(payload.get("kind", "agent_update"), max_chars=40) or "agent_update",
            "text": text,
            "day": _to_int(payload.get("day"), 0),
            "time": _normalize_text(payload.get("time", ""), max_chars=16),
            "activity": _normalize_text(payload.get("activity", ""), max_chars=64),
            "meta": _safe_dict(payload.get("meta")),
            "created_at": time.time(),
        }
        with self.lock:
            msg["id"] = int(self.next_message_id)
            self.next_message_id += 1
            self.messages.append(msg)
            overflow = len(self.messages) - self.max_messages
            if overflow > 0:
                self.messages = self.messages[overflow:]
            self._persist()
        return {"ok": True, "message": msg}

    def poll_messages(self, cluster, recipient_ids, since_map, limit):
        cluster = str(cluster or "default")
        ids = []
        for raw in recipient_ids if isinstance(recipient_ids, list) else []:
            aid = _to_int(raw, 0)
            if aid > 0:
                ids.append(aid)
        unique_ids = sorted(set(ids))
        since_obj = _safe_dict(since_map)
        effective_limit = max(1, min(500, _to_int(limit, 100)))
        if not unique_ids:
            return {"ok": True, "messages": [], "next_since": {}}

        id_set = set(unique_ids)
        next_since = {str(aid): _to_int(since_obj.get(str(aid), 0), 0) for aid in unique_ids}
        selected = []
        with self.lock:
            for msg in self.messages:
                if not isinstance(msg, dict):
                    continue
                if str(msg.get("cluster", "")) != cluster:
                    continue
                to_agent = _to_int(msg.get("to_agent"), 0)
                if to_agent not in id_set:
                    continue
                msg_id = _to_int(msg.get("id"), 0)
                if msg_id <= next_since.get(str(to_agent), 0):
                    continue
                selected.append(msg)
                next_since[str(to_agent)] = max(next_since.get(str(to_agent), 0), msg_id)
                if len(selected) >= effective_limit:
                    break
        return {"ok": True, "messages": selected, "next_since": next_since}

    def snapshot(self):
        with self.lock:
            cluster_count = len(self.directory)
            agent_count = sum(len(_safe_dict(v)) for v in self.directory.values())
            message_count = len(self.messages)
            latest_id = _to_int(self.messages[-1].get("id"), 0) if self.messages else 0
        return {
            "ok": True,
            "cluster_count": cluster_count,
            "registered_agent_count": agent_count,
            "message_count": message_count,
            "latest_message_id": latest_id,
            "max_messages": int(self.max_messages),
        }


class DistributedRelayRequestHandler(BaseHTTPRequestHandler):
    backend = None

    def _read_json(self):
        raw_len = self.headers.get("Content-Length", "0")
        size = _to_int(raw_len, 0)
        if size <= 0:
            return {}
        raw = self.rfile.read(size)
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/health":
            self._write_json(200, {"ok": True})
            return
        if path == "/snapshot":
            self._write_json(200, self.backend.snapshot())
            return
        if path == "/directory":
            cluster = (query.get("cluster") or ["default"])[0]
            self._write_json(200, self.backend.get_directory(cluster))
            return
        self._write_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path == "/register":
            payload = self._read_json()
            data = self.backend.register_agents(
                cluster=payload.get("cluster", "default"),
                node_id=payload.get("node_id", "node"),
                agents=payload.get("agents", []),
            )
            self._write_json(200, data)
            return
        if self.path == "/message/send":
            payload = self._read_json()
            data = self.backend.send_message(
                cluster=payload.get("cluster", "default"),
                node_id=payload.get("node_id", "node"),
                message=payload.get("message", {}),
            )
            status = 200 if data.get("ok") else 400
            self._write_json(status, data)
            return
        if self.path == "/message/poll":
            payload = self._read_json()
            data = self.backend.poll_messages(
                cluster=payload.get("cluster", "default"),
                recipient_ids=payload.get("recipient_ids", []),
                since_map=payload.get("since", {}),
                limit=payload.get("limit", 100),
            )
            self._write_json(200, data)
            return
        self._write_json(404, {"ok": False, "error": "not found"})


def run_server(host, port, state_path, max_messages):
    backend = DistributedRelayBackend(state_path=state_path, max_messages=max_messages)
    DistributedRelayRequestHandler.backend = backend
    server = ThreadingHTTPServer((host, int(port)), DistributedRelayRequestHandler)
    print(f"[distributed-relay] listening on http://{host}:{int(port)}")
    print(f"[distributed-relay] state path: {state_path}")
    print(f"[distributed-relay] max messages: {int(max_messages)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _build_arg_parser():
    parser = argparse.ArgumentParser(description="Distributed communication relay server")
    distributed_cfg = CONFIG.get("distributed", {})
    server_cfg = distributed_cfg.get("server", {}) if isinstance(distributed_cfg.get("server"), dict) else {}
    parser.add_argument("--host", default=server_cfg.get("host", "0.0.0.0"), help="Bind host")
    parser.add_argument("--port", type=int, default=_to_int(server_cfg.get("port", 8877), 8877), help="Bind port")
    parser.add_argument(
        "--state-path",
        default=server_cfg.get("state_path", "output/distributed/relay_state.json"),
        help="State persistence path",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=_to_int(server_cfg.get("max_messages", 20000), 20000),
        help="Max retained messages",
    )
    return parser


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()
    run_server(
        host=args.host,
        port=args.port,
        state_path=args.state_path,
        max_messages=args.max_messages,
    )


if __name__ == "__main__":
    main()
