import random
import unittest
from unittest.mock import patch

import generative_city_sim as sim


class TestMemoryRecallAndReview(unittest.TestCase):
    def test_negative_recall_discourages_repeated_bad_action(self):
        agent = {
            "id": 21,
            "state": {
                "emotion": 0.5,
                "stress": 0.5,
                "econ_security": 0.5,
                "energy": 0.6,
                "hunger": 0.4,
                "social_need": 0.4,
            },
            "habits": {},
            "last_activity": "",
            "last_action": "",
        }
        action_space = {"工作": ["推进方案", "拖延刷手机"]}
        recall_context = {
            "hits": [
                {
                    "type": "episode",
                    "text": "上次拖延刷手机导致项目失败，自己很后悔也更焦虑。",
                    "score": 0.9,
                }
            ]
        }
        with patch.object(sim, "STATEFUL", False):
            random.seed(11)
            productive = 0
            for _ in range(200):
                choice = sim.choose_action(
                    agent,
                    "工作",
                    action_space,
                    context="工作",
                    location_bias={},
                    location="Office",
                    time_str="10:00",
                    recall_context=recall_context,
                )
                if choice == "推进方案":
                    productive += 1
        self.assertGreater(productive, 115)

    def test_evoke_memory_surfaces_recollection_and_changes_state(self):
        agent = {
            "id": 22,
            "state": {
                "emotion": 0.50,
                "stress": 0.50,
            },
        }
        hits = [
            {
                "type": "memory",
                "text": "你之前顺利完成过类似任务，当时感到很满意也更放松。",
                "score": 0.6,
            }
        ]
        with patch.object(sim, "retrieve_relevant_memories", return_value=hits):
            recall = sim.evoke_memory(agent, "planning", "类似任务")
        self.assertIn("想起", recall["recollection"])
        self.assertGreater(agent["state"]["emotion"], 0.50)
        self.assertLess(agent["state"]["stress"], 0.50)

    def test_interview_agent_includes_recollection_in_prompt(self):
        agent = {"id": 23, "name": "测试者", "state": {"emotion": 0.5, "stress": 0.5}}
        questions = ["你为什么最近减少社交？"]
        llm_output = '[{"question":"你为什么最近减少社交？","answer":"因为前几次聚会让我有点疲惫。"}]'
        with patch.object(
            sim,
            "evoke_memory",
            return_value={
                "hint": "最近几次聚会后的疲惫感",
                "recollection": "这些问题让你回忆起一段经历：聚会后明显感到疲惫。",
                "hits": [],
            },
        ), patch.object(sim, "call_llm", return_value=llm_output) as mock_call:
            answers = sim.interview_agent(agent, questions, context="关注近期社交变化")
        prompt = mock_call.call_args.args[0]
        self.assertIn("这些问题勾起的回忆", prompt)
        self.assertIn("聚会后明显感到疲惫", prompt)
        self.assertEqual("因为前几次聚会让我有点疲惫。", answers[0]["answer"])

    def test_memory_review_generates_meta_memory(self):
        agent = {
            "id": 24,
            "name": "复盘者",
            "state": {"emotion": 0.5, "stress": 0.5},
            "memory": [],
            "episodes": [
                {
                    "episode_id": "e1",
                    "day": 2,
                    "time": "09:00",
                    "final_activity": "上午工作",
                    "action": "推进项目",
                    "reflection": "这次推进很顺利",
                    "tags": ["work", "success"],
                    "salience": 0.8,
                }
            ],
        }
        budget = {"remaining": 1}
        with patch.object(sim, "save_agent_memory"), patch.object(
            sim, "vector_db_add_entry"
        ) as mock_vector, patch.object(
            sim, "call_llm", return_value="你意识到稳定推进重点任务时，情绪和节奏都会更稳。"
        ):
            review = sim.maybe_review_memories(
                agent,
                day=2,
                time_str="12:00",
                recent_episode=agent["episodes"][0],
                llm_budget_ctx=budget,
            )
        self.assertIn("MemoryReview", review)
        self.assertEqual(0, budget["remaining"])
        self.assertTrue(agent["memory"])
        self.assertIn("更稳", agent["memory"][0])
        self.assertEqual("meta_memory", mock_vector.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
