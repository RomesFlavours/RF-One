"""Reinstall Bank: create the current Bank schema where Bank was removed (BANK_REINSTALL_001)

Revision ID: c8e4b2a6f0d1
Revises: 84354dc654ce, a6e2c8f4b0d9
Create Date: 2026-10-17

Product Owner decision (2026-10-17): the cleaned local Bank is published on AWS again. On RDS, Bank was removed by
84354dc654ce (2026-10-14): its 53 tables are absent. This revision creates the CURRENT Bank schema there — the 46
Bank tables of today's models (the 7 tables of the old, non-AI rule system stay removed: d2b6f8a4c0e7) — with their
indexes and foreign keys, frozen here as they are on 2026-10-17 (a later model change needs its own revision).

It is also the merge of the two lines: the RDS line (84354dc654ce) and the local Bank line (a6e2c8f4b0d9).

All or nothing, never a mix:
  * every Bank table absent (RDS) → all are created (PostgreSQL only);
  * every Bank table present (a local working database, a fresh database built by the whole chain because
    84354dc654ce now drops only with an explicit confirmation) → their columns are verified against the expected
    ones and nothing is changed; a difference refuses;
  * only some present → refuses: a partial Bank schema is never completed silently.

No data: rows come back on AWS only through the authorized initial transfer (BANK_REINSTALL_001), never as an
effect of a migration. Access grants (BANK rows of the account access tables) are data too.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8e4b2a6f0d1"
down_revision: Union[str, Sequence[str], None] = ("84354dc654ce", "a6e2c8f4b0d9")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The 46 Bank tables and their columns as of 2026-10-17.
EXPECTED_COLUMNS: dict[str, tuple[str, ...]] = {
    'bank_accounting_classifications': ('active', 'code', 'created_at', 'description', 'id', 'is_contra', 'name', 'node_type', 'normal_balance', 'parent_id', 'review_sensitive', 'statement_type', 'updated_at'),
    'bank_ai_instructions': ('created_at', 'created_by_account_id', 'id', 'instructions'),
    'bank_ai_rule_application_items': ('application_id', 'explanation_id', 'financial_transaction_id', 'for_whom_after', 'for_whom_before', 'id', 'note', 'outcome', 'who_after', 'who_before', 'why_after', 'why_before'),
    'bank_ai_rule_applications': ('conflicts', 'created_by_account_id', 'error_message', 'errors', 'examined', 'excluded_ai_settled', 'finished_at', 'id', 'import_batch_id', 'mode', 'only_unsettled', 'preview_id', 'protected', 'rule_id', 'started_at', 'status', 'unchanged', 'unresolved', 'updated', 'version_id', 'who_created', 'who_only'),
    'bank_ai_rule_batch_results': ('created_at', 'id', 'items_json', 'prompt_hash'),
    'bank_ai_rule_drafts': ('ai_rule_id', 'create_missing_who', 'created_at', 'created_by_account_id', 'id', 'only_unsettled', 'origin_amount_minor', 'origin_description', 'origin_posting_date', 'origin_transaction_id', 'override_protected', 'rule_text', 'status', 'updated_at', 'user_title'),
    'bank_ai_rule_interpretations': ('cache_key', 'created_at', 'id', 'instructions_snapshot', 'model', 'provider', 'raw_answer', 'rejection_reason', 'rule_text', 'spec'),
    'bank_ai_rule_preview_items': ('amount_minor', 'currency', 'current_for_whom_name', 'current_who_name', 'current_why_name', 'description', 'extracted_who_name', 'financial_transaction_id', 'id', 'is_origin', 'plan', 'plan_note', 'posting_date', 'preview_id', 'proposed_for_whom_id', 'proposed_for_whom_name', 'proposed_who_id', 'proposed_who_is_new', 'proposed_who_name', 'proposed_why_id', 'proposed_why_is_new', 'proposed_why_name', 'reason', 'source_label', 'to_verify', 'verdict'),
    'bank_ai_rule_previews': ('ai_calls', 'conflict_count', 'create_missing_who', 'created_by_account_id', 'date_from', 'date_to', 'doubt_count', 'draft_id', 'error_message', 'examined_count', 'excluded_ai_settled', 'finished_at', 'id', 'interpretation', 'match_count', 'method', 'model', 'only_unsettled', 'origin_transaction_id', 'override_protected', 'planned_updates', 'protected_count', 'provider', 'rule_text', 'scope', 'scope_key', 'started_at', 'status', 'unchanged_count', 'unresolved_count', 'who_only'),
    'bank_ai_rule_versions': ('create_missing_who', 'created_at', 'created_by_account_id', 'id', 'instructions_snapshot', 'interpretation_id', 'method', 'override_protected', 'rule_id', 'rule_text', 'spec', 'version_no'),
    'bank_ai_rules': ('apply_future', 'created_at', 'created_by_account_id', 'deleted_at', 'deleted_by_account_id', 'id', 'last_applied_at', 'origin_description', 'origin_transaction_id', 'status', 'title', 'updated_at', 'user_title'),
    'bank_ai_test_results': ('amount_minor', 'currency', 'current_who_name', 'current_why_name', 'description', 'doubt', 'financial_transaction_id', 'id', 'posting_date', 'proposed_who_id', 'proposed_who_is_new', 'proposed_who_name', 'proposed_why_id', 'proposed_why_is_new', 'proposed_why_name', 'rationale', 'run_id', 'source_label', 'to_verify'),
    'bank_ai_test_runs': ('created_by_account_id', 'date_from', 'date_to', 'error_message', 'finished_at', 'id', 'instruction_id', 'instructions_snapshot', 'model', 'only_unclassified', 'provider', 'requested_size', 'started_at', 'status'),
    'bank_card_holder_assignments': ('created_at', 'created_by_account_id', 'credit_card_payment_instrument_id', 'holder_acting_identity_id', 'holder_display_name', 'holder_employee_id', 'holder_kind', 'id', 'notes', 'updated_at', 'valid_from', 'valid_to'),
    'bank_card_settlement_accounts': ('created_at', 'created_by_account_id', 'credit_card_payment_instrument_id', 'id', 'notes', 'settlement_bank_account_id', 'updated_at', 'valid_from', 'valid_to'),
    'bank_evidence_bypass_authorizations': ('authorized_at', 'authorized_by_account_id', 'authorized_by_name', 'capability_snapshot', 'financial_transaction_id', 'id', 'missing_document_note', 'occurrence_id', 'occurrence_name_snapshot', 'reason'),
    'bank_historical_instrument_candidate_evidence': ('candidate_id', 'created_at', 'evidence_key', 'evidence_kind', 'financial_transaction_id', 'first_observed_date', 'id', 'last_observed_date', 'occurrences', 'raw_bank_transaction_id'),
    'bank_historical_instrument_candidates': ('created_at', 'discovery', 'evidence', 'first_seen_date', 'id', 'institution', 'last_four', 'last_seen_date', 'occurrence_count', 'resolution', 'resolution_effective_date', 'resolution_note', 'resolved_at', 'resolved_by_account_id', 'resolved_payment_instrument_id', 'updated_at'),
    'bank_import_batches': ('date_range_end', 'date_range_start', 'detected_format', 'error_summary', 'id', 'import_log', 'original_file_name', 'overlap_warning', 'payment_instrument_id', 'raw_file_bytes', 'row_count', 'sha256', 'status', 'uploaded_at', 'uploaded_by_account_id'),
    'bank_instrument_assignment_audits': ('affected_transaction_count', 'changed_at', 'changed_by_account_id', 'financial_transaction_id', 'id', 'import_batch_id', 'new_payment_instrument_id', 'previous_payment_instrument_id', 'reason', 'scope'),
    'bank_instrument_identity_audits': ('changed_at', 'changed_by_account_id', 'field_name', 'id', 'new_value', 'payment_instrument_id', 'previous_value', 'reason', 'source_evidence'),
    'bank_invoice_matches': ('confidence', 'created_at', 'decided_at', 'decided_by_account_id', 'difference_kind', 'difference_minor', 'difference_note', 'financial_transaction_id', 'id', 'match_basis', 'match_method', 'matched_amount_minor', 'purchase_document_id', 'status', 'updated_at'),
    'bank_monthly_instrument_coverages': ('created_at', 'expectation', 'expectation_basis', 'id', 'import_batch_id', 'institution_snapshot', 'instrument_display_name_snapshot', 'instrument_status_snapshot', 'last_four_snapshot', 'lifecycle_label_snapshot', 'payment_instrument_id', 'period_id', 'resolution', 'resolution_effective_date', 'resolution_note', 'resolved_at', 'resolved_by_account_id', 'updated_at'),
    'bank_monthly_source_periods': ('audit_log', 'completed_at', 'completed_by_account_id', 'created_at', 'id', 'period_end', 'period_month', 'period_start', 'status'),
    'bank_occurrence_aliases': ('alias_key', 'alias_text', 'created_at', 'first_financial_transaction_id', 'id', 'occurrence_id', 'source', 'source_family'),
    'bank_occurrence_reason_associations': ('active', 'confirmation_count', 'created_at', 'first_confirmed_at', 'id', 'last_confirmed_at', 'occurrence_id', 'source', 'transaction_reason_id', 'updated_at'),
    'bank_occurrence_reporting_entities': ('active', 'created_at', 'id', 'occurrence_id', 'reporting_entity_id', 'updated_at'),
    'bank_occurrence_suppliers': ('created_at', 'id', 'link_source', 'notes', 'occurrence_id', 'supplier_id'),
    'bank_occurrence_types': ('code', 'created_at', 'description', 'id', 'name', 'status', 'updated_at'),
    'bank_occurrences': ('canonical_name', 'capability_established_at', 'capability_evidence', 'capability_source', 'category_capability', 'created_at', 'default_transaction_reason_id', 'id', 'occurrence_type_id', 'optional_notes', 'status', 'updated_at'),
    'bank_reason_groups': ('active', 'code', 'created_at', 'display_order', 'id', 'name', 'updated_at'),
    'bank_reconciliation_control_configs': ('control_start_month', 'created_at', 'id', 'note', 'updated_at', 'updated_by_account_id', 'validated_through_month'),
    'bank_source_instrument_profiles': ('account_hint', 'created_at', 'created_by_account_id', 'created_from_batch_id', 'detected_format', 'file_name_key', 'id', 'notes', 'payment_instrument_id', 'status', 'updated_at'),
    'bank_transaction_allocations': ('accounting_classification_code_snapshot', 'accounting_classification_id', 'accounting_classification_name_snapshot', 'accounting_destination_source', 'accounting_statement_type_snapshot', 'allocation_index', 'amount_minor', 'created_at', 'decided_at', 'decided_by_account_id', 'decision_source', 'economic_owner_legal_entity_id', 'evidence_kind', 'evidence_reference', 'financial_transaction_id', 'id', 'intercompany_due_from_code_snapshot', 'intercompany_due_to_code_snapshot', 'intercompany_notes', 'intercompany_outcome', 'notes', 'payer_kind', 'payer_legal_entity_id', 'reporting_entity_id', 'reporting_entity_name_snapshot', 'status', 'transaction_reason_id', 'transaction_reason_name_snapshot', 'updated_at'),
    'bank_transaction_explanations': ('accounting_classification_code_snapshot', 'accounting_classification_id', 'accounting_classification_name_snapshot', 'accounting_destination_source', 'accounting_statement_type_snapshot', 'confidence', 'confirmed_at', 'confirmed_by_account_id', 'created_at', 'decision_source', 'decision_status', 'deductible_snapshot', 'explanation_notes', 'financial_transaction_id', 'food_cost_snapshot', 'id', 'occurrence_id', 'occurrence_name_snapshot', 'operative_snapshot', 'transaction_reason_id', 'transaction_reason_name_snapshot', 'updated_at', 'what_label_snapshot'),
    'bank_transaction_reason_export_mappings': ('bank_transaction_reason_id', 'created_at', 'deductible', 'food_cost', 'id', 'operative', 'updated_at', 'what_label'),
    'bank_transaction_reasons': ('accounting_classification_id', 'code', 'created_at', 'description', 'id', 'name', 'reason_group_id', 'status', 'updated_at'),
    'financial_transaction_matches': ('confirmed_by', 'created_at', 'id', 'match_basis', 'match_method', 'match_type', 'matched_amount_minor', 'transaction_a_id', 'transaction_b_id'),
    'financial_transactions': ('accounting_canonical_transaction_id', 'accounting_dedup_key', 'accounting_dedup_reason', 'accounting_settlement_account_id', 'accounting_status', 'amount_minor', 'balance_minor', 'bank_source', 'classification', 'counterparty_identifier', 'counterparty_name', 'created_at', 'description_normalized', 'description_original', 'duplicate_of_transaction_id', 'duplicate_status', 'explanation_id', 'external_transaction_id', 'fee_amount_minor', 'fingerprint', 'gross_amount_minor', 'id', 'import_batch_id', 'native_transaction_type', 'net_amount_minor', 'occurrence_count_in_batch', 'occurrence_index_in_batch', 'payee_normalization_version', 'payee_normalized', 'payment_instrument_id', 'posting_date', 'reference', 'related_external_transaction_id', 'review_status', 'source_memo', 'source_memo_field', 'source_row_number', 'source_system_id', 'status', 'transaction_date', 'transaction_datetime', 'updated_at'),
    'payment_instruments': ('created_at', 'currency', 'display_name', 'effective_end_date', 'effective_start_date', 'external_account_identifier', 'id', 'institution', 'instrument_type', 'last_four', 'legal_entity_id', 'lifecycle_end_reason', 'linked_instrument_id', 'owner_reporting_entity_id', 'provider', 'replaced_by_instrument_id', 'source_system_id', 'status', 'updated_at'),
    'purchase_line_classifications': ('accounting_classification_code_snapshot', 'accounting_classification_id', 'accounting_statement_type_snapshot', 'confidence', 'created_at', 'decided_at', 'decided_by_account_id', 'decision_source', 'evidence', 'id', 'is_override', 'learning_id', 'purchase_document_id', 'purchase_line_id', 'reporting_entity_id', 'status', 'transaction_reason_id', 'transaction_reason_name_snapshot'),
    'raw_bank_transactions': ('anomalies', 'id', 'import_batch_id', 'normalized_transaction_id', 'parse_status', 'raw_fields', 'row_fingerprint', 'row_number'),
    'reporting_entities': ('code', 'created_at', 'description', 'entity_type', 'id', 'legal_entity_id', 'name', 'reporting_group_id', 'status', 'updated_at'),
    'reporting_entity_destination_aliases': ('confirmation_source', 'confirmed_at', 'confirmed_by_account_id', 'created_at', 'evidence', 'id', 'normalized_key', 'raw_value', 'reporting_entity_id', 'scope', 'status', 'supplier_id', 'updated_at'),
    'reporting_groups': ('code', 'created_at', 'description', 'id', 'name', 'status', 'updated_at'),
    'supplier_item_category_learnings': ('confirmation_count', 'contradiction_note', 'created_at', 'first_confirmed_at', 'id', 'identity_kind', 'identity_value', 'last_confirmed_at', 'status', 'supplier_id', 'supplier_product_id', 'transaction_reason_id', 'updated_at'),
}


def _create_tables() -> None:
    op.create_table('bank_accounting_classifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('statement_type', sa.String(length=16), nullable=True),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('node_type', sa.String(length=24), server_default='POSTING', nullable=False),
    sa.Column('is_contra', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('review_sensitive', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('normal_balance', sa.String(length=8), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("node_type IN ('GROUP', 'POSTING', 'POSTING_CATEGORY')", name='ck_bac_node_type'),
    sa.CheckConstraint("normal_balance IS NULL OR normal_balance IN ('DEBIT', 'CREDIT')", name='ck_bac_normal_balance'),
    sa.CheckConstraint("statement_type IS NULL OR statement_type IN ('PROFIT_LOSS', 'BALANCE_SHEET')", name='ck_bank_accounting_classification_statement_type'),
    sa.CheckConstraint('parent_id IS NULL OR parent_id <> id', name='ck_bac_parent_not_self'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_bank_accounting_classification_code')
    )
    op.create_table('bank_ai_rule_batch_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('prompt_hash', sa.String(length=64), nullable=False),
    sa.Column('items_json', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('prompt_hash', name='uq_bank_ai_rule_batch_prompt')
    )
    op.create_table('bank_ai_rule_interpretations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cache_key', sa.String(length=128), nullable=False),
    sa.Column('rule_text', sa.Text(), nullable=False),
    sa.Column('instructions_snapshot', sa.Text(), nullable=True),
    sa.Column('raw_answer', sa.Text(), nullable=True),
    sa.Column('spec', sa.Text(), nullable=True),
    sa.Column('rejection_reason', sa.Text(), nullable=True),
    sa.Column('provider', sa.String(length=32), nullable=True),
    sa.Column('model', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('cache_key', name='uq_bank_ai_rule_interpretation_key')
    )
    op.create_table('bank_occurrence_types',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default='ACTIVE', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name='ck_bank_occurrence_type_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_bank_occurrence_type_code')
    )
    op.create_table('bank_reason_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_bank_reason_group_code')
    )
    op.create_table('bank_transaction_explanations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('financial_transaction_id', sa.Integer(), nullable=True),
    sa.Column('occurrence_id', sa.Integer(), nullable=True),
    sa.Column('transaction_reason_id', sa.Integer(), nullable=True),
    sa.Column('decision_source', sa.String(length=8), nullable=True),
    sa.Column('decision_status', sa.String(length=24), nullable=True),
    sa.Column('confidence', sa.String(length=16), nullable=True),
    sa.Column('explanation_notes', sa.Text(), nullable=True),
    sa.Column('confirmed_by_account_id', sa.Integer(), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('occurrence_name_snapshot', sa.String(length=255), nullable=True),
    sa.Column('food_cost_snapshot', sa.Boolean(), nullable=True),
    sa.Column('operative_snapshot', sa.Boolean(), nullable=True),
    sa.Column('deductible_snapshot', sa.Boolean(), nullable=True),
    sa.Column('what_label_snapshot', sa.String(length=128), nullable=True),
    sa.Column('transaction_reason_name_snapshot', sa.String(length=255), nullable=True),
    sa.Column('accounting_classification_id', sa.Integer(), nullable=True),
    sa.Column('accounting_classification_code_snapshot', sa.String(length=64), nullable=True),
    sa.Column('accounting_classification_name_snapshot', sa.String(length=255), nullable=True),
    sa.Column('accounting_statement_type_snapshot', sa.String(length=16), nullable=True),
    sa.Column('accounting_destination_source', sa.String(length=16), server_default='WHY', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.CheckConstraint("accounting_destination_source IN ('WHY', 'TRANSACTION')", name='ck_bte_destination_source'),
    sa.CheckConstraint("decision_source IS NULL OR decision_source IN ('HUMAN', 'RULE')", name='ck_bank_transaction_explanation_decision_source'),
    sa.CheckConstraint("decision_status IS NULL OR decision_status IN ('SUGGESTED', 'AUTO_APPLIED', 'HUMAN_CONFIRMED', 'HUMAN_OVERRIDDEN', 'HUMAN_RECLASSIFIED', 'NEEDS_HUMAN_REVIEW')", name='ck_bank_transaction_explanation_decision_status'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('financial_transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('payment_instrument_id', sa.Integer(), nullable=False),
    sa.Column('source_system_id', sa.Integer(), nullable=True),
    sa.Column('external_transaction_id', sa.String(length=128), nullable=True),
    sa.Column('bank_source', sa.String(length=32), nullable=True),
    sa.Column('posting_date', sa.Date(), nullable=True),
    sa.Column('transaction_date', sa.Date(), nullable=True),
    sa.Column('transaction_datetime', sa.DateTime(timezone=True), nullable=True),
    sa.Column('description_original', sa.Text(), nullable=True),
    sa.Column('description_normalized', sa.Text(), nullable=True),
    sa.Column('source_memo', sa.Text(), nullable=True),
    sa.Column('source_memo_field', sa.String(length=64), nullable=True),
    sa.Column('amount_minor', sa.Integer(), nullable=False),
    sa.Column('native_transaction_type', sa.String(length=64), nullable=True),
    sa.Column('reference', sa.String(length=128), nullable=True),
    sa.Column('balance_minor', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('import_batch_id', sa.Integer(), nullable=True),
    sa.Column('source_row_number', sa.Integer(), nullable=True),
    sa.Column('fingerprint', sa.String(length=128), nullable=True),
    sa.Column('occurrence_index_in_batch', sa.Integer(), nullable=True),
    sa.Column('occurrence_count_in_batch', sa.Integer(), nullable=True),
    sa.Column('duplicate_status', sa.String(length=24), nullable=True),
    sa.Column('duplicate_of_transaction_id', sa.Integer(), nullable=True),
    sa.Column('payee_normalized', sa.String(length=512), nullable=True),
    sa.Column('payee_normalization_version', sa.String(length=16), nullable=True),
    sa.Column('accounting_dedup_key', sa.String(length=128), nullable=True),
    sa.Column('accounting_status', sa.String(length=40), nullable=True),
    sa.Column('accounting_canonical_transaction_id', sa.Integer(), nullable=True),
    sa.Column('accounting_dedup_reason', sa.Text(), nullable=True),
    sa.Column('accounting_settlement_account_id', sa.Integer(), nullable=True),
    sa.Column('review_status', sa.String(length=24), nullable=True),
    sa.Column('explanation_id', sa.Integer(), nullable=True),
    sa.Column('gross_amount_minor', sa.Integer(), nullable=True),
    sa.Column('fee_amount_minor', sa.Integer(), nullable=True),
    sa.Column('net_amount_minor', sa.Integer(), nullable=True),
    sa.Column('counterparty_name', sa.String(length=255), nullable=True),
    sa.Column('counterparty_identifier', sa.String(length=255), nullable=True),
    sa.Column('related_external_transaction_id', sa.String(length=128), nullable=True),
    sa.Column('classification', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("accounting_status IS NULL OR accounting_status IN ('CANONICAL', 'DUPLICATE_SUPPRESSED', 'UNRESOLVED_NO_SETTLEMENT_ACCOUNT')", name='ck_ft_accounting_status'),
    sa.CheckConstraint("classification IN ('REVENUE', 'EXPENSE', 'INTERNAL_TRANSFER', 'FEE', 'UNKNOWN')", name='ck_ft_classification'),
    sa.CheckConstraint("duplicate_status IS NULL OR duplicate_status IN ('NONE', 'CANDIDATE_DUPLICATE', 'CONFIRMED_DUPLICATE', 'CONFIRMED_DISTINCT')", name='ck_ft_duplicate_status'),
    sa.CheckConstraint("review_status IS NULL OR review_status IN ('REQUIRES_REVIEW', 'REVIEWED', 'ACCEPTED')", name='ck_ft_review_status'),
    sa.CheckConstraint("status IN ('COMPLETED', 'PENDING', 'REVERSED', 'FAILED', 'UNKNOWN')", name='ck_ft_status'),
    sa.CheckConstraint('accounting_canonical_transaction_id IS NULL OR accounting_canonical_transaction_id <> id', name='ck_ft_accounting_canonical_not_self'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('payment_instrument_id', 'external_transaction_id', name='uq_ft_instrument_external_id')
    )
    op.create_table('reporting_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default='ACTIVE', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name='ck_reporting_group_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_reporting_group_code')
    )
    op.create_table('bank_ai_instructions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('instructions', sa.Text(), nullable=False),
    sa.Column('created_by_account_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_ai_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('user_title', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('apply_future', sa.Boolean(), nullable=False),
    sa.Column('origin_transaction_id', sa.Integer(), nullable=True),
    sa.Column('origin_description', sa.Text(), nullable=True),
    sa.Column('last_applied_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by_account_id', sa.Integer(), nullable=True),
    sa.Column('created_by_account_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name='ck_bank_ai_rule_status'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_monthly_source_periods',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('period_month', sa.String(length=7), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('period_end', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_by_account_id', sa.Integer(), nullable=True),
    sa.Column('audit_log', sa.Text(), nullable=True),
    sa.CheckConstraint("status IN ('OPEN', 'INCOMPLETE', 'COMPLETE')", name='ck_bmsp_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('period_month', name='uq_bmsp_period_month')
    )
    op.create_table('bank_reconciliation_control_configs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('control_start_month', sa.String(length=7), nullable=False),
    sa.Column('validated_through_month', sa.String(length=7), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('updated_by_account_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('id = 1', name='ck_brcc_singleton'),
    sa.CheckConstraint('length(control_start_month) = 7', name='ck_brcc_month_shape'),
    sa.CheckConstraint('validated_through_month IS NULL OR length(validated_through_month) = 7', name='ck_brcc_validated_through_shape'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_transaction_reasons',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default='ACTIVE', nullable=False),
    sa.Column('accounting_classification_id', sa.Integer(), nullable=True),
    sa.Column('reason_group_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name='ck_bank_transaction_reason_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_bank_transaction_reason_code')
    )
    op.create_table('financial_transaction_matches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('transaction_a_id', sa.Integer(), nullable=False),
    sa.Column('transaction_b_id', sa.Integer(), nullable=False),
    sa.Column('match_type', sa.String(length=24), nullable=False),
    sa.Column('match_method', sa.String(length=8), nullable=False),
    sa.Column('match_basis', sa.Text(), nullable=True),
    sa.Column('matched_amount_minor', sa.Integer(), nullable=False),
    sa.Column('confirmed_by', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("match_method IN ('AUTO', 'HUMAN')", name='ck_ftm_match_method'),
    sa.CheckConstraint("match_type IN ('INTERNAL_TRANSFER')", name='ck_ftm_match_type'),
    sa.CheckConstraint('transaction_a_id < transaction_b_id', name='ck_ftm_ordered_pair'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('transaction_a_id', 'transaction_b_id', name='uq_ftm_pair')
    )
    op.create_table('reporting_entities',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('entity_type', sa.String(length=16), nullable=False),
    sa.Column('legal_entity_id', sa.Integer(), nullable=True),
    sa.Column('reporting_group_id', sa.Integer(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), server_default='ACTIVE', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(entity_type = 'LEGAL' AND legal_entity_id IS NOT NULL) OR (entity_type IN ('VIRTUAL', 'PERSONAL') AND legal_entity_id IS NULL)", name='ck_reporting_entity_type_legal_entity'),
    sa.CheckConstraint("entity_type IN ('LEGAL', 'VIRTUAL', 'PERSONAL')", name='ck_reporting_entity_type'),
    sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name='ck_reporting_entity_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_reporting_entity_code')
    )
    op.create_table('bank_ai_rule_drafts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rule_text', sa.Text(), nullable=False),
    sa.Column('user_title', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('origin_transaction_id', sa.Integer(), nullable=True),
    sa.Column('origin_posting_date', sa.Date(), nullable=True),
    sa.Column('origin_description', sa.Text(), nullable=True),
    sa.Column('origin_amount_minor', sa.Integer(), nullable=True),
    sa.Column('create_missing_who', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('override_protected', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('only_unsettled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('ai_rule_id', sa.Integer(), nullable=True),
    sa.Column('created_by_account_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('DRAFT')", name='ck_bank_ai_rule_draft_status'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_ai_rule_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rule_id', sa.Integer(), nullable=False),
    sa.Column('version_no', sa.Integer(), nullable=False),
    sa.Column('rule_text', sa.Text(), nullable=False),
    sa.Column('create_missing_who', sa.Boolean(), nullable=False),
    sa.Column('override_protected', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('method', sa.String(length=8), nullable=False),
    sa.Column('spec', sa.Text(), nullable=True),
    sa.Column('interpretation_id', sa.Integer(), nullable=True),
    sa.Column('instructions_snapshot', sa.Text(), nullable=True),
    sa.Column('created_by_account_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("method IN ('CODE', 'AI')", name='ck_bank_ai_rule_version_method'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('rule_id', 'version_no', name='uq_bank_ai_rule_version')
    )
    op.create_table('bank_ai_test_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('instruction_id', sa.Integer(), nullable=True),
    sa.Column('instructions_snapshot', sa.Text(), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('model', sa.String(length=255), nullable=True),
    sa.Column('date_from', sa.Date(), nullable=True),
    sa.Column('date_to', sa.Date(), nullable=True),
    sa.Column('only_unclassified', sa.Boolean(), nullable=False),
    sa.Column('requested_size', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_by_account_id', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('COMPLETED', 'FAILED')", name='ck_bank_ai_test_run_status'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_occurrences',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('canonical_name', sa.String(length=255), nullable=False),
    sa.Column('occurrence_type_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='ACTIVE', nullable=False),
    sa.Column('optional_notes', sa.Text(), nullable=True),
    sa.Column('default_transaction_reason_id', sa.Integer(), nullable=True),
    sa.Column('category_capability', sa.String(length=24), server_default='UNKNOWN', nullable=False),
    sa.Column('capability_source', sa.String(length=24), nullable=True),
    sa.Column('capability_established_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('capability_evidence', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name='ck_bank_occurrence_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('canonical_name', name='uq_bank_occurrence_canonical_name')
    )
    op.create_table('bank_transaction_allocations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('financial_transaction_id', sa.Integer(), nullable=False),
    sa.Column('allocation_index', sa.Integer(), nullable=False),
    sa.Column('amount_minor', sa.Integer(), nullable=False),
    sa.Column('reporting_entity_id', sa.Integer(), nullable=True),
    sa.Column('transaction_reason_id', sa.Integer(), nullable=True),
    sa.Column('accounting_classification_id', sa.Integer(), nullable=True),
    sa.Column('accounting_classification_code_snapshot', sa.String(length=64), nullable=True),
    sa.Column('accounting_classification_name_snapshot', sa.String(length=255), nullable=True),
    sa.Column('accounting_statement_type_snapshot', sa.String(length=16), nullable=True),
    sa.Column('transaction_reason_name_snapshot', sa.String(length=255), nullable=True),
    sa.Column('reporting_entity_name_snapshot', sa.String(length=255), nullable=True),
    sa.Column('accounting_destination_source', sa.String(length=16), server_default='WHY', nullable=False),
    sa.Column('payer_legal_entity_id', sa.Integer(), nullable=True),
    sa.Column('payer_kind', sa.String(length=16), nullable=True),
    sa.Column('economic_owner_legal_entity_id', sa.Integer(), nullable=True),
    sa.Column('intercompany_outcome', sa.String(length=32), nullable=True),
    sa.Column('intercompany_due_from_code_snapshot', sa.String(length=64), nullable=True),
    sa.Column('intercompany_due_to_code_snapshot', sa.String(length=64), nullable=True),
    sa.Column('intercompany_notes', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=24), server_default='UNALLOCATED', nullable=False),
    sa.Column('decision_source', sa.String(length=8), nullable=True),
    sa.Column('decided_by_account_id', sa.Integer(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('evidence_kind', sa.String(length=32), nullable=True),
    sa.Column('evidence_reference', sa.String(length=255), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("accounting_destination_source IN ('WHY', 'TRANSACTION')", name='ck_bta_destination_source'),
    sa.CheckConstraint("decision_source IS NULL OR decision_source IN ('HUMAN', 'RULE')", name='ck_bta_decision_source'),
    sa.CheckConstraint("intercompany_outcome IS NULL OR intercompany_outcome IN ('NONE', 'CROSS_ENTITY', 'PERSONAL_PAYER_DUE_TO', 'PERSONAL_PAYER_CONTRIBUTION', 'NOT_DERIVABLE')", name='ck_bta_intercompany_outcome'),
    sa.CheckConstraint("payer_kind IS NULL OR payer_kind IN ('LEGAL_ENTITY', 'PERSONAL', 'UNRESOLVED')", name='ck_bta_payer_kind'),
    sa.CheckConstraint("status <> 'COMPLETE' OR (reporting_entity_id IS NOT NULL AND transaction_reason_id IS NOT NULL AND accounting_classification_code_snapshot IS NOT NULL)", name='ck_bta_complete_requires_resolution'),
    sa.CheckConstraint("status IN ('UNALLOCATED', 'PENDING_EVIDENCE', 'NEEDS_OPERATOR', 'COMPLETE')", name='ck_bta_status'),
    sa.CheckConstraint('amount_minor <> 0', name='ck_bta_amount_not_zero'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('financial_transaction_id', 'allocation_index', name='uq_bta_transaction_index')
    )
    op.create_table('bank_transaction_reason_export_mappings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bank_transaction_reason_id', sa.Integer(), nullable=False),
    sa.Column('food_cost', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('operative', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('deductible', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('what_label', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('bank_transaction_reason_id', name='uq_btrem_reason_id')
    )
    op.create_table('payment_instruments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('legal_entity_id', sa.Integer(), nullable=True),
    sa.Column('owner_reporting_entity_id', sa.Integer(), nullable=True),
    sa.Column('instrument_type', sa.String(length=16), nullable=False),
    sa.Column('provider', sa.String(length=255), nullable=True),
    sa.Column('display_name', sa.String(length=255), nullable=False),
    sa.Column('institution', sa.String(length=64), nullable=True),
    sa.Column('last_four', sa.String(length=4), nullable=True),
    sa.Column('external_account_identifier', sa.String(length=128), nullable=True),
    sa.Column('currency', sa.String(length=8), nullable=True),
    sa.Column('linked_instrument_id', sa.Integer(), nullable=True),
    sa.Column('source_system_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('effective_start_date', sa.Date(), nullable=True),
    sa.Column('effective_end_date', sa.Date(), nullable=True),
    sa.Column('lifecycle_end_reason', sa.String(length=16), nullable=True),
    sa.Column('replaced_by_instrument_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("instrument_type IN ('BANK_ACCOUNT', 'CREDIT_CARD', 'PAYPAL', 'PURCHASE_PLATFORM')", name='ck_pi_instrument_type'),
    sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name='ck_pi_status'),
    sa.CheckConstraint('legal_entity_id IS NULL OR owner_reporting_entity_id IS NULL', name='ck_payment_instrument_single_owner'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_ai_rule_previews',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('draft_id', sa.Integer(), nullable=True),
    sa.Column('rule_text', sa.Text(), nullable=False),
    sa.Column('origin_transaction_id', sa.Integer(), nullable=True),
    sa.Column('date_from', sa.Date(), nullable=True),
    sa.Column('date_to', sa.Date(), nullable=True),
    sa.Column('examined_count', sa.Integer(), nullable=False),
    sa.Column('match_count', sa.Integer(), nullable=False),
    sa.Column('doubt_count', sa.Integer(), nullable=False),
    sa.Column('ai_calls', sa.Integer(), nullable=False),
    sa.Column('method', sa.String(length=8), server_default='AI', nullable=False),
    sa.Column('interpretation', sa.Text(), nullable=True),
    sa.Column('create_missing_who', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('override_protected', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('only_unsettled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('excluded_ai_settled', sa.Integer(), nullable=True),
    sa.Column('who_only', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('scope', sa.String(length=16), nullable=True),
    sa.Column('scope_key', sa.String(length=64), nullable=True),
    sa.Column('planned_updates', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('unchanged_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('protected_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('conflict_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('unresolved_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('model', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_by_account_id', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('COMPLETED', 'FAILED')", name='ck_bank_ai_rule_preview_status'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_ai_test_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('financial_transaction_id', sa.Integer(), nullable=True),
    sa.Column('posting_date', sa.Date(), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('amount_minor', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=8), nullable=True),
    sa.Column('source_label', sa.String(length=255), nullable=True),
    sa.Column('current_who_name', sa.String(length=255), nullable=True),
    sa.Column('current_why_name', sa.String(length=255), nullable=True),
    sa.Column('proposed_who_name', sa.String(length=255), nullable=True),
    sa.Column('proposed_who_id', sa.Integer(), nullable=True),
    sa.Column('proposed_who_is_new', sa.Boolean(), nullable=False),
    sa.Column('proposed_why_name', sa.String(length=255), nullable=True),
    sa.Column('proposed_why_id', sa.Integer(), nullable=True),
    sa.Column('proposed_why_is_new', sa.Boolean(), nullable=False),
    sa.Column('to_verify', sa.Boolean(), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=True),
    sa.Column('doubt', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_card_settlement_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('credit_card_payment_instrument_id', sa.Integer(), nullable=False),
    sa.Column('settlement_bank_account_id', sa.Integer(), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_account_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('credit_card_payment_instrument_id <> settlement_bank_account_id', name='ck_bcsa_not_self'),
    sa.CheckConstraint('valid_to IS NULL OR valid_to > valid_from', name='ck_bcsa_period'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_evidence_bypass_authorizations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('financial_transaction_id', sa.Integer(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('missing_document_note', sa.Text(), nullable=True),
    sa.Column('occurrence_id', sa.Integer(), nullable=True),
    sa.Column('occurrence_name_snapshot', sa.String(length=255), nullable=True),
    sa.Column('capability_snapshot', sa.String(length=32), nullable=True),
    sa.Column('authorized_by_account_id', sa.Integer(), nullable=True),
    sa.Column('authorized_by_name', sa.String(length=255), nullable=True),
    sa.Column('authorized_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_historical_instrument_candidates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('institution', sa.String(length=64), nullable=True),
    sa.Column('last_four', sa.String(length=4), nullable=False),
    sa.Column('discovery', sa.String(length=48), nullable=False),
    sa.Column('evidence', sa.Text(), nullable=False),
    sa.Column('first_seen_date', sa.Date(), nullable=True),
    sa.Column('last_seen_date', sa.Date(), nullable=True),
    sa.Column('occurrence_count', sa.Integer(), nullable=False),
    sa.Column('resolution', sa.String(length=40), nullable=True),
    sa.Column('resolution_note', sa.Text(), nullable=True),
    sa.Column('resolution_effective_date', sa.Date(), nullable=True),
    sa.Column('resolved_payment_instrument_id', sa.Integer(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_by_account_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("discovery IN ('DIRECT_SOURCE', 'INDIRECT_REFERENCE')", name='ck_bhic_discovery'),
    sa.CheckConstraint("resolution IS NULL OR resolution IN ('CONFIRMED_INSTRUMENT', 'SOURCE_FILE_MISSING', 'CLOSED', 'LOST', 'REPLACED', 'OTHER', 'NOT_OUR_INSTRUMENT')", name='ck_bhic_resolution'),
    sa.CheckConstraint('length(last_four) = 4', name='ck_bhic_last_four'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('institution', 'last_four', name='uq_bhic_identity')
    )
    op.create_table('bank_import_batches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('detected_format', sa.String(length=48), nullable=False),
    sa.Column('payment_instrument_id', sa.Integer(), nullable=True),
    sa.Column('original_file_name', sa.String(length=255), nullable=False),
    sa.Column('raw_file_bytes', sa.LargeBinary(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('uploaded_by_account_id', sa.Integer(), nullable=True),
    sa.Column('row_count', sa.Integer(), nullable=False),
    sa.Column('date_range_start', sa.Date(), nullable=True),
    sa.Column('date_range_end', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=24), server_default='RECEIVED', nullable=False),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.Column('overlap_warning', sa.Text(), nullable=True),
    sa.Column('import_log', sa.Text(), nullable=True),
    sa.CheckConstraint("detected_format IN ('CHASE_BANK_ACCOUNT', 'CHASE_CREDIT_CARD_WITH_CARD', 'CHASE_CREDIT_CARD_NO_CARD', 'FIRST_CITIZENS', 'AMEX_QBO', 'AMEX_XLSX', 'AMEX_CSV')", name='ck_bank_import_batch_detected_format'),
    sa.CheckConstraint("status IN ('RECEIVED', 'PARSED', 'NORMALIZED', 'REQUIRES_REVIEW', 'ACCEPTED', 'REJECTED')", name='ck_bank_import_batch_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('sha256', name='uq_bank_import_batches_sha256')
    )
    op.create_table('bank_instrument_identity_audits',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('payment_instrument_id', sa.Integer(), nullable=False),
    sa.Column('field_name', sa.String(length=64), nullable=False),
    sa.Column('previous_value', sa.String(length=255), nullable=True),
    sa.Column('new_value', sa.String(length=255), nullable=True),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('source_evidence', sa.Text(), nullable=False),
    sa.Column('changed_by_account_id', sa.Integer(), nullable=True),
    sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_occurrence_aliases',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('occurrence_id', sa.Integer(), nullable=False),
    sa.Column('alias_text', sa.String(length=255), nullable=False),
    sa.Column('alias_key', sa.String(length=255), nullable=False),
    sa.Column('source_family', sa.String(length=48), nullable=False),
    sa.Column('source', sa.String(length=16), server_default='PARSER', nullable=False),
    sa.Column('first_financial_transaction_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("source IN ('PARSER', 'HUMAN')", name='ck_bank_occurrence_alias_source'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('occurrence_id', 'alias_text', 'source_family', name='uq_bank_occurrence_alias')
    )
    op.create_table('bank_occurrence_reason_associations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('occurrence_id', sa.Integer(), nullable=False),
    sa.Column('transaction_reason_id', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('confirmation_count', sa.Integer(), server_default='1', nullable=False),
    sa.Column('first_confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source', sa.String(length=16), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('occurrence_id', 'transaction_reason_id', name='uq_bank_occurrence_reason_association')
    )
    op.create_table('bank_occurrence_reporting_entities',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('occurrence_id', sa.Integer(), nullable=False),
    sa.Column('reporting_entity_id', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('occurrence_id', 'reporting_entity_id', name='uq_bank_occurrence_reporting_entity')
    )
    op.create_table('bank_occurrence_suppliers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('occurrence_id', sa.Integer(), nullable=False),
    sa.Column('supplier_id', sa.Integer(), nullable=False),
    sa.Column('link_source', sa.String(length=16), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('occurrence_id', 'supplier_id', name='uq_bos_occurrence_supplier')
    )
    op.create_table('reporting_entity_destination_aliases',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('normalized_key', sa.String(length=512), nullable=False),
    sa.Column('raw_value', sa.String(length=512), nullable=False),
    sa.Column('scope', sa.String(length=16), server_default='GLOBAL', nullable=False),
    sa.Column('supplier_id', sa.Integer(), nullable=True),
    sa.Column('reporting_entity_id', sa.Integer(), nullable=False),
    sa.Column('confirmation_source', sa.String(length=24), nullable=False),
    sa.Column('evidence', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='ACTIVE', nullable=False),
    sa.Column('confirmed_by_account_id', sa.Integer(), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(scope = 'GLOBAL' AND supplier_id IS NULL) OR (scope = 'SUPPLIER' AND supplier_id IS NOT NULL)", name='ck_reda_scope_supplier'),
    sa.CheckConstraint("confirmation_source IN ('DOCUMENT_EVIDENCE', 'SYSTEM_EVIDENCE', 'HUMAN')", name='ck_reda_confirmation_source'),
    sa.CheckConstraint("scope IN ('GLOBAL', 'SUPPLIER')", name='ck_reda_scope'),
    sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name='ck_reda_status'),
    sa.CheckConstraint('length(normalized_key) > 0', name='ck_reda_key_not_empty'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_ai_rule_applications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rule_id', sa.Integer(), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('mode', sa.String(length=16), nullable=False),
    sa.Column('preview_id', sa.Integer(), nullable=True),
    sa.Column('import_batch_id', sa.Integer(), nullable=True),
    sa.Column('examined', sa.Integer(), nullable=False),
    sa.Column('updated', sa.Integer(), nullable=False),
    sa.Column('unchanged', sa.Integer(), nullable=False),
    sa.Column('protected', sa.Integer(), nullable=False),
    sa.Column('conflicts', sa.Integer(), nullable=False),
    sa.Column('unresolved', sa.Integer(), nullable=False),
    sa.Column('errors', sa.Integer(), nullable=False),
    sa.Column('only_unsettled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('excluded_ai_settled', sa.Integer(), nullable=True),
    sa.Column('who_only', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('who_created', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_by_account_id', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("mode IN ('EXISTING_ALL', 'SELECTED', 'IMPORT')", name='ck_bank_ai_rule_application_mode'),
    sa.CheckConstraint("status IN ('COMPLETED', 'FAILED')", name='ck_bank_ai_rule_application_status'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_ai_rule_preview_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('preview_id', sa.Integer(), nullable=False),
    sa.Column('financial_transaction_id', sa.Integer(), nullable=True),
    sa.Column('verdict', sa.String(length=8), nullable=False),
    sa.Column('is_origin', sa.Boolean(), nullable=False),
    sa.Column('posting_date', sa.Date(), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('amount_minor', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=8), nullable=True),
    sa.Column('source_label', sa.String(length=255), nullable=True),
    sa.Column('current_who_name', sa.String(length=255), nullable=True),
    sa.Column('current_why_name', sa.String(length=255), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('proposed_who_name', sa.String(length=255), nullable=True),
    sa.Column('proposed_who_id', sa.Integer(), nullable=True),
    sa.Column('proposed_who_is_new', sa.Boolean(), nullable=False),
    sa.Column('extracted_who_name', sa.String(length=255), nullable=True),
    sa.Column('proposed_why_name', sa.String(length=255), nullable=True),
    sa.Column('proposed_why_id', sa.Integer(), nullable=True),
    sa.Column('proposed_why_is_new', sa.Boolean(), nullable=False),
    sa.Column('plan', sa.String(length=12), nullable=True),
    sa.Column('plan_note', sa.Text(), nullable=True),
    sa.Column('to_verify', sa.String(length=16), nullable=True),
    sa.Column('current_for_whom_name', sa.String(length=255), nullable=True),
    sa.Column('proposed_for_whom_name', sa.String(length=255), nullable=True),
    sa.Column('proposed_for_whom_id', sa.Integer(), nullable=True),
    sa.CheckConstraint("verdict IN ('MATCH', 'DOUBT')", name='ck_bank_ai_rule_preview_item_verdict'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_card_holder_assignments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('credit_card_payment_instrument_id', sa.Integer(), nullable=False),
    sa.Column('holder_kind', sa.String(length=24), nullable=False),
    sa.Column('holder_acting_identity_id', sa.Integer(), nullable=True),
    sa.Column('holder_employee_id', sa.Integer(), nullable=True),
    sa.Column('holder_display_name', sa.String(length=255), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_account_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(holder_kind = 'ACTING_IDENTITY' AND holder_acting_identity_id IS NOT NULL  AND holder_employee_id IS NULL) OR (holder_kind = 'EMPLOYEE' AND holder_employee_id IS NOT NULL  AND holder_acting_identity_id IS NULL) OR (holder_kind = 'UNLINKED_PERSON' AND holder_acting_identity_id IS NULL  AND holder_employee_id IS NULL)", name='ck_bcha_holder_reference_matches_kind'),
    sa.CheckConstraint("holder_kind IN ('ACTING_IDENTITY', 'EMPLOYEE', 'UNLINKED_PERSON')", name='ck_bcha_holder_kind'),
    sa.CheckConstraint('valid_to IS NULL OR valid_to > valid_from', name='ck_bcha_period'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_instrument_assignment_audits',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('scope', sa.String(length=16), nullable=False),
    sa.Column('import_batch_id', sa.Integer(), nullable=True),
    sa.Column('financial_transaction_id', sa.Integer(), nullable=True),
    sa.Column('previous_payment_instrument_id', sa.Integer(), nullable=True),
    sa.Column('new_payment_instrument_id', sa.Integer(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('affected_transaction_count', sa.Integer(), nullable=False),
    sa.Column('changed_by_account_id', sa.Integer(), nullable=True),
    sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(scope = 'BATCH' AND import_batch_id IS NOT NULL AND financial_transaction_id IS NULL) OR (scope = 'TRANSACTION' AND financial_transaction_id IS NOT NULL)", name='ck_biaa_scope_target'),
    sa.CheckConstraint("scope IN ('BATCH', 'TRANSACTION')", name='ck_biaa_scope'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_monthly_instrument_coverages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('period_id', sa.Integer(), nullable=False),
    sa.Column('payment_instrument_id', sa.Integer(), nullable=False),
    sa.Column('expectation', sa.String(length=32), nullable=False),
    sa.Column('expectation_basis', sa.Text(), nullable=True),
    sa.Column('import_batch_id', sa.Integer(), nullable=True),
    sa.Column('resolution', sa.String(length=32), nullable=True),
    sa.Column('resolution_note', sa.Text(), nullable=True),
    sa.Column('resolution_effective_date', sa.Date(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_by_account_id', sa.Integer(), nullable=True),
    sa.Column('instrument_display_name_snapshot', sa.String(length=255), nullable=True),
    sa.Column('institution_snapshot', sa.String(length=64), nullable=True),
    sa.Column('last_four_snapshot', sa.String(length=4), nullable=True),
    sa.Column('instrument_status_snapshot', sa.String(length=16), nullable=True),
    sa.Column('lifecycle_label_snapshot', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("expectation IN ('EXPECTED', 'NOT_EXPECTED', 'NEEDS_HUMAN_CONFIRMATION')", name='ck_bmic_expectation'),
    sa.CheckConstraint("resolution IS NULL OR resolution IN ('NO_ACTIVITY', 'CLOSED', 'LOST', 'REPLACED', 'OTHER', 'SOURCE_FILE_MISSING', 'NOT_EXPECTED_CONFIRMED', 'STILL_ACTIVE')", name='ck_bmic_resolution'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('period_id', 'payment_instrument_id', name='uq_bmic_period_instrument')
    )
    op.create_table('bank_source_instrument_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('detected_format', sa.String(length=48), nullable=False),
    sa.Column('file_name_key', sa.String(length=255), nullable=True),
    sa.Column('account_hint', sa.String(length=128), nullable=True),
    sa.Column('payment_instrument_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='ACTIVE', nullable=False),
    sa.Column('created_from_batch_id', sa.Integer(), nullable=True),
    sa.Column('created_by_account_id', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name='ck_bsip_status'),
    sa.CheckConstraint('file_name_key IS NOT NULL OR account_hint IS NOT NULL', name='ck_bsip_has_key'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('detected_format', 'file_name_key', 'account_hint', name='uq_bsip_format_name_hint')
    )
    op.create_table('raw_bank_transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('import_batch_id', sa.Integer(), nullable=False),
    sa.Column('row_number', sa.Integer(), nullable=False),
    sa.Column('raw_fields', sa.JSON(), nullable=False),
    sa.Column('row_fingerprint', sa.String(length=128), nullable=False),
    sa.Column('parse_status', sa.String(length=16), nullable=False),
    sa.Column('anomalies', sa.Text(), nullable=True),
    sa.Column('normalized_transaction_id', sa.Integer(), nullable=True),
    sa.CheckConstraint("parse_status IN ('PARSED', 'ANOMALOUS', 'UNREADABLE')", name='ck_raw_bank_transaction_parse_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('import_batch_id', 'row_number', name='uq_raw_bank_transaction_batch_row')
    )
    op.create_table('supplier_item_category_learnings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('supplier_id', sa.Integer(), nullable=False),
    sa.Column('identity_kind', sa.String(length=32), nullable=False),
    sa.Column('identity_value', sa.String(length=512), nullable=False),
    sa.Column('supplier_product_id', sa.Integer(), nullable=True),
    sa.Column('transaction_reason_id', sa.Integer(), nullable=False),
    sa.Column('confirmation_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('status', sa.String(length=16), server_default='OBSERVED', nullable=False),
    sa.Column('contradiction_note', sa.Text(), nullable=True),
    sa.Column('first_confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("identity_kind IN ('SUPPLIER_PRODUCT', 'SUPPLIER_ITEM_CODE', 'NORMALIZED_DESCRIPTION')", name='ck_sicl_identity_kind'),
    sa.CheckConstraint("status IN ('OBSERVED', 'LEARNED', 'CONTRADICTED')", name='ck_sicl_status'),
    sa.CheckConstraint('confirmation_count >= 0', name='ck_sicl_confirmation_count'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('supplier_id', 'identity_kind', 'identity_value', 'transaction_reason_id', name='uq_sicl_identity_reason')
    )
    op.create_table('bank_ai_rule_application_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('application_id', sa.Integer(), nullable=False),
    sa.Column('financial_transaction_id', sa.Integer(), nullable=True),
    sa.Column('outcome', sa.String(length=12), nullable=False),
    sa.Column('who_before', sa.String(length=255), nullable=True),
    sa.Column('why_before', sa.String(length=255), nullable=True),
    sa.Column('who_after', sa.String(length=255), nullable=True),
    sa.Column('why_after', sa.String(length=255), nullable=True),
    sa.Column('explanation_id', sa.Integer(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('for_whom_before', sa.String(length=255), nullable=True),
    sa.Column('for_whom_after', sa.String(length=255), nullable=True),
    sa.CheckConstraint("outcome IN ('UPDATED', 'UNCHANGED', 'PROTECTED', 'CONFLICT', 'UNRESOLVED', 'ERROR')", name='ck_bank_ai_rule_application_item_outcome'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bank_historical_instrument_candidate_evidence',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('candidate_id', sa.Integer(), nullable=False),
    sa.Column('evidence_key', sa.String(length=128), nullable=False),
    sa.Column('evidence_kind', sa.String(length=48), nullable=False),
    sa.Column('raw_bank_transaction_id', sa.Integer(), nullable=True),
    sa.Column('financial_transaction_id', sa.Integer(), nullable=True),
    sa.Column('first_observed_date', sa.Date(), nullable=True),
    sa.Column('last_observed_date', sa.Date(), nullable=True),
    sa.Column('occurrences', sa.Integer(), server_default='1', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('occurrences >= 1', name='ck_bhice_occurrences_positive'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('candidate_id', 'evidence_key', name='uq_bhice_candidate_evidence')
    )
    op.create_table('bank_invoice_matches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('financial_transaction_id', sa.Integer(), nullable=False),
    sa.Column('purchase_document_id', sa.Integer(), nullable=False),
    sa.Column('matched_amount_minor', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='PROPOSED', nullable=False),
    sa.Column('match_method', sa.String(length=8), nullable=False),
    sa.Column('confidence', sa.String(length=16), nullable=True),
    sa.Column('match_basis', sa.Text(), nullable=True),
    sa.Column('difference_minor', sa.Integer(), nullable=True),
    sa.Column('difference_kind', sa.String(length=24), nullable=True),
    sa.Column('difference_note', sa.Text(), nullable=True),
    sa.Column('decided_by_account_id', sa.Integer(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("difference_kind IS NULL OR difference_kind IN ('NONE', 'TAX', 'FREIGHT', 'FEE', 'CREDIT', 'DISCOUNT', 'PARTIAL_PAYMENT', 'UNEXPLAINED')", name='ck_bim_difference_kind'),
    sa.CheckConstraint("match_method IN ('AUTO', 'HUMAN')", name='ck_bim_match_method'),
    sa.CheckConstraint("status IN ('PROPOSED', 'CONFIRMED', 'REJECTED')", name='ck_bim_status'),
    sa.CheckConstraint('matched_amount_minor <> 0', name='ck_bim_amount_not_zero'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('financial_transaction_id', 'purchase_document_id', name='uq_bim_transaction_document')
    )
    op.create_table('purchase_line_classifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('purchase_line_id', sa.Integer(), nullable=False),
    sa.Column('purchase_document_id', sa.Integer(), nullable=False),
    sa.Column('transaction_reason_id', sa.Integer(), nullable=True),
    sa.Column('reporting_entity_id', sa.Integer(), nullable=True),
    sa.Column('accounting_classification_id', sa.Integer(), nullable=True),
    sa.Column('accounting_classification_code_snapshot', sa.String(length=64), nullable=True),
    sa.Column('accounting_statement_type_snapshot', sa.String(length=16), nullable=True),
    sa.Column('transaction_reason_name_snapshot', sa.String(length=255), nullable=True),
    sa.Column('decision_source', sa.String(length=24), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='PROPOSED', nullable=False),
    sa.Column('confidence', sa.String(length=16), nullable=True),
    sa.Column('evidence', sa.Text(), nullable=True),
    sa.Column('learning_id', sa.Integer(), nullable=True),
    sa.Column('is_override', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('decided_by_account_id', sa.Integer(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("decision_source IN ('HUMAN', 'LEARNED', 'DOCUMENT_EVIDENCE')", name='ck_plc_decision_source'),
    sa.CheckConstraint("status IN ('PROPOSED', 'CONFIRMED')", name='ck_plc_status'),
    sa.PrimaryKeyConstraint('id')
    )


def _create_indexes() -> None:
    op.create_index(op.f('ix_bank_accounting_classifications_parent_id'), 'bank_accounting_classifications', ['parent_id'], unique=False)
    op.create_index(op.f('ix_bank_transaction_explanations_financial_transaction_id'), 'bank_transaction_explanations', ['financial_transaction_id'], unique=False)
    op.create_index(op.f('ix_financial_transactions_payment_instrument_id'), 'financial_transactions', ['payment_instrument_id'], unique=False)
    op.create_index('ix_ft_accounting_canonical_id', 'financial_transactions', ['accounting_canonical_transaction_id'], unique=False)
    op.create_index('ix_ft_accounting_dedup_key', 'financial_transactions', ['accounting_dedup_key'], unique=False)
    op.create_index('ix_ft_fingerprint', 'financial_transactions', ['fingerprint'], unique=False)
    op.create_index('ix_ft_instrument_datetime', 'financial_transactions', ['payment_instrument_id', 'transaction_datetime'], unique=False)
    op.create_index('ix_ft_instrument_posting_date_amount', 'financial_transactions', ['payment_instrument_id', 'posting_date', 'amount_minor'], unique=False)
    op.create_index('ix_ft_source_system_id', 'financial_transactions', ['source_system_id'], unique=False)
    op.create_index(op.f('ix_bank_transaction_reasons_accounting_classification_id'), 'bank_transaction_reasons', ['accounting_classification_id'], unique=False)
    op.create_index(op.f('ix_bank_transaction_reasons_reason_group_id'), 'bank_transaction_reasons', ['reason_group_id'], unique=False)
    op.create_index('ix_ftm_transaction_a_id', 'financial_transaction_matches', ['transaction_a_id'], unique=False)
    op.create_index('ix_ftm_transaction_b_id', 'financial_transaction_matches', ['transaction_b_id'], unique=False)
    op.create_index('ix_reporting_entity_group_id', 'reporting_entities', ['reporting_group_id'], unique=False)
    op.create_index('ux_reporting_entity_legal_entity', 'reporting_entities', ['legal_entity_id'], unique=True, sqlite_where=sa.text('legal_entity_id IS NOT NULL'), postgresql_where=sa.text('legal_entity_id IS NOT NULL'))
    op.create_index(op.f('ix_bank_ai_rule_drafts_origin_transaction_id'), 'bank_ai_rule_drafts', ['origin_transaction_id'], unique=False)
    op.create_index(op.f('ix_bank_ai_rule_versions_rule_id'), 'bank_ai_rule_versions', ['rule_id'], unique=False)
    op.create_index(op.f('ix_bank_occurrences_default_transaction_reason_id'), 'bank_occurrences', ['default_transaction_reason_id'], unique=False)
    op.create_index(op.f('ix_bank_occurrences_occurrence_type_id'), 'bank_occurrences', ['occurrence_type_id'], unique=False)
    op.create_index('ix_bta_financial_transaction_id', 'bank_transaction_allocations', ['financial_transaction_id'], unique=False)
    op.create_index('ix_bta_reporting_entity_id', 'bank_transaction_allocations', ['reporting_entity_id'], unique=False)
    op.create_index('ix_bta_status', 'bank_transaction_allocations', ['status'], unique=False)
    op.create_index('ix_bta_transaction_reason_id', 'bank_transaction_allocations', ['transaction_reason_id'], unique=False)
    op.create_index(op.f('ix_payment_instruments_external_account_identifier'), 'payment_instruments', ['external_account_identifier'], unique=False)
    op.create_index('ix_pi_legal_entity_id', 'payment_instruments', ['legal_entity_id'], unique=False)
    op.create_index('ix_pi_linked_instrument_id', 'payment_instruments', ['linked_instrument_id'], unique=False)
    op.create_index('ix_pi_source_system_id', 'payment_instruments', ['source_system_id'], unique=False)
    op.create_index(op.f('ix_bank_ai_rule_previews_draft_id'), 'bank_ai_rule_previews', ['draft_id'], unique=False)
    op.create_index(op.f('ix_bank_ai_test_results_financial_transaction_id'), 'bank_ai_test_results', ['financial_transaction_id'], unique=False)
    op.create_index(op.f('ix_bank_ai_test_results_run_id'), 'bank_ai_test_results', ['run_id'], unique=False)
    op.create_index('ix_bcsa_card_id', 'bank_card_settlement_accounts', ['credit_card_payment_instrument_id'], unique=False)
    op.create_index('ix_bcsa_settlement_id', 'bank_card_settlement_accounts', ['settlement_bank_account_id'], unique=False)
    op.create_index('ux_bcsa_one_open_per_card', 'bank_card_settlement_accounts', ['credit_card_payment_instrument_id'], unique=True, sqlite_where=sa.text('valid_to IS NULL'), postgresql_where=sa.text('valid_to IS NULL'))
    op.create_index('ix_beba_financial_transaction_id', 'bank_evidence_bypass_authorizations', ['financial_transaction_id'], unique=False)
    op.create_index('ix_biia_payment_instrument_id', 'bank_instrument_identity_audits', ['payment_instrument_id'], unique=False)
    op.create_index(op.f('ix_bank_occurrence_aliases_alias_key'), 'bank_occurrence_aliases', ['alias_key'], unique=False)
    op.create_index(op.f('ix_bank_occurrence_aliases_occurrence_id'), 'bank_occurrence_aliases', ['occurrence_id'], unique=False)
    op.create_index(op.f('ix_bank_occurrence_reason_associations_occurrence_id'), 'bank_occurrence_reason_associations', ['occurrence_id'], unique=False)
    op.create_index(op.f('ix_bank_occurrence_reason_associations_transaction_reason_id'), 'bank_occurrence_reason_associations', ['transaction_reason_id'], unique=False)
    op.create_index('ix_bore_occurrence_id', 'bank_occurrence_reporting_entities', ['occurrence_id'], unique=False)
    op.create_index('ix_bore_reporting_entity_id', 'bank_occurrence_reporting_entities', ['reporting_entity_id'], unique=False)
    op.create_index('ix_bos_occurrence_id', 'bank_occurrence_suppliers', ['occurrence_id'], unique=False)
    op.create_index('ix_bos_supplier_id', 'bank_occurrence_suppliers', ['supplier_id'], unique=False)
    op.create_index('ix_reda_normalized_key', 'reporting_entity_destination_aliases', ['normalized_key'], unique=False)
    op.create_index('ix_reda_reporting_entity_id', 'reporting_entity_destination_aliases', ['reporting_entity_id'], unique=False)
    op.create_index(op.f('ix_reporting_entity_destination_aliases_supplier_id'), 'reporting_entity_destination_aliases', ['supplier_id'], unique=False)
    op.create_index('ux_reda_global_key', 'reporting_entity_destination_aliases', ['normalized_key'], unique=True, sqlite_where=sa.text('supplier_id IS NULL'), postgresql_where=sa.text('supplier_id IS NULL'))
    op.create_index('ux_reda_supplier_key', 'reporting_entity_destination_aliases', ['supplier_id', 'normalized_key'], unique=True, sqlite_where=sa.text('supplier_id IS NOT NULL'), postgresql_where=sa.text('supplier_id IS NOT NULL'))
    op.create_index(op.f('ix_bank_ai_rule_applications_rule_id'), 'bank_ai_rule_applications', ['rule_id'], unique=False)
    op.create_index(op.f('ix_bank_ai_rule_preview_items_financial_transaction_id'), 'bank_ai_rule_preview_items', ['financial_transaction_id'], unique=False)
    op.create_index(op.f('ix_bank_ai_rule_preview_items_preview_id'), 'bank_ai_rule_preview_items', ['preview_id'], unique=False)
    op.create_index('ix_bcha_card_id', 'bank_card_holder_assignments', ['credit_card_payment_instrument_id'], unique=False)
    op.create_index('ux_bcha_one_open_per_card', 'bank_card_holder_assignments', ['credit_card_payment_instrument_id'], unique=True, sqlite_where=sa.text('valid_to IS NULL'), postgresql_where=sa.text('valid_to IS NULL'))
    op.create_index('ix_biaa_financial_transaction_id', 'bank_instrument_assignment_audits', ['financial_transaction_id'], unique=False)
    op.create_index('ix_biaa_import_batch_id', 'bank_instrument_assignment_audits', ['import_batch_id'], unique=False)
    op.create_index('ix_bmic_payment_instrument_id', 'bank_monthly_instrument_coverages', ['payment_instrument_id'], unique=False)
    op.create_index('ix_bmic_period_id', 'bank_monthly_instrument_coverages', ['period_id'], unique=False)
    op.create_index('ix_bsip_payment_instrument_id', 'bank_source_instrument_profiles', ['payment_instrument_id'], unique=False)
    op.create_index(op.f('ix_raw_bank_transactions_import_batch_id'), 'raw_bank_transactions', ['import_batch_id'], unique=False)
    op.create_index(op.f('ix_raw_bank_transactions_row_fingerprint'), 'raw_bank_transactions', ['row_fingerprint'], unique=False)
    op.create_index('ix_sicl_supplier_identity', 'supplier_item_category_learnings', ['supplier_id', 'identity_kind', 'identity_value'], unique=False)
    op.create_index(op.f('ix_bank_ai_rule_application_items_application_id'), 'bank_ai_rule_application_items', ['application_id'], unique=False)
    op.create_index(op.f('ix_bank_ai_rule_application_items_financial_transaction_id'), 'bank_ai_rule_application_items', ['financial_transaction_id'], unique=False)
    op.create_index(op.f('ix_bank_historical_instrument_candidate_evidence_candidate_id'), 'bank_historical_instrument_candidate_evidence', ['candidate_id'], unique=False)
    op.create_index('ix_bim_financial_transaction_id', 'bank_invoice_matches', ['financial_transaction_id'], unique=False)
    op.create_index('ix_bim_purchase_document_id', 'bank_invoice_matches', ['purchase_document_id'], unique=False)
    op.create_index('ix_bim_status', 'bank_invoice_matches', ['status'], unique=False)
    op.create_index('ix_plc_purchase_document_id', 'purchase_line_classifications', ['purchase_document_id'], unique=False)
    op.create_index('ix_plc_purchase_line_id', 'purchase_line_classifications', ['purchase_line_id'], unique=False)
    op.create_index('ix_plc_reporting_entity_id', 'purchase_line_classifications', ['reporting_entity_id'], unique=False)


def _create_foreign_keys() -> None:
    op.create_foreign_key(None, 'bank_accounting_classifications', 'bank_accounting_classifications', ['parent_id'], ['id'])
    op.create_foreign_key(None, 'bank_transaction_explanations', 'financial_transactions', ['financial_transaction_id'], ['id'])
    op.create_foreign_key(None, 'bank_transaction_explanations', 'bank_transaction_reasons', ['transaction_reason_id'], ['id'])
    op.create_foreign_key(None, 'bank_transaction_explanations', 'rfone_accounts', ['confirmed_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_transaction_explanations', 'bank_accounting_classifications', ['accounting_classification_id'], ['id'])
    op.create_foreign_key(None, 'bank_transaction_explanations', 'bank_occurrences', ['occurrence_id'], ['id'])
    op.create_foreign_key(None, 'financial_transactions', 'bank_import_batches', ['import_batch_id'], ['id'])
    op.create_foreign_key(None, 'financial_transactions', 'payment_instruments', ['payment_instrument_id'], ['id'])
    op.create_foreign_key(None, 'financial_transactions', 'financial_transactions', ['duplicate_of_transaction_id'], ['id'])
    op.create_foreign_key(None, 'financial_transactions', 'payment_instruments', ['accounting_settlement_account_id'], ['id'])
    op.create_foreign_key(None, 'financial_transactions', 'financial_transactions', ['accounting_canonical_transaction_id'], ['id'])
    op.create_foreign_key(None, 'financial_transactions', 'source_systems', ['source_system_id'], ['id'])
    op.create_foreign_key(None, 'financial_transactions', 'bank_transaction_explanations', ['explanation_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_instructions', 'rfone_accounts', ['created_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rules', 'rfone_accounts', ['deleted_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rules', 'financial_transactions', ['origin_transaction_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(None, 'bank_ai_rules', 'rfone_accounts', ['created_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_monthly_source_periods', 'rfone_accounts', ['completed_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_reconciliation_control_configs', 'rfone_accounts', ['updated_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_transaction_reasons', 'bank_reason_groups', ['reason_group_id'], ['id'])
    op.create_foreign_key(None, 'bank_transaction_reasons', 'bank_accounting_classifications', ['accounting_classification_id'], ['id'])
    op.create_foreign_key(None, 'financial_transaction_matches', 'financial_transactions', ['transaction_a_id'], ['id'])
    op.create_foreign_key(None, 'financial_transaction_matches', 'financial_transactions', ['transaction_b_id'], ['id'])
    op.create_foreign_key(None, 'reporting_entities', 'legal_entities', ['legal_entity_id'], ['id'])
    op.create_foreign_key(None, 'reporting_entities', 'reporting_groups', ['reporting_group_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_drafts', 'bank_ai_rules', ['ai_rule_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_drafts', 'rfone_accounts', ['created_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_drafts', 'financial_transactions', ['origin_transaction_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(None, 'bank_ai_rule_versions', 'bank_ai_rule_interpretations', ['interpretation_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_versions', 'rfone_accounts', ['created_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_versions', 'bank_ai_rules', ['rule_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_test_runs', 'rfone_accounts', ['created_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_test_runs', 'bank_ai_instructions', ['instruction_id'], ['id'])
    op.create_foreign_key(None, 'bank_occurrences', 'bank_occurrence_types', ['occurrence_type_id'], ['id'])
    op.create_foreign_key(None, 'bank_occurrences', 'bank_transaction_reasons', ['default_transaction_reason_id'], ['id'])
    op.create_foreign_key(None, 'bank_transaction_allocations', 'bank_accounting_classifications', ['accounting_classification_id'], ['id'])
    op.create_foreign_key(None, 'bank_transaction_allocations', 'reporting_entities', ['reporting_entity_id'], ['id'])
    op.create_foreign_key(None, 'bank_transaction_allocations', 'legal_entities', ['payer_legal_entity_id'], ['id'])
    op.create_foreign_key(None, 'bank_transaction_allocations', 'rfone_accounts', ['decided_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_transaction_allocations', 'bank_transaction_reasons', ['transaction_reason_id'], ['id'])
    op.create_foreign_key(None, 'bank_transaction_allocations', 'financial_transactions', ['financial_transaction_id'], ['id'])
    op.create_foreign_key(None, 'bank_transaction_allocations', 'legal_entities', ['economic_owner_legal_entity_id'], ['id'])
    op.create_foreign_key(None, 'bank_transaction_reason_export_mappings', 'bank_transaction_reasons', ['bank_transaction_reason_id'], ['id'])
    op.create_foreign_key(None, 'payment_instruments', 'payment_instruments', ['linked_instrument_id'], ['id'])
    op.create_foreign_key(None, 'payment_instruments', 'legal_entities', ['legal_entity_id'], ['id'])
    op.create_foreign_key(None, 'payment_instruments', 'source_systems', ['source_system_id'], ['id'])
    op.create_foreign_key('fk_payment_instrument_owner_reporting_entity', 'payment_instruments', 'reporting_entities', ['owner_reporting_entity_id'], ['id'])
    op.create_foreign_key(None, 'payment_instruments', 'payment_instruments', ['replaced_by_instrument_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_previews', 'rfone_accounts', ['created_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_previews', 'bank_ai_rule_drafts', ['draft_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(None, 'bank_ai_rule_previews', 'financial_transactions', ['origin_transaction_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(None, 'bank_ai_test_results', 'bank_transaction_reasons', ['proposed_why_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_test_results', 'financial_transactions', ['financial_transaction_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(None, 'bank_ai_test_results', 'bank_ai_test_runs', ['run_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(None, 'bank_ai_test_results', 'bank_occurrences', ['proposed_who_id'], ['id'])
    op.create_foreign_key(None, 'bank_card_settlement_accounts', 'payment_instruments', ['settlement_bank_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_card_settlement_accounts', 'rfone_accounts', ['created_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_card_settlement_accounts', 'payment_instruments', ['credit_card_payment_instrument_id'], ['id'])
    op.create_foreign_key(None, 'bank_evidence_bypass_authorizations', 'rfone_accounts', ['authorized_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_evidence_bypass_authorizations', 'bank_occurrences', ['occurrence_id'], ['id'])
    op.create_foreign_key(None, 'bank_evidence_bypass_authorizations', 'financial_transactions', ['financial_transaction_id'], ['id'])
    op.create_foreign_key(None, 'bank_historical_instrument_candidates', 'rfone_accounts', ['resolved_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_historical_instrument_candidates', 'payment_instruments', ['resolved_payment_instrument_id'], ['id'])
    op.create_foreign_key(None, 'bank_import_batches', 'payment_instruments', ['payment_instrument_id'], ['id'])
    op.create_foreign_key(None, 'bank_import_batches', 'rfone_accounts', ['uploaded_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_instrument_identity_audits', 'payment_instruments', ['payment_instrument_id'], ['id'])
    op.create_foreign_key(None, 'bank_instrument_identity_audits', 'rfone_accounts', ['changed_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_occurrence_aliases', 'financial_transactions', ['first_financial_transaction_id'], ['id'])
    op.create_foreign_key(None, 'bank_occurrence_aliases', 'bank_occurrences', ['occurrence_id'], ['id'])
    op.create_foreign_key(None, 'bank_occurrence_reason_associations', 'bank_transaction_reasons', ['transaction_reason_id'], ['id'])
    op.create_foreign_key(None, 'bank_occurrence_reason_associations', 'bank_occurrences', ['occurrence_id'], ['id'])
    op.create_foreign_key('fk_bore_reporting_entity_id', 'bank_occurrence_reporting_entities', 'reporting_entities', ['reporting_entity_id'], ['id'])
    op.create_foreign_key('fk_bore_occurrence_id', 'bank_occurrence_reporting_entities', 'bank_occurrences', ['occurrence_id'], ['id'])
    op.create_foreign_key(None, 'bank_occurrence_suppliers', 'suppliers', ['supplier_id'], ['id'])
    op.create_foreign_key(None, 'bank_occurrence_suppliers', 'bank_occurrences', ['occurrence_id'], ['id'])
    op.create_foreign_key(None, 'reporting_entity_destination_aliases', 'reporting_entities', ['reporting_entity_id'], ['id'])
    op.create_foreign_key(None, 'reporting_entity_destination_aliases', 'suppliers', ['supplier_id'], ['id'])
    op.create_foreign_key(None, 'reporting_entity_destination_aliases', 'rfone_accounts', ['confirmed_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_applications', 'bank_ai_rule_previews', ['preview_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(None, 'bank_ai_rule_applications', 'bank_ai_rules', ['rule_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_applications', 'rfone_accounts', ['created_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_applications', 'bank_ai_rule_versions', ['version_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_applications', 'bank_import_batches', ['import_batch_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_preview_items', 'bank_transaction_reasons', ['proposed_why_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_preview_items', 'bank_ai_rule_previews', ['preview_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(None, 'bank_ai_rule_preview_items', 'reporting_entities', ['proposed_for_whom_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_preview_items', 'bank_occurrences', ['proposed_who_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_preview_items', 'financial_transactions', ['financial_transaction_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(None, 'bank_card_holder_assignments', 'acting_identities', ['holder_acting_identity_id'], ['id'])
    op.create_foreign_key(None, 'bank_card_holder_assignments', 'employees', ['holder_employee_id'], ['id'])
    op.create_foreign_key(None, 'bank_card_holder_assignments', 'payment_instruments', ['credit_card_payment_instrument_id'], ['id'])
    op.create_foreign_key(None, 'bank_card_holder_assignments', 'rfone_accounts', ['created_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_instrument_assignment_audits', 'payment_instruments', ['new_payment_instrument_id'], ['id'])
    op.create_foreign_key(None, 'bank_instrument_assignment_audits', 'bank_import_batches', ['import_batch_id'], ['id'])
    op.create_foreign_key(None, 'bank_instrument_assignment_audits', 'financial_transactions', ['financial_transaction_id'], ['id'])
    op.create_foreign_key(None, 'bank_instrument_assignment_audits', 'rfone_accounts', ['changed_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_instrument_assignment_audits', 'payment_instruments', ['previous_payment_instrument_id'], ['id'])
    op.create_foreign_key(None, 'bank_monthly_instrument_coverages', 'payment_instruments', ['payment_instrument_id'], ['id'])
    op.create_foreign_key(None, 'bank_monthly_instrument_coverages', 'bank_import_batches', ['import_batch_id'], ['id'])
    op.create_foreign_key(None, 'bank_monthly_instrument_coverages', 'rfone_accounts', ['resolved_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_monthly_instrument_coverages', 'bank_monthly_source_periods', ['period_id'], ['id'])
    op.create_foreign_key(None, 'bank_source_instrument_profiles', 'rfone_accounts', ['created_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_source_instrument_profiles', 'bank_import_batches', ['created_from_batch_id'], ['id'])
    op.create_foreign_key(None, 'bank_source_instrument_profiles', 'payment_instruments', ['payment_instrument_id'], ['id'])
    op.create_foreign_key(None, 'raw_bank_transactions', 'bank_import_batches', ['import_batch_id'], ['id'])
    op.create_foreign_key(None, 'raw_bank_transactions', 'financial_transactions', ['normalized_transaction_id'], ['id'])
    op.create_foreign_key(None, 'supplier_item_category_learnings', 'bank_transaction_reasons', ['transaction_reason_id'], ['id'])
    op.create_foreign_key(None, 'supplier_item_category_learnings', 'supplier_products', ['supplier_product_id'], ['id'])
    op.create_foreign_key(None, 'supplier_item_category_learnings', 'suppliers', ['supplier_id'], ['id'])
    op.create_foreign_key(None, 'bank_ai_rule_application_items', 'financial_transactions', ['financial_transaction_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(None, 'bank_ai_rule_application_items', 'bank_ai_rule_applications', ['application_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(None, 'bank_ai_rule_application_items', 'bank_transaction_explanations', ['explanation_id'], ['id'])
    op.create_foreign_key(None, 'bank_historical_instrument_candidate_evidence', 'financial_transactions', ['financial_transaction_id'], ['id'])
    op.create_foreign_key(None, 'bank_historical_instrument_candidate_evidence', 'raw_bank_transactions', ['raw_bank_transaction_id'], ['id'])
    op.create_foreign_key(None, 'bank_historical_instrument_candidate_evidence', 'bank_historical_instrument_candidates', ['candidate_id'], ['id'])
    op.create_foreign_key(None, 'bank_invoice_matches', 'purchase_documents', ['purchase_document_id'], ['id'])
    op.create_foreign_key(None, 'bank_invoice_matches', 'rfone_accounts', ['decided_by_account_id'], ['id'])
    op.create_foreign_key(None, 'bank_invoice_matches', 'financial_transactions', ['financial_transaction_id'], ['id'])
    op.create_foreign_key(None, 'purchase_line_classifications', 'purchase_lines', ['purchase_line_id'], ['id'])
    op.create_foreign_key(None, 'purchase_line_classifications', 'bank_transaction_reasons', ['transaction_reason_id'], ['id'])
    op.create_foreign_key(None, 'purchase_line_classifications', 'rfone_accounts', ['decided_by_account_id'], ['id'])
    op.create_foreign_key(None, 'purchase_line_classifications', 'purchase_documents', ['purchase_document_id'], ['id'])
    op.create_foreign_key(None, 'purchase_line_classifications', 'reporting_entities', ['reporting_entity_id'], ['id'])
    op.create_foreign_key(None, 'purchase_line_classifications', 'supplier_item_category_learnings', ['learning_id'], ['id'])
    op.create_foreign_key(None, 'purchase_line_classifications', 'bank_accounting_classifications', ['accounting_classification_id'], ['id'])


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    present = sorted(t for t in EXPECTED_COLUMNS if t in existing)
    if len(present) == len(EXPECTED_COLUMNS):
        problems = []
        for table, columns in EXPECTED_COLUMNS.items():
            actual = sorted(c["name"] for c in inspector.get_columns(table))
            if actual != sorted(columns):
                missing = sorted(set(columns) - set(actual))
                extra = sorted(set(actual) - set(columns))
                problems.append(f"{table}: missing {missing}, unexpected {extra}")
        if problems:
            raise RuntimeError("The Bank tables exist but differ from the expected schema; nothing was changed: "
                               + "; ".join(problems))
        return
    if present:
        raise RuntimeError(f"Only {len(present)} of {len(EXPECTED_COLUMNS)} Bank tables exist ({', '.join(present)}): "
                           "a partial Bank schema is never completed; nothing was changed.")
    if bind.dialect.name != "postgresql":
        raise RuntimeError("Creating the Bank schema from zero is supported on PostgreSQL only (RDS).")
    _create_tables()
    _create_indexes()
    _create_foreign_keys()


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return  # this revision creates tables only on PostgreSQL: elsewhere it only verified, nothing to undo
    raise RuntimeError("c8e4b2a6f0d1 reinstalled Bank; it is not undone by a migration. Restore the RDS snapshot "
                       "taken before the reinstall.")
