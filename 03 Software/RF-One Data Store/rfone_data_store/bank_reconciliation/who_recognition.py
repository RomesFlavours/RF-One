"""WHO identity (BANK_WHO_WHY_CANONICAL_CATALOG_001).

Two questions only: the identity key of a WHO name (`who_key`), and which
ACTIVE canonical WHO a typed name already is (`CanonicalWhoResolver`), so a
duplicate WHO is never created.

The structural WHO recognizer that used to live here
(BANK_HISTORICAL_WHO_RECOGNITION_001: parsing the bank text into
DETERMINISTIC / PROPOSED / UNRESOLVED / STRUCTURAL recognitions, persisted in
`bank_who_recognitions`) belonged to the old rule system and was removed with
it (BANK_RULES_RESET_001).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import accounting_dedup


def who_key(name: str | None) -> str:
    """Exact identity key for a WHO name — the same normalization the
    accounting key and the Supplier resolver compare on (punctuation to
    spaces, upper case). Two names are one WHO only when these are equal."""
    return accounting_dedup.normalize_payee(name)


RESOLVED_BY_NAME = "NAME"
RESOLVED_BY_ALIAS = "ALIAS"


class CanonicalWhoResolver:
    """Finds the ACTIVE canonical WHO a recognised name already belongs to,
    before anything is created (BANK_WHO_WHY_CANONICAL_CATALOG_001).

    A canonical WHO may have absorbed many bank spellings: a WHO merge moves
    every fragment's aliases onto the kept WHO, records the fragment's old
    name as an alias, and marks the fragment INACTIVE.
    Looking a name up by `canonical_name` alone would then miss "Publix" for
    "PUBLIX", and would recreate an INACTIVE fragment. This resolver reads
    only what already exists — canonical names and `BankOccurrenceAlias`
    rows — and never invents a link:

    1. exactly one ACTIVE WHO whose name has this identity key;
    2. exactly one ACTIVE WHO holding an alias with this identity key.

    When none applies but an INACTIVE WHO carries the name, nothing is
    created and nothing is reactivated: the name is held for a person.
    Two active candidates are held the same way.
    Nothing here ever reads or sets a WHY."""

    def __init__(self, session: Session):
        self.by_id: dict[int, m.BankOccurrence] = {}
        self.active_by_name: dict[str, m.BankOccurrence] = {}
        self.active_by_key: dict[str, set[int]] = {}
        self.inactive_by_key: dict[str, list[m.BankOccurrence]] = {}
        for occurrence in session.scalars(select(m.BankOccurrence)):
            self.by_id[occurrence.id] = occurrence
            key = who_key(occurrence.canonical_name)
            if occurrence.status == "ACTIVE":
                self.active_by_name[occurrence.canonical_name] = occurrence
                self.active_by_key.setdefault(key, set()).add(occurrence.id)
            else:
                self.inactive_by_key.setdefault(key, []).append(occurrence)
        self.alias_owners: dict[str, set[int]] = {}
        for occurrence_id, alias_key in session.execute(
            select(m.BankOccurrenceAlias.occurrence_id, m.BankOccurrenceAlias.alias_key)
        ):
            if alias_key and self._active(occurrence_id):
                self.alias_owners.setdefault(alias_key, set()).add(occurrence_id)

    def _active(self, occurrence_id: int | None) -> bool:
        occurrence = self.by_id.get(occurrence_id)
        return occurrence is not None and occurrence.status == "ACTIVE"

    def by_identity(self, *names: str | None) -> "tuple[m.BankOccurrence | None, str | None, str | None]":
        """(active WHO, how it was found, why it was held for a person).

        All three None means the identity is genuinely new and the ordinary
        creation path may follow."""
        for name in names:
            if name and name in self.active_by_name:
                return self.active_by_name[name], RESOLVED_BY_NAME, None
        keys = [k for k in dict.fromkeys(who_key(n) for n in names if n) if k]
        for key in keys:
            owners = self.active_by_key.get(key, set())
            if len(owners) == 1:
                return self.by_id[next(iter(owners))], RESOLVED_BY_NAME, None
            if len(owners) > 1:
                return None, None, f"several active WHO share the identity {key!r}"
        for key in keys:
            owners = self.alias_owners.get(key, set())
            if len(owners) == 1:
                return self.by_id[next(iter(owners))], RESOLVED_BY_ALIAS, None
            if len(owners) > 1:
                return None, None, f"the alias {key!r} belongs to several active WHO"
        for key in keys:
            inactive = self.inactive_by_key.get(key)
            if inactive:
                held = ", ".join(f"#{o.id} {o.canonical_name!r}" for o in inactive)
                return None, None, (
                    f"the name matches INACTIVE WHO {held} and no active canonical WHO holds it "
                    "as an alias; it is neither recreated nor reactivated"
                )
        return None, None, None
