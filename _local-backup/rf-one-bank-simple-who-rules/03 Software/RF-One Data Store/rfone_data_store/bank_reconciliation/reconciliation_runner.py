"""One deterministic planner for interactive reconciliation and imports.

Planning never calls an AI provider or writes financial records. Configuration
fallback uses an explicit default, never an observed WHO/WHY association.
"""
import json,re
from sqlalchemy import select, or_
from .. import models as m
from . import flow, rule_application_safety as safety, reconciliation_status as status
from . import who_rules, recognition, economic_allocation as allocation


def pending(db):
    # The Review queue is the authority for reconciliation, not accounting
    # completeness. Never reopen a resolved WHO because WHY/WHAT is incomplete.
    from . import review_queues
    eligible={t.id for t in flow.eligible(db) if t.duplicate_status!='CANDIDATE_DUPLICATE'}
    return [t for t in db.scalars(review_queues._queue_query(
        review_queues.TO_RECONCILE,review_queues.ReviewFilters())) if t.id in eligible]


def resolved(db,txn):
    explanation=db.get(m.BankTransactionExplanation,txn.explanation_id) if txn.explanation_id else None
    return bool(explanation and explanation.occurrence_id) or txn.id in flow.ai_rules.own_account_ids(db)


def plan(db, txn, configured=None):
    configured = flow.entries(db, future=True) if configured is None else configured
    who, ids, conflict = flow.identity(db, txn, configured)
    result = dict(transaction_id=txn.id, description=txn.description_original,
                  date=str(txn.posting_date), state=safety.snapshot(db, txn),
                  extracted_who=who, choice=None, note='No rule extracts WHO.')
    if resolved(db,txn):
        result['note']='Already reconciled. No changes allowed.'
        return result
    if conflict:
        result['note'] = 'Extraction rules disagree on WHO.'
        return result
    if not who:
        return result
    photos=[e for e in flow.photo_candidates(db,configured,who) if flow.photo_who(db,e)]
    if photos:
        result = flow.plan(db, txn, [e for e in configured if flow.kind(e)=='EXTRACTOR']+photos, extracted=who)
        choice = result.get('choice')
        if choice:
            reason = db.get(m.BankTransactionReason, choice['why_id'])
            destination = db.get(m.BankAccountingClassification, choice.get('destination_id') or reason.accounting_classification_id)
            if not destination or not destination.active or not destination.is_posting_account:
                result.update(choice=None, note='Profile needs an accounting destination.')
            else:
                choice.update(destination_id=destination.id, review_before_confirm=False)
                result['note'] = 'Recognition profile.'
        return result
    try:
        known, _ = who_rules.check_new_who(db, who)
    except ValueError as exc:
        result['note']=str(exc)
        return result
    reason = db.get(m.BankTransactionReason, known.default_transaction_reason_id) if known and known.default_transaction_reason_id else None
    destination = db.get(m.BankAccountingClassification, reason.accounting_classification_id) if reason and reason.accounting_classification_id else None
    whom = flow.source_whom(db, txn)
    if not reason or reason.status != 'ACTIVE':
        result['note'] = 'No profile or explicit default WHY in Configuration.'
    elif not destination or not destination.active or not destination.is_posting_account:
        result['note'] = 'Configuration WHY needs an accounting destination.'
    elif not whom:
        result['note'] = 'Source owner or a single manual WHOM is required.'
    else:
        result.update(note='Configuration default.', choice=dict(origin='CONFIGURATION',
            who=known.canonical_name, why_id=reason.id, whom_id=whom,
            destination_id=destination.id, review_before_confirm=False))
    return result


def apply(db, txn, choice, run_id, *, account_id=None, applications=None):
    if resolved(db,txn):raise ValueError('This transaction is already reconciled. No changes were applied.')
    if choice.get('origin') != 'CONFIGURATION':
        aid = flow.write(db, txn, {**choice, 'review_before_confirm':False},
                         mode='RECONCILIATION', account_id=account_id, applications=applications)
        return dict(application_id=aid) if aid else None
    before = safety.snapshot(db, txn)
    who, _ = who_rules.check_new_who(db, choice['who'])
    note = f'Reconciliation run #{run_id}; Configuration default.'
    old = list(db.scalars(select(m.BankTransactionAllocation).where(m.BankTransactionAllocation.financial_transaction_id==txn.id)))
    if not who or len(old)>1: raise ValueError('The transaction needs manual review.')
    recognition._create_decision_row(db, txn, occurrence_id=who.id,
        transaction_reason_id=choice['why_id'], accounting_classification_id=choice['destination_id'],
        decision_source='RULE', decision_status='AUTO_APPLIED', confidence='HIGH', explanation_notes=note)
    allocation.set_allocations(db, financial_transaction_id=txn.id, specs=[allocation.AllocationSpec(
        amount_minor=txn.amount_minor, reporting_entity_id=choice['whom_id'],
        transaction_reason_id=choice['why_id'], accounting_classification_id=choice['destination_id'],
        status=m.ALLOCATION_COMPLETE, decision_source='HUMAN' if old and old[0].decision_source=='HUMAN' else 'RULE', notes=note)])
    txn.review_status='ACCEPTED'; db.flush()
    return dict(transaction_id=txn.id, before=before, after=safety.snapshot(db, txn))


