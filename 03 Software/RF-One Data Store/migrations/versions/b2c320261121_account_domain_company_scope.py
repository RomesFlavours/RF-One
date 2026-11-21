"""Company/site reach of a direct Domain access (CLOVER_MULTISITE_001, Product Owner 2026-11-21).

Additive and behaviour-preserving:
- `rfone_account_domain_access.company_scope` ('ALL' | 'SELECTED'), NOT NULL, server default 'ALL':
  every existing access keeps reaching every company/restaurant (Product Owner rule 2).
- `rfone_account_domain_company_access`: the companies chosen when company_scope is SELECTED.
No account, access, grant or company row is created, changed or removed.
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c320261121'
down_revision = 'a1c220261121'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('rfone_account_domain_access', schema=None) as batch_op:
        batch_op.add_column(sa.Column('company_scope', sa.String(length=16), nullable=False, server_default='ALL'))
        batch_op.create_check_constraint(
            'ck_rfone_account_domain_access_company_scope', "company_scope IN ('ALL', 'SELECTED')",
        )
    op.create_table(
        'rfone_account_domain_company_access',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('rfone_accounts.id'), nullable=False),
        sa.Column('domain_code', sa.String(length=32), nullable=False),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('rfone_company_contexts.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('account_id', 'domain_code', 'company_id', name='uq_account_domain_company_access'),
    )
    op.create_index('ix_rfone_account_domain_company_access_account_id',
                    'rfone_account_domain_company_access', ['account_id'])


def downgrade() -> None:
    op.drop_index('ix_rfone_account_domain_company_access_account_id',
                  table_name='rfone_account_domain_company_access')
    op.drop_table('rfone_account_domain_company_access')
    with op.batch_alter_table('rfone_account_domain_access', schema=None) as batch_op:
        batch_op.drop_constraint('ck_rfone_account_domain_access_company_scope', type_='check')
        batch_op.drop_column('company_scope')
