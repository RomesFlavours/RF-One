"""add PERSONAL entities and a personal owner for a Source

Revision ID: c9e4a1f7d3b6
Revises: b7f1c3e5a9d2
Create Date: 2026-10-06

BANK_SOURCE_EDIT_AND_ENTITIES_001 — Product Owner decision ("make the MINIMUM
clean extension needed to support COMPANY / PERSONAL"). ADDITIVE, no data
change.

  * `reporting_entities.entity_type` gains `PERSONAL`: a person (e.g.
    "Personal — Pino") who owns a Source or benefits from a transaction. Like
    VIRTUAL it never creates a `LegalEntity` (`legal_entity_id` stays NULL):
    `LegalEntity` keeps its single meaning, a genuine juridical / employing
    entity. Every existing row keeps its type.
  * `payment_instruments.owner_reporting_entity_id` — the owner of a Source
    when the owner is a PERSONAL entity. A company-owned Source keeps its
    owner where it always was, `legal_entity_id`; the two are never both set
    (`ck_payment_instrument_single_owner`). Every existing Source starts with
    no personal owner.

Downgrade refuses while any PERSONAL entity or personal owner exists, then
restores the previous constraints and drops the column.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c9e4a1f7d3b6'
down_revision: Union[str, Sequence[str], None] = 'b7f1c3e5a9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("reporting_entities", schema=None) as batch_op:
        batch_op.drop_constraint("ck_reporting_entity_type", type_="check")
        batch_op.drop_constraint("ck_reporting_entity_type_legal_entity", type_="check")
        batch_op.create_check_constraint(
            "ck_reporting_entity_type", "entity_type IN ('LEGAL', 'VIRTUAL', 'PERSONAL')",
        )
        batch_op.create_check_constraint(
            "ck_reporting_entity_type_legal_entity",
            "(entity_type = 'LEGAL' AND legal_entity_id IS NOT NULL) OR "
            "(entity_type IN ('VIRTUAL', 'PERSONAL') AND legal_entity_id IS NULL)",
        )
    with op.batch_alter_table("payment_instruments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("owner_reporting_entity_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_payment_instrument_owner_reporting_entity", "reporting_entities",
            ["owner_reporting_entity_id"], ["id"],
        )
        batch_op.create_check_constraint(
            "ck_payment_instrument_single_owner",
            "legal_entity_id IS NULL OR owner_reporting_entity_id IS NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    personal = bind.execute(sa.text(
        "SELECT COUNT(*) FROM reporting_entities WHERE entity_type = 'PERSONAL'")).scalar() or 0
    owned = bind.execute(sa.text(
        "SELECT COUNT(*) FROM payment_instruments WHERE owner_reporting_entity_id IS NOT NULL")).scalar() or 0
    if personal or owned:
        raise RuntimeError(
            f"Refusing to downgrade: {personal} PERSONAL entity(ies) and {owned} personally-owned "
            "Source(s) exist; they would have no valid shape before this revision."
        )
    with op.batch_alter_table("payment_instruments", schema=None) as batch_op:
        batch_op.drop_constraint("ck_payment_instrument_single_owner", type_="check")
        batch_op.drop_constraint("fk_payment_instrument_owner_reporting_entity", type_="foreignkey")
        batch_op.drop_column("owner_reporting_entity_id")
    with op.batch_alter_table("reporting_entities", schema=None) as batch_op:
        batch_op.drop_constraint("ck_reporting_entity_type_legal_entity", type_="check")
        batch_op.drop_constraint("ck_reporting_entity_type", type_="check")
        batch_op.create_check_constraint("ck_reporting_entity_type", "entity_type IN ('LEGAL', 'VIRTUAL')")
        batch_op.create_check_constraint(
            "ck_reporting_entity_type_legal_entity",
            "(entity_type = 'LEGAL' AND legal_entity_id IS NOT NULL) OR "
            "(entity_type = 'VIRTUAL' AND legal_entity_id IS NULL)",
        )
