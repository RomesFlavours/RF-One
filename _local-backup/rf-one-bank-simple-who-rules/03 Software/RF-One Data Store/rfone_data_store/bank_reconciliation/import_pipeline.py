"""Per-new-movement extraction -> recognition photos -> durable research job.

No provider call or background work is made until the import commits.
"""
import json
from sqlalchemy import select
from .. import models as m
from . import ai_rules, ai_rule_operations as ops, rule_organization as org, rule_application_safety as safety

PROVISIONAL = ('ONLINE_PURCHASE_UNIDENTIFIED','MIXED_PURCHASES_PENDING_ITEM_DETAILS')

def facts(session, txn):
    row=ai_rules.row_for(session,txn.id)
    return dict(who=row.current_who, why=row.current_why, source_id=txn.payment_instrument_id,
        source=row.source_label, source_type=row.source_type, owner=row.owner_name,
        source_class=row.source_class, source_class_basis=row.source_class_basis,
        description=ai_rules.mask_description(txn.description_original) if hasattr(ai_rules,'mask_description') else txn.description_original,
        memo=txn.source_memo, direction='money out' if txn.amount_minor < 0 else 'money in')

def photo_matches(context, txn):
    row=context.builder.row(txn, ops.recognition.get_current_explanation(context.session,financial_transaction_id=txn.id))
    matches=[(r,v,s) for r,v,s in context.entries if org.kind(r,v)=='RECOGNITION' and ai_rules.execute(s,row).outcome=='MATCH']
    def implies(narrow,broad):
        if narrow['field']!=broad['field']:return False
        a=' '.join(str(narrow.get('value','')).casefold().split());b=' '.join(str(broad.get('value','')).casefold().split())
        if narrow['op']==broad['op'] and a==b:return True
        return broad['op']=='contains' and narrow['op'] in ('is','contains') and b in a
    def narrower(a,b):
        if a.get('branches') or b.get('branches'):return False
        ac=a.get('conditions',[]);bc=b.get('conditions',[])
        return bool(ac and bc and all(any(implies(x,y) for x in ac) for y in bc) and not all(any(implies(y,x) for y in bc) for x in ac))
    return [(r,v,s) for r,v,s in matches if not any(narrower(other,s) for _r,_v,other in matches if _r.id!=r.id)]

def _stage(session,txn,context,entries,photo=False):
    saved=context.entries;context.entries=entries;context.photo_stage=photo
    try:return ops._apply_import_matches(session,txn,context)
    finally:context.entries=saved;context.photo_stage=False

def _complete(session,txn):
    e=session.get(m.BankTransactionExplanation,txn.explanation_id) if txn.explanation_id else None
    reason=session.get(m.BankTransactionReason,e.transaction_reason_id) if e and e.transaction_reason_id else None
    return bool(e and e.occurrence_id and reason and reason.code not in PROVISIONAL)

def reconcile_new(session,txn,context=None):
    """The validated extraction/photo flow is the single import entry point."""
    from . import flow
    return flow.import_new(session,txn)


def apply_photos(session,txn,eligible_versions=None):
    if eligible_versions is None:
        context=ops.import_context(session) or ops.ImportContext(session,[])
    else:
        entries=[]
        for rule_id,version_id in eligible_versions:
            r=session.get(m.BankAiRule,rule_id);v=session.get(m.BankAiRuleVersion,version_id)
            if r and v and v.rule_id==r.id and not r.deleted_at and r.status=='ACTIVE' and r.apply_future and v.spec:
                spec=json.loads(v.spec)
                if ai_rules.spec_usable(spec):entries.append((r,v,spec))
        context=ops.ImportContext(session,entries)
    matches=photo_matches(context,txn)
    if not matches:return False,False
    _stage(session,txn,context,matches,photo=True);ops.finish_import(context)
    errors=any(a.conflicts or a.errors or a.unresolved or a.protected for a in context.applications.values())
    return True,errors


def seal_batch(session,batch_id):
    """Finish input guards after import-only duplicate/matching annotations."""
    session.flush()
    jobs=session.scalars(select(m.BankImportReconciliation).join(m.FinancialTransaction,
        m.FinancialTransaction.id==m.BankImportReconciliation.financial_transaction_id).where(
        m.FinancialTransaction.import_batch_id==batch_id,m.BankImportReconciliation.attempts==0))
    own=ai_rules.own_account_ids(session)
    for job in jobs:
        txn=session.get(m.FinancialTransaction,job.financial_transaction_id)
        if txn.accounting_status!='CANONICAL' or txn.duplicate_status=='CONFIRMED_DUPLICATE' or txn.id in own:
            job.status='SKIPPED';job.stage='COMPLETE'
        context=json.loads(job.context_json or "{}")
        context.update(facts(session,txn))
        job.context_json=json.dumps(context,ensure_ascii=False)
        job.input_state=safety.snapshot(session,txn)
