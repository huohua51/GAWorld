import unittest
from unittest.mock import patch

from human_realism import consolidate_day


class TestDayEndConsolidation(unittest.TestCase):
    def test_consolidation_fallback_output(self):
        agent = {"id": 5, "name": "Agent5", "state": {"stress": 0.5}}
        episodes = [
            {
                "episode_id": "e1",
                "time": "10:00",
                "final_activity": "上午工作",
                "action": "整理任务",
                "salience": 0.7,
                "reflection": "今天推进顺利",
                "tags": ["work", "success"],
            }
        ]
        result = consolidate_day(agent, 3, episodes, {}, {"remaining": 0})
        self.assertIn("memory_text", result)
        self.assertIn("intentions", result)
        self.assertTrue(result["memory_text"].startswith("[Day 3 Consolidation]"))

    def test_consolidation_uses_budget_once(self):
        agent = {"id": 5, "name": "Agent5", "state": {"stress": 0.5}}
        episodes = [
            {
                "episode_id": "e1",
                "time": "10:00",
                "final_activity": "上午工作",
                "action": "整理任务",
                "salience": 0.7,
                "reflection": "今天推进顺利",
                "tags": ["work", "success"],
            }
        ]
        budget = {"remaining": 1}
        llm_json = (
            '{"summary":"今天关键进展稳定。",'
            '"priorities":["推进重点任务"],'
            '"avoidances":["情绪化决策"],'
            '"target_social":"与同事保持协作",'
            '"target_recovery":"按时休息"}'
        )
        with patch("human_realism.call_llm", return_value=llm_json):
            result = consolidate_day(agent, 3, episodes, {}, budget)
        self.assertEqual(0, budget["remaining"])
        self.assertIn("今天关键进展稳定", result["summary"])


if __name__ == "__main__":
    unittest.main()
