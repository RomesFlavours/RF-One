"""Ask Training to email its activation invitation when a candidate is marked Hired.

Training owns the invitation (same one as Training -> Students -> Invite student,
"Selection" source). Selection only tells Training which candidate was hired and
by whom, signed with a key derived from the RFONE_FLASK_SECRET_KEY all RF-One apps
share. The Hired decision is already saved before this runs and never depends on it.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request

CONTEXT = b"rfone-training-auto-invite-v1"
PATH = "/training/manage/enrollment/auto"
TIMEOUT_SECONDS = 15


def _sign(secret: str, body: bytes) -> str:
    key = hmac.new(secret.encode(), CONTEXT, hashlib.sha256).digest()
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def request_invite(base_url: str | None, *, position_candidate_id: int, actor_account_id: int) -> tuple[str, str]:
    """Returns (status, message). status is 'sent', 'already', or a reason it was not sent."""
    secret = os.environ.get("RFONE_FLASK_SECRET_KEY") or ""
    if not base_url or not secret:
        return "off", ""
    body = json.dumps({"selection_id": position_candidate_id, "actor_id": actor_account_id,
                       "ts": int(time.time())}, separators=(",", ":")).encode()
    req = urllib.request.Request(base_url.rstrip("/") + PATH, data=body, method="POST", headers={
        "Content-Type": "application/json", "X-RFOne-Signature": _sign(secret, body)})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 405):
            # Training without automatic invitations (not released yet): Hired works as before.
            return "off", ""
        try:
            data = json.loads(exc.read() or b"{}")
        except ValueError:
            data = {}
        data.setdefault("status", "error")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        data = {"status": "error"}
    status = str(data.get("status") or "error")
    message = str(data.get("message") or "")
    if status == "error" and not message:
        message = "Training could not be reached, so no invitation was sent. Invite them from Training, Students, Invite student."
    return status, message
