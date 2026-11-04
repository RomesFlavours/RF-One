#!/usr/bin/env python
"""Post-import knowledge and completeness pass
(BANK_HISTORICAL_CLEAN_CONSOLIDATE_AND_IMPORT_001 §18, §25-§39).

Runs the CURRENTLY APPROVED logic against the imported canonical
transactions and reports what it could and could not establish. It is
fail-closed throughout: where evidence is missing, the fact stays UNKNOWN,
NEEDS_OPERATOR or PENDING_EVIDENCE. Nothing is invented to improve a
percentage.

    --apply   write the WHO recognition decisions and supplier links
              the existing rules actually support
    (default) report only

Never creates a recognition rule, a Supplier, an Occurrence, a WHY, a
beneficiary or an invoice match that the evidence does not already carry.
Never touches AWS.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import economic_allocation as allocation
from rfone_data_store.bank_reconciliation import economic_reporting as reporting
from rfone_data_store.bank_reconciliation import historical_source, invoice_evidence
from rfone_data_store.bank_reconciliation import invoice_allocation_bridge as bridge
from rfone_data_store.bank_reconciliation import invoice_matching, recognition
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    redact_database_url,
)


def who_recognition(session, *, apply: bool) -> dict:
    """Run existing deterministic recognition over every imported
    transaction.

    No learned rule is created from historical repetition: a counterparty
    appearing four hundred times is a frequency, not a human confirmation,
    and treating it as one is exactly how a wrong classification becomes
    permanent. Transactions whose WHO cannot be established stay
    canonical and unresolved, which is a valid state."""
    rule_count = session.scalar(select(func.count(m.BankRecognitionRule.id)))
    occurrence_count = session.scalar(select(func.count(m.BankOccurrence.id)))
    transactions = list(
        session.scalars(
            select(m.FinancialTransaction).order_by(m.FinancialTransaction.id)
        )
    )

    resolved = 0
    unresolved = 0
    if apply and rule_count:
        for transaction in transactions:
            if transaction.explanation_id is not None:
                continue
            explanation = recognition.deduce_for_transaction(session, transaction)
            if explanation.occurrence_id is not None:
                resolved += 1
            else:
                unresolved += 1
        session.flush()
    else:
        unresolved = len(transactions)

    return {
        "recognition_rules_available": rule_count,
        "occurrences_available": occurrence_count,
        "transactions": len(transactions),
        "who_resolved": resolved,
        "who_unresolved": unresolved,
        "note": (
            "No ACTIVE recognition rule and no BankOccurrence exists in this database, so no WHO "
            "can be established by the approved deterministic logic. Every transaction remains "
            "canonical with WHO unresolved. Creating rules from historical repetition is "
            "explicitly out of scope."
            if not rule_count else ""
        ),
    }


def supplier_linking(session, *, apply: bool) -> dict:
    """Run WHO -> Supplier discovery for every resolved counterparty."""
    outcomes = Counter()
    details: list[dict] = []
    for occurrence in session.scalars(select(m.BankOccurrence).order_by(m.BankOccurrence.id)):
        proposal = invoice_evidence.propose_supplier_link_for_occurrence(
            session, occurrence_id=occurrence.id, auto_link=apply,
        )
        outcomes[proposal.outcome] += 1
        details.append(
            {
                "occurrence": occurrence.canonical_name,
                "outcome": proposal.outcome,
                "supplier_id": proposal.supplier_id,
            }
        )
    return {"outcomes": dict(sorted(outcomes.items())), "details": details}


def invoice_match_coverage(session) -> dict:
    """Run the many-to-many matcher where a WHO is linked to a Supplier
    that actually has purchase documents."""
    linked = session.scalar(select(func.count(m.BankOccurrenceSupplier.id)))
    documents = session.scalar(select(func.count(m.PurchaseDocument.id)))
    matched = session.scalar(select(func.count(m.BankInvoiceMatch.id)))
    transactions = session.scalar(select(func.count(m.FinancialTransaction.id)))

    candidates_generated = 0
    if linked:
        for transaction in session.scalars(
            select(m.FinancialTransaction).where(
                m.FinancialTransaction.explanation_id.is_not(None)
            )
        ):
            report = invoice_matching.generate_candidates(
                session, financial_transaction_id=transaction.id,
            )
            candidates_generated += len(report.candidates)

    return {
        "who_supplier_links": linked,
        "purchase_documents": documents,
        "candidates_generated": candidates_generated,
        "confirmed_matches": matched,
        "transactions": transactions,
        "coverage_pct": round(100.0 * matched / transactions, 2) if transactions else 0.0,
        "note": (
            "No WHO is linked to a Supplier, so the matcher has no supplier scope to search. "
            "Matching on amount alone is never done."
            if not linked else ""
        ),
    }


def allocation_state(session) -> dict:
    """Allocation state for every canonical transaction (§31)."""
    total = session.scalar(select(func.count(m.FinancialTransaction.id)))
    with_allocations = session.scalar(
        select(func.count(func.distinct(m.BankTransactionAllocation.financial_transaction_id)))
    )
    by_status = dict(
        session.execute(
            select(
                m.BankTransactionAllocation.status,
                func.count(func.distinct(m.BankTransactionAllocation.financial_transaction_id)),
            ).group_by(m.BankTransactionAllocation.status)
        ).all()
    )
    return {
        "transactions": total,
        "unallocated": total - (with_allocations or 0),
        "by_allocation_status": {k: int(v) for k, v in sorted(by_status.items())},
        "complete": int(by_status.get(m.ALLOCATION_COMPLETE, 0)),
        "complete_pct": round(
            100.0 * int(by_status.get(m.ALLOCATION_COMPLETE, 0)) / total, 2
        ) if total else 0.0,
    }


def instrument_census(session) -> dict:
    """The bidirectional historical instrument census (§18), run over ALL
    original evidence rather than only the accepted events.

    Three directions, because they fail in three different ways:

      registered -> source   a card RF-One knows about with no file
      source -> registered   a file for an account RF-One does not know
      indirect -> possible   an account number MENTIONED inside another
                             account's transaction text

    Candidates are reported, never pre-resolved."""
    instruments = {
        instrument.id: instrument
        for instrument in session.scalars(select(m.PaymentInstrument))
    }
    batches = list(session.scalars(select(m.BankImportBatch)))

    sourced = {b.payment_instrument_id for b in batches if b.payment_instrument_id}
    # A multi-card export has no single instrument, so the authoritative
    # answer for "which instruments have evidence" is the transactions.
    with_transactions = {
        row[0] for row in session.execute(
            select(m.FinancialTransaction.payment_instrument_id).distinct()
        ).all()
    }

    registered_without_source = sorted(
        (i.id, i.display_name, historical_source.instrument_last_four(i))
        for i in instruments.values() if i.id not in with_transactions
    )

    # Indirect references: account-like numbers appearing inside the text
    # of transactions belonging to some OTHER instrument.
    known_last_four = {
        historical_source.instrument_last_four(i)
        for i in instruments.values()
        if historical_source.instrument_last_four(i)
    }
    indirect: Counter = Counter()
    for description, memo in session.execute(
        select(m.FinancialTransaction.description_original, m.FinancialTransaction.source_memo)
    ).all():
        for text in (description, memo):
            for token in historical_source.extract_instrument_references(text):
                if token not in known_last_four:
                    indirect[token] += 1

    return {
        "registered_instruments": len(instruments),
        "instruments_with_transactions": sorted(with_transactions),
        "instruments_with_source_files": sorted(sourced),
        "registered_without_any_source": [
            {"id": i, "display_name": n, "last_four": lf}
            for i, n, lf in registered_without_source
        ],
        "indirect_references_not_registered": [
            {"last_four": token, "mentions": count}
            for token, count in sorted(indirect.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        # What is actually persisted (discover_historical_instrument_candidates.py).
        "persisted_candidates": [
            {
                "last_four": c.last_four, "discovery": c.discovery,
                "occurrence_count": c.occurrence_count, "resolution": c.resolution,
                "state": historical_source.candidate_state(c),
            }
            for c in historical_source.list_candidates(session)
        ],
    }


def per_instrument_report(session) -> list[dict]:
    """Every registered instrument, including those with no source (§38)."""
    rows: list[dict] = []
    for instrument in session.scalars(
        select(m.PaymentInstrument).order_by(m.PaymentInstrument.id)
    ):
        transactions = list(
            session.scalars(
                select(m.FinancialTransaction).where(
                    m.FinancialTransaction.payment_instrument_id == instrument.id
                )
            )
        )
        # Attributed through the canonical transaction each raw row
        # evidences, not the batch header: a multi-instrument export has no
        # header instrument, and counting by it lost those rows
        # (BANK_HISTORICAL_DATASET_AUDIT_REPAIR_001 §6).
        batches = session.scalar(
            select(func.count(func.distinct(m.RawBankTransaction.import_batch_id)))
            .join(m.FinancialTransaction,
                  m.FinancialTransaction.id == m.RawBankTransaction.normalized_transaction_id)
            .where(m.FinancialTransaction.payment_instrument_id == instrument.id)
        )
        raw_rows = session.scalar(
            select(func.count(m.RawBankTransaction.id))
            .join(m.FinancialTransaction,
                  m.FinancialTransaction.id == m.RawBankTransaction.normalized_transaction_id)
            .where(m.FinancialTransaction.payment_instrument_id == instrument.id)
        )
        dates = [t.posting_date for t in transactions if t.posting_date]
        who_resolved = sum(1 for t in transactions if t.explanation_id is not None)
        allocated = session.scalar(
            select(func.count(func.distinct(
                m.BankTransactionAllocation.financial_transaction_id
            ))).join(
                m.FinancialTransaction,
                m.FinancialTransaction.id
                == m.BankTransactionAllocation.financial_transaction_id,
            ).where(m.FinancialTransaction.payment_instrument_id == instrument.id)
        )
        rows.append(
            {
                "id": instrument.id,
                "display_name": instrument.display_name,
                "instrument_type": instrument.instrument_type,
                "last_four": historical_source.instrument_last_four(instrument),
                "legal_entity_id": instrument.legal_entity_id,
                "source_batches": int(batches or 0),
                "raw_source_rows": int(raw_rows or 0),
                "canonical_transactions": len(transactions),
                "earliest": min(dates).isoformat() if dates else None,
                "latest": max(dates).isoformat() if dates else None,
                "debit_minor": sum(t.amount_minor for t in transactions if t.amount_minor < 0),
                "credit_minor": sum(t.amount_minor for t in transactions if t.amount_minor > 0),
                "who_resolved": who_resolved,
                "who_unresolved": len(transactions) - who_resolved,
                "allocated_transactions": int(allocated or 0),
                "unallocated": len(transactions) - int(allocated or 0),
            }
        )
    return rows


def diagnostic_profit_and_loss(session) -> dict:
    """Diagnostic P&L from COMPLETE allocations only (§39).

    Explicitly NOT a financial statement while allocation coverage is
    incomplete: the excluded amount is reported alongside the included one
    so nobody can mistake a partial view for a total."""
    total_transactions = session.scalar(select(func.count(m.FinancialTransaction.id)))
    complete_transactions = session.scalar(
        select(func.count(func.distinct(m.BankTransactionAllocation.financial_transaction_id)))
        .where(m.BankTransactionAllocation.status == m.ALLOCATION_COMPLETE)
    ) or 0
    included_minor = session.scalar(
        select(func.sum(m.BankTransactionAllocation.amount_minor))
        .where(m.BankTransactionAllocation.status == m.ALLOCATION_COMPLETE)
    ) or 0
    all_money = session.scalar(select(func.sum(m.FinancialTransaction.amount_minor))) or 0

    entities = []
    for entity in session.scalars(select(m.ReportingEntity).order_by(m.ReportingEntity.code)):
        report = reporting.profit_and_loss_for_entity(session, reporting_entity_id=entity.id)
        entities.append(
            {
                "code": entity.code, "name": entity.name,
                "total_minor": report.total_minor,
                "lines": len(report.lines),
                "allocation_count": report.allocation_count,
            }
        )
    consolidated = None
    group = session.scalar(select(m.ReportingGroup))
    if group is not None:
        report = reporting.consolidated_profit_and_loss(session, reporting_group_id=group.id)
        consolidated = {
            "group": group.name, "total_minor": report.total_minor,
            "lines": len(report.lines), "allocation_count": report.allocation_count,
        }

    return {
        "entities": entities,
        "consolidated": consolidated,
        "included_minor": int(included_minor),
        "excluded_minor_allocation_incomplete": int(all_money) - int(included_minor),
        "pending_transaction_count": total_transactions - complete_transactions,
        "is_final_statement": complete_transactions == total_transactions and total_transactions > 0,
    }


def completeness(session) -> dict:
    """The six states, reported separately and never merged (§37)."""
    total = session.scalar(select(func.count(m.FinancialTransaction.id)))
    financially_resolved = session.scalar(
        select(func.count(m.FinancialTransaction.id)).where(
            m.FinancialTransaction.accounting_status == "CANONICAL"
        )
    )
    return {
        "A_source_corpus": "see source manifest: every file inventoried, hashed and classified",
        "B_financial_ingestion": {
            "clean_events_promoted": total,
            "raw_rows_preserved": session.scalar(select(func.count(m.RawBankTransaction.id))),
            "batches": session.scalar(select(func.count(m.BankImportBatch.id))),
        },
        "C_financial_reconciliation": {
            "canonical": financially_resolved,
            "pct": round(100.0 * financially_resolved / total, 2) if total else 0.0,
        },
        "D_who_resolution": {
            "resolved": session.scalar(
                select(func.count(m.FinancialTransaction.id)).where(
                    m.FinancialTransaction.explanation_id.is_not(None)
                )
            ),
            "total": total,
        },
        "E_invoice_match": {
            "matched": session.scalar(select(func.count(m.BankInvoiceMatch.id))),
            "total": total,
        },
        "F_accounting_allocation": allocation_state(session),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    url = args.database_url or get_database_url()
    print(f"Database URL: {redact_database_url(url)}")
    print(f"Mode        : {'APPLY' if args.apply else 'REPORT ONLY'}")
    print()

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            result = {
                "who_recognition": who_recognition(session, apply=args.apply),
                "supplier_linking": supplier_linking(session, apply=args.apply),
                "invoice_matching": invoice_match_coverage(session),
                "allocation": allocation_state(session),
                "instrument_census": instrument_census(session),
                "per_instrument": per_instrument_report(session),
                "completeness": completeness(session),
                "diagnostic_pl": diagnostic_profit_and_loss(session),
            }
            if args.apply:
                session.commit()
            else:
                session.rollback()
    finally:
        engine.dispose()

    for section in ("who_recognition", "supplier_linking", "invoice_matching", "allocation"):
        print(f"--- {section} ---")
        print(json.dumps(result[section], indent=2, default=str)[:1400])
        print()
    print("--- instrument census ---")
    print(json.dumps(result["instrument_census"], indent=2, default=str))
    print()
    print("--- completeness ---")
    print(json.dumps(result["completeness"], indent=2, default=str))
    print()
    print("--- diagnostic P&L ---")
    print(json.dumps(result["diagnostic_pl"], indent=2, default=str))

    if args.json_out:
        os.makedirs(os.path.dirname(args.json_out), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, default=str, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
