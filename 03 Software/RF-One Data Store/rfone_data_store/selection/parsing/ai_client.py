"""Minimal, provider-agnostic LLM chat abstraction (task §18: "Reuse the
existing RF-One AI/provider abstraction if one exists. Do not couple
Selection to one LLM provider."). No such abstraction exists yet elsewhere
in the repository (verified before writing this), so this is the first one
— intentionally small, following the same env-var/.env resolution
convention `rfone_data_store/database.py` already uses for
`RFONE_DATABASE_URL`, so a future provider swap only ever changes this file.

Only one concrete provider is wired up (Anthropic) because that is the only
credential convention available to reuse; nothing here assumes it is the
only one that will ever exist — `generate_json()` is the entire contract a
caller depends on.
"""

from __future__ import annotations

import json
import os


class AIProviderUnavailable(Exception):
    """No usable AI provider is configured/reachable right now."""


def _anthropic_api_key() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    # Reuse the same repo-root .env convention as rfone_data_store/database.py
    # (no new configuration mechanism introduced here).
    try:
        from ..core import profile as _  # noqa: F401  (import guard only)
        from pathlib import Path

        current = Path(__file__).resolve()
        for _ in range(8):
            candidate = current.parent / ".env"
            if candidate.is_file():
                for line in candidate.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                    if line.strip().startswith("ANTHROPIC_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
            if current.parent == current:
                break
            current = current.parent
    except Exception:
        return None
    return None


def generate_json(prompt: str) -> dict:
    """Call the configured LLM provider and parse its response as JSON.
    Raises `AIProviderUnavailable` if no provider is configured/reachable —
    callers must treat that as "fall back to demo," never as an application
    error surfaced to the user."""

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
        return json.loads(text)
    except Exception as exc:
        raise AIProviderUnavailable(f"AI provider call failed: {exc}") from exc
