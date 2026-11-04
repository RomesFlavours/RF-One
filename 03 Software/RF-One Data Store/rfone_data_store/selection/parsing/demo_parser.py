"""Development/demo fallback parser (task §18: "If real AI parsing cannot
run locally because credentials are unavailable: create a development/demo
fallback; use realistic fixture CandidateCVProfiles; clearly show DEMO /
MOCK mode in the UI; never disguise mock parsing as real parsing.").

Deterministically maps an uploaded résumé to one of the three fixtures
(`fixtures.py`) by filename/content, so the same upload always produces the
same demo candidate. The uploaded file's own extracted raw text (real, not
mocked — see `text_extraction.py`) is preserved separately on `RawResume`
regardless of this fallback, so the UI can still show genuine Evidence
alongside the clearly labeled demo structured data.
"""

from __future__ import annotations

from ..core.parser_base import ResumeParser
from ..core.profile import CandidateCVProfile
from ..core.resume_source import RawResumeRef
from .fixtures import select_fixture


class DemoResumeParser(ResumeParser):
    def parse(self, raw_resume: RawResumeRef) -> CandidateCVProfile:
        seed = raw_resume.original_filename or raw_resume.raw_text or ""
        profile = select_fixture(seed)
        profile.parsing_mode = "DEMO"
        profile.parser_provider = "DEMO_FIXTURE"
        profile.source_file = raw_resume.original_filename or profile.source_file
        return profile
