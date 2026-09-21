"""enforce that who never determines why by itself

Revision ID: a3d7f60b9e15
Revises: f2b8e4a61c93
Create Date: 2026-09-21

BANK_WHO_WHY_INVARIANT_001 — a CONSTRAINT plus a deterministic backfill of
recognition-rule scope. No transaction is reclassified, no decision row is
rewritten, no raw source fact is touched, no account changes and no
accounting meaning changes.

The invariant

    WHO NEVER DETERMINES WHY BY ITSELF.

A counterparty may be recognised automatically. The accounting purpose of
a payment may not be concluded from having recognised them — not for a
person, and not for a supplier either. Get Better Cleaning having been
cleaning nine times is evidence a human may weigh; it is not a rule that
Get Better Cleaning can only ever mean cleaning.

What this revision changes

`bank_recognition_rules.determines_purpose` was introduced by
`f2b8e4a61c93` as a per-rule permission, TRUE by default, which is what
every rule written before it did: match a description, resolve the Who,
and take the What from that Who's default chain. That is "identity alone
is sufficient", so:

  * every DESCRIPTION rule is set to `determines_purpose = FALSE`. Such a
    rule keeps recognising its counterparty exactly as before — what it
    stops doing is answering the accounting question on the strength of
    that recognition alone. A matching transaction whose own evidence
    proves a purpose is still classified automatically; one whose
    evidence proves nothing now reaches a human, with the Who already
    identified and the Who's usual Why shown as a suggestion;
  * a CHECK constraint makes the combination unreachable from now on, so
    the invariant is a property of the database rather than a discipline
    in the service layer.

MEMO rules are untouched: their pattern is purpose wording that would
match the same memo on any counterparty, so they carry no identity.

Scope of the behavioural change, stated plainly rather than buried: rules
that used to auto-apply from identity alone will now produce
NEEDS_HUMAN_REVIEW instead, for exactly those transactions whose own text
proves no purpose. That is the Product Owner's decision, not a side
effect. Already-recorded decisions are NOT revisited — this revision
writes to `bank_recognition_rules` and to nothing else.

Runs on SQLite and PostgreSQL. SQLite cannot add a CHECK constraint to an
existing table, so the constraint arrives through an Alembic batch
rebuild there and through `op.create_check_constraint` on PostgreSQL. The
backfill runs BEFORE the constraint is added, so a database holding rules
the constraint forbids is corrected rather than refused.

Downgrade drops the constraint only. The scope values are deliberately
NOT restored: putting `determines_purpose = TRUE` back onto description
rules would re-enable a semantics the domain no longer has, and a
downgrade that quietly re-creates a forbidden capability is worse than
one that leaves the data safe.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3d7f60b9e15'
down_revision: Union[str, Sequence[str], None] = 'f2b8e4a61c93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RULES = "bank_recognition_rules"

_CHECK_NAME = "ck_bank_recognition_rule_purpose_scope"
_CHECK_CONDITION = "determines_purpose = 0 OR match_field = 'MEMO'"


def upgrade() -> None:
    """Demote every description rule to WHO-only, then make it structural."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    demoted = bind.execute(sa.text(
        f"SELECT count(*) FROM {RULES} "
        "WHERE determines_purpose <> 0 AND match_field <> 'MEMO'"
    )).scalar() or 0

    bind.execute(sa.text(
        f"UPDATE {RULES} SET determines_purpose = 0 "
        "WHERE determines_purpose <> 0 AND match_field <> 'MEMO'"
    ))

    if is_sqlite:
        with op.batch_alter_table(RULES, schema=None, recreate="always") as batch_op:
            batch_op.create_check_constraint(_CHECK_NAME, _CHECK_CONDITION)
    else:
        op.create_check_constraint(_CHECK_NAME, RULES, _CHECK_CONDITION)

    # Said out loud: this is a behavioural change for the rules it names,
    # and an operator upgrading a populated database should see how many.
    print(
        f"[a3d7f60b9e15] description rules demoted to WHO-only: {demoted}. They still "
        "recognise their counterparty; they no longer decide the accounting purpose."
    )


def downgrade() -> None:
    """Drop the constraint. The scope values stay as they are — see above."""
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(RULES, schema=None, recreate="always") as batch_op:
            batch_op.drop_constraint(_CHECK_NAME, type_="check")
    else:
        op.drop_constraint(_CHECK_NAME, RULES, type_="check")
