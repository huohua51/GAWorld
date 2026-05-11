"""WebDesignAdapter — produce a real HTML or SVG file from a brief."""

from __future__ import annotations

import os
import re
import time
from html.parser import HTMLParser

from gaworld.logging_setup import get_logger
from gaworld.work.adapters.base import AdapterContext, make_failed, make_ok
from gaworld.work.schemas import WorkBrief, WorkResult

_LOG = get_logger("gaworld.work.adapters.web_design")

_HTML_PROMPT = """你是一名前端设计师。根据下面任务简报，输出一个**单文件 HTML**，包含内联 CSS，
能在浏览器直接打开。不要使用任何外链 CDN。代码需通过基本 HTML 解析。

【设计师】{name}（{job}）
【风格关键词】{skills}
【任务】{title}
【简报】{brief}

只输出 HTML 代码，从 <!DOCTYPE html> 开始。"""

_SVG_PROMPT = """你是一名平面设计师。根据下面任务简报，输出一张**单文件 SVG**海报，
viewBox 自定，使用矢量路径与文本，色彩与排版要符合简报。不要外链字体。

【设计师】{name}（{job}）
【风格关键词】{skills}
【任务】{title}
【简报】{brief}

只输出 SVG 代码，从 <svg 开始。"""


class _HTMLSyntaxValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.has_html_tag = False

    def handle_starttag(self, tag, attrs):  # type: ignore[override]
        if tag == "html":
            self.has_html_tag = True


_SVG_OPEN_RE = re.compile(r"<svg[\s>]", re.I)


def _validate_html(text: str) -> tuple[bool, str]:
    if "<html" not in text.lower():
        return False, "missing <html> tag"
    parser = _HTMLSyntaxValidator()
    try:
        parser.feed(text)
    except Exception as exc:  # noqa: BLE001
        return False, f"html parse error: {exc}"
    return True, ""


def _validate_svg(text: str) -> tuple[bool, str]:
    if not _SVG_OPEN_RE.search(text):
        return False, "missing <svg> root"
    if "</svg>" not in text.lower():
        return False, "missing </svg> close"
    return True, ""


def _extract_block(text: str, *, lang_hint: str) -> str:
    """Pull a code block out of a fenced response if present."""

    if not isinstance(text, str):
        return ""
    text = text.strip()
    if text.startswith("```"):
        # remove leading fence + optional lang tag
        text = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", text)
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


class WebDesignAdapter:
    name = "web_design"
    supported_deliverables = frozenset({"html_landing", "poster_svg"})

    def run(self, brief: WorkBrief, ctx: AdapterContext) -> WorkResult:
        started = time.time()
        if brief.deliverable not in self.supported_deliverables:
            return make_failed(brief, f"unsupported deliverable {brief.deliverable!r}", started)
        try:
            if brief.deliverable == "html_landing":
                return self._run_html(brief, ctx, started)
            return self._run_svg(brief, ctx, started)
        except Exception as exc:  # noqa: BLE001
            _LOG.exception("web_design adapter crashed for task %s", brief.task_id)
            return make_failed(brief, f"adapter exception: {exc}", started)

    # ------------------------------------------------------------------
    def _run_html(self, brief: WorkBrief, ctx: AdapterContext, started: float) -> WorkResult:
        prompt = _HTML_PROMPT.format(
            name=_brief_field(brief, "name"),
            job=_brief_field(brief, "job"),
            skills=_brief_field(brief, "skills"),
            title=_brief_field(brief, "title", default=brief.chosen_action),
            brief=brief.brief_text,
        )
        raw = ctx.llm(prompt) or ""
        body = _extract_block(raw, lang_hint="html")
        ok, err = _validate_html(body)
        if not ok:
            return make_failed(brief, err, started)
        out_dir = ctx.task_dir(brief)
        out_path = os.path.join(out_dir, "index.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(body)
        return make_ok(
            brief,
            [out_path],
            summary=f"完成 HTML 设计稿：{_brief_field(brief, 'title', default=brief.chosen_action)}",
            started_at=started,
        )

    def _run_svg(self, brief: WorkBrief, ctx: AdapterContext, started: float) -> WorkResult:
        prompt = _SVG_PROMPT.format(
            name=_brief_field(brief, "name"),
            job=_brief_field(brief, "job"),
            skills=_brief_field(brief, "skills"),
            title=_brief_field(brief, "title", default=brief.chosen_action),
            brief=brief.brief_text,
        )
        raw = ctx.llm(prompt) or ""
        body = _extract_block(raw, lang_hint="svg")
        ok, err = _validate_svg(body)
        if not ok:
            return make_failed(brief, err, started)
        out_dir = ctx.task_dir(brief)
        out_path = os.path.join(out_dir, "poster.svg")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(body)
        return make_ok(
            brief,
            [out_path],
            summary=f"完成 SVG 海报：{_brief_field(brief, 'title', default=brief.chosen_action)}",
            started_at=started,
        )


def _brief_field(brief: WorkBrief, key: str, default: str = "") -> str:
    """Pull semi-structured fields out of brief_text via simple labels."""

    text = brief.brief_text or ""
    pattern = rf"【{key}】([^\n】]*)"
    m = re.search(pattern, text)
    if m:
        return m.group(1).strip()
    return default


__all__ = ["WebDesignAdapter"]
