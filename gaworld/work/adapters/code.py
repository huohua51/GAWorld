"""CodeAdapter — produce a Python script (and optional pytest)."""

from __future__ import annotations

import os
import re
import time

from gaworld.logging_setup import get_logger
from gaworld.work.adapters.base import AdapterContext, make_failed, make_ok
from gaworld.work.schemas import WorkBrief, WorkResult

_LOG = get_logger("gaworld.work.adapters.code")


_PY_PROMPT = """你是一名 Python 工程师。根据下面任务简报，输出**一个 .py 文件**的完整代码。
要求：
- 顶部加 `\"\"\"docstring\"\"\"` 简述用途。
- 单文件可独立运行（如有 main 入口加 `if __name__ == \"__main__\":`）。
- 不要外部网络访问，不要硬编码本地路径。
- 行宽 ≤110，符合 PEP 8。

【工程师】{name}（{job}）
【任务】{title}
【简报】{brief}

只输出 Python 代码，不要 Markdown 围栏。"""

_TEST_PROMPT = """你是一名 Python 工程师。为下面的实现写一份 pytest 单测，覆盖正常路径与至少 2 个边界情形。

【被测代码】
{source}

【任务简报】
{brief}

只输出测试代码，文件应能直接 pytest 运行。"""


def _strip_fence(text: str) -> str:
    if not isinstance(text, str):
        return ""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", t)
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def _validate_py(source: str) -> tuple[bool, str]:
    if not source:
        return False, "empty source"
    try:
        compile(source, "<work_adapter_code>", "exec")
    except SyntaxError as exc:
        return False, f"syntax error: {exc.msg} at line {exc.lineno}"
    return True, ""


class CodeAdapter:
    name = "code"
    supported_deliverables = frozenset({"py_script", "py_test"})

    def run(self, brief: WorkBrief, ctx: AdapterContext) -> WorkResult:
        started = time.time()
        if brief.deliverable not in self.supported_deliverables:
            return make_failed(brief, f"unsupported deliverable {brief.deliverable!r}", started)
        try:
            return self._run(brief, ctx, started)
        except Exception as exc:  # noqa: BLE001
            _LOG.exception("code adapter crashed for task %s", brief.task_id)
            return make_failed(brief, f"adapter exception: {exc}", started)

    def _run(self, brief: WorkBrief, ctx: AdapterContext, started: float) -> WorkResult:
        title = _extract_label(brief.brief_text, "任务", default=brief.chosen_action)
        prompt = _PY_PROMPT.format(
            name=_extract_label(brief.brief_text, "工程师"),
            job=_extract_label(brief.brief_text, "职业"),
            title=title,
            brief=brief.brief_text,
        )
        raw = ctx.llm(prompt) or ""
        source = _strip_fence(raw)
        ok, err = _validate_py(source)
        if not ok:
            return make_failed(brief, err, started)

        out_dir = ctx.task_dir(brief)
        script_path = os.path.join(out_dir, "main.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(source if source.endswith("\n") else source + "\n")

        artifacts = [script_path]
        # Optional accompanying pytest, only if config flag is on AND brief asks for it.
        wants_test = "单测" in brief.brief_text or "pytest" in brief.brief_text.lower()
        if wants_test and ctx.config.get("write_pytest", True):
            test_prompt = _TEST_PROMPT.format(source=source[:6000], brief=brief.brief_text)
            test_raw = ctx.llm(test_prompt) or ""
            test_source = _strip_fence(test_raw)
            ok_t, _err_t = _validate_py(test_source)
            if ok_t:
                test_path = os.path.join(out_dir, "test_main.py")
                with open(test_path, "w", encoding="utf-8") as f:
                    f.write(test_source if test_source.endswith("\n") else test_source + "\n")
                artifacts.append(test_path)

        return make_ok(
            brief,
            artifacts,
            summary=f"完成 Python 脚本：{title}",
            started_at=started,
        )


def _extract_label(text: str, label: str, default: str = "") -> str:
    if not text:
        return default
    pattern = rf"【{label}】([^\n】]*)"
    m = re.search(pattern, text)
    return m.group(1).strip() if m else default


__all__ = ["CodeAdapter"]
