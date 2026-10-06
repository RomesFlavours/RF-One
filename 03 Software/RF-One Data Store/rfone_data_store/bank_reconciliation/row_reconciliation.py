"""Bank Reconciliation, one transaction row at a time (BANK_RECONCILIATION_001,
BANK_RECONCILIATION_STANDARDS_001).

Per bank transaction the page shows Account / Card, Date, Description,
Amount, WHO (WHY underneath), For Whom and one of exactly three statuses —
NEEDS REVIEW, AUTOMATIC, CONFIRMED — defined once in
`reconciliation_status`. Every row expands inline into an editor for WHO,
WHY, WHAT and For Whom. Nothing here is a new model:

=============  ==========================================================
Row fact       Authoritative storage / service
=============  ==========================================================
Transaction    `FinancialTransaction`, month scope = `export.in_scope_
               transactions`
WHO, WHY,      the CURRENT `BankTransactionExplanation`, written by
destination    `recognition.record_human_decision` (human) or by a
               Standard (`reconciliation_standards.apply_to_transaction`);
               `accounting_destination_source` says WHY / TRANSACTION /
               STANDARD
For Whom,      `BankTransactionAllocation`, written by
row status     `economic_allocation.set_allocations`
Standard       `BankReconciliationStandard` (`reconciliation_standards`)
New WHO        `configuration.save_who`, the Bank Configuration service
=============  ==========================================================

Confirm, Set as Standard and the editor's two Save actions all end the same
way: a HUMAN decision (WHO, WHY, destination) and a HUMAN, COMPLETE
allocation (For Whom) — CONFIRMED. Set as Standard / Save as New Standard
additionally create or reuse a Standard, which completes FUTURE matching
imports (AUTOMATIC). A Standard is never modified by editing a transaction.
The WHAT is never shown on the compact row.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models as m
from . import card_configuration
from . import economic_allocation
from . import export as export_service
from . import recognition
from . import reconciliation_standards as standards_service
from . import reconciliation_status
from . import reporting_entity as reporting_entity_service
from . import who_recognition

NEEDS_REVIEW = reconciliation_status.NEEDS_REVIEW
AUTOMATIC = reconciliation_status.AUTOMATIC
CONFIRMED = reconciliation_status.CONFIRMED


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def account_label(instrument: "m.PaymentInstrument | None") -> str:
    if instrument is None:
        return "—"
    return instrument.display_name + (f" ··{instrument.last_four}" if instrument.last_four else "")


def default_for_whom(
    session: Session, instrument: "m.PaymentInstrument | None", on_date: date | None,
) -> "m.ReportingEntity | None":
    """The proposed For Whom of an undecided transaction — only a default.

    Bank Account: the ReportingEntity of its own LegalEntity. Credit Card:
    the ReportingEntity of the LegalEntity its settlement account belongs to
    on that date, never the card's own value (Configuration decision D3)."""
    if instrument is None:
        return None
    if instrument.instrument_type == card_configuration.CREDIT_CARD:
        legal = card_configuration.legal_entity_for(session, instrument=instrument, on_date=on_date)
        legal_entity_id = legal.id if legal is not None else None
    else:
        legal_entity_id = instrument.legal_entity_id
    if legal_entity_id is None:
        return None
    return reporting_entity_service.reporting_entity_for_legal_entity(
        session, legal_entity_id=legal_entity_id,
    )


def _destination_label(destination: "m.BankAccountingClassification | None") -> str:
    if destination is None:
        return ""
    if destination.statement_type == "BALANCE_SHEET":
        return f"Balance Sheet destination — {destination.name}"
    return f"{destination.code} — {destination.name}"


_OWN_ACCOUNT_FAMILY_LABELS = {
    who_recognition.F_OWN_LEGAL_ENTITY: "Own legal entity",
    who_recognition.F_CARD_SETTLEMENT: "Card payment from own funds",
}


