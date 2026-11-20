"""Selection module — Resume Screening (TASK_SELECTION_001).

Implements 01 Domains/Shared Domains/Selection/ResumeScreening/.
Package layout mirrors the documented domain architecture
(ResumeScreening/README.md, "Domain architecture"):

    core/        Selection Core — generic, industry-agnostic. Never imports
                 or references anything from `industry/`.
    industry/    Industry Extensions (Restaurant today). Depends on `core/`,
                 never the reverse.
    parsing/     ResumeSource -> RawResume -> ResumeParser -> CandidateCVProfile
                 pipeline (CandidateCVProfile.md), including the real/demo
                 parser boundary (task §18).

`persistence.py` and `analysis.py` at this level are Runtime/Product
orchestration: they wire Core + an Industry Extension + the database
together for the web MVP (`03 Software/Selection/app.py`). They are not
part of Selection Core itself.
"""
