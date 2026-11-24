"""Where candidates are kept. On AWS: the selection-ai-test documents bucket,
under the one prefix this service may write. On a PC: a local folder.

There is no list permission on the bucket, so an index object holds one
short summary per candidate; each candidate's full record and CV sit next to it.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

BUCKET = os.environ.get("RFONE_TRAINER_BUCKET", "")
# Another course runs as its own service with its own folder (RFONE_TRAINER_PREFIX),
# so its people and records never mix with the Server Course's.
PREFIX = os.environ.get("RFONE_TRAINER_PREFIX", "selection/resumes/trainer-test/")
LOCAL = Path(os.environ.get("RFONE_TRAINER_STORE") or Path(__file__).resolve().parent / "local-store")
_lock = threading.Lock()

if BUCKET:
    import boto3
    from botocore.exceptions import ClientError
    _s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def _get(key: str) -> bytes | None:
    if BUCKET:
        try:
            return _s3.get_object(Bucket=BUCKET, Key=PREFIX + key)["Body"].read()
        except ClientError as exc:
            # Without list permission a missing key reads as AccessDenied.
            if exc.response["Error"]["Code"] in ("NoSuchKey", "AccessDenied"):
                return None
            raise
    path = LOCAL / key
    return path.read_bytes() if path.exists() else None


def _put(key: str, data: bytes, content_type: str = "application/json") -> None:
    if BUCKET:
        _s3.put_object(Bucket=BUCKET, Key=PREFIX + key, Body=data, ContentType=content_type)
        return
    path = LOCAL / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _delete(key: str) -> None:
    if BUCKET:
        _s3.delete_object(Bucket=BUCKET, Key=PREFIX + key)
        return
    (LOCAL / key).unlink(missing_ok=True)


def _summary(c: dict) -> dict:
    s = c.get("screen") or {}
    iv = c.get("interview") or {}
    return {"id": c["id"], "name": c.get("name") or "(no name)", "created": c.get("created"),
            "location": c.get("location"), "source": c.get("source"), "stage": c.get("stage"),
            "total": s.get("total", 0), "chance": s.get("chance"), "hard_stop": s.get("hard_stop", False),
            "flags": len(s.get("red_flags") or []), "interviewed": bool(iv.get("finished"))}


def index() -> dict:
    raw = _get("index.json")
    return json.loads(raw) if raw else {}


def get(cid: str) -> dict | None:
    if not cid.replace("-", "").replace("_", "").isalnum():
        return None
    raw = _get(f"c/{cid}.json")
    return json.loads(raw) if raw else None


def save(c: dict) -> None:
    with _lock:
        _put(f"c/{c['id']}.json", json.dumps(c, ensure_ascii=False).encode("utf-8"))
        idx = index()
        idx[c["id"]] = _summary(c)
        _put("index.json", json.dumps(idx, ensure_ascii=False).encode("utf-8"))


def delete(cid: str) -> None:
    with _lock:
        _delete(f"c/{cid}.json")
        _delete(f"c/{cid}.cv")
        idx = index()
        idx.pop(cid, None)
        _put("index.json", json.dumps(idx, ensure_ascii=False).encode("utf-8"))


def put_cv(cid: str, data: bytes) -> None:
    _put(f"c/{cid}.cv", data, "application/octet-stream")


def get_cv(cid: str) -> bytes | None:
    return _get(f"c/{cid}.cv")


# ---------- training activity (who opened the training and how far they got) ----------
# No names: one record per browser, with an anonymous id, the device and what
# was done. Kept in one object, like the candidate index.

def activity() -> dict:
    raw = _get("training-activity.json")
    return json.loads(raw) if raw else {}


def track(vid: str, source: str, device: str, now: str, update) -> None:
    with _lock:
        all_ = activity()
        rec = all_.setdefault(vid, {"id": vid, "source": source, "device": device, "first": now,
                                    "courses": {}, "guides": 0, "certificate": None})
        rec["last"], rec["source"], rec["device"] = now, source, device or rec.get("device", "")
        update(rec)
        _put("training-activity.json", json.dumps(all_, ensure_ascii=False).encode("utf-8"))


# ---------- named new hires (one link per person) ----------
# The team creates a hire with a name and a location; the hire's link is
# their own random id. Each hire is one record (progress, activity, practical
# checks, readiness), written by that person's own requests or by the team,
# so two people never write the same object. The index holds only what the
# team sets when creating or archiving, never progress.

def hires_index() -> dict:
    raw = _get("hires.json")
    return json.loads(raw) if raw else {}


def get_hire(hid: str) -> dict | None:
    if not hid or not hid.isalnum():
        return None
    raw = _get(f"h/{hid}.json")
    return json.loads(raw) if raw else None


def save_hire(rec: dict) -> None:
    _put(f"h/{rec['id']}.json", json.dumps(rec, ensure_ascii=False).encode("utf-8"))


def add_hire(rec: dict) -> None:
    with _lock:
        save_hire(rec)
        idx = hires_index()
        idx[rec["id"]] = {"id": rec["id"], "name": rec["name"], "location": rec["location"],
                          "created": rec["created"], "archived": False}
        _put("hires.json", json.dumps(idx, ensure_ascii=False).encode("utf-8"))


def set_hire_archived(hid: str, archived: bool) -> None:
    with _lock:
        idx = hires_index()
        if hid in idx:
            idx[hid]["archived"] = archived
            _put("hires.json", json.dumps(idx, ensure_ascii=False).encode("utf-8"))


def update_hire(hid: str, change) -> dict | None:
    """Read, change and write one hire's record."""
    with _lock:
        rec = get_hire(hid)
        if rec is None:
            return None
        change(rec)
        save_hire(rec)
        return rec


# ---------- full training conversations (management course) ----------
# One object per hire and unit: every session's conversation, keyed by when
# it started. Kept for the AI to structure later; the team page shows only
# the structured records.

def save_conversation(hid: str, unit_id: str, session_id: str, history: list, now: str) -> None:
    key = f"t/{hid}/{unit_id}.json"
    with _lock:
        raw = _get(key)
        rec = json.loads(raw) if raw else {"hire": hid, "unit": unit_id, "sessions": {}}
        s = rec["sessions"].setdefault(session_id, {"started": now})
        s["updated"], s["turns"] = now, history
        _put(key, json.dumps(rec, ensure_ascii=False).encode("utf-8"))
