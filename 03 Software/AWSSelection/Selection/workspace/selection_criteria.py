"""PDL-scoped Italian editor of Old's existing PrimaryScreeningCriterion rows."""
import math
from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select
from rfone_data_store import models as m
from rfone_data_store.selection import workspace_models as ps
from rfone_data_store.selection.core import primary_screening_model as psm, signal_model as sm
from . import old_screening, criterion_copies, role_catalog, screening_context
from rfone_data_store.selection import criterion_context
from .routes import bp, access_required, _position, _current_job

SOURCES = {'RESUME': 'Curriculum', 'APPLICATION_HISTORY': 'Candidature precedenti',
    'RESUME_FACT': 'Dati dichiarati nel curriculum', 'RESUME_DERIVED_INFORMATION': 'Indicatori derivati dal curriculum',
    'APPLICATION': 'Candidatura', 'FIT_ASSESSMENT': 'Valutazione dei requisiti',
    'SELEZIONATORE_INPUT': 'Evidenze del selezionatore', 'OTHER': 'Altre evidenze',
    'SELECTION_SIGNAL': 'Segnali di selezione', 'REQUIREMENT_ASSESSMENT': 'Valutazione dei requisiti',
    'PHONE_INTERVIEW': 'Colloquio telefonico', 'IN_PERSON_INTERVIEW': 'Colloquio in presenza',
    'CONSISTENCY_INFORMATION': 'Coerenza delle informazioni'}
SIGNAL_LABELS = {'DETECTED': 'Rilevato', 'POSSIBLE': 'Possibile', 'NOT_DETECTED': 'Non rilevato',
                 'NOT_ASSESSED': 'Non valutato', 'CONFLICTING': 'Contraddittorio', 'TO_CLARIFY': 'Da chiarire'}


def fields(form, db):
    name = (form.get('name') or '').strip()
    if not name or len(name) > 255:
        raise ValueError('Inserisci un nome del criterio, massimo 255 caratteri.')
    coefficient = float(form.get('coefficient', '1'))
    if not math.isfinite(coefficient) or not 0 <= coefficient <= 1000:
        raise ValueError('Il coefficiente deve essere un numero tra 0 e 1000.')
    direction = form.get('direction')
    if direction not in psm.DIRECTIONS:
        raise ValueError('Scegli una direzione valida.')
    blocking = form.get('is_hard_disqualifier') == 'on'
    trigger = form.get('hard_disqualifier_trigger_level')
    trigger = int(trigger) if trigger else None
    if blocking and trigger is None:
        raise ValueError('Indica il livello che attiva il requisito bloccante.')
    if trigger is not None:
        psm.validate_level(trigger)
    sources = form.getlist('evidence_sources_allowed')
    if not sources or any(s not in psm.EVIDENCE_SOURCES for s in sources):
        raise ValueError('Seleziona almeno una fonte di evidenza valida.')
    signal = form.get('auto_evaluation_signal_definition_id')
    signal = int(signal) if signal else None
    if signal:
        definition = db.get(m.SignalDefinition, signal)
        if definition is None or definition.restaurant_id != old_screening.restaurant_id(db):
            raise ValueError('Segnale non valido.')
    mapping = {}
    for status in sm.SIGNAL_STATUSES:
        value = form.get('auto_level_' + status, '')
        if value:
            psm.validate_level(int(value)); mapping[status] = int(value)
    answers = {}
    for answer, level in zip(form.getlist('answer_text'), form.getlist('answer_level')):
        if answer.strip():
            if not level:
                raise ValueError('Associa un livello a ciascuna risposta inserita.')
            psm.validate_level(int(level)); answers[answer.strip()] = int(level)
    result = {key: (form.get(key) or '').strip() or None for key in
        ('description', 'category', 'location_label', 'evaluation_guidance', 'evidence_positive',
         'evidence_contrary', 'evidence_insufficient', 'missing_evidence_question_text')}
    scope = form.get('criterion_group', criterion_context.ROLE_RESEARCH)
    if scope not in criterion_context.GROUPS:
        raise ValueError('Scegli Persona oppure Ruolo e ricerca.')
    result.update(criterion_group=scope, name=name, coefficient=coefficient, direction=direction,
        is_hard_disqualifier=blocking, hard_disqualifier_trigger_level=trigger,
        level_descriptions={str(n): form.get('level_description_' + str(n), '').strip() for n in range(5)},
        evidence_sources_allowed=sources, auto_evaluation_signal_definition_id=signal,
        auto_evaluation_level_map=mapping, required_for_phone_review=form.get('required_for_phone_review') == 'on',
        missing_evidence_answer_level_map=answers)
    if any(not text for text in result['level_descriptions'].values()):
        raise ValueError('Descrivi il significato di tutti i livelli da 0 a 4.')
    return result


