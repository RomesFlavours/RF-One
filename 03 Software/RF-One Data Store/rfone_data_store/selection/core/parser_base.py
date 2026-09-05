"""The ResumeParser boundary (task §18). A parser turns a `RawResumeRef`
into a `CandidateCVProfile`. Concrete implementations live in `..parsing`
(never in `core/`, so Core stays independent of any specific parser or AI
provider). `ProviderUnavailable` lets a caller fall back to the demo parser
without treating it as an application error.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .profile import CandidateCVProfile
from .resume_source import RawResumeRef


class ProviderUnavailable(Exception):
    """Raised when a real parsing provider is configured but cannot run
    right now (no credentials, package missing, request failed) — signals
    the caller to fall back to the demo parser, never to fail the upload."""


class ResumeParser(ABC):
    @abstractmethod
    def parse(self, raw_resume: RawResumeRef) -> CandidateCVProfile:
        """Return a CandidateCVProfile matching CandidateCVProfile.md's
        shape. Must set `profile.parsing_mode` and `profile.parser_provider`
        truthfully — never disguise demo output as real parsing."""
        raise NotImplementedError
