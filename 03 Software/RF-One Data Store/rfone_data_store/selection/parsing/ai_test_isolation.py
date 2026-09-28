"""Test-only isolation of the RF-One AI client (`ai_client.py`) from the
machine it runs on.

`ai_client` normally resolves its configuration from the process environment
and then from the repo-root `.env`. A developer's `.env` saying
`RFONE_AI_PROVIDER=BEDROCK` (with a model id), or holding an
`ANTHROPIC_API_KEY`, would otherwise make a test's outcome depend on that
machine and send real provider calls from a test run.

`isolated_ai_client()` applies the same principle as
`test_ai_client_provider_selection.py`: while it is active, the lookup reads
only the process environment, every AI-client variable starts unset (so the
application default applies, deterministically), and the real provider SDK
entry points (`anthropic.Anthropic`, `boto3.client("bedrock-runtime")`) are
replaced by a guard that refuses and records any attempt. The caller asserts
`guard.attempts` is empty. Everything is restored on exit. Application
behavior is untouched: nothing here is imported outside tests.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from . import ai_client

AI_CLIENT_VARIABLES = (
    "RFONE_AI_PROVIDER",
    "RFONE_BEDROCK_MODEL_ID",
    "ANTHROPIC_API_KEY",
    "AWS_REGION",
)


class RealAIProviderCallBlocked(RuntimeError):
    """Raised by the guard when a test reaches a real provider SDK."""


class AIProviderGuard:
    def __init__(self) -> None:
        self.attempts: list[str] = []

    def block(self, what: str) -> None:
        self.attempts.append(what)
        raise RealAIProviderCallBlocked(f"Real AI provider call blocked during tests: {what}")


@contextmanager
def isolated_ai_client() -> Iterator[AIProviderGuard]:
    guard = AIProviderGuard()
    saved_variables = {name: os.environ.get(name) for name in AI_CLIENT_VARIABLES}
    original_reader = ai_client._read_env_or_dotenv
    restorers = []

    for name in AI_CLIENT_VARIABLES:
        os.environ.pop(name, None)
    ai_client._read_env_or_dotenv = lambda var_name: os.environ.get(var_name) or None

    try:
        import anthropic
    except ImportError:
        anthropic = None
    if anthropic is not None:
        original_anthropic = anthropic.Anthropic

        def _blocked_anthropic(*args, **kwargs):
            guard.block("anthropic.Anthropic")

        anthropic.Anthropic = _blocked_anthropic
        restorers.append(lambda: setattr(anthropic, "Anthropic", original_anthropic))

    try:
        import boto3
    except ImportError:
        boto3 = None
    if boto3 is not None:
        original_boto3_client = boto3.client

        def _guarded_boto3_client(service_name, *args, **kwargs):
            if service_name == "bedrock-runtime":
                guard.block('boto3.client("bedrock-runtime")')
            return original_boto3_client(service_name, *args, **kwargs)

        boto3.client = _guarded_boto3_client
        restorers.append(lambda: setattr(boto3, "client", original_boto3_client))

    try:
        yield guard
    finally:
        for restore in reversed(restorers):
            restore()
        ai_client._read_env_or_dotenv = original_reader
        for name, value in saved_variables.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
