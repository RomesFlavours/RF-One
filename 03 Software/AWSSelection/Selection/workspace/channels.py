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
    Channel(MANUAL_UPLOAD, "Manager résumé upload", True, "Multiple files: PDF, DOCX, TXT."),
    Channel(PUBLIC_LINK, "Public application page", True,
            "Candidates verify their email, then upload a résumé and complete a short "
            "English interview that they can save and resume. No access to internal functions."),
    Channel("INDEED", "Indeed", False,
            "Available: the public page includes JobPosting structured data and can be used as an "
            "“Apply on company site” link. No automatic Indeed integration."),
)
CHANNEL_LABELS = {c.code: c.label for c in CHANNELS}
