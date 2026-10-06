#!/usr/bin/env python
"""HTTP test for the final Bank release blockers (BANK_FINAL_RELEASE_BLOCKERS_002).

   1      Configuration no longer edits Sources (link to /bank/sources only);
   2-3    Source create / edit, and Active / Inactive through the lifecycle
          service (end date derived; reactivation expected again);
   4-5    a missing expected Source is a warning: Confirm Import stays enabled;
   6      a re-downloaded file is reported as duplicate before Confirm, also
          against retained rows whose `description_normalized` is empty;
   7-10   a WHY is created with Name + Group only, from Select WHO / WHY and
          from the Rule modal; existing WHY -> WHAT mappings are untouched;
   11     create WHY + use it in the same human event = confirmation_count 1;
   12-13  Cancel writes nothing; Confirm imports once, atomically.

Runs against a DISPOSABLE SQLite database and staging directory, both
created here and deleted at the end.
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_release_blockers_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "release-blockers-test-secret"
_STAGING_DIR = tempfile.mkdtemp(prefix="rfoneweb_release_staging_")

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import bank_routes  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import monthly_source, why_catalog  # noqa: E402

web_app.app.config["BANK_IMPORT_STAGING_DIR"] = _STAGING_DIR

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
STAGED_RE = re.compile(r"staged=([0-9a-f]{32})")
HEADER = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
CHECKING_AUG = (HEADER
    + "DEBIT,08/05/2026,US FOODS INVOICE 1001,-412.50,ACH_DEBIT,9000.00,\n"
    + "DEBIT,08/12/2026,AMAZON MKTPLACE PMTS,-58.20,DEBIT_CARD,8941.80,\n").encode("utf-8")
# The same two operations, downloaded again with one more row: new bytes.
CHECKING_AUG_REDOWNLOAD = (CHECKING_AUG.decode("utf-8")
    + "DEBIT,08/20/2026,SYSCO FOODS 2231,-230.00,ACH_DEBIT,8711.80,\n").encode("utf-8")


def counts() -> dict[str, int]:
    with SessionFactory() as s:
        return {name: s.scalar(select(func.count()).select_from(model)) or 0
                for name, model in (("batches", m.BankImportBatch), ("raw", m.RawBankTransaction),
                                    ("transactions", m.FinancialTransaction),
                                    ("explanations", m.BankTransactionExplanation))}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f"   [{str(detail)[:300]}]"))

    try:
        # ---------------------------------------------------------- fixture
        with SessionFactory() as s:
            account_service.create_account(s, username="rb_operator", display_name="rb_operator",
                                           password="OperatorPass123!", status="ACTIVE", is_admin=False)
            s.commit()
            operator_id = s.query(m.RFOneAccount).filter_by(username="rb_operator").one().id
            account_service.set_domain_access(s, account_id=operator_id, domain_code="BANK", enabled=True, role_code=None)
            entity = m.LegalEntity(legal_name="Release LLC", status="ACTIVE")
            s.add(entity)
            s.flush()
            checking = m.PaymentInstrument(display_name="Chase Checking 0214", instrument_type="BANK_ACCOUNT",
                                           institution="CHASE", last_four="0214", status="ACTIVE",
                                           effective_start_date=date(2026, 1, 1), legal_entity_id=entity.id)
            savings = m.PaymentInstrument(display_name="Chase Savings 5555", instrument_type="BANK_ACCOUNT",
                                          institution="CHASE", last_four="5555", status="ACTIVE",
                                          effective_start_date=date(2026, 1, 1), legal_entity_id=entity.id)
            s.add_all([checking, savings])
            s.flush()
            monthly_source.set_control_start(s, year=2026, month=1, account_id=operator_id)
            counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
            atm = m.BankOccurrence(canonical_name="Corner ATM", occurrence_type_id=counterparty.id, status="ACTIVE")
            zeta = m.BankOccurrence(canonical_name="Zeta Exchange", occurrence_type_id=counterparty.id, status="ACTIVE")
            s.add_all([atm, zeta])
            s.flush()
            s.commit()
            ids = {"checking": checking.id, "savings": savings.id, "atm": atm.id, "zeta": zeta.id}
            groups = why_catalog.groups(s)
            group_id = groups[0].id
            whats_before = {r.id: r.accounting_classification_id for r in s.scalars(select(m.BankTransactionReason))}

        client = web_app.app.test_client()
        client.post("/login", data={"username": "rb_operator", "password": "OperatorPass123!",
                                    "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})
        csrf = CSRF_RE.search(client.get("/bank/sources").data.decode()).group(1)
        fetch = {"X-Requested-With": "fetch"}

        # ============================================================== 1
        page = client.get("/bank/configuration").data.decode("utf-8")
        block = page[page.index('id="cp-accounts"'):page.index('id="cp-support"')]
        check("1. Configuration no longer edits Sources: only a 'Manage Sources' link to /bank/sources",
              "Manage Sources" in block and 'href="/bank/sources"' in block and "<table" not in block
              and 'data-add="account"' not in page)
        check("1. the former Configuration account routes are gone",
              client.post("/bank/configuration/account", data={"csrf_token": csrf, "label": "X"}).status_code == 404)

        # ============================================================ 2-3
        resp = client.post("/bank/instruments/new", headers=fetch, data={
            "csrf_token": csrf, "display_name": "Amex 3001", "instrument_type": "CREDIT_CARD",
            "institution": "AMEX", "last_four": "3001"})
        amex_id = (resp.get_json() or {}).get("id")
        check("2. Source create works (modal route)", resp.status_code == 200 and amex_id is not None, resp.data[:200])
        resp = client.post(f"/bank/instruments/{amex_id}/edit", headers=fetch, data={
            "csrf_token": csrf, "display_name": "Amex Business 3001", "instrument_type": "CREDIT_CARD",
            "institution": "AMEX", "last_four": "3001", "status": "ACTIVE"})
        with SessionFactory() as s:
            amex = s.get(m.PaymentInstrument, amex_id)
            check("2. Source edit works", resp.status_code == 200 and amex.display_name == "Amex Business 3001")

        html = client.get("/bank/sources").data.decode("utf-8")
        check("3. the Edit Source modal offers Active / Inactive",
              'id="source-status" name="status"' in html and '<option value="INACTIVE">Inactive</option>' in html)

        # Checking has a posting on 2026-08-12 (imported below); deactivate after that.
        # Savings: deactivate now (no postings -> end date UNKNOWN).
        resp = client.post(f"/bank/instruments/{ids['savings']}/edit", headers=fetch, data={
            "csrf_token": csrf, "display_name": "Chase Savings 5555", "instrument_type": "BANK_ACCOUNT",
            "institution": "CHASE", "last_four": "5555", "legal_entity_id": str(entity.id), "status": "INACTIVE"})
        with SessionFactory() as s:
            sv = s.get(m.PaymentInstrument, ids["savings"])
            check("3. Inactive: status INACTIVE through the lifecycle service (reason CLOSED, end date "
                  "derived — UNKNOWN when there is no posting)",
                  resp.status_code == 200 and sv.status == "INACTIVE" and sv.lifecycle_end_reason == "CLOSED"
                  and sv.effective_end_date is None, f"{sv.status} {sv.lifecycle_end_reason} {sv.effective_end_date}")
        html = client.get("/bank/sources").data.decode("utf-8")
        row = html[html.index(f'data-source-id="{ids["savings"]}"'):]
        check("3. the list refreshes showing Inactive", ">Inactive<" in row[:row.index("</tr>")])
        resp = client.post(f"/bank/instruments/{ids['savings']}/edit", data={
            "csrf_token": csrf, "display_name": "Chase Savings 5555", "instrument_type": "BANK_ACCOUNT",
            "institution": "CHASE", "last_four": "5555", "legal_entity_id": str(entity.id)})
        with SessionFactory() as s:
            check("3. a form without the State control (Card settings) never changes it",
                  s.get(m.PaymentInstrument, ids["savings"]).status == "INACTIVE")
        client.post(f"/bank/instruments/{ids['savings']}/edit", headers=fetch, data={
            "csrf_token": csrf, "display_name": "Chase Savings 5555", "instrument_type": "BANK_ACCOUNT",
            "institution": "CHASE", "last_four": "5555", "legal_entity_id": str(entity.id), "status": "ACTIVE"})
        with SessionFactory() as s:
            sv = s.get(m.PaymentInstrument, ids["savings"])
            period = monthly_source.get_or_create_period(s, 2026, 9)
            verdict = monthly_source.expectation_with_lifecycle_boundary(s, sv, period)
            s.rollback()
            check("3. Active again: status ACTIVE, end reason and end date cleared, expected again",
                  sv.status == "ACTIVE" and sv.lifecycle_end_reason is None and sv.effective_end_date is None
                  and verdict.verdict == m.COVERAGE_EXPECTED, verdict.verdict)

        # ============================================================ 4-5
        before = counts()
        resp = client.post("/bank/upload", data={
            "csrf_token": csrf, "return_to": "import_review", "year": "2026", "month": "8",
            "payment_instrument_id": str(ids["checking"]),
            "files": [(io.BytesIO(CHECKING_AUG), "checking_aug.csv")]}, content_type="multipart/form-data")
        token = STAGED_RE.search(resp.headers["Location"]).group(1)
        modal = client.get(resp.headers["Location"]).data.decode("utf-8")
        modal = modal[modal.index('id="import-review-dialog"'):]
        missing = modal[modal.index('data-review-row="missing"'):]
        missing = missing[:missing.index("</tr>")]
        check("4. a missing expected Source (Savings) is shown clearly", "Chase Savings 5555" in missing, missing)
        check("4. ... as a warning, not a blocking issue",
              "Chase Savings 5555" in modal[modal.index("<h4>Warnings</h4>"):modal.index("<h4>Blocking issues</h4>")]
              and "None" in modal[modal.index("<h4>Blocking issues</h4>"):][:200])
        check("5. Confirm Import stays available with a Source missing",
              re.search(r'id="import-review-confirm"\s*>', modal) is not None)

        # ============================================================== 12
        client.post(f"/bank/upload/{token}/cancel", data={"csrf_token": csrf})
        check("12. Cancel writes nothing", counts() == before, f"{before} -> {counts()}")

        # ============================================================== 13
        resp = client.post("/bank/upload", data={
            "csrf_token": csrf, "payment_instrument_id": str(ids["checking"]),
            "files": [(io.BytesIO(CHECKING_AUG), "checking_aug.csv")]}, content_type="multipart/form-data")
        token = STAGED_RE.search(resp.headers["Location"]).group(1)
        real_import = bank_routes.bank_service.import_csv

        def failing(*args, **kwargs):
            real_import(*args, **kwargs)
            raise RuntimeError("synthetic failure after the rows were written")

        bank_routes.bank_service.import_csv = failing
        try:
            client.post(f"/bank/upload/{token}/confirm", data={"csrf_token": csrf})
        finally:
            bank_routes.bank_service.import_csv = real_import
        check("13. a failing Confirm keeps nothing (one transaction)", counts() == before, f"{before} -> {counts()}")
        resp = client.post("/bank/upload", data={
            "csrf_token": csrf, "payment_instrument_id": str(ids["checking"]),
            "files": [(io.BytesIO(CHECKING_AUG), "checking_aug.csv")]}, content_type="multipart/form-data")
        token = STAGED_RE.search(resp.headers["Location"]).group(1)
        client.post(f"/bank/upload/{token}/confirm", data={"csrf_token": csrf})
        client.post(f"/bank/upload/{token}/confirm", data={"csrf_token": csrf})
        after = counts()
        check("13. Confirm imports exactly once (second Confirm of the same set imports nothing)",
              after["batches"] == before["batches"] + 1 and after["transactions"] == before["transactions"] + 2,
              f"{before} -> {after}")

        # =============================================================== 6
        # Rows retained from the historical load carry no normalized
        # description: make the imported rows look like that.
        with SessionFactory() as s:
            for t in s.scalars(select(m.FinancialTransaction)):
                t.description_normalized = None
            s.commit()
        resp = client.post("/bank/upload", data={
            "csrf_token": csrf, "payment_instrument_id": str(ids["checking"]),
            "files": [(io.BytesIO(CHECKING_AUG_REDOWNLOAD), "checking_aug_again.csv")]},
            content_type="multipart/form-data")
        token = STAGED_RE.search(resp.headers["Location"]).group(1)
        modal = client.get(resp.headers["Location"]).data.decode("utf-8")
        modal = modal[modal.index('id="import-review-dialog"'):]
        check("6. a re-downloaded file is reported as duplicate BEFORE Confirm, even against rows with an "
              "empty normalized description",
              "2 transaction(s) look like ones already recorded" in modal, modal[modal.index("<h4>Files</h4>"):][:1500])
        check("6. the review wrote nothing", counts() == after)
        client.post(f"/bank/upload/{token}/confirm", data={"csrf_token": csrf})
        with SessionFactory() as s:
            dup = s.scalar(select(func.count()).select_from(m.FinancialTransaction).where(
                m.FinancialTransaction.duplicate_status == "CANDIDATE_DUPLICATE"))
            stored_empty = s.scalar(select(func.count()).select_from(m.FinancialTransaction).where(
                m.FinancialTransaction.description_normalized.is_(None)))
        check("6. after Confirm the two repeated rows are candidate duplicates; the third is new; the "
              "retained rows were not rewritten", dup == 2 and stored_empty == 2, f"dup={dup} empty={stored_empty}")

        # ========================================================== 7-11
        def create(name, *, group=None, who_id=None):
            data = {"csrf_token": csrf, "name": name}
            if group is not None:
                data["group_id"] = str(group)
            if who_id is not None:
                data["occurrence_id"] = str(who_id)
            return client.post("/bank/whys/create", headers=fetch, data=data)

        def association(who_id, why_id):
            with SessionFactory() as s:
                row = s.scalars(select(m.BankOccurrenceReasonAssociation).where(
                    m.BankOccurrenceReasonAssociation.occurrence_id == who_id,
                    m.BankOccurrenceReasonAssociation.transaction_reason_id == why_id)).first()
                return (row.active, row.confirmation_count) if row else None

        no_group = create("Cash Withdrawal", who_id=ids["atm"])
        check("7. the WHY Group is required", no_group.status_code == 400)
        made = create("Cash Withdrawal", group=group_id, who_id=ids["atm"])
        body = made.get_json() or {}
        why_id = (body.get("why") or {}).get("id")
        with SessionFactory() as s:
            why = s.get(m.BankTransactionReason, why_id) if why_id else None
        check("7/9. Select WHO / WHY: a WHY is created with Name + Group only — no WHAT, no P&L, no account",
              made.status_code == 200 and body.get("ok") and why is not None
              and why.accounting_classification_id is None and why.reason_group_id == group_id, str(body))
        dialog = client.get("/bank/review").data.decode("utf-8")
        dialog = dialog[dialog.index('id="why-create-dialog"'):]
        check("7. the dialog asks only Name and Group; the WHAT is marked optional",
              "WHY Name" in dialog and "WHY Group" in dialog and "(optional)" in dialog)
        check("11. creating the WHY is not yet a confirmation (count 0)",
              association(ids["atm"], why_id) == (True, 0), str(association(ids["atm"], why_id)))

        with SessionFactory() as s:
            txn_id = s.scalars(select(m.FinancialTransaction.id).order_by(m.FinancialTransaction.id)).first()
        confirmed = client.post(f"/bank/transactions/{txn_id}/who-why", headers=fetch, data={
            "csrf_token": csrf, "occurrence_id": str(ids["atm"]), "transaction_reason_id": str(why_id)})
        check("9. Select WHO / WHY: Confirm with the WHY without WHAT works",
              confirmed.status_code == 200 and (confirmed.get_json() or {}).get("ok"), confirmed.data[:300])
        check("11. create WHY + use it in the same human reconciliation = confirmation_count 1",
              association(ids["atm"], why_id) == (True, 1), str(association(ids["atm"], why_id)))

        rule_made = create("Exchange Commission", group=group_id, who_id=ids["zeta"])
        rule_why = (rule_made.get_json() or {}).get("why", {}).get("id")
        applied = client.post("/bank/who-rules/apply", headers=fetch, data={
            "csrf_token": csrf, "occurrence_id": str(ids["zeta"]), "instruction": "Dove nella descrizione trovi ZETA EXCHANGE",
            "transaction_reason_id": [str(rule_why)]})
        check("10. Rule modal: a WHY with Name + Group only is created and Apply accepts it",
              rule_made.status_code == 200 and applied.status_code == 200 and (applied.get_json() or {}).get("ok"),
              f"{rule_made.data[:200]} {applied.data[:300]}")
        check("11. Rule modal: create WHY + Apply = confirmation_count 1",
              association(ids["zeta"], rule_why) == (True, 1), str(association(ids["zeta"], rule_why)))
        client.post("/bank/who-rules/apply", headers=fetch, data={
            "csrf_token": csrf, "occurrence_id": str(ids["zeta"]), "instruction": "Dove nella descrizione trovi ZETA EXCHANGE",
            "transaction_reason_id": [str(rule_why)]})
        check("11. a second identical Apply counts nothing more", association(ids["zeta"], rule_why) == (True, 1))

        with SessionFactory() as s:
            whats_after = {r.id: r.accounting_classification_id for r in s.scalars(select(m.BankTransactionReason))
                           if r.id in whats_before}
        check("8. every existing WHY -> WHAT mapping is intact", whats_after == whats_before)
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
