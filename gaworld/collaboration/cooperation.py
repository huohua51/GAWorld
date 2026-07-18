from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from gaworld.collaboration.models import SessionEvent, SessionStatus
from gaworld.collaboration.store import SessionStore


class CooperationRunner:
    def __init__(
        self,
        *,
        store: SessionStore,
        agent_loader: Callable[[int], dict[str, Any] | None],
        llm: Callable[..., str],
        episode_writer: Callable[[int, dict[str, Any]], None] | None = None,
        max_context_events: int = 24,
        step_retries: int = 2,
    ) -> None:
        self.store = store
        self.agent_loader = agent_loader
        self.llm = llm
        self.episode_writer = episode_writer or (lambda agent_id, episode: None)
        self.max_context_events = max(1, int(max_context_events))
        self.step_retries = max(0, int(step_retries))

    def _call(self, prompt: str, *, task: str, agent_id: int | None = None) -> str:
        last_error: Exception | None = None
        for _attempt in range(self.step_retries + 1):
            try:
                return str(self.llm(prompt, task=task, agent_id=agent_id)).strip()
            except Exception as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    @staticmethod
    def _json(raw: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _safe_filename(value: Any, fallback: str) -> str:
        filename = str(value or fallback).strip()
        return filename if filename and Path(filename).name == filename else fallback

    def _capabilities(self, member_ids: list[int]) -> list[dict[str, Any]]:
        table = []
        for agent_id in member_ids:
            detail = self.agent_loader(agent_id) or {}
            table.append(
                {
                    "agent_id": agent_id,
                    "identity": detail.get("identity", detail),
                    "capabilities": detail.get("capabilities", {}),
                    "private_skills": detail.get("private_skills", []),
                    "growth": detail.get("growth", {}),
                    "cognition": detail.get("cognition", {}),
                }
            )
        return table

    def _fallback_plan(self, member_ids: list[int]) -> dict[str, Any]:
        return {
            "leader_id": member_ids[0],
            "roles": {
                str(agent_id): f"成员{index}"
                for index, agent_id in enumerate(member_ids, start=1)
            },
            "steps": [
                {
                    "title": f"完成成员 {agent_id} 的子任务",
                    "agent_id": agent_id,
                    "artifact": f"member_{agent_id}.md",
                }
                for agent_id in member_ids
            ],
        }

    def _normalized_plan(self, raw: str, member_ids: list[int]) -> dict[str, Any]:
        payload = self._json(raw)
        fallback = self._fallback_plan(member_ids)
        try:
            leader_id = int(payload.get("leader_id", fallback["leader_id"]))
        except (TypeError, ValueError):
            leader_id = int(fallback["leader_id"])
        if leader_id not in member_ids:
            leader_id = int(fallback["leader_id"])
        incoming_roles = payload.get("roles")
        roles = dict(fallback["roles"])
        if isinstance(incoming_roles, dict):
            for agent_id in member_ids:
                value = str(incoming_roles.get(str(agent_id), "")).strip()
                if value:
                    roles[str(agent_id)] = value
        steps = []
        incoming_steps = payload.get("steps")
        if isinstance(incoming_steps, list):
            for index, item in enumerate(incoming_steps, start=1):
                if not isinstance(item, dict):
                    continue
                try:
                    agent_id = int(item.get("agent_id", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if agent_id not in member_ids:
                    continue
                steps.append(
                    {
                        "title": str(item.get("title") or f"子任务 {index}").strip(),
                        "agent_id": agent_id,
                        "artifact": self._safe_filename(
                            item.get("artifact"),
                            f"member_{agent_id}_{index}.md",
                        ),
                        "status": "pending",
                    }
                )
        if not steps:
            steps = [dict(item, status="pending") for item in fallback["steps"]]
        return {"leader_id": leader_id, "roles": roles, "steps": steps}

    @staticmethod
    def _step_event(
        events: list[SessionEvent],
        event_type: str,
        step_index: int,
    ) -> SessionEvent | None:
        return next(
            (
                event
                for event in events
                if event.type == event_type
                and event.metadata.get("step_index") == step_index
            ),
            None,
        )

    def _artifact_text(self, session_id: str, event: SessionEvent) -> str:
        relative = str(event.metadata.get("path") or "")
        if not relative:
            return ""
        return (self.store.root / session_id / relative).read_text(encoding="utf-8")

    def _fail(self, session_id: str, exc: Exception) -> None:
        with self.store.session_guard(session_id):
            session = self.store.get(session_id)
            if session.status is SessionStatus.COMPLETED:
                if session.error:
                    session.error = ""
                    self.store.save(session)
                return
            session.error = str(exc)[:500]
            if session.status is SessionStatus.RUNNING:
                session.transition(SessionStatus.FAILED)
            self.store.save(session)
            self.store.append_event(session_id, "error", session.error)

    def _finalize(self, session_id: str) -> None:
        with self.store.session_guard(session_id):
            session = self.store.get(session_id)
            if session.status is not SessionStatus.RUNNING:
                return
            events = self.store.events(session_id)
            completed_episodes = {
                event.metadata.get("agent_id")
                for event in events
                if event.type == "side_effect_completed"
                and event.metadata.get("effect") == "episode"
            }
            episode = {
                "source": "collaboration",
                "session_id": session_id,
                "kind": "cooperation",
                "summary": session.task,
                "artifact": "final.md",
                "salience": 0.75,
            }
            for agent_id in session.member_ids:
                if agent_id in completed_episodes:
                    continue
                self.episode_writer(agent_id, dict(episode))
                self.store.append_event(
                    session_id,
                    "side_effect_completed",
                    "合作经历已写入",
                    agent_id=agent_id,
                    metadata={"effect": "episode", "agent_id": agent_id},
                )
                if self.store.get(session_id).status is not SessionStatus.RUNNING:
                    return
            events = self.store.events(session_id)
            if not any(event.type == "completed" for event in events):
                self.store.append_event(session_id, "completed", "合作任务已完成")
            latest = self.store.get(session_id)
            latest.transition(SessionStatus.COMPLETED)
            self.store.save(latest)

    def _start(self, session_id: str) -> bool:
        with self.store.session_guard(session_id):
            self.store.get(session_id)
            session = self.store.get(session_id)
            if session.status in {
                SessionStatus.QUEUED,
                SessionStatus.FAILED,
                SessionStatus.INTERRUPTED,
            }:
                session.transition(SessionStatus.RUNNING)
                session.error = ""
                self.store.save(session)
            elif session.status is not SessionStatus.RUNNING:
                return False
            if not any(
                event.type == "started" for event in self.store.events(session_id)
            ):
                self.store.append_event(session_id, "started", "合作任务开始")
            return True

    def _create_plan(self, session_id: str) -> bool:
        session = self.store.get(session_id)
        if session.plan:
            return session.status is SessionStatus.RUNNING
        plan_raw = self._call(
            json.dumps(
                {
                    "task": session.task,
                    "members": self._capabilities(session.member_ids),
                    "instruction": (
                        "输出 JSON：leader_id、roles 对象、steps 数组。"
                        "每个 step 包含 title、agent_id、artifact。"
                    ),
                },
                ensure_ascii=False,
            ),
            task="collaboration_plan",
        )
        plan = self._normalized_plan(plan_raw, session.member_ids)
        with self.store.session_guard(session_id):
            latest = self.store.get(session_id)
            if latest.plan:
                return latest.status is SessionStatus.RUNNING
            if latest.status is SessionStatus.CANCELLED:
                return False
            if latest.status not in {SessionStatus.RUNNING, SessionStatus.PAUSED}:
                return False
            latest.leader_id = (
                latest.leader_id
                if latest.leader_id in latest.member_ids
                else plan["leader_id"]
            )
            latest.roles = dict(plan["roles"])
            latest.roles.update(
                {
                    str(agent_id): str(role)
                    for agent_id, role in latest.role_overrides.items()
                    if str(agent_id) in latest.roles and str(role).strip()
                }
            )
            latest.plan = list(plan["steps"])
            self.store.save(latest)
            events = self.store.events(session_id)
            if not any(event.type == "role_assigned" for event in events):
                self.store.append_event(
                    session_id,
                    "role_assigned",
                    "团队角色已确定",
                    metadata={
                        "leader_id": latest.leader_id,
                        "roles": latest.roles,
                    },
                )
            if not any(event.type == "plan_created" for event in events):
                self.store.append_event(
                    session_id,
                    "plan_created",
                    "团队计划已生成",
                    metadata={"plan": latest.plan},
                )
            return latest.status is SessionStatus.RUNNING

    def _execute_step(self, session_id: str, step_index: int) -> bool:
        session = self.store.get(session_id)
        step = session.plan[step_index]
        author_id = int(step["agent_id"])
        events = self.store.events(session_id)
        artifact_event = self._step_event(events, "artifact", step_index)
        if artifact_event is None:
            delivery = self._call(
                json.dumps(
                    {
                        "task": session.task,
                        "role": session.roles.get(str(author_id), ""),
                        "step": step,
                        "instruction": "完成该子任务并输出可直接保存的 Markdown。",
                    },
                    ensure_ascii=False,
                ),
                task="collaboration_execute",
                agent_id=author_id,
            )
            with self.store.session_guard(session_id):
                latest = self.store.get(session_id)
                artifact_event = self._step_event(
                    self.store.events(session_id),
                    "artifact",
                    step_index,
                )
                if artifact_event is None:
                    if latest.status is SessionStatus.CANCELLED:
                        return False
                    if latest.status not in {
                        SessionStatus.RUNNING,
                        SessionStatus.PAUSED,
                    }:
                        return False
                    artifact = self.store.write_artifact(
                        session_id,
                        str(step["artifact"]),
                        delivery,
                        agent_id=author_id,
                    )
                    metadata = dict(artifact)
                    metadata["step_index"] = step_index
                    artifact_event = self.store.append_event(
                        session_id,
                        "artifact",
                        artifact["filename"],
                        agent_id=author_id,
                        metadata=metadata,
                    )
                status = self.store.get(session_id).status
            if status is not SessionStatus.RUNNING:
                return False
        assert artifact_event is not None
        delivery = self._artifact_text(session_id, artifact_event)

        events = self.store.events(session_id)
        review_event = self._step_event(events, "review", step_index)
        if review_event is None:
            reviewer_id = next(
                member_id for member_id in session.member_ids if member_id != author_id
            )
            review_raw = self._call(
                json.dumps(
                    {
                        "task": session.task,
                        "artifact": delivery,
                        "instruction": "输出 JSON：approved 布尔值与 feedback 字符串。",
                    },
                    ensure_ascii=False,
                ),
                task="collaboration_review",
                agent_id=reviewer_id,
            )
            review = self._json(review_raw)
            approved = review.get("approved") is True
            feedback = str(review.get("feedback") or review_raw).strip()
            with self.store.session_guard(session_id):
                latest = self.store.get(session_id)
                review_event = self._step_event(
                    self.store.events(session_id),
                    "review",
                    step_index,
                )
                if review_event is None:
                    if latest.status is SessionStatus.CANCELLED:
                        return False
                    if latest.status not in {
                        SessionStatus.RUNNING,
                        SessionStatus.PAUSED,
                    }:
                        return False
                    review_event = self.store.append_event(
                        session_id,
                        "review",
                        feedback,
                        agent_id=reviewer_id,
                        metadata={
                            "approved": approved,
                            "artifact": artifact_event.content,
                            "step_index": step_index,
                        },
                    )
                status = self.store.get(session_id).status
            if status is not SessionStatus.RUNNING:
                return False
        assert review_event is not None
        approved = review_event.metadata.get("approved") is True
        feedback = review_event.content

        revision_event = self._step_event(
            self.store.events(session_id),
            "revision",
            step_index,
        )
        if not approved and revision_event is None:
            revised = self._call(
                json.dumps(
                    {
                        "task": session.task,
                        "artifact": delivery,
                        "feedback": feedback,
                        "instruction": "根据审阅意见修订并输出完整 Markdown。",
                    },
                    ensure_ascii=False,
                ),
                task="collaboration_revision",
                agent_id=author_id,
            )
            with self.store.session_guard(session_id):
                latest = self.store.get(session_id)
                revision_event = self._step_event(
                    self.store.events(session_id),
                    "revision",
                    step_index,
                )
                if revision_event is None:
                    if latest.status is SessionStatus.CANCELLED:
                        return False
                    if latest.status not in {
                        SessionStatus.RUNNING,
                        SessionStatus.PAUSED,
                    }:
                        return False
                    self.store.write_artifact(
                        session_id,
                        artifact_event.content,
                        revised,
                        agent_id=author_id,
                    )
                    self.store.append_event(
                        session_id,
                        "revision",
                        artifact_event.content,
                        agent_id=author_id,
                        metadata={
                            "artifact": artifact_event.content,
                            "step_index": step_index,
                        },
                    )
                status = self.store.get(session_id).status
            if status is not SessionStatus.RUNNING:
                return False

        with self.store.session_guard(session_id):
            latest = self.store.get(session_id)
            if latest.status is SessionStatus.CANCELLED:
                return False
            if latest.status not in {SessionStatus.RUNNING, SessionStatus.PAUSED}:
                return False
            if latest.current_step == step_index:
                latest.plan[step_index]["status"] = "completed"
                latest.current_step += 1
                self.store.save(latest)
            status = self.store.get(session_id).status
        return status is SessionStatus.RUNNING

    def _synthesize(self, session_id: str) -> bool:
        session = self.store.get(session_id)
        final_event = next(
            (
                event
                for event in self.store.events(session_id)
                if event.type == "artifact" and event.metadata.get("final") is True
            ),
            None,
        )
        if final_event is None:
            final_text = self._call(
                json.dumps(
                    {
                        "task": session.task,
                        "plan": session.plan,
                        "artifacts": session.artifacts,
                        "instruction": "汇总团队成果，输出完整最终 Markdown。",
                    },
                    ensure_ascii=False,
                ),
                task="collaboration_synthesis",
                agent_id=session.leader_id,
            )
            with self.store.session_guard(session_id):
                final_event = next(
                    (
                        event
                        for event in self.store.events(session_id)
                        if event.type == "artifact"
                        and event.metadata.get("final") is True
                    ),
                    None,
                )
                latest = self.store.get(session_id)
                if final_event is None:
                    if latest.status is SessionStatus.CANCELLED:
                        return False
                    if latest.status not in {
                        SessionStatus.RUNNING,
                        SessionStatus.PAUSED,
                    }:
                        return False
                    final = self.store.write_artifact(
                        session_id,
                        "final.md",
                        final_text,
                        agent_id=latest.leader_id,
                    )
                    metadata = dict(final)
                    metadata["final"] = True
                    self.store.append_event(
                        session_id,
                        "artifact",
                        final["filename"],
                        agent_id=latest.leader_id,
                        metadata=metadata,
                    )
                status = self.store.get(session_id).status
            return status is SessionStatus.RUNNING
        return session.status is SessionStatus.RUNNING

    def run(self, session_id: str) -> None:
        if not self._start(session_id):
            return
        try:
            if not self._create_plan(session_id):
                return
            while True:
                session = self.store.get(session_id)
                if session.status is not SessionStatus.RUNNING:
                    return
                if session.current_step >= len(session.plan):
                    break
                if not self._execute_step(session_id, session.current_step):
                    return
            if not self._synthesize(session_id):
                return
            self._finalize(session_id)
        except Exception as exc:
            self._fail(session_id, exc)
