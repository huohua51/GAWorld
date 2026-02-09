import random
import unittest
from unittest.mock import patch

import generative_city_sim as sim


class TestNeedsInfluenceActionChoice(unittest.TestCase):
    def test_low_energy_prefers_rest(self):
        agent = {
            "id": 11,
            "state": {
                "emotion": 0.5,
                "stress": 0.5,
                "econ_security": 0.5,
                "energy": 0.1,
                "hunger": 0.2,
                "social_need": 0.4,
            },
            "habits": {},
            "last_activity": "",
            "last_action": "",
        }
        action_space = {"个人时间": ["回家休息", "继续工作"]}
        with patch.object(sim, "STATEFUL", False), patch.object(
            sim, "retrieve_relevant_memories", return_value=[]
        ):
            random.seed(7)
            rest_count = 0
            for _ in range(200):
                choice = sim.choose_action(
                    agent,
                    "个人时间",
                    action_space,
                    context="个人时间",
                    location_bias={},
                    location="Central Block",
                    time_str="20:00",
                )
                if "休息" in choice:
                    rest_count += 1
            self.assertGreater(rest_count, 105)


if __name__ == "__main__":
    unittest.main()
