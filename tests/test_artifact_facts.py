"""Permission and truthfulness tests for artifact facts."""

from __future__ import annotations

import unittest

from gaworld.work.artifact_facts import extract_facts, nack_payload, verify_review


_SPECS = [
    {"symbol": "SPEC_VERSION", "criterion_path": "spec_version", "parse": "str"},
    {"symbol": "THRESHOLD", "criterion_path": "reservation_wage", "parse": "int"},
]


class TestArtifactFacts(unittest.TestCase):
    def setUp(self):
        self.source = 'SPEC_VERSION = "v1"\nTHRESHOLD = 60000\n'
        self.facts = extract_facts(self.source, specs=_SPECS)
        self.hash = self.facts[0].artifact_hash
        self.private_v1 = {
            "criterion_id": "reservation_wage_threshold",
            "spec_version": "v1",
            "required_change": {"reservation_wage": 60000, "spec_version": "v1"},
        }
        self.private_v2 = {
            "criterion_id": "reservation_wage_threshold",
            "spec_version": "v2",
            "required_change": {"reservation_wage": 70000, "spec_version": "v2"},
        }

    def test_extracts_observed_only(self):
        public = self.facts[1].to_public_dict()
        self.assertEqual(60000, public["observed_value"])
        self.assertNotIn("required_value", public)
        self.assertTrue(public["artifact_hash"].startswith("sha256:"))

    def test_control_mismatch_is_rejected(self):
        review = {
            "decision": "revise",
            "mismatches": [
                {
                    "criterion_id": "reservation_wage_threshold",
                    "fact_id": "fact-02",
                    "observed_value": 60000,
                    "required_value": 70000,
                    "operator": "equals",
                }
            ],
        }
        out = verify_review(review, facts=self.facts, private=self.private_v1, current_hash=self.hash)
        self.assertFalse(out["ok"])
        self.assertEqual("required_value_not_registered", out["reason"])

    def test_fabricated_observed_is_rejected(self):
        review = {
            "decision": "revise",
            "mismatches": [
                {
                    "criterion_id": "reservation_wage_threshold",
                    "fact_id": "fact-02",
                    "observed_value": 1,
                    "required_value": 70000,
                    "operator": "equals",
                }
            ],
        }
        out = verify_review(review, facts=self.facts, private=self.private_v2, current_hash=self.hash)
        self.assertFalse(out["ok"])
        self.assertEqual("observed_value_false", out["reason"])

    def test_unknown_fact_id_is_rejected(self):
        review = {
            "decision": "revise",
            "mismatches": [
                {
                    "criterion_id": "reservation_wage_threshold",
                    "fact_id": "fact-99",
                    "observed_value": 60000,
                    "required_value": 70000,
                    "operator": "equals",
                }
            ],
        }
        out = verify_review(review, facts=self.facts, private=self.private_v2, current_hash=self.hash)
        self.assertFalse(out["ok"])
        self.assertEqual("review_evidence_not_bound", out["reason"])

    def test_real_intervention_mismatch_is_accepted(self):
        review = {
            "decision": "revise",
            "mismatches": [
                {
                    "criterion_id": "reservation_wage_threshold",
                    "fact_id": "fact-02",
                    "observed_value": 60000,
                    "required_value": 70000,
                    "operator": "equals",
                }
            ],
        }
        out = verify_review(review, facts=self.facts, private=self.private_v2, current_hash=self.hash)
        self.assertTrue(out["ok"])

    def test_matching_draft_cannot_carry_value_mismatch(self):
        review = {
            "decision": "revise",
            "mismatches": [
                {
                    "criterion_id": "reservation_wage_threshold",
                    "fact_id": "fact-02",
                    "observed_value": 60000,
                    "required_value": 60000,
                    "operator": "equals",
                }
            ],
        }
        out = verify_review(review, facts=self.facts, private=self.private_v1, current_hash=self.hash)
        self.assertFalse(out["ok"])
        self.assertEqual("mismatch_not_real", out["reason"])

    def test_nack_does_not_leak_required_value(self):
        payload = nack_payload()
        self.assertFalse(payload["accepted"])
        self.assertNotIn("70000", payload["reason"])
        self.assertNotIn("required", payload["reason"])

    def test_empty_facts_are_missing(self):
        out = verify_review(
            {"decision": "approve", "mismatches": []},
            facts=[],
            private=self.private_v1,
            current_hash=self.hash,
        )
        self.assertEqual("artifact_fact_missing", out["reason"])

    def test_stale_hash_is_rejected(self):
        review = {"decision": "approve", "mismatches": []}
        out = verify_review(review, facts=self.facts, private=self.private_v1, current_hash="sha256:stale")
        self.assertEqual("artifact_fact_stale", out["reason"])

    def test_approve_with_mismatches_is_inconsistent(self):
        review = {
            "decision": "approve",
            "mismatches": [
                {
                    "criterion_id": "reservation_wage_threshold",
                    "fact_id": "fact-02",
                    "observed_value": 60000,
                    "required_value": 70000,
                    "operator": "equals",
                }
            ],
        }
        out = verify_review(review, facts=self.facts, private=self.private_v2, current_hash=self.hash)
        self.assertEqual("review_decision_inconsistent", out["reason"])

    def test_revise_without_mismatches_is_inconsistent(self):
        review = {"decision": "revise", "mismatches": []}
        out = verify_review(review, facts=self.facts, private=self.private_v2, current_hash=self.hash)
        self.assertEqual("review_decision_inconsistent", out["reason"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
