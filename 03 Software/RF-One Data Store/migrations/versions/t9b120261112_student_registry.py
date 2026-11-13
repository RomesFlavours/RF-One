"""Explicit student qualifications and links; no historical guesses or grant writes."""
from alembic import op
from rfone_data_store.student_registry import PersonQualification, TrainingPersonLink
from rfone_data_store.people_registry import PersonAccountLink, PersonEmployeeLink

revision = 't9b120261112'
down_revision = 'k9b120261112'
branch_labels = None
depends_on = None


def upgrade():
    for model in (PersonAccountLink, PersonEmployeeLink, PersonQualification, TrainingPersonLink):
        model.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Preserve person qualifications and links; roll back application code only.')