def _own_account_labels(session: Session, ids: list[int],
                        instruments: dict[int, "m.PaymentInstrument"]) -> dict[int, str]:
    """{transaction id: label} for the own-account movements among `ids` —
    the ones the model resolves WITHOUT a WHO (`review_queues.
    own_account_movement`): a confirmed INTERNAL_TRANSFER match, or a
    STRUCTURAL current recognition. Shown in place of "No WHO yet"; never a
    WHO. Two queries, whatever the number of rows."""
    if not ids:
        return {}
    labels: dict[int, str] = {}
    for a_id, b_id in session.execute(
        select(m.FinancialTransactionMatch.transaction_a_id, m.FinancialTransactionMatch.transaction_b_id)
        .where(m.FinancialTransactionMatch.match_type == "INTERNAL_TRANSFER",
               or_(m.FinancialTransactionMatch.transaction_a_id.in_(ids),
                   m.FinancialTransactionMatch.transaction_b_id.in_(ids)))
    ):
        labels[a_id] = labels[b_id] = "Internal transfer (matched)"
    for recognized in session.scalars(
        select(m.BankWhoRecognition).where(
            m.BankWhoRecognition.recognizer_version == who_recognition.RECOGNIZER_VERSION,
            m.BankWhoRecognition.tier == m.WHO_TIER_STRUCTURAL,
            m.BankWhoRecognition.financial_transaction_id.in_(ids))
    ):
        if recognized.financial_transaction_id in labels:
            continue
        other = instruments.get(recognized.internal_payment_instrument_id)
        labels[recognized.financial_transaction_id] = (
            f"Internal transfer · {other.display_name}" if other is not None
            else _OWN_ACCOUNT_FAMILY_LABELS.get(recognized.family, "Own account")
        )
    return labels


def month_view(session: Session, *, year: int, month: int) -> dict:
    """Everything the page renders for one month, as plain values. A fixed
    number of queries plus one settlement lookup per (card, date) pair; the
    WHO / WHY / WHAT / entity catalogs are sent ONCE for the page's single
    modal and single inline editor."""
    return rows_view(session, export_service.in_scope_transactions(session, year, month))


