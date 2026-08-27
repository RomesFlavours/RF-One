"""Configuration loading for the Clover Data Explorer.

Reads CLOVER_MERCHANT_ID and CLOVER_API_TOKEN from the process environment,
falling back to a local `.env` file (searched upward from this file) if the
variables are not already set. The token is never logged, printed, returned
in error messages, or written to any output file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

CLOVER_PRODUCTION_BASE_URL = "https://api.clover.com"

REQUIRED_VARS = ("CLOVER_MERCHANT_ID", "CLOVER_API_TOKEN")


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid.

    Messages must never include the token value itself.
    """


def _find_dotenv(start: Path, max_levels: int = 8) -> Path | None:
    current = start
    for _ in range(max_levels):
        candidate = current / ".env"
        if candidate.is_file():
            return candidate
        if current.parent == current:
            break
        current = current.parent
    return None


def _parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


@dataclass(frozen=True)
class CloverConfig:
    merchant_id: str
    api_token: str
    base_url: str = CLOVER_PRODUCTION_BASE_URL


def load_config() -> CloverConfig:
    """Load Clover configuration from the environment or a local .env file.

    Raises ConfigError with a description that never contains the token
    value if a required variable is missing or empty.
    """
    values = {name: os.environ.get(name, "") for name in REQUIRED_VARS}

    if not all(values.values()):
        dotenv_path = _find_dotenv(Path(__file__).resolve().parent)
        if dotenv_path is not None:
            dotenv_values = _parse_dotenv(dotenv_path)
            for name in REQUIRED_VARS:
                if not values.get(name):
                    values[name] = dotenv_values.get(name, "")

    missing = [name for name in REQUIRED_VARS if not values.get(name)]
    if missing:
        raise ConfigError(
            "Missing or empty required configuration: "
            + ", ".join(missing)
            + ". Set them as environment variables or in a local .env file "
            "at the repository root (never committed to Git)."
        )

    return CloverConfig(
        merchant_id=values["CLOVER_MERCHANT_ID"],
        api_token=values["CLOVER_API_TOKEN"],
    )
