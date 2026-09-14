"""Which email attachments are potentially documental (candidate source
documents for Purchased), vs. incidental (logos, signature images, ICS
invites, etc.).

Mirrors `app.py`'s `ALLOWED_EXT` for the manual-upload path — the same file
types this prototype's OCR/parser can already read (`ocr_engine.py`). Kept
as its own small constant here (not imported from `app.py`) to avoid
coupling this background acquisition package to the Flask app module,
matching this repository's existing convention of small, deliberately
duplicated constants over a shared-util layer (e.g. `_find_dotenv` is
duplicated the same way across `config.py` modules).
"""

from __future__ import annotations

import os

ALLOWED_ATTACHMENT_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}


def is_documental_attachment(filename: str) -> bool:
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_ATTACHMENT_EXT
