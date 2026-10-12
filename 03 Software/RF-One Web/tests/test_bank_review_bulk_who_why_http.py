"""To Reconcile: tick rows, one WHO + WHY for all of them (BANK_REVIEW_BULK_WHO_WHY_001).

Proves, on a throwaway database, that `POST /bank/transactions/who-why/bulk`:

* records the same WHO and WHY on every ticked transaction — and only them —
  as single HUMAN decisions (WHAT from the WHY), each keeping its own For
  Whom, with no rule created;
* is idempotent: the same request again writes nothing;
* refuses the WHOLE request, naming each transaction and why, when one of
  them changed since the dialog opened, is no longer To Reconcile, is a
  possible duplicate still to decide or has a For Whom split into lines —
  nothing is saved; invalid WHO / WHY, an empty selection and a post
  without CSRF are refused too;
* the page offers the ticks on To Reconcile only.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_bulk_who_why_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-bulk-who-why-secret"

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
from rfone_data_store.bank_reconciliation import economic_allocation  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
AUG = date(2026, 8, 12)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    try:
        with SessionFactory() as s:
            account_service.create_account(s, username="bulk", display_name="Bulk",
                                           password="BulkPass123!", status="ACTIVE", is_admin=False)
            s.flush()
            operator = s.query(m.RFOneAccount).filter_by(username="bulk").one()
            account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True,
                                              role_code=None)
            legal = m.LegalEntity(legal_name="Bulk LLC", status="ACTIVE")
            s.add(legal)
            s.flush()
            entity_a = m.ReportingEntity(code="RE_A", name="Entity A", entity_type="LEGAL",
                                         legal_entity_id=legal.id, status="ACTIVE")
            legal_b = m.LegalEntity(legal_name="Bulk B LLC", status="ACTIVE")
            s.add(legal_b)
            s.flush()
            entity_b = m.ReportingEntity(code="RE_B", name="Entity B", entity_type="LEGAL",
                                         legal_entity_id=legal_b.id, status="ACTIVE")
            checking = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                           display_name="Bulk Checking", institution="CHASE", last_four="0055",
                                           currency="USD")
            s.add_all([entity_a, entity_b, checking])
            s.flush()
            batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="seed.csv",
                                      raw_file_bytes=b"x", sha256="3" * 64, status="NORMALIZED",
                                      payment_instrument_id=checking.id)
            s.add(batch)
            s.flush()
            counterparty = s.scalars(select(m.BankOccurrenceType).where(
                m.BankOccurrenceType.code == "COUNTERPARTY")).one()
            who = m.BankOccurrence(canonical_name="Delta Airlines", occurrence_type_id=counterparty.id, status="ACTIVE")
            s.add(who)
            s.flush()
            why = s.scalars(select(m.BankTransactionReason).where(
                m.BankTransactionReason.status == "ACTIVE",
                m.BankTransactionReason.accounting_classification_id.is_not(None))
                .order_by(m.BankTransactionReason.id)).first()
            seq = [0]

            def tx(description, dup="NONE"):
                seq[0] += 1
                t = m.FinancialTransaction(
                    payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", import_batch_id=batch.id,
                    posting_date=AUG, transaction_date=AUG, description_original=description,
                    description_normalized=description, amount_minor=-1000 - seq[0], status="COMPLETED",
                    duplicate_status=dup, review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                    fingerprint=f"bulk-{seq[0]}", classification="UNKNOWN")
                s.add(t)
                s.flush()
                return t

            rows = {k: tx(f"FLIGHT {k.upper()}") for k in ("t1", "t2", "t3", "t4", "t5", "t6")}
            rows["dup"] = tx("FLIGHT DUP", dup="CANDIDATE_DUPLICATE")
            rows["split"] = tx("FLIGHT SPLIT")
            for key, entity in (("t2", entity_a), ("t3", entity_b)):
                economic_allocation.set_allocations(s, financial_transaction_id=rows[key].id, specs=[
                    economic_allocation.AllocationSpec(amount_minor=rows[key].amount_minor,
                                                       reporting_entity_id=entity.id,
                                                       status=m.ALLOCATION_NEEDS_OPERATOR, decision_source="HUMAN")])
            half = rows["split"].amount_minor // 2
            economic_allocation.set_allocations(s, financial_transaction_id=rows["split"].id, specs=[
                economic_allocation.AllocationSpec(amount_minor=half, reporting_entity_id=entity_a.id,
                                                   status=m.ALLOCATION_NEEDS_OPERATOR, decision_source="HUMAN"),
                economic_allocation.AllocationSpec(amount_minor=rows["split"].amount_minor - half,
                                                   reporting_entity_id=entity_b.id,
                                                   status=m.ALLOCATION_NEEDS_OPERATOR, decision_source="HUMAN")])
            s.commit()
            ids = {k: t.id for k, t in rows.items()}
            ids.update(who=who.id, why=why.id, what=why.accounting_classification_id,
                       entity_a=entity_a.id, entity_b=entity_b.id)

        def state(key):
            with SessionFactory() as s:
                t = s.get(m.FinancialTransaction, ids[key])
                e = recognition.get_current_explanation(s, financial_transaction_id=t.id)
                allocs = economic_allocation.get_allocations(s, financial_transaction_id=t.id)
                return {"expl": t.explanation_id, "who": e.occurrence_id if e else None,
                        "why": e.transaction_reason_id if e else None,
                        "what": e.accounting_classification_id if e else None,
                        "source": e.decision_source if e else None,
                        "for_whom": [a.reporting_entity_id for a in allocs]}

        def counts():
            with SessionFactory() as s:
                return (s.scalar(select(func.count(m.BankTransactionExplanation.id))),
                        s.scalar(select(func.count(m.BankRecognitionRule.id))))

        client = web_app.app.test_client()
        csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
        client.post("/login", data={"username": "bulk", "password": "BulkPass123!", "csrf_token": csrf})
        page = client.get("/bank/review?year=2026&month=8").data.decode()
        csrf = CSRF_RE.search(page).group(1)
        reconciled = client.get("/bank/review?view=reconciled&year=2026&month=8").data.decode()
        check("1. To Reconcile: a tick on each row, the selection bar and the bulk route; not on Reconciled",
              page.count('class="review-select"') == 8 and 'id="review-selection"' in page
              and ">Clear selection</button>" in page and 'data-bulk-url="/bank/transactions/who-why/bulk"' in page
              and 'class="review-select"' not in reconciled)

        def bulk(keys, *, seen=None, who_id=None, why_id=None, with_csrf=True):
            data = {"occurrence_id": str(who_id or ids["who"]), "transaction_reason_id": str(why_id or ids["why"]),
                    "return_to": "/bank/review?year=2026&month=8&q=flight",
                    "seen": [f"{ids[k]}:{(seen or {}).get(k, state(k)['expl']) or ''}" for k in keys]}
            if with_csrf:
                data["csrf_token"] = csrf
            resp = client.post("/bank/transactions/who-why/bulk", data=data, headers={"X-Requested-With": "fetch"})
            return resp, resp.get_json() or {}

        t4_before, before = state("t4"), counts()
        resp, body = bulk(["t1", "t2", "t3"])
        after = counts()
        check("2. the three ticked transactions get the WHO and the WHY as HUMAN decisions; WHAT from the WHY",
              body.get("ok") and body["updated"] == 3
              and all((state(k)["who"], state(k)["why"], state(k)["what"], state(k)["source"])
                      == (ids["who"], ids["why"], ids["what"], "HUMAN") for k in ("t1", "t2", "t3")),
              str([state(k) for k in ("t1", "t2", "t3")]))
        check("3. the fourth (not ticked) is unchanged; no rule created",
              state("t4") == t4_before and after[1] == before[1] and after[0] == before[0] + 3)
        check("4. each keeps its own For Whom", state("t2")["for_whom"] == [ids["entity_a"]]
              and state("t3")["for_whom"] == [ids["entity_b"]] and state("t1")["for_whom"] == [], str(
                  (state("t2"), state("t3"))))
        check("5. back to the page with its search", body.get("redirect") == "/bank/review?year=2026&month=8&q=flight")
        resp, body = bulk(["t1", "t2", "t3"], seen={"t1": None, "t2": None, "t3": None})
        check("6. the same request again (double click / replay) writes nothing",
              body.get("ok") and body["updated"] == 0 and body["already"] == 3 and counts() == after)

        # ------------------------------------------------- refusals: all or none
        def refused(keys, needle, **kw):
            snap = counts()
            states = {k: state(k) for k in keys}
            resp, body = bulk(keys, **kw)
            return (resp.status_code == 400 and needle in body.get("error", "") and counts() == snap
                    and all(state(k) == states[k] for k in keys)), body.get("error", "")

        ok, err = refused(["t5", "t6"], "changed after the dialog was opened", seen={"t6": 999999})
        check("7. a row whose classification changed since the dialog opened refuses ALL (nothing saved)", ok, err)
        ok, err = refused(["t5", "split"], "split into several lines")
        check("8. a For Whom split into lines refuses all, naming the transaction", ok and f"#{ids['split']}" in err, err)
        ok, err = refused(["t5", "dup"], "possible duplicate still to decide")
        check("9. a possible duplicate still to decide refuses all", ok, err)
        with SessionFactory() as s:
            other_why = s.scalars(select(m.BankTransactionReason.id).where(
                m.BankTransactionReason.status == "ACTIVE", m.BankTransactionReason.id != ids["why"])).first()
        ok, err = refused(["t5", "t1"], "no longer To Reconcile", why_id=other_why)
        check("10. a row no longer To Reconcile refuses all", ok, err)
        resp, body = bulk(["t5"], why_id=999999)
        check("11. an invalid WHY is refused", resp.status_code == 400 and "WHY" in body.get("error", ""))
        resp = client.post("/bank/transactions/who-why/bulk", data={
            "csrf_token": csrf, "occurrence_id": str(ids["who"]), "transaction_reason_id": str(ids["why"])},
            headers={"X-Requested-With": "fetch"})
        check("12. an empty selection is refused", resp.status_code == 400)
        resp, body = bulk(["t5"], with_csrf=False)
        check("13. refused without CSRF", resp.status_code in (400, 403) and state("t5")["who"] is None)
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    if failed:
        print("FAILED CHECKS:")
        for description in failed:
            print(f"  - {description}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
