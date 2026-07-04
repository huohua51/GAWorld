"""Tests for the Agent Studio backend helpers in ``gaworld.apps.dashboard_server``.

These exercise the read/write paths added for the Studio UI without starting an
HTTP server: state round-trip + profile sync, agent creation, and the social
snapshot reader. All writes target temp copies so repo seed data is untouched.
"""

import json
import os
import shutil
import tempfile
import unittest

import gaworld.apps.dashboard_server as ds

REPO_ROOT = ds.REPO_ROOT
REAL_CSV = os.path.join(REPO_ROOT, "data", "hangzhou_agents_state_init.csv")
REAL_MD = os.path.join(REPO_ROOT, "data", "hangzhou_profiles_with_names.md")


class TestStateRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._csv, self._md = ds.STATE_CSV_PATH, ds.PROFILE_PATH
        ds.STATE_CSV_PATH = os.path.join(self.tmp, "state.csv")
        ds.PROFILE_PATH = os.path.join(self.tmp, "profiles.md")
        shutil.copy(REAL_CSV, ds.STATE_CSV_PATH)
        shutil.copy(REAL_MD, ds.PROFILE_PATH)

    def tearDown(self):
        ds.STATE_CSV_PATH, ds.PROFILE_PATH = self._csv, self._md
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_state_write_persists_to_csv(self):
        ds._save_agent_state(1, {"state": {"emotion": 0.123, "risk_preference": 0.9}})
        again = ds._agent_state(1)
        self.assertAlmostEqual(again["state"]["emotion"], 0.123, places=4)
        self.assertAlmostEqual(again["state"]["risk_preference"], 0.9, places=4)

    def test_state_write_syncs_profile_markdown(self):
        ds._save_agent_state(1, {"state": {"emotion": 0.11, "mobility_intent": 0.77}})
        block = ds._agent_profile(1)["text"]
        self.assertIn("emotion 0.11", block)
        self.assertIn("- mobility_intent：0.77", block)

    def test_identity_edit_persists(self):
        ds._save_agent_state(1, {"name": "测试改名", "age": 41})
        again = ds._agent_state(1)
        self.assertEqual(again["name"], "测试改名")
        self.assertEqual(again["age"], 41)

    def test_state_clamped_to_unit_interval(self):
        ds._save_agent_state(1, {"state": {"stress": 5.0, "emotion": -3}})
        again = ds._agent_state(1)
        self.assertEqual(again["state"]["stress"], 1.0)
        self.assertEqual(again["state"]["emotion"], 0.0)


class TestCreateAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._csv, self._md = ds.STATE_CSV_PATH, ds.PROFILE_PATH
        ds.STATE_CSV_PATH = os.path.join(self.tmp, "state.csv")
        ds.PROFILE_PATH = os.path.join(self.tmp, "profiles.md")
        shutil.copy(REAL_CSV, ds.STATE_CSV_PATH)
        shutil.copy(REAL_MD, ds.PROFILE_PATH)

    def tearDown(self):
        ds.STATE_CSV_PATH, ds.PROFILE_PATH = self._csv, self._md
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_appends_row_and_block(self):
        before = {a["id"] for a in ds._agents_summary()}
        res = ds._create_agent({"name": "新居民甲", "gender": "女", "age": 27, "state": {"risk_preference": 0.9}})
        self.assertNotIn(res["id"], before)
        # readable from CSV
        state = ds._agent_state(res["id"])
        self.assertEqual(state["name"], "新居民甲")
        self.assertAlmostEqual(state["state"]["risk_preference"], 0.9, places=4)
        # profile block appended
        with open(ds.PROFILE_PATH, encoding="utf-8") as f:
            self.assertIn("新居民甲", f.read())

    def test_create_preserves_bom(self):
        ds._create_agent({"name": "BOM测试"})
        with open(ds.STATE_CSV_PATH, "rb") as f:
            self.assertEqual(f.read(3), b"\xef\xbb\xbf")


class TestSocialSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._root, self._cfg = ds.REPO_ROOT, ds._effective_config
        ds.REPO_ROOT = self.tmp
        ds._effective_config = lambda: {"memory_dir": "output/memory"}
        mem = os.path.join(self.tmp, "output", "memory")
        os.makedirs(mem, exist_ok=True)
        rels = {
            "42": {"kind": "agent", "role": "coworker", "dunbar_tier": "close",
                   "closeness": 0.6, "trust": 0.5, "profile": {"name": "同事小王"}},
            "g_mother": {"kind": "ghost", "role": "mother", "dunbar_tier": "inner",
                         "closeness": 0.85, "trust": 0.86, "profile": {"name": "母亲"}},
        }
        with open(os.path.join(mem, "agent_9_relationships.json"), "w", encoding="utf-8") as f:
            json.dump(rels, f, ensure_ascii=False)

    def tearDown(self):
        ds.REPO_ROOT, ds._effective_config = self._root, self._cfg
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_snapshot_parses_and_sorts(self):
        snap = ds._social_snapshot(9)
        self.assertEqual(snap["count"], 2)
        self.assertEqual(snap["tier_counts"]["inner"], 1)
        self.assertEqual(snap["tier_counts"]["close"], 1)
        # sorted by closeness desc → mother first
        self.assertEqual(snap["relations"][0]["name"], "母亲")
        self.assertEqual(snap["relations"][0]["kind"], "ghost")

    def test_snapshot_none_when_absent(self):
        self.assertIsNone(ds._social_snapshot(9999))


if __name__ == "__main__":
    unittest.main()
