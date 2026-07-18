import json

from gaworld.collaboration.relationships import (
    RelationshipService,
    merge_persisted_agent_edges,
)


def _agent(agent_id):
    return {"identity": {"id": agent_id, "name": f"居民{agent_id}"}}


def test_make_friends_creates_every_reciprocal_pair(tmp_path):
    service = RelationshipService(
        memory_dir=tmp_path,
        agent_loader=lambda agent_id: _agent(agent_id),
    )
    result = service.make_friends([1, 2, 3])

    assert result["created_pairs"] == [[1, 2], [1, 3], [2, 3]]
    for left, right in result["created_pairs"]:
        left_rels = json.loads((tmp_path / f"agent_{left}_relationships.json").read_text())
        right_rels = json.loads((tmp_path / f"agent_{right}_relationships.json").read_text())
        assert left_rels[str(right)]["role"] == "friend"
        assert right_rels[str(left)]["role"] == "friend"
        assert left_rels[str(right)]["closeness"] == 0.65


def test_make_friends_is_idempotent_and_preserves_stronger_role(tmp_path):
    (tmp_path / "agent_1_relationships.json").write_text(
        json.dumps({"2": {"role": "mentor", "closeness": 0.9, "trust": 0.8, "friction": 0.0}}),
        encoding="utf-8",
    )
    service = RelationshipService(memory_dir=tmp_path, agent_loader=lambda agent_id: _agent(agent_id))
    service.make_friends([1, 2])
    second = service.make_friends([1, 2])
    rel = json.loads((tmp_path / "agent_1_relationships.json").read_text())["2"]

    assert rel["role"] == "mentor"
    assert rel["closeness"] == 0.9
    assert second["existing_pairs"] == [[1, 2]]


def test_make_friends_rejects_missing_agent_without_writes(tmp_path):
    service = RelationshipService(
        memory_dir=tmp_path,
        agent_loader=lambda agent_id: _agent(agent_id) if agent_id != 9 else None,
    )
    try:
        service.make_friends([1, 9])
    except ValueError as exc:
        assert "9" in str(exc)
    else:
        raise AssertionError("missing agent was accepted")
    assert list(tmp_path.iterdir()) == []


def test_merge_persisted_edges_updates_runtime_neighbors():
    agents = [
        {
            "id": 1,
            "social_neighbors": [],
            "relationships": {"2": {"kind": "agent", "role": "friend"}},
        },
        {"id": 2, "social_neighbors": [], "relationships": {}},
    ]
    merge_persisted_agent_edges(agents)
    assert agents[0]["social_neighbors"] == [2]
    assert agents[1]["social_neighbors"] == [1]


def test_touch_interaction_updates_existing_edges_without_creating_new_ones(tmp_path):
    service = RelationshipService(memory_dir=tmp_path, agent_loader=lambda agent_id: _agent(agent_id))
    service.make_friends([1, 2])
    service.touch_interaction([1, 2, 3])
    rels_1 = json.loads((tmp_path / "agent_1_relationships.json").read_text())
    assert rels_1["2"]["last_dashboard_interaction_at"]
    assert "3" not in rels_1
