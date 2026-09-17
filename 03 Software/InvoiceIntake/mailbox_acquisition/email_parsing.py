"""RFC822 email parsing shared by the real Aruba IMAP client and tests.

Kept separate from `imap_client.py` so the exact same parsing logic runs
whether the raw bytes came from a real IMAP `FETCH` or a fake client's
in-memory fixture — the two paths must never diverge.

Also captures the MIME evidence `attachment_filter.py` needs to tell a real
document attachment apart from an inline email asset (signature logo,
embedded banner) — see that module's docstring for the classification
itself; this module only extracts the evidence, unmodified and
uninterpreted.
"""

from __future__ import annotations

import email
import re
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime

# Matches a `cid:...` reference inside an HTML body, e.g. `src="cid:image001.jpg@01DD4478.F3097330"`.
_CID_REFERENCE_RE = re.compile(r"cid:([^\"'\s>]+)")


@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes
    # MIME evidence for inline-asset classification (attachment_filter.py) —
    # never used to alter OCR/parsing, only acquisition-candidacy.
    content_disposition: str | None = None  # "attachment", "inline", or None if unset
    content_id: str | None = None  # raw Content-ID header value, e.g. "<image001.jpg@...>"
    referenced_as_inline_by_html: bool = False  # this part's Content-ID appears as a `cid:` reference in an HTML part of the same message


@dataclass(frozen=True)
class ParsedEmail:
    sender: str
    subject: str
    received_at: datetime | None
    attachments: list[Attachment] = field(default_factory=list)


def _html_cid_references(msg: email.message.Message) -> set[str]:
    """Every `cid:...` value referenced by any `text/html` part of the
    message — used to confirm a part is genuinely embedded/displayed
    inline, not merely carrying a Content-ID header for some other reason."""

    references: set[str] = set()
    for part in msg.walk():
        if part.get_content_type() != "text/html":
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            html = payload.decode(charset, errors="replace")
        except (LookupError, UnicodeError):
            html = payload.decode("utf-8", errors="replace")
        references.update(_CID_REFERENCE_RE.findall(html))
    return references


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

    cid_references = _html_cid_references(msg)

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

        content_id = part.get("Content-ID")
        stripped_content_id = content_id.strip("<>") if content_id else None
        referenced = bool(stripped_content_id) and stripped_content_id in cid_references

        attachments.append(
            Attachment(
                filename=filename,
                content=payload,
                content_disposition=part.get_content_disposition(),
                content_id=content_id,
                referenced_as_inline_by_html=referenced,
            )
        )

    return ParsedEmail(sender=sender, subject=subject, received_at=received_at, attachments=attachments)
