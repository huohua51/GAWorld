"""Tests for the four work adapters using a stub LLM."""

from __future__ import annotations

import os
import tempfile
import unittest

from gaworld.work.adapters.base import AdapterContext
from gaworld.work.adapters.code import CodeAdapter
from gaworld.work.adapters.content import ContentAdapter
from gaworld.work.adapters.teaching import TeachingAdapter
from gaworld.work.adapters.web_design import WebDesignAdapter
from gaworld.work.schemas import WorkBrief


def _brief(deliverable: str, adapter: str, brief_text: str = "【任务】demo") -> WorkBrief:
    return WorkBrief(
        task_id=f"wt_{deliverable}",
        agent_id=2,
        sim_day=1,
        sim_time="10:00",
        activity="工作",
        chosen_action="完成任务",
        deliverable=deliverable,
        adapter=adapter,
        brief_text=brief_text,
        estimated_minutes=20,
        submitted_at=1.0,
    )


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _ctx(tmp: str, llm) -> AdapterContext:
    return AdapterContext(
        artifacts_root=os.path.join(tmp, "art"),
        llm=llm,
        config={},
    )


class TestWebDesignAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.adapter = WebDesignAdapter()

    def test_html_success_writes_file(self):
        def llm(_p: str) -> str:
            return (
                "<!DOCTYPE html><html><head><style>body{color:red}</style></head>"
                "<body><h1>Hi</h1></body></html>"
            )

        result = self.adapter.run(_brief("html_landing", "web_design"), _ctx(self.tmp, llm))
        self.assertEqual("ok", result.status)
        self.assertTrue(result.artifact_paths)
        self.assertTrue(os.path.exists(result.artifact_paths[0]))
        self.assertIn("<html", _read(result.artifact_paths[0]).lower())

    def test_html_strips_fence(self):
        def llm(_p: str) -> str:
            return "```html\n<!DOCTYPE html><html><body>x</body></html>\n```"

        result = self.adapter.run(_brief("html_landing", "web_design"), _ctx(self.tmp, llm))
        self.assertEqual("ok", result.status)
        self.assertNotIn("```", _read(result.artifact_paths[0]))

    def test_html_invalid_marks_failed(self):
        def llm(_p: str) -> str:
            return "not html at all"

        result = self.adapter.run(_brief("html_landing", "web_design"), _ctx(self.tmp, llm))
        self.assertEqual("failed", result.status)

    def test_svg_success_writes_file(self):
        def llm(_p: str) -> str:
            return '<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><text x="10" y="50">海报</text></svg>'

        result = self.adapter.run(_brief("poster_svg", "web_design"), _ctx(self.tmp, llm))
        self.assertEqual("ok", result.status)
        body = _read(result.artifact_paths[0])
        self.assertIn("<svg", body.lower())
        self.assertIn("</svg>", body.lower())

    def test_unsupported_deliverable_fails(self):
        result = self.adapter.run(
            _brief("md_article", "web_design"),  # wrong type
            _ctx(self.tmp, lambda _p: ""),
        )
        self.assertEqual("failed", result.status)


class TestCodeAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.adapter = CodeAdapter()

    def test_valid_python_compiles_and_writes(self):
        def llm(_p: str) -> str:
            return '"""sample"""\n\ndef add(a, b):\n    return a + b\n'

        result = self.adapter.run(_brief("py_script", "code"), _ctx(self.tmp, llm))
        self.assertEqual("ok", result.status)
        self.assertTrue(os.path.exists(result.artifact_paths[0]))

    def test_syntax_error_fails(self):
        def llm(_p: str) -> str:
            return "def broken( :\n  pass"

        result = self.adapter.run(_brief("py_script", "code"), _ctx(self.tmp, llm))
        self.assertEqual("failed", result.status)
        self.assertIn("syntax", (result.error or "").lower())


class TestContentAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.adapter = ContentAdapter()

    def test_md_success_writes_with_front_matter(self):
        def llm(_p: str) -> str:
            return "# 标题\n\n## 段落\n\n正文内容。\n"

        result = self.adapter.run(_brief("md_article", "content"), _ctx(self.tmp, llm))
        self.assertEqual("ok", result.status)
        body = _read(result.artifact_paths[0])
        self.assertTrue(body.startswith("---"))
        self.assertIn("# 标题", body)

    def test_md_without_heading_fails(self):
        def llm(_p: str) -> str:
            return "just some prose with no heading."

        result = self.adapter.run(_brief("md_article", "content"), _ctx(self.tmp, llm))
        self.assertEqual("failed", result.status)


class TestTeachingAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.adapter = TeachingAdapter()

    def test_lesson_plan_success(self):
        def llm(_p: str) -> str:
            return "# 自由落体\n\n## 教学目标\n- a\n- b\n- c\n\n## 教学过程\n...\n"

        result = self.adapter.run(_brief("lesson_plan", "teaching"), _ctx(self.tmp, llm))
        self.assertEqual("ok", result.status)
        self.assertTrue(result.artifact_paths[0].endswith("lesson_plan.md"))

    def test_research_note_success(self):
        def llm(_p: str) -> str:
            return "# 综述\n\n## 研究问题\n\n问题陈述。\n"

        result = self.adapter.run(_brief("research_note", "teaching"), _ctx(self.tmp, llm))
        self.assertEqual("ok", result.status)
        self.assertTrue(result.artifact_paths[0].endswith("research_note.md"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
