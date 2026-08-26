"""Tests for OpenAI-compatible response and reasoning controls."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from llm_providers import OpenAIProvider


class TestOpenAIProvider(unittest.TestCase):
    def _provider(self, **kwargs) -> OpenAIProvider:
        return OpenAIProvider(
            "https://example.invalid/v1",
            "test-model",
            api_key="test-key",
            **kwargs,
        )

    @patch("llm_providers.requests.post")
    def test_reasoning_controls_are_sent(self, post: Mock):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": '{"status":"ok"}'}}]
        }
        post.return_value = response
        provider = self._provider(
            thinking={"type": "disabled"}, reasoning_effort="none"
        )

        self.assertEqual('{"status":"ok"}', provider.call("hello"))
        payload = post.call_args.kwargs["json"]
        self.assertEqual({"type": "disabled"}, payload["thinking"])
        self.assertEqual("none", payload["reasoning_effort"])

    @patch("llm_providers.requests.post")
    def test_reasoning_without_final_content_has_actionable_error(self, post: Mock):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "reasoning_content": "unfinished reasoning",
                    }
                }
            ]
        }
        post.return_value = response

        with self.assertRaisesRegex(ValueError, "increase max_tokens or disable thinking"):
            self._provider().call("hello")

    @patch("llm_providers.requests.post")
    def test_list_content_is_joined(self, post: Mock):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {"message": {"content": [{"text": "hello"}, {"text": " world"}]}}
            ]
        }
        post.return_value = response

        self.assertEqual("hello world", self._provider().call("hello"))


if __name__ == "__main__":
    unittest.main()
