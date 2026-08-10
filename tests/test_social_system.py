import json
import random
import unittest
from unittest.mock import patch

import networkx as nx

from gaworld.social.decision import SocialContext, decide_pair_interaction
from gaworld.social.hooks import on_agent_pre_step
from gaworld.social.llm_events import generate_interaction
from gaworld.social.memory import format_social_memory, social_event_salience, write_social_memories
from gaworld.social.reflection import relationship_reflection_text, write_relationship_reflections
from gaworld.social.runtime import SocialInteractionRuntime, initialize_agent_social_state
from gaworld.social.schemas import SocialDecision


def _agent(agent_id, **overrides):
    base = {
        "id": agent_id,
        "name": f"Agent-{agent_id}",
        "gender": "女",
        "age": 30 + agent_id,
        "hukou": "杭州",
        "residence": "西湖区·A小区",
        "state": {
            "emotion": 0.5,
            "stress": 0.55,
            "econ_security": 0.5,
            "city_identity": 0.6,
            "policy_sensitivity": 0.6,
            "platform_dependence": 0.5,
            "risk_preference": 0.5,
            "voice_propensity": 0.7,
            "social_need": 0.6,
            "energy": 0.7,
        },
        "relationships": {},
    }
    for key, value in overrides.items():
        if key == "state":
            base["state"].update(value)
        else:
            base[key] = value
    return base


def _decision(source_id=1, target_id=2):
    return SocialDecision(
        day=1,
        time="12:00",
        source_id=source_id,
        target_id=target_id,
        motivation_type="relationship_triggered",
        motivation="maintain_close_tie",
        interaction_type="invite",
        topic="午餐和近况",
        probability=0.9,
        random_draw=0.0,
        intensity=0.8,
        reason="test decision",
        motivation_reason="test motivation",
        trace={},
    )


