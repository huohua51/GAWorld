"""Opt-in eval_mode must freeze rewrites without changing default run."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from gaworld.eval_mode import (
    apply_eval_mode_runtime,
    diary_fallback_allowed,
    interview_fallback_allowed,
    parse_structured_action,
    unique_intervention_audit,
    write_run_manifest,
)

import generative_city_sim as sim


class TestEvalModeHelpers(unittest.TestCase):
    def test_default_config_declares_eval_mode_off(self):
        from config import CONFIG

        self.assertIn("eval_mode", CONFIG)
        self.assertFalse(CONFIG["eval_mode"]["enabled"])
        self.assertTrue(interview_fallback_allowed(CONFIG))
        self.assertTrue(diary_fallback_allowed(CONFIG))

    def test_apply_runtime_disables_rewrites(self):
        cfg = {
            "eval_mode": {"enabled": True},
            "dynamic_behavior": {"enabled": True},
            "routine_change": {"enabled": True},
        }
        applied = apply_eval_mode_runtime(cfg)
        self.assertTrue(applied["applied"])
        self.assertFalse(cfg["dynamic_behavior"]["enabled"])
        self.assertFalse(cfg["routine_change"]["enabled"])

    def test_unique_path_audit_rejects_spillover(self):
        rows = [
            {"metric": "mobility_intent", "delta_final": 0.5},
            {"metric": "stress", "delta_final": 0.2},
        ]
        audit = unique_intervention_audit(rows, ["mobility_intent"])
        self.assertFalse(audit["unique_path_ok"])
        self.assertFalse(audit["measurement_valid"])
        self.assertEqual(["stress"], [item["metric"] for item in audit["leaked_metrics"]])

    def test_unique_path_audit_accepts_registered_only(self):
        rows = [
            {"metric": "mobility_intent", "delta_final": 0.5},
            {"metric": "stress", "delta_final": 0.0},
        ]
        audit = unique_intervention_audit(rows, ["mobility_intent"])
        self.assertTrue(audit["measurement_valid"])

    def test_parse_structured_action(self):
        text = '{"target_action": {"action": "evaluate_job_offer", "payload": {"decision": "accept"}}}'
        action = parse_structured_action(text)
        self.assertEqual("evaluate_job_offer", action["action"])
        self.assertEqual("accept", action["payload"]["decision"])

    def test_write_run_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "run_manifest.json")
            write_run_manifest(path, {"eval_mode": {"enabled": True}, "agent_ids": [4]})
            payload = json.loads(open(path, encoding="utf-8").read())
            self.assertTrue(payload["eval_mode"]["enabled"])
            self.assertEqual([4], payload["agent_ids"])


class TestEvalModeWiring(unittest.TestCase):
    def test_interview_refuses_prose_when_eval_mode_on(self):
        agent = {"id": 23, "name": "测试者", "state": {"emotion": 0.5, "stress": 0.5}}
        with patch.object(sim, "CONFIG", {"eval_mode": {"enabled": True, "strict_interview_json": True}}), patch.object(
            sim,
            "evoke_memory",
            return_value={"hint": "", "recollection": "", "hits": []},
        ), patch.object(sim, "call_llm", return_value="今天心情不错。"):
            answers = sim.interview_agent(agent, ["你为什么减少社交？"])
        self.assertEqual([], answers)

    def test_interview_still_falls_back_by_default(self):
        agent = {"id": 23, "name": "测试者", "state": {"emotion": 0.5, "stress": 0.5}}
        with patch.object(sim, "CONFIG", {"eval_mode": {"enabled": False}}), patch.object(
            sim,
            "evoke_memory",
            return_value={"hint": "", "recollection": "", "hits": []},
        ), patch.object(sim, "call_llm", return_value="今天心情不错。"):
            answers = sim.interview_agent(agent, ["问1", "问2"])
        self.assertEqual(2, len(answers))
        self.assertEqual("今天心情不错。", answers[0]["answer"])
        self.assertEqual("今天心情不错。", answers[1]["answer"])

    def test_maybe_adjust_activity_frozen_in_eval_mode(self):
        agent = {"id": 1, "name": "A", "state": {}}
        with patch.object(sim, "CONFIG", {"eval_mode": {"enabled": True, "disable_routine_change": True}}):
            activity, reason, changed = sim.maybe_adjust_activity(
                agent, "10:00", "工作", "", "", "", [], ""
            )
        self.assertEqual("工作", activity)
        self.assertFalse(changed)
        self.assertEqual("", reason)

    def test_diary_refuses_fallback_in_eval_mode(self):
        agent = {"id": 8, "name": "Agent8", "intentions": {}, "episodes": []}
        with patch.object(
            sim,
            "CONFIG",
            {"eval_mode": {"enabled": True, "disable_diary_fallback": True}},
        ), patch.object(sim, "call_llm", return_value="太短"):
            text = sim.generate_daily_diary(agent, 1, logs="x")
        self.assertEqual("", text)

    def test_comparison_report_writes_unique_path_audit(self):
        rows = [
            {
                "metric": "mobility_intent",
                "baseline_final": 0.3,
                "event_final": 0.8,
                "delta_final": 0.5,
                "baseline_mean": 0.3,
                "event_mean": 0.8,
                "delta_mean": 0.5,
            },
            {
                "metric": "stress",
                "baseline_final": 0.4,
                "event_final": 0.7,
                "delta_final": 0.3,
                "baseline_mean": 0.4,
                "event_mean": 0.7,
                "delta_mean": 0.3,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            report_md, _metrics = sim._write_comparison_report(
                tmp,
                {"name": "限行", "day": 1, "time": "10:00", "description": "只改出行意愿"},
                rows,
                registered_paths=["mobility_intent"],
            )
            audit_path = os.path.join(tmp, "unique_path_audit.json")
            self.assertTrue(os.path.exists(audit_path))
            audit = json.loads(open(audit_path, encoding="utf-8").read())
            self.assertFalse(audit["measurement_valid"])
            body = open(report_md, encoding="utf-8").read()
            self.assertIn("唯一干预审计", body)


if __name__ == "__main__":
    unittest.main()
