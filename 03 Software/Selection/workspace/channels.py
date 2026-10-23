"""Candidate acquisition channels.

Every channel ends in the same place: a CV file handed to the existing
Selection import (`import_pipeline.import_one_resume`). A future channel
(Indeed, a job board, email) only has to deliver files plus the applicant's
declared contacts; nothing downstream changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from rfone_data_store.selection.workspace_models import MANUAL_UPLOAD, PUBLIC_LINK


@dataclass(frozen=True)
class Channel:
    code: str
    label: str
    active: bool
    note: str


CHANNELS = (
    Channel(MANUAL_UPLOAD, "Résumé upload by the manager", True, "Several files at once: PDF, DOCX, TXT."),
    Channel(PUBLIC_LINK, "Public position page", True,
            "The candidate registers and verifies their email, then uploads the résumé and answers a short "
            "interview in English that can be paused and resumed. No access to internal functions."),
    Channel("INDEED", "Indeed", False,
            "Prepared: the public page contains JobPosting structured data and can be used as the "
            "“Apply on company site” link. No automatic integration with Indeed."),
)
CHANNEL_LABELS = {c.code: c.label for c in CHANNELS}
