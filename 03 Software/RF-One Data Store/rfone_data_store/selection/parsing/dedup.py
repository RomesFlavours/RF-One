"""Best-effort résumé duplicate detection (TASK_SELECTION_002 §2:
"reasonable duplicate detection"). Deliberately simple: a hash of the
résumé's extracted text is a much stronger identity signal than filename
alone (catches the common "same PDF, re-uploaded with a renamed file"
case), so it is preferred whenever text extraction succeeded; only when a
PDF has no extractable text layer do we fall back to hashing the filename,
which is weaker but still catches an exact re-upload within one batch.

This is intentionally NOT identity resolution (e.g. "same candidate applied
twice under a different résumé") — that is a future, more sophisticated
capability. This module only answers "have we already stored this exact
résumé artifact for this restaurant?"
"""

from __future__ import annotations

import hashlib
import re

_WHITESPACE_RE = re.compile(r"\s+")


def compute_content_hash(raw_text: str | None, original_filename: str | None) -> str | None:
    """Returns a stable SHA-256 hex digest identifying this résumé's
    content, or None if there is nothing at all to hash (no extracted text
    and no filename) — callers must treat None as "duplicate detection not
    possible for this file," never as "not a duplicate."""

    if raw_text and raw_text.strip():
        normalized = _WHITESPACE_RE.sub(" ", raw_text).strip().lower()
        return "text:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    if original_filename:
        return "filename:" + hashlib.sha256(original_filename.strip().lower().encode("utf-8")).hexdigest()

    return None
