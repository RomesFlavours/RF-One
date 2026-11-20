"""WHO names in upper case; a WHO with one possible WHY has it as default

Revision ID: a9d3f5b7c1e2
Revises: f3b7d9a1c5e8
Create Date: 2026-10-09

DATA ONLY — no schema change. Product Owner request 2026-10-09:

  * BANK_WHO_UPPERCASE_001 — every `bank_occurrences.canonical_name` is
    stored in upper case without outer spaces. Ids and every reference stay
    as they are. Two WHO that would end with the SAME name are left
    unchanged and reported here, for a person to merge (never merged
    automatically).
  * BANK_WHO_SINGLE_DEFAULT_WHY_001 — a WHO with exactly one active possible
    WHY gets that WHY as its default WHY, when the WHY can be a default (it
    has a WHAT). No transaction is touched.

Downgrade changes nothing: the previous spelling of a name is not kept
(decisions keep their own name snapshots).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a9d3f5b7c1e2'
down_revision: Union[str, Sequence[str], None] = 'f3b7d9a1c5e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, canonical_name FROM bank_occurrences")).all()
    groups: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for occurrence_id, name in rows:
        groups[(name or "").strip().upper()].append((occurrence_id, name))
    renamed, held = 0, []
    for normalized, members in groups.items():
        if len(members) > 1:
            held.append(f"{normalized!r}: " + ", ".join(f"#{i} {n!r}" for i, n in members))
            continue
        occurrence_id, name = members[0]
        if name != normalized and normalized:
            bind.execute(sa.text("UPDATE bank_occurrences SET canonical_name = :n WHERE id = :i"),
                         {"n": normalized, "i": occurrence_id})
            renamed += 1

    defaults = 0
    single = bind.execute(sa.text("""
        SELECT a.occurrence_id, MIN(a.transaction_reason_id), COUNT(*), MIN(r.accounting_classification_id)
        FROM bank_occurrence_reason_associations a
        JOIN bank_transaction_reasons r ON r.id = a.transaction_reason_id
        WHERE a.active = 1 AND r.status = 'ACTIVE'
        GROUP BY a.occurrence_id
    """)).all()
    for occurrence_id, reason_id, count, what_id in single:
        if count != 1 or what_id is None:
            continue
        defaults += bind.execute(sa.text(
            "UPDATE bank_occurrences SET default_transaction_reason_id = :r "
            "WHERE id = :i AND (default_transaction_reason_id IS NULL OR default_transaction_reason_id != :r)"),
            {"r": reason_id, "i": occurrence_id}).rowcount or 0

    print(f"[a9d3f5b7c1e2] WHO names normalized to upper case: {renamed}. "
          f"Default WHY set from a single possible WHY: {defaults}. "
          f"Names left unchanged because they would collide (merge them by hand): {len(held)}"
          + ("" if not held else " — " + "; ".join(held)))


def downgrade() -> None:
    # Data only: nothing to undo structurally, and the previous spellings are not kept.
    pass
