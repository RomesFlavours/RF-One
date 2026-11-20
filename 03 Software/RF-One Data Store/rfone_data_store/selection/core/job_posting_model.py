"""Job Posting + Channel/Publication vocabulary (Task 5E). Mirrors every
other `core/*_model.py` module's role: fixed structural vocabulary only —
never a specific restaurant's actual posting content, channel list, or
publication data (task's own "do NOT hard-code these as the only possible
channels... use a generic configurable Channel model").
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Base Job Posting / Channel Variant status (task §4/§6) — a small, shared
# lifecycle: a draft is editable/versioned; approval is one explicit,
# recorded event on one specific version, never implied by editing.
# ---------------------------------------------------------------------------

DRAFT = "DRAFT"
APPROVED = "APPROVED"

POSTING_STATUSES = (DRAFT, APPROVED)

# ---------------------------------------------------------------------------
# Version content origin (task §4 — "preserve AI/system-generated draft,
# human-edited version").
# ---------------------------------------------------------------------------

SYSTEM_GENERATED = "SYSTEM_GENERATED"
HUMAN_EDITED = "HUMAN_EDITED"

CONTENT_ORIGINS = (SYSTEM_GENERATED, HUMAN_EDITED)


def validate_content_origin(value: str) -> None:
    if value not in CONTENT_ORIGINS:
        raise ValueError(f"Unknown Job Posting content origin {value!r}; expected one of {CONTENT_ORIGINS}")


# ---------------------------------------------------------------------------
# Publication (placement) status (task §9/§10).
# ---------------------------------------------------------------------------

PUBLICATION_DRAFT = "DRAFT"
PUBLICATION_PUBLISHED = "PUBLISHED"
PUBLICATION_PAUSED = "PAUSED"
PUBLICATION_STOPPED = "STOPPED"

PUBLICATION_STATUSES = (PUBLICATION_DRAFT, PUBLICATION_PUBLISHED, PUBLICATION_PAUSED, PUBLICATION_STOPPED)


def validate_publication_status(value: str) -> None:
    if value not in PUBLICATION_STATUSES:
        raise ValueError(f"Unknown publication status {value!r}; expected one of {PUBLICATION_STATUSES}")


# ---------------------------------------------------------------------------
# Post-publication edit reasons (task §7) — a practical, non-exhaustive
# starter set for the UI (mirrors `requirement_model.STARTER_CATEGORIES`'
# own "offered as convenience, never the only allowed values").
# ---------------------------------------------------------------------------

STARTER_CHANGE_REASONS = (
    "Too few applicants", "Low applicant quality", "Changed availability", "Changed role need",
    "Changed wording", "Channel-specific adjustment", "Other",
)

# ---------------------------------------------------------------------------
# Advisory channel recommendations (task §33) — advisory only; RF-One never
# automatically alters budget or a live publication based on these.
# ---------------------------------------------------------------------------

RECOMMEND_INCREASE = "INCREASE"
RECOMMEND_REDUCE = "REDUCE"
RECOMMEND_MAINTAIN = "MAINTAIN"
RECOMMEND_TEST = "TEST"

RECOMMENDATION_ACTIONS = (RECOMMEND_INCREASE, RECOMMEND_REDUCE, RECOMMEND_MAINTAIN, RECOMMEND_TEST)


# ---------------------------------------------------------------------------
# Application/First-Screening Question response types (task §16/§37) — kept
# intentionally small; restaurant-authored question TEXT is never defined
# here (task's own "do NOT hard-code those questions universally").
# ---------------------------------------------------------------------------

RESPONSE_TEXT = "TEXT"
RESPONSE_YES_NO = "YES_NO"
RESPONSE_NUMBER = "NUMBER"
RESPONSE_SCALE = "SCALE"

RESPONSE_TYPES = (RESPONSE_TEXT, RESPONSE_YES_NO, RESPONSE_NUMBER, RESPONSE_SCALE)


def validate_response_type(value: str) -> None:
    if value not in RESPONSE_TYPES:
        raise ValueError(f"Unknown Application Question response type {value!r}; expected one of {RESPONSE_TYPES}")


# ---------------------------------------------------------------------------
# Missing-Evidence Questionnaire status (task Part E).
# ---------------------------------------------------------------------------

QUESTIONNAIRE_PENDING = "PENDING"
QUESTIONNAIRE_ANSWERED = "ANSWERED"

QUESTIONNAIRE_STATUSES = (QUESTIONNAIRE_PENDING, QUESTIONNAIRE_ANSWERED)
