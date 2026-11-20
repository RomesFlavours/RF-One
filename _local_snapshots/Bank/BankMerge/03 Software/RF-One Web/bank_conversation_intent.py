"""Bridge conversational intent to a WHO rule and explicitly reviewed WHO + Source pairs.

Conversation and preview are read-only for operational knowledge. Only the existing
preview-confirmed Save calls apply(), in the same transaction as the WHO rule.
"""
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import card_configuration, source_classification, who_rules

KEY = 'classification_plan'
INSTRUCTIONS = '''
Understand intent before terminology. People may write informally, make typos, or call
WHY "WHO" (or confuse WHAT/WHOM). Correct the term briefly and continue with the clear
intent; never reject an understood request because it belongs to another editor.
WHO identifies the merchant; WHY is payment purpose; WHAT derives from WHY; the Source
owner remains the accounting subject (Decision 86). Do not change that owner or WHOM.
When an extraction conversation also defines purpose, return BOTH the extraction spec
and classification_plan (a sibling of spec):
{who:merchant name,cases:[{source_class:"PERSONAL_CARD"|"PERSONAL"|"NOT_PERSONAL"|"OTHER"|"ANY",why_id:existing catalog ID or why_name:human's purpose name}]}.
PERSONAL_CARD means a CREDIT_CARD whose configured settlement-account owner is a person;
PERSONAL and NOT_PERSONAL refer to configured Source ownership; OTHER is the explicit
"in all other cases" fallback, ANY means explicitly always. Preserve all conditions.
Unknown ownership must stay undecided, never assumed corporate. Use only existing catalog
WHYs by operational meaning; if none fits, preserve the name and propose its creation,
do not fabricate IDs or substitute an unrelated purpose. Ask only genuinely unresolved
questions. A clear WHO/WHY terminology mistake is not an unresolved question.
If the person names a merchant example followed by a store number (e.g. SHOP #123)
and describes personal-card versus other payment purposes, prepare WHO extraction
without that store number and the corresponding WHY cases. If the named merchant can occur anywhere in the description, use fixed_who with its literal name and a required identifying text; never extract from the description beginning up to the first #, because a card reference may precede the merchant. When a purpose is called
WHO, explain the corrected term and continue; do not ask them to change editors.
Keep the rule itself concise: merchant extraction and WHY conditions, then WHAT from WHY and default WHOM from Source. Do not mix implementation details, configuration review steps or new-Source limitations into the rule text; the preview presents those separately.
Return ready=true when both requested parts are clear and executable. Restate the whole
policy in the user's language. Never say it is saved/applied before confirmation.
When revising a rule, preserve its classification_plan unless the person explicitly
changes or removes it; to remove it return drop_classification_plan:true.
The preview expands the plan into exact WHO + Source pairs for currently configured
Sources. It does not install a global default, change Recognition Profiles or classify
new Sources automatically. Save requires review of those pairs. Extraction itself
continues to assign WHO only; classification_plan is a separate configuration proposal.
'''


def _key(value):
    return re.sub(r'[^\w]+', ' ', unicodedata.normalize('NFKC', str(value or '')).casefold()).strip()


def normalize(db, plan):
    if not isinstance(plan, dict) or set(plan)-{'who','cases'} or not isinstance(plan.get('who'), str):
        raise ValueError('Name the merchant for the WHO and WHY proposal.')
    name = ' '.join(plan['who'].split()).upper()
    who_rules.check_new_who(db, name)
    cases = plan.get('cases')
    if not isinstance(cases, list) or not cases or len(cases) > 10:
        raise ValueError('Explain when each WHY applies.')
    reasons = list(db.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.status == 'ACTIVE')))
    by_id = {r.id: r for r in reasons}
    normalized = []
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or set(case)-{'source_class','why_id','why_name'}:
            raise ValueError('Explain when each WHY applies.')
        condition = case.get('source_class')
        if condition not in ('PERSONAL_CARD', 'PERSONAL', 'NOT_PERSONAL', 'OTHER', 'ANY') or condition in seen:
            raise ValueError('Use distinct, supported Source conditions for each WHY.')
        seen.add(condition)
        rid = case.get('why_id')
        reason = by_id.get(rid) if type(rid) is int else None
        supplied = case.get('why_name')
        if rid is not None and reason is None:
            raise ValueError('Choose an active WHY from Configuration.')
        if supplied:
            matches = [r for r in reasons if _key(r.name) == _key(supplied)]
            if len(matches) != 1 or reason and matches[0].id != reason.id:
                raise ValueError(f'Choose or create the exact WHY “{supplied}”; no unrelated WHY was substituted.')
            reason = matches[0]
        if not reason:
            raise ValueError('Name the WHY to use in each case.')
        if not reason.accounting_classification_id:
            raise ValueError(f'Complete WHAT for WHY “{reason.name}” in Configuration first.')
        normalized.append(dict(source_class=condition, why_id=reason.id, why_name=reason.name))
    if 'ANY' in seen and len(seen) > 1 or {'PERSONAL', 'PERSONAL_CARD'} <= seen:
        raise ValueError('These Source conditions overlap. Explain which one takes precedence.')
    return dict(who=name, cases=normalized)


def incorporate(db, answer, old_spec):
    """Keep purpose outside extraction execution, but version/draft it with the rule."""
    spec = answer.get('spec')
    if not isinstance(spec, dict) or spec.get('kind') != 'EXTRACTOR':
        return spec
    spec = dict(spec)
    plan = answer.get(KEY, spec.get(KEY, (old_spec or {}).get(KEY)))
    if answer.get('drop_classification_plan') is True:
        spec.pop(KEY, None)
    elif plan is not None:
        spec[KEY] = normalize(db, plan)
    return compile_spec(db,spec)


