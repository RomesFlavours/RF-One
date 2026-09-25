"""Where standalone Tips sends a person to finalize a saved period.

TIPS_AWS_FINALIZATION_WORKFLOW_001: the ONE human finalization path is
RF-One Web's `/tips/runs/<run_id>`, on the host where the person signed in.
Tips itself never validates. It only links there, for the SAME run id.

`RFONE_WEB_BASE_URL` is the authoritative RF-One Web base address (e.g.
`https://rfone.example.com`). It is configuration, never a hostname in
code, so moving RF-One Web to another domain needs no code change.

A base URL that is absent, or is not a plain `http(s)://host[/path]`
address, counts as not configured: no link is rendered and the page says
so. Credentials, a query string or a fragment are refused rather than
passed on, so the link can never carry a secret. The run id is an `int`,
so nothing a person types can become part of the URL.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

ENV_VAR = "RFONE_WEB_BASE_URL"

NOT_CONFIGURED_MESSAGE = (
    "RF-One Web navigation is not configured (RFONE_WEB_BASE_URL is not set), so this page "
    "cannot link to the validation screen. Periods are validated only in RF-One Web, under "
    "Tips → saved periods. Ask an RF-One administrator to set RFONE_WEB_BASE_URL for Tips."
)


def base_url() -> str | None:
    """The configured RF-One Web base URL without a trailing slash, or `None`."""
    raw = (os.environ.get(ENV_VAR) or "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        return None
    return raw.rstrip("/")


def tips_run_url(run_id: int) -> str | None:
    """RF-One Web's page for this exact run, or `None` when not configured."""
    base = base_url()
    if base is None:
        return None
    return f"{base}/tips/runs/{int(run_id)}"
