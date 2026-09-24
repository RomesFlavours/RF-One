#!/usr/bin/env python
"""Deterministic structural WHY — BANK_HISTORICAL_DETERMINISTIC_WHY_EXPERTIZATION_001.

Proves, on a throwaway database:

* each rule fires only on the bank's own wording, in the verified
  direction and source layout — "INTEREST PAYMENT ON LOAN" debited is never
  interest income, a vague "FEE REVERSAL" is never a service charge;
* WHO never determines WHY: a Zelle payment, an ADP wage/tax debit and a
  mixed supplier stay UNRESOLVED;
* a transfer between two accounts of ONE legal entity is an internal
  transfer, between two legal entities a related-party transfer, and
  anything involving a personal instrument or an unregistered account is
  not decided;
* a card payment settles the card only when the paying account is that
  card's own settlement owner; unregistered cards are not decided;
* persistence writes one RULE decision per resolved transaction, derives the
  WHAT/destination from the WHY, writes no allocation, never overwrites a
  human decision, and a second run changes nothing.

Never touches AWS, RDS, the operational database, or a real bank file.
"""

from __future__ import annotations

import sys
from datetime import date

from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import recognition
from rfone_data_store.bank_reconciliation import structural_why as sw
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)

POSTING_DATE = date(2026, 3, 15)

LE1_CHECKING = sw.InstrumentInfo(6, 1, "BANK_ACCOUNT")
LE1_SAVING = sw.InstrumentInfo(4, 1, "BANK_ACCOUNT")
LE2_CHECKING = sw.InstrumentInfo(5, 2, "BANK_ACCOUNT")
PERSONAL = sw.InstrumentInfo(2, None, "BANK_ACCOUNT")
LE1_CARD = sw.InstrumentInfo(9, 1, "CREDIT_CARD")
REGISTERED = {"3376": LE1_CHECKING, "7129": LE1_SAVING, "3583": LE2_CHECKING, "9318": PERSONAL,
              "1057": LE1_CARD}


