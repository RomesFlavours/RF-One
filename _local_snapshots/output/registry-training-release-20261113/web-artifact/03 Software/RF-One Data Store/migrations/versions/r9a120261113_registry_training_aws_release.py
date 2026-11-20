"""Add Registry/Training person links from the actual deployed Kitchen branch.

No historical identity matching, student deletion, permission or credential update.
"""
from alembic import op
from rfone_data_store.people_registry import PersonAccountLink, PersonEmployeeLink, PersonCompanyStatus
from rfone_data_store.student_registry import PersonQualification, TrainingPersonLink

revision = 'r9a120261113'
down_revision = 'k9g120261112'
branch_labels = ('registry_training_aws_20261113',)
depends_on = None


def upgrade():
    for model in (PersonAccountLink, PersonEmployeeLink, PersonQualification, TrainingPersonLink, PersonCompanyStatus):
        model.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Preserve person identities and Training links; roll back application images only.')
