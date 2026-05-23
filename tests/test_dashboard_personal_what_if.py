import subprocess
import unittest
from unittest.mock import patch

import dashboard_server as ds


class TestDashboardPersonalWhatIf(unittest.TestCase):
    def test_run_personal_what_if_builds_response(self):
        completed = subprocess.CompletedProcess(
            args=["python", "generative_city_sim.py"],
            returncode=0,
            stdout=(
                "✅ 个人 What-if simulation 完成\n"
                "输出目录: output/personal_what_if/20260523_demo\n"
                "通用报告: output/personal_what_if/20260523_demo/comparison_summary.md\n"
                "个人报告: output/personal_what_if/20260523_demo/personal_twin_recommendation.md\n"
            ),
            stderr="",
        )
        with patch.object(ds.subprocess, "run", return_value=completed) as run_mock:
            result = ds._run_personal_what_if(
                {
                    "agent_id": 2,
                    "question": "如果我明天不去上班而是准备面试，会怎样？",
                    "sim_days": 2,
                    "event_day": 1,
                    "event_time": "09:00",
                }
            )
        self.assertEqual(0, result["returncode"])
        self.assertIn("output/personal_what_if", result.get("output_root", ""))
        self.assertIn("personal_twin_recommendation.md", result.get("personal_report", ""))
        run_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
