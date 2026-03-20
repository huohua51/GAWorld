import unittest
from unittest.mock import patch

import generative_city_sim as sim


class TestStateDynamicsRebalancing(unittest.TestCase):
    def test_update_needs_matches_realistic_meal_and_social_phrasing(self):
        agent = {
            "state": {
                "energy": 0.6,
                "hunger": 0.82,
                "social_need": 0.72,
            }
        }
        sim.update_needs(agent, "12:30", "与学生和合作者开组会讨论项目进展后一起午餐")
        self.assertLess(agent["state"]["hunger"], 0.82)
        self.assertLess(agent["state"]["social_need"], 0.72)
        self.assertGreater(agent["state"]["energy"], 0.5)

    def test_breakfast_phrase_counts_as_meal(self):
        agent = {
            "state": {
                "energy": 0.7,
                "hunger": 0.74,
                "social_need": 0.4,
            }
        }
        sim.update_needs(agent, "08:00", "早餐后前往高校实验室")
        self.assertLess(agent["state"]["hunger"], 0.74)

    def test_state_update_stays_off_hard_edges_over_long_horizon(self):
        agent = {
            "state": {
                "emotion": 0.58,
                "stress": 0.52,
                "econ_security": 0.5,
                "city_identity": 0.55,
                "policy_sensitivity": 0.55,
                "platform_dependence": 0.72,
                "risk_preference": 0.45,
                "voice_propensity": 0.66,
                "mobility_intent": 0.5,
                "energy": 0.75,
                "hunger": 0.25,
                "social_need": 0.4,
            }
        }
        tracked = {k: [] for k in agent["state"]}
        with patch.object(sim, "HUMAN_REALISM_ENABLED", True), patch.object(
            sim.random, "uniform", side_effect=lambda lo, hi: 0.0
        ):
            for _ in range(400):
                sim.update_state(agent)
                for key, value in agent["state"].items():
                    tracked[key].append(value)

        for key in [
            "emotion",
            "stress",
            "econ_security",
            "city_identity",
            "policy_sensitivity",
            "platform_dependence",
            "risk_preference",
            "voice_propensity",
            "mobility_intent",
            "energy",
            "hunger",
            "social_need",
        ]:
            self.assertGreater(min(tracked[key]), 0.05, key)
            self.assertLess(max(tracked[key]), 0.95, key)


if __name__ == "__main__":
    unittest.main()
