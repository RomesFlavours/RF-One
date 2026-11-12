"""Training local student roster and explicit employee links.

Revision ID: e6f120261109
Revises: e5e620261110
"""
from alembic import op
import sqlalchemy as sa

revision='e6f120261109'
down_revision='e5e620261110'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('training_student_profiles',
        sa.Column('training_account_id',sa.Integer(),sa.ForeignKey('training_accounts.id'),primary_key=True),
        sa.Column('employee_id',sa.Integer(),sa.ForeignKey('employees.id'),unique=True,nullable=True),
        sa.Column('phone',sa.String(80),nullable=False,server_default=''),
        sa.Column('archived_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('must_change_password',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.create_table('training_assignment_submissions',
        sa.Column('token',sa.String(64),primary_key=True),
        sa.Column('trainer_id',sa.Integer(),sa.ForeignKey('training_accounts.id'),nullable=False))


def downgrade():
    op.drop_table('training_assignment_submissions')
    op.drop_table('training_student_profiles')
