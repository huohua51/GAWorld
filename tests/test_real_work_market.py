"""Tests for the JobMarket and capability-derivation."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from gaworld.work.capabilities import (
    AgentCapabilities,
    bootstrap_all_agents,
    derive_one,
)
from gaworld.work.market import (
    JobAlreadyTaken,
    JobMarket,
    accept_probability,
    browse_probability,
    deterministic_random,
)


_SEED = [
    {
        "job_id": "mj_design_1",
        "title": "海报",
        "description": "活动海报",
        "deliverable": "poster_svg",
        "required_skills": ["排版", "色彩搭配"],
        "required_job_labels": ["ui_designer"],
        "reward_econ": 0.15,
        "reward_text": "￥800",
        "deadline_window_days": 3,
        "source_tag": "mock_seed",
    },
    {
        "job_id": "mj_doctor_1",
        "title": "对照组",
        "description": "需要医生职业",
        "deliverable": "md_article",
        "required_skills": ["医学"],
        "required_job_labels": ["doctor"],
        "reward_econ": 0.20,
        "reward_text": "￥1200",
        "deadline_window_days": 4,
        "source_tag": "mock_seed_control",
    },
    {
        "job_id": "mj_code_1",
        "title": "脚本",
        "description": "数据脚本",
        "deliverable": "py_script",
        "required_skills": ["数据处理"],
        "required_job_labels": ["algorithm_engineer"],
        "reward_econ": 0.10,
        "reward_text": "￥500",
        "deadline_window_days": 2,
        "source_tag": "mock_seed",
    },
]


def _seed_file(tmpdir: str, payload=_SEED) -> str:
    path = os.path.join(tmpdir, "seed.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return path


def _make_market(tmpdir: str) -> JobMarket:
    return JobMarket(
        store_path=os.path.join(tmpdir, "market.jsonl"),
        seed_path=_seed_file(tmpdir),
    )


def _designer_caps() -> AgentCapabilities:
    return AgentCapabilities(
        agent_id=2, job_label="ui_designer",
        skills=["排版", "色彩搭配", "插画"],
        interests=[], deliverables=["poster_svg", "html_landing"],
        adapter_priority=["web_design"], notes="设计师",
    )


def _engineer_caps() -> AgentCapabilities:
    return AgentCapabilities(
        agent_id=3, job_label="algorithm_engineer",
        skills=["数据处理", "Python"],
        interests=[], deliverables=["py_script"],
        adapter_priority=["code"], notes="工程师",
    )


class TestJobMarketBasics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.market = _make_market(self.tmp)

    def test_seed_loads_jobs_and_skips_unsupported(self):
        ids = {j.job_id for j in self.market.all_jobs()}
        self.assertIn("mj_design_1", ids)
        self.assertIn("mj_code_1", ids)
        # The doctor control job has a valid deliverable; it loads but
        # remains unmatchable because no agent has job_label="doctor".
        self.assertIn("mj_doctor_1", ids)

    def test_browse_filters_by_label_and_ranks_by_score(self):
        listings = self.market.browse(_designer_caps(), sim_day=1, top_k=5)
        self.assertGreaterEqual(len(listings), 1)
        # Designer can NOT see code job (different label) or doctor job.
        for job, _score in listings:
            self.assertIn(_designer_caps().job_label, job.required_job_labels)
        # Engineer sees the code job.
        eng_listings = self.market.browse(_engineer_caps(), sim_day=1, top_k=5)
        eng_ids = {j.job_id for j, _ in eng_listings}
        self.assertIn("mj_code_1", eng_ids)

    def test_doctor_control_never_matches_residents(self):
        # No agent in the residents pool has 'doctor' label.
        listings = self.market.browse(_designer_caps(), sim_day=1, top_k=10)
        listings += self.market.browse(_engineer_caps(), sim_day=1, top_k=10)
        for job, _ in listings:
            self.assertNotIn("doctor", job.required_job_labels)

    def test_take_locks_job_and_blocks_second_take(self):
        taken = self.market.take(
            "mj_design_1", agent_id=2,
            sim_time="09:30", sim_day=1,
            max_taken_per_agent_per_day=2,
        )
        self.assertEqual("taken", taken.status)
        self.assertEqual(2, taken.taken_by_agent_id)
        with self.assertRaises(JobAlreadyTaken):
            self.market.take(
                "mj_design_1", agent_id=5,
                sim_time="09:31", sim_day=1,
                max_taken_per_agent_per_day=2,
            )

    def test_daily_quota_enforced(self):
        self.market.take(
            "mj_design_1", agent_id=2,
            sim_time="09:00", sim_day=1,
            max_taken_per_agent_per_day=1,
        )
        with self.assertRaises(JobAlreadyTaken):
            self.market.take(
                "mj_code_1", agent_id=2,
                sim_time="10:00", sim_day=1,
                max_taken_per_agent_per_day=1,
            )

    def test_release_reopens_taken_job(self):
        self.market.take(
            "mj_design_1", agent_id=2,
            sim_time="09:00", sim_day=1,
            max_taken_per_agent_per_day=2,
        )
        self.market.release("mj_design_1")
        job = next(j for j in self.market.all_jobs() if j.job_id == "mj_design_1")
        self.assertEqual("open", job.status)
        self.assertIsNone(job.taken_by_agent_id)

    def test_settle_marks_done_or_failed(self):
        self.market.take(
            "mj_design_1", agent_id=2,
            sim_time="09:00", sim_day=1,
            max_taken_per_agent_per_day=2,
        )
        self.market.settle("mj_design_1", success=True)
        job = next(j for j in self.market.all_jobs() if j.job_id == "mj_design_1")
        self.assertEqual("done", job.status)

    def test_tick_day_expires_open_jobs(self):
        # day 5 > deadline_window 3; mj_design_1 should expire.
        self.market.tick_day(5)
        job = next(j for j in self.market.all_jobs() if j.job_id == "mj_design_1")
        self.assertEqual("expired", job.status)

    def test_persistence_reloads_state(self):
        self.market.take(
            "mj_design_1", agent_id=2,
            sim_time="09:00", sim_day=1,
            max_taken_per_agent_per_day=2,
        )
        # Reopen from disk; status should still be 'taken'.
        m2 = JobMarket(
            store_path=os.path.join(self.tmp, "market.jsonl"),
            seed_path=_seed_file(self.tmp),
        )
        job = next(j for j in m2.all_jobs() if j.job_id == "mj_design_1")
        self.assertEqual("taken", job.status)


class TestProbabilityHelpers(unittest.TestCase):
    def test_browse_probability_increases_with_platform_dependence(self):
        low = browse_probability({"platform_dependence": 0.1, "econ_security": 0.7, "energy": 0.7}, base=0.15)
        high = browse_probability({"platform_dependence": 0.9, "econ_security": 0.7, "energy": 0.7}, base=0.15)
        self.assertGreater(high, low)

    def test_browse_probability_clipped(self):
        p = browse_probability(
            {"platform_dependence": 1.0, "econ_security": 0.0, "energy": 1.0},
            base=0.5,
        )
        self.assertLessEqual(p, 0.6)

    def test_accept_probability_in_unit_interval(self):
        for score in (0.0, 0.5, 1.0):
            p = accept_probability(score, {"risk_preference": 0.5, "stress": 0.5})
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)

    def test_deterministic_random_is_stable(self):
        r1 = deterministic_random(7, 3, salt="s")
        r2 = deterministic_random(7, 3, salt="s")
        self.assertEqual(r1.random(), r2.random())


class TestCapabilitiesDerivation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.tmp, "caps.json")

    def _llm_returns(self, payload: dict):
        text = json.dumps(payload, ensure_ascii=False)

        def _fn(_prompt: str) -> str:
            return text

        return _fn

    def test_derive_one_parses_valid_json(self):
        agent = {"id": 1, "name": "李", "job": "UI 设计师", "personality": "外向",
                 "daily_life": "看展", "values": "美学"}
        llm = self._llm_returns({
            "job_label": "ui_designer",
            "skills": ["排版"],
            "interests": ["插画"],
            "deliverables": ["html_landing", "poster_svg"],
            "adapter_priority": ["web_design"],
            "notes": "ok",
        })
        caps = derive_one(agent, llm=llm)
        self.assertEqual("ui_designer", caps.job_label)
        self.assertIn("html_landing", caps.deliverables)

    def test_invalid_label_falls_back_to_other(self):
        agent = {"id": 1, "name": "x", "job": "?", "personality": "", "daily_life": "", "values": ""}
        llm = self._llm_returns({"job_label": "not_in_enum", "skills": [], "deliverables": [],
                                 "interests": [], "adapter_priority": [], "notes": ""})
        caps = derive_one(agent, llm=llm)
        self.assertEqual("other", caps.job_label)

    def test_unknown_deliverables_filtered(self):
        agent = {"id": 1, "name": "x", "job": "?", "personality": "", "daily_life": "", "values": ""}
        llm = self._llm_returns({
            "job_label": "ui_designer",
            "skills": ["x"],
            "interests": [],
            "deliverables": ["html_landing", "fictional_thing", "py_script"],
            "adapter_priority": ["web_design"],
            "notes": "",
        })
        caps = derive_one(agent, llm=llm)
        self.assertIn("html_landing", caps.deliverables)
        self.assertNotIn("fictional_thing", caps.deliverables)

    def test_cache_hit_skips_llm_call(self):
        calls = {"n": 0}

        def llm(_prompt: str) -> str:
            calls["n"] += 1
            return json.dumps({
                "job_label": "ui_designer", "skills": [], "interests": [],
                "deliverables": ["html_landing"], "adapter_priority": ["web_design"], "notes": "",
            })

        agents = [{"id": 1, "name": "x", "job": "j", "personality": "p", "daily_life": "d", "values": "v"}]
        bootstrap_all_agents(agents, self.cache_path, llm=llm)
        self.assertEqual(1, calls["n"])
        # Re-bootstrap with the same profile; should hit cache.
        bootstrap_all_agents(agents, self.cache_path, llm=llm)
        self.assertEqual(1, calls["n"])
        # Profile change → cache miss.
        agents[0]["job"] = "different"
        bootstrap_all_agents(agents, self.cache_path, llm=llm)
        self.assertEqual(2, calls["n"])

    def test_llm_failure_yields_empty_capabilities(self):
        def llm(_prompt: str) -> str:
            raise RuntimeError("boom")

        agent = {"id": 1, "name": "x", "job": "j", "personality": "", "daily_life": "", "values": ""}
        caps = derive_one(agent, llm=llm)
        self.assertEqual("other", caps.job_label)
        self.assertEqual([], caps.deliverables)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
