"""OpenCode Go chat-completions integration (mocked; no paid API calls)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from uuid import UUID

from stellenpilot.config import Settings
from stellenpilot import llm as llm_module
from stellenpilot.llm import LLM, OPENCODE_GO_BASE_URL


class OpenCodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home / "config.toml").write_text(
            '[llm]\nprovider = "opencode"\nmodel = "deepseek-v4.1-flash"\n', encoding="utf-8"
        )

    def test_missing_api_key_is_rejected(self):
        with mock.patch.dict("os.environ", {"OPENCODE_API_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "OPENCODE_API_KEY"):
                LLM(Settings(self.home))

    def test_default_endpoint_headers_and_stable_session(self):
        with mock.patch.dict("os.environ", {"OPENCODE_API_KEY": "test-secret"}):
            instance = LLM(Settings(self.home))
            self.assertEqual(instance.base_url, OPENCODE_GO_BASE_URL)
            self.assertFalse(instance.local)
            calls = []

            def fake_request(url, **kwargs):
                calls.append((url, kwargs))
                return {"choices": [{"message": {"content": '{"match": 83}'}}]}

            with mock.patch.object(llm_module, "request_json", side_effect=fake_request):
                self.assertEqual(instance.complete_json("system", "user"), {"match": 83})
                self.assertEqual(instance.complete_json("system", "next"), {"match": 83})
            self.assertEqual(len(calls), 2)
            for url, args in calls:
                self.assertEqual(url, OPENCODE_GO_BASE_URL + "/chat/completions")
                self.assertEqual(args["headers"]["Authorization"], "Bearer test-secret")
                self.assertIn("stellenpilot", args["headers"]["User-Agent"])
                self.assertEqual(UUID(args["headers"]["x-opencode-session"]).version, 4)
                self.assertEqual(args["headers"]["x-opencode-session"], instance.session_id)
                self.assertEqual(args["body"]["model"], "deepseek-v4.1-flash")
                self.assertEqual(args["body"]["response_format"], {"type": "json_object"})

    def test_can_override_base_url_for_other_opencode_chat_endpoints(self):
        (self.home / "config.toml").write_text(
            '[llm]\nprovider = "opencode"\nmodel = "example-model"\n'
            'base_url = "https://opencode.ai/zen/v1"\n', encoding="utf-8"
        )
        with mock.patch.dict("os.environ", {"OPENCODE_API_KEY": "test-secret"}):
            self.assertEqual(LLM(Settings(self.home)).base_url, "https://opencode.ai/zen/v1")


if __name__ == "__main__":
    unittest.main()
