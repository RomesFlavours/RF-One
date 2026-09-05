"""add Selection resume screening schema (TASK_SELECTION_001)

Revision ID: b8f1c4a2e6d9
Revises: a9d3e5f7c2b4
Create Date: 2026-08-31 00:00:00.000000

One additive, non-destructive change: four new tables for the Selection
module's Resume Screening capability (01 Domains/Cross Domain/Personnel Management/
Selection/ResumeScreening/) — `raw_resumes`, `candidates`,
`candidate_education`, `candidate_work_history`. Only Facts are persisted
(RawResume raw text, Candidate/Education/WorkHistory fields as stated in the
résumé); Derived Information, Flags and Indicators are computed on every
read, never stored, so no schema exists for them.

No existing table or row is affected by this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8f1c4a2e6d9'
down_revision: Union[str, Sequence[str], None] = 'a9d3e5f7c2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'raw_resumes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=True),
        sa.Column('storage_path', sa.String(length=500), nullable=True),
        sa.Column('raw_text', sa.Text(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_raw_resumes_restaurant_id'), 'raw_resumes', ['restaurant_id'], unique=False)

    op.create_table(
        'candidates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('raw_resume_id', sa.Integer(), nullable=True),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=64), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('languages', sa.Text(), nullable=True),
        sa.Column('target_role', sa.String(length=64), nullable=True),
        sa.Column('declared_availability', sa.String(length=255), nullable=True),
        sa.Column('source', sa.String(length=64), nullable=True),
        sa.Column('source_file', sa.String(length=255), nullable=True),
        sa.Column('parsing_mode', sa.String(length=16), nullable=False),
        sa.Column('parser_provider', sa.String(length=64), nullable=True),
        sa.Column('declared_age_context', sa.String(length=64), nullable=True),
        sa.Column('derived_age_context_range', sa.String(length=64), nullable=True),
        sa.Column('derived_age_context_rationale', sa.Text(), nullable=True),
        sa.Column('derived_age_context_confidence', sa.String(length=16), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(['raw_resume_id'], ['raw_resumes.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_candidates_restaurant_id'), 'candidates', ['restaurant_id'], unique=False)
    op.create_index(op.f('ix_candidates_raw_resume_id'), 'candidates', ['raw_resume_id'], unique=False)

    op.create_table(
        'candidate_education',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('candidate_id', sa.Integer(), nullable=False),
        sa.Column('institution', sa.String(length=255), nullable=True),
        sa.Column('program', sa.String(length=255), nullable=True),
        sa.Column('qualification', sa.String(length=255), nullable=True),
        sa.Column('field', sa.String(length=255), nullable=True),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completion_status', sa.String(length=32), nullable=True),
        sa.Column('certifications', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_candidate_education_candidate_id'), 'candidate_education', ['candidate_id'], unique=False)

    op.create_table(
        'candidate_work_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('candidate_id', sa.Integer(), nullable=False),
        sa.Column('employer', sa.String(length=255), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('original_job_title', sa.String(length=255), nullable=True),
        sa.Column('normalized_role', sa.String(length=64), nullable=True),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.Column('responsibilities', sa.Text(), nullable=True),
        sa.Column('achievements', sa.Text(), nullable=True),
        sa.Column('reason_for_leaving', sa.Text(), nullable=True),
        sa.Column('evidence_snippet', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_candidate_work_history_candidate_id'), 'candidate_work_history', ['candidate_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_candidate_work_history_candidate_id'), table_name='candidate_work_history')
    op.drop_table('candidate_work_history')
    op.drop_index(op.f('ix_candidate_education_candidate_id'), table_name='candidate_education')
    op.drop_table('candidate_education')
    op.drop_index(op.f('ix_candidates_raw_resume_id'), table_name='candidates')
    op.drop_index(op.f('ix_candidates_restaurant_id'), table_name='candidates')
    op.drop_table('candidates')
    op.drop_index(op.f('ix_raw_resumes_restaurant_id'), table_name='raw_resumes')
    op.drop_table('raw_resumes')
