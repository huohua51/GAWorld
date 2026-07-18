from __future__ import annotations

import json
import threading
import time
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

import gaworld.apps.dashboard_server as ds


class FakeCollaborationService:
    def __init__(self):
        self.calls = []
        self.shutdown_calls = 0
        self.sessions = {
            "s1": {
                "id": "s1",
                "kind": "discussion",
                "member_ids": [1, 2],
                "status": "running",
                "artifacts": [
                    {"path": "artifacts/result.md", "filename": "result.md"},
                    {"path": "../../outside.txt", "filename": "outside.txt"},
                    {"path": "/etc/passwd", "filename": "passwd"},
                    "/etc/shadow",
                ],
            }
        }

    def shutdown(self):
        self.shutdown_calls += 1

    def make_friends(self, agent_ids):
        self.calls.append(("make_friends", list(agent_ids)))
        if not agent_ids:
            raise ValueError("agent_ids are required")
        return {
            "created_pairs": [[1, 2]],
            "updated_pairs": [],
            "existing_pairs": [],
        }

    def create_discussion(self, agent_ids, *, topic, max_rounds):
        self.calls.append(
            (
                "create_discussion",
                list(agent_ids),
                topic,
                max_rounds,
            )
        )
        payload = {
            "id": "discussion-1",
            "kind": "discussion",
            "member_ids": list(agent_ids),
            "topic": topic,
            "max_rounds": max_rounds,
            "status": "queued",
            "artifacts": [],
        }
        self.sessions[payload["id"]] = payload
        return SimpleNamespace(to_dict=lambda: dict(payload))

    def create_cooperation(
        self,
        agent_ids,
        *,
        task,
        leader_id=None,
        role_overrides=None,
    ):
        self.calls.append(
            (
                "create_cooperation",
                list(agent_ids),
                task,
                leader_id,
                role_overrides,
            )
        )
        payload = {
            "id": "cooperation-1",
            "kind": "cooperation",
            "member_ids": list(agent_ids),
            "task": task,
            "leader_id": leader_id,
            "role_overrides": role_overrides or {},
            "status": "queued",
            "artifacts": [],
        }
        self.sessions[payload["id"]] = payload
        return SimpleNamespace(to_dict=lambda: dict(payload))

    def list_sessions(self, *, kind="", status=""):
        self.calls.append(("list_sessions", kind, status))
        if kind == "explode":
            raise RuntimeError("unexpected service failure")
        return [
            dict(session)
            for session in self.sessions.values()
            if (not kind or session["kind"] == kind)
            and (not status or session["status"] == status)
        ]

    def health(self):
        return {"malformed_sessions": []}

    def get_session(self, session_id):
        self.calls.append(("get_session", session_id))
        if session_id not in self.sessions:
            raise KeyError(session_id)
        return dict(self.sessions[session_id])

    def events(self, session_id, *, after=0):
        if session_id not in self.sessions:
            raise KeyError(session_id)
        self.calls.append(("events", session_id, after))
        return [
            {"seq": seq, "type": "message", "content": f"event {seq}"}
            for seq in range(after + 1, 4)
        ]

    def pause(self, session_id):
        return self._action("pause", session_id, "paused")

    def resume(self, session_id):
        return self._action("resume", session_id, "running")

    def cancel(self, session_id):
        return self._action("cancel", session_id, "cancelled")

    def _action(self, action, session_id, status):
        if session_id not in self.sessions:
            raise KeyError(session_id)
        self.calls.append((action, session_id))
        result = dict(self.sessions[session_id])
        result["status"] = status
        self.sessions[session_id] = result
        return result


