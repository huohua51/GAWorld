"""Tests for gaworld.work schemas and the WorkQueue persistence layer."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from gaworld.work.queue import WorkQueue
from gaworld.work.schemas import (
    AgentCapabilities,
    MarketJob,
    WorkBrief,
    WorkResult,
)


def _sample_brief(task_id: str = "wt_1", agent_id: int = 1) -> WorkBrief:
    return WorkBrief(
        task_id=task_id,
        agent_id=agent_id,
        sim_day=1,
        sim_time="09:30",
        activity="工作",
        chosen_action="设计首页",
        deliverable="html_landing",
        adapter="web_design",
        brief_text="【任务】demo",
        estimated_minutes=30,
        submitted_at=1.0,
    )


class TestSchemaRoundTrip(unittest.TestCase):
    def test_brief_round_trip(self):
        brief = _sample_brief()
        recovered = WorkBrief.from_dict(brief.to_dict())
        self.assertEqual(brief, recovered)

    def test_brief_spec_version_defaults_to_v1(self):
        payload = _sample_brief().to_dict()
        payload.pop("spec_version", None)
        recovered = WorkBrief.from_dict(payload)
        self.assertEqual("v1", recovered.spec_version)

    def test_result_round_trip(self):
        r = WorkResult(
            task_id="wt_1", agent_id=1, status="ok",
            artifact_paths=["a.html"], summary="done",
            error=None, finished_at=2.0, duration_seconds=1.0,
        )
        self.assertEqual(r, WorkResult.from_dict(r.to_dict()))

    def test_market_job_round_trip(self):
        job = MarketJob(
            job_id="mj_1", title="t", description="d",
            deliverable="md_article",
            required_skills=["写作"], required_job_labels=["content_creator"],
            reward_econ=0.1, reward_text="￥500",
            posted_sim_day=1, deadline_sim_day=4,
        )
        self.assertEqual(job, MarketJob.from_dict(job.to_dict()))

    def test_capabilities_round_trip(self):
        caps = AgentCapabilities(
            agent_id=2, job_label="ui_designer",
            skills=["排版"], interests=["插画"],
            deliverables=["html_landing"], adapter_priority=["web_design"],
            notes="x", source_hash="abc",
        )
        self.assertEqual(caps, AgentCapabilities.from_dict(caps.to_dict()))


class TestWorkQueue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "queue.jsonl")

    def test_submit_then_claim(self):
        q = WorkQueue(self.path)
        q.submit(_sample_brief("wt_1"))
        q.submit(_sample_brief("wt_2"))
        self.assertEqual(2, q.pending_count())
        first = q.claim_next()
        self.assertIsNotNone(first)
        self.assertEqual("wt_1", first.task_id)  # type: ignore[union-attr]
        self.assertEqual(1, q.pending_count())

    def test_record_result_marks_done(self):
        q = WorkQueue(self.path)
        q.submit(_sample_brief("wt_1"))
        q.claim_next()
        q.record_result(WorkResult(
            task_id="wt_1", agent_id=1, status="ok",
            artifact_paths=["a"], summary="ok",
        ))
        self.assertEqual("done", q.status_of("wt_1"))

    def test_drain_completed_for_returns_once(self):
        q = WorkQueue(self.path)
        q.submit(_sample_brief("wt_1"))
        q.claim_next()
        q.record_result(WorkResult(
            task_id="wt_1", agent_id=1, status="ok",
            artifact_paths=["a"], summary="ok",
        ))
        first = q.drain_completed_for(1)
        self.assertEqual(1, len(first))
        # Already drained.
        again = q.drain_completed_for(1)
        self.assertEqual(0, len(again))

    def test_has_unfinished_for(self):
        q = WorkQueue(self.path)
        self.assertFalse(q.has_unfinished_for(1))
        q.submit(_sample_brief("wt_1", agent_id=1))
        self.assertTrue(q.has_unfinished_for(1))
        self.assertFalse(q.has_unfinished_for(2))

    def test_crash_recovery_replays_jsonl(self):
        q = WorkQueue(self.path)
        q.submit(_sample_brief("wt_1"))
        q.claim_next()
        q.record_result(WorkResult(
            task_id="wt_1", agent_id=1, status="ok",
            artifact_paths=["a"], summary="ok",
        ))
        # Re-instantiate over the same file.
        q2 = WorkQueue(self.path)
        self.assertEqual("done", q2.status_of("wt_1"))

    def test_malformed_line_is_skipped(self):
        q = WorkQueue(self.path)
        q.submit(_sample_brief("wt_1"))
        # Append a corrupt line manually.
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("not-json{\n")
            f.write(json.dumps({"event": "submit", "brief": _sample_brief("wt_2").to_dict()}) + "\n")
        q2 = WorkQueue(self.path)
        # wt_1 and wt_2 should both load despite the corrupt line.
        statuses = {q2.status_of("wt_1"), q2.status_of("wt_2")}
        self.assertIn("pending", statuses)

    def test_revise_pending_updates_brief_and_version(self):
        q = WorkQueue(self.path)
        q.submit(_sample_brief("wt_1"))
        out = q.revise("wt_1", brief_text="【任务】v2", spec_version="v2")
        self.assertTrue(out["ok"])
        brief = q.get_brief("wt_1")
        self.assertEqual("v2", brief.spec_version)
        self.assertEqual("【任务】v2", brief.brief_text)
        claimed = q.claim_next()
        self.assertEqual("v2", claimed.spec_version)

    def test_revise_after_claim_updates_running_brief(self):
        q = WorkQueue(self.path)
        q.submit(_sample_brief("wt_1"))
        claimed = q.claim_next()
        self.assertEqual("v1", claimed.spec_version)
        out = q.revise("wt_1", brief_text="【任务】v2", spec_version="v2")
        self.assertTrue(out["ok"])
        self.assertEqual("v2", q.get_brief("wt_1").spec_version)

    def test_revise_after_result_is_rejected(self):
        q = WorkQueue(self.path)
        q.submit(_sample_brief("wt_1"))
        q.claim_next()
        q.record_result(WorkResult(
            task_id="wt_1", agent_id=1, status="ok",
            artifact_paths=["a"], summary="ok",
        ))
        out = q.revise("wt_1", brief_text="【任务】v2", spec_version="v2")
        self.assertFalse(out["ok"])
        self.assertEqual("not_revisable", out["reason"])
        self.assertEqual("v1", q.get_brief("wt_1").spec_version)

    def test_revise_replays_from_jsonl(self):
        q = WorkQueue(self.path)
        q.submit(_sample_brief("wt_1"))
        q.revise("wt_1", brief_text="【任务】v2", spec_version="v2")
        q2 = WorkQueue(self.path)
        self.assertEqual("v2", q2.get_brief("wt_1").spec_version)

    def test_worker_re_reads_brief_after_running_revise(self):
        from gaworld.work.adapters.base import AdapterContext
        from gaworld.work.worker import WorkerPool

        q = WorkQueue(self.path)
        q.submit(_sample_brief("wt_1"))
        claimed = q.claim_next()
        self.assertEqual("v1", claimed.spec_version)
        q.revise("wt_1", brief_text="【任务】v2", spec_version="v2")
        pool = WorkerPool(
            queue=q,
            adapters={},
            ctx_factory=lambda _n: AdapterContext(artifacts_root=self.tmp, llm=lambda _p: "", config={}),
        )
        latest = pool._latest_brief(claimed)
        self.assertEqual("v2", latest.spec_version)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
