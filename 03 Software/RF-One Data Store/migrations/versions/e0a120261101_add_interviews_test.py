"""Add TEST interviews using the existing canonical RF-One person directory."""
from alembic import op
import sqlalchemy as sa

revision = 'e0a120261101'
down_revision = 'd9e220261029'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('interview_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('requester_id', sa.Integer(), sa.ForeignKey('rfone_accounts.id'), nullable=False),
        sa.Column('recipient_id', sa.Integer(), sa.ForeignKey('rfone_accounts.id'), nullable=False),
        sa.Column('person_id', sa.Integer(), sa.ForeignKey('employees.id', name='fk_interview_person'), nullable=False),
        sa.Column('purpose', sa.Text(), nullable=False),
        sa.Column('specialization', sa.String(32), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('transcript', sa.Text(), nullable=False),
        sa.Column('results', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('REQUESTED', 'IN_PROGRESS', 'COMPLETED')", name='ck_interview_status'))
    for field in ['requester_id', 'recipient_id', 'person_id']:
        op.create_index('ix_interview_sessions_' + field, 'interview_sessions', [field])


def downgrade():
    op.drop_table('interview_sessions')