def rows_view(session: Session, transactions: list["m.FinancialTransaction"]) -> dict:
    """`month_view` for any list of transactions — the Reconciliation page's
    month, or the Review's Reconciled queue (BANK_TWO_STAGE_REVIEW_001), so
    both render the SAME rows, statuses and editor from one definition."""
    ids = [t.id for t in transactions]
    explanation_ids = [t.explanation_id for t in transactions if t.explanation_id is not None]
    explanations = {
        e.id: e for e in session.scalars(
            select(m.BankTransactionExplanation).where(m.BankTransactionExplanation.id.in_(explanation_ids))
        )
    } if explanation_ids else {}
    allocations: dict[int, list] = {}
    if ids:
        for a in session.scalars(
            select(m.BankTransactionAllocation)
            .where(m.BankTransactionAllocation.financial_transaction_id.in_(ids))
            .order_by(m.BankTransactionAllocation.allocation_index)
        ):
            allocations.setdefault(a.financial_transaction_id, []).append(a)
    instruments = {i.id: i for i in session.scalars(select(m.PaymentInstrument))}
    own_account = _own_account_labels(session, ids, instruments)
    whos = {o.id: o for o in session.scalars(select(m.BankOccurrence))}
    whys = {r.id: r for r in session.scalars(select(m.BankTransactionReason))}
    classifications = {c.id: c for c in session.scalars(select(m.BankAccountingClassification))}
    entities = list(session.scalars(select(m.ReportingEntity).order_by(m.ReportingEntity.name)))
    entity_names = {e.id: e.name for e in entities}

    default_cache: dict[tuple, int | None] = {}
    used_standard_ids: set[int] = set()
    rows = []
    for t in transactions:
        instrument = instruments.get(t.payment_instrument_id)
        on_date = t.posting_date or t.transaction_date
        key = (t.payment_instrument_id,
               on_date if instrument is not None and instrument.instrument_type == card_configuration.CREDIT_CARD else None)
        if key not in default_cache:
            entity = default_for_whom(session, instrument, on_date)
            default_cache[key] = entity.id if entity is not None else None
        default_id = default_cache[key]

        explanation = explanations.get(t.explanation_id)
        row_allocations = allocations.get(t.id, [])
        status = reconciliation_status.status_of(t, explanation, row_allocations)
        stored_for_whom = row_allocations[0].reporting_entity_id if len(row_allocations) == 1 else None
        for_whom = stored_for_whom if stored_for_whom is not None else default_id
        who = whos.get(explanation.occurrence_id) if explanation and explanation.occurrence_id else None
        why = whys.get(explanation.transaction_reason_id) if explanation and explanation.transaction_reason_id else None
        destination = (classifications.get(explanation.accounting_classification_id)
                       if explanation and explanation.accounting_classification_id else None)
        standard_id = row_allocations[0].reconciliation_standard_id if status == AUTOMATIC else None
        if standard_id is not None:
            used_standard_ids.add(standard_id)
        if who is None:
            who_source = None
        elif status == AUTOMATIC:
            who_source = "standard"
        else:
            who_source = "person" if explanation.decision_source == "HUMAN" else "auto"
        rows.append({
            "id": t.id,
            "account": account_label(instrument),
            "date": on_date.isoformat() if on_date else "",
            "date_label": on_date.strftime("%b %d").replace(" 0", " ") if on_date else "",
            "description": t.description_original or "",
            "amount_minor": t.amount_minor,
            "who_id": who.id if who else None,
            "who": who.canonical_name if who else None,
            "who_source": who_source,
            "own_account": own_account.get(t.id) if who is None else None,
            "why_id": why.id if why else None,
            "why": why.name if why else None,
            "what_id": destination.id if destination else None,
            "what": _destination_label(destination),
            "destination_source": explanation.accounting_destination_source if explanation else None,
            "for_whom": for_whom,
            "default_for_whom": default_id,
            "split": len(row_allocations) > 1,
            "status": status,
            "standard_id": standard_id,
            "memo": t.source_memo or "",
        })

    # The ONE catalog for the page's single modal and single editor.
    possible: dict[int, list[int]] = {}
    for occurrence_id, reason_id in session.execute(
        select(m.BankOccurrenceReasonAssociation.occurrence_id,
               m.BankOccurrenceReasonAssociation.transaction_reason_id)
        .where(m.BankOccurrenceReasonAssociation.active.is_(True))
    ):
        reason = whys.get(reason_id)
        if reason is not None and reason.status == "ACTIVE":
            possible.setdefault(occurrence_id, []).append(reason_id)
    served: dict[int, list[int]] = {}
    for occurrence_id, entity_id in session.execute(
        select(m.BankOccurrenceReportingEntity.occurrence_id,
               m.BankOccurrenceReportingEntity.reporting_entity_id)
        .where(m.BankOccurrenceReportingEntity.active.is_(True))
    ):
        served.setdefault(occurrence_id, []).append(entity_id)
    assigned = {r["who_id"] for r in rows if r["who_id"] is not None}
    # Compact on purpose (1,229 WHO today): empty facts are omitted and the
    # page reads a missing key as "none".
    who_catalog = []
    for o in sorted(whos.values(), key=lambda o: o.canonical_name.lower()):
        if o.status != "ACTIVE" and o.id not in assigned:
            continue
        entry = {"id": o.id, "name": o.canonical_name}
        if possible.get(o.id):
            entry["whys"] = possible[o.id]
            if o.default_transaction_reason_id in possible[o.id]:
                entry["default_why"] = o.default_transaction_reason_id
        if served.get(o.id):
            entry["entities"] = served[o.id]
        if o.status != "ACTIVE":
            entry["inactive"] = True
        who_catalog.append(entry)

    standards = {}
    if used_standard_ids:
        accounts = {a.id: a.display_name for a in session.scalars(
            select(m.RFOneAccount).where(m.RFOneAccount.id.in_(
                select(m.BankReconciliationStandard.approved_by_account_id)
                .where(m.BankReconciliationStandard.id.in_(used_standard_ids)))))}
        for s in session.scalars(select(m.BankReconciliationStandard)
                                 .where(m.BankReconciliationStandard.id.in_(used_standard_ids))):
            standards[s.id] = {
                "pattern": s.normalized_pattern,
                "match": {"EXACT_NORMALIZED_DESCRIPTION": "Exact", "CONTAINS_TEXT": "Contains",
                          "PREFIX": "Prefix"}.get(s.match_type, s.match_type),
                "scope": account_label(instruments.get(s.payment_instrument_id))
                if s.payment_instrument_id else "Any account or card",
                "direction": {"DEBIT": "Money out", "CREDIT": "Money in"}.get(s.direction, "Either direction"),
                "who": whos[s.occurrence_id].canonical_name if s.occurrence_id in whos else "",
                "why": whys[s.transaction_reason_id].name if s.transaction_reason_id in whys else "",
                "what": _destination_label(classifications.get(s.accounting_classification_id)),
                "for_whom": entity_names.get(s.reporting_entity_id, ""),
                "approved_by": accounts.get(s.approved_by_account_id, ""),
                "approved_at": s.approved_at.date().isoformat() if s.approved_at else "",
            }

    return {
        "rows": rows,
        "entities": [{"id": e.id, "name": e.name, "active": e.status == "ACTIVE"} for e in entities],
        "whos": who_catalog,
        "whys": [{"id": r.id, "name": r.name, "what": r.accounting_classification_id}
                 for r in sorted(whys.values(), key=lambda r: r.name) if r.status == "ACTIVE"],
        "whats": [{"id": c.id, "label": _destination_label(c)}
                  for c in sorted(classifications.values(), key=lambda c: c.code) if c.is_what],
        # Labels of every destination the editor may need to show truthfully:
        # the rows' current ones and each active WHY's own (which may be a
        # Balance Sheet destination, never offered as a WHAT choice).
        "destinations": {
            **{str(r.accounting_classification_id): _destination_label(classifications.get(r.accounting_classification_id))
               for r in whys.values() if r.status == "ACTIVE" and r.accounting_classification_id in classifications},
            **{str(r["what_id"]): r["what"] for r in rows if r["what_id"] is not None},
        },
        "standards": {str(k): v for k, v in standards.items()},
    }


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _transaction(session: Session, transaction_id: int) -> "m.FinancialTransaction":
    transaction = session.get(m.FinancialTransaction, transaction_id)
    if transaction is None:
        raise ValueError(f"Transaction {transaction_id} does not exist.")
    return transaction


