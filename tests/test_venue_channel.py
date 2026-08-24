"""Permission, delivery, and schedule tests for VenueEventChannel."""

from __future__ import annotations

import os
import tempfile
import unittest

from city_map_system import load_city_map
from gaworld.life.venue import VenueEventChannel


class TestVenueEventChannel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.city = load_city_map("citymap.md")
        self.ch = VenueEventChannel(os.path.join(self.tmp, "venue.jsonl"), city_map=self.city)
        self.task = "restaurant_close_001"
        self.original = "Student Canteen"
        self.alternative = "Riverside Night Market"
        self.distractor = "Riverside Community Hospital"
        self.ch.register_venues(
            self.task,
            {
                self.original: {"type": "restaurant", "status": "open"},
                self.alternative: {"type": "restaurant", "status": "open"},
                self.distractor: {"type": "clinic", "status": "open"},
            },
            origin="Central Block",
            required_type="restaurant",
            slot_id="visit_1200",
        )
        self.ch.set_schedule(
            self.task,
            [
                {"slot_id": "visit_1200", "start": "12:00", "end": "13:00", "destination": self.original},
                {"slot_id": "after_1400", "start": "14:00", "end": "15:00", "destination": "Central Block"},
            ],
        )

    def _inject_closed(self):
        return self.ch.inject_event(
            self.task,
            venue_id=self.original,
            status="closed",
            state_version="v2",
            slot_id="visit_1200",
        )

    def test_inject_updates_world_status(self):
        out = self._inject_closed()
        self.assertTrue(out["ok"])
        self.assertEqual("closed", self.ch.venue_of(self.task, self.original)["status"])
        self.assertEqual("v2", out["payload"]["state_version"])

    def test_drop_does_not_enter_inbox(self):
        self._inject_closed()
        self.ch.package_perception(self.task)
        dropped = self.ch.deliver_perception(self.task, drop=True)
        self.assertTrue(dropped["dropped"])
        self.assertEqual([], self.ch.inbox_of(self.task))

    def test_full_delivers_perception(self):
        injected = self._inject_closed()
        self.ch.package_perception(self.task)
        self.ch.deliver_perception(self.task)
        inbox = self.ch.read_perception(self.task, "agent")
        self.assertEqual(1, len(inbox["notices"]))
        self.assertEqual(injected["payload"]["event_id"], inbox["notices"][0]["event_id"])

    def test_environment_cannot_submit_or_rewrite(self):
        denied = self.ch.reject_submit(self.task, "environment")
        self.assertFalse(denied["ok"])
        self.assertEqual("unauthorized_action_submit", denied["reason"])
        rewrite = self.ch.rewrite_schedule(self.task, "environment", [])
        self.assertEqual("environment_rewrote_schedule", rewrite["reason"])

    def test_agent_submit_overwrites_slot_only(self):
        injected = self._inject_closed()
        self.ch.seed_direct(self.task)
        self.ch.adopt_event(self.task, injected["payload"]["event_id"])
        submitted = self.ch.submit_action(
            self.task,
            agent_id=1,
            payload={
                "action": "update_visit",
                "destination": self.alternative,
                "slot_id": "visit_1200",
                "adopted_state_version": "v2",
                "evidence_event_id": injected["payload"]["event_id"],
            },
        )
        self.assertTrue(submitted["ok"])
        self.assertEqual(self.alternative, self.ch.slot_of(self.task, "visit_1200")["destination"])
        self.assertEqual("Central Block", self.ch.slot_of(self.task, "after_1400")["destination"])
        self.assertTrue(self.ch.destination_open(self.task, self.alternative))
        self.assertTrue(self.ch.type_match(self.task, self.alternative))
        self.assertFalse(self.ch.type_match(self.task, self.distractor))
        self.assertTrue(self.ch.reachable(self.task, self.alternative))
        self.assertFalse(self.ch.schedule_conflict(self.task))
        self.assertTrue(self.ch.old_schedule_overwritten(self.task, self.original, must_change=True))

    def test_missing_action_fields_denied(self):
        out = self.ch.submit_action(self.task, agent_id=1, payload={"action": "update_visit"})
        self.assertFalse(out["ok"])
        self.assertEqual("fields_not_extractable", out["reason"])


if __name__ == "__main__":
    unittest.main()
