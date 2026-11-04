#!/usr/bin/env python
"""WHO recognition from the bank's own text — BANK_HISTORICAL_WHO_RECOGNITION_001.

Proves, on a throwaway database:

* each parser reads the counterparty only from a proven structure, and
  everything it cannot prove stays PROPOSED or UNRESOLVED;
* a transfer between RF-One's own instruments, a card settlement and a
  payment to one of its own legal entities never become an external WHO,
  so they can never become a supplier;
* an account RF-One has not registered is reported, never guessed;
* Zelle recipients are extracted only from the structured Chase line;
* recognition writes no WHY, no decision, no allocation, and does not touch
  a single financial transaction;
* a WHO is linked to a Supplier only on an exact normalized name;
* a second run changes nothing.

Never touches AWS, RDS, the operational database, or a real bank file.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import date

from sqlalchemy import func, select, text

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import who_recognition as wr
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)

POSTING_DATE = date(2026, 3, 15)


def _ctx(fmt="CHASE_BANK_ACCOUNT", amount=-1000, institution="Chase", registered=None,
         entities=None) -> wr.WhoContext:
    return wr.WhoContext(
        detected_format=fmt, instrument_type=None, institution=institution, amount_minor=amount,
        registered_last_four=registered or {"3376": 6, "3583": 5, "1562": 8},
        legal_entities=entities or {wr.legal_entity_key("Angeli E Demoni, LLC"): 1},
    )


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    # =================================================================
    # Pure recognition — no database
    # =================================================================
    r = wr.recognize("Zelle payment to Charlize Irizarry JPM99b5p8jv0", _ctx())
    check("Chase Zelle recipient before the bank reference is DETERMINISTIC",
          r.tier == wr.DETERMINISTIC and r.name == "CHARLIZE IRIZARRY", repr(r))
    check("the Zelle reference is never part of the WHO", "JPM" not in (r.name or ""))

    r = wr.recognize("Zelle payment to Mario Rossi", _ctx())
    check("a Zelle line without the bank reference is only PROPOSED",
          r.tier == wr.PROPOSED and r.proposed_name == "MARIO ROSSI", repr(r))

    r = wr.recognize("Zelle Gabrielle Alexia Mi 877-206-3818", _ctx(fmt="FIRST_CITIZENS"))
    check("a First Citizens Zelle line (truncated name) is PROPOSED, not DETERMINISTIC",
          r.tier == wr.PROPOSED and r.name is None and r.proposed_name == "GABRIELLE ALEXIA MI",
          repr(r))

    r = wr.recognize("Zelle ANGELI E DEMONI  877-206-3818", _ctx(fmt="FIRST_CITIZENS"))
    check("a First Citizens Zelle line naming RF-One's own legal entity is STRUCTURAL",
          r.tier == wr.STRUCTURAL and r.internal_legal_entity_id == 1, repr(r))

    r = wr.recognize("Zelle payment from ANGELI E DEMONI LLC 23149425230", _ctx(amount=5000))
    check("a Chase Zelle from RF-One's own legal entity is STRUCTURAL, never a WHO",
          r.tier == wr.STRUCTURAL and r.family == wr.F_OWN_LEGAL_ENTITY and r.name is None, repr(r))

    r = wr.recognize("Online Transfer from CHK ...3376 transaction#: 24742536198", _ctx(amount=100))
    check("an online transfer from a registered instrument is STRUCTURAL with that instrument",
          r.tier == wr.STRUCTURAL and r.internal_payment_instrument_id == 6, repr(r))

    r = wr.recognize("Payment to Chase card ending in 0246 08/03", _ctx())
    check("a payment to an unregistered card is UNRESOLVED and names the last four only",
          r.tier == wr.UNRESOLVED and r.referenced_last_four == "0246"
          and r.internal_payment_instrument_id is None, repr(r))

    r = wr.recognize("FCB FUNDS TRANSFER TO  X8326", _ctx(fmt="FIRST_CITIZENS"))
    check("a First Citizens transfer to an unknown account is not guessed",
          r.tier == wr.UNRESOLVED and r.referenced_last_four == "8326", repr(r))

    r = wr.recognize("Payment Thank You - Web", _ctx(fmt="CHASE_CREDIT_CARD_NO_CARD", amount=5000))
    check("a card settlement received on the card has no external WHO",
          r.tier == wr.STRUCTURAL and r.family == wr.F_CARD_SETTLEMENT, repr(r))

    r = wr.recognize(
        "ORIG CO NAME:ADP Tax                ORIG ID:1223006057 DESC DATE:241016 CO ENTRY "
        "DESCR:ADP Tax   SEC:CCD    TRACE#:091000012591149", _ctx())
    r2 = wr.recognize(
        "ORIG CO NAME:ADP WAGE PAY           ORIG ID:9333006057 DESC DATE:260416 CO ENTRY "
        "DESCR:WAGE PAY  SEC:CCD    TRACE#:021000029684342", _ctx())
    check("ADP service lines are one WHO (ADP) — the service suffix is not identity",
          r.name == "ADP" and r2.name == "ADP", f"{r!r} {r2!r}")
    check("WHO recognition carries no WHY field at all",
          not any(hasattr(r, attr) for attr in ("why_code", "transaction_reason_id", "account_code")))

    r = wr.recognize("FOREIGN TRANSACTION FEE", _ctx(fmt="CHASE_CREDIT_CARD_NO_CARD"))
    check("a bank-generated fee names the institution as WHO",
          r.tier == wr.DETERMINISTIC and r.name == "JPMORGAN CHASE BANK", repr(r))

    r = wr.recognize("Check", _ctx())
    check("a bare Check names nobody", r.tier == wr.UNRESOLVED and r.family == wr.F_NOT_NAMED)

    r = wr.recognize("POS SIG 12/21 VISA #5363 IC* INSTACART INSTACART.COM CA",
                     _ctx(fmt="FIRST_CITIZENS", institution="First Citizens"))
    check("a facilitator/brand grammar collapses only proven reference variants",
          r.tier == wr.DETERMINISTIC and r.name == "INSTACART", repr(r))

    check("normalization keeps store numbers (splitting is the safe error)",
          wr.normalize_who_name("COSTCO WHSE #0183") == "COSTCO WHSE #0183")
    check("normalization removes masked reference digits only",
          wr.normalize_who_name("CHENEY BROTHERS A/R PAYMNT ****5383") == "CHENEY BROTHERS A/R PAYMNT")

    body = wr.WhoResult(wr.PROPOSED, wr.F_ACH_MASKED, "ACH_MASKED_BODY",
                        proposed_name="CHENEY BROTHERS A/R PAYMNT", needs_corroboration=True,
                        reference_token="****5383")
    corroborated = wr.corroborate(body, {"CHENEY BROTHERS": "CHENEY BROTHERS"}, {}, _ctx())
    check("a run-together body is DETERMINISTIC only when it begins with a proven name",
          corroborated.tier == wr.DETERMINISTIC and corroborated.name == "CHENEY BROTHERS",
          repr(corroborated))
    uncorroborated = wr.corroborate(body, {"CHENEY": "CHENEY"}, {}, _ctx())
    check("a proven prefix matches only on a whole-word boundary",
          uncorroborated.name == "CHENEY"
          and wr.corroborate(body, {"CHEN": "CHEN"}, {}, _ctx()).tier == wr.PROPOSED,
          repr(uncorroborated))
    alone = wr.corroborate(body, {}, {}, _ctx())
    check("without corroboration the body stays PROPOSED", alone.tier == wr.PROPOSED)

    lone = [wr.WhoResult(wr.PROPOSED, wr.F_ACH_MASKED, "ACH_MASKED_BODY",
                         proposed_name="PAYROLL PAYROLL", reference_token="***2111"),
            wr.WhoResult(wr.PROPOSED, wr.F_ACH_MASKED, "ACH_MASKED_BODY",
                         proposed_name="PAYROLL", reference_token="***2111")]
    check("a single generic shared word is never promoted to an identity",
          wr.masked_reference_companies(lone) == {})

    # =================================================================
    # Persistence — throwaway database
    # =================================================================
    url = resolve_test_database_url("bank_who_recognition")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as s:
            own = m.LegalEntity(legal_name="Angeli E Demoni, LLC", status="ACTIVE")
            s.add(own)
            s.flush()
            checking = m.PaymentInstrument(instrument_type="BANK_ACCOUNT", display_name="Checking",
                                           institution="Chase", last_four="3376",
                                           legal_entity_id=own.id)
            saving = m.PaymentInstrument(instrument_type="BANK_ACCOUNT", display_name="Saving",
                                         institution="Chase", last_four="7129",
                                         legal_entity_id=own.id)
            s.add_all([checking, saving])
            s.flush()
            batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="t.csv",
                                      raw_file_bytes=b"x", sha256="0" * 64,
                                      payment_instrument_id=checking.id)
            s.add(batch)
            restaurant = m.Restaurant(name="Test Restaurant")
            s.add(restaurant)
            s.flush()
            s.add(m.Supplier(restaurant_id=restaurant.id, name="Gordon Food Serv"))
            s.add(m.Supplier(restaurant_id=restaurant.id, name="Cheney Bros"))
            s.flush()

            descriptions = [
                ("Zelle payment to Charlize Irizarry JPM99b5p8jv0", -5000),
                ("Zelle payment to Charlize Irizarry JPM99b6fmucj", -7000),
                ("Online Transfer to SAV ...7129 transaction#: 1234567", -10000),
                ("Payment to Chase card ending in 0246 08/03", -3000),
                ("ORIG CO NAME:GORDON FOOD SERV       ORIG ID:1381249848 DESC DATE:       "
                 "CO ENTRY DESCR:AR PAYMENTSEC:CCD    TRACE#:111000015742249", -90000),
                ("ORIG CO NAME:CHENEY BROTHERS       ORIG ID:1 DESC DATE:       "
                 "CO ENTRY DESCR:A/R PAYMNTSEC:CCD    TRACE#:1", -80000),
                ("Zelle payment from ANGELI E DEMONI LLC 23149425230", 20000),
                ("MONTHLY SERVICE FEE", -1500),
                ("Check", -2500),
            ]
            for index, (description, amount) in enumerate(descriptions):
                s.add(m.FinancialTransaction(
                    payment_instrument_id=checking.id, posting_date=POSTING_DATE,
                    transaction_date=POSTING_DATE, description_original=description,
                    amount_minor=amount, status="COMPLETED", classification="UNKNOWN",
                    import_batch_id=batch.id, fingerprint=f"fp{index}:0",
                ))
            s.flush()
            s.commit()

            def financial_hash() -> str:
                digest = hashlib.sha256()
                for row in s.execute(text("SELECT * FROM financial_transactions ORDER BY id")):
                    digest.update(repr(tuple(row)).encode())
                return digest.hexdigest()

            before = financial_hash()
            summary, results = wr.recognize_transactions(s)
            s.commit()
            by_desc = {d: r for (d, _), (_, r) in zip(descriptions, results)}

            check("every transaction gets exactly one recognition row",
                  s.scalar(select(func.count(m.BankWhoRecognition.id))) == len(descriptions))
            check("two Zelle payments to one person are ONE WHO",
                  s.scalar(select(func.count(m.BankOccurrence.id))
                           .where(m.BankOccurrence.canonical_name == "CHARLIZE IRIZARRY")) == 1)
            check("the internal transfer creates no WHO",
                  by_desc[descriptions[2][0]].tier == wr.STRUCTURAL
                  and by_desc[descriptions[2][0]].internal_payment_instrument_id == saving.id)
            check("the payment from RF-One's own legal entity creates no WHO",
                  s.scalar(select(func.count(m.BankOccurrence.id))
                           .where(m.BankOccurrence.canonical_name.like("%ANGELI%"))) == 0)
            check("the unregistered card stays UNRESOLVED",
                  by_desc[descriptions[3][0]].tier == wr.UNRESOLVED)
            check("aliases preserve the source spelling",
                  s.scalar(select(func.count(m.BankOccurrenceAlias.id))) >= 1)

            links = s.execute(
                select(m.BankOccurrence.canonical_name, m.Supplier.name)
                .join(m.BankOccurrenceSupplier, m.BankOccurrenceSupplier.occurrence_id == m.BankOccurrence.id)
                .join(m.Supplier, m.Supplier.id == m.BankOccurrenceSupplier.supplier_id)
            ).all()
            check("a WHO is linked to a Supplier on an exact normalized name",
                  ("GORDON FOOD SERV", "Gordon Food Serv") in links, repr(links))
            check("a merely similar Supplier name is never linked (no fuzzy merge)",
                  not any(name == "Cheney Bros" for _, name in links), repr(links))

            check("recognition wrote no decision row",
                  s.scalar(select(func.count(m.BankTransactionExplanation.id))) == 0)
            check("recognition wrote no allocation",
                  s.scalar(select(func.count(m.BankTransactionAllocation.id))) == 0)
            check("recognition wrote no recognition rule (rules carry a WHY)",
                  s.scalar(select(func.count(m.BankRecognitionRule.id))) == 0)
            check("no BankOccurrence carries a default WHY",
                  s.scalar(select(func.count(m.BankOccurrence.id))
                           .where(m.BankOccurrence.default_transaction_reason_id.is_not(None))) == 0)
            check("not one financial transaction changed", financial_hash() == before)

            occurrences = s.scalar(select(func.count(m.BankOccurrence.id)))
            aliases = s.scalar(select(func.count(m.BankOccurrenceAlias.id)))
            second, _ = wr.recognize_transactions(s)
            s.commit()
            check("second run creates no WHO", second.occurrences_created == 0
                  and s.scalar(select(func.count(m.BankOccurrence.id))) == occurrences)
            check("second run creates no alias", second.aliases_created == 0
                  and s.scalar(select(func.count(m.BankOccurrenceAlias.id))) == aliases)
            check("second run creates or changes no recognition",
                  second.recognitions_created == 0 and second.recognitions_updated == 0
                  and second.recognitions_unchanged == len(descriptions))
            check("second run still changes no financial transaction", financial_hash() == before)
    finally:
        engine.dispose()

    print(f"\n{len(checks_passed)} passed, {len(checks_failed)} failed")
    return 1 if checks_failed else 0


if __name__ == "__main__":
    sys.exit(main())
