"""WHO -> served ReportingEntities, and WHO-only recognition rules
(BANK_CONFIGURATION_001, Product Owner decisions D1 and D2)

Revision ID: e5b1d7c3a9f2
Revises: d4a8c2e6f1b3
Create Date: 2026-09-29 12:00:00.000000

Two schema changes, nothing else. No row is written, inferred or moved.

D1 — `bank_occurrence_reporting_entities`: which ReportingEntities a WHO
(BankOccurrence) serves. Many to many, one row per pair, never deleted —
`active` is how a pairing is withdrawn, so what was configured stays
readable. ReportingEntity (not LegalEntity) is the target because it is
also the future "For whom" of a transaction. The table starts EMPTY: no
association is derived from transactions, accounts, names or history.

D2 — `bank_recognition_rules.transaction_reason_id` becomes NULLABLE. A
recognition rule recognises a WHO; a rule configured by hand on the Bank
Configuration page has no WHY to store, and none is invented. Existing
rules keep the WHY they already have. WHO still never determines WHY:
matching reads only the rule's WHO (`recognition._propose`).

Runs on SQLite and PostgreSQL. SQLite cannot relax NOT NULL in place, so
the column change goes through an Alembic batch rebuild there, which
keeps every named CHECK constraint of the table.

Downgrade restores NOT NULL only when no rule relies on the relaxation;
it refuses otherwise rather than inventing a WHY for WHO-only rules.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b1d7c3a9f2'
down_revision: Union[str, Sequence[str], None] = 'd4a8c2e6f1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RULES = "bank_recognition_rules"
WHO_ENTITIES = "bank_occurrence_reporting_entities"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        WHO_ENTITIES,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("occurrence_id", sa.Integer(), nullable=False),
        sa.Column("reporting_entity_id", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["occurrence_id"], ["bank_occurrences.id"],
                                name="fk_bore_occurrence_id"),
        sa.ForeignKeyConstraint(["reporting_entity_id"], ["reporting_entities.id"],
                                name="fk_bore_reporting_entity_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("occurrence_id", "reporting_entity_id",
                            name="uq_bank_occurrence_reporting_entity"),
    )
    op.create_index("ix_bore_occurrence_id", WHO_ENTITIES, ["occurrence_id"])
    op.create_index("ix_bore_reporting_entity_id", WHO_ENTITIES, ["reporting_entity_id"])

    if op.get_context().dialect.name == "sqlite":
        with op.batch_alter_table(RULES, schema=None, recreate="always") as batch_op:
            batch_op.alter_column("transaction_reason_id", existing_type=sa.Integer(), nullable=True)
    else:
        op.alter_column(RULES, "transaction_reason_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    who_only = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM {RULES} WHERE transaction_reason_id IS NULL")
    ).scalar() or 0
    if who_only:
        raise RuntimeError(
            f"{who_only} WHO-only recognition rule(s) have no WHY. Restoring NOT NULL would "
            "require inventing one; deactivate or remove those rules deliberately first."
        )
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(RULES, schema=None, recreate="always") as batch_op:
            batch_op.alter_column("transaction_reason_id", existing_type=sa.Integer(), nullable=False)
    else:
        op.alter_column(RULES, "transaction_reason_id", existing_type=sa.Integer(), nullable=False)

    op.drop_index("ix_bore_reporting_entity_id", table_name=WHO_ENTITIES)
    op.drop_index("ix_bore_occurrence_id", table_name=WHO_ENTITIES)
    op.drop_table(WHO_ENTITIES)
