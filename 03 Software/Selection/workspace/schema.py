"""Provision only new Selection tables without changing shared Alembic state.

Run once before deployment, after a snapshot. Other RF-One services retain
their existing migration history and can restart with their current images.

`verify()` is what Selection does at start instead of migrating (see
`RF-One Data Store/MIGRATIONS.md`): a read-only check that every table its
code maps exists with every mapped column. Tables of other Domains are not
required, so their migrations cannot stop Selection.
"""
from rfone_data_store.models import Base
from rfone_data_store.schema_compatibility import read_only_engine, require_compatible_schema
from rfone_data_store.selection import workspace_models  # noqa: F401
from .aruba_bridge import CandidateBridgeTicket  # noqa: F401
from .mail_delivery import EmailOutbox  # noqa: F401

# Shared-model tables (rfone_data_store/models.py) used by Selection's code.
# test_schema_startup.py fails if Selection starts using one not listed here.
REQUIRED_TABLES = (
    'acquisition_source_definitions', 'acting_identities', 'application_notes', 'application_ownerships',
    'application_question_answers', 'application_question_definitions', 'application_queue_movements',
    'application_stage_transitions', 'applications', 'assessment_item_definitions', 'assessment_item_instances',
    'candidate_certifications', 'candidate_communications', 'candidate_education', 'candidate_flags',
    'candidate_languages', 'candidate_persons', 'candidate_scheduling_tokens', 'candidate_skills',
    'candidate_work_history', 'candidates', 'channel_definitions', 'channel_publications', 'channel_tracking_links',
    'communication_reminder_policies', 'communication_template_snapshots', 'communication_templates',
    'compliance_dispositions', 'compliance_reviews', 'compliance_warnings', 'consistency_statements',
    'consistency_threads', 'employees', 'evidence_items', 'fit_assessments', 'in_person_interview_plans',
    'in_person_interview_section_definitions', 'inbound_communications', 'interview_appointments',
    'interview_scheduling_windows', 'job_posting_channel_variant_versions', 'job_posting_channel_variants',
    'job_posting_versions', 'job_postings', 'locations', 'missing_evidence_answers',
    'missing_evidence_questionnaires', 'missing_evidence_questions', 'person_match_candidates',
    'phone_interview_plans', 'phone_interview_question_definitions', 'phone_interview_question_instances',
    'primary_screening_criteria', 'primary_screening_criterion_evaluations', 'primary_screening_criterion_snapshots',
    'primary_screening_runs', 'raw_resumes', 'requirement_assessments', 'requirement_set_snapshots',
    'requirement_sets', 'requirement_snapshot_items', 'requirement_template_items', 'requirement_templates',
    'requirements', 'restaurant_roles', 'restaurants', 'review_priority_policies', 'review_priority_policy_rules',
    'rfone_accounts', 'selection_authority_levels', 'selection_case_memories',
    'selection_downstream_outcome_feedback', 'selection_efforts', 'selection_governance_requirements',
    'selection_learning_traces', 'selection_outcome_decisions', 'selection_outcome_definition_snapshots',
    'selection_outcome_definitions', 'selection_pattern_case_comparisons', 'selection_pattern_definition_snapshots',
    'selection_pattern_definitions', 'selection_pattern_examples', 'selection_pattern_observations',
    'selection_queues', 'selection_reminders', 'selection_rule_change_impacts', 'selection_rule_changes',
    'selection_rule_set_versions', 'selection_session_assignments', 'selection_sessions',
    'selection_stage_pattern_deltas', 'selection_stage_pattern_snapshots', 'signal_definitions',
    'signal_evidence_items', 'signal_observations', 'trainable_gaps',
)


def _workspace_tables():
    return [t for t in Base.metadata.tables.values()
            if t.name.startswith(('selection_workspace_', 'selection_candidate_'))]


def provision(bind):
    tables = _workspace_tables()
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)
    return [t.name for t in tables]


def required_tables():
    return [Base.metadata.tables[name] for name in REQUIRED_TABLES] + _workspace_tables()


def verify(url):
    """Read-only start check; raises IncompatibleSchemaError, never migrates."""
    engine = read_only_engine(url)
    try:
        return require_compatible_schema(engine, required_tables(), service='Selection')
    finally:
        engine.dispose()
