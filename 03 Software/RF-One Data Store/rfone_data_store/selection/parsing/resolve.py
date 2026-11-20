"""Single entry point the web app uses to turn an acquired résumé into a
CandidateCVProfile — hides the real-AI/rule-based-fallback decision (task
§18) and applies date + role normalization (Task 2B) uniformly, regardless
of which parser produced the profile.

Task 2A §2/§4/§7 removed the earlier fabricated-fixture `DemoResumeParser`
from this fallback chain: a real upload must never be resolved to
made-up candidate data merely because no AI provider is configured.
`DeterministicResumeParser` (real, rule-based extraction from the résumé's
own text) is the fallback instead — it may extract less than the AI parser,
but everything it does extract is genuinely this résumé's own content.
`DemoResumeParser`/its fixtures remain used only for direct,
synthetic-fixture testing of the analysis engine (`selection_validation.py`),
never reached through this production entry point.

Task 2B: both parsers now emit raw, un-normalized date text
(`start_date_text`/`end_date_text`) — `normalize_profile()` is the single
place that turns that text (and `original_job_title`) into normalized
dates/roles, so the two parsers never need their own, possibly-diverging
normalization logic (pipeline: file -> text extraction -> structured parsing
-> DATE + ROLE NORMALIZATION -> persisted candidate profile).
"""

from __future__ import annotations

from ..core.parser_base import ProviderUnavailable
from ..core.resume_source import MANUAL_PROVIDER, RawResumeRef
from ..normalization import normalize_profile
from .deterministic_parser import DeterministicResumeParser
from .llm_parser import LLMResumeParser


def parse_resume(raw_resume: RawResumeRef):
    """Returns a CandidateCVProfile. Tries the real AI parser first; falls
    back to real, rule-based extraction on ANY `ProviderUnavailable`
    (missing credentials, missing package, request failure) — never raises
    up to the caller for that reason, so an upload always completes, and
    never fabricates candidate data either way."""

    try:
        profile = LLMResumeParser().parse(raw_resume)
    except ProviderUnavailable:
        profile = DeterministicResumeParser().parse(raw_resume)

    profile.target_role = profile.target_role or "SERVER"
    normalize_profile(profile)

    # Source metadata (TASK_SELECTION_002 §3) — applied uniformly here,
    # authoritatively, regardless of which parser produced the structured
    # content. `raw_resume.source_type` is ground truth about how this
    # résumé was ACQUIRED (e.g. LOCAL_UPLOAD); it must never be shadowed by
    # a parser's own internal detail — in particular, DemoResumeParser's
    # fixtures carry a hardcoded "DEMO_FIXTURE" `source` for their own
    # standalone use in tests, which described *parsing*, not acquisition,
    # and must not leak onto a real upload that merely fell back to DEMO
    # parsing (that fact is already captured separately by
    # `parsing_mode`/`parser_provider`).
    profile.source = raw_resume.source_type
    profile.source_provider = profile.source_provider or MANUAL_PROVIDER

    return profile
