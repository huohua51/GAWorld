"""Deterministic mock for :func:`llm_providers.call_llm`.

Why this exists
---------------
End-to-end tests that exercise :func:`generative_city_sim.run_simulation`
need a controllable substitute for the LLM. The substitute must:

* Be **deterministic**: the same inputs produce the same outputs across
  runs and Python versions.
* Be **shape-correct**: respond in the format the simulator expects
  for each ``task`` it dispatches (schedule, planning, reflection,
  daily diary, intervention text, etc.). The simulator's parsers fall
  back to heuristics on malformed responses, so this only needs to be
  good enough to keep the parsers happy.
* Be **patchable**: tests should be able to drop in a custom response
  per task without rewriting the simulator wiring.

Usage
-----

>>> from tests.fixtures.mock_llm import MockLLM, install
>>> mock = MockLLM()
>>> with install(mock):
...     run_simulation_or_whatever()

By default the mock uses task-specific canned responses; tests can
override them with :meth:`MockLLM.set_response`.
"""

from __future__ import annotations

import contextlib
import json
import threading
from typing import Any, Callable, Iterator


# Default canned responses keyed by ``task`` name. Each value is the
# raw string the LLM router would have returned. Parsers in
# ``generative_city_sim`` are forgiving — these payloads only need to
# satisfy whatever format check the parser performs.
DEFAULT_RESPONSES: dict[str, str] = {
    # JSON schedule for the day. Parser tolerates both list-of-pairs
    # and list-of-dicts; we use the dict form for clarity.
    "schedule": json.dumps(
        [
            {"time": "07:00", "activity": "起床洗漱"},
            {"time": "08:00", "activity": "通勤"},
            {"time": "09:00", "activity": "工作"},
            {"time": "12:00", "activity": "午餐"},
            {"time": "13:30", "activity": "工作"},
            {"time": "18:00", "activity": "下班通勤"},
            {"time": "19:00", "activity": "晚餐"},
            {"time": "21:00", "activity": "休闲"},
            {"time": "23:00", "activity": "睡觉"},
        ],
        ensure_ascii=False,
    ),
    "daily_routine": json.dumps(
        [
            {"time": "07:30", "activity": "起床洗漱"},
            {"time": "08:30", "activity": "通勤"},
            {"time": "09:30", "activity": "工作"},
            {"time": "12:30", "activity": "午餐"},
            {"time": "14:00", "activity": "工作"},
            {"time": "18:30", "activity": "晚餐"},
            {"time": "20:00", "activity": "阅读"},
            {"time": "22:30", "activity": "睡觉"},
        ],
        ensure_ascii=False,
    ),
    "actions": json.dumps(
        {
            "工作": ["写代码", "开会", "整理文档"],
            "通勤": ["乘地铁", "步行"],
            "午餐": ["吃食堂", "外卖"],
            "晚餐": ["回家做饭", "下馆子"],
            "休闲": ["看书", "散步"],
            "阅读": ["看小说", "看技术文章"],
            "睡觉": ["睡觉"],
            "起床洗漱": ["洗漱", "穿衣"],
            "下班通勤": ["乘地铁", "步行"],
        },
        ensure_ascii=False,
    ),
    "location_actions": json.dumps(
        {
            "Office": ["写代码", "开会"],
            "Home": ["看书", "做饭"],
        },
        ensure_ascii=False,
    ),
    "perception": "今天感觉一切如常，没有特别的事情发生。",
    "planning": json.dumps(
        {
            "plan": "继续按计划完成今天的工作，留出时间处理邮件。",
            "alternative": "如果时间允许，下午可以去咖啡馆放松一下。",
        },
        ensure_ascii=False,
    ),
    "reflection": json.dumps(
        {
            "summary": "今天的工作进展顺利，整体平静。",
            "lesson": "保持稳定的节奏比追求高峰更可持续。",
        },
        ensure_ascii=False,
    ),
    "daily_diary": (
        "## 今天主要发生的事情\n"
        "正常上班，处理了几封邮件，开了一个短会。\n\n"
        "## 今天的感想\n"
        "整体平稳，没有特别的波动。\n\n"
        "## 明天的计划\n"
        "继续推进手头的项目，争取早点回家。"
    ),
    "summary": "近期生活节奏平稳，工作与休息平衡良好。",
    "interview": "我今天的选择主要基于既定的日程安排和当下的精力状态。",
    "memory_review": "近期模式：稳定的工作节奏与适度的社交。",
    "memory_consolidation": json.dumps(
        {
            "summary": "今天的记忆整合稳定。",
            "priorities": ["保持工作节奏", "晚上早点休息"],
            "avoidances": ["熬夜"],
            "target_social": "和朋友保持基本联系",
            "target_recovery": "早点入睡",
        },
        ensure_ascii=False,
    ),
    "daily_intentions": json.dumps(
        {
            "priorities": ["专注工作", "保证休息"],
            "avoidances": ["拖延"],
            "target_social": "回复一条消息",
            "target_recovery": "晚饭后散步",
        },
        ensure_ascii=False,
    ),
    "routine_change": json.dumps(
        {"change": False, "reason": "状态平稳，按计划执行。"},
        ensure_ascii=False,
    ),
    "event_effect": json.dumps(
        {"impact": "neutral", "summary": "事件对我的影响有限。"},
        ensure_ascii=False,
    ),
    "external_environment": json.dumps(
        {
            "day_events": [
                {
                    "type": "weather",
                    "topic": "weather",
                    "name": "晴",
                    "description": "今日天气晴朗，气温适宜。",
                    "severity": 0.2,
                }
            ],
            "summary": "今日外部环境总体平稳。",
        },
        ensure_ascii=False,
    ),
    "external_rag_bootstrap": json.dumps(
        [
            {"text": "用户日常通勤距离较短", "source": "profile"},
            {"text": "近期对城市生活有一些观察", "source": "profile"},
        ],
        ensure_ascii=False,
    ),
    "info_seek_reaction": "对这条信息无特别反应，保持中性看法。",
    "web_search_reaction": "了解到一些背景信息，对今天的决定影响有限。",
    "news_reaction": "看完后心情没有明显波动。",
    "social_profile": json.dumps(
        {
            "name": "测试用户",
            "personality": "稳定温和",
            "daily_life": "通勤工作为主",
        },
        ensure_ascii=False,
    ),
    "diary_import_summary": "这是一段稳定的日常记录。",
    "weekend_routine": json.dumps(
        [
            {"time": "09:00", "activity": "起床"},
            {"time": "10:00", "activity": "买菜"},
            {"time": "12:00", "activity": "午餐"},
            {"time": "14:00", "activity": "看书"},
            {"time": "18:00", "activity": "晚餐"},
            {"time": "22:00", "activity": "睡觉"},
        ],
        ensure_ascii=False,
    ),
}

