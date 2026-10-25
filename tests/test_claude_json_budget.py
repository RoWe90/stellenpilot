"""Structured Claude API replies should survive default adaptive-thinking budgets."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from stellenpilot import llm as llm_module
from stellenpilot.config import Settings
from stellenpilot.llm import LLM, CLAUDE_JSON_MIN_TOKENS


class ClaudeJsonBudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        key_patch = mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
        key_patch.start()
        self.addCleanup(key_patch.stop)

    def model(self, model: str) -> LLM:
        self.home.joinpath("config.toml").write_text(
            f'[llm]\nprovider = "anthropic"\nmodel = "{model}"\n',
            encoding="utf-8",
        )
        return LLM(Settings(self.home))

    def test_json_requests_allow_room_for_haiku_55_thinking(self):
        llm = self.model("claude-haiku-5-5")
        calls = []

        def fake(url, **kwargs):
            calls.append((url, kwargs))
            return {"content": [{"type": "thinking", "thinking": "", "signature": "signed"},
                                {"type": "text", "text": '{"body":"Personalized letter."}'}],
                    "stop_reason": "end_turn", "usage": {"output_tokens": 390}}

        with mock.patch.object(llm_module, "request_json", side_effect=fake):
            result = llm.complete_json("Write a letter", "Candidate: Python", max_tokens=900)
        self.assertEqual(result, {"body": "Personalized letter."})
        self.assertEqual(len(calls), 1)
        url, kw = calls[0]
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(kw["body"]["max_tokens"], CLAUDE_JSON_MIN_TOKENS)
        self.assertEqual(kw["body"]["output_config"], {"effort": "low"})
        self.assertEqual(kw["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(kw["headers"]["x-api-key"], "test-key")

    def test_sonnet_55_uses_same_json_budget(self):
        llm = self.model("claude-sonnet-5-5")
        with mock.patch.object(llm_module, "request_json",
                               return_value={"content": [{"type": "text", "text": '{"x": 1}'}]}) as req:
            self.assertEqual(llm.complete_json("s", "u", max_tokens=1200), {"x": 1})
        self.assertEqual(req.call_args.kwargs["body"]["max_tokens"], CLAUDE_JSON_MIN_TOKENS)
        self.assertEqual(req.call_args.kwargs["body"]["output_config"]["effort"], "low")

    def test_old_models_and_unstructured_responses_unchanged(self):
        old = self.model("claude-haiku-4-5-20251001")
        current = self.model("claude-haiku-5-5")
        response = {"content": [{"type": "text", "text": '{"ok": true}'}]}
        with mock.patch.object(llm_module, "request_json", return_value=response) as req:
            self.assertEqual(old.complete_json("s", "u", max_tokens=900)["ok"], True)
            self.assertEqual(req.call_args.kwargs["body"]["max_tokens"], 900)
            self.assertNotIn("output_config", req.call_args.kwargs["body"])
            self.assertEqual(current.complete("s", "u", max_tokens=900), '{"ok": true}')
            self.assertEqual(req.call_args.kwargs["body"]["max_tokens"], 900)
            self.assertNotIn("output_config", req.call_args.kwargs["body"])

    def test_empty_response_reports_stop_reason_and_thinking_blocks(self):
        llm = self.model("claude-haiku-5-5")
        data = {"content": [{"type": "thinking", "thinking": "", "signature": "signed"}],
                "stop_reason": "max_tokens", "usage": {"output_tokens": 4096}}
        with mock.patch.object(llm_module, "request_json", return_value=data):
            with self.assertRaises(RuntimeError) as cm:
                llm.complete_json("s", "u", max_tokens=900)
        message = str(cm.exception)
        self.assertIn("stop_reason=max_tokens", message)
        self.assertIn("output_tokens=4096", message)
        self.assertIn("block_types=['thinking']", message)
        self.assertNotIn("test-key", message)

    def test_empty_openai_compatible_reply_is_not_disguised_as_bad_json(self):
        class S:
            def __getitem__(self, key):
                return {"provider": "local", "model": "test-model",
                        "base_url": "http://127.0.0.1:8000/v1"} if key == "llm" else {}
            def secret(self, name):
                return None

        llm = LLM(S())
        result = {"choices": [{"message": {"content": None}, "finish_reason": "length"}]}
        with mock.patch.object(llm_module, "request_json", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "finish_reason=length"):
                llm.complete_json("s", "u")


if __name__ == "__main__":
    unittest.main()
