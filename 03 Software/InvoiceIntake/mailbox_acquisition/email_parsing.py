"""RFC822 email parsing shared by the real Aruba IMAP client and tests.

Kept separate from `imap_client.py` so the exact same parsing logic runs
whether the raw bytes came from a real IMAP `FETCH` or a fake client's
in-memory fixture — the two paths must never diverge.
"""

from __future__ import annotations

import email
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime


@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes


@dataclass(frozen=True)
class ParsedEmail:
    sender: str
    subject: str
    received_at: datetime | None
    attachments: list[Attachment] = field(default_factory=list)


def parse_email(raw_bytes: bytes) -> ParsedEmail:
    """Parses one RFC822 message, extracting header fields and every part
    that carries a filename (i.e. every attachment, regardless of how many —
    Purchased/README.md: "an invoice, or invoice + support documents" — this
    function never assumes exactly one)."""

    msg = email.message_from_bytes(raw_bytes)
    sender = msg.get("From", "") or ""
    subject = msg.get("Subject", "") or ""

    received_at: datetime | None = None
    date_header = msg.get("Date")
    if date_header:
        try:
            received_at = parsedate_to_datetime(date_header)
        except (TypeError, ValueError):
            received_at = None

    attachments: list[Attachment] = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        if not filename:
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        attachments.append(Attachment(filename=filename, content=payload))

    return ParsedEmail(sender=sender, subject=subject, received_at=received_at, attachments=attachments)