def _allocations(session: Session, transaction_id: int) -> list["m.BankTransactionAllocation"]:
    return economic_allocation.get_allocations(session, financial_transaction_id=transaction_id)


def _status(session: Session, transaction: "m.FinancialTransaction") -> str:
    explanation = recognition.get_current_explanation(session, financial_transaction_id=transaction.id)
    return reconciliation_status.status_of(transaction, explanation, _allocations(session, transaction.id))


def record_who(
    session: Session, *, transaction_id: int, occurrence_id: int | None, reason_id: int | None,
    account_id: int | None, any_active_why: bool = False,
) -> "m.BankTransactionExplanation":
    """Record WHO — and the WHY the operator chose — for one transaction.
    Never confirms the row.

    `any_active_why` (the grouped "Select WHO / WHY" popup,
    BANK_WHY_NAVIGATION_GROUPS_001) accepts ANY active WHY: the HUMAN
    decision itself then records the WHO -> WHY association
    (`recognition.record_human_decision`), once.

    A row that was CONFIRMED keeps its confirmation only when WHO and WHY are restated
    unchanged; any other change — and any change to an AUTOMATIC row — removes
    its allocation, so the row is NEEDS REVIEW until saved again."""
    transaction = _transaction(session, transaction_id)
    if occurrence_id is None:
        raise ValueError("Choose a WHO for this transaction.")
    occurrence = session.get(m.BankOccurrence, occurrence_id)
    if occurrence is None:
        raise ValueError(f"WHO {occurrence_id} does not exist.")
    if reason_id is not None and not any_active_why:
        allowed = set(session.scalars(
            select(m.BankOccurrenceReasonAssociation.transaction_reason_id).where(
                m.BankOccurrenceReasonAssociation.occurrence_id == occurrence.id,
                m.BankOccurrenceReasonAssociation.active.is_(True),
            )
        ))
        if reason_id not in allowed:
            raise ValueError(
                f"That WHY is not one of {occurrence.canonical_name!r}'s possible WHY. Add it to the "
                "WHO in Bank Configuration first, or choose it in the row's expanded editor."
            )

    previous = recognition.get_current_explanation(session, financial_transaction_id=transaction.id)
    was_confirmed = _status(session, transaction) == CONFIRMED
    unchanged = (previous is not None and previous.occurrence_id == occurrence.id
                 and previous.transaction_reason_id == reason_id)
    # Restating the same WHO/WHY keeps a transaction-level WHAT exception.
    keep_destination = (previous.accounting_classification_id
                        if unchanged and previous.accounting_destination_source == m.DESTINATION_SOURCE_TRANSACTION
                        else None)
    explanation = recognition.record_human_decision(
        session,
        recognition.HumanDecisionRequest(
            transaction_id=transaction.id, occurrence_id=occurrence.id,
            transaction_reason_id=reason_id, confirmed_by_account_id=account_id,
            accounting_classification_id=keep_destination,
            # The approved modal offers no learning choice, so none is made.
            learn_description=False,
        ),
    )
    if reason_id is not None:
        transaction.review_status = "REVIEWED"
    if _allocations(session, transaction.id) and not (was_confirmed and unchanged):
        economic_allocation.clear_allocations(session, financial_transaction_id=transaction.id)
    session.flush()
    return explanation


