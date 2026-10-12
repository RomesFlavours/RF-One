#!/usr/bin/env python
"""HTTP test for the Monthly Accountant Export page
(BANK_EXPORT_ACTIONABLE_BLOCKERS_001).

The page summarises the month's status and groups what blocks the export by
what fixes it — Source issues, Transactions to reconcile, Reconciled but not
ready, Other — each with an action that keeps the month; a group's
transactions are listed only on request. Whether the month may be exported
is still decided by `export.compute_export_blockers` alone. Import refuses a
file whose own Source cannot be identified; a missing EXPECTED Source stays
a warning.

Runs against a DISPOSABLE SQLite database created here and deleted at the end.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import sys
import tempfile
from datetime import date
from urllib.parse import parse_qs, urlparse

import html as html_lib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_export_blockers_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "export-blockers-test-secret"
_STAGING_DIR = tempfile.mkdtemp(prefix="rfoneweb_export_blockers_staging_")

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import openpyxl  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import configuration as config_service  # noqa: E402
from rfone_data_store.bank_reconciliation import export as export_service  # noqa: E402
from rfone_data_store.bank_reconciliation import export_readiness  # noqa: E402
from rfone_data_store.bank_reconciliation import import_preview  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.bank_reconciliation import reconciliation_standards  # noqa: E402
from rfone_data_store.bank_reconciliation import row_reconciliation  # noqa: E402
from rfone_data_store.bank_reconciliation import service as bank_service  # noqa: E402

web_app.app.config["BANK_IMPORT_STAGING_DIR"] = _STAGING_DIR

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
STAGED_RE = re.compile(r"(?:staged=|/bank/import/)([0-9a-f]{32})")
HEADER = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
JULY = "/bank/export?year=2026&month=7"
JUNE = "/bank/export?year=2026&month=6"


def chase_csv(*rows: str) -> bytes:
    return (HEADER + "".join(rows)).encode("utf-8")


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}"
              + ("" if condition or not detail else f"   [{str(detail)[:300]}]"))

    try:
        # ------------------------------------------------------------ fixture
        ids: dict[str, int] = {}
        with SessionFactory() as db:
            account_service.create_account(db, username="ex_operator", display_name="ex_operator",
                                           password="OperatorPass123!", status="ACTIVE", is_admin=False)
            db.commit()
            operator = db.query(m.RFOneAccount).filter_by(username="ex_operator").one()
            account_service.set_domain_access(db, account_id=operator.id, domain_code="BANK",
                                              enabled=True, role_code=None)
            wp = config_service.create_entity(db, name="Rome's Flavours WP", legal_name="Rome's Flavours WP, LLC")
            checking = m.PaymentInstrument(display_name="RFWP-Checking", instrument_type="BANK_ACCOUNT",
                                           institution="CHASE", last_four="3376",
                                           legal_entity_id=wp.legal_entity_id, status="ACTIVE")
            savings = m.PaymentInstrument(display_name="RFWP-Savings", instrument_type="BANK_ACCOUNT",
                                          institution="CHASE", last_four="5512",
                                          legal_entity_id=wp.legal_entity_id, status="ACTIVE")
            db.add_all([checking, savings])
            db.flush()
            why = db.scalars(select(m.BankTransactionReason).where(
                m.BankTransactionReason.status == "ACTIVE",
                m.BankTransactionReason.accounting_classification_id.is_not(None),
            ).order_by(m.BankTransactionReason.id)).first()
            gfs = config_service.save_who(db, occurrence_id=None, name="Gordon Food Service", active=True,
                                          reason_ids=[why.id], default_reason_id=why.id,
                                          reporting_entity_ids=[], rules=[])

            def txn(day, text, minor, month=7):
                t = m.FinancialTransaction(
                    payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT",
                    posting_date=date(2026, month, day), description_original=text, description_normalized=text,
                    amount_minor=minor, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW")
                db.add(t)
                db.flush()
                return t

            def decide(t):
                recognition.record_human_decision(db, recognition.HumanDecisionRequest(
                    transaction_id=t.id, occurrence_id=gfs.id, transaction_reason_id=why.id,
                    confirmed_by_account_id=operator.id, learn_description=False))

            t_open1 = txn(3, "ZELLE PAYMENT TO MARIA LOPEZ", -30000)        # To Reconcile
            t_open2 = txn(4, "ONLINE TRANSFER 99812", -12000)               # To Reconcile
            t_review = txn(5, "GORDON FOOD SERVICE #1 ORLANDO", -10000)     # Reconciled, Needs review
            t_conf = txn(6, "GORDON FOOD SERVICE #2 ORLANDO", -20000)       # Confirmed
            t_auto = txn(7, "GORDON FOOD SERVICE WEEKLY 7731", -40000)      # Automatic
            t_june = txn(9, "GORDON FOOD SERVICE #3 ORLANDO", -5000, month=6)  # June: Confirmed
            db.commit()
            for t in (t_review, t_conf, t_june):
                decide(t)
            db.commit()
            for t in (t_conf, t_june):
                row_reconciliation.confirm_row(db, transaction_id=t.id, reporting_entity_id=wp.id,
                                               account_id=operator.id)
            standard, _ = reconciliation_standards.create_or_reuse(
                db, signature=reconciliation_standards.signature_for(db, t_auto),
                result=reconciliation_standards.Result(gfs.id, why.id, why.accounting_classification_id, wp.id),
                approved_by_account_id=operator.id, created_from_transaction_id=None,
            )
            reconciliation_standards.apply_to_transaction(db, t_auto)
            db.commit()

            # A LEGACY batch whose Source was never identified (imported
            # before Import refused such files), covering July.
            legacy = bank_service.import_csv(
                db, file_bytes=chase_csv("DEBIT,07/15/2026,LEGACY ROW,-10.00,ACH_DEBIT,100.00,\n"),
                original_file_name="Download/Chase9999_Activity_20260715.csv", uploaded_by_account_id=None,
            )
            db.commit()
            ids.update(wp=wp.id, checking=checking.id, savings=savings.id, open1=t_open1.id, open2=t_open2.id,
                       review=t_review.id, conf=t_conf.id, auto=t_auto.id, june=t_june.id,
                       legacy_batch=legacy.batch.id, legacy_instrument=legacy.batch.payment_instrument_id or 0)

        check("fixture: the legacy batch has no Source", ids["legacy_instrument"] == 0)
        # BANK_EXPORT_BY_OWNER_001 — the report is per Owning Entity.
        OWNER = f"re:{ids['wp']}"
        JULY_O, JUNE_O = f"{JULY}&owner={OWNER}", f"{JUNE}&owner={OWNER}"

        client = web_app.app.test_client()
        client.post("/login", data={"username": "ex_operator", "password": "OperatorPass123!",
                                    "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})

        def get(path):
            resp = client.get(path)
            return resp.status_code, resp.data.decode("utf-8")

        def figure(page, key):
            match = re.search(rf'data-figure="{key}">(\d+)<', page)
            return int(match.group(1)) if match else None

        def href(page, action):
            match = re.search(rf'href="([^"]+)" data-action="{action}"', page)
            if not match:
                return None, {}
            url = urlparse(html_lib.unescape(match.group(1)))
            return url.path, {k: v[0] for k, v in parse_qs(url.query).items()}

        status, page = get(JULY_O)
        check("page responds 200", status == 200, str(status))

        # ================================================================ 1-2
        check("1. the page title is Monthly Accountant Export", "<h2>Monthly Accountant Export</h2>" in page)
        check("2. the person-specific 'Kermali' label is gone", "kermali" not in page.lower())

        # ================================================================ 3-8
        with SessionFactory() as s:
            expected = export_readiness.readiness(s, year=2026, month=7, owner_key=OWNER)
            blockers = export_service.compute_export_blockers(s, year=2026, month=7, owner_key=OWNER)
        check("3. EXPORT NOT READY, with the blocker summary from the export's own blockers",
              "EXPORT NOT READY" in page and expected.blocker_count == len(blockers) and not expected.ready)
        check("3. each group shows its count", all(
            f'data-group="{g}"' in page for g in ("to_reconcile", "reconciled", "unattributed")))
        # A file whose Source was never identified has no owner: it is listed
        # as not attributed, on every owner's page, and blocks no owner.
        check("4. the owner's Sources are resolved: Sources unresolved = 0", figure(page, "source") == 0,
              figure(page, "source"))
        check("4. the batch with no Source is listed as not attributed",
              "Download/Chase9999_Activity_20260715.csv"
              in page.split('data-group="unattributed"')[1].split("</section>")[0])
        check("5. Transactions to reconcile = 2", figure(page, "to_reconcile") == 2, figure(page, "to_reconcile"))
        check("6. Reconciled but Needs review = 1", figure(page, "reconciled") == 1, figure(page, "reconciled"))
        check("7. Automatic = 1", figure(page, "automatic") == 1, figure(page, "automatic"))
        check("8. Confirmed = 1", figure(page, "confirmed") == 1, figure(page, "confirmed"))
        _, review_tab = get("/bank/review?year=2026&month=7")
        check("5. the count equals the Review tab's own To Reconcile count",
              "To Reconcile (2)" in review_tab)

        # ================================================================ 9-10
        check("9. no transaction is listed by default (no raw blocker dump, no open details)",
              "data-transaction-id=" not in page and "<details" not in page and "reason(s)" not in page)
        check("9. the page offers the details on demand", "Show 2 transactions" in page and "Show 1 transaction" in page)
        status, shown = get(JULY_O + "&show=to_reconcile")
        rows = re.findall(r'data-transaction-id="(\d+)"', shown)
        check("10. details can be viewed: exactly the 2 transactions to reconcile",
              status == 200 and sorted(map(int, rows)) == sorted([ids["open1"], ids["open2"]]), str(rows))
        check("10. the details section is opened only on request", 'id="details-to_reconcile" open' in shown)
        _, shown_rec = get(JULY_O + "&show=reconciled")
        check("10. Reconciled details list the Needs review row",
              re.findall(r'data-transaction-id="(\d+)"', shown_rec) == [str(ids["review"])])

        # ================================================================ 11-13
        path, query = href(page, "fix-file")
        check("11. Fix this file goes to Import and Review for the same month",
              path == "/bank" and query == {"year": "2026", "month": "7"}, f"{path} {query}")
        check("11. the file's own Fix link targets its row on Import and Review",
              f"/bank?year=2026&amp;month=7#batch-{ids['legacy_batch']}" in page
              or f"/bank?month=7&amp;year=2026#batch-{ids['legacy_batch']}" in page)
        _, home = get("/bank?year=2026&month=7")
        check("11. Import and Review carries that row anchor and its Resolve Source action",
              f'id="batch-{ids["legacy_batch"]}"' in home and "Resolve Source" in home)
        path, query = href(page, "review-transactions")
        check("12. Review Transactions keeps the month",
              path == "/bank/review" and query == {"year": "2026", "month": "7"}, f"{path} {query}")
        path, query = href(page, "review-reconciled")
        check("13. Review Reconciled keeps the month",
              path == "/bank/review" and query == {"year": "2026", "month": "7", "view": "reconciled"},
              f"{path} {query}")

        # ================================================================ 14-15 (Import)
        with SessionFactory() as s:
            review = import_preview.preview_import(
                s, files=[import_preview.StagedFile("Chase3376_Activity_20260815.csv", chase_csv(
                    "DEBIT,08/05/2026,US FOODS 1001,-41.00,ACH_DEBIT,900.00,\n"))],
                uploaded_by_account_id=None, payment_instrument_id=ids["checking"],
            )
        check("14. a missing EXPECTED Source is a warning, not a blocking issue",
              any("expected Source(s) missing" in w and "RFWP-Savings" in w for w in review["warnings"])
              and review["blocking"] == [], str(review["warnings"]) + str(review["blocking"]))

        csrf = CSRF_RE.search(get("/bank")[1]).group(1)
        with SessionFactory() as s:
            batches_before = s.scalar(select(func.count(m.BankImportBatch.id)))
        # BANK_TWO_PASS_IMPORT_001: a file whose name carries no account is
        # put to the person in Pass 1; Confirm stays closed until it has one.
        resp = client.post("/bank/upload", content_type="multipart/form-data", data={
            "csrf_token": csrf,
            "files": (io.BytesIO(chase_csv("DEBIT,08/07/2026,UNKNOWN FILE ROW,-9.00,ACH_DEBIT,50.00,\n")), "statement.csv"),
        })
        token = STAGED_RE.search(resp.headers.get("Location", ""))
        _, modal = get(f"/bank/import/{token.group(1)}")
        check("15. a file whose own Source cannot be identified is put to the person before Confirm",
              token is not None and 'data-file-status="PENDING"' in modal and "Source not set" in modal
              and 'id="import-confirm" disabled' in modal)
        resp = client.post(f"/bank/upload/{token.group(1)}/confirm", data={"csrf_token": csrf},
                           follow_redirects=True)
        with SessionFactory() as s:
            batches_after = s.scalar(select(func.count(m.BankImportBatch.id)))
        check("15. Confirm is refused on the server too: nothing is imported",
              batches_after == batches_before and b"Import not confirmed" in resp.data,
              f"{batches_before} -> {batches_after}")
        resp = client.post("/bank/upload", content_type="multipart/form-data", data={
            "csrf_token": csrf, "payment_instrument_id": str(ids["checking"]),
            "files": (io.BytesIO(chase_csv("DEBIT,08/07/2026,UNKNOWN FILE ROW,-9.00,ACH_DEBIT,50.00,\n")), "statement.csv"),
        })
        token = STAGED_RE.search(resp.headers.get("Location", ""))
        get(f"/bank/import/{token.group(1)}")
        client.post(f"/bank/import/{token.group(1)}/check", data={"csrf_token": csrf})
        client.post(f"/bank/upload/{token.group(1)}/confirm", data={"csrf_token": csrf})
        with SessionFactory() as s:
            check("15. the same file with its Source chosen in the upload form imports normally",
                  s.scalar(select(func.count(m.BankImportBatch.id))) == batches_after + 1)

        # ================================================================ 16-17
        status, june = get(JUNE_O)
        check("16. a month with no blocker shows EXPORT READY and the download",
              status == 200 and "EXPORT READY" in june and "EXPORT NOT READY" not in june
              and "Download RfBank_2026_06_" in june
              and all(f'data-group="{g}"' not in june for g in ("source", "to_reconcile", "reconciled", "other")))
        check("16. a blocked month offers no download", "Download RfBank_2026_07" not in page)
        csrf = CSRF_RE.search(june).group(1)
        resp = client.post("/bank/export", data={"year": "2026", "month": "6", "owner": OWNER, "csrf_token": csrf})
        check("17. the download is the same xlsx file (name and type)",
              resp.status_code == 200 and "RfBank_2026_06_" in resp.headers.get("Content-Disposition", "")
              and resp.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with SessionFactory() as s:
            direct = export_service.build_kermali_workbook(s, year=2026, month=6, owner_key=OWNER)

        def cells(data):
            book = openpyxl.load_workbook(io.BytesIO(data))
            return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in book.worksheets}

        downloaded = cells(resp.data)
        check("17. its content is exactly the export service's workbook", downloaded == cells(direct))
        first_sheet = next(iter(downloaded.values()))
        check("17. the columns are unchanged", tuple(first_sheet[0][:len(export_service.KERMALI_COLUMNS)])
              == export_service.KERMALI_COLUMNS, str(first_sheet[0]))
        check("17. the June row is exported with its amount",
              any(-50.0 in row or -50 in row for row in first_sheet[1:]), str(first_sheet[1:]))
        resp = client.post("/bank/export", data={"year": "2026", "month": "7", "owner": OWNER, "csrf_token": csrf})
        check("17. a blocked month still cannot be downloaded", resp.status_code == 200
              and resp.mimetype == "text/html")

        # ================================================================ 5/6 multi-card file
        # A file covering several cards keeps no single Source by design; once
        # each of its rows is assigned from its own identifier, nothing in it
        # is unresolved — it is no longer a Source issue.
        with SessionFactory() as s:
            for raw in s.scalars(select(m.RawBankTransaction).where(
                    m.RawBankTransaction.import_batch_id == ids["legacy_batch"])):
                raw.normalized_transaction_id = ids["open1"]
            s.commit()
        with SessionFactory() as s:
            after = export_readiness.readiness(s, year=2026, month=7)
            still_null = s.get(m.BankImportBatch, ids["legacy_batch"]).payment_instrument_id is None
        check("5/6. a batch with no single Source but every row assigned is not a Source issue",
              still_null and after.counts["source"] == 0, str(after.counts))
    finally:
        try:
            from db import engine
            engine.dispose()
        except Exception:  # noqa: BLE001
            pass
        for path in (_TEST_DB_PATH,):
            try:
                os.remove(path)
            except OSError:
                pass
        shutil.rmtree(_STAGING_DIR, ignore_errors=True)

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    if failed:
        print("FAILED CHECKS:")
        for description in failed:
            print(f"  - {description}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
