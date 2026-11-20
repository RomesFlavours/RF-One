"""ResumeSource / RawResume (01 Domains/Cross Domain/Selection/
ResumeScreening/CandidateCVProfile.md, "Resume Source architecture").
Local PDF upload is the first ResumeSource; a future API-based source
(Indeed, another provider) is a new `source_type` value, not a new pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

LOCAL_UPLOAD = "LOCAL_UPLOAD"
DEMO_FIXTURE = "DEMO_FIXTURE"
# Future values (not implemented): e.g. "API_INDEED". Adding one never
# requires touching `ResumeParser` or `CandidateCVProfile`.

# `source_provider` values — who/what acquired the résumé within a
# `source_type` (TASK_SELECTION_002 §3). Only "manual" is used today; a
# future API ResumeSource would set its own provider name here.
MANUAL_PROVIDER = "manual"


@dataclass
class RawResumeRef:
    """A lightweight, persistence-independent reference to an acquired
    résumé — enough for a `ResumeParser` to do its job without depending on
    how/where it was stored."""

    source_type: str
    raw_text: str | None
    original_filename: str | None = None