def render(db, actor, position, *, default_role=None, draft=None, error=None, status=200):
    criteria = (criterion_copies.defaults(db, default_role.code, old_screening.restaurant_id(db))
                if default_role else old_screening.criteria(db, position) if position else [])
    definitions = list(db.scalars(select(m.SignalDefinition).where(
        m.SignalDefinition.restaurant_id == old_screening.restaurant_id(db)).order_by(m.SignalDefinition.name)))
    data = {str(c.id): {key: getattr(c, key) for key in
        ('criterion_group', 'id', 'version', 'name', 'description', 'category', 'target_role', 'location_label', 'coefficient',
         'direction', 'is_hard_disqualifier', 'hard_disqualifier_trigger_level', 'level_descriptions',
         'evidence_sources_allowed', 'evaluation_guidance', 'evidence_positive', 'evidence_contrary',
         'evidence_insufficient', 'auto_evaluation_signal_definition_id', 'auto_evaluation_level_map',
         'required_for_phone_review', 'missing_evidence_question_text', 'missing_evidence_answer_level_map')}
        for c in criteria}
    return render_template('workspace/selection_criteria.html', actor=actor, position=position,
        criteria=criteria, criteria_data=data, signal_definitions=definitions,
        criterion_groups=[('PERSON', 'Persona'), ('ROLE_RESEARCH', 'Ruolo e ricerca')],
        context_fields=screening_context.FIELDS,
        research_context=screening_context.values(position) if position else {},
        context_version=screening_context.version(position) if position else '',
        context_draft=draft if draft and draft.get('action') == ['save_context'] else None,
        default_role=default_role, default_mode=default_role is not None,
        can_manage_criteria=actor.is_owner if default_role else bool(position and actor.can_edit(position)),
        sources=[(s, SOURCES.get(s, s.replace('_', ' ').capitalize())) for s in psm.EVIDENCE_SOURCES],
        signal_statuses=[(s, SIGNAL_LABELS.get(s, s.replace('_', ' ').capitalize())) for s in sm.SIGNAL_STATUSES],
        draft=draft, error=error, section='configuration' if default_role else 'selection-criteria'), status


@bp.get('/criteri-selezione')
@access_required
def selection_criteria_current(db, actor):
    if not old_screening.enabled():
        abort(404)
    position = _current_job(db, actor)
    if position:
        return redirect(url_for('.selection_criteria', position_id=position.id))
    return render(db, actor, None)


@bp.route('/posizioni/<int:position_id>/criteri-selezione', methods=['GET', 'POST'])
@access_required
def selection_criteria(db, actor, position_id):
    if not old_screening.enabled():
        abort(404)
    position = _position(db, actor, position_id)
    if request.method == 'GET':
        return render(db, actor, position)
    if not actor.can_edit(position):
        abort(403)
    return save(db, actor, position)


@bp.route('/configurazioni/pdl/<role_code>/criteri', methods=['GET', 'POST'])
@access_required
def default_selection_criteria(db, actor, role_code):
    if not old_screening.enabled():
        abort(404)
    role = db.get(role_catalog.JobRole, role_code)
    if role is None:
        abort(404)
    if request.method == 'GET':
        return render(db, actor, None, default_role=role)
    if not actor.is_owner:
        abort(403)
    return save(db, actor, None, default_role=role)


def save(db, actor, position, *, default_role=None):
    draft = request.form.to_dict(flat=False)
    try:
        if request.form.get('action') == 'save_context':
            if default_role or not position:
                abort(400)
            position = db.scalar(select(ps.Position).where(ps.Position.id == position.id).with_for_update())
            db.refresh(position)
            screening_context.save(position, request.form)
            ps.log_event(db, position_id=position.id, kind='OLD_SCREENING_CONTEXT_SAVED',
                detail='Contesto del ruolo e della ricerca aggiornato.', actor_id=actor.id, actor_name=actor.name)
            db.commit()
            flash('Contesto salvato. Applica nuovamente i criteri per aggiornare le valutazioni.', 'success')
            return redirect(url_for('.selection_criteria', position_id=position.id, _anchor='research-context'))
        criterion_id = request.form.get('criterion_id', type=int)
        row = db.scalar(select(m.PrimaryScreeningCriterion).where(
            m.PrimaryScreeningCriterion.id == criterion_id).with_for_update()) if criterion_id else None
        allowed = (criterion_copies.defaults(db, default_role.code, old_screening.restaurant_id(db))
                   if default_role else old_screening.criteria(db, position))
        if criterion_id and (row is None or row.id not in {c.id for c in allowed}):
            abort(404)
        if row and row.version != request.form.get('version', type=int):
            raise ValueError('Il criterio è cambiato nel frattempo. Riapri la pagina prima di modificarlo.')
        if request.form.get('action') == 'toggle':
            if not row:
                abort(400)
            old_screening.screening.update_criterion(db, row.id, is_active=not row.is_active)
        else:
            values = fields(request.form, db)
            if row:
                old_screening.screening.update_criterion(db, row.id, **values)
            else:
                row = old_screening.screening.create_criterion(db,
                    restaurant_id=old_screening.restaurant_id(db),
                    target_role=default_role.code if default_role else position.role_code,
                    research_id=None if default_role else position.id, **values)
        if position:
            ps.log_event(db, position_id=position.id, kind='OLD_CRITERION_SAVED',
                detail=f'Criterio della ricerca aggiornato: {row.name}', actor_id=actor.id, actor_name=actor.name)
        db.commit()
        target = url_for('.default_selection_criteria', role_code=default_role.code, _anchor='criterion-' + str(row.id)) if default_role else url_for('.selection_criteria', position_id=position.id, _anchor='criterion-' + str(row.id))
        return redirect(target)
    except (ValueError, TypeError) as exc:
        db.rollback()
        return render(db, actor, position, default_role=default_role, draft=draft, error=str(exc), status=422)
