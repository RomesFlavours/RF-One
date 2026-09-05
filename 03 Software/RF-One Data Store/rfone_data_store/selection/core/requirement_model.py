"""Selection Requirement vocabulary (Task 3A; 01 Domains/Cross Domain/Selection/
SelectionRequirement.md). Defines the generic, industry-agnostic MEANING of
Criticality, Trainability and Assessment Stage — never a restaurant's
specific requirements, never Rome's Flavours' hiring philosophy. Which
requirements exist, their wording, and their values for these fields are
always restaurant/template DATA (`RequirementTemplate`/`RequirementSet` in
`.. models`, populated via `selection/requirements_service.py`), never
hard-coded here.

This module defines vocabulary only — no dataclass mirror of
`RequirementSet`/`Requirement` exists here (unlike `core/profile.py`'s
`CandidateCVProfile`). A Requirement Set has no parser producing it
independently of persistence: it is always directly authored (by a user, or
by cloning a template) through `requirements_service.py`, which is the
service/model layer the task asks for and operates on the SQLAlchemy rows
directly (the same pattern `selection/normalization.py`'s
`reprocess_candidate()` already uses for persisted Work History rows) —
introducing a second, parallel plain-dataclass shape here would be exactly
the "elaborate new framework" the task says not to build.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Criticality (task §3) — the restaurant's own judgment of importance/
# consequence. RF-One does not decide which requirements ARE must-haves;
# it only defines what these four levels mean.
# ---------------------------------------------------------------------------

MUST_HAVE = "MUST_HAVE"  # The restaurant considers this necessary for the role.
PREFERRED = "PREFERRED"  # Valuable but not mandatory.
OPTIONAL = "OPTIONAL"  # Positive but not important enough to materially drive selection.
DISQUALIFIER = "DISQUALIFIER"  # Evidence of this condition may make the candidate unsuitable.

CRITICALITY_LEVELS = (MUST_HAVE, PREFERRED, OPTIONAL, DISQUALIFIER)


# ---------------------------------------------------------------------------
# Trainability (task §4) — whether THIS restaurant considers a requirement
# teachable. Never decided by RF-One: the same requirement (e.g. "menu
# knowledge") may be TRAINABLE for one restaurant/template and
# NOT_TRAINABLE for another.
# ---------------------------------------------------------------------------

TRAINABLE = "TRAINABLE"
NOT_TRAINABLE = "NOT_TRAINABLE"
PARTIALLY_TRAINABLE = "PARTIALLY_TRAINABLE"
TRAINABILITY_UNKNOWN = "UNKNOWN"

TRAINABILITY_LEVELS = (TRAINABLE, NOT_TRAINABLE, PARTIALLY_TRAINABLE, TRAINABILITY_UNKNOWN)


# ---------------------------------------------------------------------------
# Assessment Stage (task §5) — WHERE a requirement may legitimately be
# assessed; a Requirement may declare more than one. Task 3A defines this
# only — it does not perform any assessment at any stage.
# ---------------------------------------------------------------------------

RESUME = "RESUME"
PHONE_INTERVIEW = "PHONE_INTERVIEW"
IN_PERSON_INTERVIEW = "IN_PERSON_INTERVIEW"
PRACTICAL_ASSESSMENT = "PRACTICAL_ASSESSMENT"
REFERENCE_CHECK = "REFERENCE_CHECK"
OTHER_STAGE = "OTHER"

ASSESSMENT_STAGES = (
    RESUME, PHONE_INTERVIEW, IN_PERSON_INTERVIEW, PRACTICAL_ASSESSMENT, REFERENCE_CHECK, OTHER_STAGE,
)


# ---------------------------------------------------------------------------
# Requirement categories (task §7) — a practical, non-exhaustive starter
# set for organizing requirements in the UI. Restaurants/templates are free
# to use any category string; this list is offered as UI convenience
# (dropdown choices), never enforced as the only allowed values.
# ---------------------------------------------------------------------------

STARTER_CATEGORIES = (
    "Attitude / Behavioral Traits",
    "Teamwork",
    "Trainability / Learning",
    "Customer Orientation",
    "Accountability / Work Ethic",
    "Experience",
    "Role Skills",
    "Technical Knowledge",
    "Sales",
    "Leadership / Management",
    "Communication",
    "Availability / Practical Constraints",
    "Certifications / Legal Requirements",
    "Other",
)
