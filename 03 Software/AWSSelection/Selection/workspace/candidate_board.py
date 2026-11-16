"""PDL-rule-only candidate ordering and idempotent per-candidate actions."""
from local_i18n import ui
import hashlib
import json
from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select
from rfone_data_store import models as m
from rfone_data_store.selection import persistence, workspace_models as ps
from . import pdl_rule_application as rules, position_settings,automations, old_screening, conversational_rules as conversation
from .pdl_rule_store import PDLRule
from .routes import bp, access_required, _position, _pc, _cfg

# Existing decision actions; no email, invitation or external side effect.


def active_rules(db, position):
    return conversation.active(db,position.role_code)


def signature(active):
    return conversation.signature(active)


def locked_position(db, actor, position_id):
    position = db.scalar(select(ps.Position).where(ps.Position.id == position_id).with_for_update())
    if position is None:
        abort(404)
    if not actor.can_view(position):   # an existing Job outside the person's scope (fix A1)
        abort(403)
    if not actor.can_edit(position):
        abort(403)
    return position


def summary(result):
    if result is None:
        return "Criteri di selezione non ancora applicati a questo CV." if old_screening.enabled() else "Filtri e regole non ancora applicati a questo CV."
    if result.get('natural_language'):
        from .candidate_review import conclusions
        return conclusions(result)
    if result.get('old_engine'):
        return result['reason']
    if not result['active']:
        return "Nessuna regola attiva per questa PDL; ordine precedente mantenuto."
    details = result['details']
    matched = [d['title'] for d in details if d['outcome'] is True and
               d['section'] == ('requirements' if result['unfit'] else 'priorities')]
    if result['unfit']:
        return "UnFit: " + "; ".join(matched)
    if matched:
        return f"Priorità +{result['priority']}: " + "; ".join(matched)
    if result['unknown']:
        return "Priorità non incrementata; informazioni da chiarire nelle regole."
    return "Nessuna condizione UnFit verificata; nessuna preferenza di priorità corrispondente."


def board_rows(db, position):
    context = position_settings.context(position)
    saved = context.get('pdl_filter_run', {})
    valid = saved.get('role_code') == position.role_code and saved.get('mode')=='natural_language'
    results = saved.get('results', {}) if valid else {}
    stale = valid and saved.get('signature') != signature(active_rules(db, position))
    completed = context.get('candidate_actions', {})
    rows = []
    pcs = list(db.scalars(select(ps.PositionCandidate).where(ps.PositionCandidate.position_id == position.id)
                          .order_by(ps.PositionCandidate.added_at,ps.PositionCandidate.id)))
    from .cv_delete import blockers
    delete_blocked = blockers(db, pcs)   # Delete only for CVs not yet analyzed; the server checks again
    for pc in pcs:
        candidate = persistence.get_candidate(db, pc.candidate_id)
        result = results.get(str(pc.id))
        pending=valid and saved.get('state')=='RUNNING' and str(pc.id) not in results and str(pc.id) not in saved.get('errors',{})
        evaluation_error=saved.get('errors',{}).get(str(pc.id)) if valid else None
        from .incremental_rules import cv_input
        cv_changed=bool(result and saved.get('incremental_version')==1
            and saved.get('cv_hashes',{}).get(str(pc.id))!=cv_input(db,pc)[1])
        row_stale=stale or cv_changed
        from .candidate_review import effective
        result=effective(db,position,pc,result)
        runs=automations.reconcile(db,[pc.id])
        done={r.action_code:{'at':r.completed_at.isoformat() if r.completed_at else None} for r in runs if r.status=='SUCCEEDED'}
        states={r.action_code:{'status':ui(automations.STATUSES[r.status]),'code':r.status,'error':r.error} for r in runs}
        latest = db.scalar(select(ps.Decision).where(ps.Decision.position_candidate_id==pc.id).order_by(ps.Decision.id.desc()))
        selected=runs[-1].action_code if runs else ''
        if request.args.get('candidate')==str(pc.id):selected=request.args.get('action',selected)
        rows.append({'pc':pc,'name':(candidate.full_name if candidate else None) or pc.declared_name or 'Nome non estratto',
            'email':(candidate.email if candidate else None) or pc.declared_email,
            'phone':(candidate.phone if candidate else None) or pc.declared_phone,
            'result':result,'reason':evaluation_error or ('Lettura AI in corso…' if pending else 'CV o regole aggiornati: premi Applica Filtri e Regole.' if row_stale else summary(result)),'stale':row_stale,
            'unknown':[d['title'] for d in result['details'] if d['outcome'] is None] if result else [],
            'completed':done,'selected':selected,'action_states':states,
            'decision':ps.DECISION_LABELS.get(latest.decision) if latest else None,
            'deletable':not delete_blocked[pc.id]})
    return sorted(rows,key=lambda row:(bool(row['result'] and row['result']['unfit']),bool(row['result'] and row['result']['unknown']),
        -(row['result']['priority'] if row['result'] else 0)))


def render_board(db, actor, position):
    rows=board_rows(db,position)
    db.commit()
    return render_template('workspace/candidate_board.html',actor=actor,position=position,
        rows=rows,actions={a['code']:a['name'] for a in automations.items(db,'action',active=True)},can_edit=actor.can_edit(position),section='applications',
        applied=position_settings.context(position).get('pdl_filter_run'))


@bp.post('/posizioni/<int:position_id>/applica-regole-pdl')
@access_required
def apply_pdl_filters(db, actor, position_id):
    position = locked_position(db,actor,position_id)
    from . import incremental_rules
    run=incremental_rules.prepare(db,position,actor)
    db.commit()
    if run['state']=='RUNNING':
        conversation.dispatch(_cfg.SessionFactory,position.id,run['run_id'])
    return redirect(url_for('positions.position_detail',position_id=position.id,tab='candidature'))



@bp.post('/posizioni/<int:position_id>/candidati/<int:pc_id>/azione')
@access_required
def execute_candidate_action(db,actor,position_id,pc_id):
    position = locked_position(db,actor,position_id)
    pc = _pc(db,position,pc_id)
    selected_action=request.form.get('action','')
    try:
        automations.execute(db,pc,selected_action,actor)
        db.commit()
    except ValueError as exc:
        db.rollback();flash(str(exc))
    return redirect(url_for('positions.position_detail',position_id=position.id,tab='candidature',candidate=pc.id,action=selected_action,_anchor='candidate-'+str(pc.id)))


@bp.get('/posizioni/<int:position_id>/lettura-ai/stato')
@access_required
def ai_reading_status(db,actor,position_id):
    from flask import jsonify
    position=_position(db,actor,position_id);run=position_settings.context(position).get('pdl_filter_run',{})
    if run.get('mode')!='natural_language':return jsonify(state='NOT_STARTED',done=0,total=0,errors=0)
    if run['state']=='RUNNING':conversation.dispatch(_cfg.SessionFactory,position.id,run['run_id'])
    return jsonify(state=run['state'],done=len(run.get('completed_candidates',run['results']))+len(run['errors']),total=len(run['candidates']),errors=len(run['errors']))
