"""Test helper: upload Bank files the way the page now does it.

Since BANK_SOURCE_AND_IMPORT_REVIEW_001 `/bank/upload` only stages the set
and opens the Import Set Review; the import happens on Confirm. Tests that
are about what an import produces (not about the review) use this to take
both steps, and get back the Confirm response — whose redirect is the one
the upload used to return.
"""

from __future__ import annotations

import re

_STAGED_RE = re.compile(r"staged=([0-9a-f]{32})")


def staged_token(response) -> str | None:
    match = _STAGED_RE.search(response.headers.get("Location", ""))
    return match.group(1) if match else None


def upload_and_confirm(client, data: dict):
    """POST the files to `/bank/upload`, then Confirm the staged set."""
    response = client.post("/bank/upload", data=data, content_type="multipart/form-data")
    token = staged_token(response)
    if token is None:
        return response
    return client.post(f"/bank/upload/{token}/confirm", data={"csrf_token": data["csrf_token"]})
