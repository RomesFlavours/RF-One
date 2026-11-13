"""Course drafts, immutable revisions, files and assignment revision references."""
from alembic import op
import sqlalchemy as sa

revision='e9f120261110'
down_revision='e7f120261110'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('training_courses',
        sa.Column('pill_id',sa.Integer(),sa.ForeignKey('training_pills.id'),primary_key=True),
        sa.Column('active_version',sa.Integer(),nullable=True),
        sa.Column('draft_json',sa.Text(),nullable=True),
        sa.Column('edit_revision',sa.Integer(),nullable=False,server_default='0'))
    op.create_table('training_course_revisions',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('pill_id',sa.Integer(),sa.ForeignKey('training_pills.id'),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('content_json',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.UniqueConstraint('pill_id','version'))
    op.create_table('training_course_files',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('pill_id',sa.Integer(),sa.ForeignKey('training_pills.id'),nullable=False),
        sa.Column('filename',sa.String(255),nullable=False),
        sa.Column('media_type',sa.String(80),nullable=False),
        sa.Column('sha256',sa.String(64),nullable=False),
        sa.Column('data',sa.LargeBinary(),nullable=False))
    op.create_table('training_course_assignment_revisions',
        sa.Column('assignment_id',sa.Integer(),sa.ForeignKey('training_assignments.id'),primary_key=True),
        sa.Column('revision_id',sa.Integer(),sa.ForeignKey('training_course_revisions.id'),nullable=False))


def downgrade():
    for table in ('training_course_assignment_revisions','training_course_files','training_course_revisions','training_courses'):
        op.drop_table(table)