def _ctx(amount, fmt="CHASE_BANK_ACCOUNT", instrument=LE1_CHECKING, settlement=None):
    return sw.WhyContext(detected_format=fmt, amount_minor=amount, instrument=instrument,
                         registered_last_four=REGISTERED,
                         settlement_of=lambda card_id: settlement)


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    def why(description, ctx):
        return sw.recognize_why(description, ctx)

    # =================================================================
    # Pure rules
    # =================================================================
    r = why("FOREIGN TRANSACTION FEE", _ctx(-300, fmt="CHASE_CREDIT_CARD_NO_CARD", instrument=LE1_CARD))
    check("a named foreign transaction fee is DETERMINISTIC", r.tier == sw.DETERMINISTIC
          and r.why_code == "FOREIGN_TRANSACTION_FEE", repr(r))
    r = why("FOREIGN TRANSACTION FEE", _ctx(300, fmt="CHASE_CREDIT_CARD_NO_CARD", instrument=LE1_CARD))
    check("the same words credited are not a fee", not r.is_resolved, repr(r))

    r = why("INTEREST PAYMENT", _ctx(5, instrument=LE1_SAVING))
    check("bank interest credited is INTEREST_INCOME", r.why_code == "INTEREST_INCOME", repr(r))
    r = why("DEBIT MEMORANDUM REF: INTEREST PAYMENT ON LOAN TRN: 0803792329DM 08/25", _ctx(-69894))
    check("loan interest debited is INTEREST_EXPENSE, never income",
          r.why_code == "INTEREST_EXPENSE", repr(r))
    r = why("INTEREST PAYMENT", _ctx(-5))
    check("'INTEREST PAYMENT' debited is not interest income", r.why_code != "INTEREST_INCOME", repr(r))

    for text in ("MONTHLY SERVICE FEE", "OFFICIAL CHECKS CHARGE", "Zelle Credit Transaction Fee",
                 "OVERDRAFT FEE FOR A $3,854.66 ITEM - DETAILS: ORIG CO NAME:ADP Tax"):
        r = why(text, _ctx(-1500, fmt="FIRST_CITIZENS" if "Zelle" in text else "CHASE_BANK_ACCOUNT"))
        check(f"{text[:32]!r} is a bank service charge", r.why_code == "BANK_SERVICE_CHARGE", repr(r))
    r = why("FEE REVERSAL", _ctx(1500))
    check("an unspecified fee reversal is not decided", not r.is_resolved and r.family == "FEE_UNSPECIFIED")
    r = why("MF1 REFUND OF MONTHLY SERVICE FEE CHARGED 01-01-2026", _ctx(1500))
    check("a refund naming the service fee reverses BANK_SERVICE_CHARGE",
          r.why_code == "BANK_SERVICE_CHARGE", repr(r))

    r = why("FRST BK MRCH SVC INTERCHNG ********0885", _ctx(-2000, fmt="FIRST_CITIZENS"))
    check("a named merchant-services fee component is MERCHANT_PROCESSING_FEE",
          r.why_code == "MERCHANT_PROCESSING_FEE", repr(r))
    r = why("FRST BK MRCH SVC DEPOSIT ********0885", _ctx(200000, fmt="FIRST_CITIZENS"))
    check("a merchant settlement deposit is NOT revenue and NOT decided",
          not r.is_resolved and r.family == "MERCHANT_SETTLEMENT_DEPOSIT", repr(r))

    r = why("Payment Thank You - Web", _ctx(50000, fmt="CHASE_CREDIT_CARD_NO_CARD", instrument=LE1_CARD))
    check("a payment received on the card settles it", r.tier == sw.DETERMINISTIC
          and r.why_code == "CREDIT_CARD_SETTLEMENT", repr(r))
    r = why("Payment to Chase card ending in 1057 07/29", _ctx(-50000, settlement=LE1_CHECKING))
    check("paying a registered card from its own settlement account settles it",
          r.tier == sw.DETERMINISTIC and r.why_code == "CREDIT_CARD_SETTLEMENT", repr(r))
    r = why("Payment to Chase card ending in 1057 07/29",
            _ctx(-50000, instrument=LE2_CHECKING, settlement=LE1_CHECKING))
    check("paying another legal entity's card is not decided",
          not r.is_resolved and r.family == "CARD_PAYMENT_CROSS_OWNER", repr(r))
    r = why("Payment to Chase card ending in 0246 08/03", _ctx(-3000))
    check("paying an unregistered card is not decided (candidate not resolved)",
          not r.is_resolved and r.family == "CARD_PAYMENT_UNREGISTERED_CARD", repr(r))
    r = why("ORIG CO NAME:AMERICAN EXPRESS       ORIG ID:9493560001 DESC DATE:260610 CO ENTRY "
            "DESCR:ACH PMT   SEC:CCD    TRACE#:021000029014846", _ctx(-90000))
    check("an issuer-originated card payment is STRONG_STRUCTURAL card settlement",
          r.tier == sw.STRONG_STRUCTURAL and r.why_code == "CREDIT_CARD_SETTLEMENT", repr(r))
    r = why("ORIG CO NAME:CHASE CREDIT CRD       ORIG ID:4760039224 DESC DATE:251008 CO ENTRY "
            "DESCR:AUTOPAYBUSSEC:PPD    TRACE#:021000024512217", _ctx(-90000))
    check("the AUTOPAYBUS entry filling its fixed-width field is still recognised",
          r.why_code == "CREDIT_CARD_SETTLEMENT", repr(r))

    r = why("Online Transfer to SAV ...7129 transaction#: 1234567", _ctx(-10000))
    check("a transfer between two accounts of one legal entity is INTERNAL_BANK_TRANSFER",
          r.tier == sw.DETERMINISTIC and r.why_code == "INTERNAL_BANK_TRANSFER", repr(r))
    r = why("Online Transfer to CHK ...3583 transaction#: 1234567", _ctx(-10000))
    check("a transfer to another legal entity is RELATED_PARTY_TRANSFER_OUT, never internal",
          r.why_code == "RELATED_PARTY_TRANSFER_OUT", repr(r))
    r = why("Online Transfer from CHK ...3376 transaction#: 1234567", _ctx(10000, instrument=LE2_CHECKING))
    check("the receiving entity records RELATED_PARTY_TRANSFER_IN",
          r.why_code == "RELATED_PARTY_TRANSFER_IN", repr(r))
    r = why("Online Transfer to CHK ...9318 transaction#: 1234567", _ctx(-10000))
    check("a transfer involving a personal instrument is not decided",
          not r.is_resolved and r.family == "TRANSFER_PERSONAL_INSTRUMENT", repr(r))
    r = why("Online Transfer to CHK ...4444 transaction#: 1234567", _ctx(-10000))
    check("a transfer to an unregistered account is not guessed",
          not r.is_resolved and r.family == "TRANSFER_UNKNOWN_ACCOUNT", repr(r))

    for text, family in (
        ("Zelle payment to Alice Martini JPM99bzcwxfi", "ZELLE"),
        ("ORIG CO NAME:ADP WAGE PAY           ORIG ID:9333006057 CO ENTRY DESCR:WAGE PAY  SEC:CCD", "ADP_WAGE_PAY"),
        ("ORIG CO NAME:ADP Tax                ORIG ID:1223006057 CO ENTRY DESCR:ADP Tax   SEC:CCD", "ADP_TAX_IMPOUND"),
        ("FLA DEPT REVENUE C01 ****6811", "TAX_AUTHORITY"),
        ("PURCHASE 06/25 COSTCO WHSE #01 COSTCO WHSE #018ALTAMONTE SPFL 990183", "NO_STRUCTURAL_PURPOSE"),
        ("AMAZON MKTPL*Q078B1TJ3", "NO_STRUCTURAL_PURPOSE"),
    ):
        r = why(text, _ctx(-5000, fmt="FIRST_CITIZENS" if text.startswith(("FLA", "PURCHASE")) else "CHASE_BANK_ACCOUNT"))
        check(f"WHO alone never decides WHY: {family}", not r.is_resolved and r.family == family, repr(r))

    # =================================================================
    # Persistence — throwaway database
    # =================================================================
    url = resolve_test_database_url("bank_structural_why")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as s:
            le = m.LegalEntity(legal_name="RF Winter Park, LLC", status="ACTIVE")
            s.add(le)
            s.flush()
            checking = m.PaymentInstrument(instrument_type="BANK_ACCOUNT", display_name="Checking",
                                           institution="Chase", last_four="3376", legal_entity_id=le.id)
            saving = m.PaymentInstrument(instrument_type="BANK_ACCOUNT", display_name="Saving",
                                         institution="Chase", last_four="7129", legal_entity_id=le.id)
            s.add_all([checking, saving])
            s.flush()
            batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="t.csv",
                                      raw_file_bytes=b"x", sha256="1" * 64,
                                      payment_instrument_id=checking.id)
            s.add(batch)
            s.flush()
            rows = [
                ("MONTHLY SERVICE FEE", -1500),
                ("Online Transfer to SAV ...7129 transaction#: 1234567", -10000),
                ("Zelle payment to Alice Martini JPM99bzcwxfi", -5000),
                ("INTEREST PAYMENT", 7),
                ("OFFICIAL CHECKS CHARGE", -1000),
            ]
            txns = []
            for index, (description, amount) in enumerate(rows):
                txn = m.FinancialTransaction(
                    payment_instrument_id=checking.id, posting_date=POSTING_DATE,
                    transaction_date=POSTING_DATE, description_original=description,
                    amount_minor=amount, status="COMPLETED", classification="UNKNOWN",
                    import_batch_id=batch.id, fingerprint=f"fp{index}:0",
                )
                s.add(txn)
                txns.append(txn)
            s.flush()
            # A human already decided the last row: it must never be overwritten.
            human_reason = s.scalar(select(m.BankTransactionReason)
                                    .where(m.BankTransactionReason.code == "CONSULTING"))
            recognition._create_decision_row(
                s, txns[4], occurrence_id=None, transaction_reason_id=human_reason.id,
                recognition_rule_id=None, decision_source="HUMAN", decision_status="HUMAN_CONFIRMED",
                confidence=None, explanation_notes="human test decision",
            )
            s.commit()

            summary, _ = sw.apply_structural_why(s)
            s.commit()
            check("three structural decisions were written (fee, transfer, interest)",
                  summary.decisions_created == 3, repr(summary))
            check("the human decision was skipped, not overwritten",
                  summary.skipped_human == 1
                  and recognition.get_current_explanation(
                      s, financial_transaction_id=txns[4].id).decision_source == "HUMAN")
            check("the Zelle payment received no decision",
                  recognition.get_current_explanation(s, financial_transaction_id=txns[2].id) is None)
            fee = recognition.get_current_explanation(s, financial_transaction_id=txns[0].id)
            check("the WHAT is derived from the WHY (7220), recorded as RULE / AUTO_APPLIED",
                  fee.accounting_classification_code_snapshot == "7220"
                  and fee.decision_source == "RULE" and fee.decision_status == "AUTO_APPLIED"
                  and fee.explanation_notes.startswith(sw.tag("BANK_SERVICE_CHARGE")), repr(fee.explanation_notes))
            transfer = recognition.get_current_explanation(s, financial_transaction_id=txns[1].id)
            check("the internal transfer lands on a Balance Sheet destination",
                  transfer.accounting_statement_type_snapshot == "BALANCE_SHEET")
            check("no allocation was created (FOR WHOM is not decided)",
                  s.scalar(select(func.count(m.BankTransactionAllocation.id))) == 0)
            check("no recognition rule was created",
                  s.scalar(select(func.count(m.BankRecognitionRule.id))) == 0)
            check("no refused destination", summary.refused_destination == [], repr(summary.refused_destination))

            decisions = s.scalar(select(func.count(m.BankTransactionExplanation.id)))
            second, _ = sw.apply_structural_why(s)
            s.commit()
            check("second run creates no decision",
                  second.decisions_created == 0 and second.decisions_unchanged == 3
                  and s.scalar(select(func.count(m.BankTransactionExplanation.id))) == decisions,
                  repr(second))
            check("second run has no conflict", second.conflicts == [])
    finally:
        engine.dispose()

    print(f"\n{len(checks_passed)} passed, {len(checks_failed)} failed")
    return 1 if checks_failed else 0


if __name__ == "__main__":
    sys.exit(main())
