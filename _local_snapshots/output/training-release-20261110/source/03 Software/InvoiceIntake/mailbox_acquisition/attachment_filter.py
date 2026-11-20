"""Which email attachments are potentially documental (candidate source
documents for Purchased), vs. incidental (logos, signature images, embedded
banners, etc.).

Two independent questions:

1. `is_documental_attachment(filename)` — is this a file TYPE the existing
   OCR/parser pipeline can read at all? Mirrors `app.py`'s `ALLOWED_EXT` for
   the manual-upload path. Kept as its own small constant here (not
   imported from `app.py`) to avoid coupling this background acquisition
   package to the Flask app module, matching this repository's existing
   convention of small, deliberately duplicated constants over a
   shared-util layer (e.g. `_find_dotenv` is duplicated the same way
   across `config.py` modules).

2. `classify_attachment(attachment)` — regardless of file type, is this
   part actually an EMAIL_ASSET (an inline signature logo/banner the email
   client embedded for display, never something a supplier meant as a
   document) rather than a genuine DOCUMENT_CANDIDATE?

   This is evidence-based, never a filename guess. A real invoice photo
   attached normally (`Content-Disposition: attachment`, no `Content-ID`)
   is a DOCUMENT_CANDIDATE regardless of its filename — including one that
   happens to be named like a generic embedded asset. The classifier only
   ever returns EMAIL_ASSET when there is *structural* MIME evidence that
   the part is meant to be displayed inline as part of the message body,
   not delivered as a document:

   - `Content-Disposition: inline` is the explicit, authoritative signal.
   - A `Content-ID` that is actually referenced via a `cid:...` link inside
     an HTML part of the same message is the next-strongest signal — this
     is literally what makes an image "embedded" in an HTML email; nothing
     else legitimately produces that combination.
   - A `Content-ID` present but NOT confirmed referenced (e.g. no HTML
     part to cross-check against) is weaker on its own; it is only treated
     as EMAIL_ASSET evidence together with a filename matching a common
     auto-generated inline-asset naming convention (e.g. `image001.jpg`,
     `logo.png`). Neither signal alone is sufficient — this is the
     "generalizable, not a filename hack" requirement: a plain `photo.jpg`
     invoice attachment with no `Content-ID` at all is never touched by
     this rule.

   Anything not matching one of the above stays a DOCUMENT_CANDIDATE — per
   the Task's own "Safe filter principle": when in doubt, process it as a
   candidate (it may still end up HUMAN for other reasons); never silently
   discard a possibly-real invoice.
"""

from __future__ import annotations

import os
import re
from typing import Protocol

ALLOWED_ATTACHMENT_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}

EMAIL_ASSET = "EMAIL_ASSET"
DOCUMENT_CANDIDATE = "DOCUMENT_CANDIDATE"

# Illustrative, non-exhaustive: common auto-generated names mail clients
# (Outlook, etc.) give an embedded signature/logo/banner image. Used only
# as corroboration alongside a Content-ID (see module docstring) — never
# alone.
_GENERIC_INLINE_ASSET_NAME_RE = re.compile(r"^(image|img|logo|signature|banner|pic)[\s_-]?\d*\.\w+$", re.IGNORECASE)


class _AttachmentLike(Protocol):
    filename: str
    content_disposition: str | None
    content_id: str | None
    referenced_as_inline_by_html: bool


def is_documental_attachment(filename: str) -> bool:
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_ATTACHMENT_EXT


def classify_attachment(attachment: _AttachmentLike) -> str:
    """Returns `EMAIL_ASSET` or `DOCUMENT_CANDIDATE` — see module docstring
    for the evidence this decision is based on."""

    if attachment.content_disposition == "inline":
        return EMAIL_ASSET

    if attachment.content_id:
        if attachment.referenced_as_inline_by_html:
            return EMAIL_ASSET
        if _GENERIC_INLINE_ASSET_NAME_RE.match(attachment.filename or ""):
            return EMAIL_ASSET

    return DOCUMENT_CANDIDATE


def is_email_asset(attachment: _AttachmentLike) -> bool:
    return classify_attachment(attachment) == EMAIL_ASSET
