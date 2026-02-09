import unittest
from unittest.mock import patch

import generative_city_sim as sim


class TestResetGateForMemoryModel(unittest.TestCase):
    def test_run_blocked_on_version_mismatch(self):
        with patch.object(sim, "REQUIRE_CLEAN_RESET_ON_MEMORY_MODEL_CHANGE", True), patch.object(
            sim, "MEMORY_MODEL_VERSION", 99
        ):
            with self.assertRaises(RuntimeError):
                sim._enforce_memory_model_compat({"memory_model_version": 2})

    def test_run_allowed_on_matching_version(self):
        with patch.object(sim, "REQUIRE_CLEAN_RESET_ON_MEMORY_MODEL_CHANGE", True), patch.object(
            sim, "MEMORY_MODEL_VERSION", 2
        ):
            sim._enforce_memory_model_compat({"memory_model_version": 2})


if __name__ == "__main__":
    unittest.main()
