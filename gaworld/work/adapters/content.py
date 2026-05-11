"""ContentAdapter — produce a Markdown article from a brief."""

from __future__ import annotations

import os
import re
import time

from gaworld.logging_setup import get_logger
from gaworld.work.adapters.base import AdapterContext, make_failed, make_ok
from gaworld.work.schemas import WorkBrief, WorkResult

_LOG = get_logger("gaworld.work.adapters.content")


_MD_PROMPT = """你是一名内容创作者。根据下面任务简报，输出一篇 Markdown 文章。

要求：
- 第一行是 # 标题。
- 接着用 1-2 个二级标题组织正文。
- 字数符合简报要求；语调贴近创作者人设。
- 不要在文末加"以上由 AI 生成"之类的免责声明。

【创作者】{name}（{job}）
【个性 / 调性】{tone}
【任务】{title}
【简报】{brief}

只输出 Markdown 内容，不要外层围栏。"""


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


class ContentAdapter:
    name = "content"
    supported_deliverables = frozenset({"md_article"})

    def run(self, brief: WorkBrief, ctx: AdapterContext) -> WorkResult:
        started = time.time()
        if brief.deliverable not in self.supported_deliverables:
            return make_failed(brief, f"unsupported deliverable {brief.deliverable!r}", started)
        try:
            return self._run(brief, ctx, started)
        except Exception as exc:  # noqa: BLE001
            _LOG.exception("content adapter crashed for task %s", brief.task_id)
            return make_failed(brief, f"adapter exception: {exc}", started)

    def _run(self, brief: WorkBrief, ctx: AdapterContext, started: float) -> WorkResult:
        title = _extract_label(brief.brief_text, "任务", default=brief.chosen_action)
        prompt = _MD_PROMPT.format(
            name=_extract_label(brief.brief_text, "创作者"),
            job=_extract_label(brief.brief_text, "职业"),
            tone=_extract_label(brief.brief_text, "调性"),
            title=title,
            brief=brief.brief_text,
        )
        raw = ctx.llm(prompt) or ""
        body = _strip_fence(raw)
        ok, err = _validate_md(body)
        if not ok:
            return make_failed(brief, err, started)
        # Add a YAML-ish front-matter for downstream traceability.
        front = (
            "---\n"
            f"agent_id: {brief.agent_id}\n"
            f"sim_day: {brief.sim_day}\n"
            f"sim_time: {brief.sim_time}\n"
            f"task_id: {brief.task_id}\n"
            "---\n\n"
        )
        out_dir = ctx.task_dir(brief)
        out_path = os.path.join(out_dir, "article.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(front + body + ("\n" if not body.endswith("\n") else ""))
        return make_ok(brief, [out_path], summary=f"完成文章：{title}", started_at=started)


def _extract_label(text: str, label: str, default: str = "") -> str:
    if not text:
        return default
    pattern = rf"【{label}】([^\n】]*)"
    m = re.search(pattern, text)
    return m.group(1).strip() if m else default


__all__ = ["ContentAdapter"]
