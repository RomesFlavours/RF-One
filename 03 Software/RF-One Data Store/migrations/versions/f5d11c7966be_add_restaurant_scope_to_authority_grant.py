"""widen authority_grants.scope_type to allow RESTAURANT
(TASK_TIPS_RESTAURANT_AUTHORITY_SCOPE_001)

Revision ID: f5d11c7966be
Revises: b4e7c1a9f3d6
Create Date: 2026-09-14 00:00:00.000000

One additive, non-destructive change: widens `authority_grants`'
`ck_authority_grant_scope_type` CHECK constraint from
`('CORPORATE', 'BRAND', 'OPERATIONAL_UNIT', 'OPERATIONAL_AREA', 'GLOBAL')`
to also allow `'RESTAURANT'` — no column, index, or table is added or
removed, and no existing row's data changes (every existing grant's
`scope_type` is already one of the previously-allowed values, so the wider
constraint accepts every existing row unchanged).

Closes a real Authority-model gap reported (not silently worked around) in
`rfone_data_store/tips/payment_cycle_service.py`'s own prior module
docstring: Tips' Approve & Pay gate could previously only be scoped GLOBAL
(authorizing every Restaurant at once) or not scoped at a Restaurant
granularity at all, because `AuthorityGrant.scope_type` had no `RESTAURANT`
value — unlike `Position`/`ProcessOwnership`'s own `POSITION_SCOPE_KINDS`,
which already includes `POSITION_SCOPE_RESTAURANT`. This migration adds the
matching value to `AuthorityGrant`'s own, separate scope vocabulary (the two
enums remain independent — see `models.py`'s updated comment above
`AUTHORITY_SCOPE_KINDS`), so a grant can now read
`scope_type='RESTAURANT', scope_id=<restaurants.id>`, letting one Acting
Identity hold independent Approve & Pay authority for one, several, or (via
a GLOBAL grant, unaffected by this change) every Restaurant.

SQLite requires `batch_alter_table` to replace a CHECK constraint (SQLite
has no native `ALTER TABLE ... DROP CONSTRAINT`) — this recreates the table
under the hood and copies every row across unchanged, the same idiom already
used by this migration set's own prior CHECK-constraint changes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5d11c7966be'
down_revision: Union[str, Sequence[str], None] = 'b4e7c1a9f3d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('authority_grants', schema=None) as batch_op:
        batch_op.drop_constraint('ck_authority_grant_scope_type', type_='check')
        batch_op.create_check_constraint(
            'ck_authority_grant_scope_type',
            "scope_type IN ('CORPORATE', 'BRAND', 'OPERATIONAL_UNIT', 'OPERATIONAL_AREA', 'RESTAURANT', 'GLOBAL')",
        )


def downgrade() -> None:
    """Downgrade schema.

    Narrows the constraint back — this would reject any 'RESTAURANT'-scoped
    row created while this migration was applied. Consistent with every
    other CHECK-widening migration in this set, no data migration/deletion
    is performed here; a downgrade with existing RESTAURANT-scoped grants
    present will fail loudly (constraint violation) rather than silently
    drop data.
    """
    with op.batch_alter_table('authority_grants', schema=None) as batch_op:
        batch_op.drop_constraint('ck_authority_grant_scope_type', type_='check')
        batch_op.create_check_constraint(
            'ck_authority_grant_scope_type',
            "scope_type IN ('CORPORATE', 'BRAND', 'OPERATIONAL_UNIT', 'OPERATIONAL_AREA', 'GLOBAL')",
        )
