"""Temporary holding area for an uploaded Bank file set awaiting the
operator's Confirm or Cancel (BANK_SOURCE_AND_IMPORT_REVIEW_001).

Between "files selected" and "human decided" the files exist ONLY here —
never in the database. A staged set is a directory named by an unguessable
token, holding the original bytes and a `manifest.json` (who uploaded it,
the options chosen, and the review computed for it). It is bound to the
account that uploaded it: no one else can confirm or cancel it.

Confirm CLAIMS the set first, by renaming its directory — an atomic step on
one filesystem — so a double click or a replayed POST finds nothing to
import the second time. Cancel deletes it. A set nobody decided on is
removed after `MAX_AGE` by the next upload; it never held authoritative
data, so leaving it behind loses nothing.

Deliberately not a database table: a cancelled import must leave the Bank
data exactly as it was, and the simplest way to guarantee that is to never
write it there in the first place.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import tempfile
import time
from dataclasses import dataclass

MAX_AGE_SECONDS = 24 * 60 * 60
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
_MANIFEST = "manifest.json"


@dataclass(frozen=True)
class StagedSet:
    token: str
    directory: str
    manifest: dict

    def files(self) -> list[tuple[str, bytes]]:
        """The staged files, in upload order, as (original name, bytes)."""
        out = []
        for entry in self.manifest["files"]:
            with open(os.path.join(self.directory, entry["stored_as"]), "rb") as handle:
                out.append((entry["file_name"], handle.read()))
        return out


def staging_root(configured: str | None) -> str:
    root = configured or os.path.join(tempfile.gettempdir(), "rfone_bank_import_staging")
    os.makedirs(root, exist_ok=True)
    return root


def _valid(token: str | None) -> bool:
    return bool(token) and bool(_TOKEN_RE.match(token))


def stage(root: str, *, account_id: int, files: list[tuple[str, bytes]], options: dict) -> str:
    """Write the set to a new token directory and return the token."""
    purge_stale(root)
    token = secrets.token_hex(16)
    directory = os.path.join(root, token)
    os.makedirs(directory)
    entries = []
    for index, (file_name, content) in enumerate(files):
        stored_as = f"{index:03d}.bin"
        with open(os.path.join(directory, stored_as), "wb") as handle:
            handle.write(content)
        entries.append({"file_name": file_name, "stored_as": stored_as})
    _write_manifest(directory, {
        "account_id": account_id, "created_at": time.time(), "files": entries,
        "options": options, "review": None,
    })
    return token


def _write_manifest(directory: str, manifest: dict) -> None:
    with open(os.path.join(directory, _MANIFEST), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle)


def save_review(staged: StagedSet, review: dict) -> None:
    manifest = dict(staged.manifest, review=review)
    _write_manifest(staged.directory, manifest)


def load(root: str, token: str | None, *, account_id: int) -> StagedSet | None:
    """The staged set for `token`, if it exists and belongs to `account_id`."""
    if not _valid(token):
        return None
    directory = os.path.join(root, token)
    try:
        with open(os.path.join(directory, _MANIFEST), encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError):
        return None
    if manifest.get("account_id") != account_id:
        return None
    return StagedSet(token=token, directory=directory, manifest=manifest)


def claim(root: str, token: str | None, *, account_id: int) -> StagedSet | None:
    """Take the set for exactly one Confirm. Returns None if it does not
    exist, is not this account's, or was already claimed or cancelled."""
    staged = load(root, token, account_id=account_id)
    if staged is None:
        return None
    claimed = os.path.join(root, f"{token}.claimed-{secrets.token_hex(4)}")
    try:
        os.rename(staged.directory, claimed)
    except OSError:
        return None
    return StagedSet(token=token, directory=claimed, manifest=staged.manifest)


def discard(staged: StagedSet | None) -> None:
    if staged is not None:
        shutil.rmtree(staged.directory, ignore_errors=True)


def purge_stale(root: str, *, now: float | None = None) -> None:
    """Remove sets older than MAX_AGE_SECONDS, decided or not."""
    now = time.time() if now is None else now
    try:
        names = os.listdir(root)
    except OSError:
        return
    for name in names:
        path = os.path.join(root, name)
        try:
            if now - os.path.getmtime(path) > MAX_AGE_SECONDS:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            continue
