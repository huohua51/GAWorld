import json

import pytest

from gaworld.collaboration.cooperation import CooperationRunner
from gaworld.collaboration.models import CollaborationSession, SessionStatus
from gaworld.collaboration.store import SessionStore


def _agent(agent_id):
    return {
        "identity": {"id": agent_id, "name": f"居民{agent_id}"},
        "capabilities": {"skills": ["研究"] if agent_id == 1 else ["数据分析"]},
    }


def _step(title, agent_id, artifact):
    return {
        "title": title,
        "agent_id": agent_id,
        "artifact": artifact,
        "status": "pending",
    }


def _basic_llm(prompt, task=None, agent_id=None):
    if task == "collaboration_review":
        return json.dumps({"approved": True, "feedback": "通过"}, ensure_ascii=False)
    if task == "collaboration_synthesis":
        return "# 最终成果"
    return f"# 成员 {agent_id} 交付"


def test_cooperation_plans_executes_reviews_and_synthesizes(tmp_path):
    def llm(prompt, task=None, agent_id=None):
        if task == "collaboration_plan":
            return json.dumps(
                {
                    "leader_id": 1,
                    "roles": {"1": "研究负责人", "2": "分析员"},
                    "steps": [
                        {"title": "需求研究", "agent_id": 1, "artifact": "research.md"},
                        {"title": "数据归纳", "agent_id": 2, "artifact": "analysis.md"},
                    ],
                },
                ensure_ascii=False,
            )
        if task == "collaboration_review":
            return json.dumps({"approved": True, "feedback": "证据充分"}, ensure_ascii=False)
        if task == "collaboration_synthesis":
            return "# 最终建议\n先开展社区试点。"
        return f"# {agent_id} 的交付\n已完成"

    store = SessionStore(tmp_path)
    session = CollaborationSession.new(
        kind="cooperation",
        member_ids=[1, 2],
        task="形成社区服务行动建议",
    )
    store.create(session)
    runner = CooperationRunner(store=store, agent_loader=_agent, llm=llm)
    runner.run(session.id)

    saved = store.get(session.id)
    event_types = [event.type for event in store.events(session.id)]
    assert saved.status is SessionStatus.COMPLETED
    assert saved.roles == {"1": "研究负责人", "2": "分析员"}
    assert event_types.count("artifact") == 3
    assert "review" in event_types
    assert any(item["filename"] == "final.md" for item in saved.artifacts)


