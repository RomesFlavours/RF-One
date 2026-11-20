"""IMAP access to the Aruba mailbox, behind a small provider-agnostic
contract (`ImapClient`) so `acquisition_service.py` never depends on
`imaplib` directly and tests can substitute a fake client (see
`test_mailbox_acquisition.py`).

Read-only by design (`SELECT ... readonly=True`): this module never marks a
message as read, moves it, or deletes it — the mailbox must remain normally
usable by a human (Task requirement, "Email state"). No message content or
credential is ever logged here.
"""

from __future__ import annotations

import imaplib
from dataclasses import dataclass
from typing import Protocol

from .config import MailboxConfig


@dataclass(frozen=True)
class RawEmailMessage:
    uid: str
    raw_bytes: bytes


class ImapClient(Protocol):
    """The contract `acquisition_service.py` relies on. `ArubaImapClient`
    (below) implements it against a real Aruba mailbox; tests implement it
    against an in-memory fixture."""

    def list_message_uids(self, mailbox: str, since_uid: str | None = None) -> list[str]: ...

    def fetch_message(self, mailbox: str, uid: str) -> RawEmailMessage: ...

    def close(self) -> None: ...


class ImapClientError(Exception):
    """Raised for any IMAP-level failure. Messages must never include the
    mailbox password."""


class ArubaImapClient:
    """Real IMAP4/IMAP4_SSL client for Aruba's standard IMAP service.
    Connects lazily on first use and reuses the connection across calls
    within one poll cycle; `close()` logs out cleanly."""

    def __init__(self, config: MailboxConfig):
        self._config = config
        self._conn: imaplib.IMAP4 | None = None

    def _connect(self) -> imaplib.IMAP4:
        if self._conn is not None:
            return self._conn
        try:
            if self._config.use_ssl:
                conn = imaplib.IMAP4_SSL(self._config.host, self._config.port)
            else:
                conn = imaplib.IMAP4(self._config.host, self._config.port)
            conn.login(self._config.username, self._config.password)
        except Exception as exc:  # noqa: BLE001 — normalized below, never re-raises raw creds
            detail = _scrub_text(str(exc), self._config)
            raise ImapClientError(f"Could not connect/login to {self._config.host}:{self._config.port} ({detail})") from None
        self._conn = conn
        return conn

    def list_message_uids(self, mailbox: str, since_uid: str | None = None) -> list[str]:
        conn = self._connect()
        typ, _ = conn.select(mailbox, readonly=True)
        if typ != "OK":
            raise ImapClientError(f"Could not select mailbox folder {mailbox!r}")

        criteria = f"UID {int(since_uid) + 1}:*" if since_uid is not None else "ALL"
        typ, data = conn.uid("search", None, criteria)
        if typ != "OK":
            raise ImapClientError("IMAP UID SEARCH failed")
        if not data or not data[0]:
            return []
        uids = [uid.decode() for uid in data[0].split()]

        if since_uid is not None:
            # Observed against real Aruba IMAP (RF-One smoke test): a
            # "UID N:*" search where N exceeds every existing UID does not
            # reliably return an empty result -- the server returns the
            # highest existing UID instead (a known ambiguity in how "*" in
            # a UID range is resolved, not unique to Aruba). Filtering
            # client-side guarantees this method's own contract ("since"
            # is exclusive) regardless of server-specific interpretation.
            uids = [uid for uid in uids if int(uid) > int(since_uid)]

        return uids

    def fetch_message(self, mailbox: str, uid: str) -> RawEmailMessage:
        conn = self._connect()
        conn.select(mailbox, readonly=True)
        typ, data = conn.uid("fetch", uid, "(RFC822)")
        if typ != "OK" or not data or data[0] is None:
            raise ImapClientError(f"IMAP UID FETCH failed for uid {uid}")
        raw_bytes = data[0][1]
        return RawEmailMessage(uid=uid, raw_bytes=raw_bytes)

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.logout()
            except Exception:  # noqa: BLE001 — best-effort cleanup only
                pass
            self._conn = None


def _scrub_text(text: str, config: MailboxConfig) -> str:
    """Returns `text` with the mailbox password (if it somehow appears —
    IMAP servers do not normally echo credentials) replaced, so nothing
    derived from it is ever safe to print/log as-is."""

    if config.password and config.password in text:
        text = text.replace(config.password, "***")
    return text
