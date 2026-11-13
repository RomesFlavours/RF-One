"""Add concurrent company statuses without rewriting historical identities."""
from alembic import op
import sqlalchemy as sa

revision = 't9c120261112'
down_revision = 't9b120261112'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table('person_company_statuses'):
        columns = {c['name'] for c in inspector.get_columns('person_company_statuses')}
        if columns != {'person_id', 'code', 'assigned_at'} or set(inspector.get_pk_constraint('person_company_statuses')['constrained_columns']) != {'person_id', 'code'}:
            raise RuntimeError('Unexpected company status schema; no changes applied.')
        checks = inspector.get_check_constraints('person_company_statuses')
        foreign_keys = inspector.get_foreign_keys('person_company_statuses')
        if not any(all(code in check['sqltext'] for code in ('CANDIDATE', 'EXTERNAL', 'EMPLOYEE')) for check in checks) or not any(
                fk['constrained_columns'] == ['person_id'] and fk['referred_table'] == 'candidate_persons'
                and fk['referred_columns'] == ['id'] for fk in foreign_keys):
            raise RuntimeError('Unexpected company status constraints; no changes applied.')
        return
    op.create_table('person_company_statuses',
        sa.Column('person_id', sa.Integer(), sa.ForeignKey('candidate_persons.id'), primary_key=True),
        sa.Column('code', sa.String(32), primary_key=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("code IN ('CANDIDATE', 'EXTERNAL', 'EMPLOYEE')", name='ck_person_company_status_code'))


def downgrade():
    raise RuntimeError('Preserve company statuses; roll back application code only.')