def _accept(
    session: Session, transaction: "m.FinancialTransaction", *, occurrence_id: int | None,
    reason_id: int | None, destination_id: int | None, reporting_entity_id: int | None,
    account_id: int | None,
) -> None:
    """The one way a person accepts a transaction: a HUMAN decision (WHO,
    WHY, destination — WHY-derived or a TRANSACTION exception, decided by the
    decision service from authoritative values) and a HUMAN, COMPLETE
    allocation for the whole amount (For Whom). Result: CONFIRMED."""
    if occurrence_id is None:
        raise ValueError("Choose the WHO of this transaction before confirming it.")
    if reason_id is None:
        raise ValueError("Choose the WHY of this transaction before confirming it.")
    if reporting_entity_id is None:
        raise ValueError("Choose For Whom before confirming this transaction.")
    occurrence = session.get(m.BankOccurrence, occurrence_id)
    if occurrence is None:
        raise ValueError(f"WHO {occurrence_id} does not exist.")
    entity = session.get(m.ReportingEntity, reporting_entity_id)
    if entity is None:
        raise ValueError(f"Entity {reporting_entity_id} does not exist.")
    if entity.status != "ACTIVE":
        raise ValueError(f"Entity {entity.name!r} is inactive.")
    if len(_allocations(session, transaction.id)) > 1:
        raise ValueError(
            "This transaction is split across several allocations; it is not confirmed from this row."
        )
    explanation = recognition.record_human_decision(
        session,
        recognition.HumanDecisionRequest(
            transaction_id=transaction.id, occurrence_id=occurrence.id,
            transaction_reason_id=reason_id, confirmed_by_account_id=account_id,
            accounting_classification_id=destination_id, learn_description=False,
        ),
    )
    economic_allocation.set_allocations(
        session, financial_transaction_id=transaction.id,
        specs=[economic_allocation.AllocationSpec(
            amount_minor=transaction.amount_minor, reporting_entity_id=entity.id,
            transaction_reason_id=explanation.transaction_reason_id,
            accounting_classification_id=explanation.accounting_classification_id,
            status=economic_allocation.COMPLETE, decision_source="HUMAN",
            decided_by_account_id=account_id, notes="Confirmed on Bank Reconciliation.",
        )],
    )
    transaction.review_status = "REVIEWED"
    session.flush()


