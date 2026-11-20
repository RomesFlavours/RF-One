"""Source preservation — §5/§6 of `CROSS_DOMAIN_INVOICE_INTAKE_AGENT_001.md`.

Preserves the original source file(s), the raw provider response, and
acquisition metadata for one submission. Reuses the existing `uploads/`
directory convention `app.py` already established for original files
(unique-prefixed filename, never overwritten, never modified) — this
module only adds what `app.py`'s current flow never preserved at all: the
raw provider response and structured acquisition metadata, written
alongside the originals rather than to a new, separate storage location.

This module never calls Purchasing and is never invoked by `app.py`'s
existing upload/save routes in this task — see the task report for why.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .base import InvoiceSourceSubmission, NormalizedInvoice, RawExtractionResult, SourceFile

UTC = timezone.utc

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(_BASE_DIR, "uploads")
PROVIDER_MIRROR_DIR = os.path.join(UPLOAD_DIR, "_provider_mirror")


def preserve_source_file(original_path: str, original_filename: str) -> SourceFile:
    """Copies an already-on-disk file into `uploads/` under a unique-
    prefixed name (the exact same convention `app.py` already uses for a
    web upload), leaving the caller's own copy of the file untouched.
    Returns the `SourceFile` pointing at the preserved copy."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex[:8]}_{original_filename}"
    dest_path = os.path.join(UPLOAD_DIR, unique_name)
    with open(original_path, "rb") as src, open(dest_path, "wb") as dst:
        dst.write(src.read())
    return SourceFile(path=dest_path, original_filename=original_filename)


def preserve_extraction_result(
    submission: InvoiceSourceSubmission,
    normalized: NormalizedInvoice,
    raw: RawExtractionResult,
) -> str:
    """Writes the raw provider response (§6, Provider Mirror) and
    acquisition metadata (§5) to `uploads/_provider_mirror/<submission_id>/`,
    append-only (a new submission always gets a new, unique directory —
    nothing here is ever overwritten in place, consistent with the
    Provider Mirror already established for the Clover connector's
    `SourceRecord`). Returns the submission directory path.

    The normalized draft is also written alongside, for inspection/
    debugging convenience only — the raw response remains the audit
    source of truth (§6): no consuming Domain may depend on this
    convenience file."""
    submission_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}_{uuid.uuid4().hex[:8]}"
    submission_dir = os.path.join(PROVIDER_MIRROR_DIR, submission_id)
    os.makedirs(submission_dir, exist_ok=True)

    metadata: dict[str, Any] = {
        "submission_id": submission_id,
        "submitted_at": submission.submitted_at.isoformat(),
        "invoking_domain_reference": submission.invoking_domain_reference,
        "source_files": [asdict(sf) for sf in submission.source_files],
        "provider_name": raw.provider_name,
        "retrieved_at": raw.retrieved_at.isoformat(),
    }
    with open(os.path.join(submission_dir, "acquisition_metadata.json"), "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, ensure_ascii=False, default=str)

    with open(os.path.join(submission_dir, "raw_provider_response.json"), "w", encoding="utf-8") as fh:
        json.dump(raw.raw_response, fh, indent=2, ensure_ascii=False, default=str)

    with open(os.path.join(submission_dir, "normalized_draft.json"), "w", encoding="utf-8") as fh:
        json.dump(normalized.to_dict(), fh, indent=2, ensure_ascii=False, default=str)

    return submission_dir
