"""One RF-One account per person (EMPLOYEE_ACCOUNTS_001, Product Owner 2026-11-02).

`employee_context_links.rfone_account_id` is already unique: an account refers
to at most one person. This adds the other direction: a person has at most one
linked RF-One account. Existing data is never changed here: if a person has
more than one linked account the upgrade stops and names them, so an
administrator unlinks explicitly (Employee Directory) before retrying.
"""
from alembic import op
import sqlalchemy as sa

revision = 'f1a220261102'
down_revision = 'e0a120261101'
branch_labels = None
depends_on = None

INDEX = 'uq_employee_context_one_rfone_account'


def upgrade():
    duplicates = op.get_bind().execute(sa.text(
        "SELECT employee_id, COUNT(*) FROM employee_context_links "
        "WHERE rfone_account_id IS NOT NULL GROUP BY employee_id HAVING COUNT(*) > 1")).all()
    if duplicates:
        raise RuntimeError(
            "People with more than one linked RF-One account (employee_id, accounts): "
            + ", ".join(f"{row[0]}: {row[1]}" for row in duplicates)
            + ". Unlink the extra accounts explicitly in Employee Directory; nothing was changed.")
    op.create_index(INDEX, 'employee_context_links', ['employee_id'], unique=True,
                    sqlite_where=sa.text('rfone_account_id IS NOT NULL'),
                    postgresql_where=sa.text('rfone_account_id IS NOT NULL'))


def downgrade():
    op.drop_index(INDEX, table_name='employee_context_links')
