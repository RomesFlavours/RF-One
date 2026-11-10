"""Additive Training repository on the published AWS schema; no directory writes."""
from alembic import op
import sqlalchemy as sa
from rfone_data_store import models as m
from rfone_data_store.training.workspace import TrainingStudentProfile,TrainingAssignmentSubmission

revision='t9a120261110'
down_revision='k9a020261110'
branch_labels=None
depends_on=None


def upgrade():
    bind=op.get_bind()
    models=[TrainingStudentProfile,TrainingAssignmentSubmission,m.TrainingRetiredPill,m.TrainingCourse,
            m.TrainingCourseRevision,m.TrainingCourseFile,m.TrainingCourseAssignmentRevision]
    for model in models:
        table=model.__table__;table.create(bind,checkfirst=True)
        existing={c['name'] for c in sa.inspect(bind).get_columns(table.name)}
        if not set(table.c.keys())<=existing:raise RuntimeError('Incompatible Training table: '+table.name)


def downgrade():
    raise RuntimeError('Restore the prior service/routing. Do not destroy course versions, files or student history.')
