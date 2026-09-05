"""Organization Intelligence — OPEN / TBD (task §16).

Deliberately not implemented. A future capability would reason about the
*employer* side of a candidate's Work History (e.g. what a given employer's
real operating/training standard is, so two candidates' "3 years" carry
correctly calibrated weight) — see 01 Domains/Cross Domain/Personnel Management/
Selection/ResumeScreening/README.md, "Organization Intelligence — OPEN /
TBD." No employer-quality score, employer-training score, external employer
research, or employer-enrichment logic exists here or anywhere else in
Resume Screening.

This module exists only as the documented extension point: when
Organization Intelligence is itself defined, it plugs in here, consuming
`CandidateWorkHistory.employer` (currently preserved only as a Fact) as its
input — nothing in `core/experience_analysis.py`, `core/indicators.py`, or
`core/flags.py` should be modified to add employer reasoning; it belongs in
a module like this one instead.
"""

NOT_IMPLEMENTED = True