# Used when the simulator dispatches a task we haven't seen before.
GENERIC_RESPONSE = "ok"


class MockLLM:
    """Deterministic stand-in for :func:`llm_providers.call_llm`.

    Records every call so tests can assert what prompts were dispatched
    without standing up a real provider.
    """

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self._responses: dict[str, str] = dict(DEFAULT_RESPONSES)
        if responses:
            self._responses.update(responses)
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_response(self, task: str, response: str) -> None:
        """Override the response for a single ``task`` name."""
        with self._lock:
            self._responses[task] = response

    def set_handler(self, task: str, handler: Callable[[str, Any], str]) -> None:
        """Install a callable that computes the response per call.

        The handler receives the prompt and ``agent_id`` and must
        return a string. Useful when a test wants to assert on prompt
        contents.
        """
        with self._lock:
            self._responses[task] = handler  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def call_count(self, task: str | None = None) -> int:
        with self._lock:
            if task is None:
                return len(self.calls)
            return sum(1 for entry in self.calls if entry.get("task") == task)

    def tasks_seen(self) -> list[str]:
        with self._lock:
            return sorted({entry.get("task") or "" for entry in self.calls})

    # ------------------------------------------------------------------
    # The actual stub
    # ------------------------------------------------------------------

    def __call__(self, prompt: str, task: str | None = None, agent_id: Any = None) -> str:
        with self._lock:
            self.calls.append(
                {"prompt": prompt, "task": task or "", "agent_id": agent_id}
            )
            response = self._responses.get(task or "", GENERIC_RESPONSE)
        if callable(response):
            return str(response(prompt, agent_id))
        return str(response)


@contextlib.contextmanager
def install(mock: MockLLM | None = None) -> Iterator[MockLLM]:
    """Patch ``llm_providers.call_llm`` and ``generative_city_sim.call_llm``.

    The simulator imports ``call_llm`` into its own module namespace,
    so we have to patch both bindings to make the substitution
    universal.
    """
    import llm_providers

    real_mock = mock if mock is not None else MockLLM()
    original_router = llm_providers.call_llm
    llm_providers.call_llm = real_mock  # type: ignore[assignment]

    # Patch the legacy module binding too if it has been imported.
    legacy = None
    try:
        import generative_city_sim as legacy_mod  # noqa: F401
        legacy = legacy_mod
    except Exception:  # noqa: BLE001 — sandbox may lack heavy deps
        legacy = None
    original_legacy = None
    if legacy is not None and hasattr(legacy, "call_llm"):
        original_legacy = legacy.call_llm
        legacy.call_llm = real_mock  # type: ignore[assignment]

    try:
        yield real_mock
    finally:
        llm_providers.call_llm = original_router  # type: ignore[assignment]
        if legacy is not None and original_legacy is not None:
            legacy.call_llm = original_legacy  # type: ignore[assignment]


__all__ = ["DEFAULT_RESPONSES", "GENERIC_RESPONSE", "MockLLM", "install"]
