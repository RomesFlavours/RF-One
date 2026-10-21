"""Capture the current human-reviewed classification as a signed reusable photo."""
import json
from sqlalchemy import select
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import ai_rules,ai_rule_operations as ops,rule_application_safety as safety,rule_organization as org
import bank_rule_workflow as workflow


def current(db,transaction_id):
    txn=db.get(m.FinancialTransaction,transaction_id)
    if not txn or txn.accounting_status!='CANONICAL' or txn.duplicate_status=='CONFIRMED_DUPLICATE':raise ValueError('Transaction unavailable for a recognition profile.')
    if txn.id in ai_rules.own_account_ids(db):raise ValueError('Transfer between own accounts: no external WHO applies.')
    decision=db.get(m.BankTransactionExplanation,txn.explanation_id) if txn.explanation_id else None
    who=db.get(m.BankOccurrence,decision.occurrence_id) if decision and decision.occurrence_id else None
    why=db.get(m.BankTransactionReason,decision.transaction_reason_id) if decision and decision.transaction_reason_id else None
    allocations=list(db.scalars(select(m.BankTransactionAllocation).where(m.BankTransactionAllocation.financial_transaction_id==txn.id)))
    if not who or not why:raise ValueError('Complete WHO and WHY before saving this transaction as a recognition profile.')
    if len(allocations)!=1 or not allocations[0].reporting_entity_id or allocations[0].amount_minor!=txn.amount_minor:
        raise ValueError('Choose one WHOM for the whole transaction. Split allocations require a separate profile for each case.')
    allocation=allocations[0];entity=db.get(m.ReportingEntity,allocation.reporting_entity_id)
    if who.status!='ACTIVE' or why.status!='ACTIVE' or not entity or entity.status!='ACTIVE':raise ValueError('WHO, WHY and WHOM must be active.')
    destination=db.get(m.BankAccountingClassification,decision.accounting_classification_id) if decision.accounting_classification_id else None
    if destination and (not destination.is_complete or destination.node_type=='GROUP'):raise ValueError('The accounting destination is inactive.')
    source=db.get(m.PaymentInstrument,txn.payment_instrument_id)
    contains=' '.join(who.canonical_name.casefold().split()) in ' '.join((txn.description_original or '').casefold().split())
    return dict(txn=txn,who=who,why=why,entity=entity,destination=destination,source=source,
        pattern=who.canonical_name,match_op='who')


def as_dict(values):
    return dict(ok=True,transaction_id=values['txn'].id,description=values['txn'].description_original,
        who=values['who'].canonical_name,why=values['why'].name,whom=values['entity'].name,
        destination=(values['destination'].code+' — '+values['destination'].name) if values['destination'] else None,
        source=values['source'].display_name,direction='money out' if values['txn'].amount_minor<0 else 'money in',
        pattern=values['pattern'],match_op=values['match_op'],memo=values['txn'].source_memo or '')


def prepare(db,transaction_id,account_id,pattern,match_op,memo_pattern=None):
    v=current(db,transaction_id);txn=v['txn'];pattern=(pattern or '').strip()
    if match_op not in ('contains','is','who') or not pattern or len(pattern)>2000:raise ValueError('Enter the text to match and choose contains or exact match.')
    normalized=lambda x:' '.join((x or '').casefold().split())
    if (normalized(pattern)!=normalized(v['who'].canonical_name) if match_op=='who' else (normalized(pattern) not in normalized(txn.description_original) if match_op=='contains' else normalized(pattern)!=normalized(txn.description_original))):
        raise ValueError('The criteria must also match the example transaction.')
    field="who_name" if match_op=="who" else "description"
    op="is" if match_op=="who" else match_op
    direction='money out' if txn.amount_minor<0 else 'money in'
    text=f'Recognition profile: {"recognized WHO is" if match_op=="who" else ("description contains" if match_op=="contains" else "description exactly matches")} "{pattern}"; Source ID "{txn.payment_instrument_id}" ({v["source"].display_name}); direction "{direction}". WHO "{v["who"].canonical_name}"; WHY "{v["why"].name}"; WHOM "{v["entity"].name}". Awaiting confirmation.'
    raw=dict(kind='STRUCTURED',conditions=[dict(field=field,op=op,value=pattern),
        dict(field='source_id',op='is',value=str(txn.payment_instrument_id)),dict(field='direction',op='is',value=direction)],
        who=dict(mode='fixed',name=v['who'].canonical_name),why=dict(mode='fixed',name=v['why'].name),
        for_whom=dict(mode='fixed',entity=v['entity'].name),status=dict(mode='to_confirm'),
        coverage=[dict(instruction='Recognition and classification approved by the user',represented_by='description, Source, direction, WHO, WHY, WHOM, status')])
    memo_pattern=(memo_pattern or '').strip()
    if memo_pattern:
        if len(memo_pattern)>2000 or normalized(memo_pattern) not in normalized(txn.source_memo):
            raise ValueError('The memo text must appear in the original bank memo.')
        text+=f' Memo contains "{memo_pattern}".'
        raw['conditions'].append(dict(field='memo',op='contains',value=memo_pattern))
    if v['destination']:
        d=v['destination'];text+=f' Accounting destination "{d.code}" "{d.name}".'
        raw['captured_destination']=dict(id=d.id,code=d.code,name=d.name)
    spec,error=ai_rules.validate_interpretation(raw,text,entities=ai_rules.EntityCatalog(db))
    if error:raise ValueError(error)
    existing=[]
    for r in ops.rules(db):
        version=ops.current_version(r)
        if org.kind(r,version)=='RECOGNITION' and version and version.spec:
            old=json.loads(version.spec)
            if old.get('conditions')==spec['conditions'] and not old.get('branches'):existing.append((r,version))
    if len(existing)>1:raise ValueError('Several profiles match these conditions. Open Rules and choose which one to update.')
    rule,version=existing[0] if existing else (None,None)
    instructions=workflow._instructions(db)
    payload=dict(rule_text=text,origin_id=txn.id,raw=raw,spec=spec,instructions=instructions,
        provider='HUMAN_CAPTURE',model='Validated transaction photo',engine_version=ai_rules.INTERPRETATION_VERSION,
        account_id=account_id,who_id=v['who'].id,rule_id=rule.id if rule else None,
        previous_version=version.version_no if version else None,previous_future=rule.apply_future if rule else None,
        previous_organization_kind=rule.organization_kind if rule else None,organization_kind='RECOGNITION',
        capture_state=safety.snapshot(db,txn))
    return dict(ok=True,rule_text=text,confirmation_token=workflow.signer().dumps(payload),rule_id=payload['rule_id'])
