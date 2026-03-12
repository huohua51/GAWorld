import os
import random
import tempfile
import unittest
import csv
from unittest.mock import patch

import economy_module as eco


def _build_agent(agent_id=1):
    return {
        "id": agent_id,
        "name": f"A{agent_id}",
        "age": 30,
        "job": "软件工程师",
        "personality": "上进务实",
        "values": "重视稳定和成长",
        "daily_life": "规律生活",
        "state": {
            "emotion": 0.5,
            "stress": 0.5,
            "econ_security": 0.5,
            "risk_preference": 0.6,
        },
    }


class TestEconomyModule(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.memory_dir = os.path.join(self.tmpdir.name, "memory")
        self.log_dir = os.path.join(self.tmpdir.name, "logs")
        self.output_dir = os.path.join(self.tmpdir.name, "economy")
        self.config = {
            "stateful": True,
            "memory_dir": self.memory_dir,
            "log_dir": self.log_dir,
            "economy": {
                "enabled": True,
                "output_dir": self.output_dir,
                "hours_per_step": 1.0,
            },
        }

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_init_sets_finance_profile(self):
        random.seed(7)
        agent = _build_agent()
        ctx = {"config": self.config, "agents": [agent], "extension_state": {}}
        eco.on_simulation_start(ctx)
        self.assertIn("economy", agent)
        self.assertGreater(agent["economy"]["balance"], 0.0)
        self.assertIn("wealth_drive", agent["economy"])
        self.assertIn("initial_assets", agent["economy"])
        self.assertIn("inheritance", agent["economy"]["initial_assets"])
        self.assertTrue(os.path.exists(os.path.join(self.log_dir, "agent_1.log")))

    def test_init_can_include_inheritance_assets(self):
        random.seed(9)
        agent = _build_agent()
        cfg = dict(self.config)
        cfg["economy"] = dict(self.config["economy"])
        cfg["economy"]["inheritance_enabled"] = True
        cfg["economy"]["inheritance_base_probability"] = 1.0
        start_ctx = {"config": cfg, "agents": [agent], "extension_state": {}}
        eco.on_simulation_start(start_ctx)
        init_assets = agent["economy"]["initial_assets"]
        self.assertGreater(init_assets["inheritance"], 0.0)
        self.assertAlmostEqual(
            init_assets["total"],
            init_assets["labor_savings"] + init_assets["inheritance"],
            places=6,
        )

    def test_high_wealth_drive_can_seek_income_activity(self):
        random.seed(11)
        agent = _build_agent()
        ctx = {"config": self.config, "agents": [agent], "extension_state": {}}
        eco.on_simulation_start(ctx)
        agent["economy"]["wealth_drive"] = 0.95
        agent["economy"]["balance"] = 0.0
        agent["economy"]["daily_income"] = 0.0
        agent["economy"]["income_target_daily"] = 500.0

        step = {"scheduled_activity": "散步", "activity": "散步"}
        pre_ctx = {
            "config": self.config,
            "agent": agent,
            "step": step,
            "actions": {1: {"工作": ["处理任务"]}},
            "extension_state": ctx["extension_state"],
        }
        with patch("economy_module.random.random", return_value=0.0):
            eco.on_agent_pre_step(pre_ctx)
        self.assertEqual("工作", step["activity"])
        self.assertTrue(step.get("economy_forced_income", False))

    def test_post_step_records_income_and_expense(self):
        random.seed(19)
        agent = _build_agent()
        ext = {}
        start_ctx = {"config": self.config, "agents": [agent], "extension_state": ext}
        eco.on_simulation_start(start_ctx)
        day_ctx = {
            "config": self.config,
            "day": 1,
            "agents": [agent],
            "daily_logs": {1: ""},
            "extension_state": ext,
        }
        eco.on_day_start(day_ctx)
        before_balance = agent["economy"]["balance"]
        post_ctx = {
            "config": self.config,
            "day": 1,
            "time_str": "10:00",
            "agent": agent,
            "step": {
                "activity": "工作",
                "action": "推进研发任务",
                "location": "Office",
            },
            "daily_logs": day_ctx["daily_logs"],
            "extension_state": ext,
        }
        eco.on_agent_post_step(post_ctx)
        econ = agent["economy"]
        self.assertGreater(econ["daily_income"], 0.0)
        self.assertGreater(econ["daily_expense"], 0.0)
        self.assertNotEqual(before_balance, econ["balance"])

    def test_day_end_can_raise_income_after_deficit(self):
        random.seed(23)
        agent = _build_agent()
        ext = {}
        start_ctx = {"config": self.config, "agents": [agent], "extension_state": ext}
        eco.on_simulation_start(start_ctx)
        econ = agent["economy"]
        base_before = econ["base_hourly_income"]
        econ["wealth_drive"] = 0.9
        econ["daily_income"] = 20.0
        econ["daily_expense"] = 180.0
        econ["income_target_daily"] = 120.0
        end_ctx = {
            "config": self.config,
            "day": 1,
            "agents": [agent],
            "daily_logs": {1: ""},
            "extension_state": ext,
        }
        eco.on_day_end(end_ctx)
        self.assertGreater(agent["economy"]["base_hourly_income"], base_before)
        self.assertEqual(1, len(ext["economy_module"]["day_rows"]))

    def test_simulation_end_exports_per_agent_files(self):
        random.seed(31)
        agent1 = _build_agent(1)
        agent2 = _build_agent(2)
        ext = {}
        start_ctx = {"config": self.config, "agents": [agent1, agent2], "extension_state": ext}
        eco.on_simulation_start(start_ctx)
        for agent in (agent1, agent2):
            agent["economy"]["daily_income"] = 100.0 + agent["id"]
            agent["economy"]["daily_expense"] = 40.0 + agent["id"]
        day_ctx = {
            "config": self.config,
            "day": 1,
            "agents": [agent1, agent2],
            "daily_logs": {1: "", 2: ""},
            "extension_state": ext,
        }
        eco.on_day_end(day_ctx)
        end_ctx = {"config": self.config, "agents": [agent1, agent2], "extension_state": ext}
        eco.on_simulation_end(end_ctx)

        self.assertTrue(os.path.exists(os.path.join(self.output_dir, "daily_ledger.csv")))
        self.assertTrue(os.path.exists(os.path.join(self.output_dir, "wealth_snapshot.csv")))
        ledger_1 = os.path.join(self.output_dir, "agents", "agent_1_ledger.csv")
        ledger_2 = os.path.join(self.output_dir, "agents", "agent_2_ledger.csv")
        snap_1 = os.path.join(self.output_dir, "agents", "agent_1_snapshot.json")
        snap_2 = os.path.join(self.output_dir, "agents", "agent_2_snapshot.json")
        self.assertTrue(os.path.exists(ledger_1))
        self.assertTrue(os.path.exists(ledger_2))
        self.assertTrue(os.path.exists(snap_1))
        self.assertTrue(os.path.exists(snap_2))

        with open(ledger_1, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(1, len(rows))
        self.assertEqual("1", rows[0]["agent_id"])
        with open(os.path.join(self.output_dir, "wealth_snapshot.csv"), "r", encoding="utf-8") as f:
            snap_rows = list(csv.DictReader(f))
        self.assertIn("initial_inheritance", snap_rows[0])
        self.assertIn("initial_labor_savings", snap_rows[0])


if __name__ == "__main__":
    unittest.main()
