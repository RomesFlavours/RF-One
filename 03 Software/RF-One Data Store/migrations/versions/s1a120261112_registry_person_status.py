"""Add explicit company relationships to the existing Registry identities."""
from alembic import op
import sqlalchemy as sa
revision = 's1a120261112'
down_revision = 'f3b120261110'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('rfone_person_company_statuses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id')),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('rfone_accounts.id')),
        sa.Column('code', sa.String(32), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("code IN ('CANDIDATE','EXTERNAL','EMPLOYEE')", name='ck_profile_company_status'),
        sa.CheckConstraint('(employee_id IS NOT NULL AND account_id IS NULL) OR (employee_id IS NULL AND account_id IS NOT NULL)', name='ck_profile_status_target'),
        sa.UniqueConstraint('employee_id','code',name='uq_profile_employee_status'),
        sa.UniqueConstraint('account_id','code',name='uq_profile_account_status'))
    op.create_index('ix_rfone_person_company_statuses_employee_id','rfone_person_company_statuses',['employee_id'])
    op.create_index('ix_rfone_person_company_statuses_account_id','rfone_person_company_statuses',['account_id'])


def downgrade():
    raise RuntimeError('Preserve company relationships; roll back application code only.')
