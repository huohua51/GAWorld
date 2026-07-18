from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from gaworld.collaboration.models import SessionStatus
from gaworld.collaboration.store import SessionStore


_FALLBACK_MESSAGE = "本轮未生成有效发言。"
_FALLBACK_SUMMARY = "讨论已完成，暂无可用摘要。"


class DiscussionRunner:
    def __init__(
        self,
        *,
        store: SessionStore,
        agent_loader: Callable[[int], dict[str, Any] | None],
        llm: Callable[..., str],
        episode_writer: Callable[[int, dict[str, Any]], None] | None = None,
        interaction_writer: Callable[[list[int]], None] | None = None,
        max_context_events: int = 24,
        step_retries: int = 2,
    ) -> None:
        self.store = store
        self.agent_loader = agent_loader
        self.llm = llm
        self.episode_writer = episode_writer or (lambda agent_id, episode: None)
        self.interaction_writer = interaction_writer or (lambda agent_ids: None)
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
    def _response(raw: str) -> tuple[str, bool]:
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            text = raw.strip()
            return (text or _FALLBACK_MESSAGE), False
        if isinstance(payload, dict):
            content = str(payload.get("content") or "").strip()
            converged = bool(payload.get("converged", False))
            if content:
                return content, converged
        return _FALLBACK_MESSAGE, False

    def _prompt(self, session_id: str, speaker_id: int) -> str:
        session = self.store.get(session_id)
        detail = self.agent_loader(speaker_id) or {}
        recent = [
            {
                "agent_id": event.agent_id,
                "content": event.content,
            }
            for event in self.store.events(session_id)
            if event.type == "message"
        ][-self.max_context_events :]
        context = {
            "speaker": {
                "identity": detail.get("identity", detail),
                "profile_text": detail.get("profile_text", ""),
                "capabilities": detail.get("capabilities", {}),
            },
            "topic": session.topic or "自由选择一个成员们自然感兴趣的话题",
            "recent_messages": recent,
            "instruction": (
                "以该居民自身视角自然回应。输出 JSON，字段 content 为本轮发言，"
                "converged 表示讨论是否已形成足够明确的结论。"
            ),
        }
        return json.dumps(context, ensure_ascii=False)

    def _fail(self, session_id: str, exc: Exception) -> None:
        session = self.store.get(session_id)
        session.error = str(exc)[:500]
        if session.status is SessionStatus.RUNNING:
            session.transition(SessionStatus.FAILED)
        self.store.save(session)
        self.store.append_event(session_id, "error", session.error)

    def run(self, session_id: str) -> None:
        session = self.store.get(session_id)
        if session.status in {
            SessionStatus.QUEUED,
            SessionStatus.FAILED,
            SessionStatus.INTERRUPTED,
        }:
            session.transition(SessionStatus.RUNNING)
            session.error = ""
            self.store.save(session)
            self.store.append_event(session_id, "started", "讨论开始")
        elif session.status is not SessionStatus.RUNNING:
            return

        converged = False
        try:
            while True:
                session = self.store.get(session_id)
                if session.status is not SessionStatus.RUNNING:
                    return
                if session.current_round >= session.max_rounds:
                    break
                speaker_id = session.member_ids[
                    session.current_round % len(session.member_ids)
                ]
                raw = self._call(
                    self._prompt(session_id, speaker_id),
                    task="collaboration_discussion",
                    agent_id=speaker_id,
                )
                after_call = self.store.get(session_id)
                if after_call.status is SessionStatus.CANCELLED:
                    return
                if after_call.status not in {
                    SessionStatus.RUNNING,
                    SessionStatus.PAUSED,
                }:
                    return
                content, convergence_signal = self._response(raw)
                self.store.append_event(
                    session_id,
                    "message",
                    content,
                    agent_id=speaker_id,
                    metadata={"round": session.current_round + 1},
                )
                latest = self.store.get(session_id)
                latest.current_round += 1
                self.store.save(latest)
                converged = (
                    convergence_signal
                    and latest.current_round >= len(latest.member_ids)
                )
                if latest.status is not SessionStatus.RUNNING:
                    return
                if converged:
                    break

            transcript = [
                {
                    "agent_id": event.agent_id,
                    "content": event.content,
                }
                for event in self.store.events(session_id)
                if event.type == "message"
            ]
            summary = self._call(
                json.dumps(
                    {"topic": session.topic, "transcript": transcript},
                    ensure_ascii=False,
                ),
                task="collaboration_discussion_summary",
            )
            summary = summary or _FALLBACK_SUMMARY
            self.store.append_event(session_id, "summary", summary)
            latest = self.store.get(session_id)
            if latest.status is not SessionStatus.RUNNING:
                return
            latest.transition(SessionStatus.COMPLETED)
            self.store.save(latest)
            self.store.append_event(
                session_id,
                "completed",
                summary,
                metadata={"converged": converged},
            )
            for agent_id in latest.member_ids:
                self.episode_writer(
                    agent_id,
                    {
                        "source": "collaboration",
                        "session_id": session_id,
                        "kind": "discussion",
                        "summary": summary,
                        "salience": 0.65,
                    },
                )
            self.interaction_writer(latest.member_ids)
        except Exception as exc:
            self._fail(session_id, exc)
