"""Goals context must reach the intention/consolidation prompts."""

import json
import unittest
from unittest.mock import patch

from gaworld.cognition import realism


def _agent():
    return {
        "id": 5, "name": "测试者", "job": "教师", "personality": "耐心",
        "state": {"stress": 0.3}, "growth_profile": {}, "episodes": [],
    }


def _episode():
    return {"day": 1, "final_activity": "备课", "action": "整理教案",
            "salience": 0.7, "tags": [], "reflection": "还算顺利"}


class TestIntentionPromptInjection(unittest.TestCase):
    def test_goals_context_in_prompt(self):
        prompts = []

        def fake_llm(prompt, task=None, agent_id=None):
            prompts.append(prompt)
            return json.dumps({"priorities": ["推进课题"], "avoidances": ["拖延"],
                               "target_social": "", "target_recovery": "",
                               "growth_focus": []}, ensure_ascii=False)

        with patch.object(realism, "call_llm", fake_llm):
            realism.build_daily_intentions(
                _agent(), [_episode()], {}, {"remaining": 2},
                goals_context="- 短期[stg1]：完成课题申报（进度 20%）",
            )
        self.assertIn("当前人生与阶段目标", prompts[0])
        self.assertIn("完成课题申报", prompts[0])

    def test_default_goals_context_keeps_signature_optional(self):
        result = realism.build_daily_intentions(_agent(), [], {}, {"remaining": 0})
        self.assertIn("priorities", result)


class TestConsolidationGoalProgress(unittest.TestCase):
    def test_prompt_contains_goals_and_result_carries_goal_progress(self):
        prompts = []

        def fake_llm(prompt, task=None, agent_id=None):
            prompts.append(prompt)
            return json.dumps({
                "summary": "有推进", "priorities": ["继续"], "avoidances": [],
                "target_social": "", "target_recovery": "", "growth_focus": [],
                "goal_progress": [{"id": "stg1", "progress": 0.5, "note": "写了一半"}],
            }, ensure_ascii=False)

        with patch.object(realism, "call_llm", fake_llm):
            result = realism.consolidate_day(
                _agent(), 3, [_episode()], {}, {"remaining": 2},
                goals_context="- 短期[stg1]：完成课题申报（进度 20%）",
            )
        self.assertIn("当前人生与阶段目标", prompts[0])
        self.assertEqual(result["goal_progress"][0]["id"], "stg1")

    def test_no_llm_budget_returns_empty_goal_progress(self):
        result = realism.consolidate_day(_agent(), 3, [_episode()], {}, {"remaining": 0})
        self.assertEqual(result["goal_progress"], [])

    def test_no_episodes_returns_empty_goal_progress(self):
        result = realism.consolidate_day(_agent(), 3, [], {}, {"remaining": 2})
        self.assertEqual(result["goal_progress"], [])

    def test_malformed_goal_progress_becomes_empty_list(self):
        def fake_llm(prompt, task=None, agent_id=None):
            return json.dumps({"summary": "ok", "priorities": [], "avoidances": [],
                               "target_social": "", "target_recovery": "",
                               "growth_focus": [], "goal_progress": "不是列表"},
                              ensure_ascii=False)

        with patch.object(realism, "call_llm", fake_llm):
            result = realism.consolidate_day(
                _agent(), 3, [_episode()], {}, {"remaining": 2}, goals_context="x")
        self.assertEqual(result["goal_progress"], [])


if __name__ == "__main__":
    unittest.main()
