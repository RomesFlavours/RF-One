"""add legal entities table and restaurants legal entity id

Revision ID: 2747004fc651
Revises: a3cafbea7fe7
Create Date: 2026-09-08 19:18:17.249094

Adds the canonical `LegalEntity` model (Product Owner decision, correcting
the earlier `Restaurant`-as-Legal-Entity mapping — read-only verification
confirmed `Restaurant` is formally an Operational Unit per the approved
`01 Domains/Business Domain/Restaurant/Model/OU-Restaurant.md`, "Extends:
Operational Unit", never the juridical entity itself) and
`restaurants.legal_entity_id`, recording which Legal Entity owns/employs
through a given Restaurant. One Legal Entity may own many Restaurants; a
Restaurant belongs to exactly one Legal Entity at a time in this MVP.

No Corporate table is introduced — `LegalEntity` exists independently of any
persisted Corporate concept for now (none exists in this schema). No Brand
table is touched or repurposed.

`restaurants.legal_entity_id` is nullable: the existing `restaurants` row(s)
predate this column and are never guessed at. Added via a plain
`ALTER TABLE ... ADD COLUMN ... REFERENCES ...` (SQLite supports this
natively for a nullable column with an inline foreign key — no table
rebuild/batch mode required, unlike changing an existing column or an
unnamed constraint).

Autogenerate also detected pre-existing, unrelated drift on Selection tables
(`applications`, `in_person_interview_plans`, `phone_interview_plans`) —
those are intentionally NOT included here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2747004fc651'
down_revision: Union[str, Sequence[str], None] = 'a3cafbea7fe7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'legal_entities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('legal_name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name='ck_legal_entities_status'),
        sa.PrimaryKeyConstraint('id'),
    )

    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.add_column(sa.Column('legal_entity_id', sa.Integer(), nullable=True))
        batch_op.create_index(
            op.f('ix_restaurants_legal_entity_id'), ['legal_entity_id'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_restaurants_legal_entity_id', 'legal_entities', ['legal_entity_id'], ['id']
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('restaurants', schema=None) as batch_op:
        batch_op.drop_constraint('fk_restaurants_legal_entity_id', type_='foreignkey')
        batch_op.drop_index(op.f('ix_restaurants_legal_entity_id'))
        batch_op.drop_column('legal_entity_id')
    op.drop_table('legal_entities')
