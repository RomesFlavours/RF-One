#!/usr/bin/env python
"""HTTP test for BANK_SOURCE_AND_IMPORT_REVIEW_001.

Source replaces the Instruments and Monthly Sources pages, and source
completeness moves to the moment it matters: right after the operator
selects the files, before anything is imported. This file pins down:

  SOURCE    1-9    one Source page; the New / Edit Source modal and its
                   routes; active/inactive kept; the retired routes land
                   safely; the navigation shows Source only.
  PREVIEW   10-16  `/bank/upload` stages and rehearses the import, writing
                   nothing; the review names expected, missing,
                   unrecognized and duplicate, and the periods covered.
  DECISION  17-23  Cancel writes nothing; Confirm imports exactly once, in
                   one transaction (a failure keeps nothing), with full
                   traceability; a set is only its uploader's to decide.
  REGRESSION 24-27 Review, Classification and Export still answer; the
                   parser's result is unchanged.

Runs against a DISPOSABLE SQLite database and a disposable staging
directory, both created here and deleted at the end.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_source_import_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "source-import-review-test-secret"
_STAGING_DIR = tempfile.mkdtemp(prefix="rfoneweb_staging_")

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import bank_routes  # noqa: E402
from _bank_upload_helper import confirm_leave_outs, create_missing_sources, session_state  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import monthly_source  # noqa: E402
from rfone_data_store.bank_reconciliation import parsers  # noqa: E402

web_app.app.config["BANK_IMPORT_STAGING_DIR"] = _STAGING_DIR

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
STAGED_RE = re.compile(r"(?:staged=|/bank/import/)([0-9a-f]{32})")
HEADER = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"

CHECKING_AUG = (HEADER
    + "DEBIT,08/05/2026,US FOODS INVOICE 1001,-412.50,ACH_DEBIT,9000.00,\n"
    + "DEBIT,08/12/2026,AMAZON MKTPLACE PMTS,-58.20,DEBIT_CARD,8941.80,\n"
    + "DEBIT,08/20/2026,SYSCO FOODS 2231,-230.00,ACH_DEBIT,8711.80,\n").encode("utf-8")
SAVINGS_AUG = (HEADER
    + "CREDIT,08/03/2026,INTEREST PAYMENT,1.25,ACCT_XFER,5001.25,\n"
    + "DEBIT,08/18/2026,TRANSFER OUT,-100.00,ACCT_XFER,4901.25,\n").encode("utf-8")
SAVINGS_JUL_AUG = (HEADER
    + "CREDIT,07/28/2026,JULY INTEREST,1.10,ACCT_XFER,5000.00,\n"
    + "CREDIT,08/09/2026,AUGUST DEPOSIT,20.00,ACCT_XFER,5020.00,\n").encode("utf-8")
NOT_A_BANK_FILE = b"name,email\nalice,alice@example.com\n"

APPROVED_TABS = ["Import and Review", "Review Transactions", "Monthly Export", "Source",
                 "AI Rules", "Configuration", "Instructions"]  # AI Rules: BANK_AI_RULES_001
# BANK_RULES_RESET_001: the old "Rules" tab (/bank/classification) is retired.


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found"
    return match.group(1)


def tab_labels(html: str) -> list[str]:
    nav = html[html.index('<nav class="module-tabs'):]
    nav = nav[:nav.index("</nav>")]
    return [re.sub(r"\s+", " ", label).strip()
            for label in re.findall(r'class="module-tab[^"]*"[^>]*>([^<]+)</a>', nav)]


def counts() -> dict[str, int]:
    """Every table an import (or its Recognition / completeness side
    effects) writes — the 'authoritative Bank data' a Cancel must leave
    untouched."""
    with SessionFactory() as s:
        return {
            name: s.scalar(select(func.count()).select_from(model)) or 0
            for name, model in (
                ("batches", m.BankImportBatch), ("raw", m.RawBankTransaction),
                ("transactions", m.FinancialTransaction),
                ("explanations", m.BankTransactionExplanation),
                ("periods", m.BankMonthlySourcePeriod),
                ("coverage", m.BankMonthlyInstrumentCoverage),
                ("assignment_audits", m.BankInstrumentAssignmentAudit),
            )
        }


def staged_dirs() -> list[str]:
    return sorted(os.listdir(_STAGING_DIR))


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
            print(f"  PASS  {description}")
        else:
            failed.append(description)
            print(f"  FAIL  {description}" + (f"   [{str(detail)[:400]}]" if detail else ""))

    try:
        # ------------------------------------------------------------ fixture
        with SessionFactory() as db:
            for username in ("si_operator", "si_other"):
                account_service.create_account(
                    db, username=username, display_name=username,
                    password="OperatorPass123!", status="ACTIVE", is_admin=False,
                )
            db.commit()
            for username in ("si_operator", "si_other"):
                account = db.query(m.RFOneAccount).filter_by(username=username).one()
                account_service.set_domain_access(
                    db, account_id=account.id, domain_code="BANK", enabled=True, role_code=None,
                )
            operator_id = db.query(m.RFOneAccount).filter_by(username="si_operator").one().id
            entity = m.LegalEntity(legal_name="Synthetic Restaurant LLC", status="ACTIVE")
            db.add(entity)
            db.flush()
            checking = m.PaymentInstrument(
                display_name="Chase Checking 0214", instrument_type="BANK_ACCOUNT",
                institution="CHASE", last_four="0214", status="ACTIVE",
                effective_start_date=date(2026, 1, 1), legal_entity_id=entity.id,
            )
            savings = m.PaymentInstrument(
                display_name="Chase Savings 5555", instrument_type="BANK_ACCOUNT",
                institution="CHASE", last_four="5555", status="ACTIVE",
                effective_start_date=date(2026, 1, 1), legal_entity_id=entity.id,
                external_account_identifier="XXXXXX445555",
            )
            retired = m.PaymentInstrument(
                display_name="Old Card 1111", instrument_type="CREDIT_CARD",
                institution="CHASE", last_four="1111", status="INACTIVE",
                effective_start_date=date(2025, 1, 1), effective_end_date=date(2025, 12, 31),
            )
            db.add_all([checking, savings, retired])
            db.flush()
            monthly_source.set_control_start(db, year=2026, month=1, account_id=operator_id)
            db.commit()
            checking_id, savings_id, retired_id = checking.id, savings.id, retired.id
            entity_id = entity.id

        def login(username):
            c = web_app.app.test_client()
            c.post("/login", data={
                "username": username, "password": "OperatorPass123!",
                "csrf_token": extract_csrf(c.get("/login").data),
            })
            return c

        client = login("si_operator")
        csrf = extract_csrf(client.get("/bank/sources").data)
        fetch = {"X-Requested-With": "fetch"}

        # ============================================================ SOURCE
        page = client.get("/bank/sources")
        html = page.data.decode("utf-8")
        check("1. the Source page exists", page.status_code == 200 and "<h2>Sources</h2>" in html,
              str(page.status_code))
        check("2. every existing instrument is a Source row",
              all(f'data-source-id="{i}"' in html for i in (checking_id, savings_id, retired_id)))
        check("2. the row shows the Source's account by its last four only, and its owning LLC",
              "··0214" in html and "Synthetic Restaurant LLC" in html)
        check("3. + New Source opens one modal that posts to the existing create route",
              "data-source-new" in html and 'id="source-dialog"' in html
              and 'data-create-url="/bank/instruments/new"' in html)
        check("3. the modal is on the page itself — no navigation to another page to add one",
              'id="source-form"' in html and "bank-source.js" in html)

        resp = client.post("/bank/instruments/new", headers=fetch, data={
            "csrf_token": csrf, "display_name": "Amex Business 3001", "instrument_type": "CREDIT_CARD",
            "institution": "AMEX", "last_four": "3001",
        })
        check("4. Save from the modal creates the Source and answers the modal in JSON",
              resp.status_code == 200 and resp.get_json().get("ok") is True, resp.data[:200])
        new_id = (resp.get_json() or {}).get("id")
        html = client.get("/bank/sources").data.decode("utf-8")
        order = [int(x) for x in re.findall(r'data-source-id="(\d+)"', html)]
        check("4. the refreshed list shows the new Source in its place (ordered by name)",
              new_id in order and order.index(new_id) == 0, str(order))
        check("4. the saved message is shown after the refresh",
              "Source &#39;Amex Business 3001&#39; created." in html or "Source 'Amex Business 3001' created." in html)

        resp = client.post("/bank/instruments/new", headers=fetch, data={
            "csrf_token": csrf, "display_name": "Bad digits", "instrument_type": "BANK_ACCOUNT",
            "last_four": "12a",
        })
        check("4. an invalid Source is refused inside the modal (JSON error, nothing created)",
              resp.status_code == 400 and resp.get_json().get("ok") is False
              and "Bad digits" not in client.get("/bank/sources").data.decode("utf-8"),
              resp.data[:200])

        resp = client.post(f"/bank/instruments/{savings_id}/edit", headers=fetch, data={
            "csrf_token": csrf, "display_name": "Chase Savings 5555 (Reserve)",
            "instrument_type": "BANK_ACCOUNT", "institution": "CHASE", "last_four": "5555",
            "legal_entity_id": str(entity_id), "status": "ACTIVE",
            "external_account_identifier": "", "keep_external_account_identifier": "1",
        })
        with SessionFactory() as s:
            sv = s.get(m.PaymentInstrument, savings_id)
            check("5. Edit from the same modal updates the Source in place",
                  resp.status_code == 200 and sv.display_name == "Chase Savings 5555 (Reserve)",
                  resp.data[:200])
            check("6. an edit that keeps the state keeps it (Active stays Active)",
                  sv.status == "ACTIVE", sv.status)
            check("6. the edit keeps the owning LLC it was given", sv.legal_entity_id == entity_id)
            check("5. an untouched account identifier is kept, not cleared, by the modal",
                  sv.external_account_identifier == "XXXXXX445555", sv.external_account_identifier)
        check("5. the Source page never sends a stored account identifier to the browser",
              "XXXXXX445555" not in client.get("/bank/sources").data.decode("utf-8"))
        html = client.get("/bank/sources").data.decode("utf-8")
        retired_row = html[html.index(f'data-source-id="{retired_id}"'):]
        retired_row = retired_row[:retired_row.index("</tr>")]
        check("6. an inactive Source is listed and shown Inactive", ">Inactive<" in retired_row)

        resp = client.get("/bank/instruments")
        check("7. the old Instruments address lands on Source",
              resp.status_code == 302 and resp.headers["Location"].endswith("/bank/sources"),
              resp.headers.get("Location"))
        resp = client.get("/bank/monthly?year=2026&month=8")
        check("8. the old Monthly Sources address lands on Check Sources for the same month",
              resp.status_code == 302
              and resp.headers["Location"] == "/bank?year=2026&month=8#step-sources",
              resp.headers.get("Location"))
        resp = client.get("/bank/monthly")
        check("8. ... and without a month, on Check Sources of the default month",
              resp.status_code == 302 and resp.headers["Location"] == "/bank#step-sources",
              resp.headers.get("Location"))

        pages = ("/bank", "/bank/review", "/bank/export", "/bank/sources",
                 "/bank/ai-rules", "/bank/configuration", "/bank/instructions")
        labels = {p: tab_labels(client.get(p).data.decode("utf-8")) for p in pages}
        check("9. every Bank page shows exactly the approved tabs, Source among them",
              all(v == APPROVED_TABS for v in labels.values()), str(labels))
        all_html = "".join(client.get(p).data.decode("utf-8") for p in pages)
        check("9. no tab is called Instruments or Monthly Sources any more",
              ">Instruments</a>" not in all_html and ">Monthly Sources</a>" not in all_html)

        # =========================================================== SESSION
        # BANK_TWO_PASS_IMPORT_001 — `/bank/upload` stages the set and opens its
        # import session; nothing reaches the Bank data before Confirm.
        def run_passes(token, decision="EXCLUDE"):
            create_missing_sources(client, token, csrf)
            confirm_leave_outs(client, token, csrf)
            client.post(f"/bank/import/{token}/check", data={"csrf_token": csrf})
            for issue in (session_state(client, token).get("check") or {}).get("issues", []):
                client.post(f"/bank/import/{token}/decide",
                            data={"csrf_token": csrf, "key": issue["key"], "decision": decision})
            return client.get(f"/bank/import/{token}").data.decode("utf-8")

        before = counts()
        resp = client.post("/bank/upload", data={
            "csrf_token": csrf, "return_to": "import_review", "year": "2026", "month": "8",
            "files": [
                (io.BytesIO(CHECKING_AUG), "Chase0214_Activity_20260905.csv"),
                (io.BytesIO(NOT_A_BANK_FILE), "contacts.csv"),
                (io.BytesIO(CHECKING_AUG), "Chase0214_Activity_20260905 (1).csv"),
            ],
        }, content_type="multipart/form-data")
        token_match = STAGED_RE.search(resp.headers.get("Location", ""))
        token = token_match.group(1) if token_match else ""
        check("10. upload opens the import session of the staged set",
              resp.status_code == 302 and resp.headers["Location"] == f"/bank/import/{token}",
              resp.headers.get("Location"))
        check("16. staging is read-only: nothing authoritative was written",
              counts() == before, f"{before} -> {counts()}")
        check("10. the files are held outside the database, in the staging area",
              token in staged_dirs(), str(staged_dirs()))
        page = client.get(f"/bank/import/{token}").data.decode("utf-8")
        check("10. one session page with Confirm Import and Cancel, listing every file",
              "Confirm Import" in page and "Cancel import" in page and page.count('data-file-status=') == 3)
        check("13. the unrecognized file is named, as not a known layout",
              "contacts.csv" in page and 'data-file-status="UNRECOGNIZED"' in page and "Not a known layout" in page)
        page = run_passes(token)
        state = session_state(client, token)
        check("10. the account comes from the file name: both Chase0214 files go to Chase Checking 0214",
              [f["source_id"] for f in state["files"] if f["kind"] == "BANK"] == [checking_id, checking_id])
        warnings = page[page.index('id="expected-missing"'):] if 'id="expected-missing"' in page else ""
        check("11/12. the missing expected Sources of the period are named (ACTIVE only: not the inactive "
              "Old Card, not the checking in the upload)",
              "August 2026" in warnings and "Chase Savings 5555 (Reserve)" in warnings
              and "Amex Business 3001" in warnings[:warnings.index("</ul>")]
              and "Old Card" not in warnings[:warnings.index("</ul>")]
              and "Chase Checking" not in warnings[:warnings.index("</ul>")],
              warnings[:600])
        check("14. the duplicate file in the set is named (same content, whatever its name)",
              "Same content as Chase0214_Activity_20260905.csv" in page)
        check("15. the period each file covers is shown", 'data-file-period="0">2026-08-05 &rarr; 2026-08-20<' in page)
        check("16. still nothing written after both passes", counts() == before)

        # ============================================================ CANCEL
        resp = client.post(f"/bank/upload/{token}/cancel", data={"csrf_token": csrf})
        check("17-19. Cancel writes no transaction, raw row, batch or coverage",
              counts() == before, f"{before} -> {counts()}")
        check("12. Cancel returns to the same month, ready for a new selection",
              resp.status_code == 302 and resp.headers["Location"] == "/bank?year=2026&month=8",
              resp.headers.get("Location"))
        check("17. the staged files are removed", token not in staged_dirs(), str(staged_dirs()))
        gone = client.get(f"/bank/import/{token}")
        check("17. a cancelled set cannot be shown again", gone.status_code == 302 and "/bank/import/" not in gone.headers["Location"])
        client.post(f"/bank/upload/{token}/confirm", data={"csrf_token": csrf})
        check("17. ... nor confirmed afterwards", counts() == before)

        # --------------------------------------- a file spanning two months
        resp = client.post("/bank/upload", data={
            "csrf_token": csrf, "payment_instrument_id": str(savings_id),
            "files": [(io.BytesIO(SAVINGS_JUL_AUG), "savings_jul_aug.csv")],
        }, content_type="multipart/form-data")
        span_token = STAGED_RE.search(resp.headers["Location"]).group(1)
        span_html = run_passes(span_token)
        check("15. a file covering two months is shown covering both — no monthly shape forced",
              'data-file-period="0">2026-07-28 &rarr; 2026-08-09<' in span_html)
        client.post(f"/bank/upload/{span_token}/cancel", data={"csrf_token": csrf})
        check("16. still nothing written", counts() == before)

        # ------------------------------ a set only its uploader may decide
        resp = client.post("/bank/upload", data={
            "csrf_token": csrf,
            "files": [(io.BytesIO(CHECKING_AUG), "Chase0214_Activity_20260905.csv")],
        }, content_type="multipart/form-data")
        foreign_token = STAGED_RE.search(resp.headers["Location"]).group(1)
        other = login("si_other")
        other_csrf = extract_csrf(other.get("/bank").data)
        other_view = other.get(f"/bank/import/{foreign_token}")
        other.post(f"/bank/upload/{foreign_token}/confirm", data={"csrf_token": other_csrf})
        check("13. another account can neither see nor confirm someone else's staged set",
              other_view.status_code == 302 and counts() == before and foreign_token in staged_dirs())
        client.post(f"/bank/upload/{foreign_token}/cancel", data={"csrf_token": csrf})

        # ------------------------------------------- failure rolls back whole
        resp = client.post("/bank/upload", data={
            "csrf_token": csrf, "return_to": "import_review", "year": "2026", "month": "8",
            "files": [
                (io.BytesIO(CHECKING_AUG), "Chase0214_Activity_20260905.csv"),
                (io.BytesIO(SAVINGS_AUG), "Chase5555_Activity_20260905.csv"),
            ],
        }, content_type="multipart/form-data")
        fail_token = STAGED_RE.search(resp.headers["Location"]).group(1)
        run_passes(fail_token)
        real_import = bank_routes.bank_service.import_csv
        calls = {"n": 0}

        def failing_import(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("synthetic failure on the second file")
            return real_import(*args, **kwargs)

        bank_routes.bank_service.import_csv = failing_import
        try:
            resp = client.post(f"/bank/upload/{fail_token}/confirm", data={"csrf_token": csrf},
                               follow_redirects=True)
        finally:
            bank_routes.bank_service.import_csv = real_import
        check("22. a Confirm that fails part-way keeps NOTHING of the set (one transaction)",
              calls["n"] == 2 and counts() == before, f"{calls} {before} -> {counts()}")
        check("22. the failure is reported", "IMPORT FAILED" in resp.data.decode("utf-8"))

        # ============================================= COMPLETE SET + CONFIRM
        with SessionFactory() as s:
            # The Amex card was created above with no history; give it a start
            # after August so that August expects exactly the two bank accounts.
            s.get(m.PaymentInstrument, new_id).effective_start_date = date(2026, 9, 1)
            s.commit()
        resp = client.post("/bank/upload", data={
            "csrf_token": csrf, "return_to": "import_review", "year": "2026", "month": "8",
            "files": [
                (io.BytesIO(CHECKING_AUG), "Chase0214_Activity_20260905.csv"),
                (io.BytesIO(SAVINGS_AUG), "Chase5555_Activity_20260905.csv"),
            ],
        }, content_type="multipart/form-data")
        ok_token = STAGED_RE.search(resp.headers["Location"]).group(1)
        ok_html = run_passes(ok_token)
        check("A. a complete set: every expected Source present, no missing-Source warning",
              'id="expected-missing"' not in ok_html)
        check("A. nothing blocks a complete set: Confirm Import is enabled",
              re.search(r'id="import-confirm"\s*>', ok_html) is not None)
        check("16. still nothing written before Confirm", counts() == before)

        resp = client.post(f"/bank/upload/{ok_token}/confirm", data={"csrf_token": csrf})
        after = counts()
        check("20. Confirm imports the set: two batches, five raw rows, five transactions",
              after["batches"] == before["batches"] + 2 and after["raw"] == before["raw"] + 5
              and after["transactions"] == before["transactions"] + 5, f"{before} -> {after}")
        check("20. Confirm returns to the month the upload came from",
              resp.status_code == 302 and resp.headers["Location"] == "/bank?year=2026&month=8",
              resp.headers.get("Location"))
        check("20. the import's completeness control ran as before (August opened under control)",
              after["periods"] >= before["periods"] + 1)
        check("20. the staged set is gone once imported", ok_token not in staged_dirs(), str(staged_dirs()))
        client.post(f"/bank/upload/{ok_token}/confirm", data={"csrf_token": csrf})
        check("21. a second Confirm of the same set imports nothing", counts() == after)
        html_home = client.get("/bank?year=2026&month=8").data.decode("utf-8")
        check("8. Check Sources on Import and Review carries the former Monthly Sources control "
              "(per-Source table, Complete Month, control start)",
              'id="source-details"' in html_home and 'id="completeness-control"' in html_home
              and "Accounts and cards for 2026-08" in html_home
              and "Complete Month" in html_home and "Set control start" in html_home)

        with SessionFactory() as s:
            batches = s.scalars(select(m.BankImportBatch).order_by(m.BankImportBatch.id)).all()
            by_name = {b.original_file_name: b for b in batches}
            checking_batch = by_name.get("Chase0214_Activity_20260905.csv")
            check("23. traceability: original file name, original bytes, hash and uploader kept",
                  checking_batch is not None and checking_batch.raw_file_bytes == CHECKING_AUG
                  and checking_batch.sha256 == parsers.sha256_bytes(CHECKING_AUG)
                  and checking_batch.uploaded_by_account_id == operator_id)
            check("23. each file resolved to its Source, and its rows point at their batch",
                  checking_batch.payment_instrument_id == checking_id
                  and by_name["Chase5555_Activity_20260905.csv"].payment_instrument_id == savings_id
                  and all(r.import_batch_id == checking_batch.id for r in s.scalars(
                      select(m.RawBankTransaction).where(
                          m.RawBankTransaction.import_batch_id == checking_batch.id)).all()))
            parsed = parsers.parse_csv_bytes(CHECKING_AUG)
            check("27. the parser's result is unchanged by the session "
                  "(rows and range as the parser reads them)",
                  checking_batch.row_count == len(parsed.rows) == 3
                  and checking_batch.date_range_start == date(2026, 8, 5)
                  and checking_batch.date_range_end == date(2026, 8, 20))

        # ---------------------------------------- the same set a second time
        resp = client.post("/bank/upload", data={
            "csrf_token": csrf,
            "files": [(io.BytesIO(CHECKING_AUG), "renamed_checking.csv")],
        }, content_type="multipart/form-data")
        again_token = STAGED_RE.search(resp.headers["Location"]).group(1)
        client.get(f"/bank/import/{again_token}")
        client.post(f"/bank/import/{again_token}/assign",
                    data={"csrf_token": csrf, "file_index": "0", "source": str(checking_id)})
        client.post(f"/bank/import/{again_token}/check", data={"csrf_token": csrf})
        again = client.get(f"/bank/import/{again_token}").data.decode("utf-8")
        issues = (session_state(client, again_token).get("check") or {}).get("issues", [])
        check("D. an already-imported file is recognized by content, even renamed",
              f"This exact file was already imported (batch #{checking_batch.id})" in again
              and len(issues) == 3 and all(i["exclusion_only"] for i in issues))
        client.post(f"/bank/import/{again_token}/decide",
                    data={"csrf_token": csrf, "key": issues[0]["key"], "decision": "IMPORT_DISTINCT"})
        check("D. its rows cannot be authorized as distinct operations: Confirm stays disabled",
              re.search(r'id="import-confirm"\s+disabled', client.get(f"/bank/import/{again_token}").data.decode("utf-8")) is not None)
        client.post(f"/bank/upload/{again_token}/cancel", data={"csrf_token": csrf})
        check("D. and cancelling it changes nothing", counts() == after)

        # ======================================================== REGRESSION
        for path, label in (("/bank/review?year=2026&month=8", "24. Review Transactions"),
                            ("/bank/export", "26. Monthly Export")):
            r = client.get(path)
            check(f"{label} still answers 200", r.status_code == 200, str(r.status_code))
        check("25. the retired Classification (Rules) page answers 404",
              client.get("/bank/classification").status_code == 404)
        review = client.get("/bank/review?year=2026&month=8").data.decode("utf-8")
        check("24. Review lists the confirmed import's transactions", "US FOODS INVOICE 1001" in review)

    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
        shutil.rmtree(_STAGING_DIR, ignore_errors=True)

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
