"""Tests for the new :class:`gaworld.core.agent.Agent` adapter."""

from __future__ import annotations

import unittest

from gaworld.core.agent import Agent, ensure_agent_dict, view_as_agent


class TestAgentAdapter(unittest.TestCase):
    def test_dict_interface_round_trips(self):
        a = Agent(data={"id": 7, "name": "X"})
        a["foo"] = 1
        self.assertEqual(1, a["foo"])
        self.assertEqual({"id": 7, "name": "X", "foo": 1}, a.to_dict())

    def test_typed_accessors(self):
        a = Agent(data={"id": "11", "name": "Bob", "state": {"energy": "0.4"}})
        self.assertEqual(11, a.id)
        self.assertEqual("Bob", a.name)
        self.assertAlmostEqual(0.4, a.need("energy"), places=6)
        self.assertEqual(0.0, a.need("missing"))

    def test_id_invalid_returns_none(self):
        self.assertIsNone(Agent(data={"id": "xx"}).id)
        self.assertIsNone(Agent().id)

    def test_view_as_agent_does_not_copy(self):
        d = {"id": 1, "state": {"energy": 0.5}}
        a = view_as_agent(d)
        a["state"]["energy"] = 0.8
        self.assertEqual(0.8, d["state"]["energy"])
        # And calling on an Agent returns the same instance.
        self.assertIs(a, view_as_agent(a))

    def test_ensure_agent_dict_handles_both_inputs(self):
        d = {"id": 2}
        self.assertIs(d, ensure_agent_dict(d))
        a = Agent(data=d)
        self.assertIs(d, ensure_agent_dict(a))


class TestAgentMutableProperties(unittest.TestCase):
    def test_state_property_initialises_dict(self):
        a = Agent()
        self.assertEqual({}, a.state)
        a.state["energy"] = 1.0
        self.assertEqual({"energy": 1.0}, a.data["state"])


if __name__ == "__main__":
    unittest.main()
