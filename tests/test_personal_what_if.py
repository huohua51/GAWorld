import os
import tempfile
import unittest
from pathlib import Path

from gaworld.personal_twin.what_if import write_personal_what_if_report


class TestPersonalWhatIf(unittest.TestCase):
    def test_source_contains_personal_what_if_command(self):
        source = Path("generative_city_sim.py").read_text(encoding="utf-8")
        self.assertIn('"personal-what-if"', source)
        self.assertIn("_cli_personal_what_if", source)

    def test_write_personal_what_if_report_outputs_recommendation(self):
        rows = [
            {
                "metric": "stress",
                "baseline_final": 0.42,
                "event_final": 0.51,
                "delta_final": 0.09,
            },
            {
                "metric": "emotion",
                "baseline_final": 0.55,
                "event_final": 0.49,
                "delta_final": -0.06,
            },
        ]
        event_payload = {
            "name": "Interview Focus",
            "day": 1,
            "time": "09:00",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            baseline_dir = os.path.join(tmpdir, "baseline")
            scenario_dir = os.path.join(tmpdir, "scenario")
            os.makedirs(os.path.join(baseline_dir, "memory"), exist_ok=True)
            os.makedirs(os.path.join(scenario_dir, "memory"), exist_ok=True)
            os.makedirs(os.path.join(baseline_dir, "logs"), exist_ok=True)
            os.makedirs(os.path.join(scenario_dir, "logs"), exist_ok=True)
            with open(os.path.join(baseline_dir, "memory", "agent_2_schedule.json"), "w", encoding="utf-8") as f:
                f.write('[{"time":"09:00","activity":"工作"}]')
            with open(os.path.join(scenario_dir, "memory", "agent_2_schedule.json"), "w", encoding="utf-8") as f:
                f.write('[{"time":"09:00","activity":"面试准备"}]')
            with open(os.path.join(baseline_dir, "memory", "agent_2.json"), "w", encoding="utf-8") as f:
                f.write('["原有记忆"]')
            with open(os.path.join(scenario_dir, "memory", "agent_2.json"), "w", encoding="utf-8") as f:
                f.write('["原有记忆", "新增记忆：开始把更多时间转向求职准备"]')
            with open(os.path.join(baseline_dir, "logs", "agent_2.log"), "w", encoding="utf-8") as f:
                f.write("[Base]\n")
            with open(os.path.join(scenario_dir, "logs", "agent_2.log"), "w", encoding="utf-8") as f:
                f.write("[Scenario]\nDistributedOutbox\n消息\n")
            path = write_personal_what_if_report(
                tmpdir,
                question="What if I spend tomorrow on interview preparation instead of my current job?",
                agent_id=2,
                event_payload=event_payload,
                rows=rows,
                baseline_dir=baseline_dir,
                scenario_dir=scenario_dir,
            )
            self.assertTrue(os.path.exists(path))
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        self.assertIn("个人孪生 What-if 报告", text)
        self.assertIn("Interview Focus", text)
        self.assertIn("压力明显上升", text)
        self.assertIn("日程偏移", text)
        self.assertIn("baseline/", text)


if __name__ == "__main__":
    unittest.main()
