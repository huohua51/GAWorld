"""Permission and delivery tests for FamilyCareChannel."""

from __future__ import annotations

import os
import tempfile
import unittest

from gaworld.life.family import NONE, FamilyCareChannel


class TestFamilyCareChannel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ch = FamilyCareChannel(os.path.join(self.tmp, "family.jsonl"))
        self.task = "child_fever_001"
        self.ch.register_household(
            self.task,
            {
                "patient_id": "child-01",
                "legal_caregiver_id": "parent-01",
                "distractor_id": "neighbor-01",
                "conflict_slot_id": "work-slot-01",
                "registered_expense": 200,
            },
        )
        self.ch.set_schedule(
            self.task,
            [{"slot_id": "work-slot-01", "start": "10:00", "end": "12:00", "status": "planned"}],
        )

    def test_inject_and_drop(self):
        injected = self.ch.inject_event(
            self.task, requires_care=True, state_version="v2",
            patient_id="child-01", caregiver_id="parent-01",
            slot_id="work-slot-01", expense_amount=200,
        )
        self.assertTrue(injected["ok"])
        self.ch.package_perception(self.task)
        dropped = self.ch.deliver_perception(self.task, drop=True)
        self.assertTrue(dropped["dropped"])
        self.assertEqual([], self.ch.inbox_of(self.task))

    def test_environment_cannot_assign(self):
        denied = self.ch.assign_caregiver(self.task, "environment", "parent-01")
        self.assertEqual("environment_assigned_caregiver", denied["reason"])

    def test_agent_submit_cancels_and_posts_expense_once(self):
        injected = self.ch.inject_event(
            self.task, requires_care=True, state_version="v2",
            patient_id="child-01", caregiver_id="parent-01",
            slot_id="work-slot-01", expense_amount=200,
        )
        self.ch.seed_direct(self.task)
        event_id = injected["payload"]["event_id"]
        submitted = self.ch.submit_action(
            self.task,
            agent_id=1,
            payload={
                "action": "provide_care",
                "caregiver_id": "parent-01",
                "patient_id": "child-01",
                "event_id": event_id,
                "slot_id": "work-slot-01",
                "schedule_decision": "cancel",
                "expense_amount": 200,
                "adopted_state_version": "v2",
                "evidence_event_id": event_id,
            },
        )
        self.assertTrue(submitted["ok"])
        self.assertEqual("cancelled", self.ch.slot_of(self.task, "work-slot-01")["status"])
        self.assertEqual(1, len(self.ch.expenses_of(self.task)))
        self.assertEqual("parent-01", self.ch.responsibility_of(self.task))

    def test_missing_fields_denied(self):
        out = self.ch.submit_action(self.task, agent_id=1, payload={"action": "keep_schedule"})
        self.assertEqual("fields_not_extractable", out["reason"])

    def test_control_placeholder_keep(self):
        self.ch.inject_event(
            self.task, requires_care=False, state_version="v1",
            patient_id="child-01", caregiver_id="parent-01",
            slot_id="work-slot-01", expense_amount=200,
        )
        submitted = self.ch.submit_action(
            self.task,
            agent_id=1,
            payload={
                "action": "keep_schedule",
                "caregiver_id": NONE,
                "patient_id": NONE,
                "event_id": NONE,
                "slot_id": "work-slot-01",
                "schedule_decision": "keep",
                "expense_amount": 0,
                "adopted_state_version": "v1",
                "evidence_event_id": NONE,
            },
        )
        self.assertTrue(submitted["ok"])
        self.assertEqual([], self.ch.expenses_of(self.task))
        self.assertNotEqual("cancelled", self.ch.slot_of(self.task, "work-slot-01")["status"])


if __name__ == "__main__":
    unittest.main()
