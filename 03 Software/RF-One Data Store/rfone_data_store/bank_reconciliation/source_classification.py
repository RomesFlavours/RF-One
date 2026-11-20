"""Explicit classification for an exact WHO + Source pair; no fallback to another Source."""

from datetime import date

from sqlalchemy import select

from .. import models as m

from . import card_configuration



def save(db, *, occurrence_id, payment_instrument_id, transaction_reason_id=None, account_id=None, classification_id=None):

    who = db.get(m.BankOccurrence, occurrence_id)

    instrument = db.get(m.PaymentInstrument, payment_instrument_id)

    reason = db.get(m.BankTransactionReason, transaction_reason_id) if transaction_reason_id else None

    if not who or who.status != "ACTIVE":

        raise ValueError("Choose an active WHO from the catalog.")

    if not instrument:

        raise ValueError("Choose an existing Source.")

    if transaction_reason_id and (not reason or reason.status != "ACTIVE"):

        raise ValueError("Choose an active WHY.")

    current = db.scalar(select(m.BankWhoSourceClassification).where(

        m.BankWhoSourceClassification.occurrence_id == occurrence_id,

        m.BankWhoSourceClassification.payment_instrument_id == payment_instrument_id))

    if classification_id:

        row = db.get(m.BankWhoSourceClassification, classification_id)

        if not row:

            raise ValueError("This classification no longer exists.")

        if current is not None and current.id != row.id:

            raise ValueError("This WHO + Source pair already exists. Edit that row instead.")

    else:

        if current is not None:

            raise ValueError("This WHO + Source pair already exists. Edit that row instead.")

        row = m.BankWhoSourceClassification(occurrence_id=occurrence_id, payment_instrument_id=payment_instrument_id)

        db.add(row)

    row.occurrence_id, row.payment_instrument_id = occurrence_id, payment_instrument_id

    row.transaction_reason_id, row.updated_by_account_id = transaction_reason_id, account_id

    db.flush()

    return row



def ensure_pairs(db, pairs):

    existing = set(db.execute(select(m.BankWhoSourceClassification.occurrence_id,

                                    m.BankWhoSourceClassification.payment_instrument_id)).all())

    active = set(db.scalars(select(m.BankOccurrence.id).where(m.BankOccurrence.status == "ACTIVE")))

    instruments = set(db.scalars(select(m.PaymentInstrument.id)))

    count = 0

    for who, source in sorted(set(pairs)):

        if (who, source) not in existing and who in active and source in instruments:

            db.add(m.BankWhoSourceClassification(occurrence_id=who, payment_instrument_id=source))

            existing.add((who, source)); count += 1

    db.flush()

    return count



def view(db):

    names = dict(db.execute(select(m.BankOccurrence.id, m.BankOccurrence.canonical_name)).all())

    sources = []

    for instrument in db.scalars(select(m.PaymentInstrument).order_by(m.PaymentInstrument.display_name)):

        owner = card_configuration.owner_entity_for(db, instrument=instrument, on_date=date.today())

        sources.append(dict(id=instrument.id, name=instrument.display_name, whom=owner.name if owner else None))

    rows = [dict(id=x.id, who_id=x.occurrence_id, source_id=x.payment_instrument_id,

                 why_id=x.transaction_reason_id, active=True)

            for x in db.scalars(select(m.BankWhoSourceClassification))]

    rows.sort(key=lambda x: (names.get(x['who_id'], ''), x['source_id']))

    return rows, sources





def merge_pairs(db, keep_id, absorb_id):

    kept = {x.payment_instrument_id: x for x in db.scalars(select(m.BankWhoSourceClassification).where(

        m.BankWhoSourceClassification.occurrence_id == keep_id))}

    absorbed = list(db.scalars(select(m.BankWhoSourceClassification).where(

        m.BankWhoSourceClassification.occurrence_id == absorb_id)))

    for row in absorbed:

        other = kept.get(row.payment_instrument_id)

        if other and other.transaction_reason_id and row.transaction_reason_id and other.transaction_reason_id != row.transaction_reason_id:

            raise ValueError("These WHO have different WHYs for the same Source. Resolve those classifications before merging.")

    for row in absorbed:

        other = kept.get(row.payment_instrument_id)

        if other:

            if not other.transaction_reason_id: other.transaction_reason_id = row.transaction_reason_id

            db.delete(row)

        else:

            row.occurrence_id = keep_id

    db.flush()





