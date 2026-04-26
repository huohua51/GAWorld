"""Tests for the typed :class:`gaworld.config.SimulationConfig` wrapper."""

from __future__ import annotations

import unittest

from gaworld.config import LLMProvider, SimulationConfig, from_legacy


SAMPLE = {
    "agent_ids": ["1", 2, 0, 2, "x"],
    "sim_days": "5",
    "seconds_per_day": 7,
    "simulate_realtime": "true",
    "time_step_minutes": "2 hours",
    "stateful": True,
    "background": "B",
    "memory_model_version": 3,
    "require_clean_reset_on_memory_model_change": True,
    "csv_path": "data.csv",
    "memory_dir": "out/m",
    "llm": {
        "providers": {
            "p1": {"type": "ollama", "model": "qwen", "timeout": 99},
            "broken": "not a dict",
        },
        "routing": {
            "default": "p1",
            "tasks": {"plan": "p1"},
            "agents": {7: "p1"},
        },
    },
    "random_seed": 42,
}


class TestFromLegacy(unittest.TestCase):
    def test_scalar_coercion(self):
        cfg = from_legacy(SAMPLE)
        self.assertIsInstance(cfg, SimulationConfig)
        self.assertEqual((1, 2), cfg.agent_ids)
        self.assertEqual(5, cfg.sim_days)
        self.assertEqual(7, cfg.seconds_per_day)
        self.assertTrue(cfg.simulate_realtime)
        self.assertEqual(120, cfg.time_step_minutes)  # "2 hours"
        self.assertEqual(3, cfg.memory_model_version)
        self.assertTrue(cfg.require_clean_reset_on_memory_model_change)
        self.assertEqual(42, cfg.random_seed)

    def test_paths_default_when_missing(self):
        cfg = from_legacy({})
        self.assertTrue(cfg.paths.csv_path.endswith(".csv"))
        self.assertEqual("output/memory", cfg.paths.memory_dir)

    def test_llm_providers_filter_invalid(self):
        cfg = from_legacy(SAMPLE)
        self.assertIn("p1", cfg.llm.providers)
        self.assertNotIn("broken", cfg.llm.providers)
        self.assertIsInstance(cfg.llm.providers["p1"], LLMProvider)
        self.assertEqual("qwen", cfg.llm.providers["p1"].model)
        self.assertEqual(99, cfg.llm.providers["p1"].extras["timeout"])

    def test_llm_routing(self):
        cfg = from_legacy(SAMPLE)
        self.assertEqual("p1", cfg.llm.routing.default)
        self.assertEqual({"plan": "p1"}, dict(cfg.llm.routing.tasks))
        self.assertEqual({"7": "p1"}, dict(cfg.llm.routing.agents))


if __name__ == "__main__":
    unittest.main()
