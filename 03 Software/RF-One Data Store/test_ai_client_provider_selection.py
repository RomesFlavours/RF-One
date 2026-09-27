#!/usr/bin/env python
"""Unit checks for the RF-One AI client's provider-selection mechanism
(RFONE_AI_PROVIDER_BEDROCK_001) — `rfone_data_store/selection/parsing/
ai_client.py`.

No database, no real network/AWS/Anthropic call: the Bedrock path is
exercised against a monkeypatched `boto3.client`, so this suite runs
identically with or without live AWS credentials configured. Confirms the
existing `generate_json(prompt) -> dict` contract, `AIProviderUnavailable`
behavior, and the default-to-Anthropic backward-compatibility guarantee are
all unchanged by adding Bedrock.

Isolated from the machine's configuration: while the checks run, the
client's configuration lookup reads only the process environment this test
controls — never the repo-root `.env` — and every AI-client variable starts
unset. A local `.env` saying `RFONE_AI_PROVIDER=BEDROCK`, or holding a real
model id or API key, can therefore neither change an outcome nor trigger a
real provider call.

Usage:
    python test_ai_client_provider_selection.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rfone_data_store.selection.parsing import ai_client  # noqa: E402


class _Result:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, description: str, condition: bool) -> None:
        (self.passed if condition else self.failed).append(description)


class _FakeBedrockClient:
    def __init__(self, response_text: str):
        self._response_text = response_text
        self.last_call_kwargs: dict | None = None

    def converse(self, **kwargs):
        self.last_call_kwargs = kwargs
        return {"output": {"message": {"content": [{"text": self._response_text}]}}}


class _RaisingBedrockClient:
    def converse(self, **kwargs):
        from botocore.exceptions import ClientError

        raise ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "not authorized"}}, "Converse",
        )


_AI_CLIENT_VARIABLES = (
    "RFONE_AI_PROVIDER",
    "RFONE_BEDROCK_MODEL_ID",
    "ANTHROPIC_API_KEY",
    "AWS_REGION",
)


def main() -> int:
    result = _Result()
    original_environ = dict(os.environ)
    original_reader = ai_client._read_env_or_dotenv
    ai_client._read_env_or_dotenv = lambda var_name: os.environ.get(var_name) or None
    for var_name in _AI_CLIENT_VARIABLES:
        os.environ.pop(var_name, None)

    try:
        # --- default provider (no RFONE_AI_PROVIDER set) is unchanged ------
        os.environ.pop("RFONE_AI_PROVIDER", None)
        result.check(
            "Default provider (unset RFONE_AI_PROVIDER) resolves to ANTHROPIC",
            ai_client._active_provider() == ai_client.PROVIDER_ANTHROPIC,
        )

        # --- explicit provider selection -----------------------------------
        os.environ["RFONE_AI_PROVIDER"] = "bedrock"
        result.check(
            "RFONE_AI_PROVIDER=bedrock resolves case-insensitively to BEDROCK",
            ai_client._active_provider() == ai_client.PROVIDER_BEDROCK,
        )

        # --- unknown provider is a clean AIProviderUnavailable, not a crash -
        os.environ["RFONE_AI_PROVIDER"] = "SOME_OTHER_PROVIDER"
        try:
            ai_client.generate_json("irrelevant")
            result.check("Unknown RFONE_AI_PROVIDER raises AIProviderUnavailable", False)
        except ai_client.AIProviderUnavailable:
            result.check("Unknown RFONE_AI_PROVIDER raises AIProviderUnavailable", True)

        # --- Bedrock: missing model id ---------------------------------------
        os.environ["RFONE_AI_PROVIDER"] = "BEDROCK"
        os.environ.pop("RFONE_BEDROCK_MODEL_ID", None)
        try:
            ai_client.generate_json("irrelevant")
            result.check("Bedrock with no RFONE_BEDROCK_MODEL_ID raises AIProviderUnavailable", False)
        except ai_client.AIProviderUnavailable:
            result.check("Bedrock with no RFONE_BEDROCK_MODEL_ID raises AIProviderUnavailable", True)

        # --- Bedrock: successful call, parsed via the real code path -------
        os.environ["RFONE_BEDROCK_MODEL_ID"] = "us.anthropic.claude-fake-test-model-v1:0"
        fake_client = _FakeBedrockClient(json.dumps({"outcome": "PROPOSED", "value": 42}))
        import boto3
        original_boto3_client = boto3.client
        boto3.client = lambda *a, **k: fake_client
        try:
            data = ai_client.generate_json("return {\"outcome\": \"PROPOSED\", \"value\": 42}")
            result.check("Bedrock success path returns a plain dict", isinstance(data, dict))
            result.check("Bedrock success path returns the parsed JSON content", data == {"outcome": "PROPOSED", "value": 42})
            result.check(
                "Bedrock call used the configured model id, never guessed",
                fake_client.last_call_kwargs is not None
                and fake_client.last_call_kwargs.get("modelId") == "us.anthropic.claude-fake-test-model-v1:0",
            )
            result.check(
                "Bedrock call requests temperature 0 (deterministic structured output)",
                fake_client.last_call_kwargs is not None
                and fake_client.last_call_kwargs.get("inferenceConfig", {}).get("temperature") == 0,
            )
        finally:
            boto3.client = original_boto3_client

        # --- Bedrock: malformed (non-JSON) response never leaks a raw parse
        # error or a Bedrock-specific object to the caller --------------------
        fake_bad_client = _FakeBedrockClient("not valid json")
        boto3.client = lambda *a, **k: fake_bad_client
        try:
            try:
                ai_client.generate_json("irrelevant")
                result.check("Malformed Bedrock JSON raises AIProviderUnavailable, never a raw JSONDecodeError", False)
            except ai_client.AIProviderUnavailable:
                result.check("Malformed Bedrock JSON raises AIProviderUnavailable, never a raw JSONDecodeError", True)
            except Exception:
                result.check("Malformed Bedrock JSON raises AIProviderUnavailable, never a raw JSONDecodeError", False)
        finally:
            boto3.client = original_boto3_client

        # --- Bedrock: provider/network error is translated, never leaked ---
        boto3.client = lambda *a, **k: _RaisingBedrockClient()
        try:
            try:
                ai_client.generate_json("irrelevant")
                result.check("A Bedrock ClientError is translated to AIProviderUnavailable, never leaked", False)
            except ai_client.AIProviderUnavailable:
                result.check("A Bedrock ClientError is translated to AIProviderUnavailable, never leaked", True)
        finally:
            boto3.client = original_boto3_client

        # --- Anthropic path is untouched: still requires ANTHROPIC_API_KEY -
        os.environ["RFONE_AI_PROVIDER"] = "ANTHROPIC"
        os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            ai_client.generate_json("irrelevant")
            result.check("Anthropic path with no ANTHROPIC_API_KEY still raises AIProviderUnavailable", False)
        except ai_client.AIProviderUnavailable:
            result.check("Anthropic path with no ANTHROPIC_API_KEY still raises AIProviderUnavailable", True)

    finally:
        ai_client._read_env_or_dotenv = original_reader
        os.environ.clear()
        os.environ.update(original_environ)

    if not result.failed:
        print(f"AI client provider-selection tests: SUCCESS ({len(result.passed)}/{len(result.passed)} checks passed)")
        return 0

    print(f"AI client provider-selection tests: FAILURE ({len(result.passed)} passed, {len(result.failed)} failed)")
    for description in result.failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