def compile_spec(db,spec):
    if not isinstance(spec,dict) or not spec.get(KEY):return spec
    spec=dict(spec);plan=normalize(db,spec[KEY]);spec[KEY]=plan
    if spec.get('from_beginning') and any(plan['who'].casefold() in text.casefold() for text in spec.get('require',[])):
        spec['fixed_who']=plan['who']
    return spec


def preview(db, spec):
    if not isinstance(spec, dict) or not spec.get(KEY):
        return None
    plan = normalize(db, spec[KEY])
    known, _ = who_rules.check_new_who(db, plan['who'])
    existing = {r.payment_instrument_id: r for r in db.scalars(select(m.BankWhoSourceClassification).where(
        m.BankWhoSourceClassification.occurrence_id == known.id))} if known else {}
    reasons = {r.id: r.name for r in db.scalars(select(m.BankTransactionReason))}
    rows, skipped = [], []
    for source in db.scalars(select(m.PaymentInstrument).where(m.PaymentInstrument.status == 'ACTIVE').order_by(m.PaymentInstrument.id)):
        owner = card_configuration.owner_entity_for(db, instrument=source, on_date=datetime.now(ZoneInfo('America/New_York')).date())
        if not owner or owner.status != 'ACTIVE':
            skipped.append(dict(source_id=source.id, source=source.display_name, reason='Source owner is not configured.'))
            continue
        personal = owner.entity_type == m.REPORTING_ENTITY_PERSONAL
        matches = [c for c in plan['cases'] if c['source_class'] == 'ANY'
            or c['source_class'] == 'PERSONAL_CARD' and personal and source.instrument_type == 'CREDIT_CARD'
            or c['source_class'] == 'PERSONAL' and personal
            or c['source_class'] == 'NOT_PERSONAL' and not personal]
        matches = matches or [c for c in plan['cases'] if c['source_class'] == 'OTHER']
        if len(matches) > 1:
            raise ValueError('More than one WHY matches a Source. Clarify the conditions.')
        if not matches:
            skipped.append(dict(source_id=source.id, source=source.display_name, reason='No requested case covers this Source.'))
            continue
        row = existing.get(source.id)
        case = matches[0]
        rows.append(dict(source_id=source.id, source=source.display_name, owner=owner.name,
            source_class=case['source_class'], why_id=case['why_id'], why=case['why_name'],
            before_why_id=row.transaction_reason_id if row else None,
            before_why=reasons.get(row.transaction_reason_id) if row else None))
    return dict(who=plan['who'], who_id=known.id if known else None, cases=plan['cases'], rows=rows, skipped=skipped,
        scope='Exact WHO + Source pairs for the Sources listed here. New Sources require their own classification.')


def apply(db, spec, reviewed, *, account_id):
    current = preview(db, spec)
    if current != reviewed:
        raise ValueError('The WHO + Source classifications changed. Preview again before saving.')
    if not current:
        return 0
    if not current['rows']:
        raise ValueError('No configured Source can receive this classification. Complete Source ownership first.')
    from rfone_data_store.bank_reconciliation import manual_reconciliation
    who = manual_reconciliation.create_who(db, name=current['who']).occurrence
    for row in current['rows']:
        existing = db.scalar(select(m.BankWhoSourceClassification).where(
            m.BankWhoSourceClassification.occurrence_id == who.id,
            m.BankWhoSourceClassification.payment_instrument_id == row['source_id']))
        source_classification.save(db, occurrence_id=who.id, payment_instrument_id=row['source_id'],
            transaction_reason_id=row['why_id'], classification_id=existing.id if existing else None, account_id=account_id)
    return len(current['rows'])


def summary(spec):
    plan = spec.get(KEY) if isinstance(spec, dict) else None
    if not plan:
        return None
    labels = {'PERSONAL_CARD': 'per carte personali', 'PERSONAL': 'per Source personali',
              'NOT_PERSONAL': 'per Source aziendali', 'OTHER': 'negli altri casi', 'ANY': 'sempre'}
    cases = '; '.join(f"{case['why_name']} {labels[case['source_class']]}" for case in plan['cases'])
    condition = "Per «" + ", ".join(spec.get("require") or []) + "»: " if spec.get("require") else ""
    return f"{condition}WHO: {plan['who']}. WHY: {cases}. WHAT dal WHY; WHOM predefinito dalla Source."


def movement_choice(db, txn, proposed, who):
    """Prepare the exact reviewed Source assignment; never overwrite human decisions."""
    from rfone_data_store.bank_reconciliation import flow
    explanation = db.get(m.BankTransactionExplanation, txn.explanation_id) if txn.explanation_id else None
    allocations = list(db.scalars(select(m.BankTransactionAllocation).where(
        m.BankTransactionAllocation.financial_transaction_id == txn.id)))
    if explanation and explanation.decision_source == 'HUMAN':
        return None, 'Human decision protected.'
    if txn.duplicate_status == 'CANDIDATE_DUPLICATE':
        return None, 'Possible duplicate requires review.'
    if len(allocations) > 1:
        return None, 'Split allocations require review.'
    reason = db.get(m.BankTransactionReason, proposed['why_id'])
    destination = db.get(m.BankAccountingClassification, reason.accounting_classification_id)
    whom = flow.source_whom(db, txn)
    if not whom:
        return None, 'Choose WHOM: Source ownership is missing for this transaction.'
    if not destination or not destination.active or not destination.is_posting_account:
        return None, 'Choose an active accounting destination first.'
    return dict(who=who, why_id=reason.id, whom_id=whom,
        destination_id=destination.id, rule_id=-1, version_id=-1,
        review_before_confirm=False), 'Ready to apply the reviewed WHO and WHY.'