def _request_json(base_url, path, *, method="GET", payload=None, raw=None):
    data = raw
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(
        base_url + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def get_json(api_server, path):
    status, payload = _request_json(api_server["url"], path)
    assert status == 200
    return payload


def post_json_with_status(api_server, path, payload):
    return _request_json(
        api_server["url"],
        path,
        method="POST",
        payload=payload,
    )


def post_json(api_server, path, payload):
    status, response = post_json_with_status(api_server, path, payload)
    assert status == 200
    return response


@pytest.fixture(autouse=True)
def reset_collaboration_service():
    reset = getattr(
        ds,
        "_reset_collaboration_service_for_tests",
        lambda: None,
    )
    reset()
    yield
    reset()


@pytest.fixture
def api_server(monkeypatch, tmp_path):
    fake = FakeCollaborationService()
    monkeypatch.setattr(ds, "REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(
        ds,
        "_effective_config",
        lambda: {
            "collaboration": {
                "sessions_dir": "runtime/sessions",
            },
            "memory_dir": "runtime/memory",
        },
    )
    monkeypatch.setattr(
        ds,
        "_COLLABORATION_SERVICE",
        fake,
        raising=False,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), ds.DashboardHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    host, port = server.server_address
    fixture = {
        "url": f"http://{host}:{port}",
        "service": fake,
        "root": tmp_path,
    }
    try:
        yield fixture
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_friendship_endpoint_returns_service_result(api_server):
    payload = post_json(
        api_server,
        "/api/relationships/friends",
        {"agent_ids": [1, 2]},
    )

    assert payload["created_pairs"] == [[1, 2]]
    assert api_server["service"].calls[-1] == ("make_friends", [1, 2])


def test_discussion_create_detail_and_incremental_events(api_server):
    created = post_json(
        api_server,
        "/api/collaboration/sessions",
        {
            "kind": "discussion",
            "agent_ids": [1, 2],
            "topic": "公共空间",
            "max_rounds": 6,
        },
    )
    detail = get_json(
        api_server,
        f"/api/collaboration/sessions/{created['id']}",
    )
    events = get_json(
        api_server,
        f"/api/collaboration/sessions/{created['id']}/events?after=1",
    )

    assert detail["kind"] == "discussion"
    assert all(event["seq"] > 1 for event in events["events"])
    assert ("events", created["id"], 1) in api_server["service"].calls


def test_cooperation_creation_forwards_leader_and_roles(api_server):
    created = post_json(
        api_server,
        "/api/collaboration/sessions",
        {
            "kind": "cooperation",
            "agent_ids": [1, 2],
            "task": "共同报告",
            "leader_id": 2,
            "role_overrides": {"1": "研究", "2": "编辑"},
        },
    )

    assert created["kind"] == "cooperation"
    assert api_server["service"].calls[-1] == (
        "create_cooperation",
        [1, 2],
        "共同报告",
        2,
        {"1": "研究", "2": "编辑"},
    )


def test_session_list_forwards_filters_and_wraps_health(api_server):
    query = urlencode({"kind": "discussion", "status": "running"})

    payload = get_json(
        api_server,
        f"/api/collaboration/sessions?{query}",
    )

    assert [item["id"] for item in payload["sessions"]] == ["s1"]
    assert payload["health"] == {"malformed_sessions": []}
    assert api_server["service"].calls[-1] == (
        "list_sessions",
        "discussion",
        "running",
    )


@pytest.mark.parametrize(
    ("action", "expected_status"),
    [
        ("pause", "paused"),
        ("resume", "running"),
        ("cancel", "cancelled"),
    ],
)
def test_session_action_routes(api_server, action, expected_status):
    payload = post_json(
        api_server,
        f"/api/collaboration/sessions/s1/{action}",
        {},
    )

    assert payload["status"] == expected_status
    assert api_server["service"].calls[-1] == (action, "s1")


def test_artifact_links_are_confined_to_repository(api_server):
    payload = get_json(api_server, "/api/collaboration/sessions/s1")

    safe, escaped, absolute = payload["artifacts"]
    assert safe["url"] == (
        "/runtime/sessions/s1/artifacts/result.md"
    )
    assert escaped == {"filename": "outside.txt"}
    assert absolute == {"filename": "passwd"}
    assert api_server["service"].sessions["s1"]["artifacts"][1]["path"] == (
        "../../outside.txt"
    )


@pytest.mark.parametrize(
    ("method", "path", "payload", "raw"),
    [
        ("POST", "/api/collaboration/sessions", {"kind": "invalid"}, None),
        ("POST", "/api/collaboration/sessions/missing/pause", {}, None),
        ("GET", "/api/collaboration/sessions/s1/events?after=bad", None, None),
        ("POST", "/api/relationships/friends", None, b"{bad json"),
    ],
)
def test_invalid_requests_return_400(
    api_server,
    method,
    path,
    payload,
    raw,
):
    status, response = _request_json(
        api_server["url"],
        path,
        method=method,
        payload=payload,
        raw=raw,
    )

    assert status == 400
    assert response["error"]


def test_unknown_endpoint_is_404_and_unexpected_failure_is_500(api_server):
    unknown_status, unknown = _request_json(
        api_server["url"],
        "/api/collaboration/unknown",
    )
    failure_status, failure = _request_json(
        api_server["url"],
        "/api/collaboration/sessions?kind=explode",
    )

    assert unknown_status == 404
    assert unknown == {"error": "Unknown endpoint"}
    assert failure_status == 500
    assert failure == {"error": "unexpected service failure"}


def test_lazy_service_is_thread_safe_and_reset_stops_it(monkeypatch, tmp_path):
    from gaworld.collaboration import service as service_module
    from gaworld.llm import providers
    from gaworld.memory import experience

    created = []
    episodes = []

    class StandaloneService:
        def __init__(self, **kwargs):
            time.sleep(0.01)
            self.kwargs = kwargs
            self.started = 0
            self.stopped = 0
            created.append(self)

        def start(self):
            self.started += 1

        def shutdown(self):
            self.stopped += 1

    fake_llm = lambda *args, **kwargs: "ok"
    monkeypatch.setattr(
        service_module,
        "CollaborationService",
        StandaloneService,
    )
    monkeypatch.setattr(providers, "call_llm", fake_llm)
    monkeypatch.setattr(
        experience,
        "append_agent_episode",
        lambda agent_id, episode, cfg=None: episodes.append(
            (agent_id, episode, cfg)
        ),
    )
    monkeypatch.setattr(ds, "REPO_ROOT", str(tmp_path))
    config = {
        "collaboration": {
            "sessions_dir": "var/collaboration",
            "max_concurrent_sessions": 4,
        },
        "memory_dir": "var/memory",
    }
    monkeypatch.setattr(ds, "_effective_config", lambda: config)
    monkeypatch.setattr(
        ds,
        "_agent_detail",
        lambda agent_id: {"identity": {"id": agent_id}},
    )
    barrier = threading.Barrier(8)
    results = []

    def resolve():
        barrier.wait(timeout=5)
        results.append(ds._get_collaboration_service())

    threads = [threading.Thread(target=resolve) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len(created) == 1
    assert all(result is created[0] for result in results)
    assert created[0].started == 1
    assert created[0].kwargs["config"] == config["collaboration"]
    assert created[0].kwargs["sessions_dir"] == (
        tmp_path / "var" / "collaboration"
    ).resolve()
    assert created[0].kwargs["memory_dir"] == (
        tmp_path / "var" / "memory"
    ).resolve()
    assert created[0].kwargs["llm"] is fake_llm
    assert created[0].kwargs["agent_loader"](9) == {
        "identity": {"id": 9}
    }
    created[0].kwargs["episode_writer"](9, {"summary": "done"})
    assert episodes == [(9, {"summary": "done"}, config)]

    ds._reset_collaboration_service_for_tests()
    ds._reset_collaboration_service_for_tests()

    assert created[0].stopped == 1
    assert ds._COLLABORATION_SERVICE is None
