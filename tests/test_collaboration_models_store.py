from gaworld.collaboration.models import CollaborationSession, SessionStatus


def test_session_round_trip_preserves_public_fields():
    session = CollaborationSession.new(
        kind="discussion",
        member_ids=[3, 1],
        topic="城市公共空间",
        max_rounds=6,
    )
    restored = CollaborationSession.from_dict(session.to_dict())
    assert restored.id == session.id
    assert restored.kind == "discussion"
    assert restored.member_ids == [3, 1]
    assert restored.status is SessionStatus.QUEUED
    assert restored.max_rounds == 6


def test_transition_table_rejects_completed_to_running():
    session = CollaborationSession.new(kind="discussion", member_ids=[1, 2])
    session.transition(SessionStatus.RUNNING)
    session.transition(SessionStatus.COMPLETED)
    try:
        session.transition(SessionStatus.RUNNING)
    except ValueError as exc:
        assert "completed" in str(exc)
    else:
        raise AssertionError("terminal session accepted an invalid transition")
