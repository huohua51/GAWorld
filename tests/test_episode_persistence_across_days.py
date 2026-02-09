import tempfile
import unittest

from experience_store import append_agent_episode, load_agent_episodes


class TestEpisodePersistenceAcrossDays(unittest.TestCase):
    def test_episodes_append_and_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = {"memory_dir": tmpdir}
            append_agent_episode(
                7,
                {
                    "episode_id": "e1",
                    "day": 1,
                    "time": "09:00",
                    "final_activity": "上午工作",
                    "action": "整理任务",
                    "salience": 0.4,
                    "created_at_day": 1,
                },
                cfg=cfg,
            )
            append_agent_episode(
                7,
                {
                    "episode_id": "e2",
                    "day": 2,
                    "time": "10:00",
                    "final_activity": "上午工作",
                    "action": "推进项目",
                    "salience": 0.6,
                    "created_at_day": 2,
                },
                cfg=cfg,
            )
            episodes = load_agent_episodes(7, cfg=cfg)
            self.assertEqual(2, len(episodes))
            self.assertEqual("e1", episodes[0]["episode_id"])
            self.assertEqual("e2", episodes[1]["episode_id"])


if __name__ == "__main__":
    unittest.main()
