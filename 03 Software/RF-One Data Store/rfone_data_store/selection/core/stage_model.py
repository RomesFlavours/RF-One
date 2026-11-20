"""Selection Stage vocabulary (Task 5A). Defines WHERE an Application
currently sits in the Selection process — a concept deliberately kept
separate from `core/application_model.py`'s workflow-status vocabulary
(the operational DECISION about the Application) and from
`core/outcome_model.py` (the restaurant-configurable OUTCOME). Mirrors
every other `core/*_model.py` module's role: vocabulary + nothing else, no
persistence, no ordering/sequence logic.

Deliberately NOT a state machine: the Selezionatore has total freedom to
move an Application to any Stage, forward, backward, repeated, or skipped
(task §2/§10/§32) — this module defines the fixed set of Stage NAMES only,
never a required order between them. Application Received/Primary
Screening/Phone Interview/In-Person Practical are the Stages of the
Selection process this repository currently implements; the tuple is the
one place a genuinely new future Stage name would be added.
"""

from __future__ import annotations

APPLICATION_RECEIVED = "APPLICATION_RECEIVED"
PRIMARY_SCREENING = "PRIMARY_SCREENING"
PHONE_INTERVIEW = "PHONE_INTERVIEW"
IN_PERSON_PRACTICAL = "IN_PERSON_PRACTICAL"

STAGES = (APPLICATION_RECEIVED, PRIMARY_SCREENING, PHONE_INTERVIEW, IN_PERSON_PRACTICAL)

DEFAULT_STAGE = APPLICATION_RECEIVED


def validate_stage(stage: str) -> None:
    if stage not in STAGES:
        raise ValueError(f"Unknown Selection Stage {stage!r}; expected one of {STAGES}")
