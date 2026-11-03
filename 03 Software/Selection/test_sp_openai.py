"""Offline contract tests. All inputs synthetic; network always mocked."""
import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path[:0] = [str(Path(__file__).parent), str(Path(__file__).parent.parent / "RF-One Data Store")]
from workspace.sp import provider as p
from workspace import ai_adapter
from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable

def reply(text='{"jobs": []}', **extra):
    return {"status": "completed", "output": [{"content": [{"type": "output_text", "text": text}]}], **extra}

class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"RFONE_SP_SYNTHETIC_ONLY": "1", "RFONE_SP_AI_PROVIDER": "OPENAI",
            "RFONE_SP_AI_FALLBACK": "", "RFONE_SP_DATA_REVIEWED": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_windows_user_secret_when_process_is_stale(self):
        with patch.dict(os.environ, {"RFONE_SP_OPENAI_API_KEY": "", "OPENAI_API_KEY": ""}), patch.object(p, "_windows_user_key", return_value="synthetic-test-secret") as stored:
            self.assertEqual(p._api_key(), "synthetic-test-secret")
        stored.assert_called_once()

    def test_process_secret_has_priority(self):
        with patch.dict(os.environ, {"RFONE_SP_OPENAI_API_KEY": "synthetic-process-secret"}), patch.object(p, "_windows_user_key") as stored:
            self.assertEqual(p._api_key(), "synthetic-process-secret")
        stored.assert_not_called()

    def test_payload(self):
        with patch.object(p, "_post", return_value=reply(usage={"input_tokens": 10})) as post:
            self.assertEqual(p.generate_json("synthetic JSON"), {"jobs": []})
        payload, timeout = post.call_args.args
        self.assertEqual(payload["model"], "gpt-6.1-terra")
        self.assertIs(payload["store"], False)
        self.assertEqual(payload["reasoning"], {"effort": "none"})
        self.assertEqual(payload["text"]["format"]["type"], "json_object")
        self.assertEqual(timeout, 45)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(p.last_usage()["input_tokens"], 10)

    def test_real_data_closed(self):
        os.environ["RFONE_SP_SYNTHETIC_ONLY"] = "0"
        with patch.object(p, "_post") as post, self.assertRaises(AIProviderUnavailable):
            p.generate_json("synthetic")
        post.assert_not_called()

    def test_reviewed_account(self):
        os.environ.update(RFONE_SP_SYNTHETIC_ONLY="0", RFONE_SP_DATA_REVIEWED="openai-api-reviewed")
        with patch.object(p, "_post", return_value=reply()) as post:
            p.generate_json("synthetic JSON")
        post.assert_called_once()

    def test_scanned_retry_limited(self):
        with patch.object(p, "_post", side_effect=[p.TransportError("429", retryable=True), reply("Synthetic CV")]) as post, patch.object(p.time, "sleep"):
            self.assertEqual(p.transcribe([b"synthetic jpeg"], "Copy"), "Synthetic CV")
        self.assertEqual(post.call_count, 2)
        payload, timeout = post.call_args.args
        self.assertEqual(timeout, 12)
        self.assertTrue(payload["input"][0]["content"][1]["image_url"].startswith("data:image/jpeg;base64,"))
        self.assertNotIn("text", payload)

    def test_scan_exhaustion(self):
        with patch.object(p, "_post", side_effect=p.TransportError("503", retryable=True)) as post, patch.object(p.time, "sleep"), self.assertRaises(AIProviderUnavailable):
            p.transcribe([b"jpeg"], "Copy")
        self.assertEqual(post.call_count, 2)

    def test_no_retry_auth_or_bad_input(self):
        for status in ("400", "401", "403"):
            with patch.object(p, "_post", side_effect=p.TransportError(status)) as post, self.assertRaises(AIProviderUnavailable):
                p.transcribe([b"jpeg"], "Copy")
            self.assertEqual(post.call_count, 1)

    def test_fallback_opt_in(self):
        os.environ["RFONE_SP_AI_FALLBACK"] = "BEDROCK"
        with patch.object(p, "_post", side_effect=p.TransportError("503", retryable=True)), patch.object(p, "_bedrock", return_value='{"jobs": []}') as fallback:
            self.assertEqual(p.generate_json("JSON"), {"jobs": []})
        fallback.assert_called_once()

    def test_fallback_retention_separately_reviewed(self):
        os.environ.update(RFONE_SP_SYNTHETIC_ONLY="0", RFONE_SP_DATA_REVIEWED="openai-api-reviewed", RFONE_SP_AI_FALLBACK="BEDROCK")
        with patch.object(p, "_post", side_effect=p.TransportError("503", retryable=True)), patch.object(p, "_bedrock") as fallback, self.assertRaises(AIProviderUnavailable):
            p.generate_json("JSON")
        fallback.assert_not_called()

    def test_scan_fallback_max_two_total(self):
        os.environ["RFONE_SP_AI_FALLBACK"] = "BEDROCK"
        with patch.object(p, "_post", side_effect=p.TransportError("503", retryable=True)) as post, patch.object(p, "_bedrock", return_value="Synthetic") as fallback:
            self.assertEqual(p.transcribe([b"jpeg"], "Copy"), "Synthetic")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(fallback.call_args.kwargs["attempts"], 1)

    def test_incomplete_and_bad_json(self):
        for response in (reply(status="incomplete"), reply("[]"), reply("bad JSON"), reply("")):
            with patch.object(p, "_post", return_value=response), self.assertRaises(AIProviderUnavailable):
                p.generate_json("JSON")

    def test_scoped_routing(self):
        with patch.object(ai_adapter, "_REAL_GENERATE_JSON", return_value={"shared": True}) as shared, patch.object(p, "generate_json", return_value={"sp": True}) as sp:
            self.assertEqual(ai_adapter._transport("JSON", "test"), {"shared": True})
            with p.scope():
                self.assertEqual(ai_adapter._transport("JSON", "test"), {"sp": True})
            self.assertEqual(ai_adapter._transport("JSON", "test"), {"shared": True})
        self.assertEqual(shared.call_count, 2)
        sp.assert_called_once()
        self.assertFalse(p.in_scope())

    def test_years_survive_contacts_removed(self):
        for dates in ("2019 - 2021", "2018–2020", "2019 - 2021 - 2023", "Jan 2020 - Present", "2018.2020"):
            self.assertEqual(ai_adapter.redact_contacts(dates), dates)
        text = "2019 - 2021\n(407) 555-0132\nsynthetic@example.test\n2022 - 2024"
        redacted = ai_adapter.redact_contacts(text)
        self.assertIn("2019 - 2021", redacted)
        self.assertIn("2022 - 2024", redacted)
        self.assertNotIn("555", redacted)
        self.assertNotIn("example.test", redacted)

if __name__ == "__main__":
    unittest.main(verbosity=2)
