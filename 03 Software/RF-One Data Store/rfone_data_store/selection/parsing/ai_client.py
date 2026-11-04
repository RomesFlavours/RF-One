"""Minimal, provider-agnostic LLM chat abstraction (task §18: "Reuse the
existing RF-One AI/provider abstraction if one exists. Do not couple
Selection to one LLM provider."). Consumers (Selection's résumé parsing/
Primary Screening AI evaluation, Organizational AI review, Tips AI Rule
Authoring) depend on exactly one contract — `generate_json(prompt) -> dict`
— and never know or care which provider actually answered it.

Two concrete providers are wired up: Anthropic (the original, default) and
AWS Bedrock (RFONE_AI_PROVIDER_BEDROCK_001 — reuses the AWS account/
credential chain already configured for this environment, never a second
AWS account, never Anthropic-issued credentials). `RFONE_AI_PROVIDER`
selects which one is active; unset defaults to ANTHROPIC, preserving every
existing deployment's current behavior unchanged. Adding a provider here
only ever means adding one function + one registry entry — no consumer,
and no other part of this contract, changes.
"""

from __future__ import annotations

import json
import os

PROVIDER_ANTHROPIC = "ANTHROPIC"
PROVIDER_BEDROCK = "BEDROCK"
DEFAULT_PROVIDER = PROVIDER_ANTHROPIC


class AIProviderUnavailable(Exception):
    """No usable AI provider is configured/reachable right now."""


def _read_env_or_dotenv(var_name: str) -> str | None:
    """Generic version of this module's original `.env` resolution
    convention (previously inlined in `_anthropic_api_key` alone) — env var
    first, then the same repo-root `.env` file `rfone_data_store/database.py`
    already uses, found by walking upward from this file. Reused for every
    RF-One AI-client configuration value (`ANTHROPIC_API_KEY`,
    `RFONE_AI_PROVIDER`, `RFONE_BEDROCK_MODEL_ID`) so a future provider
    follows the exact same lookup, never a competing convention."""
    value = os.environ.get(var_name)
    if value:
        return value
    try:
        from pathlib import Path

        current = Path(__file__).resolve()
        for _ in range(8):
            candidate = current.parent / ".env"
            if candidate.is_file():
                for line in candidate.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                    if line.strip().startswith(f"{var_name}="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
            if current.parent == current:
                break
            current = current.parent
    except Exception:
        return None
    return None


def _anthropic_api_key() -> str | None:
    return _read_env_or_dotenv("ANTHROPIC_API_KEY")


def _active_provider() -> str:
    return (_read_env_or_dotenv("RFONE_AI_PROVIDER") or DEFAULT_PROVIDER).strip().upper()


def _strip_markdown_json_fence(text: str) -> str:
    """Every prompt built on this contract already asks for "no markdown
    fences," but a model may still wrap its answer in a ```json ... ```
    block (observed from AWS Bedrock's Claude Haiku 4.5; the same latent
    risk exists for the direct Anthropic path). Strips ONLY a single
    leading/trailing fence, never touches interior content — the JSON
    payload itself is still fully parsed and validated exactly as before,
    nothing here weakens that."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped[3:]
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()
    return stripped


def _generate_json_anthropic(prompt: str) -> dict:
    api_key = _anthropic_api_key()
    if not api_key:
        raise AIProviderUnavailable("No ANTHROPIC_API_KEY configured.")

    try:
        import anthropic
    except ImportError as exc:
        raise AIProviderUnavailable("The 'anthropic' package is not installed.") from exc

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        return json.loads(_strip_markdown_json_fence(text))
    except Exception as exc:
        raise AIProviderUnavailable(f"AI provider call failed: {exc}") from exc


def _generate_json_bedrock(prompt: str) -> dict:
    """AWS Bedrock Runtime, behind the exact same `generate_json` contract
    (RFONE_AI_PROVIDER_BEDROCK_001). Deliberately introduces NO new AWS
    credential mechanism: `boto3.client("bedrock-runtime")` with no explicit
    profile/region arguments uses boto3's own standard resolution chain —
    the same `AWS_REGION`/`AWS_PROFILE`/`~/.aws/credentials`/SSO
    configuration this environment's `aws` CLI already relies on. Uses the
    Bedrock Runtime `Converse` API (provider-neutral within Bedrock itself,
    the current AWS-recommended entry point) at temperature 0 — the lowest
    available, for the deterministic/structured output RF-One's Rule
    interpretation and evidence-extraction prompts require.

    `RFONE_BEDROCK_MODEL_ID` must name a model this AWS account actually has
    Bedrock access to — never guessed or hardcoded here; the caller
    determines it once (e.g. via `aws bedrock list-foundation-models`) and
    configures it."""
    model_id = _read_env_or_dotenv("RFONE_BEDROCK_MODEL_ID")
    if not model_id:
        raise AIProviderUnavailable("No RFONE_BEDROCK_MODEL_ID configured.")

    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:
        raise AIProviderUnavailable("The 'boto3' package is not installed.") from exc

    try:
        # `AWS_REGION` follows this module's own env-var/.env convention
        # (RF-One's `.env` is never auto-loaded into the OS process
        # environment, so boto3 cannot see it on its own) — passed through
        # explicitly; `None` falls back to boto3's own standard region
        # resolution (`~/.aws/config`, etc.) unchanged.
        client = boto3.client("bedrock-runtime", region_name=_read_env_or_dotenv("AWS_REGION"))
        response = client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 4096, "temperature": 0},
        )
    except (BotoCoreError, ClientError) as exc:
        raise AIProviderUnavailable(f"AWS Bedrock call failed: {exc}") from exc

    try:
        content_blocks = response["output"]["message"]["content"]
        text = "".join(block["text"] for block in content_blocks if "text" in block)
        return json.loads(_strip_markdown_json_fence(text))
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise AIProviderUnavailable(f"AWS Bedrock returned an unparsable response: {exc}") from exc


_PROVIDERS = {
    PROVIDER_ANTHROPIC: _generate_json_anthropic,
    PROVIDER_BEDROCK: _generate_json_bedrock,
}


def generate_json(prompt: str) -> dict:
    """Call the configured LLM provider and parse its response as JSON.
    Raises `AIProviderUnavailable` if no provider is configured/reachable —
    callers must treat that as "fall back to demo," never as an application
    error surfaced to the user. Which provider actually runs is controlled
    entirely by `RFONE_AI_PROVIDER` (default: Anthropic) — this function's
    signature and behavior are identical regardless."""
    provider = _active_provider()
    impl = _PROVIDERS.get(provider)
    if impl is None:
        raise AIProviderUnavailable(
            f"Unknown RFONE_AI_PROVIDER {provider!r} — expected one of {sorted(_PROVIDERS)}."
        )
    return impl(prompt)
