"""Row photo capture and visible automatic reconciliation outcomes."""
import json
from flask import jsonify,request
from sqlalchemy import select
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import rule_application_safety as safety
import bank_photo_capture as capture


def register(app,*,gate,SessionFactory,load_current_account,require_csrf):
    @app.route('/bank/ai-rules/capture/<int:transaction_id>',methods=['GET','POST'])
    @gate
    def bank_photo_capture(transaction_id):
        if request.method=='POST':require_csrf()
        with SessionFactory() as db:
            try:
                account=load_current_account(db)
                if request.method=='GET':return jsonify(capture.as_dict(capture.current(db,transaction_id)))
                result=capture.prepare(db,transaction_id,account.id if account else None,request.form.get('pattern'),request.form.get('match_op'),request.form.get('memo_pattern'))
                return jsonify(result)
            except (ValueError,TypeError) as exc:
                db.rollback();return jsonify(ok=False,error=str(exc)),409

    @app.route('/bank/import-reconciliation/status')
    @gate
    def bank_import_reconciliation_status():
        try:ids=[int(x) for x in request.args.get('ids','').split(',') if x][:500]
        except ValueError:return jsonify(ok=False,error='Invalid identifiers.'),400
        with SessionFactory() as db:
            items=[]
            for job in db.scalars(select(m.BankImportReconciliation).where(m.BankImportReconciliation.financial_transaction_id.in_(ids))):
                proposal=json.loads(job.proposal_json) if job.proposal_json else None
                reason=db.get(m.BankTransactionReason,proposal.get('suggested_reason_id')) if proposal and proposal.get('suggested_reason_id') else None
                if proposal:proposal['suggested_why']=reason.name if reason else None
                items.append(dict(id=job.financial_transaction_id,status=job.status,stage=job.stage,proposal=proposal,error=job.last_error))
            return jsonify(ok=True,items=items)

    @app.route('/bank/import-reconciliation/<int:transaction_id>/retry',methods=['POST'])
    @gate
    def bank_import_reconciliation_retry(transaction_id):
        require_csrf()
        with SessionFactory() as db:
            safety.lock_writes(db)
            job=db.scalar(select(m.BankImportReconciliation).where(m.BankImportReconciliation.financial_transaction_id==transaction_id))
            txn=db.get(m.FinancialTransaction,transaction_id)
            if not job or job.status!='ERROR':return jsonify(ok=False,error='Only failed processing can be retried.'),409
            if not txn or safety.snapshot(db,txn)!=job.input_state:
                job.status='STALE';job.last_error='Transaction modificato: completa la verifica manuale.';db.commit()
                return jsonify(ok=False,error=job.last_error),409
            job.status='QUEUED';job.last_error=None;db.commit()
        worker=app.extensions.get('bank_import_worker')
        if worker:worker.wake()
        return jsonify(ok=True)