def movement_groups(db):

    """Read current human WHO first, otherwise latest completed engine proposal.



    Counts and detail share this definition; no recognition or writes occur here.

    """

    import json

    from sqlalchemy import func

    run_id = db.scalar(select(func.max(m.BankEngineRun.id)).where(m.BankEngineRun.summary_json.is_not(None)))

    proposals = {r.financial_transaction_id: json.loads(r.payload_json) for r in db.scalars(

        select(m.BankEngineResult).where(m.BankEngineResult.run_id == run_id))} if run_id else {}

    allocations = {}
    for allocation in db.scalars(select(m.BankTransactionAllocation)):
        allocations.setdefault(allocation.financial_transaction_id, []).append(allocation)
    groups = {}

    query = select(m.FinancialTransaction, m.BankTransactionExplanation).outerjoin(

        m.BankTransactionExplanation, m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id)

    for txn, explanation in db.execute(query):

        if txn.duplicate_status == 'CONFIRMED_DUPLICATE' or txn.accounting_status == 'DUPLICATE_SUPPRESSED':

            continue

        proposal = proposals.get(txn.id, {})

        human = explanation is not None and explanation.decision_source == 'HUMAN' and explanation.occurrence_id is not None

        who_id = explanation.occurrence_id if human else proposal.get('who_id')

        if who_id is None:

            continue

        key = (who_id, txn.payment_instrument_id)

        day = txn.posting_date or txn.transaction_date

        groups.setdefault(key, []).append(dict(id=txn.id, date=day.isoformat() if day else '',

            description=txn.description_original or txn.description_normalized or '',

            amount_minor=txn.amount_minor, method='HUMAN' if human else proposal.get('who_method', ''),

            why_id=explanation.transaction_reason_id if human and explanation.transaction_reason_id else proposal.get('why_id'),
            whom_id=(allocations[txn.id][0].reporting_entity_id if len(allocations.get(txn.id, [])) == 1 and allocations[txn.id][0].decision_source == 'HUMAN' else proposal.get('beneficiary_id')),
            whom_manual=bool(len(allocations.get(txn.id, [])) == 1 and allocations[txn.id][0].decision_source == 'HUMAN'),
            split=len(allocations.get(txn.id, [])) > 1,
            status=proposal.get('status', '')))

    for rows in groups.values():

        rows.sort(key=lambda r: (r['date'], r['id']), reverse=True)

    return groups



def delete_pair(db, classification_id):
    """Remove exactly one mapping; catalog identities and decisions are untouched."""
    row = db.get(m.BankWhoSourceClassification, classification_id)
    if row is None:
        raise ValueError("This WHO + Source classification no longer exists.")
    db.delete(row)
    db.flush()


def save_movement_override(db, *, classification_id, transaction_id, why_id, whom_id, account_id):
    """One movement only: no pair default, rule, alias or catalog change."""
    from . import recognition, row_reconciliation
    pair = db.get(m.BankWhoSourceClassification, classification_id)
    if pair is None:
        raise ValueError("This classification no longer exists.")
    rows = movement_groups(db).get((pair.occurrence_id, pair.payment_instrument_id), [])
    if transaction_id not in {r['id'] for r in rows}:
        raise ValueError("This movement no longer belongs to the selected WHO + Source. Reload the list.")
    if why_id is None and whom_id is None:
        raise ValueError("Choose WHY or WHOM.")
    if why_id is not None:
        recognition.record_human_decision(db, recognition.HumanDecisionRequest(
            transaction_id=transaction_id, occurrence_id=pair.occurrence_id,
            confirmed_by_account_id=account_id, transaction_reason_id=why_id,
            record_association=False, notes="WHY chosen for this movement only in Classification."))
    if whom_id is not None:
        row_reconciliation.set_for_whom(db, transaction_id=transaction_id,
            reporting_entity_id=whom_id, account_id=account_id)
    db.flush()


def set_pair_whys(db, *, classification_ids, why_id, account_id=None):
    """One atomic WHY change on exactly the selected pairs, with all identities preserved."""
    ids = set(classification_ids)
    if not ids or len(ids) > 5000:
        raise ValueError("Select at least one classification (maximum 5000).")
    rows = list(db.scalars(select(m.BankWhoSourceClassification).where(m.BankWhoSourceClassification.id.in_(ids))))
    if {row.id for row in rows} != ids:
        raise ValueError("One or more selected classifications no longer exist. Reload the page.")
    if why_id is not None:
        why = db.get(m.BankTransactionReason, why_id)
        if why is None or why.status != "ACTIVE":
            raise ValueError("Choose an active WHY.")
    # Validate the whole selection before touching any row.
    for row in rows:
        row.transaction_reason_id = why_id
        row.updated_by_account_id = account_id
    db.flush()
    return len(rows)
