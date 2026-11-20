"""add Selection résumé content fields (TASK 2A)

Revision ID: 9c4a2f7b1e3d
Revises: 2e9125cf954b
Create Date: 2026-09-01 00:00:00.000000

Additive, non-destructive change supporting the real résumé parser's fuller
structured extraction (summary, LinkedIn/profile URLs, skills,
certifications, languages, other useful sections):

- `candidates.summary`, `candidates.linkedin_url`,
  `candidates.other_profile_url`, `candidates.other_sections_text` — new
  nullable columns on the existing table.
- `candidate_skills`, `candidate_certifications`, `candidate_languages` —
  three new child tables, one row per stated skill/certification/language,
  mirroring the existing `candidate_education` / `candidate_work_history`
  pattern.

No existing table, row or column is altered or dropped.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c4a2f7b1e3d'
down_revision: Union[str, Sequence[str], None] = '2e9125cf954b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('candidates', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('candidates', sa.Column('linkedin_url', sa.String(length=500), nullable=True))
    op.add_column('candidates', sa.Column('other_profile_url', sa.String(length=500), nullable=True))
    op.add_column('candidates', sa.Column('other_sections_text', sa.Text(), nullable=True))

    op.create_table(
        'candidate_skills',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('candidate_id', sa.Integer(), nullable=False),
        sa.Column('skill', sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_candidate_skills_candidate_id'), 'candidate_skills', ['candidate_id'], unique=False)

    op.create_table(
        'candidate_certifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('candidate_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('issuer', sa.String(length=255), nullable=True),
        sa.Column('date_text', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_candidate_certifications_candidate_id'), 'candidate_certifications', ['candidate_id'], unique=False
    )

    op.create_table(
        'candidate_languages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('candidate_id', sa.Integer(), nullable=False),
        sa.Column('language', sa.String(length=64), nullable=False),
        sa.Column('proficiency', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_candidate_languages_candidate_id'), 'candidate_languages', ['candidate_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_candidate_languages_candidate_id'), table_name='candidate_languages')
    op.drop_table('candidate_languages')
    op.drop_index(op.f('ix_candidate_certifications_candidate_id'), table_name='candidate_certifications')
    op.drop_table('candidate_certifications')
    op.drop_index(op.f('ix_candidate_skills_candidate_id'), table_name='candidate_skills')
    op.drop_table('candidate_skills')

    op.drop_column('candidates', 'other_sections_text')
    op.drop_column('candidates', 'other_profile_url')
    op.drop_column('candidates', 'linkedin_url')
    op.drop_column('candidates', 'summary')
