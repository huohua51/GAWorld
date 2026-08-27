"""Joint assignment: violations without answers, no environment repair."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from gaworld.work.coordination import (
    JointAssignmentChannel,
    actual_final_conflict_free,
    occupancy_table,
)


def _channel(path: str) -> JointAssignmentChannel:
    return JointAssignmentChannel(
        resource_id="ferry_berth",
        slots=["k1", "k2", "k3"],
        priority=["agent_a", "agent_b"],
        feasible={"agent_a": ["k1", "k2", "k3"], "agent_b": ["k1", "k2", "k3"]},
        max_retries=1,
        path=path,
    )


class TestJointAssignmentChannel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "coord.jsonl")
        self.ch = _channel(self.path)

    def test_occupancy_and_conflict_free_are_scorer_facts(self):
        free = {"agent_a": "k1", "agent_b": "k2"}
        clash = {"agent_a": "k1", "agent_b": "k1"}
        self.assertEqual({"k1": ["agent_a"], "k2": ["agent_b"]}, occupancy_table(free))
        self.assertTrue(actual_final_conflict_free(free))
        self.assertFalse(actual_final_conflict_free(clash))

    def test_inspect_duplicate_does_not_name_repair_slot(self):
        self.ch.save_initial({"agent_a": "k1", "agent_b": "k1"})
        out = self.ch.inspect_violations()
        self.assertTrue(out["ok"])
        self.assertEqual("duplicate_resource_claim", out["violations"][0]["type"])
        self.assertEqual("k1", out["violations"][0]["slot"])
        blob = json.dumps(out)
        self.assertNotIn("k2", blob)
        self.assertNotIn("k3", blob)
        self.assertNotIn("suggested", blob)
        self.assertNotIn("actual_final_conflict_free", blob)

    def test_inspect_control_has_no_violations(self):
        self.ch.save_initial({"agent_a": "k1", "agent_b": "k2"})
        out = self.ch.inspect_violations()
        self.assertEqual([], out["violations"])

    def test_environment_cannot_write_assignment(self):
        self.ch.save_initial({"agent_a": "k1", "agent_b": "k1"})
        out = self.ch.write_assignment(role="environment", assignments={"agent_a": "k1", "agent_b": "k2"})
        self.assertFalse(out["ok"])
        self.assertEqual("unauthorized_assignment_write", out["reason"])
        self.assertEqual(1, self.ch.world_state()["unregistered_modification"])
        self.assertEqual({"agent_a": "k1", "agent_b": "k1"}, self.ch.world_state()["assignments"])

    def test_failed_proposal_is_not_auto_corrected(self):
        self.ch.save_initial({"agent_a": "k1", "agent_b": "k1"})
        out = self.ch.propose_joint_assignment("coordinator", {"agent_a": "k1", "agent_b": "k1"})
        self.assertTrue(out["ok"])
        self.assertFalse(out["accepted"])
        self.assertEqual(1, out["retries_remaining"])
        self.assertNotIn("plan_id", out)
        self.assertNotIn("suggested_slot", out)
        self.assertNotIn("actual_final_conflict_free", out)
        world = self.ch.world_state()
        self.assertEqual({"agent_a": "k1", "agent_b": "k1"}, world["assignments"])
        self.assertFalse(world["actual_final_conflict_free"])

    def test_retry_then_accept_without_leaking_k2_in_nack(self):
        self.ch.save_initial({"agent_a": "k1", "agent_b": "k1"})
        nack = self.ch.propose_joint_assignment("coordinator", {"agent_a": "k1", "agent_b": "k1"})
        blob = json.dumps(nack)
        self.assertNotIn("k2", blob)
        ack = self.ch.propose_joint_assignment("coordinator", {"agent_a": "k1", "agent_b": "k2"})
        self.assertTrue(ack["accepted"])
        self.assertTrue(self.ch.world_state()["actual_final_conflict_free"])

    def test_wrong_unique_assignment_does_not_name_correct_slot(self):
        self.ch.save_initial({"agent_a": "k1", "agent_b": "k1"})
        out = self.ch.propose_joint_assignment("coordinator", {"agent_a": "k1", "agent_b": "k3"})
        self.assertFalse(out["accepted"])
        types = {item["type"] for item in out["violations"]}
        self.assertIn("not_earliest_feasible_idle", types)
        self.assertNotIn("k2", json.dumps(out["violations"]))

    def test_priority_move_returns_only_agent_a(self):
        self.ch.save_initial({"agent_a": "k1", "agent_b": "k1"})
        out = self.ch.propose_joint_assignment("coordinator", {"agent_a": "k2", "agent_b": "k3"})
        self.assertFalse(out["accepted"])
        self.assertEqual(1, len(out["violations"]))
        item = out["violations"][0]
        self.assertEqual("priority_preservation_violation", item["violation"])
        self.assertEqual("A", item["agent"])
        self.assertTrue(item.get("keep_protected_assignment"))
        self.assertTrue(item.get("forbid_duplicate_claim"))
        blob = json.dumps(out["violations"])
        self.assertNotIn("k1", blob)
        self.assertNotIn("k2", blob)
        self.assertNotIn("k3", blob)
        self.assertNotIn("suggested", blob)

    def test_retry_after_priority_nack_accepts_keep_a_move_b(self):
        self.ch.save_initial({"agent_a": "k1", "agent_b": "k1"})
        nack = self.ch.propose_joint_assignment("coordinator", {"agent_a": "k2", "agent_b": "k3"})
        self.assertEqual("priority_preservation_violation", nack["violations"][0]["violation"])
        ack = self.ch.propose_joint_assignment("coordinator", {"agent_a": "k1", "agent_b": "k2"})
        self.assertTrue(ack["accepted"])
        self.assertTrue(self.ch.world_state()["actual_final_conflict_free"])
        self.assertEqual({"agent_a": "k1", "agent_b": "k2"}, self.ch.world_state()["assignments"])

    def test_infeasible_does_not_list_allowed_slots(self):
        self.ch.save_initial({"agent_a": "k1", "agent_b": "k1"})
        out = self.ch.propose_joint_assignment("coordinator", {"agent_a": "k1", "agent_b": "k9"})
        self.assertFalse(out["accepted"])
        types = {item["type"] for item in out["violations"]}
        self.assertIn("private_infeasible", types)
        self.assertNotIn("k2", json.dumps(out["violations"]))

    def test_protection_revision_nacks_first_plan_without_naming_repair_slot(self):
        ch = JointAssignmentChannel(
            resource_id="ferry_berth",
            slots=["k1", "k2", "k3"],
            priority=["agent_b", "agent_a"],
            feasible={"agent_a": ["k1", "k2", "k3"], "agent_b": ["k1", "k2", "k3"]},
            max_retries=0,
            path=self.path,
        )
        ch.save_initial({"agent_a": "k2", "agent_b": "k1"})
        registered = ch.register_protection(agent="agent_a", slot="k1")
        self.assertTrue(registered["ok"])
        self.assertEqual("A", registered["protected_agent"])
        self.assertEqual("spec-002", registered["spec_version"])
        self.assertNotIn("slot", registered)
        self.assertNotIn("k2", json.dumps(registered))
        nack = ch.inspect_registered_constraints()
        self.assertEqual("priority_preservation_violation", nack["violations"][0]["violation"])
        blob = json.dumps(nack["violations"])
        self.assertNotIn("k1", blob)
        self.assertNotIn("k2", blob)
        self.assertNotIn("k3", blob)
        self.assertNotIn("suggested", blob)
        ack = ch.propose_joint_assignment("coordinator", {"agent_a": "k1", "agent_b": "k2"})
        self.assertTrue(ack["accepted"])
        self.assertEqual("spec-002", ack["spec_version"])
        self.assertEqual({"agent_a": "k1", "agent_b": "k2"}, ch.world_state()["assignments"])

    def test_spec_revision_invalidates_pre_revision_plan(self):
        self.ch.save_initial({"agent_a": "k1", "agent_b": "k2"})
        accepted = self.ch.propose_joint_assignment(
            "coordinator", {"agent_a": "k1", "agent_b": "k2"}
        )
        old_plan_id = accepted["plan_id"]
        self.assertTrue(
            self.ch.confirm_assignment(
                agent_id="agent_a", slot="k1", plan_id=old_plan_id
            )["ok"]
        )

        revised = self.ch.register_protection(agent="agent_a", slot="k1")
        self.assertEqual("spec-002", revised["spec_version"])
        stale = self.ch.confirm_assignment(
            agent_id="agent_a", slot="k1", plan_id=old_plan_id
        )
        self.assertFalse(stale["ok"])
        self.assertEqual("stale_plan_spec", stale["reason"])
        self.assertIsNone(self.ch.world_state()["plan_id"])

    def test_protection_noop_when_first_plan_already_keeps_high_priority(self):
        self.ch.save_initial({"agent_a": "k1", "agent_b": "k2"})
        registered = self.ch.register_protection(agent="agent_a", slot="k1")
        self.assertTrue(registered["ok"])
        nack = self.ch.inspect_registered_constraints()
        self.assertEqual([], nack["violations"])
        ack = self.ch.propose_joint_assignment("coordinator", {"agent_a": "k1", "agent_b": "k2"})
        self.assertTrue(ack["accepted"])

    def test_register_protection_does_not_rewrite_proposal(self):
        self.ch.save_initial({"agent_a": "k2", "agent_b": "k1"})
        self.ch.register_protection(agent="agent_a", slot="k1")
        self.assertEqual({"agent_a": "k2", "agent_b": "k1"}, self.ch.world_state()["assignments"])

    def test_third_proposal_exhausted(self):
        self.ch.save_initial({"agent_a": "k1", "agent_b": "k1"})
        self.ch.propose_joint_assignment("coordinator", {"agent_a": "k1", "agent_b": "k1"})
        self.ch.propose_joint_assignment("coordinator", {"agent_a": "k1", "agent_b": "k1"})
        out = self.ch.propose_joint_assignment("coordinator", {"agent_a": "k1", "agent_b": "k2"})
        self.assertFalse(out["ok"])
        self.assertEqual("retry_exhausted", out["reason"])
        self.assertEqual({"agent_a": "k1", "agent_b": "k1"}, self.ch.world_state()["assignments"])

    def test_platform_stamps_plan_id_agent_does_not_submit_version(self):
        self.ch.save_initial({"agent_a": "k1", "agent_b": "k2"})
        out = self.ch.propose_joint_assignment("coordinator", {"agent_a": "k1", "agent_b": "k2"})
        self.assertTrue(out["accepted"])
        self.assertTrue(out["plan_id"].startswith("plan-"))
        self.assertEqual("spec-001", out["spec_version"])
        denied = self.ch.propose_joint_assignment(
            "coordinator",
            {"agent_a": "k1", "agent_b": "k2", "plan_version": "plan-001"},
        )
        self.assertFalse(denied["ok"])
        self.assertEqual("agent_must_not_issue_plan_id", denied["reason"])
        ok = self.ch.confirm_assignment(agent_id="agent_b", slot="k2", plan_id=out["plan_id"])
        self.assertTrue(ok["ok"])
        self.assertEqual(out["plan_id"], ok["plan_id"])
        bad = self.ch.confirm_assignment(agent_id="agent_b", slot="k3", plan_id=out["plan_id"])
        self.assertFalse(bad["ok"])
        self.assertEqual("slot_mismatch", bad["reason"])


if __name__ == "__main__":
    unittest.main()
