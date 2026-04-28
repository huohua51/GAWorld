"""Tests for the LLM cross-provider fallback chain."""

from __future__ import annotations

import unittest

from llm_providers import LLMRouter


class _StubProvider:
    def __init__(self, name: str, *, fail: bool = False):
        self.name = name
        self.fail = fail
        self.calls = 0

    def call(self, prompt: str) -> str:
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.name} simulated failure")
        return f"hello from {self.name}"


def _make_router(routing, providers):
    router = object.__new__(LLMRouter)
    router.providers = providers
    router.routing = routing
    router.config = {}
    return router


class TestFallbackChain(unittest.TestCase):
    def test_primary_succeeds_no_fallback_used(self):
        a = _StubProvider("a")
        b = _StubProvider("b")
        router = _make_router({"default": "a", "fallback": ["b"]}, {"a": a, "b": b})
        out = router.call("hi")
        self.assertEqual("hello from a", out)
        self.assertEqual(1, a.calls)
        self.assertEqual(0, b.calls)

    def test_primary_fails_fallback_succeeds(self):
        a = _StubProvider("a", fail=True)
        b = _StubProvider("b")
        router = _make_router({"default": "a", "fallback": ["b"]}, {"a": a, "b": b})
        out = router.call("hi")
        self.assertEqual("hello from b", out)
        self.assertEqual(1, a.calls)
        self.assertEqual(1, b.calls)

    def test_all_fail_raises_last_exception(self):
        a = _StubProvider("a", fail=True)
        b = _StubProvider("b", fail=True)
        router = _make_router({"default": "a", "fallback": ["b"]}, {"a": a, "b": b})
        with self.assertRaises(RuntimeError) as ctx:
            router.call("hi")
        self.assertIn("b simulated", str(ctx.exception))

    def test_fallback_string_value_is_normalized_to_list(self):
        a = _StubProvider("a", fail=True)
        b = _StubProvider("b")
        router = _make_router({"default": "a", "fallback": "b"}, {"a": a, "b": b})
        self.assertEqual("hello from b", router.call("hi"))

    def test_unknown_fallback_name_is_skipped(self):
        a = _StubProvider("a")
        router = _make_router({"default": "a", "fallback": ["nonexistent"]}, {"a": a})
        # Primary works; nonexistent silently dropped, no exception.
        self.assertEqual("hello from a", router.call("hi"))

    def test_task_routing_overrides_default(self):
        a = _StubProvider("a")
        b = _StubProvider("b")
        c = _StubProvider("c")
        router = _make_router(
            {"default": "a", "tasks": {"plan": "b"}, "fallback": ["c"]},
            {"a": a, "b": b, "c": c},
        )
        self.assertEqual("hello from b", router.call("hi", task="plan"))
        self.assertEqual(0, a.calls)
        self.assertEqual(1, b.calls)
        self.assertEqual(0, c.calls)


if __name__ == "__main__":
    unittest.main()
