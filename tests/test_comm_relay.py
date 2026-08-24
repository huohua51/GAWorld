"""Permission and delivery tests for RelayChannel."""

from __future__ import annotations

import os
import tempfile
import unittest

from gaworld.comm.relay import RelayAction, RelayChannel


class TestRelayChannel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ch = RelayChannel(os.path.join(self.tmp, "relay.jsonl"))
        self.task = "road_status_001"
        self.ch.put_private(self.task, "verifier", {"trusted_source_id": "src_ok"})

    def _raw_pair(self):
        self.ch.send_raw(self.task, observer_id=1, message={"source_id": "src_ok", "reported_state": "main_open"})
        self.ch.send_raw(self.task, observer_id=1, message={"source_id": "src_no", "reported_state": "main_closed"})
        self.ch.deliver_raw(self.task)

    def test_dispatcher_cannot_read_trust_table(self):
        out = self.ch.read_private(self.task, "dispatcher", "verifier")
        self.assertFalse(out["ok"])
        self.assertEqual("unauthorized_private_read", out["reason"])

    def test_verifier_cannot_submit_action(self):
        out = self.ch.reject_submit(self.task, "verifier")
        self.assertFalse(out["ok"])
        self.assertEqual("unauthorized_action_submit", out["reason"])

    def test_wrong_source_is_rejected(self):
        self._raw_pair()
        out = self.ch.emit_verified(
            self.task,
            verifier_id=2,
            payload={"verified_state": "main_closed", "source_id": "src_no", "state_version": "v1"},
        )
        self.assertFalse(out["ok"])
        self.assertEqual("wrong_source_verified", out["reason"])

    def test_drop_verified_does_not_enter_inbox(self):
        self._raw_pair()
        self.ch.emit_verified(
            self.task,
            verifier_id=2,
            payload={"verified_state": "main_open", "source_id": "src_ok", "state_version": "v1"},
        )
        dropped = self.ch.deliver_verified(self.task, drop=True)
        self.assertTrue(dropped["dropped"])
        inbox = self.ch.read_inbox(self.task, "dispatcher")
        self.assertEqual([], inbox["messages"])

    def test_adopt_once_and_submit(self):
        self._raw_pair()
        emitted = self.ch.emit_verified(
            self.task,
            verifier_id=2,
            payload={"verified_state": "main_open", "source_id": "src_ok", "state_version": "v1"},
        )
        self.ch.deliver_verified(self.task)
        mid = emitted["message"]["message_id"]
        first = self.ch.adopt_verified(self.task, mid)
        again = self.ch.adopt_verified(self.task, mid)
        self.assertTrue(first["ok"])
        self.assertFalse(again["ok"])
        self.assertEqual("verified_already_adopted", again["reason"])
        submitted = self.ch.submit_action(
            self.task,
            dispatcher_id=3,
            payload={
                "action": "submit_route",
                "value": "main_route",
                "adopted_state_version": "v1",
                "evidence_message_id": mid,
            },
        )
        self.assertTrue(submitted["ok"])

    def test_stale_verified_is_rejected(self):
        self._raw_pair()
        emitted = self.ch.emit_verified(
            self.task,
            verifier_id=2,
            payload={"verified_state": "main_open", "source_id": "src_ok", "state_version": "v1"},
        )
        self.ch.deliver_verified(self.task)
        out = self.ch.adopt_verified(
            self.task, emitted["message"]["message_id"], current_version="v2"
        )
        self.assertFalse(out["ok"])
        self.assertEqual("stale_state_used", out["reason"])

    def test_action_round_trip(self):
        action = RelayAction.from_dict(
            {
                "action": "submit_route",
                "value": "alternate_route",
                "adopted_state_version": "v2",
                "evidence_message_id": "verified-msg-x",
            }
        )
        self.assertEqual(action, RelayAction.from_dict(action.to_dict()))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