def history_key(description):
    """Retrieve precedents despite bank reference changes; never extract WHO.

    Results are human-reviewed evidence, not an executable extraction rule.
    ACH entry purpose stays in the key so deposits and charges are not merged.
    """
    text=' '.join((description or '').upper().split())
    if text.startswith('ZELLE PAYMENT TO '):
        return re.sub(r'\s+(?:JPM[A-Z0-9]+|(?=[A-Z0-9]*\d)[A-Z0-9]+)$','',text)
    if text.startswith('ORIG CO NAME:') and 'ORIG ID:' in text:
        company=text.split('ORIG ID:',1)[0].strip()
        purpose=re.search(r'CO ENTRY DESCR:(.*?)(?:SEC:|TRACE#:|$)',text)
        return company+' | '+(purpose.group(1).strip() if purpose else '')
    return text


def history(db, txn):
    rows=list(db.scalars(select(m.FinancialTransaction).where(
        m.FinancialTransaction.id!=txn.id,
        m.FinancialTransaction.accounting_status=='CANONICAL',
        or_(m.FinancialTransaction.duplicate_status.is_(None),m.FinancialTransaction.duplicate_status.notin_(['CONFIRMED_DUPLICATE','CANDIDATE_DUPLICATE'])))
        .order_by(m.FinancialTransaction.id.desc())))
    key=history_key(txn.description_original);result=[]
    for row in rows:
        if history_key(row.description_original)!=key:continue
        e=db.get(m.BankTransactionExplanation,row.explanation_id) if row.explanation_id else None
        if not e or not e.occurrence_id:continue
        reason=db.get(m.BankTransactionReason,e.transaction_reason_id) if e.transaction_reason_id else None
        a=db.scalar(select(m.BankTransactionAllocation).where(m.BankTransactionAllocation.financial_transaction_id==row.id))
        destination=e.accounting_classification_id or (reason.accounting_classification_id if reason else None)
        result.append(dict(transaction_id=row.id,date=str(row.posting_date),
            who=db.get(m.BankOccurrence,e.occurrence_id).canonical_name,
            description=row.description_original,
            why_id=e.transaction_reason_id,destination_id=destination,
            whom_id=a.reporting_entity_id if a else None))
    return result[:30]


def queue(db,txn,result):
    job=db.scalar(select(m.BankImportReconciliation).where(m.BankImportReconciliation.financial_transaction_id==txn.id))
    if not job:
        job=m.BankImportReconciliation(financial_transaction_id=txn.id,input_state=safety.snapshot(db,txn),eligible_versions_json='[]');db.add(job)
    job.status='MATCHED' if result.get('choice') else 'AMBIGUOUS'
    job.stage='COMPLETE' if result.get('choice') else 'GUIDED'
    job.context_json=json.dumps(dict(engine=flow.ENGINE,extracted_who=result.get('extracted_who')))
    job.input_state=safety.snapshot(db,txn);job.lease_until=None;job.last_error=None
    return job


def imported(db,txn,configured):
    if resolved(db,txn):
        job=queue(db,txn,{});job.status='SKIPPED';job.stage='COMPLETE'
        return False
    result=plan(db,txn,configured)
    changed=False
    if result.get('choice'):
        run=m.BankFlowArtifact(kind='RUN',payload='{}',account_id=None);db.add(run);db.flush()
        item=apply(db,txn,result['choice'],run.id)
        run.payload=json.dumps(dict(scope='IMPORT',phase='COMPLETE',ids=[txn.id],items=[item] if item else [],remaining=[],updated=int(bool(item))))
        changed=bool(item)
    queue(db,txn,result)
    return changed
