"""RF-One employee registry source controls and change history. Additive only."""
from alembic import op
import sqlalchemy as sa
revision = 'e6b220261026'
down_revision = 'd5a120261021'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('employee_registry_profiles',
        sa.Column('employee_id',sa.Integer(),sa.ForeignKey('employees.id'),primary_key=True),
        sa.Column('source_name',sa.String(255)),sa.Column('source_custom_id',sa.String(64)),
        sa.Column('protect_name',sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column('protect_code',sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column('protect_status',sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column('protect_roles',sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column('source_roles_signature',sa.String(1000)),
        sa.Column('needs_review',sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column('reviewed_at',sa.DateTime(timezone=True)),
        sa.Column('reviewed_by',sa.Integer(),sa.ForeignKey('rfone_accounts.id')),
        sa.Column('version',sa.Integer(),nullable=False,server_default='1'),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('employee_registry_changes',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('employee_id',sa.Integer(),sa.ForeignKey('employees.id'),nullable=False),
        sa.Column('account_id',sa.Integer(),sa.ForeignKey('rfone_accounts.id')),
        sa.Column('changed_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('kind',sa.String(32),nullable=False),sa.Column('details',sa.JSON(),nullable=False))
    op.create_index('ix_employee_registry_changes_employee_id','employee_registry_changes',['employee_id'])

def downgrade():
    op.drop_table('employee_registry_changes')
    op.drop_table('employee_registry_profiles')
