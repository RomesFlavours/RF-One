"""Compliance / Rule Review vocabulary (Task 5F Part A). Mirrors every
other `core/*_model.py` module's role: fixed structural vocabulary only.

This module — and everything built on it — is explicitly NOT a legal
service. `DISCLAIMER` is the one sentence every Compliance Review surface
(UI and audit) must show; RF-One never presents a review as legal advice,
legal approval, legal certification, or a guarantee of compliance (task
§3) — it is an automated aid to help a human notice things worth a second
look before they judge a candidate.
"""

from __future__ import annotations

DISCLAIMER = (
    "This is an automated review to help identify potential issues that may need human judgment. "
    "It is not legal advice, legal approval, legal certification, or a guarantee of compliance."
)

# ---------------------------------------------------------------------------
# Reviewable object types (task §1) — the minimum clean abstraction: any
# Selection configuration object with restaurant-authored text/config may be
# registered here without this module needing to know its full schema (see
# `compliance_service._extract_reviewable_text`, which reads only common,
# optionally-present attribute names). Never hard-coded to one model.
# ---------------------------------------------------------------------------

REQUIREMENT = "REQUIREMENT"
PRIMARY_SCREENING_CRITERION = "PRIMARY_SCREENING_CRITERION"
SIGNAL_DEFINITION = "SIGNAL_DEFINITION"
REVIEW_PRIORITY_POLICY_RULE = "REVIEW_PRIORITY_POLICY_RULE"
APPLICATION_QUESTION_DEFINITION = "APPLICATION_QUESTION_DEFINITION"
PHONE_INTERVIEW_QUESTION_DEFINITION = "PHONE_INTERVIEW_QUESTION_DEFINITION"
ASSESSMENT_ITEM_DEFINITION = "ASSESSMENT_ITEM_DEFINITION"
SELECTION_OUTCOME_DEFINITION = "SELECTION_OUTCOME_DEFINITION"
JOB_POSTING_VERSION = "JOB_POSTING_VERSION"

OBJECT_TYPES = (
    REQUIREMENT, PRIMARY_SCREENING_CRITERION, SIGNAL_DEFINITION, REVIEW_PRIORITY_POLICY_RULE,
    APPLICATION_QUESTION_DEFINITION, PHONE_INTERVIEW_QUESTION_DEFINITION, ASSESSMENT_ITEM_DEFINITION,
    SELECTION_OUTCOME_DEFINITION, JOB_POSTING_VERSION,
)


def validate_object_type(value: str) -> None:
    if value not in OBJECT_TYPES:
        raise ValueError(f"Unknown compliance-reviewable object type {value!r}; expected one of {OBJECT_TYPES}")


# ---------------------------------------------------------------------------
# Severity (task §7) — small and understandable; internal stable category
# codes may be more granular (below), but user-facing severity is always
# one of exactly these three.
# ---------------------------------------------------------------------------

INFO = "INFO"
WARNING = "WARNING"
HIGH_CONCERN = "HIGH_CONCERN"

SEVERITIES = (INFO, WARNING, HIGH_CONCERN)


def validate_severity(value: str) -> None:
    if value not in SEVERITIES:
        raise ValueError(f"Unknown compliance severity {value!r}; expected one of {SEVERITIES}")


# ---------------------------------------------------------------------------
# Warning category (task §2) — a stable internal identifier; conversational
# `explanation` text (never these codes) is what a human actually reads.
# ---------------------------------------------------------------------------

PROTECTED_CHARACTERISTIC = "PROTECTED_CHARACTERISTIC"
POTENTIAL_PROXY = "POTENTIAL_PROXY"
NON_JOB_RELATED = "NON_JOB_RELATED"
APPEARANCE_BODY = "APPEARANCE_BODY"
NATIONALITY_ETHNICITY_RACE = "NATIONALITY_ETHNICITY_RACE"
SEX_GENDER = "SEX_GENDER"
AGE = "AGE"
RELIGION = "RELIGION"
DISABILITY = "DISABILITY"
FAMILY_MARITAL_PREGNANCY = "FAMILY_MARITAL_PREGNANCY"
VAGUE_SUBJECTIVE = "VAGUE_SUBJECTIVE"
PERSONAL_LIFE = "PERSONAL_LIFE"
STAGE_RELIABILITY = "STAGE_RELIABILITY"
MISSING_EVIDENCE_AS_NEGATIVE = "MISSING_EVIDENCE_AS_NEGATIVE"
OTHER = "OTHER"

WARNING_CATEGORIES = (
    PROTECTED_CHARACTERISTIC, POTENTIAL_PROXY, NON_JOB_RELATED, APPEARANCE_BODY, NATIONALITY_ETHNICITY_RACE,
    SEX_GENDER, AGE, RELIGION, DISABILITY, FAMILY_MARITAL_PREGNANCY, VAGUE_SUBJECTIVE, PERSONAL_LIFE,
    STAGE_RELIABILITY, MISSING_EVIDENCE_AS_NEGATIVE, OTHER,
)


# ---------------------------------------------------------------------------
# Human disposition actions (task §5/§8) — the ONLY ways a reviewed rule's
# text/config may actually change or be acted on; RF-One never silently
# rewrites anything itself.
# ---------------------------------------------------------------------------

ACCEPT_REWRITE = "ACCEPT_REWRITE"
EDIT_MANUALLY = "EDIT_MANUALLY"
KEEP_ORIGINAL = "KEEP_ORIGINAL"
DEACTIVATE = "DEACTIVATE"
ACKNOWLEDGE_HIGH_CONCERN = "ACKNOWLEDGE_HIGH_CONCERN"

DISPOSITION_ACTIONS = (ACCEPT_REWRITE, EDIT_MANUALLY, KEEP_ORIGINAL, DEACTIVATE, ACKNOWLEDGE_HIGH_CONCERN)

# Dispositions that resolve a HIGH_CONCERN warning for activation purposes
# (task §8) — changing the text (ACCEPT_REWRITE/EDIT_MANUALLY) always
# triggers a fresh review of the NEW text, so activation is governed by
# whatever that new review finds; ACKNOWLEDGE_HIGH_CONCERN is the explicit,
# reasoned override that keeps the original text active anyway.
# `KEEP_ORIGINAL` alone does NOT resolve a HIGH_CONCERN block — a human
# choosing it has decided not to change the rule, not to override the
# concern; see `compliance_service.assert_activation_allowed`.
ACTIVATION_RESOLVING_ACTIONS = (ACCEPT_REWRITE, EDIT_MANUALLY, ACKNOWLEDGE_HIGH_CONCERN)


def validate_disposition_action(value: str) -> None:
    if value not in DISPOSITION_ACTIONS:
        raise ValueError(f"Unknown compliance disposition action {value!r}; expected one of {DISPOSITION_ACTIONS}")


ENGINE_VERSION = "SELECTION_COMPLIANCE_RULES_V1"
