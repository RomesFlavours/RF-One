"""Configuration loading for the Aruba mailbox acquisition.

Reads `ARUBA_IMAP_USERNAME` / `ARUBA_IMAP_PASSWORD` (required) and
`ARUBA_IMAP_HOST` / `ARUBA_IMAP_PORT` / `ARUBA_IMAP_MAILBOX` /
`ARUBA_IMAP_POLL_INTERVAL_SECONDS` (optional) from the process environment,
falling back to a local `.env` file (searched upward from this file) if the
variables are not already set — same pattern as
`03 Software/Clover Data Explorer/clover_explorer/config.py` and
`03 Software/RF-One Data Store/rfone_data_store/database.py`.

The password is never logged, printed, returned in an error message, or
written to any output file. The host defaults to Aruba's own standard IMAPS
endpoint (public information, not a secret) but stays overridable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ARUBA_IMAP_DEFAULT_HOST = "imaps.aruba.it"
ARUBA_IMAP_DEFAULT_PORT = 993
DEFAULT_MAILBOX_FOLDER = "INBOX"
DEFAULT_POLL_INTERVAL_SECONDS = 45

REQUIRED_VARS = ("ARUBA_IMAP_USERNAME", "ARUBA_IMAP_PASSWORD")


class MailboxConfigError(Exception):
    """Raised when required mailbox configuration is missing or invalid.

    Messages must never include the password value itself.
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
class MailboxConfig:
    host: str
    port: int
    username: str
    password: str
    mailbox: str = DEFAULT_MAILBOX_FOLDER
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS
    use_ssl: bool = True


def _resolve(name: str, default: str, dotenv_values: dict[str, str]) -> str:
    value = os.environ.get(name)
    if value:
        return value
    return dotenv_values.get(name) or default


def load_config() -> MailboxConfig:
    """Load mailbox configuration from the environment or a local `.env`
    file. Raises `MailboxConfigError` (never containing the password value)
    if a required variable is missing or empty.
    """
    dotenv_values: dict[str, str] = {}
    dotenv_path = _find_dotenv(Path(__file__).resolve().parent)
    if dotenv_path is not None:
        dotenv_values = _parse_dotenv(dotenv_path)

    username = _resolve("ARUBA_IMAP_USERNAME", "", dotenv_values)
    password = _resolve("ARUBA_IMAP_PASSWORD", "", dotenv_values)

    missing = [name for name, value in (("ARUBA_IMAP_USERNAME", username), ("ARUBA_IMAP_PASSWORD", password)) if not value]
    if missing:
        raise MailboxConfigError(
            "Missing or empty required configuration: "
            + ", ".join(missing)
            + ". Set them as environment variables or in a local .env file "
            "at the repository root (never committed to Git)."
        )

    host = _resolve("ARUBA_IMAP_HOST", ARUBA_IMAP_DEFAULT_HOST, dotenv_values)
    port_raw = _resolve("ARUBA_IMAP_PORT", str(ARUBA_IMAP_DEFAULT_PORT), dotenv_values)
    try:
        port = int(port_raw)
    except ValueError:
        port = ARUBA_IMAP_DEFAULT_PORT
    mailbox_folder = _resolve("ARUBA_IMAP_MAILBOX", DEFAULT_MAILBOX_FOLDER, dotenv_values)
    interval_raw = _resolve("ARUBA_IMAP_POLL_INTERVAL_SECONDS", str(DEFAULT_POLL_INTERVAL_SECONDS), dotenv_values)
    try:
        poll_interval_seconds = int(interval_raw)
    except ValueError:
        poll_interval_seconds = DEFAULT_POLL_INTERVAL_SECONDS
    use_ssl_raw = _resolve("ARUBA_IMAP_USE_SSL", "true", dotenv_values)
    use_ssl = use_ssl_raw.strip().lower() not in ("0", "false", "no")

    return MailboxConfig(
        host=host,
        port=port,
        username=username,
        password=password,
        mailbox=mailbox_folder,
        poll_interval_seconds=poll_interval_seconds,
        use_ssl=use_ssl,
    )
