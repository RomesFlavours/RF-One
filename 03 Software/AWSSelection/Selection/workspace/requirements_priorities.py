"""Chat-first general rules and explicit PDL-only replacements."""
from local_i18n import ui
import hashlib,json
from types import SimpleNamespace
from uuid import uuid4
from flask import abort,current_app,jsonify,redirect,render_template,request,url_for
from itsdangerous import URLSafeTimedSerializer,BadData
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from . import pdl_rule_engine as engine,pdl_rule_store as store,role_catalog,conversational_rules as conversation
from .routes import bp,access_required

ALL='__all__'

def signer():return URLSafeTimedSerializer(current_app.secret_key,salt='selection-pdl-rules-v2')

def role_for(db,code):
    if code in (None,'',ALL):return SimpleNamespace(code=None,name='Tutte le PDL')
    role=db.get(role_catalog.JobRole,code)
    if role is None or not role.active:abort(400)
    return role

def payload():
    if request.content_length and request.content_length>180000:abort(413)
    value=json.loads(request.form.get('payload','{}'))
    if not isinstance(value,dict):raise ValueError('Richiesta non valida.')
    return value

def fingerprint(rule):
    if rule is None:return None
    return hashlib.sha256(json.dumps({'id':rule.id,'title':rule.title,'section':rule.section,'condition':rule.condition,'active':rule.is_active},sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def current_override(db,code,target_id):
    if target_id is None:return None
    return db.scalar(select(store.PDLRule).where(store.PDLRule.role_code==code,store.PDLRule.overrides_rule_id==target_id,store.PDLRule.is_active.is_(True)))

def editable(db,code,rule_id,lock=False):
    if rule_id is None:return None
    if type(rule_id) is not int:raise ValueError('Regola da modificare non valida.')
    query=select(store.PDLRule).where(store.PDLRule.id==rule_id,store.PDLRule.role_code==code)
    row=db.scalar(query.with_for_update() if lock else query)
    if row is None or not conversation.natural(row):abort(404)
    return row

@bp.get('/requisiti-priorita')
@access_required
def requirements_priorities(db,actor):
    role=role_for(db,request.args.get('pdl',ALL));local=store.list_rules(db,role.code)
    entries=store.entries(db,role.code)
    displayed={e['rule'].id for e in entries}
    archived=[r for r in local if conversation.natural(r) and r.id not in displayed]
    return render_template('workspace/requirements_priorities.html',actor=actor,roles=role_catalog.choices(db),
        selected_role=role.code or ALL,selected_role_name=(ui(role.name) if role.code is None else role.name),is_general=role.code is None,
        rule_entries=entries,archived_rules=archived,saved_rules=local,natural=conversation.natural,
        section='requirements-priorities')

@bp.post('/requisiti-priorita/proposta')
@access_required
def pdl_rules_propose(db,actor):
    if not actor.is_owner:abort(403)
    try:
        data=payload();role=role_for(db,data.get('pdl',ALL))
        edit=editable(db,role.code,data.get('edit_id'))
        chosen=data.get('replacement_id');store.validate_target(db,role.code,chosen)
        if edit and chosen is not None:raise ValueError('Scegli modifica oppure sostituzione per la PDL.')
        rows=store.list_rules(db,None)+(store.list_rules(db,role.code) if role.code is not None else [])
        existing=[{'id':r.id,'title':r.title,'need':r.condition['need'],'instruction':r.condition['instruction'],
            'scope':'general' if r.role_code is None else 'specific','replaces_rule_id':r.overrides_rule_id} for r in rows if conversation.natural(r) and r.is_active]
        edit_data={'id':edit.id,'title':edit.title,'need':edit.condition['need'],'instruction':edit.condition['instruction'],'section':edit.section,'replaces_rule_id':edit.overrides_rule_id} if edit else None
        result=conversation.propose(role.name,data.get('messages'),existing,scope='general' if role.code is None else 'specific',replacement_id=chosen,edit_rule=edit_data)
        if result['rule']:
            rule=result['rule'];target=store.validate_target(db,role.code,rule.get('replaces_rule_id'))
            if edit and rule.get('replaces_rule_id')!=edit.overrides_rule_id:raise ValueError('La modifica deve mantenere l’ambito e la regola generale eventualmente sostituita.')
            if chosen is not None and rule.get('replaces_rule_id')!=chosen:raise ValueError('La proposta deve sostituire la regola generale scelta, non un’altra.')
            previous=current_override(db,role.code,rule.get('replaces_rule_id'))
            result['replacement_title']=target.title if target else None
            result['previous_override_title']=previous.title if previous else None
            result['token']=signer().dumps({'actor':actor.id,'pdl':role.code,'rule':rule,'target_hash':fingerprint(target),
                'edit_id':edit.id if edit else None,'edit_hash':fingerprint(edit),
                'override_hash':fingerprint(previous),'messages':data['messages']+[{'role':'assistant','content':result['reply']}],'key':str(uuid4())})
        return jsonify(result)
    except (ValueError,TypeError) as exc:return jsonify(error=str(exc)),422
    except (RuntimeError,TimeoutError):return jsonify(error='ChatGPT non ha completato la proposta. Il testo è conservato; riprova.'),503

@bp.post('/requisiti-priorita/salva')
@access_required
def pdl_rules_save(db,actor):
    if not actor.is_owner:abort(403)
    try:
        data=signer().loads(payload().get('token',''),max_age=3600)
        if data['actor']!=actor.id:abort(403)
        role=role_for(db,data['pdl']);rule=conversation.validate(data['rule'])
        existing=db.scalar(select(store.PDLRule).where(store.PDLRule.proposal_key==data['key']))
        if existing:return jsonify(ok=True,id=existing.id,pdl=existing.role_code,section=existing.section)
        edit=editable(db,role.code,data.get('edit_id'),lock=True)
        if edit:
            if fingerprint(edit)!=data.get('edit_hash'):
                return jsonify(error='La regola è cambiata. Riapri Modifica e chiedi una proposta aggiornata.'),409
            if rule['replaces_rule_id']!=edit.overrides_rule_id:raise ValueError('Ambito della modifica non valido.')
            target=store.validate_target(db,role.code,edit.overrides_rule_id,lock=True)
            if fingerprint(target)!=data['target_hash']:return jsonify(error='La regola generale è cambiata. Aggiorna la proposta.'),409
            edit.title=rule['title'];edit.section=rule['section']
            edit.condition={'op':'natural_language','need':rule['need'],'instruction':rule['instruction']}
            edit.conversation=data['messages'];edit.proposal_key=data['key']
            db.commit()
            return jsonify(ok=True,id=edit.id,pdl=edit.role_code,section=edit.section)
        target=store.validate_target(db,role.code,rule['replaces_rule_id'],lock=True)
        previous=current_override(db,role.code,rule['replaces_rule_id'])
        existing=db.scalar(select(store.PDLRule).where(store.PDLRule.proposal_key==data['key']))
        if existing:return jsonify(ok=True,id=existing.id,pdl=existing.role_code,section=existing.section)
        if fingerprint(target)!=data['target_hash'] or fingerprint(previous)!=data['override_hash']:
            return jsonify(error='La regola generale o la modifica locale sono cambiate. Chiedi una proposta aggiornata prima di salvare.'),409
        if previous:previous.is_active=False;db.flush()
        row=store.PDLRule(role_code=role.code,overrides_rule_id=rule['replaces_rule_id'],section=rule['section'],
            title=rule['title'],weight=1,condition={'op':'natural_language','need':rule['need'],'instruction':rule['instruction']},
            conversation=data['messages'],proposal_key=data['key'],created_by=actor.id)
        db.add(row);db.commit()
        return jsonify(ok=True,id=row.id,pdl=row.role_code,section=row.section)
    except (BadData,KeyError,ValueError,TypeError) as exc:
        db.rollback();return jsonify(error=str(exc) if isinstance(exc,ValueError) else 'Proposta scaduta o non valida. Rigenerala.'),400
    except IntegrityError:
        db.rollback();return jsonify(error='Esiste già una modifica attiva per questa regola e PDL. Riapri la pagina.'),409

@bp.post('/requisiti-priorita/<int:rule_id>/attivazione')
@access_required
def pdl_rule_toggle(db,actor,rule_id):
    if not actor.is_owner:abort(403)
    row=db.get(store.PDLRule,rule_id)
    if row is None:abort(404)
    role=role_for(db,row.role_code)
    try:
        if not row.is_active:store.validate_target(db,role.code,row.overrides_rule_id,lock=True)
        row.is_active=not row.is_active;db.commit()
    except (ValueError,IntegrityError):
        db.rollback()
        from flask import flash
        flash('Non è possibile riattivare: esiste un’altra sostituzione attiva oppure la regola generale è disattivata.')
    return redirect(url_for('.requirements_priorities',pdl=role.code or ALL,_anchor='rule-'+str(row.id)))
