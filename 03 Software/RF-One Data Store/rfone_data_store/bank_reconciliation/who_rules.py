"""WHO lookups (formerly the simple WHO Rule, BANK_SIMPLE_WHO_RULE_001).

BANK_RULES_RESET_001 removed the old (non-AI) WHO rules: nothing here saves,
applies or lists a rule any more. What remains answers one question — which
ACTIVE WHO a typed name already is — through the one canonical resolver
(`who_recognition.CanonicalWhoResolver`), so the "new WHO" dialog, the
manual reconciliation and the AI rules never create a duplicate WHO.

Nothing here writes.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from . import who_recognition as wr

# The decision fields that describe PURPOSE. A WHO given to an existing
# transaction carries them over from its current decision verbatim.
_PURPOSE_FIELDS = (
    "food_cost_snapshot", "operative_snapshot", "deductible_snapshot", "what_label_snapshot",
    "transaction_reason_name_snapshot", "accounting_classification_id",
    "accounting_classification_code_snapshot", "accounting_classification_name_snapshot",
    "accounting_statement_type_snapshot",
)


def existing_identity(session: Session, name: str | None) -> "tuple[m.BankOccurrence | None, str | None]":
    """The ACTIVE WHO a typed name already IS, by exact identity only — the
    same name, the same identity key (`who_key`), or an active alias with
    that key — through `CanonicalWhoResolver.by_identity`, the resolver WHO
    recognition uses. Returns (WHO, None), (None, why it is ambiguous or
    held) or (None, None) when the name is genuinely new. Similar-looking
    names are NOT identity: they are only ever offered to the operator."""
    clean = (name or "").strip()
    if not clean:
        return None, None
    occurrence, _how, held = wr.CanonicalWhoResolver(session).by_identity(clean)
    return occurrence, held


def check_new_who(session: Session, name: str | None) -> "tuple[m.BankOccurrence | None, str]":
    """Validate a WHO the operator asked to create, WITHOUT creating it.

    Returns (existing ACTIVE WHO to reuse, name) when the identity already
    exists — a duplicate is never created — or (None, clean name) when it
    is new. Refuses an empty or ambiguous name, and a name that belongs to
    a merged (INACTIVE) WHO, which is neither recreated nor reactivated."""
    clean = " ".join((name or "").split())
    if not clean:
        raise ValueError("Type the name of the WHO to create.")
    if sum(ch.isalpha() for ch in clean) < 2:
        raise ValueError(f"“{clean}” is too short to name a WHO.")
    if len(clean) > 255:
        raise ValueError("A WHO name is at most 255 characters.")
    occurrence, held = existing_identity(session, clean)
    if occurrence is not None:
        return occurrence, occurrence.canonical_name
    if held is not None:
        raise ValueError(
            f"“{clean}” cannot be created: {held}. Choose an existing WHO instead."
        )
    # BANK_WHO_UPPERCASE_001 — the name is stored in upper case; any other
    # WHO with the same name (case / outer spaces aside) is not a new one.
    from .classification import normalize_who_name
    upper = normalize_who_name(clean)
    same = next((o for o in session.scalars(select(m.BankOccurrence))
                 if normalize_who_name(o.canonical_name) == upper), None)
    if same is not None and same.status == "ACTIVE":
        return same, same.canonical_name
    if same is not None:
        raise ValueError(
            f"A WHO named “{same.canonical_name}” already exists but is inactive (merged). "
            "Choose its active WHO instead."
        )
    return None, upper


def who_options(session: Session, *, search: str = "", limit: int = 25) -> dict:
    """What the modal's creatable WHO combo shows for a typed text.

    * `matches` — ACTIVE WHO whose name contains the text;
    * `identity` — the ACTIVE WHO the text already IS (same name, identity
      key or alias), which is offered instead of creating a duplicate;
    * `similar` — ACTIVE WHO that only look alike (one name begins with the
      other, word by word): shown for the operator to decide, never chosen;
    * `create` — the name to offer as "Create", or None when the identity
      already exists or the text is empty.

    Bounded: one query over active WHO names, never rendered as a list."""
    needle = " ".join((search or "").split())
    if not needle:
        return {"matches": [], "identity": None, "similar": [], "create": None}
    matches = [
        {"id": occurrence_id, "name": name} for occurrence_id, name in session.execute(
            select(m.BankOccurrence.id, m.BankOccurrence.canonical_name)
            .where(m.BankOccurrence.status == "ACTIVE",
                   func.upper(m.BankOccurrence.canonical_name).contains(needle.upper()))
            .order_by(func.upper(m.BankOccurrence.canonical_name)).limit(limit))
    ]
    identity, held = existing_identity(session, needle)
    key = wr.who_key(needle)
    similar = []
    if key:
        shown = {match["id"] for match in matches} | ({identity.id} if identity else set())
        for occurrence_id, name in session.execute(
                select(m.BankOccurrence.id, m.BankOccurrence.canonical_name)
                .where(m.BankOccurrence.status == "ACTIVE")):
            other = wr.who_key(name)
            if occurrence_id in shown or not other or len(other) < 4:
                continue
            if key.startswith(other + " ") or other.startswith(key + " "):
                similar.append({"id": occurrence_id, "name": name})
        similar = sorted(similar, key=lambda o: o["name"].upper())[:10]
    inactive_exact = session.scalar(select(func.count(m.BankOccurrence.id)).where(
        m.BankOccurrence.canonical_name == needle, m.BankOccurrence.status != "ACTIVE"))
    can_create = identity is None and held is None and not inactive_exact and sum(
        ch.isalpha() for ch in needle) >= 2
    return {
        "matches": matches,
        "identity": {"id": identity.id, "name": identity.canonical_name} if identity else None,
        "similar": similar,
        "create": needle if can_create else None,
        "held": held,
    }
