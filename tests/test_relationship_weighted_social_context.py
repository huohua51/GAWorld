import unittest
from unittest.mock import patch

import generative_city_sim as sim


class TestRelationshipWeightedSocialContext(unittest.TestCase):
    def test_high_closeness_sampled_more(self):
        agent = {
            "social_neighbors": [1, 2, 3, 4],
            "relationships": {
                "1": {"closeness": 0.95},
                "2": {"closeness": 0.05},
                "3": {"closeness": 0.05},
                "4": {"closeness": 0.05},
            },
        }
        agents_by_id = {
            1: {"name": "甲"},
            2: {"name": "乙"},
            3: {"name": "丙"},
            4: {"name": "丁"},
        }
        with patch.object(sim, "HUMAN_REALISM_ENABLED", True):
            counts = {1: 0, 2: 0, 3: 0, 4: 0}
            for _ in range(300):
                sim.get_social_context(agent, agents_by_id)
                for n in agent.get("_recent_social_partners", []):
                    counts[n] += 1
        self.assertGreater(counts[1], counts[2])
        self.assertGreater(counts[1], counts[3])
        self.assertGreater(counts[1], counts[4])


if __name__ == "__main__":
    unittest.main()
