"""The Server Course joined to RF-One Training (13 November 2026).

Two things, with no shared secret and no change to AWS permissions. Each side
proves a request by calling the other back on its fixed address:

1. A named hire, on their own course link, types the email they want for
   RF-One Training. The course keeps a one-time code on their record and asks
   Training to send the invitation. Training calls the course back with that
   code (GET /api/training-link/<code>) to read the email, then emails its own
   activation link. Nothing is created in RF-One until the person activates.

2. In RF-One Training, the "Server Course" card sends a signed-in person here
   with a short-lived code. The course asks Training whether that code is real
   (POST /training/courses/server/verify) and gets back the RF-One account and
   its verified email. It opens that person's own course record: the one already
   joined to the account, else the hire who asked for an invitation with that
   same email, else a new record. Progress stays exactly where it was.
"""
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import store

TRAINING_URL = (os.environ.get("RFONE_TRAINING_URL") or "https://rfone.romesflavours.com").rstrip("/")
TIMEOUT = 15
EMAIL = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")
CODE_HOURS = 2


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _post(path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(TRAINING_URL + path, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except ValueError:
            return exc.code, {}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 0, {}


_ready = {"value": None, "at": 0.0}


def training_ready() -> bool:
    """Whether RF-One Training already has these routes (checked at most every 5 minutes).
    Until it does, the course shows nothing new, so the two can be released in any order."""
    import time
    if _ready["value"] is not None and time.time() - _ready["at"] < 300:
        return _ready["value"]
    code, _ = _post("/training/courses/server/verify", {"code": ""})
    _ready.update(value=code == 403, at=time.time())
    return _ready["value"]


def status(hire: dict) -> dict:
    """What the hire's page shows about RF-One Training."""
    link = hire.get("rfone") or {}
    if not link.get("account_id") and not training_ready():
        return {"state": "off", "email": ""}
    if link.get("account_id"):
        return {"state": "joined", "email": link.get("email", "")}
    inv = hire.get("training_invite") or {}
    if inv.get("sent"):
        return {"state": "invited", "email": inv.get("email", "")}
    return {"state": "none", "email": ""}


def request_invite(hid: str, email: str) -> tuple[bool, str]:
    email = (email or "").strip().lower()[:254]
    if not EMAIL.fullmatch(email):
        return False, "That email doesn't look right. Check it and try again."
    code = f"{hid}.{secrets.token_urlsafe(24)}"

    def keep(h):
        h["training_invite"] = {"email": email, "code": code, "at": _now().isoformat(timespec="seconds"),
                                "sent": False}
    if store.update_hire(hid, keep) is None:
        return False, "Your course record wasn't found."
    code_status, data = _post("/training/courses/server/invite", {"code": code})
    if data.get("status") == "sent":
        store.update_hire(hid, lambda h: h["training_invite"].update(sent=True))
        return True, f"We emailed your RF-One Training invitation to {email}. Open it within 48 hours to choose your password."
    if code_status == 0 or code_status == 404:
        return False, "RF-One Training couldn't be reached. Try again later; your course keeps working as it is."
    return False, data.get("message") or "The invitation couldn't be sent. Try again in a minute."


def invite_details(code: str) -> dict | None:
    """Training's call back: the email behind a code this course issued, once, within two hours."""
    hid = (code or "").split(".", 1)[0]
    hire = store.get_hire(hid) if hid.isalnum() else None
    inv = (hire or {}).get("training_invite") or {}
    if not inv or not secrets.compare_digest(str(inv.get("code") or ""), code or ""):
        return None
    try:
        if _now() - datetime.fromisoformat(inv["at"]) > timedelta(hours=CODE_HOURS):
            return None
    except (KeyError, ValueError):
        return None
    return {"email": inv["email"]}


def verify(code: str) -> dict | None:
    """Ask Training whether a handoff code is real. Returns the account, or None."""
    if not code or len(code) > 2000:
        return None
    status_code, data = _post("/training/courses/server/verify", {"code": code})
    if status_code != 200 or not data.get("account_id"):
        return None
    return data


def hire_for(account: dict) -> str:
    """The course record for this RF-One account: joined already, invited with the same
    verified email, or new. Returns the hire id."""
    account_id = int(account["account_id"])
    email = str(account.get("email") or "").strip().lower()
    idx = store.hires_index()
    invited = None
    for hid, row in idx.items():
        h = store.get_hire(hid)
        if not h:
            continue
        if (h.get("rfone") or {}).get("account_id") == account_id:
            return hid
        inv = h.get("training_invite") or {}
        if email and inv.get("email") == email and not (h.get("rfone") or {}).get("account_id") and not row.get("archived"):
            invited = invited or hid
    link = {"account_id": account_id, "email": email, "joined": _now().isoformat(timespec="seconds")}
    if invited:
        store.update_hire(invited, lambda h: h.__setitem__("rfone", link))
        return invited
    hid = secrets.token_hex(10)
    name = re.sub(r"\s+", " ", str(account.get("name") or "")).strip()[:60] or "New server"
    store.add_hire({"id": hid, "name": name, "location": "", "created": _now().isoformat(timespec="seconds"),
                    "rfone": link})
    return hid


def status_request(code: str) -> list[int] | None:
    """The accounts Training asks about, from a code Training confirms it signed for this purpose."""
    if not code or len(code) > 20000 or not verify(code):
        return None
    try:
        body = code.rsplit(".", 1)[0]
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if data.get("k") != "status":
            return None
        return [int(x) for x in data.get("q") or []][:1000]
    except (ValueError, TypeError, AttributeError):
        return None


def hires_by_account(account_ids: list[int]) -> dict[int, dict]:
    """Course records joined to these RF-One accounts (testers left out)."""
    wanted, out = set(account_ids), {}
    for hid, row in store.hires_index().items():
        h = store.get_hire(hid)
        acc = ((h or {}).get("rfone") or {}).get("account_id")
        if acc in wanted and not h.get("tester") and (acc not in out or not row.get("archived")):
            h["archived"] = row.get("archived", False)
            out[acc] = h
    return out
