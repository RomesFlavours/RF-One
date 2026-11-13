"""Kitchen-only bootstrap on the verified AWS schema line; no directory/access changes."""
from alembic import op
import sqlalchemy as sa
from rfone_data_store.kitchen_configuration import items
from rfone_data_store.kitchen import menu_cards,KITCHEN_TABLES
revision='k9a020261110'
down_revision='f2a120261110'
branch_labels=None
depends_on=None


def upgrade():
    bind=op.get_bind()
    for table in [items,menu_cards,*KITCHEN_TABLES]:
        table.create(bind=bind,checkfirst=True)
        actual={column['name'] for column in sa.inspect(bind).get_columns(table.name)}
        if not {c.name for c in table.columns}<=actual:raise RuntimeError('Incompatible existing Kitchen table: '+table.name)


def downgrade():
    raise RuntimeError('Kitchen contains published domain data. Roll back the service image; do not drop data.')
