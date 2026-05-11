"""TeachingAdapter — produce a lesson plan or research note."""

from __future__ import annotations

import os
import re
import time

from gaworld.logging_setup import get_logger
from gaworld.work.adapters.base import AdapterContext, make_failed, make_ok
from gaworld.work.schemas import WorkBrief, WorkResult

_LOG = get_logger("gaworld.work.adapters.teaching")


_LESSON_PROMPT = """你是一名一线教师。请输出一份 Markdown 课时教案，结构包含：
- # 课题标题
- ## 教学目标（3 条）
- ## 教学过程（含活动设计、互动提示、时长分配）
- ## 板书要点
- ## 作业 / 变式题（≥3 题）

【教师】{name}（{job}）
【任务】{title}
【简报】{brief}

只输出 Markdown，不要外层围栏。"""

_NOTE_PROMPT = """你是一名研究人员。请输出一份 Markdown 文献综述笔记：
- # 主题
- ## 研究问题
- ## 主要文献回顾（≥3 篇，含 1-2 句各自贡献）
- ## 分歧与待解决问题
- ## 个人评述

【研究者】{name}（{job}）
【任务】{title}
【简报】{brief}

只输出 Markdown，不要外层围栏。"""


def _strip_fence(text: str) -> str:
    if not isinstance(text, str):
        return ""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", t)
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def _validate_md(body: str) -> tuple[bool, str]:
    if not body:
        return False, "empty markdown"
    if not body.lstrip().startswith("#"):
        return False, "missing top-level heading"
    return True, ""


class TeachingAdapter:
    name = "teaching"
    supported_deliverables = frozenset({"lesson_plan", "research_note"})

    def run(self, brief: WorkBrief, ctx: AdapterContext) -> WorkResult:
        started = time.time()
        if brief.deliverable not in self.supported_deliverables:
            return make_failed(brief, f"unsupported deliverable {brief.deliverable!r}", started)
        try:
            return self._run(brief, ctx, started)
        except Exception as exc:  # noqa: BLE001
            _LOG.exception("teaching adapter crashed for task %s", brief.task_id)
            return make_failed(brief, f"adapter exception: {exc}", started)

    def _run(self, brief: WorkBrief, ctx: AdapterContext, started: float) -> WorkResult:
        title = _extract_label(brief.brief_text, "任务", default=brief.chosen_action)
        is_lesson = brief.deliverable == "lesson_plan"
        template = _LESSON_PROMPT if is_lesson else _NOTE_PROMPT
        role_label = "教师" if is_lesson else "研究者"
        prompt = template.format(
            name=_extract_label(brief.brief_text, role_label),
            job=_extract_label(brief.brief_text, "职业"),
            title=title,
            brief=brief.brief_text,
        )
        raw = ctx.llm(prompt) or ""
        body = _strip_fence(raw)
        ok, err = _validate_md(body)
        if not ok:
            return make_failed(brief, err, started)
        out_dir = ctx.task_dir(brief)
        filename = "lesson_plan.md" if is_lesson else "research_note.md"
        out_path = os.path.join(out_dir, filename)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(body + ("\n" if not body.endswith("\n") else ""))
        kind = "教案" if is_lesson else "研究笔记"
        return make_ok(brief, [out_path], summary=f"完成{kind}：{title}", started_at=started)


def _extract_label(text: str, label: str, default: str = "") -> str:
    if not text:
        return default
    pattern = rf"【{label}】([^\n】]*)"
    m = re.search(pattern, text)
    return m.group(1).strip() if m else default


__all__ = ["TeachingAdapter"]
