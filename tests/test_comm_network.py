"""Deterministic tests for audited multi-hop propagation."""

from __future__ import annotations

from pathlib import Path

from gaworld.comm.network import NetworkPropagationChannel


def _channel(tmp_path: Path) -> NetworkPropagationChannel:
    return NetworkPropagationChannel(
        str(tmp_path / "network.jsonl"),
        [("source", "bridge"), ("bridge", "relay"), ("relay", "target")],
    )


def _inject(channel: NetworkPropagationChannel) -> None:
    result = channel.inject(
        message_id="msg-1",
        source_id="source",
        state_version="v1",
        payload={"action_required": True, "target_action": "reroute"},
    )
    assert result["ok"] is True


def test_message_requires_registered_hops_and_acceptance(tmp_path: Path) -> None:
    channel = _channel(tmp_path)
    _inject(channel)

    jump = channel.deliver("msg-1", "source", "target")
    first = channel.deliver("msg-1", "source", "bridge")
    blocked = channel.deliver("msg-1", "bridge", "relay")
    channel.accept("msg-1", "bridge")
    second = channel.deliver("msg-1", "bridge", "relay")

    assert jump["reason"] == "edge_unavailable"
    assert first["ok"] is True
    assert blocked["reason"] == "sender_has_not_accepted"
    assert second["ok"] is True


def test_bridge_removal_blocks_the_registered_path(tmp_path: Path) -> None:
    channel = _channel(tmp_path)
    _inject(channel)
    channel.deliver("msg-1", "source", "bridge")
    channel.accept("msg-1", "bridge")
    removed = channel.remove_edge("bridge", "relay", intervention_id="remove-bridge")
    delivery = channel.deliver("msg-1", "bridge", "relay")

    assert removed["ok"] is True
    assert delivery["reason"] == "edge_unavailable"
    assert channel.received_by("msg-1", "target") is False


def test_drop_is_audited_without_delivery(tmp_path: Path) -> None:
    channel = _channel(tmp_path)
    _inject(channel)
    dropped = channel.deliver("msg-1", "source", "bridge", drop=True)

    assert dropped == {"ok": True, "dropped": True, "depth": 1}
    assert channel.received_by("msg-1", "bridge") is False
    assert "message_dropped" in channel.event_names()


def test_path_and_action_bind_to_adopted_message(tmp_path: Path) -> None:
    channel = _channel(tmp_path)
    _inject(channel)
    for sender, receiver in (("source", "bridge"), ("bridge", "relay"), ("relay", "target")):
        channel.deliver("msg-1", sender, receiver)
        channel.accept("msg-1", receiver)

    action = channel.submit_action("target", "reroute", message_id="msg-1")

    assert action["ok"] is True
    assert channel.path_to("msg-1", "target") == ["source", "bridge", "relay", "target"]
    assert channel.action_of("target")["evidence_message_id"] == "msg-1"


def test_non_default_action_requires_evidence(tmp_path: Path) -> None:
    channel = _channel(tmp_path)
    denied = channel.submit_action("target", "reroute", message_id=None)
    default = channel.submit_action("target", "keep_current", message_id=None)

    assert denied["reason"] == "action_evidence_missing"
    assert default["ok"] is True


def test_rejection_revokes_acceptance_in_memory_and_replay(tmp_path: Path) -> None:
    channel = _channel(tmp_path)
    _inject(channel)
    channel.deliver("msg-1", "source", "bridge")
    channel.accept("msg-1", "bridge")
    rejected = channel.accept("msg-1", "bridge", accepted=False)

    assert rejected == {"ok": True, "accepted": False}
    assert channel.accepted_by("msg-1", "bridge") is False
    assert channel.deliver("msg-1", "bridge", "relay")["reason"] == ("sender_has_not_accepted")
    assert _channel(tmp_path).accepted_by("msg-1", "bridge") is False


def test_jsonl_replay_restores_delivery_and_action(tmp_path: Path) -> None:
    channel = _channel(tmp_path)
    _inject(channel)
    channel.deliver("msg-1", "source", "bridge")
    channel.accept("msg-1", "bridge")
    channel.submit_action("bridge", "reroute", message_id="msg-1")

    replayed = _channel(tmp_path)

    assert replayed.received_by("msg-1", "bridge") is True
    assert replayed.accepted_by("msg-1", "bridge") is True
    assert replayed.action_of("bridge")["action"] == "reroute"
