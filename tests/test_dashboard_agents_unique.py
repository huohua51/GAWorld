"""Regression tests for duplicate agent ids in ``/api/agents``.

``_agents_summary()`` emits one entry per ``## Profile N｜Name`` header match and
does not dedupe, so a repeated header in the seed markdown surfaces as two cards
in the dashboard 选择成员 picker that toggle the same id. The seed file used to
carry a stale legacy-schema copy of Profile 05 (王思远) alongside the current one;
these tests keep the data honest rather than papering over it in the loader.
"""

import os
import re
import shutil
import tempfile
import unittest
from collections import Counter

import gaworld.apps.dashboard_server as ds

REPO_ROOT = ds.REPO_ROOT
REAL_MD = os.path.join(REPO_ROOT, "data", "hangzhou_profiles_with_names.md")

# The schema every current profile block uses. The retired one keyed its state
# variables in Chinese under **可运行状态变量（示例）**.
CURRENT_STATE_RE = re.compile(r"^\*\*核心状态变量\*\*：", re.MULTILINE)
LEGACY_STATE_RE = re.compile(r"^\*\*可运行状态变量")


def _profile_blocks(path):
    """Split the seed markdown into (id, name, body) tuples, headers only."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    matches = list(ds.PROFILE_HEADER_RE.finditer(text))
    blocks = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((int(match.group(1)), match.group(2).strip(), text[match.start():end]))
    return blocks


class TestSeedProfilesUnique(unittest.TestCase):
    def test_seed_profile_ids_are_unique(self):
        ids = [block[0] for block in _profile_blocks(REAL_MD)]
        duplicates = sorted(i for i, count in Counter(ids).items() if count > 1)
        self.assertEqual([], duplicates, f"duplicate profile ids in seed markdown: {duplicates}")

    def test_agents_summary_returns_one_entry_per_id(self):
        agents = ds._agents_summary()
        ids = [agent["id"] for agent in agents]
        self.assertEqual(len(ids), len(set(ids)), "/api/agents returned duplicate agent ids")
        self.assertEqual(len(ids), len(_profile_blocks(REAL_MD)))

    def test_no_profile_uses_the_retired_state_schema(self):
        stale = [
            (agent_id, name)
            for agent_id, name, body in _profile_blocks(REAL_MD)
            if LEGACY_STATE_RE.search(body)
        ]
        self.assertEqual([], stale, f"profiles still on the retired state schema: {stale}")

    def test_every_profile_declares_current_state_variables(self):
        missing = [
            (agent_id, name)
            for agent_id, name, body in _profile_blocks(REAL_MD)
            if not CURRENT_STATE_RE.search(body)
        ]
        self.assertEqual([], missing, f"profiles missing **核心状态变量**: {missing}")


class TestDuplicateHeaderIsDetectable(unittest.TestCase):
    """Guard that the checks above would actually fail on a reintroduced duplicate."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._md = ds.PROFILE_PATH
        ds.PROFILE_PATH = os.path.join(self.tmp, "profiles.md")
        shutil.copy(REAL_MD, ds.PROFILE_PATH)

    def tearDown(self):
        ds.PROFILE_PATH = self._md
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_duplicate_header_surfaces_in_agents_summary(self):
        before = ds._agents_summary()
        with open(ds.PROFILE_PATH, "a", encoding="utf-8") as f:
            f.write("\n## Profile 05｜王思远\n**基础信息**：男，30岁。\n\n---\n")
        after = ds._agents_summary()
        self.assertEqual(len(before) + 1, len(after))
        self.assertEqual(2, Counter(a["id"] for a in after)[5])
