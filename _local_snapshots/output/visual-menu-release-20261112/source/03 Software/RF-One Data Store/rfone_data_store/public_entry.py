"""RF-One's one official entry address (UI_OFFICIAL_ENTRY_AND_LOCAL_DAYS_001).

Product Owner decision (2026-09-27): `https://rfone.romesflavours.com` is the
only address a person uses. It is the CloudFront distribution in front of
RF-One Web (`/`) and Tips (`/tips/`). The App Runner hostnames stay as the
infrastructure behind it, but are never proposed to a person.

CloudFront adds `X-RFOne-Entry: cloudfront` to every request it forwards.
A browser GET/HEAD that reaches an App Runner hostname WITHOUT it came
straight to the technical address, so it is sent (301) to the same page on
the official address. The header is a routing hint, not a security control:
someone forging it only reaches the technical hostname they already typed.
Other methods are never redirected (a redirected POST would lose its body).

`RFONE_PUBLIC_BASE_URL` turns this on; unset (local development, tests),
nothing is redirected.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlsplit

ENV_VAR = "RFONE_PUBLIC_BASE_URL"
ENTRY_HEADER = "X-RFOne-Entry"
ENTRY_VALUE = "cloudfront"


def public_base_url() -> str | None:
    """The official base address without a trailing slash, or `None`."""
    raw = (os.environ.get(ENV_VAR) or "").strip()
    parts = urlsplit(raw)
    if parts.scheme != "https" or not parts.hostname or parts.query or parts.fragment or parts.username:
        return None
    return raw.rstrip("/")


def official_redirect(method: str, headers: Mapping, path_with_query: str, *, prefix: str = "") -> str | None:
    """Where a direct request to a technical hostname should go, or `None`.

    `prefix` is where the app lives on the official address ("" for RF-One
    Web, "/tips" for Tips); `path_with_query` is the path inside the app."""
    base = public_base_url()
    if base is None or method not in ("GET", "HEAD"):
        return None
    if headers.get(ENTRY_HEADER) == ENTRY_VALUE:
        return None
    return f"{base}{prefix}{path_with_query.rstrip('?') or '/'}"
