"""Owner-only current configuration and AI proposals."""
from local_i18n import ui
import json
from flask import abort,jsonify,request
from sqlalchemy import select
from .routes import bp,access_required,_position,_pc
from . import automations as service
from .action_models import ActionRun
from .mail_delivery import EmailOutbox


def data():
    if request.content_length and request.content_length>180000:abort(413)
    value=json.loads(request.form.get('payload','{}'))
    if not isinstance(value,dict):raise ValueError('Richiesta non valida.')
    return value


@bp.post('/configurazioni/automazioni/salva')
@access_required
def automation_save(db,actor):
    if not actor.is_owner:abort(403)
    try:
        d=data()
        code=service.save(db,kind=d.get('kind'),code=d.get('code') or None,name=d.get('name'),description=d.get('description'),active=d.get('active') is True,expected=d.get('version'),steps=d.get('steps'),procedure_code=d.get('procedure_code'),actor=actor)
        db.commit();return jsonify(ok=True,code=code)
    except ValueError as exc:
        db.rollback();return jsonify(error=str(exc)),422


@bp.post('/configurazioni/automazioni/proposta')
@access_required
def automation_propose(db,actor):
    if not actor.is_owner:abort(403)
    try:
        d=data();result=service.propose(d.get('messages'),d.get('existing'))
        if result['steps']:result['description']=service.describe(result['steps'])
        return jsonify(result)
    except ValueError as exc:return jsonify(error=str(exc)),422
    except Exception:return jsonify(error='ChatGPT non ha completato la proposta. La conversazione è conservata; riprova.'),503


@bp.get('/posizioni/<int:position_id>/candidati/<int:pc_id>/azioni/storico')
@access_required
def candidate_action_history(db,actor,position_id,pc_id):
    position=_position(db,actor,position_id);pc=_pc(db,position,pc_id)
    service.reconcile(db,[pc.id]);db.commit()
    runs=list(db.scalars(select(ActionRun).where(ActionRun.position_candidate_id==pc.id).order_by(ActionRun.id.desc())))
    if request.args.get('status_only')=='1':
        return jsonify(runs=[{'action_code':r.action_code,'code':r.status,'status':ui(service.STATUSES[r.status]),'error':r.error} for r in runs])
    return jsonify(runs=[{'id':r.id,'action':r.action_snapshot,'procedure':r.procedure_snapshot,'status':ui(service.STATUSES[r.status]),
        'attempts':r.attempts,'steps':r.steps,'error':r.error,
        'emails':[{'subject':mail.subject,'body':mail.body,'recipient':mail.recipient,'status':mail.status} for step in r.steps if step.get('outbox_id') for mail in [db.get(EmailOutbox,step['outbox_id'])] if mail],
        'completed_at':r.completed_at.isoformat() if r.completed_at else None} for r in runs])
