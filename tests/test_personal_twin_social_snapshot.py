import os
import tempfile
import unittest

from distributed_comm_server import DistributedRelayBackend


class TestPersonalTwinSocialSnapshot(unittest.TestCase):
    def test_snapshot_tracks_multiple_nodes_and_recent_partners(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = DistributedRelayBackend(
                state_path=os.path.join(tmpdir, "relay_state.json"),
                max_messages=200,
            )
            backend.register_agents(
                "cluster-a",
                "node-1",
                [
                    {
                        "id": 1,
                        "name": "Twin-1",
                        "public_profile": {"summary": "node1 twin", "tags": ["pm"]},
                    }
                ],
                agent_type="personal_twin",
            )
            backend.register_agents(
                "cluster-a",
                "node-2",
                [
                    {
                        "id": 2,
                        "name": "Twin-2",
                        "public_profile": {"summary": "node2 twin", "tags": ["design"]},
                    }
                ],
                agent_type="personal_twin",
            )
            backend.send_message(
                "cluster-a",
                "node-1",
                {
                    "from_agent": 1,
                    "from_name": "Twin-1",
                    "to_agent": 2,
                    "text": "今天在本地做了一个求职方向的 what-if。",
                    "intent": "what_if_share",
                    "social_summary": {"summary": "分享求职方向推演结果", "topic": "职业选择"},
                },
            )
            backend.send_message(
                "cluster-a",
                "node-2",
                {
                    "from_agent": 2,
                    "from_name": "Twin-2",
                    "to_agent": 1,
                    "text": "我这边更建议先做短周期验证。",
                    "intent": "advice_request",
                    "social_summary": {"summary": "建议先做短周期验证", "topic": "建议反馈"},
                },
            )

            snapshot = backend.social_snapshot("cluster-a", recent_limit=5)
            self.assertEqual(2, snapshot["stats"]["agent_count"])
            self.assertEqual(1, snapshot["stats"]["edge_count"])
            self.assertEqual(2, snapshot["stats"]["recent_message_count"])
            agents = {item["agent_id"]: item for item in snapshot["agents"]}
            self.assertEqual([2], agents[1].get("recent_partners", [])[:1])
            self.assertEqual([1], agents[2].get("recent_partners", [])[:1])
            self.assertEqual("personal_twin", agents[1].get("agent_type"))
            self.assertEqual("node-1", agents[1].get("node_id"))


if __name__ == "__main__":
    unittest.main()
