"""Permission and delivery tests for ReviewChannel."""

from __future__ import annotations

import os
import tempfile
import unittest

from gaworld.work.review import ReviewAction, ReviewChannel


def _action(**overrides):
    payload = {
        "decision": "revise",
        "reviewed_spec_version": "v1",
        "required_spec_version": "v2",
        "criterion_id": "reservation_wage_threshold",
        "evidence": "uses 60000",
        "required_change": {"reservation_wage": 70000},
    }
    payload.update(overrides)
    return payload


class TestReviewChannel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "review.jsonl")
        self.ch = ReviewChannel(self.path)
        self.task = "t1"
        self.draft = os.path.join(self.tmp, "draft_main.py")
        with open(self.draft, "w", encoding="utf-8") as handle:
            handle.write('SPEC_VERSION = "v1"\nTHRESHOLD = 60000\n')

    def _ready(self, spec="v2"):
        self.ch.put_private(self.task, "reviewer", {"spec_version": spec, "reservation_wage": 70000})
        self.ch.submit_draft(self.task, executor_id=5, path=self.draft, spec_version="v1")
        self.ch.request_review(self.task)

    def test_executor_cannot_read_reviewer_private(self):
        self.ch.put_private(self.task, "reviewer", {"spec_version": "v2"})
        out = self.ch.read_private(self.task, "executor")
        self.assertFalse(out["ok"])
        self.assertEqual("unauthorized_private_read", out["reason"])

    def test_reviewer_cannot_write_artifact(self):
        target = os.path.join(self.tmp, "final_main.py")
        out = self.ch.write_artifact(
            task_id=self.task, role="reviewer", kind="final", path=target, content="stolen"
        )
        self.assertFalse(out["ok"])
        self.assertEqual("unauthorized_artifact_write", out["reason"])
        self.assertFalse(os.path.isfile(target))

    def test_executor_can_write_draft_and_final(self):
        out = self.ch.write_artifact(
            task_id=self.task, role="executor", kind="final",
            path=os.path.join(self.tmp, "final_main.py"), content="ok",
        )
        self.assertTrue(out["ok"])
        self.assertTrue(os.path.isfile(out["path"]))

    def test_drop_review_does_not_enter_inbox(self):
        self._ready()
        self.ch.emit_review(self.task, reviewer_id=6, payload=_action())
        delivered = self.ch.deliver_review(self.task, drop=True)
        self.assertTrue(delivered["ok"])
        self.assertTrue(delivered["dropped"])
        inbox = self.ch.read_inbox(self.task, "executor")
        self.assertEqual([], inbox["reviews"])

    def test_deliver_then_adopt(self):
        self._ready()
        emitted = self.ch.emit_review(self.task, reviewer_id=6, payload=_action())
        self.ch.deliver_review(self.task, drop=False)
        review_id = emitted["action"]["review_id"]
        adopted = self.ch.adopt_review(self.task, review_id, current_spec_version="v1")
        self.assertTrue(adopted["ok"])

    def test_stale_review_is_rejected(self):
        self._ready()
        emitted = self.ch.emit_review(
            self.task, reviewer_id=6,
            payload=_action(required_spec_version="v1", reviewed_spec_version="v2"),
        )
        self.ch.deliver_review(self.task)
        out = self.ch.adopt_review(
            self.task, emitted["action"]["review_id"], current_spec_version="v2"
        )
        self.assertFalse(out["ok"])
        self.assertEqual("stale_review", out["reason"])

    def test_duplicate_adopt_is_rejected(self):
        self._ready()
        emitted = self.ch.emit_review(self.task, reviewer_id=6, payload=_action())
        self.ch.deliver_review(self.task)
        review_id = emitted["action"]["review_id"]
        first = self.ch.adopt_review(self.task, review_id, current_spec_version="v1")
        again = self.ch.adopt_review(self.task, review_id, current_spec_version="v1")
        self.assertTrue(first["ok"])
        self.assertFalse(again["ok"])
        self.assertEqual("review_already_adopted", again["reason"])

    def test_invalid_contract_is_rejected(self):
        self._ready()
        out = self.ch.emit_review(self.task, reviewer_id=6, payload={"decision": "maybe"})
        self.assertFalse(out["ok"])
        self.assertEqual("review_contract_invalid", out["reason"])

    def test_request_without_private_context_fails(self):
        self.ch.submit_draft(self.task, executor_id=5, path=self.draft, spec_version="v1")
        out = self.ch.request_review(self.task)
        self.assertFalse(out["ok"])
        self.assertEqual("review_private_context_missing", out["reason"])

    def test_action_round_trip(self):
        action = ReviewAction.from_dict(_action())
        self.assertEqual(action, ReviewAction.from_dict(action.to_dict()))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
