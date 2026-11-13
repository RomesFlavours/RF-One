"""Explicit central identity links; no historical backfill or grant writes."""
from alembic import op
import sqlalchemy as sa
revision='r1a120261112'
down_revision='t9a120261110'
branch_labels=None
depends_on=None


def upgrade():
    bind=op.get_bind()
    def create(name,*columns):
        if not sa.inspect(bind).has_table(name):
            op.create_table(name,*columns)
            return True
        return False
    create('person_account_links',
        sa.Column('account_id',sa.Integer(),sa.ForeignKey('rfone_accounts.id'),primary_key=True),
        sa.Column('person_id',sa.Integer(),sa.ForeignKey('candidate_persons.id'),nullable=False,unique=True),
        sa.Column('linked_by_id',sa.Integer(),sa.ForeignKey('rfone_accounts.id'),nullable=False),
        sa.Column('linked_at',sa.DateTime(timezone=True),nullable=False))
    if create('person_employee_links',
        sa.Column('employee_id',sa.Integer(),sa.ForeignKey('employees.id'),primary_key=True),
        sa.Column('person_id',sa.Integer(),sa.ForeignKey('candidate_persons.id'),nullable=False),
        sa.Column('linked_by_id',sa.Integer(),sa.ForeignKey('rfone_accounts.id'),nullable=False),
        sa.Column('linked_at',sa.DateTime(timezone=True),nullable=False)):
        op.create_index('ix_person_employee_links_person_id','person_employee_links',['person_id'])
    create('training_person_links',
        sa.Column('training_account_id',sa.Integer(),sa.ForeignKey('training_accounts.id'),primary_key=True),
        sa.Column('person_id',sa.Integer(),sa.ForeignKey('candidate_persons.id'),nullable=False,unique=True))
    create('person_qualifications',
        sa.Column('person_id',sa.Integer(),sa.ForeignKey('candidate_persons.id'),primary_key=True),
        sa.Column('code',sa.String(32),primary_key=True),
        sa.Column('assigned_at',sa.DateTime(timezone=True),nullable=False))
    create('person_reconciliation_events',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('person_id',sa.Integer(),sa.ForeignKey('candidate_persons.id'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('rfone_accounts.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('action',sa.String(32),nullable=False),
        sa.Column('details',sa.JSON(),nullable=False))


def downgrade():
    raise RuntimeError('Person identity links and reconciliation history must be preserved.')
