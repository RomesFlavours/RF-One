"""Sequential, previewed automatic pass followed by a stoppable guided pass."""
import json
from datetime import datetime, timezone
from flask import request, jsonify
from sqlalchemy import select
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import flow, reconciliation_runner as runner, rule_application_safety as safety


def load(db, run_id, account_id):
    rec=db.get(m.BankFlowArtifact,run_id)
    if not rec or rec.kind!='RUN' or rec.account_id!=account_id:raise ValueError('Reconciliation run unavailable.')
    return rec,json.loads(rec.payload)


def guard(db, data, account_id, *, allow_resolved=False):
    if not data.get('run_id'):return None,None
    rec,run=load(db,data['run_id'],account_id)
    if run['phase']!='GUIDED' or run.get('current_id')!=data.get('transaction_id'):
        raise ValueError('This reconciliation run was stopped or moved to another transaction.')
    txn=db.get(m.FinancialTransaction,data['transaction_id'])
    if not txn or not allow_resolved and runner.resolved(db,txn):raise ValueError('This transaction is already reconciled. Continue with the next pending transaction.')
    return rec,run


def store(rec,run):rec.payload=json.dumps(run,ensure_ascii=False)


def advance(db,rec,run,txn_id,item=None):
    if item:run['items'].append(item);run['updated']+=1
    run['remaining']=[x for x in run['remaining'] if x!=txn_id]
    run['current_id']=None
    if not run['remaining']:run['phase']='COMPLETE'
    store(rec,run)


