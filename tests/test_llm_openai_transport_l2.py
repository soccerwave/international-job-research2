from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from src.llm.openai_transport import OpenAIChatCompletionsTransport, OpenAITransportConfig


class OpenAITransportL2Tests(unittest.TestCase):
    def test_empty_api_key_is_rejected(self):
        with self.assertRaises(ValueError):
            OpenAIChatCompletionsTransport(OpenAITransportConfig(api_key=""))

    @patch("src.llm.openai_transport.requests.post")
    def test_structured_output_request_and_usage_are_preserved(self, post: Mock):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "model": "gpt-6-luna-2026-09-01",
            "choices": [{"message": {"content": '{"ok":true}'}}],
            "usage": {"prompt_tokens": 1234, "completion_tokens": 96},
        }
        post.return_value = response
        transport = OpenAIChatCompletionsTransport(
            OpenAITransportConfig(api_key="test-only", model="gpt-6-luna")
        )
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["ok"],
            "properties": {"ok": {"type": "boolean"}},
        }
        result = transport.generate(
            system_prompt="system",
            user_prompt="user",
            response_schema=schema,
        )
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["json"]["model"], "gpt-6-luna")
        self.assertEqual(kwargs["json"]["response_format"]["type"], "json_schema")
        self.assertTrue(kwargs["json"]["response_format"]["json_schema"]["strict"])
        self.assertEqual(kwargs["json"]["response_format"]["json_schema"]["schema"], schema)
        self.assertEqual(result.input_tokens, 1234)
        self.assertEqual(result.output_tokens, 96)
        self.assertEqual(result.model, "gpt-6-luna-2026-09-01")

    @patch("src.llm.openai_transport.requests.post")
    def test_refusal_is_explicit_failure(self, post: Mock):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "model": "gpt-6-luna",
            "choices": [{"message": {"refusal": "cannot comply", "content": None}}],
            "usage": {},
        }
        post.return_value = response
        transport = OpenAIChatCompletionsTransport(OpenAITransportConfig(api_key="test-only"))
        with self.assertRaisesRegex(RuntimeError, "refusal"):
            transport.generate(
                system_prompt="system",
                user_prompt="user",
                response_schema={"type": "object", "properties": {}, "additionalProperties": False},
            )


if __name__ == "__main__":
    unittest.main()
