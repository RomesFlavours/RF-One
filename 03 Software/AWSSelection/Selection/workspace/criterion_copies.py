"""One-time deep copies of PDL defaults into research-owned Old criteria."""
from copy import deepcopy
import json
from sqlalchemy import inspect, select, text
from rfone_data_store import models as m
from rfone_data_store.selection import primary_screening_service as screening, workspace_models as ps
from . import position_settings

FIELDS = ('criterion_group', 'name', 'description', 'category', 'coefficient', 'direction', 'location_label',
    'is_hard_disqualifier', 'hard_disqualifier_trigger_level', 'level_descriptions',
    'evidence_sources_allowed', 'evaluation_guidance', 'evidence_positive', 'evidence_contrary',
    'evidence_insufficient', 'auto_evaluation_signal_definition_id', 'auto_evaluation_level_map',
    'display_order', 'required_for_phone_review', 'missing_evidence_question_text',
    'missing_evidence_answer_level_map')


def initialize(engine):
    """Explicit additive setup, restricted to disposable SQLite or canonical local PG."""
    if engine.dialect.name != 'sqlite' and (engine.url.host, engine.url.port, engine.url.database) != ('127.0.0.1', 55436, 'rfone_aws_copy'):
        raise RuntimeError('Research criterion setup requires the canonical local database.')
    columns = {c['name'] for c in inspect(engine).get_columns('primary_screening_criteria')}
    with engine.begin() as connection:
        if 'research_id' not in columns:
            connection.execute(text('ALTER TABLE primary_screening_criteria ADD COLUMN research_id INTEGER NULL'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS ix_primary_screening_criteria_research_id ON primary_screening_criteria (research_id)'))
        for table in ('primary_screening_criteria', 'primary_screening_criterion_snapshots'):
            existing = {c['name'] for c in inspect(connection).get_columns(table)}
            if 'criterion_group' not in existing:
                connection.execute(text(f'ALTER TABLE {table} ADD COLUMN criterion_group VARCHAR(32) NULL'))
        existing = {c['name'] for c in inspect(connection).get_columns('primary_screening_runs')}
        if 'evaluation_context' not in existing:
            connection.execute(text('ALTER TABLE primary_screening_runs ADD COLUMN evaluation_context JSON NULL'))


def defaults(db, role_code, restaurant_id=None):
    return [c for c in screening.list_criteria(db, restaurant_id=restaurant_id, active_only=False)
            if c.target_role == role_code]


def owned(db, position, active_only=False):
    query = select(m.PrimaryScreeningCriterion).where(
        m.PrimaryScreeningCriterion.research_id == position.id,
        m.PrimaryScreeningCriterion.target_role == position.role_code).order_by(
        m.PrimaryScreeningCriterion.display_order, m.PrimaryScreeningCriterion.id)
    if active_only:
        query = query.where(m.PrimaryScreeningCriterion.is_active.is_(True))
    return list(db.scalars(query))


def ensure_research(db, position, *, restaurant_id=None):
    """Must run inside creation/migration/explicit write, never as a read fallback."""
    context = position_settings.context(position)
    copies = context.get('old_criteria_copies', {})
    if position.role_code in copies:
        return owned(db, position)
    existing = owned(db, position)
    provenance = []
    if not existing:
        for source in defaults(db, position.role_code, restaurant_id):
            values = {key: deepcopy(getattr(source, key)) for key in FIELDS}
            values['criterion_group'] = values['criterion_group'] or 'ROLE_RESEARCH'
            target = screening.create_criterion(db, restaurant_id=source.restaurant_id,
                target_role=position.role_code, research_id=position.id, **values)
            target.is_active = source.is_active
            provenance.append({'source_id': source.id, 'source_version': source.version, 'copy_id': target.id})
    copies[position.role_code] = {'at': ps.utcnow().isoformat(), 'criteria': provenance,
                                  'existing_owned_ids': [c.id for c in existing]}
    context['old_criteria_copies'] = copies
    position.organization_context_json = json.dumps(context, ensure_ascii=False)
    db.flush()
    return owned(db, position)