def confirm_row(
    session: Session, *, transaction_id: int, reporting_entity_id: int | None,
    account_id: int | None,
) -> None:
    """Compact-row Confirm: accept THIS transaction with its current WHO,
    WHY and destination and the chosen For Whom. Creates no Standard."""
    transaction = _transaction(session, transaction_id)
    current = recognition.get_current_explanation(session, financial_transaction_id=transaction.id)
    if current is None or current.occurrence_id is None:
        raise ValueError("Choose the WHO of this transaction before confirming it.")
    if current.transaction_reason_id is None:
        raise ValueError("Choose the WHY of this transaction before confirming it.")
    _accept(session, transaction, occurrence_id=current.occurrence_id,
            reason_id=current.transaction_reason_id, destination_id=current.accounting_classification_id,
            reporting_entity_id=reporting_entity_id, account_id=account_id)


def save_row(
    session: Session, *, transaction_id: int, occurrence_id: int | None, reason_id: int | None,
    destination_id: int | None, reporting_entity_id: int | None, account_id: int | None,
    as_standard: bool,
) -> "m.BankReconciliationStandard | None":
    """The expanded editor's Save (`as_standard` False: keep every Standard
    unchanged) and Save as New Standard (`as_standard` True). Both accept the
    transaction as CONFIRMED with exactly the values given; the WHY may be
    any active WHY and the WHAT any P&L WHAT (or the destination the
    transaction already has). Save as New Standard then creates — or reuses,
    when identical — a Standard with a signature distinct from any ACTIVE
    Standard giving a different result; otherwise it refuses and nothing is
    written, so the operator can save the exception individually."""
    transaction = _transaction(session, transaction_id)
    signature = standards_service.signature_for(session, transaction) if as_standard else None
    if reason_id is not None:
        reason = session.get(m.BankTransactionReason, reason_id)
        if reason is None:
            raise ValueError(f"WHY {reason_id} does not exist.")
    _accept(session, transaction, occurrence_id=occurrence_id, reason_id=reason_id,
            destination_id=destination_id, reporting_entity_id=reporting_entity_id, account_id=account_id)
    if not as_standard:
        return None
    explanation = recognition.get_current_explanation(session, financial_transaction_id=transaction.id)
    standard, _created = standards_service.create_or_reuse(
        session, signature=signature,
        result=standards_service.Result(
            occurrence_id=explanation.occurrence_id, transaction_reason_id=explanation.transaction_reason_id,
            accounting_classification_id=explanation.accounting_classification_id,
            reporting_entity_id=reporting_entity_id,
        ),
        approved_by_account_id=account_id, created_from_transaction_id=transaction.id,
    )
    return standard


def set_as_standard(
    session: Session, *, transaction_id: int, reporting_entity_id: int | None, account_id: int | None,
) -> "m.BankReconciliationStandard":
    """Compact-row Set as Standard: the current values, as shown."""
    transaction = _transaction(session, transaction_id)
    current = recognition.get_current_explanation(session, financial_transaction_id=transaction.id)
    if current is None or current.occurrence_id is None or current.transaction_reason_id is None:
        raise ValueError("A Standard needs a WHO and a WHY. Complete the row first.")
    return save_row(
        session, transaction_id=transaction.id, occurrence_id=current.occurrence_id,
        reason_id=current.transaction_reason_id, destination_id=current.accounting_classification_id,
        reporting_entity_id=reporting_entity_id, account_id=account_id, as_standard=True,
    )


def reopen_row(session: Session, *, transaction_id: int) -> int:
    """Withdraw a row's acceptance (CONFIRMED or AUTOMATIC). The decision is
    untouched; no Standard is changed."""
    transaction = _transaction(session, transaction_id)
    allocations = _allocations(session, transaction.id)
    if len(allocations) > 1:
        raise ValueError("This transaction is split across several allocations; reopen it where it was split.")
    return economic_allocation.clear_allocations(session, financial_transaction_id=transaction.id)
