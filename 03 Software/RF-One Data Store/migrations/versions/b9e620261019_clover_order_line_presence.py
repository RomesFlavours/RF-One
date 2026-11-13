"""Retain Clover historical lines while recording current source membership.

Revision ID: b9e620261019
Revises: 540ee75caa65
"""
from alembic import op
import sqlalchemy as sa

revision = 'b9e620261019'
down_revision = '540ee75caa65'
branch_labels = None
depends_on = None

def upgrade():
    # Recovery may have applied this single additive column to an older AWS
    # schema without advancing unrelated migration revisions.
    if 'source_present' not in {c['name'] for c in sa.inspect(op.get_bind()).get_columns('order_items')}:
        op.add_column('order_items', sa.Column('source_present', sa.Boolean(), nullable=True))

def downgrade():
    op.drop_column('order_items', 'source_present')
