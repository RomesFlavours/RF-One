"""General (structural) WHO rules (BANK_GENERAL_RULES_001).

Proves, on a throwaway database migrated to head, that:

* Classification shows GENERAL RULES before WHO CLASSIFICATION, with the
  seeded "Chase ACH — ORIG CO NAME" rule; rules are created, edited,
  deactivated from the page;
* the between-markers extraction: the Chase example gives MERCHANT BANKCD,
  different descriptions give different candidates, markers are
  case-insensitive, whitespace is trimmed, a missing marker or an empty value
  gives nothing;
* Apply resolves a candidate only through the canonical resolver (name,
  alias, approved rule), never creates a WHO, leaves an unknown candidate To
  Reconcile as a suggested WHO, moves a resolved one to Reconciled with its
  WHY untouched, and never overwrites a HUMAN, Standard or other existing WHO;
* a future import uses the same General Rule; the level-2 WHO Rule is
  unchanged; Classification stays fast.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import time
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_general_rules_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-general-rules-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from sqlalchemy import func, select  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import general_rules  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.bank_reconciliation import review_queues  # noqa: E402
from rfone_data_store.bank_reconciliation import row_reconciliation  # noqa: E402
from rfone_data_store.bank_reconciliation import why_catalog  # noqa: E402
from rfone_data_store.bank_reconciliation import service as bank_service  # noqa: E402
from rfone_data_store.bank_reconciliation import who_recognition as wr  # noqa: E402
from rfone_data_store.bank_reconciliation import who_rules  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
AUG = date(2026, 8, 12)
CHASE = ("ORIG CO NAME:MERCHANT BANKCD ORIG ID:G592126793 DESC DATE:260919 CO ENTRY DESCR:DEPOSIT SEC:CCD "
         "TRACE#:041001036172233 EED:260921 IND ID:496170610885 IND NAME:ROME'S FLAVOURS TRN: 2646172233TC")
S, E = "ORIG CO NAME:", "ORIG ID:"


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    # ------------------------------------------------------------------
    # EXTRACTION (5-11) — the pure function
    # ------------------------------------------------------------------
    x = general_rules.extract
    check("5. the Chase example extracts MERCHANT BANKCD", x(CHASE, S, E) == "MERCHANT BANKCD", x(CHASE, S, E))
    check("6. different descriptions give different candidates",
          x("ORIG CO NAME:TABLE TOP LINEN ORIG ID:123...", S, E) == "TABLE TOP LINEN"
          and x("ORIG CO NAME:ADP PAYROLL ORIG ID:9", S, E) == "ADP PAYROLL")
    check("7. markers are case-insensitive (the value keeps its own case)",
          x("orig co name:Acme Supplies orig id:1", S, E) == "Acme Supplies")
    check("8. whitespace is trimmed and collapsed", x("ORIG CO NAME:   GORDON   FOOD SERV      ORIG ID:1", S, E)
          == "GORDON FOOD SERV")
    check("9. a missing start marker gives nothing", x("NO NAME HERE ORIG ID:1", S, E) is None)
    check("10. a missing end marker gives nothing", x("ORIG CO NAME:ADP PAYROLL", S, E) is None)
    check("11. an empty extraction gives nothing", x("ORIG CO NAME:    ORIG ID:1", S, E) is None)

    # ------------------------------------------------------------------
    # DATA
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        account_service.create_account(s, username="general_rules", display_name="General Rules",
                                       password="GeneralRules123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="general_rules").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        legal = m.LegalEntity(legal_name="General Rules LLC", status="ACTIVE")
        s.add(legal)
        s.flush()
        entity = m.ReportingEntity(code="RE_GENERAL", name="General Rules", entity_type="LEGAL",
                                   legal_entity_id=legal.id, status="ACTIVE")
        checking = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                       display_name="General Checking", institution="CHASE", last_four="0099",
                                       currency="USD")
        s.add_all([entity, checking])
        s.flush()
        batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="seed.csv",
                                  raw_file_bytes=b"x", sha256="8" * 64, status="NORMALIZED",
                                  payment_instrument_id=checking.id)
        s.add(batch)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        food = s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.code == "FOOD_PURCHASES")).one()

        def who(name):
            o = m.BankOccurrence(canonical_name=name, occurrence_type_id=counterparty.id, status="ACTIVE",
                                 optional_notes="Canonical WHO.")
            s.add(o)
            s.flush()
            return o

        merchant = who("MERCHANT BANKCD")
        gordon = who("Gordon Food Service")
        s.add(m.BankOccurrenceAlias(occurrence_id=gordon.id, alias_text="GORDON FOOD SERV",
                                    alias_key=wr.who_key("GORDON FOOD SERV"), source_family="ACH_ORIGINATOR",
                                    source="PARSER"))
        ttl = who("Table Top Linen")
        other = who("Somebody Else")
        seq = [0]

        def tx(description, *, decision=None, why=None, source="RULE", standard=None):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", import_batch_id=batch.id,
                posting_date=AUG, transaction_date=AUG, description_original=description,
                description_normalized=description, amount_minor=-1000 - seq[0], status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"general-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            if decision is not None or why is not None:
                recognition._create_decision_row(
                    s, t, occurrence_id=decision.id if decision else None, transaction_reason_id=why.id if why else None,
                    recognition_rule_id=None, decision_source=source, decision_status="NEEDS_HUMAN_REVIEW",
                    confidence=None, explanation_notes="seed", accounting_classification_id=why.accounting_classification_id if why else None,
                    reconciliation_standard_id=standard,
                    accounting_destination_source=(m.DESTINATION_SOURCE_STANDARD if standard
                                                   else m.DESTINATION_SOURCE_WHY))
            s.flush()
            return t

        rows = {
            "chase": tx(CHASE, why=food),                                                   # canonical name, has a WHY
            "alias": tx("ORIG CO NAME:GORDON FOOD SERV       ORIG ID:1381249848 DESC DATE:"),  # alias
            "unknown": tx("ORIG CO NAME:XYZ PAYMENTS ORIG ID:77 DESC DATE:"),               # unknown
            "human": tx("ORIG CO NAME:MERCHANT BANKCD ORIG ID:5", decision=other, why=food, source="HUMAN"),
            "other_who": tx("ORIG CO NAME:MERCHANT BANKCD ORIG ID:6", decision=other),
            "plain": tx("SOME CARD PURCHASE 123"),
        }
        s.commit()
        # A Standard-protected decision needs a real Standard: made, as in the
        # product, from a row a person gave WHO + WHY.
        std_source = tx("STANDARD SOURCE ROW")
        why_catalog.associate(s, occurrence_id=other.id, transaction_reason_id=food.id, source="HUMAN")
        row_reconciliation.record_who(s, transaction_id=std_source.id, occurrence_id=other.id, reason_id=food.id,
                                      account_id=None)
        standard = row_reconciliation.set_as_standard(s, transaction_id=std_source.id, reporting_entity_id=entity.id,
                                                      account_id=None)
        s.commit()
        rows["standard"] = tx("ORIG CO NAME:MERCHANT BANKCD ORIG ID:7", decision=other, why=food, standard=standard.id)
        s.commit()
        ids = {k: t.id for k, t in rows.items()}
        ids.update(merchant=merchant.id, gordon=gordon.id, ttl=ttl.id, other=other.id, food=food.id,
                   checking=checking.id)
        who_before = s.scalar(select(func.count(m.BankOccurrence.id)))
        rules_before = sorted(s.execute(select(m.BankRecognitionRule.id, m.BankRecognitionRule.normalized_pattern,
                                               m.BankRecognitionRule.occurrence_id)).all())

    def decision(key):
        with SessionFactory() as s:
            e = recognition.get_current_explanation(s, financial_transaction_id=ids[key])
            return (e.occurrence_id, e.transaction_reason_id, e.decision_source) if e else None

    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "general_rules", "password": "GeneralRules123!", "csrf_token": csrf})

    # ------------------------------------------------------------------
    # PAGE (1-4)
    # ------------------------------------------------------------------
    started = time.perf_counter()
    page = client.get("/bank/classification")
    page_secs = time.perf_counter() - started
    html = page.data.decode()
    check("1. GENERAL RULES appears before WHO CLASSIFICATION",
          page.status_code == 200 and 0 < html.index('id="general-rules"') < html.index('id="who-classification"'))
    check("3. the seeded Chase rule is shown: name, between-markers extraction, active",
          "Chase ACH — ORIG CO NAME" in html and "ORIG CO NAME:</code>" in html and "ORIG ID:</code>" in html
          and "+ New General Rule" in html and "Apply to Existing Transactions" in html)
    csrf = CSRF_RE.search(html).group(1)
    saved = client.post("/bank/general-rules/save", data={
        "csrf_token": csrf, "name": "Test PPD", "start_marker": "PPD NAME:", "end_marker": "PPD ID:", "active": "on"})
    with SessionFactory() as s:
        created = s.scalars(select(m.BankGeneralRule).where(m.BankGeneralRule.name == "Test PPD")).one_or_none()
        created_id = created.id if created else None
        created_fields = (created.start_marker, created.end_marker, created.status) if created else None
    check("2. a new General Rule is created from the page (markers saved)",
          saved.status_code == 302 and created_fields == ("PPD NAME:", "PPD ID:", "ACTIVE"), str(created_fields))
    bad = client.post("/bank/general-rules/save", data={"csrf_token": csrf, "name": "Bad", "start_marker": "X:",
                                                        "end_marker": ""})
    with SessionFactory() as s:
        bad_saved = s.scalar(select(func.count(m.BankGeneralRule.id)).where(m.BankGeneralRule.name == "Bad"))
    check("2b. a rule without both markers is refused", bad.status_code == 302 and bad_saved == 0)
    client.post(f"/bank/general-rules/{created_id}/status", data={"csrf_token": csrf, "active": "0"})
    with SessionFactory() as s:
        status_off = s.get(m.BankGeneralRule, created_id).status
        active_names = [r.name for r in general_rules.active_rules(s)]
    client.post(f"/bank/general-rules/{created_id}/status", data={"csrf_token": csrf, "active": "1"})
    with SessionFactory() as s:
        status_on = s.get(m.BankGeneralRule, created_id).status
    check("4. active / inactive works (an inactive rule is not used)",
          status_off == "INACTIVE" and "Test PPD" not in active_names and status_on == "ACTIVE")

    # ------------------------------------------------------------------
    # APPLY (12-19)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        chase_rule = s.scalars(select(m.BankGeneralRule).where(m.BankGeneralRule.start_marker == S)).one()
        chase_id = chase_rule.id
        to_rec_before = {t.id for t in review_queues.queue(s, review_queues.TO_RECONCILE, review_queues.ReviewFilters())}
    with SessionFactory() as s:
        decisions_before = s.scalar(select(func.count(m.BankTransactionExplanation.id)))
    client.post(f"/bank/general-rules/{chase_id}/preview", data={"csrf_token": csrf})
    preview_page = client.get("/bank/classification").data.decode()
    with SessionFactory() as s:
        decisions_after_preview = s.scalar(select(func.count(m.BankTransactionExplanation.id)))
    check("4b. Preview shows what Apply would do and writes nothing",
          decisions_after_preview == decisions_before and "nothing was written" in preview_page
          and "XYZ PAYMENTS" in preview_page and decision("chase")[0] is None)
    applied = client.post(f"/bank/general-rules/{chase_id}/apply", data={"csrf_token": csrf})
    result_page = client.get("/bank/classification").data.decode()
    with SessionFactory() as s:
        who_after = s.scalar(select(func.count(m.BankOccurrence.id)))
        to_rec = {t.id for t in review_queues.queue(s, review_queues.TO_RECONCILE, review_queues.ReviewFilters())}
        reconciled = {t.id for t in review_queues.queue(s, review_queues.RECONCILED, review_queues.ReviewFilters())}
    check("12. a candidate that is a canonical WHO name resolves (Chase -> MERCHANT BANKCD)",
          decision("chase")[0] == ids["merchant"], str(decision("chase")))
    check("13. a candidate that is an alias resolves to its canonical WHO (GORDON FOOD SERV -> Gordon Food Service)",
          decision("alias")[0] == ids["gordon"], str(decision("alias")))
    check("14. an unknown candidate creates no WHO", who_after == who_before and decision("unknown") is None)
    check("15. an unknown candidate stays To Reconcile and is listed as a suggested WHO",
          ids["unknown"] in to_rec and "XYZ PAYMENTS" in result_page and "Suggested WHO" in result_page)
    check("16. a resolved candidate moves to Reconciled",
          ids["chase"] in to_rec_before and ids["chase"] in reconciled and ids["alias"] in reconciled)
    check("17. the WHY is unchanged (Chase keeps Food Purchases; no WHY is chosen where there was none)",
          decision("chase")[1] == ids["food"] and decision("alias")[1] is None)
    check("18. a HUMAN decision is protected", decision("human") == (ids["other"], ids["food"], "HUMAN"))
    check("19. a Standard-protected decision and another existing WHO are not overwritten",
          decision("standard")[0] == ids["other"] and decision("other_who")[0] == ids["other"])
    check("14b. the result reports scanned / matches / resolved / assigned / unknown / protected",
          applied.status_code == 302 and all(t in result_page for t in (
              "Transactions scanned", "Structured matches", "Distinct WHO candidates", "Resolved to canonical WHO",
              "Transactions newly assigned", "Already resolved", "Unknown candidates", "Protected conflicts"))
          and re.search(r"Protected conflicts</dt><dd>3", result_page) is not None,
          str(re.findall(r"Protected conflicts</dt><dd>[^<]*", result_page)))
    again = client.post(f"/bank/general-rules/{chase_id}/apply", data={"csrf_token": csrf})
    again_page = client.get("/bank/classification").data.decode()
    check("14c. Apply is idempotent", re.search(r"Transactions newly assigned</dt><dd>0", again_page) is not None)

    # ------------------------------------------------------------------
    # FUTURE IMPORT (20) and level-2 Rule (21)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        result = who_rules.apply_who_rule(s, occurrence_id=ids["ttl"],
                                          instruction="Dove nella descrizione trovi TABLE TOP LINEN il WHO è Table Top Linen")
        s.commit()
        csv_bytes = ("Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
                     "DEBIT,08/20/2026,ORIG CO NAME:MERCHANT BANKCD ORIG ID:G1 DESC DATE:260820,-12.00,ACH_DEBIT,100.00,\n"
                     "DEBIT,08/21/2026,ORIG CO NAME:NEW VENDOR ZZ ORIG ID:G2 DESC DATE:260821,-13.00,ACH_DEBIT,87.00,\n"
                     "DEBIT,08/22/2026,ORIG CO NAME:TABLE TOP LINEN ORIG ID:G3 DESC DATE:260822,-14.00,ACH_DEBIT,73.00,\n"
                     ).encode()
        upload = bank_service.import_csv(s, file_bytes=csv_bytes, original_file_name="chase0099_general.csv",
                                         uploaded_by_account_id=None, payment_instrument_id=ids["checking"])
        s.commit()
        imported = {t.description_original.split("ORIG ID")[0]: t for t in s.scalars(
            select(m.FinancialTransaction).where(m.FinancialTransaction.import_batch_id == upload.batch.id))}
        whos = {k: (recognition.get_current_explanation(s, financial_transaction_id=t.id).occurrence_id) for k, t in imported.items()}
        who_after_import = s.scalar(select(func.count(m.BankOccurrence.id)))
        rules_after = sorted(s.execute(select(m.BankRecognitionRule.id, m.BankRecognitionRule.normalized_pattern,
                                              m.BankRecognitionRule.occurrence_id)).all())
    check("20. a future import uses the same General Rule (known -> WHO, unknown -> none, no WHO created)",
          whos.get("ORIG CO NAME:MERCHANT BANKCD ") == ids["merchant"] and whos.get("ORIG CO NAME:NEW VENDOR ZZ ") is None
          and who_after_import == who_after, str(whos))
    check("21. level-2 WHO Rules are unchanged and still win (TABLE TOP LINEN rule -> Table Top Linen)",
          whos.get("ORIG CO NAME:TABLE TOP LINEN ") == ids["ttl"] and result.rule_created
          and [r for r in rules_after if r not in rules_before] and all(r in rules_after for r in rules_before))
    check("22. Classification stays fast", page_secs < 2.0, f"{page_secs:.2f}s")

    print()
    print(f"{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            from db import _engine
            _engine.dispose()
            os.remove(_TEST_DB_PATH)
        except Exception:  # noqa: BLE001 — best-effort cleanup of the throwaway file
            pass