class TestSocialSystem(unittest.TestCase):
    def test_initialize_social_state_syncs_graph_edges_to_agent_relationships(self):
        agents = [
            _agent(1, relationships={"2": {"trust": 0.91, "closeness": 0.88}}),
            _agent(2),
            _agent(3, residence="滨江区·B小区", hukou="外地"),
        ]

        graph = initialize_agent_social_state(
            agents,
            {"network_seed": 7, "avg_degree": 2, "weak_tie_probability": 0.0},
        )

        self.assertGreater(graph.number_of_edges(), 0)
        self.assertEqual(sorted(graph.neighbors(1)), sorted(agents[0]["social_neighbors"]))
        rel = agents[0]["relationships"][str(agents[0]["social_neighbors"][0])]
        self.assertIn("trust", rel)
        self.assertIn("closeness", rel)
        self.assertIn("support", rel)
        self.assertIn("influence", rel)
        if graph.has_edge(1, 2):
            self.assertAlmostEqual(0.91, graph.edges[1, 2]["trust"])

    def test_decision_uses_relationship_strength_and_conflict_rule(self):
        graph = nx.Graph()
        graph.add_node(1, stress=0.4, voice_propensity=0.4, platform_dependence=0.4, policy_sensitivity=0.4)
        graph.add_node(2, stress=0.4, voice_propensity=0.4, platform_dependence=0.4, policy_sensitivity=0.4)
        graph.add_edge(
            1,
            2,
            closeness=0.8,
            trust=0.8,
            friction=0.7,
            influence=0.7,
            obligation=0.3,
        )
        decision = decide_pair_interaction(graph, 1, 2, SocialContext(day=1, time="10:00"), random.Random(1))

        self.assertIsNotNone(decision)
        self.assertEqual("conflict", decision.interaction_type)
        self.assertGreater(decision.probability, 0.1)

    def test_runtime_tick_writes_state_relationship_and_pending_context(self):
        agents = [_agent(1), _agent(2)]
        runtime = SocialInteractionRuntime(
            {
                "seed": 1,
                "network_seed": 1,
                "avg_degree": 2,
                "max_events_per_tick": 1,
                "pair_cooldown_minutes": 0,
                "agent_daily_budget": 4,
            },
            agents,
        )
        with patch("gaworld.social.runtime.decide_interactions_for_slot", return_value=[_decision()]):
            events = runtime.tick(day=1, time_str="12:00", agents=agents, agent_activities={1: "午餐", 2: "午餐"})

        self.assertEqual(1, len(events))
        self.assertNotEqual(0.5, agents[0]["state"]["emotion"])
        self.assertIn("2", agents[0]["relationships"])
        self.assertGreater(agents[0]["relationships"]["2"]["closeness"], 0.5)
        self.assertTrue(agents[0].get("_pending_social_interactions"))

    def test_runtime_blocks_sleeping_agents_and_pair_cooldown(self):
        agents = [_agent(1), _agent(2)]
        runtime = SocialInteractionRuntime(
            {
                "seed": 1,
                "network_seed": 1,
                "avg_degree": 2,
                "max_events_per_tick": 1,
                "pair_cooldown_minutes": 180,
                "agent_daily_budget": 4,
            },
            agents,
        )
        with patch("gaworld.social.runtime.decide_interactions_for_slot", return_value=[_decision()]):
            blocked = runtime.tick(day=1, time_str="00:00", agents=agents, agent_activities={1: "睡觉", 2: "睡觉"})
            first = runtime.tick(day=1, time_str="12:00", agents=agents, agent_activities={1: "午餐", 2: "午餐"})
            second = runtime.tick(day=1, time_str="13:00", agents=agents, agent_activities={1: "午餐", 2: "午餐"})

        self.assertEqual([], blocked)
        self.assertEqual(1, len(first))
        self.assertEqual([], second)

    def test_hook_injects_pending_social_context(self):
        agent = {
            "id": 1,
            "_pending_social_interactions": [
                {"partner_id": 2, "text": "12:00 你和Agent-2聊到「午餐」。"}
            ],
        }
        step = {"social_context": "原有上下文"}

        on_agent_pre_step({"agent": agent, "step": step})

        self.assertIn("Agent-2", step["social_context"])
        self.assertTrue(step["social_interaction_trigger"])
        self.assertEqual([2], agent["_recent_social_partners"])

    def test_llm_bad_numeric_fields_do_not_crash_generation(self):
        graph = nx.Graph()
        graph.add_node(1, name="甲")
        graph.add_node(2, name="乙")
        graph.add_edge(1, 2, closeness=0.5, trust=0.5, friction=0.2)
        payload = {
            "message": "你好",
            "reply": "你好",
            "subjective_effect": "平稳",
            "emotion_delta_source": "bad",
            "stress_delta_target": None,
            "trust_delta": "0.02",
        }

        event = generate_interaction(graph, _decision(), llm_fn=lambda _: json.dumps(payload, ensure_ascii=False))

        self.assertEqual(0.0, event.emotion_delta_source)
        self.assertEqual(0.0, event.stress_delta_target)
        self.assertEqual(0.02, event.trust_delta)

    def test_social_memory_formats_and_persists_salient_events(self):
        agents = [_agent(1), _agent(2)]
        runtime = SocialInteractionRuntime(
            {
                "seed": 1,
                "network_seed": 1,
                "avg_degree": 2,
                "max_events_per_tick": 1,
                "pair_cooldown_minutes": 0,
                "agent_daily_budget": 4,
            },
            agents,
        )
        with patch("gaworld.social.runtime.decide_interactions_for_slot", return_value=[_decision()]):
            event = runtime.tick(day=1, time_str="12:00", agents=agents, agent_activities={1: "午餐", 2: "午餐"})[0]

        vector_records = []
        log_records = []
        saved = []
        records = write_social_memories(
            [event],
            agents,
            min_salience=0.0,
            vector_writer=lambda agent_id, entry_type, text, day, time_str: vector_records.append(
                (agent_id, entry_type, text, day, time_str)
            ),
            log_writer=lambda agent, text: log_records.append((agent["id"], text)),
            memory_saver=lambda agent: saved.append(agent["id"]),
        )

        self.assertGreaterEqual(social_event_salience(event), 0.5)
        self.assertIn("SocialMemory", format_social_memory(event, 1))
        self.assertEqual(2, len(records))
        self.assertEqual(2, len(vector_records))
        self.assertIn("social_memory", {row[1] for row in vector_records})
        self.assertTrue(agents[0]["_recent_social_memories"])
        self.assertTrue(saved)

    def test_relationship_reflection_persists_daily_summary(self):
        agents = [_agent(1), _agent(2)]
        runtime = SocialInteractionRuntime(
            {
                "seed": 1,
                "network_seed": 1,
                "avg_degree": 2,
                "max_events_per_tick": 1,
                "pair_cooldown_minutes": 0,
                "agent_daily_budget": 4,
            },
            agents,
        )
        with patch("gaworld.social.runtime.decide_interactions_for_slot", return_value=[_decision()]):
            event = runtime.tick(day=1, time_str="12:00", agents=agents, agent_activities={1: "午餐", 2: "午餐"})[0]

        text = relationship_reflection_text(agents[0], 1, [event])
        vector_records = []
        records = write_relationship_reflections(
            [event],
            agents,
            day=1,
            vector_writer=lambda agent_id, entry_type, text, day, time_str: vector_records.append(
                (agent_id, entry_type, text, day, time_str)
            ),
            log_writer=lambda agent, text: None,
            memory_saver=lambda agent: None,
        )

        self.assertIn("RelationshipReflection", text)
        self.assertEqual(2, len(records))
        self.assertEqual("social_reflection", vector_records[0][1])
        self.assertIn("_social_relationship_reflection", agents[0])


if __name__ == "__main__":
    unittest.main()
