"""Review in two queues: To Reconcile and Reconciled (BANK_TWO_STAGE_REVIEW_001).

Proves, on a throwaway database, that:

* /bank/review opens on To Reconcile; both tabs keep month and filters, and
  their counts are right;
* To Reconcile holds only transactions whose WHO is not resolved — a raw
  recognizer proposal is not a resolved WHO — and a transaction leaves it the
  moment its current decision names a WHO: through a Rule (Samuels), a person
  choosing the WHO, or a future import the Rule recognises;
* Reconciled holds every WHO-resolved transaction — incomplete ones first —
  with the real statuses: Automatic (orange, exportable without a click),
  Confirmed (green), Needs review; Confirm and Reopen keep their semantics and
  return to the tab;
* only the selected queue is loaded, quickly, with no Classification rebuild;
* Classification, Configuration, Standards, Export and the WHO/WHY invariant
  are unchanged.

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_two_stage_review_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-two-stage-review-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from sqlalchemy import event, func, select  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import export as export_service  # noqa: E402
from rfone_data_store.bank_reconciliation import receiver_candidates  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.bank_reconciliation import reconciliation_status  # noqa: E402
from rfone_data_store.bank_reconciliation import review_queues  # noqa: E402
from rfone_data_store.bank_reconciliation import row_reconciliation  # noqa: E402
from rfone_data_store.bank_reconciliation import service as bank_service  # noqa: E402
from rfone_data_store.bank_reconciliation import who_recognition as wr  # noqa: E402
from rfone_data_store.bank_reconciliation import why_catalog  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
AUG = date(2026, 8, 12)
JUL = date(2026, 7, 9)
RECOGNIZED = "Recognised by who-v1 from the bank's own text (CARD_MERCHANT). Identity only."
CANONICAL = "Canonical WHO from the WHO/WHY import."
SAMUELS_RULE = "Dove nella descrizione trovi SAMUELS il WHO è Samuels & Son"
STATEMENTS = [0]


@event.listens_for(Engine, "before_cursor_execute")
def _count(*_args, **_kwargs):
    STATEMENTS[0] += 1


def csv(description: str, day: str, amount: str) -> bytes:
    return ("Card,Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
            f"1057,{day},{day},{description},Food,Sale,{amount},\n").encode("utf-8")


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="two_stage", display_name="Two Stage",
                                       password="TwoStageReview123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="two_stage").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        legal = m.LegalEntity(legal_name="Two Stage LLC", status="ACTIVE")
        s.add(legal)
        s.flush()
        entity = m.ReportingEntity(code="RE_TWO_STAGE", name="Two Stage", entity_type="LEGAL",
                                   legal_entity_id=legal.id, status="ACTIVE")
        checking = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                       display_name="Two Stage Checking", institution="CHASE", last_four="0001",
                                       currency="USD")
        s.add_all([entity, checking])
        s.flush()
        card = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                   display_name="Chase Card 1057", institution="CHASE", last_four="1057", currency="USD")
        s.add(card)
        s.flush()
        batch = m.BankImportBatch(detected_format="CHASE_CREDIT_CARD_WITH_CARD", original_file_name="seed.csv",
                                  raw_file_bytes=b"x", sha256="4" * 64, status="NORMALIZED",
                                  payment_instrument_id=card.id)
        s.add(batch)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        food = s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE",
                                                               m.BankTransactionReason.name.ilike("%food%"))
                         .order_by(m.BankTransactionReason.id)).first()

        def who(name, notes=CANONICAL):
            o = m.BankOccurrence(canonical_name=name, occurrence_type_id=counterparty.id, status="ACTIVE",
                                 optional_notes=notes)
            s.add(o)
            s.flush()
            return o

        samuels_fragment = who("SAMUELS AND SON SEAF", notes=RECOGNIZED)
        gordon = who("Gordon Food Service")
        publix = who("Publix")
        sysco = who("Sysco")
        for occurrence in (gordon, publix, sysco):
            why_catalog.associate(s, occurrence_id=occurrence.id, transaction_reason_id=food.id, source="HUMAN")
        seq = [0]

        def tx(description, day=AUG, amount=-1000, *, recognized=None, decision=None, why=None,
               duplicate="NONE", accounting="CANONICAL"):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=card.id, bank_source="CHASE_CREDIT_CARD_WITH_CARD", import_batch_id=batch.id,
                posting_date=day, transaction_date=day, description_original=description,
                description_normalized=description, amount_minor=amount - seq[0], status="COMPLETED",
                duplicate_status=duplicate, review_status="REQUIRES_REVIEW", accounting_status=accounting,
                fingerprint=f"two-stage-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            if recognized is not None:
                s.add(m.BankWhoRecognition(
                    financial_transaction_id=t.id, recognizer_version=wr.RECOGNIZER_VERSION, tier=wr.DETERMINISTIC,
                    family="CARD_MERCHANT", parser_code="CARD_DESCRIPTOR", extracted_name=recognized.canonical_name,
                    occurrence_id=recognized.id, evidence="card statement merchant descriptor"))
            if decision is not None:
                source, occurrence = decision
                recognition._create_decision_row(
                    s, t, occurrence_id=occurrence.id if occurrence else None,
                    transaction_reason_id=why.id if why else None, recognition_rule_id=None,
                    decision_source=source, decision_status="NEEDS_HUMAN_REVIEW",
                    confidence=None, explanation_notes="seed")
            s.flush()
            return t

        rows = {
            "samuels_1": tx("SAMUELS AND SON SEAFOOD - 1001", recognized=samuels_fragment),
            "samuels_2": tx("SAMUELS AND SON SEAFOOD - 1002", recognized=samuels_fragment),
            "samuels_july": tx("SAMUELS AND SON SEAFOOD - 0901", day=JUL, recognized=samuels_fragment),
            "no_who": tx("SOME UNKNOWN PAYEE 4477"),
            "ambiguous": tx("TWO RULES DISAGREE 55", decision=("RULE", None)),
            "who_no_why": tx("GORDON FOOD SERVICE 7788", decision=("RULE", gordon)),
            "confirmed": tx("SYSCO ORLANDO 2211", decision=("RULE", sysco)),
            "standard_source": tx("PUBLIX SUPER MARKETS 0123", decision=("RULE", publix)),
            "candidate_dup": tx("GORDON FOOD SERVICE 7788", decision=("RULE", gordon), duplicate="CANDIDATE_DUPLICATE"),
            "suppressed": tx("SYSCO ORLANDO COPY", accounting="DUPLICATE_SUPPRESSED"),
            "july_other": tx("JULY ONLY VENDOR", day=JUL),
        }
        s.commit()
        # A Confirmed row and a Standard, through the Reconciliation services.
        row_reconciliation.record_who(s, transaction_id=rows["confirmed"].id, occurrence_id=sysco.id,
                                      reason_id=food.id, account_id=operator.id)
        row_reconciliation.confirm_row(s, transaction_id=rows["confirmed"].id, reporting_entity_id=entity.id,
                                       account_id=operator.id)
        row_reconciliation.record_who(s, transaction_id=rows["standard_source"].id, occurrence_id=publix.id,
                                      reason_id=food.id, account_id=operator.id)
        row_reconciliation.set_as_standard(s, transaction_id=rows["standard_source"].id,
                                           reporting_entity_id=entity.id, account_id=operator.id)
        s.commit()
        # A new import the Standard completes: AUTOMATIC.
        upload = bank_service.import_csv(s, file_bytes=csv("PUBLIX SUPER MARKETS 0123", "08/20/2026", "-12.34"),
                                         original_file_name="chase1057_publix.csv", uploaded_by_account_id=None,
                                         payment_instrument_id=card.id)
        s.commit()
        automatic = s.scalars(select(m.FinancialTransaction).where(
            m.FinancialTransaction.import_batch_id == upload.batch.id)).one()
        # The import recomputes accounting deduplication; the synthetic copy is
        # marked suppressed afterwards, the way a real duplicate group ends up.
        suppressed_copy = s.get(m.FinancialTransaction, rows["suppressed"].id)
        suppressed_copy.accounting_status = "DUPLICATE_SUPPRESSED"
        suppressed_copy.accounting_canonical_transaction_id = rows["confirmed"].id
        s.commit()
        ids = {k: t.id for k, t in rows.items()}
        ids.update(automatic=automatic.id, entity=entity.id, gordon=gordon.id, food=food.id)
        statuses = reconciliation_status.statuses_for(s, [s.get(m.FinancialTransaction, i) for i in ids.values()
                                                          if isinstance(i, int) and s.get(m.FinancialTransaction, i)])
        check("setup: one Automatic and one Confirmed row exist",
              statuses.get(ids["automatic"]) == reconciliation_status.AUTOMATIC
              and statuses.get(ids["confirmed"]) == reconciliation_status.CONFIRMED,
              detail=f"{statuses.get(ids['automatic'])} / {statuses.get(ids['confirmed'])}")
        config_before = (
            sorted(s.execute(select(m.BankTransactionReason.id, m.BankTransactionReason.status,
                                    m.BankTransactionReason.accounting_classification_id)).all()),
            sorted(s.execute(select(m.BankAccountingClassification.id, m.BankAccountingClassification.active)).all()),
            sorted(s.execute(select(m.PaymentInstrument.id, m.PaymentInstrument.status)).all()),
            sorted(s.execute(select(m.ReportingEntity.id, m.ReportingEntity.status)).all()),
        )
        standards_before = sorted(s.execute(select(m.BankReconciliationStandard.id,
                                                   m.BankReconciliationStandard.occurrence_id,
                                                   m.BankReconciliationStandard.status)).all())

    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "two_stage", "password": "TwoStageReview123!", "csrf_token": csrf})

    original_build = receiver_candidates.build_candidates

    def forbidden(*_a, **_k):
        raise AssertionError("no receiver candidate rebuild on Review or Classification")

    receiver_candidates.build_candidates = forbidden

    def get(path):
        STATEMENTS[0] = 0
        start = time.perf_counter()
        response = client.get(path)
        return response, time.perf_counter() - start, STATEMENTS[0]

    def in_to_reconcile(html, key):
        return f'data-transaction-id="{ids[key]}"' in html

    def in_reconciled(html, key):
        return f'id="t-{ids[key]}"' in html

    MONTH = "year=2026&month=8"
    default, _, _ = get("/bank/review")
    to_rec, to_rec_time, to_rec_statements = get(f"/bank/review?{MONTH}")
    rec, rec_time, rec_statements = get(f"/bank/review?{MONTH}&view=reconciled")
    to_rec_html, rec_html = to_rec.data.decode(), rec.data.decode()
    check("1. /bank/review opens on To Reconcile",
          'class="review-tab is-active"' in default.data.decode()
          and re.search(r'is-active"[^>]*aria-current="page">To Reconcile', default.data.decode()) is not None)
    check("2. both tabs render", to_rec.status_code == 200 and rec.status_code == 200
          and "To Reconcile (" in rec_html and "Reconciled (" in to_rec_html)
    check("3. the tabs keep the month (and filters) in their links; July rows are not listed in August",
          'href="/bank/review?view=reconciled&amp;year=2026&amp;month=8"' in to_rec_html
          and 'href="/bank/review?view=to_reconcile&amp;year=2026&amp;month=8"' in rec_html
          and not in_to_reconcile(to_rec_html, "samuels_july") and not in_to_reconcile(to_rec_html, "july_other"))
    expected = {"to_reconcile": 5, "reconciled": 4}   # samuels x2, no_who, ambiguous, candidate dup | gordon, sysco, publix, automatic
    check("4. the counts are right and shown on the tabs",
          f"To Reconcile ({expected['to_reconcile']})" in to_rec_html
          and f"Reconciled ({expected['reconciled']})" in to_rec_html,
          detail=re.findall(r"(To Reconcile \(\d+\)|Reconciled \(\d+\))", to_rec_html)[:2].__str__())

    check("5. a transaction with no WHO is To Reconcile", in_to_reconcile(to_rec_html, "no_who"))
    check("6. an ambiguous WHO (rules disagree, decision without WHO) is To Reconcile",
          in_to_reconcile(to_rec_html, "ambiguous"))
    check("6b. a raw recognizer proposal is not a resolved WHO: Samuels is To Reconcile",
          in_to_reconcile(to_rec_html, "samuels_1") and in_to_reconcile(to_rec_html, "samuels_2"))
    check("7. a WHO-resolved transaction is not To Reconcile",
          not in_to_reconcile(to_rec_html, "who_no_why") and in_reconciled(rec_html, "who_no_why"))
    check("8. a Confirmed transaction is not To Reconcile", not in_to_reconcile(to_rec_html, "confirmed"))
    check("9. an Automatic transaction is not To Reconcile", not in_to_reconcile(to_rec_html, "automatic"))
    check("9b. an undecided candidate duplicate stays To Reconcile until its duplicate question is answered",
          in_to_reconcile(to_rec_html, "candidate_dup") and not in_reconciled(rec_html, "candidate_dup"))
    check("9c. a suppressed accounting copy stays visible for audit but needs no work (uncounted, no WHO control)",
          "EXCLUDED FROM ACCOUNTING" in to_rec_html and not in_to_reconcile(to_rec_html, "suppressed"))
    check("26. the Rule action is available on To Reconcile rows",
          re.search(r'class="who-rule-open" data-transaction-id="%d"' % ids["samuels_1"], to_rec_html) is not None
          and 'id="who-rule-modal"' in to_rec_html)

    # ------------------------------------------------------------------
    # RULE FLOW — Samuels (10-15, 27, 28)
    # ------------------------------------------------------------------
    csrf = CSRF_RE.search(to_rec_html).group(1)
    check("10. Samuels initially appears in To Reconcile", in_to_reconcile(to_rec_html, "samuels_1"))
    applied = client.post("/bank/who-rules/apply", headers={"X-Requested-With": "fetch"}, data={
        "csrf_token": csrf, "new_who_name": "Samuels & Son", "instruction": SAMUELS_RULE,
        "transaction_reason_id": [str(ids["food"])], "transaction_id": str(ids["samuels_1"]),
        "return_to": f"/bank/review?{MONTH}"})
    body = applied.get_json()
    check("11/27. the Samuels Rule is applied from To Reconcile, creating the WHO in the same Apply",
          applied.status_code == 200 and body["ok"] and body["redirect"] == f"/bank/review?{MONTH}", detail=str(body))
    after = client.get(body["redirect"]).data.decode()
    with SessionFactory() as s:
        samuels = s.scalars(select(m.BankOccurrence).where(m.BankOccurrence.canonical_name == "Samuels & Son")).one()
        decided = [recognition.get_current_explanation(s, financial_transaction_id=ids[k])
                   for k in ("samuels_1", "samuels_2", "samuels_july")]
        check("12. the WHO is assigned to every Samuels transaction, with no WHY chosen",
              all(d.occurrence_id == samuels.id and d.transaction_reason_id is None for d in decided))
        associations = [a.transaction_reason_id for a in s.scalars(select(m.BankOccurrenceReasonAssociation).where(
            m.BankOccurrenceReasonAssociation.occurrence_id == samuels.id))]
        check("28. possible WHY behaviour unchanged: the chosen WHY is a possible WHY, no default",
              associations == [ids["food"]] and samuels.default_transaction_reason_id is None)
        samuels_id = samuels.id
    check("13. the Samuels transactions disappear from To Reconcile on the reloaded page",
          not in_to_reconcile(after, "samuels_1") and not in_to_reconcile(after, "samuels_2")
          and "To Reconcile (3)" in after)
    check("8b. the result says where they went, with a link to Reconciled",
          "WHO assigned to" in after and "View reconciled transactions" in after
          and 'href="/bank/review?view=reconciled&amp;year=2026&amp;month=8"' in after)
    reconciled_after = client.get(f"/bank/review?{MONTH}&view=reconciled").data.decode()
    check("14. they appear under Reconciled with the WHO populated",
          re.search(r'id="t-%d"[^>]*data-who="%d"' % (ids["samuels_1"], samuels_id), reconciled_after) is not None
          and "Reconciled (6)" in reconciled_after)
    with SessionFactory() as s:
        upload = bank_service.import_csv(s, file_bytes=csv("SAMUELS AND SON SEAFOOD - 1099", "08/25/2026", "-77.00"),
                                         original_file_name="chase1057_samuels.csv", uploaded_by_account_id=None,
                                         payment_instrument_id=ids["automatic"] and s.get(
                                             m.FinancialTransaction, ids["automatic"]).payment_instrument_id)
        s.commit()
        future_id = s.scalars(select(m.FinancialTransaction.id).where(
            m.FinancialTransaction.import_batch_id == upload.batch.id)).one()
    future_rec = client.get(f"/bank/review?{MONTH}&view=reconciled").data.decode()
    future_to = client.get(f"/bank/review?{MONTH}").data.decode()
    check("15. a future matching transaction goes straight to Reconciled",
          f'id="t-{future_id}"' in future_rec and f'data-transaction-id="{future_id}"' not in future_to)

    # ------------------------------------------------------------------
    # MANUAL FLOW (16-18)
    # ------------------------------------------------------------------
    # The one manual path: Select WHO / WHY (BANK_MANUAL_WHO_WHY_001).
    manual = client.post(f"/bank/transactions/{ids['no_who']}/who-why",
                         data={"csrf_token": csrf, "occurrence_id": str(ids["gordon"]),
                               "transaction_reason_id": str(ids["food"]), "return_to": f"/bank/review?{MONTH}"})
    manual_to = client.get(f"/bank/review?{MONTH}").data.decode()
    manual_rec = client.get(f"/bank/review?{MONTH}&view=reconciled").data.decode()
    check("16. the operator chooses the WHO by hand", manual.status_code in (302, 303))
    check("17. the transaction leaves To Reconcile", not in_to_reconcile(manual_to, "no_who"))
    row = re.search(r'<tr id="t-%d"[^>]*>' % ids["no_who"], manual_rec)
    check("18/20. it appears under Reconciled with its WHO and WHY, still to accept (Needs review)",
          row is not None and f'data-why="{ids["food"]}"' in row.group(0) and 'data-status="Needs review"' in row.group(0))

    # ------------------------------------------------------------------
    # RECONCILED (19-25)
    # ------------------------------------------------------------------
    gordon_row = re.search(r'<tr id="t-%d"[^>]*>' % ids["who_no_why"], manual_rec)
    check("19. a WHO-populated, WHY-incomplete row appears", gordon_row is not None
          and 'data-status="Needs review"' in gordon_row.group(0))
    auto_row = re.search(r'<tr id="t-%d".*?</tr>' % ids["automatic"], manual_rec, re.S)
    conf_row = re.search(r'<tr id="t-%d".*?</tr>' % ids["confirmed"], manual_rec, re.S)
    check("21. the Automatic row is marked with the orange check",
          auto_row is not None and "rp-st-automatic" in auto_row.group(0))
    check("22. the Confirmed row is marked with the green check",
          conf_row is not None and "rp-st-confirmed" in conf_row.group(0))
    check("12b. rows still to accept come before the accepted ones",
          manual_rec.index(f'id="t-{ids["who_no_why"]}"') < manual_rec.index(f'id="t-{ids["confirmed"]}"')
          and manual_rec.index(f'id="t-{ids["samuels_1"]}"') < manual_rec.index(f'id="t-{ids["automatic"]}"'))
    with SessionFactory() as s:
        unresolved = {t.id for t in export_service.unresolved_transactions(s, year=2026, month=8)}
    check("23. the Automatic row is exportable without any Confirm",
          ids["automatic"] not in unresolved and ids["confirmed"] not in unresolved
          and ids["who_no_why"] in unresolved)
    with SessionFactory() as s:
        row_reconciliation.record_who(s, transaction_id=ids["who_no_why"], occurrence_id=ids["gordon"],
                                      reason_id=ids["food"], account_id=None)
        s.commit()
    back = f"/bank/review?{MONTH}&view=reconciled"
    confirmed = client.post(f"/bank/reconciliation/{ids['who_no_why']}/confirm", data={
        "csrf_token": csrf, "for_whom_id": str(ids["entity"]), "return_to": back})
    with SessionFactory() as s:
        status_now = reconciliation_status.statuses_for(s, [s.get(m.FinancialTransaction, ids["who_no_why"])])
    check("24. Confirm from Reconciled turns the row Confirmed and returns to the same tab and row",
          confirmed.status_code in (302, 303) and confirmed.headers["Location"].endswith(f"{back}#t-{ids['who_no_why']}")
          and status_now[ids["who_no_why"]] == reconciliation_status.CONFIRMED)
    reopened = client.post(f"/bank/reconciliation/{ids['who_no_why']}/reopen", data={
        "csrf_token": csrf, "return_to": back})
    reopened_page = client.get(back).data.decode()
    with SessionFactory() as s:
        status_now = reconciliation_status.statuses_for(s, [s.get(m.FinancialTransaction, ids["who_no_why"])])
    check("25. Reopen keeps the reconciliation semantics: Needs review, still Reconciled (WHO kept)",
          reopened.status_code in (302, 303) and status_now[ids["who_no_why"]] == reconciliation_status.NEEDS_REVIEW
          and in_reconciled(reopened_page, "who_no_why"))
    offsite = client.post(f"/bank/reconciliation/{ids['who_no_why']}/reopen", data={
        "csrf_token": csrf, "return_to": "https://example.com/bank/review"})
    check("25b. a row action never redirects outside the Review",
          "/bank/review" in offsite.headers["Location"] and "view=reconciled" in offsite.headers["Location"]
          and "example.com" not in offsite.headers["Location"])

    # ------------------------------------------------------------------
    # PERFORMANCE (29-34)
    # ------------------------------------------------------------------
    check("29. only the selected queue's rows are loaded",
          not any(f'id="t-{ids[k]}"' in to_rec_html for k in ("who_no_why", "confirmed", "automatic"))
          and not any(f'data-transaction-id="{ids[k]}"' in rec_html for k in ("no_who", "ambiguous")))
    print(f"  To Reconcile: {to_rec_time:.3f}s, {len(to_rec.data) / 1024:.1f} KB, {to_rec_statements} statements; "
          f"Reconciled: {rec_time:.3f}s, {len(rec.data) / 1024:.1f} KB, {rec_statements} statements")
    check("30. To Reconcile answers quickly with a bounded statement count",
          to_rec_time < 3.0 and to_rec_statements < 150, detail=f"{to_rec_time:.2f}s {to_rec_statements}")
    check("31. Reconciled answers quickly with a bounded statement count",
          rec_time < 3.0 and rec_statements < 80, detail=f"{rec_time:.2f}s {rec_statements}")
    classification, classification_time, _ = get("/bank/classification")
    check("32. no Classification candidate rebuild on Review or Classification (the rebuild is forbidden here)",
          to_rec.status_code == rec.status_code == classification.status_code == 200)
    check("33. no giant HTML", len(to_rec.data) < 600 * 1024 and len(rec.data) < 600 * 1024)
    check("34. Classification remains fast", classification_time < 2.0, detail=f"{classification_time:.2f}s")
    receiver_candidates.build_candidates = original_build

    # ------------------------------------------------------------------
    # REGRESSION (35-38)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        config_after = (
            sorted(s.execute(select(m.BankTransactionReason.id, m.BankTransactionReason.status,
                                    m.BankTransactionReason.accounting_classification_id)).all()),
            sorted(s.execute(select(m.BankAccountingClassification.id, m.BankAccountingClassification.active)).all()),
            sorted(s.execute(select(m.PaymentInstrument.id, m.PaymentInstrument.status)).all()),
            sorted(s.execute(select(m.ReportingEntity.id, m.ReportingEntity.status)).all()),
        )
        check("35. Configuration unchanged", config_after == config_before)
        check("36. Standards unchanged by the Review, the Rule and the queue moves",
              sorted(s.execute(select(m.BankReconciliationStandard.id, m.BankReconciliationStandard.occurrence_id,
                                      m.BankReconciliationStandard.status)).all()) == standards_before)
        in_scope = export_service.in_scope_transactions(s, 2026, 8)
        statuses = reconciliation_status.statuses_for(s, in_scope)
        unresolved = {t.id for t in export_service.unresolved_transactions(s, year=2026, month=8)}
        exportable = {tid for tid, st in statuses.items() if st in reconciliation_status.EXPORTABLE}
        check("37. Export semantics unchanged: exactly the Automatic/Confirmed rows are not blocked",
              exportable and exportable.isdisjoint(unresolved) and ids["automatic"] in exportable)
        check("38. WHO/WHY invariant: no description rule determines purpose; the Rule chose no WHY",
              not s.scalar(select(func.count(m.BankRecognitionRule.id)).where(
                  m.BankRecognitionRule.match_field == recognition.DESCRIPTION,
                  m.BankRecognitionRule.determines_purpose.is_(True)))
              and recognition.get_current_explanation(s, financial_transaction_id=ids["samuels_2"]).transaction_reason_id is None)
        counts = review_queues.counts(s, review_queues.ReviewFilters(year=2026, month=8))
        check("4b. the service counts equal the listed rows",
              counts[review_queues.RECONCILED] == len(review_queues.queue(
                  s, review_queues.RECONCILED, review_queues.ReviewFilters(year=2026, month=8))))

    # ------------------------------------------------------------------
    # The batched internal-transfer candidates equal the per-row ones
    # ------------------------------------------------------------------
    from datetime import timedelta
    from rfone_data_store.bank_reconciliation import matching
    with SessionFactory() as s:
        card_id = s.get(m.FinancialTransaction, ids["automatic"]).payment_instrument_id
        checking_id = s.scalars(select(m.PaymentInstrument.id).where(
            m.PaymentInstrument.display_name == "Two Stage Checking")).one()

        def plain(instrument_id, day, amount, tag):
            t = m.FinancialTransaction(
                payment_instrument_id=instrument_id, bank_source="CHASE_BANK_ACCOUNT", posting_date=day,
                transaction_date=day, description_original=f"TRANSFER {tag}", description_normalized=f"TRANSFER {tag}",
                amount_minor=amount, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                accounting_status="CANONICAL", fingerprint=f"transfer-{tag}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            return t

        base = date(2026, 8, 15)
        out = plain(checking_id, base, -50000, "out")
        plain(card_id, base + timedelta(days=2), 50000, "in-window")
        plain(card_id, base + timedelta(days=9), 50000, "out-of-window")
        plain(checking_id, base, 50000, "same-instrument")
        matched_a = plain(checking_id, base, -70000, "matched-a")
        matched_b = plain(card_id, base, 70000, "matched-b")
        s.add(m.FinancialTransactionMatch(transaction_a_id=matched_a.id, transaction_b_id=matched_b.id,
                                          match_method="HUMAN", match_basis="test", matched_amount_minor=70000))
        third = plain(card_id, base, 70000, "second-candidate")
        s.flush()
        pool = s.scalars(select(m.FinancialTransaction).where(
            m.FinancialTransaction.description_original.like("TRANSFER %"))).all()
        one = {t.id: [c.id for c in matching.find_cross_ledger_candidates(s, t, require_linked_instrument=False)]
               for t in pool}
        one = {k: v for k, v in one.items() if v}
        many = {k: [c.id for c in v] for k, v in matching.find_cross_ledger_candidates_for_many(
            s, pool, require_linked_instrument=False).items()}
        check("29b. the batched transfer candidates equal the per-row ones (window, instrument, already matched)",
              one == many and out.id in one and third.id in one[matched_a.id], detail=f"{one} vs {many}")
        s.rollback()

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
