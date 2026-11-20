"""Selection identity-resolution vocabulary (Task 3C-FIX — CandidatePerson
identity resolution). Defines match-confidence tiers, possible-match review
status, and the normalization helpers `identity_service.py` uses to decide
whether a newly-imported résumé belongs to an already-known CandidatePerson.
Mirrors `core/signal_model.py`'s role: vocabulary + small pure functions
only, no persistence.

Matching evidence is limited to ordinary contact/identity fields already
captured by Selection (email, phone, name). No biometric or protected-
characteristic matching is performed or planned (task's own boundary).
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Match confidence tiers. Only VERY_STRONG (identical normalized email or
# phone) is ever used to auto-attach an Application to an existing person —
# STRONG/POSSIBLE always produce a `PersonMatchCandidate` suggestion for the
# Selezionatore to confirm or reject, never an automatic merge.
# ---------------------------------------------------------------------------

VERY_STRONG = "VERY_STRONG"
STRONG = "STRONG"
POSSIBLE = "POSSIBLE"

MATCH_CONFIDENCE_TIERS = (VERY_STRONG, STRONG, POSSIBLE)


# ---------------------------------------------------------------------------
# Possible-match review status (a `PersonMatchCandidate` row).
# ---------------------------------------------------------------------------

PENDING = "PENDING"
CONFIRMED = "CONFIRMED"
REJECTED = "REJECTED"

MATCH_STATUSES = (PENDING, CONFIRMED, REJECTED)


# ---------------------------------------------------------------------------
# Application identity-resolution origin — mirrors the SYSTEM_GENERATED/
# HUMAN_* pattern `core/fit_assessment_model.py` already uses for Fit
# Assessment/Signal Observation, applied here to "which CandidatePerson is
# this Application actually for."
# ---------------------------------------------------------------------------

SYSTEM_RESOLVED = "SYSTEM_RESOLVED"
HUMAN_CONFIRMED = "HUMAN_CONFIRMED"

IDENTITY_ORIGINS = (SYSTEM_RESOLVED, HUMAN_CONFIRMED)


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    return value or None


def normalize_phone(value: str | None) -> str | None:
    """Digits only. Returns None for anything with fewer than 7 digits —
    too short to be a reliable phone-identity match. A leading US/CA
    country code ("1" + 10 digits) is dropped so "+1 555-123-4567" and
    "555-123-4567" still match the same underlying number."""

    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) < 7:
        return None
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def normalize_name(value: str | None) -> str | None:
    if not value:
        return None
    collapsed = re.sub(r"[^a-z\s]", " ", value.strip().lower())
    collapsed = re.sub(r"\s+", " ", collapsed).strip()
    return collapsed or None


def _name_tokens(normalized_name: str | None) -> tuple[str, ...]:
    return tuple(normalized_name.split(" ")) if normalized_name else ()


def names_share_surname_and_initial(name_a: str | None, name_b: str | None) -> bool:
    """A conservative partial-name-match check used for POSSIBLE-tier
    suggestions only: same last token (surname) and same first-token
    initial — e.g. "Jamie Fox" vs "J. Fox". Both inputs must already be
    `normalize_name()`d."""

    tokens_a, tokens_b = _name_tokens(name_a), _name_tokens(name_b)
    if not tokens_a or not tokens_b:
        return False
    if tokens_a[-1] != tokens_b[-1]:
        return False
    return tokens_a[0][:1] == tokens_b[0][:1]
