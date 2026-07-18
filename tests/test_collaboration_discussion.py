import json

import pytest

from gaworld.collaboration.discussion import DiscussionRunner
from gaworld.collaboration.models import CollaborationSession, SessionStatus
from gaworld.collaboration.store import SessionStore


def _agent(agent_id):
    return {"identity": {"id": agent_id}}


def test_discussion_runs_round_robin_and_writes_summary(tmp_path):
    calls = []

    def llm(prompt, task=None, agent_id=None):
        calls.append((task, agent_id))
        if task == "collaboration_discussion_summary":
            return "双方同意先做社区试点。"
        return json.dumps({"content": f"居民{agent_id}的观点", "converged": False}, ensure_ascii=False)

    store = SessionStore(tmp_path)
    session = CollaborationSession.new(
        kind="discussion",
        member_ids=[2, 1],
        topic="公共空间",
        max_rounds=3,
    )
    store.create(session)
    runner = DiscussionRunner(store=store, agent_loader=_agent, llm=llm)
    runner.run(session.id)

    messages = [event for event in store.events(session.id) if event.type == "message"]
    assert [event.agent_id for event in messages] == [2, 1, 2]
    assert store.get(session.id).status is SessionStatus.COMPLETED
    assert store.events(session.id)[-1].type == "completed"
    assert calls[-1][0] == "collaboration_discussion_summary"


