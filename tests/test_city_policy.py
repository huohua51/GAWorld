"""Tests for audited urban-policy activation and resident response."""

from __future__ import annotations

from pathlib import Path

from gaworld.city.policy import PolicyEvent, UrbanPolicyChannel


def _residents() -> list[dict[str, object]]:
    return [
        {
            "agent_id": "low-1",
            "group": "low_income",
            "state": {"travel_mode": "metro", "commute_cost": 8},
        },
        {
            "agent_id": "high-1",
            "group": "high_income",
            "state": {"travel_mode": "metro", "commute_cost": 8},
        },
    ]


def _policy() -> PolicyEvent:
    return PolicyEvent(
        policy_id="fare-v2",
        policy_version="v2",
        effective_step=4,
        condition="real_policy",
        target_groups=("low_income",),
        signal={"name": "metro fare change"},
    )


def _channel(tmp_path: Path) -> UrbanPolicyChannel:
    return UrbanPolicyChannel(
        str(tmp_path / "policy.jsonl"),
        _residents(),
        {
            "keep_current": {},
            "switch_to_bus": {"travel_mode": "bus", "commute_cost": 5},
        },
    )


def test_policy_activates_only_at_registered_step(tmp_path: Path) -> None:
    channel = _channel(tmp_path)
    channel.register_policy(_policy())

    channel.advance_to(3)
    early = channel.perceive("fare-v2", "low-1")
    activated = channel.advance_to(4)
    perceived = channel.perceive("fare-v2", "low-1")

    assert early["reason"] == "policy_not_active"
    assert activated["activated"] == ["fare-v2"]
    assert perceived["eligible"] is True


def test_targeting_is_observed_but_does_not_rewrite_actions(tmp_path: Path) -> None:
    channel = _channel(tmp_path)
    channel.register_policy(_policy())
    channel.advance_to(4)
    low = channel.perceive("fare-v2", "low-1")
    high = channel.perceive("fare-v2", "high-1")

    assert low["eligible"] is True
    assert high["eligible"] is False
    assert channel.state_of("low-1") == channel.baseline_of("low-1")


def test_non_default_action_requires_perceived_policy(tmp_path: Path) -> None:
    channel = _channel(tmp_path)
    denied = channel.submit_action("low-1", "switch_to_bus", evidence_policy_id="fare-v2")
    default = channel.submit_action("low-1", "keep_current", evidence_policy_id=None)

    assert denied["reason"] == "action_evidence_not_perceived"
    assert default["ok"] is True


def test_explicit_resident_action_updates_only_registered_fields(tmp_path: Path) -> None:
    channel = _channel(tmp_path)
    channel.register_policy(_policy())
    channel.advance_to(4)
    channel.perceive("fare-v2", "low-1")
    result = channel.submit_action("low-1", "switch_to_bus", evidence_policy_id="fare-v2")

    assert result["ok"] is True
    assert result["state"] == {"travel_mode": "bus", "commute_cost": 5}
    assert result["action"]["changed_fields"] == ["commute_cost", "travel_mode"]
    assert channel.state_of("high-1") == channel.baseline_of("high-1")


def test_jsonl_replay_restores_policy_state_and_action(tmp_path: Path) -> None:
    channel = _channel(tmp_path)
    channel.register_policy(_policy())
    channel.advance_to(4)
    channel.perceive("fare-v2", "low-1")
    channel.submit_action("low-1", "switch_to_bus", evidence_policy_id="fare-v2")

    replayed = _channel(tmp_path)

    assert replayed.policy_active("fare-v2") is True
    assert replayed.state_of("low-1")["travel_mode"] == "bus"
    assert replayed.action_of("low-1")["evidence_policy_id"] == "fare-v2"
