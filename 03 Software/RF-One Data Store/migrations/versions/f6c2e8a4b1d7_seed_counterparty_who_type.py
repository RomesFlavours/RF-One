"""seed the COUNTERPARTY WHO type (BANK_CONFIGURATION_001, decision D10)

Revision ID: f6c2e8a4b1d7
Revises: e5b1d7c3a9f2
Create Date: 2026-09-29 18:00:00.000000

Data-only, additive, idempotent. COUNTERPARTY is the WHO type every WHO
created on the Bank Configuration page receives (decision D5), so it is
system reference data: a freshly migrated database must have it. Until now
only `apply_deterministic_bank_classification.py` created it, on the
databases that script had run against.

Identified by its canonical CODE, never by an id. If a COUNTERPARTY row
already exists it is left exactly as it is; otherwise one row is inserted
with the semantics that script already established (same code, name and
description, frozen here so this revision never depends on code that may
later change). The INSERT is conditional and the code is UNIQUE, so no run
can create a duplicate. No other WHO type is added.

Downgrade removes nothing: the row may predate this revision, and WHOs
reference it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6c2e8a4b1d7'
down_revision: Union[str, Sequence[str], None] = 'e5b1d7c3a9f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CODE = "COUNTERPARTY"
NAME = "Counterparty"
DESCRIPTION = (
    "The party a bank movement concerns, where the movement's own description identifies it. "
    "Deliberately generic: Supplier is only one possible kind, and a bank line rarely says which."
)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            "INSERT INTO bank_occurrence_types (code, name, description, status) "
            "SELECT :code, :name, :description, 'ACTIVE' "
            "WHERE NOT EXISTS (SELECT 1 FROM bank_occurrence_types WHERE code = :code)"
        ).bindparams(code=CODE, name=NAME, description=DESCRIPTION)
    )


def downgrade() -> None:
    """Downgrade schema — intentionally nothing (see module docstring)."""