def register(app,*,gate,SessionFactory,require_csrf,owner,endpoint):
    @app.route('/bank/flow/runs',methods=['GET','POST'])
    @gate
    @endpoint
    def bank_reconcile_runs():
        if request.method=='POST':require_csrf()
        with SessionFactory() as db:
            if request.method=='GET':
                rows=db.scalars(select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind=='RUN').order_by(m.BankFlowArtifact.id.desc()).limit(100))
                return jsonify(ok=True,runs=[dict(id=r.id,**public(json.loads(r.payload))) for r in rows if r.account_id==owner(db) or r.account_id is None and json.loads(r.payload).get('scope')=='IMPORT'])
            safety.lock_writes(db)
            for r in db.scalars(select(m.BankFlowArtifact).where(m.BankFlowArtifact.kind=='RUN',m.BankFlowArtifact.account_id==owner(db))):
                if json.loads(r.payload).get('phase') in ('AUTO','PREVIEW','GUIDED'):raise ValueError('Continue or stop the current run first.')
            tid=request.form.get('transaction_id',type=int)
            rows=runner.pending(db)
            if tid:
                rows=[t for t in rows if t.id==tid]
                if not rows:raise ValueError('This transaction is already reconciled or excluded from the pending queue.')
            run=dict(scope='SINGLE' if tid else 'ALL',phase='AUTO',ids=[t.id for t in rows],
                cursor=0,plans=[],remaining=[],items=[],updated=0,current_id=None,
                signature=flow.signature(db),created_at=datetime.now(timezone.utc).isoformat())
            rec=m.BankFlowArtifact(kind='RUN',payload=json.dumps(run),account_id=owner(db));db.add(rec);db.flush();rid=rec.id;db.commit()
            return jsonify(ok=True,id=rid,**run)

    @app.route('/bank/flow/runs/<int:id>/<action>',methods=['POST'])
    @gate
    @endpoint
    def bank_reconcile_run_action(id,action):
        require_csrf()
        with SessionFactory() as db:
            safety.lock_writes(db)
            rec=db.get(m.BankFlowArtifact,id)
            if rec and rec.kind=='RUN' and rec.account_id is None and json.loads(rec.payload).get('scope')=='IMPORT' and action=='rollback':run=json.loads(rec.payload)
            else:rec,run=load(db,id,owner(db))
            if action=='stop':
                if run['phase'] in ('AUTO','PREVIEW','GUIDED'):run['phase']='STOPPED'
            elif action=='auto':
                if run['phase']!='AUTO':raise ValueError('Automatic pass is not active.')
                if flow.signature(db)!=run['signature']:raise ValueError('Rules or Configuration changed. Stop and restart this run.')
                eligible={t.id:t for t in runner.pending(db)};configured=flow.entries(db,future=True)
                for tid in run['ids'][run['cursor']:run['cursor']+25]:
                    txn=eligible.get(tid)
                    if not txn:raise ValueError('Transaction eligibility changed. Stop and restart.')
                    plan=runner.plan(db,txn,configured);run['plans'].append(plan)
                    if plan.get('choice'):
                        c=plan['choice'];why=db.get(m.BankTransactionReason,c['why_id']);what=db.get(m.BankAccountingClassification,c['destination_id']);whom=db.get(m.ReportingEntity,c['whom_id'])
                        plan['after']=f'WHY: {why.name}\nWHAT: {what.name if what.is_what else "No P&L WHAT; "+what.name}\nWHOM: {whom.name}'
                    if not plan.get('choice'):run['remaining'].append(tid)
                    run['cursor']+=1
                if run['cursor']==len(run['ids']):
                    if any(p.get('choice') for p in run['plans']):run['phase']='PREVIEW'
                    else:run['phase']='GUIDED' if run['remaining'] else 'COMPLETE'
            elif action=='apply':
                if run['phase']!='PREVIEW':raise ValueError('Preview this automatic pass first.')
                if flow.signature(db)!=run['signature']:raise ValueError('Rules or Configuration changed. Stop and restart this run.')
                eligible={t.id:t for t in runner.pending(db)}
                for p in run['plans']:
                    txn=eligible.get(p['transaction_id'])
                    if not txn or safety.snapshot(db,txn)!=p['state']:raise ValueError('A transaction changed. Stop and restart the preview.')
                applications={}
                for p in run['plans']:
                    txn=eligible[p['transaction_id']]
                    if p.get('choice'):
                        item=runner.apply(db,txn,p['choice'],id,account_id=owner(db),applications=applications)
                        if item:run['items'].append(item);run['updated']+=1
                    runner.queue(db,txn,p)
                run['phase']='GUIDED' if run['remaining'] else 'COMPLETE'
                # Snapshot payloads stay server-side for rollback; do not expose them in the UI.
            elif action=='next':
                if run['phase']=='COMPLETE':return jsonify(ok=True,id=id,**public(run))
                if run['phase']!='GUIDED':raise ValueError('Guided pass is not active.')
                pending={t.id for t in runner.pending(db)}
                run['remaining']=[x for x in run['remaining'] if x in pending]
                run['current_id']=run['remaining'][0] if run['remaining'] else None
                if not run['current_id']:run['phase']='COMPLETE'
            elif action=='skip':
                if run['phase']!='GUIDED' or not run.get('current_id'):raise ValueError('No guided transaction is active.')
                run.setdefault('skipped',[]).append(run['current_id']);advance(db,rec,run,run['current_id'])
            elif action=='rollback':
                if run['phase'] in ('AUTO','PREVIEW','GUIDED'):raise ValueError('Stop this run before rollback.')
                if run.get('rolled_back'):return jsonify(ok=True,id=id,restored=0,skipped=[],already_rolled_back=True)
                restored=0;skipped=[];seen=set()
                for item in reversed(run['items']):
                    if item.get('application_id'):
                        aid=item['application_id']
                        if aid in seen:continue
                        seen.add(aid);result=safety.rollback_application(db,aid,account_id=owner(db))
                        restored+=result['restored'];skipped+=result['skipped']
                    else:
                        txn=db.get(m.FinancialTransaction,item['transaction_id'])
                        if txn and safety.restore_snapshot(db,txn,item['before'],item['after'],f'Rollback reconciliation run #{id}.'):restored+=1
                        else:skipped.append(dict(id=item['transaction_id'],reason='Changed after reconciliation.'))
                run['rolled_back']=True;run['rollback']=dict(restored=restored,skipped=skipped);store(rec,run);db.commit()
                return jsonify(ok=True,id=id,restored=restored,skipped=skipped)
            else:raise ValueError('Unknown reconciliation action.')
            store(rec,run);db.commit()
            return jsonify(ok=True,id=id,**public(run))


def public(run):
    data={k:v for k,v in run.items() if k not in ('signature','items','plans')}
    data['plans']=[{k:v for k,v in p.items() if k!='state'} for p in run.get('plans',[])]
    return data
