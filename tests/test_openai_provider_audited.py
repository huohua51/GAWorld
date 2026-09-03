"""Tests for OpenAI-compatible response and reasoning controls."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from llm_providers_audited import OpenAIProvider


class TestOpenAIProvider(unittest.TestCase):
    def _provider(self, **kwargs) -> OpenAIProvider:
        return OpenAIProvider(
            "https://example.invalid/v1",
            "test-model",
            api_key="test-key",
            **kwargs,
        )

    @patch("llm_providers_audited.requests.post")
    def test_reasoning_controls_are_sent(self, post: Mock):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"choices": [{"message": {"content": '{"status":"ok"}'}}]}
        post.return_value = response
        provider = self._provider(thinking={"type": "disabled"}, reasoning_effort="none")

        self.assertEqual('{"status":"ok"}', provider.call("hello"))
        payload = post.call_args.kwargs["json"]
        self.assertEqual({"type": "disabled"}, payload["thinking"])
        self.assertEqual("none", payload["reasoning_effort"])

    @patch("llm_providers_audited.requests.post")
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

    @patch("llm_providers_audited.requests.post")
    def test_list_content_is_joined(self, post: Mock):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": [{"text": "hello"}, {"text": " world"}]}}]
        }
        post.return_value = response

        self.assertEqual("hello world", self._provider().call("hello"))

    @patch("llm_providers_audited.requests.post")
    def test_response_format_is_forwarded_without_modification(self, post: Mock):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"choices": [{"message": {"content": '{"status":"ok"}'}}]}
        post.return_value = response
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "status",
                "schema": {
                    "type": "object",
                    "properties": {"status": {"type": "string"}},
                    "required": ["status"],
                    "additionalProperties": False,
                },
            },
        }

        provider = self._provider(response_format=response_format, retry_attempts=1)
        self.assertEqual('{"status":"ok"}', provider.call("hello"))
        self.assertEqual(response_format, post.call_args.kwargs["json"]["response_format"])
        self.assertEqual(1, post.call_count)

    @patch("llm_providers_audited.time.sleep")
    @patch("llm_providers_audited.requests.post")
    def test_transport_attempts_and_retry_reason_are_returned(self, post: Mock, sleep: Mock):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"choices": [{"message": {"content": '{"status":"ok"}'}}]}
        post.side_effect = [requests.exceptions.ConnectionError("tls eof"), response]

        result = self._provider(retry_attempts=2).call_with_metadata("hello")

        self.assertEqual('{"status":"ok"}', result.text)
        self.assertEqual(2, result.metadata["transport_attempt_count"])
        self.assertEqual(1, result.metadata["transport_retry_count"])
        first, second = result.metadata["transport_attempts"]
        self.assertFalse(first["success"])
        self.assertTrue(first["retryable"])
        self.assertTrue(first["will_retry"])
        self.assertEqual("ConnectionError", first["error_type"])
        self.assertTrue(second["success"])
        sleep.assert_called_once_with(0.6)

    @patch("llm_providers_audited.requests.post")
    def test_single_attempt_mode_fails_without_hidden_retry(self, post: Mock):
        post.side_effect = requests.exceptions.ConnectionError("tls eof")
        provider = self._provider(retry_attempts=1)

        with self.assertRaises(requests.exceptions.ConnectionError) as captured:
            provider.call("hello")

        metadata = captured.exception.gaworld_call_metadata
        self.assertEqual(1, post.call_count)
        self.assertEqual(1, metadata["transport_attempt_count"])
        self.assertEqual(0, metadata["transport_retry_count"])
        self.assertFalse(metadata["transport_attempts"][0]["will_retry"])


if __name__ == "__main__":
    unittest.main()