def test_discussion_honors_pause_before_next_turn(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(kind="discussion", member_ids=[1, 2], max_rounds=4)
    store.create(session)
    session.transition(SessionStatus.RUNNING)
    session.transition(SessionStatus.PAUSED)
    store.save(session)
    runner = DiscussionRunner(store=store, agent_loader=_agent, llm=lambda *a, **k: "")

    runner.run(session.id)

    assert not [event for event in store.events(session.id) if event.type == "message"]
    assert store.get(session.id).status is SessionStatus.PAUSED


def test_discussion_persists_in_flight_response_then_honors_pause(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(kind="discussion", member_ids=[1, 2], max_rounds=3)
    store.create(session)
    episodes = []
    interactions = []

    def llm(prompt, task=None, agent_id=None):
        active = store.get(session.id)
        active.transition(SessionStatus.PAUSED)
        store.save(active)
        return json.dumps({"content": "迟到的回复", "converged": False}, ensure_ascii=False)

    runner = DiscussionRunner(
        store=store,
        agent_loader=_agent,
        llm=llm,
        episode_writer=lambda agent_id, episode: episodes.append((agent_id, episode)),
        interaction_writer=interactions.append,
    )

    runner.run(session.id)

    restored = store.get(session.id)
    messages = [event for event in store.events(session.id) if event.type == "message"]
    assert restored.status is SessionStatus.PAUSED
    assert restored.current_round == 1
    assert [event.content for event in messages] == ["迟到的回复"]
    assert not episodes
    assert not interactions


def test_discussion_discards_in_flight_response_after_cancel(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(kind="discussion", member_ids=[1, 2], max_rounds=3)
    store.create(session)

    def llm(prompt, task=None, agent_id=None):
        active = store.get(session.id)
        active.transition(SessionStatus.CANCELLED)
        store.save(active)
        return json.dumps({"content": "迟到的回复", "converged": False}, ensure_ascii=False)

    runner = DiscussionRunner(store=store, agent_loader=_agent, llm=llm)

    runner.run(session.id)

    restored = store.get(session.id)
    assert restored.status is SessionStatus.CANCELLED
    assert restored.current_round == 0
    assert not [event for event in store.events(session.id) if event.type == "message"]


def test_discussion_discards_in_flight_summary_after_cancel(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(kind="discussion", member_ids=[1, 2], max_rounds=1)
    store.create(session)

    def llm(prompt, task=None, agent_id=None):
        if task == "collaboration_discussion_summary":
            active = store.get(session.id)
            active.transition(SessionStatus.CANCELLED)
            store.save(active)
            return "迟到的总结"
        return json.dumps({"content": "讨论内容", "converged": False}, ensure_ascii=False)

    DiscussionRunner(store=store, agent_loader=_agent, llm=llm).run(session.id)

    events = store.events(session.id)
    assert store.get(session.id).status is SessionStatus.CANCELLED
    assert not [event for event in events if event.type == "summary"]
    assert not [event for event in events if event.type == "completed"]


def test_discussion_reuses_in_flight_summary_after_pause_without_duplicate(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(kind="discussion", member_ids=[1, 2], max_rounds=1)
    store.create(session)
    summary_calls = 0

    def llm(prompt, task=None, agent_id=None):
        nonlocal summary_calls
        if task == "collaboration_discussion_summary":
            summary_calls += 1
            active = store.get(session.id)
            active.transition(SessionStatus.PAUSED)
            store.save(active)
            return "可复用的总结"
        return json.dumps({"content": "讨论内容", "converged": False}, ensure_ascii=False)

    runner = DiscussionRunner(store=store, agent_loader=_agent, llm=llm)
    runner.run(session.id)

    assert store.get(session.id).status is SessionStatus.PAUSED
    assert [event.content for event in store.events(session.id) if event.type == "summary"] == [
        "可复用的总结"
    ]

    resumed = store.get(session.id)
    resumed.transition(SessionStatus.RUNNING)
    store.save(resumed)
    runner.run(session.id)

    events = store.events(session.id)
    assert store.get(session.id).status is SessionStatus.COMPLETED
    assert summary_calls == 1
    assert len([event for event in events if event.type == "summary"]) == 1
    assert len([event for event in events if event.type == "completed"]) == 1


def test_discussion_resume_uses_persisted_convergence_without_extra_turn(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(kind="discussion", member_ids=[1, 2], max_rounds=5)
    store.create(session)
    discussion_calls = 0
    summary_calls = 0

    def llm(prompt, task=None, agent_id=None):
        nonlocal discussion_calls, summary_calls
        if task == "collaboration_discussion_summary":
            summary_calls += 1
            return "已经收敛。"
        discussion_calls += 1
        converged = discussion_calls == 2
        if converged:
            active = store.get(session.id)
            active.transition(SessionStatus.PAUSED)
            store.save(active)
        return json.dumps(
            {"content": f"第{discussion_calls}轮", "converged": converged},
            ensure_ascii=False,
        )

    runner = DiscussionRunner(store=store, agent_loader=_agent, llm=llm)
    runner.run(session.id)

    messages = [event for event in store.events(session.id) if event.type == "message"]
    assert store.get(session.id).status is SessionStatus.PAUSED
    assert store.get(session.id).current_round == 2
    assert messages[-1].metadata["converged"] is True

    resumed = store.get(session.id)
    resumed.transition(SessionStatus.RUNNING)
    store.save(resumed)
    runner.run(session.id)

    assert store.get(session.id).status is SessionStatus.COMPLETED
    assert discussion_calls == 2
    assert summary_calls == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", "本轮未生成有效发言。"),
        (json.dumps({"converged": False}), "本轮未生成有效发言。"),
        ("自然语言回复", "自然语言回复"),
    ],
)
def test_discussion_falls_back_for_empty_or_model_invalid_responses(tmp_path, raw, expected):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(kind="discussion", member_ids=[1, 2], max_rounds=1)
    store.create(session)

    def llm(prompt, task=None, agent_id=None):
        if task == "collaboration_discussion_summary":
            return ""
        return raw

    DiscussionRunner(store=store, agent_loader=_agent, llm=llm).run(session.id)

    events = store.events(session.id)
    message = next(event for event in events if event.type == "message")
    summary = next(event for event in events if event.type == "summary")
    assert message.content == expected
    assert summary.content == "讨论已完成，暂无可用摘要。"
    assert store.get(session.id).status is SessionStatus.COMPLETED


def test_discussion_retries_transient_llm_errors(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(kind="discussion", member_ids=[1, 2], max_rounds=1)
    store.create(session)
    attempts = 0

    def llm(prompt, task=None, agent_id=None):
        nonlocal attempts
        if task == "collaboration_discussion_summary":
            return "重试后完成。"
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary")
        return json.dumps({"content": "恢复后的回复", "converged": False}, ensure_ascii=False)

    DiscussionRunner(
        store=store,
        agent_loader=_agent,
        llm=llm,
        step_retries=2,
    ).run(session.id)

    assert attempts == 3
    assert store.get(session.id).status is SessionStatus.COMPLETED


def test_discussion_marks_failed_after_retry_budget_is_exhausted(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(kind="discussion", member_ids=[1, 2], max_rounds=1)
    store.create(session)
    attempts = 0

    def llm(prompt, task=None, agent_id=None):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("provider unavailable")

    DiscussionRunner(
        store=store,
        agent_loader=_agent,
        llm=llm,
        step_retries=1,
    ).run(session.id)

    restored = store.get(session.id)
    assert attempts == 2
    assert restored.status is SessionStatus.FAILED
    assert "provider unavailable" in restored.error
    assert store.events(session.id)[-1].type == "error"


def test_discussion_writes_member_episodes_and_touches_interactions_on_completion(tmp_path):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(kind="discussion", member_ids=[4, 5], max_rounds=2)
    store.create(session)
    episodes = []
    interactions = []

    def llm(prompt, task=None, agent_id=None):
        if task == "collaboration_discussion_summary":
            return "形成共同结论。"
        return json.dumps({"content": f"成员{agent_id}发言", "converged": False}, ensure_ascii=False)

    runner = DiscussionRunner(
        store=store,
        agent_loader=_agent,
        llm=llm,
        episode_writer=lambda agent_id, episode: episodes.append((agent_id, episode)),
        interaction_writer=lambda member_ids: interactions.append(list(member_ids)),
    )

    runner.run(session.id)

    assert [agent_id for agent_id, _episode in episodes] == [4, 5]
    for _agent_id, episode in episodes:
        assert episode == {
            "source": "collaboration",
            "session_id": session.id,
            "kind": "discussion",
            "summary": "形成共同结论。",
            "salience": 0.65,
        }
    assert interactions == [[4, 5]]


@pytest.mark.parametrize("failure_target", ["episode", "interaction"])
def test_discussion_resumes_only_missing_completion_side_effects(tmp_path, failure_target):
    store = SessionStore(tmp_path)
    session = CollaborationSession.new(kind="discussion", member_ids=[1, 2], max_rounds=1)
    store.create(session)
    episode_attempts = []
    interaction_attempts = []

    def llm(prompt, task=None, agent_id=None):
        if task == "collaboration_discussion_summary":
            return "持久化总结"
        return json.dumps({"content": "发言", "converged": False}, ensure_ascii=False)

    def episode_writer(agent_id, episode):
        episode_attempts.append(agent_id)
        if failure_target == "episode" and agent_id == 2 and episode_attempts.count(2) == 1:
            raise RuntimeError("episode write failed")

    def interaction_writer(member_ids):
        interaction_attempts.append(list(member_ids))
        if failure_target == "interaction" and len(interaction_attempts) == 1:
            raise RuntimeError("interaction write failed")

    runner = DiscussionRunner(
        store=store,
        agent_loader=_agent,
        llm=llm,
        episode_writer=episode_writer,
        interaction_writer=interaction_writer,
    )
    runner.run(session.id)

    first_events = store.events(session.id)
    assert store.get(session.id).status is SessionStatus.FAILED
    assert not [event for event in first_events if event.type == "completed"]

    runner.run(session.id)
    runner.run(session.id)

    restored = store.get(session.id)
    events = store.events(session.id)
    markers = [event.metadata for event in events if event.type == "side_effect_completed"]
    assert restored.status is SessionStatus.COMPLETED
    assert restored.error == ""
    assert len([event for event in events if event.type == "summary"]) == 1
    assert len([event for event in events if event.type == "completed"]) == 1
    assert markers == [
        {"effect": "episode", "agent_id": 1},
        {"effect": "episode", "agent_id": 2},
        {"effect": "interaction", "member_ids": [1, 2]},
    ]
    if failure_target == "episode":
        assert episode_attempts == [1, 2, 2]
        assert interaction_attempts == [[1, 2]]
    else:
        assert episode_attempts == [1, 2]
        assert interaction_attempts == [[1, 2], [1, 2]]
