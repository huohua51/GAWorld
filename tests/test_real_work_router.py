"""Tests for RealWorkRouter and ingest absorption."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from gaworld.work.ingest import absorb_completed_for, summarise_for_outcome
from gaworld.work.market import JobMarket
from gaworld.work.queue import WorkQueue
from gaworld.work.router import RealWorkRouter
from gaworld.work.schemas import AgentCapabilities, WorkResult


_SEED = [
    {
        "job_id": "mj_d1",
        "title": "海报设计",
        "description": "活动海报",
        "deliverable": "poster_svg",
        "required_skills": ["排版"],
        "required_job_labels": ["ui_designer"],
        "reward_econ": 0.15,
        "reward_text": "￥800",
        "deadline_window_days": 4,
        "source_tag": "mock_seed",
    },
]


def _seed_path(tmpdir: str) -> str:
    path = os.path.join(tmpdir, "seed.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_SEED, f, ensure_ascii=False)
    return path


def _agent(agent_id: int = 2) -> dict:
    return {
        "id": agent_id,
        "name": "周婉清",
        "job": "互联网公司 UI 设计师",
        "state": {
            "emotion": 0.6,
            "stress": 0.5,
            "econ_security": 0.5,
            "platform_dependence": 0.9,
            "risk_preference": 0.6,
            "energy": 0.7,
        },
        "memory": [],
    }


def _designer_caps(agent_id: int = 2) -> AgentCapabilities:
    return AgentCapabilities(
        agent_id=agent_id, job_label="ui_designer",
        skills=["排版", "色彩搭配"],
        interests=[],
        deliverables=["html_landing", "poster_svg"],
        adapter_priority=["web_design"],
        notes="设计师",
    )


def _engineer_caps(agent_id: int = 5) -> AgentCapabilities:
    return AgentCapabilities(
        agent_id=agent_id, job_label="algorithm_engineer",
        skills=["Python"],
        interests=[],
        deliverables=["py_script"],
        adapter_priority=["code"],
        notes="工程师",
    )


def _full_config(market_enabled: bool = True, browse_p: float = 1.0) -> dict:
    return {
        "enabled": True,
        "market": {
            "enabled": market_enabled,
            "browse_top_k": 5,
            "max_taken_per_agent_per_day": 2,
            "browse_probability_base": browse_p,
        },
    }


class TestRouterDisabledByDefault(unittest.TestCase):
    def test_returns_none_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = WorkQueue(os.path.join(tmp, "q.jsonl"))
            router = RealWorkRouter(queue=queue, market=None, capabilities={}, config={})
            agent = _agent()
            out = router.maybe_dispatch(
                agent, activity="工作", chosen_action="设计页面",
                sim_day=1, sim_time="10:00",
            )
            self.assertIsNone(out)
            self.assertEqual(0, queue.pending_count())


class TestRouterPathA(unittest.TestCase):
    def test_self_driven_dispatch_when_market_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = WorkQueue(os.path.join(tmp, "q.jsonl"))
            caps = {2: _designer_caps()}
            cfg = _full_config(market_enabled=False)
            router = RealWorkRouter(queue=queue, market=None, capabilities=caps, config=cfg)
            agent = _agent()
            out = router.maybe_dispatch(
                agent, activity="上午工作", chosen_action="设计落地页",
                sim_day=1, sim_time="10:00",
            )
            self.assertIsNotNone(out)
            self.assertIn("着手", out)
            self.assertEqual(1, queue.pending_count())
            brief = next(iter(queue.all_briefs()))
            self.assertEqual("html_landing", brief.deliverable)
            self.assertEqual("web_design", brief.adapter)
            self.assertIsNone(brief.market_job_id)

    def test_non_work_activity_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = WorkQueue(os.path.join(tmp, "q.jsonl"))
            caps = {2: _designer_caps()}
            router = RealWorkRouter(
                queue=queue, market=None, capabilities=caps,
                config=_full_config(market_enabled=False),
            )
            out = router.maybe_dispatch(
                _agent(), activity="吃午饭", chosen_action="点外卖",
                sim_day=1, sim_time="12:00",
            )
            self.assertIsNone(out)

    def test_no_capabilities_means_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = WorkQueue(os.path.join(tmp, "q.jsonl"))
            router = RealWorkRouter(
                queue=queue, market=None, capabilities={},
                config=_full_config(market_enabled=False),
            )
            out = router.maybe_dispatch(
                _agent(), activity="工作", chosen_action="设计",
                sim_day=1, sim_time="10:00",
            )
            self.assertIsNone(out)

    def test_in_flight_task_blocks_new_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = WorkQueue(os.path.join(tmp, "q.jsonl"))
            caps = {2: _designer_caps()}
            router = RealWorkRouter(
                queue=queue, market=None, capabilities=caps,
                config=_full_config(market_enabled=False),
            )
            agent = _agent()
            first = router.maybe_dispatch(
                agent, activity="工作", chosen_action="设计页面",
                sim_day=1, sim_time="10:00",
            )
            second = router.maybe_dispatch(
                agent, activity="工作", chosen_action="设计页面",
                sim_day=1, sim_time="10:30",
            )
            self.assertIsNotNone(first)
            self.assertIsNone(second)


class TestRouterPathB(unittest.TestCase):
    def test_market_dispatch_when_browse_p_is_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = WorkQueue(os.path.join(tmp, "q.jsonl"))
            market = JobMarket(
                store_path=os.path.join(tmp, "market.jsonl"),
                seed_path=_seed_path(tmp),
            )
            caps = {2: _designer_caps()}
            cfg = _full_config(market_enabled=True, browse_p=1.0)
            router = RealWorkRouter(queue=queue, market=market, capabilities=caps, config=cfg)
            agent = _agent()
            out = router.maybe_dispatch(
                agent, activity="工作", chosen_action="设计页面",
                sim_day=1, sim_time="10:00",
            )
            self.assertIsNotNone(out)
            self.assertIn("接单", out)
            briefs = list(queue.all_briefs())
            self.assertEqual(1, len(briefs))
            self.assertIsNotNone(briefs[0].market_job_id)
            taken_jobs = [j for j in market.all_jobs() if j.status == "taken"]
            self.assertEqual(1, len(taken_jobs))

    def test_doctor_only_job_never_taken_by_designer(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = list(_SEED)
            seed.append({
                "job_id": "mj_doctor_only",
                "title": "对照组",
                "description": "x",
                "deliverable": "md_article",
                "required_skills": ["x"],
                "required_job_labels": ["doctor"],
                "reward_econ": 0.5,
                "reward_text": "￥",
                "deadline_window_days": 5,
                "source_tag": "mock_seed_control",
            })
            seed_path = os.path.join(tmp, "seed.json")
            with open(seed_path, "w", encoding="utf-8") as f:
                json.dump(seed, f, ensure_ascii=False)
            queue = WorkQueue(os.path.join(tmp, "q.jsonl"))
            market = JobMarket(
                store_path=os.path.join(tmp, "market.jsonl"),
                seed_path=seed_path,
            )
            caps = {2: _designer_caps()}
            router = RealWorkRouter(
                queue=queue, market=market, capabilities=caps,
                config=_full_config(market_enabled=True, browse_p=1.0),
            )
            router.maybe_dispatch(
                _agent(), activity="工作", chosen_action="设计页面",
                sim_day=1, sim_time="10:00",
            )
            doctor_job = next(j for j in market.all_jobs() if j.job_id == "mj_doctor_only")
            self.assertEqual("open", doctor_job.status)


class TestIngestAbsorption(unittest.TestCase):
    def _populate(self, tmp: str, status: str = "ok") -> tuple[WorkQueue, JobMarket, dict]:
        queue = WorkQueue(os.path.join(tmp, "q.jsonl"))
        market = JobMarket(
            store_path=os.path.join(tmp, "market.jsonl"),
            seed_path=_seed_path(tmp),
        )
        caps = {2: _designer_caps()}
        router = RealWorkRouter(
            queue=queue, market=market, capabilities=caps,
            config=_full_config(market_enabled=True, browse_p=1.0),
        )
        agent = _agent()
        router.maybe_dispatch(
            agent, activity="工作", chosen_action="设计页面",
            sim_day=1, sim_time="10:00",
        )
        brief = queue.claim_next()
        assert brief is not None
        queue.record_result(WorkResult(
            task_id=brief.task_id, agent_id=2, status=status,  # type: ignore[arg-type]
            artifact_paths=["/tmp/art.svg"], summary="海报",
            error=None if status == "ok" else "boom",
        ))
        return queue, market, agent

    def test_success_settles_market_and_bumps_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue, market, agent = self._populate(tmp, status="ok")
            before_econ = agent["state"]["econ_security"]
            results = absorb_completed_for(
                agent, queue=queue, market=market,
                sim_day=1, sim_time="10:30", limit=5,
            )
            self.assertEqual(1, len(results))
            done = [j for j in market.all_jobs() if j.status == "done"]
            self.assertEqual(1, len(done))
            self.assertGreater(agent["state"]["econ_security"], before_econ)
            self.assertGreater(agent["state"]["emotion"], 0.6)
            self.assertEqual(1, len(agent["memory"]))

    def test_failure_settles_market_and_dings_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue, market, agent = self._populate(tmp, status="failed")
            before_emotion = agent["state"]["emotion"]
            absorb_completed_for(
                agent, queue=queue, market=market,
                sim_day=1, sim_time="10:30", limit=5,
            )
            failed_jobs = [j for j in market.all_jobs() if j.status == "failed"]
            self.assertEqual(1, len(failed_jobs))
            self.assertLess(agent["state"]["emotion"], before_emotion)

    def test_summarise_for_outcome_is_compact(self):
        rs = [
            WorkResult(task_id="wt_1", agent_id=2, status="ok", summary="海报"),
            WorkResult(task_id="wt_2", agent_id=2, status="failed", error="bad"),
        ]
        s = summarise_for_outcome(rs)
        self.assertIn("海报", s)
        self.assertIn("失败", s)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
