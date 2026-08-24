"""Permission, delivery, update, and relationship tests for TrustLedger."""

from __future__ import annotations

import os
import tempfile
import unittest

from gaworld.comm.trust import TrustAction, TrustLedger
from human_realism import relationship_weight


class TestTrustLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ch = TrustLedger(os.path.join(self.tmp, "trust.jsonl"))
        self.task = "road_status_001"
        self.ch.bind_agent(self.task, {"relationships": {}, "current_day": 1})
        self.ch.put_history(
            self.task,
            "trust_updater",
            [
                {"round": 1, "person_a": "main_open", "person_b": "main_closed", "outcome": "main_open"},
                {"round": 2, "person_a": "main_open", "person_b": "main_closed", "outcome": "main_open"},
            ],
        )

    def _current_pair(self):
        self.ch.send_current(self.task, observer_id=1, message={"person_id": "neighbor_lin", "reported_state": "main_open"})
        self.ch.send_current(self.task, observer_id=1, message={"person_id": "passer_wu", "reported_state": "main_closed"})
        self.ch.deliver_current(self.task)

    def test_dispatcher_cannot_read_history(self):
        out = self.ch.read_history(self.task, "dispatcher")
        self.assertFalse(out["ok"])
        self.assertEqual("unauthorized_history_read", out["reason"])

    def test_trust_updater_cannot_submit_action(self):
        out = self.ch.reject_submit(self.task, "trust_updater")
        self.assertFalse(out["ok"])
        self.assertEqual("unauthorized_action_submit", out["reason"])

    def test_empty_history_cannot_emit(self):
        empty = TrustLedger(os.path.join(self.tmp, "empty.jsonl"))
        empty.send_current("t", observer_id=1, message={"person_id": "a", "reported_state": "open"})
        empty.deliver_current("t")
        out = empty.emit_trust(
            "t",
            updater_id=2,
            payload={"trusted_person_id": "a", "trusted_state": "open", "trust_version": "v1"},
        )
        self.assertFalse(out["ok"])
        self.assertEqual("history_not_available", out["reason"])

    def test_drop_trust_does_not_enter_inbox(self):
        self._current_pair()
        self.ch.emit_trust(
            self.task,
            updater_id=2,
            payload={
                "trusted_person_id": "neighbor_lin",
                "trusted_state": "main_open",
                "trust_version": "v1",
            },
        )
        dropped = self.ch.deliver_trust(self.task, drop=True)
        self.assertTrue(dropped["dropped"])
        inbox = self.ch.read_inbox(self.task, "dispatcher")
        self.assertEqual([], inbox["messages"])

    def test_adopt_v1_then_v2_and_reject_stale(self):
        self._current_pair()
        first = self.ch.emit_trust(
            self.task,
            updater_id=2,
            payload={
                "trusted_person_id": "neighbor_lin",
                "trusted_state": "main_open",
                "trust_version": "v1",
                "other_person_id": "passer_wu",
            },
            round_name="formation",
        )
        self.ch.deliver_trust(self.task)
        mid1 = first["message"]["message_id"]
        self.assertTrue(self.ch.adopt_trust(self.task, mid1)["ok"])
        again = self.ch.adopt_trust(self.task, mid1)
        self.assertFalse(again["ok"])
        self.assertEqual("trust_already_adopted", again["reason"])

        self.ch.append_outcome(
            self.task,
            "trust_updater",
            {"round": 3, "person_a": "main_open", "person_b": "main_closed", "outcome": "main_closed"},
        )
        second = self.ch.emit_trust(
            self.task,
            updater_id=2,
            payload={
                "trusted_person_id": "passer_wu",
                "trusted_state": "main_closed",
                "trust_version": "v2",
                "other_person_id": "neighbor_lin",
            },
            round_name="update",
        )
        self.ch.deliver_trust(self.task)
        mid2 = second["message"]["message_id"]
        self.assertTrue(self.ch.adopt_trust(self.task, mid2)["ok"])
        seeded_stale = self.ch.seed_focused(
            self.task,
            trusted_person_id="neighbor_lin",
            trusted_state="main_open",
            version="v1",
            other_person_id="passer_wu",
        )
        stale = self.ch.adopt_trust(self.task, seeded_stale["message"]["message_id"])
        self.assertFalse(stale["ok"])
        self.assertEqual("stale_trust_used", stale["reason"])

        submitted = self.ch.submit_action(
            self.task,
            dispatcher_id=3,
            payload={
                "action": "submit_route",
                "value": "alternate_route",
                "adopted_trust_version": "v2",
                "evidence_message_id": mid2,
                "round": "update",
            },
        )
        self.assertTrue(submitted["ok"])
        stored = self.ch.action_of(self.task, "update")
        self.assertIsNotNone(stored)
        self.assertEqual("alternate_route", stored.value)

    def test_relationship_updates_on_adopt(self):
        self._current_pair()
        first = self.ch.emit_trust(
            self.task,
            updater_id=2,
            payload={
                "trusted_person_id": "neighbor_lin",
                "trusted_state": "main_open",
                "trust_version": "v1",
                "other_person_id": "passer_wu",
            },
        )
        self.ch.deliver_trust(self.task)
        self.ch.adopt_trust(self.task, first["message"]["message_id"])
        agent = self.ch._agents[self.task]
        self.assertGreater(relationship_weight(agent, "neighbor_lin"), relationship_weight(agent, "passer_wu"))
        rel = self.ch.relationships_of(self.task)
        trust_a = float(rel["neighbor_lin"]["trust"])
        trust_b = float(rel["passer_wu"]["trust"])
        self.assertGreater(trust_a, trust_b)

        second = self.ch.emit_trust(
            self.task,
            updater_id=2,
            payload={
                "trusted_person_id": "passer_wu",
                "trusted_state": "main_closed",
                "trust_version": "v2",
                "other_person_id": "neighbor_lin",
            },
            round_name="update",
        )
        self.ch.deliver_trust(self.task)
        self.ch.adopt_trust(self.task, second["message"]["message_id"])
        rel2 = self.ch.relationships_of(self.task)
        self.assertGreater(float(rel2["passer_wu"]["trust"]), trust_b)
        self.assertLess(float(rel2["neighbor_lin"]["trust"]), trust_a)

    def test_action_round_trip(self):
        action = TrustAction.from_dict(
            {
                "action": "submit_route",
                "value": "alternate_route",
                "adopted_trust_version": "v2",
                "evidence_message_id": "trust-msg-x",
                "round": "update",
            }
        )
        self.assertEqual(action, TrustAction.from_dict(action.to_dict()))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
