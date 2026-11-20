"""Research-owned context and candidate answers for contextual Old screening."""
import hashlib
import json
from sqlalchemy import select
from rfone_data_store import models as m
from rfone_data_store.selection import workspace_models as ps
from . import position_settings, engine

FIELDS = (
    ('tasks', 'Mansioni del ruolo'),
    ('responsibilities', 'Responsabilità'),
    ('skills', 'Competenze, formazione, certificazioni e lingue richieste'),
    ('autonomy', 'Autonomia richiesta'),
    ('schedule', 'Giorni e orari richiesti'),
    ('conditions', 'Condizioni e necessità specifiche della ricerca'),
)


def values(position):
    data = position_settings.context(position).get('screening_context') or {}
    return {key: str(data.get(key) or '') for key, _ in FIELDS}


def version(position):
    return hashlib.sha256(json.dumps(values(position), sort_keys=True).encode()).hexdigest()


def shared(position):
    data = values(position)
    return {
        'role': {'code': position.role_code, 'title': position.title,
            'tasks': data['tasks'] or position.description or None,
            'responsibilities': data['responsibilities'] or None,
            'requirements': data['skills'] or None, 'autonomy': data['autonomy'] or None},
        'research': {'id': position.id, 'location': position.location_label,
            'timezone': position.timezone, 'schedule': data['schedule'] or None,
            'conditions': data['conditions'] or None,
            'approved_snapshot_id': position.approved_snapshot_id,
            'approved_job_ad': position.approved_job_ad_en or None},
    }


def for_candidate(db, position, pc):
    requirements = list(db.scalars(select(m.RequirementSnapshotItem).where(
        m.RequirementSnapshotItem.snapshot_id == position.approved_snapshot_id,
        m.RequirementSnapshotItem.was_active.is_(True)).order_by(m.RequirementSnapshotItem.display_order))) if position.approved_snapshot_id else []
    return {**shared(position), 'evaluated_at': ps.utcnow().isoformat(), 'approved_requirements': [
        {key: getattr(item, key) for key in ('id', 'name', 'description', 'criticality',
            'trainability', 'evidence_positive', 'evidence_contrary', 'evidence_insufficient', 'guidance_notes')}
        for item in requirements], 'candidate_answers': [
        {'source_reference': f'answer:{answer.id}', 'question': answer.question_text,
         'answer': answer.answer_text, 'date': answer.answered_at.isoformat() if answer.answered_at else None}
        for answer in engine.answers(db, pc.id) if answer.answer_text.strip()]}


def save(position, form):
    if form.get('context_version') != version(position):
        raise ValueError('Il contesto è cambiato nel frattempo. Riapri la pagina prima di modificarlo.')
    data = {}
    for key, label in FIELDS:
        value = (form.get('context_' + key) or '').strip()
        if len(value) > 12000:
            raise ValueError(f'{label}: massimo 12000 caratteri.')
        data[key] = value
    context = position_settings.context(position)
    context['screening_context'] = data
    position.organization_context_json = json.dumps(context, ensure_ascii=False)
