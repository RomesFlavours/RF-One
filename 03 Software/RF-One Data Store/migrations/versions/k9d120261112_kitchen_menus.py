"""Kitchen menus reference existing locations, menu areas and dish recipes."""
from alembic import op
from rfone_data_store.kitchen_menus import menus,entries
revision='k9d120261112'
down_revision='k9c120261112'
branch_labels=None
depends_on=None
def upgrade():
    for table in (menus,entries):table.create(op.get_bind())
def downgrade():
    raise RuntimeError('Preserve saved menus and entries; roll back application code only.')
