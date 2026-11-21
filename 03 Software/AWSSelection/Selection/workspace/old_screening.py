"""Local adapter to Old's actual Primary Screening service, not a second engine."""
import hashlib
import json
import os
from sqlalchemy import select
from rfone_data_store import models as m
from rfone_data_store.selection import primary_screening_service as screening, signal_service, fit_assessment_service
from rfone_data_store.selection import workspace_models as ps
from . import position_settings, rule_ai, criterion_copies, screening_context


def enabled():
    return os.environ.get('RFONE_SELECTION_ENGINE') == 'old'


def restaurant_id(db):
    return db.scalar(select(m.Restaurant.id).order_by(m.Restaurant.id))


def criteria(db, position, active_only=False):
    rows = criterion_copies.owned(db, position, active_only=active_only)
    return [c for c in rows if not active_only or not c.location_label or c.location_label == position.location_label]


def signature(rows, position=None):
    payload = {'criteria': [(c.id, c.version, c.is_active, c.criterion_group) for c in rows]}
    if position is not None:
        payload['context'] = screening_context.shared(position)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def apply(db, position, actor):
    """Called by explicit POST only; GETs never evaluate or contact providers."""
    criterion_copies.ensure_research(db, position, restaurant_id=restaurant_id(db))
    selected = criteria(db, position, active_only=True)
    if not selected:
        raise ValueError('Nessun criterio attivo per questa PDL. Configuralo in Criteri di selezione.')
    ids = {}
    pcs = list(db.scalars(select(ps.PositionCandidate).where(ps.PositionCandidate.position_id == position.id)
                          .order_by(ps.PositionCandidate.id)))
    for pc in pcs:
        application = db.get(m.Application, pc.application_id) if pc.application_id else None
        if application is None or application.candidate_id != pc.candidate_id:
            raise ValueError('Una candidatura non è collegata correttamente al motore Old. Nessuna nuova valutazione salvata.')
        if application.target_role != position.role_code:
            raise ValueError('Il ruolo di una candidatura non corrisponde alla PDL. Nessuna nuova valutazione salvata.')
        if position.approved_snapshot_id:
            assessments = fit_assessment_service.list_fit_assessments_for_candidate(db, pc.candidate_id)
            assessment = next((a for a in assessments if a.requirement_set_snapshot_id == position.approved_snapshot_id), None)
            if assessment is None:
                assessment = fit_assessment_service.create_fit_assessment_from_snapshot(db,
                    candidate_id=pc.candidate_id, snapshot_id=position.approved_snapshot_id)
            fit_assessment_service.generate_resume_stage_assessment(db, assessment.id)
        # Reuse existing evidence detector and preserve human-confirmed signals.
        signal_service.generate_resume_stage_signals(db, application.id)
        run = screening.create_screening_run(db, application.id,
            research_id=position.id, evaluation_context=screening_context.for_candidate(db, position, pc),
            criterion_ids=[c.id for c in selected], ai_generate_json_fn=lambda prompt: rule_ai.generate(
                prompt + '\nReturn explanation and interpretation in Italian. Keep JSON enum values and quoted evidence unchanged.'))
        ids[str(pc.id)] = run.id
    context = position_settings.context(position)
    context['old_screening_run'] = {'role_code': position.role_code, 'signature': signature(selected, position),
        'at': ps.utcnow().isoformat(), 'by': actor.name, 'runs': ids}
    position.organization_context_json = json.dumps(context, ensure_ascii=False)
    ps.log_event(db, position_id=position.id, kind='OLD_SCREENING_APPLIED',
                 detail=f'Criteri Old applicati a {len(pcs)} CV.', actor_id=actor.id, actor_name=actor.name)
    db.commit()


def results(db, position):
    from local_i18n import ui
    saved = position_settings.context(position).get('old_screening_run') or {}
    if saved.get('role_code') != position.role_code:
        return {}, False
    output = {}
    for pc_id, run_id in saved.get('runs', {}).items():
        run = screening.get_run(db, run_id)
        pc = db.get(ps.PositionCandidate, int(pc_id))
        if not run or not pc or pc.position_id != position.id or run.application_id != pc.application_id:
            continue
        evaluations = screening.list_evaluations(db, run.id)
        unknown = [ui(e.criterion_snapshot.name) for e in evaluations if e.status in ('NOT_EVALUATED', 'INSUFFICIENT_EVIDENCE')]
        blocked = [ui(e.criterion_snapshot.name) for e in evaluations if e.is_active_hard_disqualifier and not e.hard_disqualifier_overridden]
        positive = [ui(e.criterion_snapshot.name) for e in sorted(evaluations, key=lambda e: e.contribution, reverse=True) if e.contribution > 0][:3]
        negative = [ui(e.criterion_snapshot.name) for e in sorted(evaluations, key=lambda e: e.contribution) if e.contribution < 0][:3]
        reasons = []
        if blocked:
            reasons.append('Requisiti bloccanti: ' + '; '.join(blocked) + '.')
        if positive:
            reasons.append('Fattori favorevoli: ' + '; '.join(positive) + '.')
        if negative:
            reasons.append('Fattori contrari: ' + '; '.join(negative) + '.')
        if unknown:
            reasons.append('Informazioni da chiarire: ' + '; '.join(unknown) + '.')
        output[str(pc.id)] = {'active': True, 'old_engine': True, 'run_id': run.id,
            'unfit': run.has_active_hard_disqualifier, 'priority': run.priority_index,
            'unknown': any(e.status in ('NOT_EVALUATED', 'INSUFFICIENT_EVIDENCE') for e in evaluations),
            'status': 'Requisito bloccante' if run.has_active_hard_disqualifier else 'Priorità di revisione',
            'reason': ' '.join(reasons) or 'Nessun fattore favorevole o contrario documentato; valutazione da completare.',
            'details': [{'title': ui(e.criterion_snapshot.name),
                         'outcome': None if e.status in ('NOT_EVALUATED', 'INSUFFICIENT_EVIDENCE') else True,
                         'status': e.status, 'level': e.effective_level,
                         'explanation': e.explanation or ''} for e in evaluations]}
    return output, saved.get('signature') != signature(criteria(db, position, active_only=True), position)


def decorate(db, position, rows):
    data, stale = results(db, position)
    for row in rows:
        result = data.get(str(row['pc'].id))
        row['pdl_result'] = result
        row['old_screening_stale'] = stale
    return sorted(rows, key=lambda r: (bool(r['pdl_result'] and r['pdl_result']['unfit']),
        -(r['pdl_result']['priority'] if r['pdl_result'] else 0)))
