import os
import tempfile
import unittest

import memory_store as ms


class TestMemoryStoreCaches(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.old_log_dir = ms.LOG_DIR
        self.old_memory_dir = ms.MEMORY_DIR
        self.old_vector_db_path = ms.VECTOR_DB_PATH
        ms.LOG_DIR = os.path.join(self.tmpdir.name, "logs")
        ms.MEMORY_DIR = os.path.join(self.tmpdir.name, "memory")
        ms.VECTOR_DB_PATH = os.path.join(ms.MEMORY_DIR, "vector.sqlite")
        ms._LOG_CACHE.clear()
        ms._close_vector_db()

    def tearDown(self):
        ms._close_vector_db()
        ms._LOG_CACHE.clear()
        ms.LOG_DIR = self.old_log_dir
        ms.MEMORY_DIR = self.old_memory_dir
        ms.VECTOR_DB_PATH = self.old_vector_db_path

    def test_recent_log_blocks_and_actions_follow_append_cache(self):
        agent = {"id": 7}
        ms.append_agent_log(agent, "[Morning]\nPlan: 出门\nAction: 吃早餐\n")
        ms.append_agent_log(agent, "[Noon]\nPlan: 工作\nAction: 写代码\n")

        blocks = ms.load_recent_log_blocks(7, max_blocks=2, max_chars=200)
        actions = ms.load_recent_actions(7, max_items=4)

        self.assertEqual(2, len(blocks))
        self.assertIn("[Morning]", blocks[0])
        self.assertIn("[Noon]", blocks[1])
        self.assertEqual(["吃早餐", "写代码"], actions)

    def test_vector_db_connection_is_reused(self):
        first = ms._vector_db_connect()
        second = ms._vector_db_connect()

        self.assertIs(first, second)

        ms.vector_db_add_entry(3, "memory", "project alpha launch", sim_day=1, sim_time="08:00")
        hits = ms.vector_db_search(3, "project alpha launch", top_k=1)

        self.assertEqual(1, len(hits))
        self.assertEqual("memory", hits[0]["type"])


if __name__ == "__main__":
    unittest.main()