def test_cooperation_uses_fallback_for_malformed_plan(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(
        kind="cooperation",
        member_ids=[1, 2],
        task="整理行动方案",
    )
    store.create(session)

    def llm(prompt, task=None, agent_id=None):
        if task == "collaboration_plan":
            return "{malformed"
        return _basic_llm(prompt, task=task, agent_id=agent_id)

    CooperationRunner(store=store, agent_loader=_agent, llm=llm).run(session.id)

    saved = store.get(session.id)
    assert saved.status is SessionStatus.COMPLETED
    assert saved.leader_id == 1
    assert saved.roles == {"1": "成员1", "2": "成员2"}
    assert [step["artifact"] for step in saved.plan] == ["member_1.md", "member_2.md"]


def test_cooperation_applies_user_leader_and_role_overrides(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(
        kind="cooperation",
        member_ids=[1, 2],
        task="共同研究",
        leader_id=2,
        role_overrides={"1": "访谈员"},
    )
    store.create(session)

    def llm(prompt, task=None, agent_id=None):
        if task == "collaboration_plan":
            return json.dumps(
                {
                    "leader_id": 1,
                    "roles": {"1": "研究员", "2": "分析员"},
                    "steps": [{"title": "访谈", "agent_id": 1, "artifact": "interview.md"}],
                },
                ensure_ascii=False,
            )
        return _basic_llm(prompt, task=task, agent_id=agent_id)

    CooperationRunner(store=store, agent_loader=_agent, llm=llm).run(session.id)

    saved = store.get(session.id)
    assert saved.leader_id == 2
    assert saved.roles == {"1": "访谈员", "2": "分析员"}


def test_cooperation_replaces_unsafe_artifact_name(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(kind="cooperation", member_ids=[1, 2], task="安全交付")
    store.create(session)

    def llm(prompt, task=None, agent_id=None):
        if task == "collaboration_plan":
            return json.dumps(
                {
                    "steps": [
                        {"title": "危险路径", "agent_id": 1, "artifact": "../../escape.md"}
                    ]
                }
            )
        return _basic_llm(prompt, task=task, agent_id=agent_id)

    CooperationRunner(store=store, agent_loader=_agent, llm=llm).run(session.id)

    saved = store.get(session.id)
    assert saved.plan[0]["artifact"] == "member_1_1.md"
    assert (tmp_path / session.id / "artifacts" / "member_1_1.md").is_file()
    assert not (tmp_path / "escape.md").exists()


def test_cooperation_revises_rejected_artifact_once(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(
        kind="cooperation",
        member_ids=[1, 2],
        task="修订研究",
        leader_id=1,
        roles={"1": "作者", "2": "审阅者"},
        plan=[_step("研究", 1, "research.md")],
    )
    store.create(session)
    revision_calls = 0

    def llm(prompt, task=None, agent_id=None):
        nonlocal revision_calls
        if task == "collaboration_execute":
            return "初稿"
        if task == "collaboration_review":
            return json.dumps({"approved": False, "feedback": "补充证据"})
        if task == "collaboration_revision":
            revision_calls += 1
            return "修订稿"
        return "# 汇总"

    CooperationRunner(store=store, agent_loader=_agent, llm=llm).run(session.id)

    events = store.events(session.id)
    assert revision_calls == 1
    assert len([event for event in events if event.type == "review"]) == 1
    assert len([event for event in events if event.type == "revision"]) == 1
    assert (tmp_path / session.id / "artifacts" / "research.md").read_text() == "修订稿"


@pytest.mark.parametrize("target", [SessionStatus.PAUSED, SessionStatus.CANCELLED])
def test_cooperation_stops_at_step_boundary(tmp_path, monkeypatch, target):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(
        kind="cooperation",
        member_ids=[1, 2],
        task="两步任务",
        leader_id=1,
        roles={"1": "成员1", "2": "成员2"},
        plan=[_step("第一步", 1, "one.md"), _step("第二步", 2, "two.md")],
    )
    store.create(session)
    save = store.save
    injected = False

    def inject_boundary_status(candidate):
        nonlocal injected
        saved = save(candidate)
        if (
            not injected
            and candidate.status is SessionStatus.RUNNING
            and candidate.current_step == 1
        ):
            injected = True
            boundary = store.get(session.id)
            boundary.transition(target)
            save(boundary)
        return saved

    monkeypatch.setattr(store, "save", inject_boundary_status)
    CooperationRunner(store=store, agent_loader=_agent, llm=_basic_llm).run(session.id)

    saved = store.get(session.id)
    step_artifacts = [
        event for event in store.events(session.id)
        if event.type == "artifact" and "step_index" in event.metadata
    ]
    assert saved.status is target
    assert saved.current_step == 1
    assert [event.metadata["step_index"] for event in step_artifacts] == [0]
    assert not [event for event in store.events(session.id) if event.metadata.get("final")]


def test_cooperation_marks_failed_after_retry_exhaustion(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(
        kind="cooperation",
        member_ids=[1, 2],
        task="失败任务",
        leader_id=1,
        roles={"1": "作者", "2": "审阅"},
        plan=[_step("执行", 1, "work.md")],
    )
    store.create(session)
    attempts = 0

    def llm(prompt, task=None, agent_id=None):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("execute unavailable")

    CooperationRunner(
        store=store,
        agent_loader=_agent,
        llm=llm,
        step_retries=1,
    ).run(session.id)

    saved = store.get(session.id)
    assert attempts == 2
    assert saved.status is SessionStatus.FAILED
    assert "execute unavailable" in saved.error
    assert saved.current_step == 0
    assert store.events(session.id)[-1].type == "error"


def test_cooperation_resumes_current_step_without_duplicate_artifacts_or_reviews(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(
        kind="cooperation",
        member_ids=[1, 2],
        task="可恢复任务",
        leader_id=1,
        roles={"1": "成员1", "2": "成员2"},
        plan=[_step("第一步", 1, "one.md"), _step("第二步", 2, "two.md")],
    )
    store.create(session)
    failed_once = False

    def llm(prompt, task=None, agent_id=None):
        nonlocal failed_once
        if task == "collaboration_execute" and agent_id == 2 and not failed_once:
            failed_once = True
            raise RuntimeError("second step failed")
        return _basic_llm(prompt, task=task, agent_id=agent_id)

    runner = CooperationRunner(
        store=store,
        agent_loader=_agent,
        llm=llm,
        step_retries=0,
    )
    runner.run(session.id)

    assert store.get(session.id).status is SessionStatus.FAILED
    assert store.get(session.id).current_step == 1

    runner.run(session.id)

    events = store.events(session.id)
    step_artifacts = [
        event.metadata["step_index"]
        for event in events
        if event.type == "artifact" and "step_index" in event.metadata
    ]
    step_reviews = [
        event.metadata["step_index"]
        for event in events
        if event.type == "review"
    ]
    assert store.get(session.id).status is SessionStatus.COMPLETED
    assert step_artifacts == [0, 1]
    assert step_reviews == [0, 1]
    assert len([event for event in events if event.type == "started"]) == 1


def test_cooperation_resumes_missing_episode_side_effect(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(
        kind="cooperation",
        member_ids=[1, 2],
        task="回调恢复",
        leader_id=1,
        roles={"1": "作者", "2": "审阅"},
        plan=[_step("执行", 1, "work.md")],
    )
    store.create(session)
    episode_attempts = []

    def episode_writer(agent_id, episode):
        episode_attempts.append(agent_id)
        if agent_id == 2 and episode_attempts.count(2) == 1:
            raise RuntimeError("episode failed")

    runner = CooperationRunner(
        store=store,
        agent_loader=_agent,
        llm=_basic_llm,
        episode_writer=episode_writer,
    )
    runner.run(session.id)

    assert store.get(session.id).status is SessionStatus.FAILED

    runner.run(session.id)

    events = store.events(session.id)
    assert store.get(session.id).status is SessionStatus.COMPLETED
    assert episode_attempts == [1, 2, 2]
    assert len([event for event in events if event.type == "completed"]) == 1
    assert len(
        [event for event in events if event.type == "artifact" and event.metadata.get("final")]
    ) == 1


def test_cooperation_reuses_completed_marker_after_snapshot_failure(tmp_path, monkeypatch):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(
        kind="cooperation",
        member_ids=[1, 2],
        task="完成恢复",
        leader_id=1,
        roles={"1": "作者", "2": "审阅"},
        plan=[_step("执行", 1, "work.md")],
    )
    store.create(session)
    save = store.save
    failed_once = False

    def fail_first_completed_save(candidate):
        nonlocal failed_once
        if candidate.status is SessionStatus.COMPLETED and not failed_once:
            failed_once = True
            raise OSError("completed snapshot failed")
        return save(candidate)

    monkeypatch.setattr(store, "save", fail_first_completed_save)
    runner = CooperationRunner(store=store, agent_loader=_agent, llm=_basic_llm)
    runner.run(session.id)

    assert store.get(session.id).status is SessionStatus.FAILED
    assert len(
        [event for event in store.events(session.id) if event.type == "completed"]
    ) == 1

    runner.run(session.id)

    events = store.events(session.id)
    assert store.get(session.id).status is SessionStatus.COMPLETED
    assert store.get(session.id).error == ""
    assert len([event for event in events if event.type == "completed"]) == 1
    assert len(
        [event for event in events if event.type == "artifact" and event.metadata.get("final")]
    ) == 1
