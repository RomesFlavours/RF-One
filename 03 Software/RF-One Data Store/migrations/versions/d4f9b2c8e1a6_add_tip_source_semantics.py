"""add tip_distribution_rule_versions.source_semantics (ORDER_SERVICE_OWNER_SOURCE_SEMANTICS_001)

Revision ID: d4f9b2c8e1a6
Revises: c3e8a4f1b6d9
Create Date: 2026-09-19 00:00:00.000000

Corrects a conceptual defect found against real Winter Park data: a Tip
Distribution Rule's SOURCE side could previously only qualify an Order via
`source_role_id` (the Order-owning Employee must hold that RestaurantRole
via `EmployeeAssignment`) — but "Service Owner" is `Order.employee_id`
itself, regardless of that Employee's current RestaurantRole (a Server, a
Team Leader, or a Manager who owns an Order should all qualify identically
as its Service Owner).

Additive and backward-compatible:
- Adds `source_semantics` (NOT NULL, `'ROLE'` or `'ORDER_SERVICE_OWNER'`),
  backfilled to `'ROLE'` for every existing row via `server_default` at add
  time (preserving the exact current meaning of every historical Version,
  including the live Winter Park `RuleVersion` 1 — nothing about its
  behavior changes) — then the server default is dropped so every FUTURE
  row must state its source semantics explicitly, never silently inheriting
  one.
- Relaxes `source_role_id` to nullable — required exactly when
  `source_semantics = 'ROLE'`, and must be NULL exactly when
  `source_semantics = 'ORDER_SERVICE_OWNER'` (both enforced by a new CHECK
  constraint, not application code alone). No existing row's `source_role_id`
  value is touched.

No `TipDistributionRule`/`TipDistributionRuleVersion` row is deleted,
recreated with different data, or has any other column altered. Recipient
determination (Host Role, ACTIVE_AT_SETTLEMENT, EQUAL, SOURCE_RETAINS) is
completely unaffected by this migration.

Cross-dialect fix (AWS_RDS_ALEMBIC_RECONCILIATION_001, found applying this
migration for real against PostgreSQL): the original second CHECK
constraint name, `ck_tip_distribution_rule_version_source_role_id_matches_semantics`
(65 characters), silently exceeded SQLite's unenforced identifier length
but fails outright on PostgreSQL, whose `NAMEDATALEN` limit rejects any
identifier over 63 characters (`IdentifierError`, empirically confirmed
against the real RDS target — the whole upgrade transaction rolled back
cleanly, no partial state). Shortened to
`ck_tip_dist_rule_version_source_role_matches_semantics` (54 characters,
same meaning, still unique and descriptive). No behavior change.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4f9b2c8e1a6'
down_revision: Union[str, Sequence[str], None] = 'c3e8a4f1b6d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('tip_distribution_rule_versions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('source_semantics', sa.String(length=32), nullable=False, server_default='ROLE'),
        )
        batch_op.alter_column('source_role_id', existing_type=sa.Integer(), nullable=True)
        batch_op.create_check_constraint(
            'ck_tip_distribution_rule_version_source_semantics',
            "source_semantics IN ('ROLE','ORDER_SERVICE_OWNER')",
        )
        batch_op.create_check_constraint(
            'ck_tip_dist_rule_version_source_role_matches_semantics',
            "(source_semantics = 'ROLE' AND source_role_id IS NOT NULL) OR "
            "(source_semantics = 'ORDER_SERVICE_OWNER' AND source_role_id IS NULL)",
        )

    # Drop the server default now that every existing row has been
    # backfilled — every future INSERT must state source_semantics
    # explicitly, never silently inheriting 'ROLE'.
    with op.batch_alter_table('tip_distribution_rule_versions', schema=None) as batch_op:
        batch_op.alter_column('source_semantics', existing_type=sa.String(length=32), server_default=None)


def downgrade() -> None:
    """Downgrade schema.

    Refuses if any row already uses ORDER_SERVICE_OWNER (source_role_id
    would need a value nothing here can honestly invent) — same convention
    as every other NOT-NULL-tightening downgrade in this migration set."""
    with op.batch_alter_table('tip_distribution_rule_versions', schema=None) as batch_op:
        batch_op.drop_constraint('ck_tip_dist_rule_version_source_role_matches_semantics', type_='check')
        batch_op.drop_constraint('ck_tip_distribution_rule_version_source_semantics', type_='check')
        batch_op.alter_column('source_role_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column('source_semantics')
