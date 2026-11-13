#!/usr/bin/env python
"""HTTP test for the contextual help of every Bank page (UI_HOW_WORKS_001).

Each Bank page declares its own help section and the layout renders, once,
the "How ... works" link and its modal:

  * the module home (`/bank`, Import and Review) says "How Bank works";
  * every other page says "How this page works" and explains THAT page;
  * `/bank/review` is two pages for the user: To Reconcile
    (bank_review.html) and Reconciled (bank_reconciliation.html), each with
    its own section;
  * the import session (`/bank/import/<token>`) is reached by a real upload.

Runs against a DISPOSABLE SQLite database created here and deleted at the
end; the staging folder is a temporary folder too. Never a real database.
"""

from __future__ import annotations

import io
import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_how_works_bank_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "how-works-bank-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
web_app.app.config["BANK_IMPORT_STAGING_DIR"] = tempfile.mkdtemp(prefix="rfoneweb_staging_")  # never the real one
from db import SessionFactory  # noqa: E402
from _bank_upload_helper import staged_token, upload_and_confirm  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')

AUGUST_CSV = (
    "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
    "DEBIT,08/05/2026,US FOODS INVOICE 1001,-412.50,ACH_DEBIT,9000.00,\n"
    "DEBIT,08/20/2026,SYSCO FOODS 2231,-230.00,ACH_DEBIT,8770.00,\n"
).encode("utf-8")
SEPTEMBER_CSV = (
    "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
    "DEBIT,09/03/2026,SEPTEMBER VENDOR,-15.00,ACH_DEBIT,100.00,\n"
).encode("utf-8")

MODULE_LABEL = "How Bank works"
PAGE_LABEL = "How this page works"


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found"
    return match.group(1)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
            print(f"  PASS  {description}")
        else:
            failed.append(description)
            print(f"  FAIL  {description}" + (f"   [{detail[:300]}]" if detail else ""))

    def check_page(name: str, response, section: str, label: str, must_contain: tuple[str, ...] = ()) -> None:
        html = response.data.decode("utf-8")
        check(f"{name}: responds 200", response.status_code == 200, str(response.status_code))
        check(f"{name}: the link opens section {section}", f'data-how-works="{section}"' in html)
        check(f"{name}: the help section is in the page", f'id="help-{section}"' in html)
        check(f"{name}: the link says {label!r}", f">{label}</button>" in html)
        other = PAGE_LABEL if label == MODULE_LABEL else MODULE_LABEL
        check(f"{name}: never the other label", f">{other}</button>" not in html)
        check(f"{name}: one help dialog", html.count('id="rf-help-dialog"') == 1,
              str(html.count('id="rf-help-dialog"')))
        help_part = html[html.index('id="rf-help-dialog"'):] if 'id="rf-help-dialog"' in html else ""
        visible = re.sub(r"<[^>]+>", " ", help_part[:help_part.find("</dialog>")] if help_part else "")
        check(f"{name}: the help has real content (300+ characters)", len(" ".join(visible.split())) >= 300,
              str(len(visible)))
        for text in must_contain:
            check(f"{name}: the help explains {text!r}", text in help_part)

    try:
        with SessionFactory() as db:
            account_service.create_account(
                db, username="hw_bank", display_name="Help Bank Operator",
                password="OperatorPass123!", status="ACTIVE", is_admin=False,
            )
            db.commit()
            operator = db.query(m.RFOneAccount).filter_by(username="hw_bank").one()
            account_service.set_domain_access(
                db, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None,
            )
            checking = m.PaymentInstrument(
                display_name="Chase Checking 0214", instrument_type="BANK_ACCOUNT",
                institution="CHASE", last_four="0214", status="ACTIVE",
                effective_start_date=date(2026, 1, 1),
            )
            db.add(checking)
            db.commit()
            checking_id = checking.id

        client = web_app.app.test_client()
        client.post("/login", data={
            "username": "hw_bank", "password": "OperatorPass123!",
            "csrf_token": extract_csrf(client.get("/login").data),
        })

        # Real movements, so the Review and Export pages render rows.
        csrf = extract_csrf(client.get("/bank?year=2026&month=8").data)
        resp = upload_and_confirm(client, {
            "files": (io.BytesIO(AUGUST_CSV), "chase_0214_august.csv"),
            "payment_instrument_id": str(checking_id), "csrf_token": csrf,
            "return_to": "import_review", "year": "2026", "month": "8",
        })
        check("fixture: the August file is imported", resp.status_code == 302, str(resp.status_code))

        check_page("Import and Review (module home)", client.get("/bank?year=2026&month=8"),
                   "bank-home", MODULE_LABEL, ("Typical flow", "Upload and review", "Complete Month"))
        check_page("Review > To Reconcile", client.get("/bank/review?year=2026&month=8"),
                   "bank-review-to-reconcile", PAGE_LABEL, ("Select WHO / WHY", "Distinct / Duplicate"))
        check_page("Review > Reconciled", client.get("/bank/review?year=2026&month=8&view=reconciled"),
                   "bank-review-reconciled", PAGE_LABEL, ("Reopen", "Needs review"))
        check_page("Source", client.get("/bank/sources"), "bank-sources", PAGE_LABEL,
                   ("+ New Source / Edit", "File recognition rules"))
        check_page("Configuration", client.get("/bank/configuration"), "bank-configuration", PAGE_LABEL,
                   ("Merge (WHO)", "+ Add &hellip; / Edit"))
        check_page("AI Rules", client.get("/bank/ai-rules"), "bank-ai-rules", PAGE_LABEL,
                   ("Save and Apply", "Save Draft"))
        check_page("Monthly Export (no month chosen)", client.get("/bank/export"), "bank-export", PAGE_LABEL,
                   ("Check", "What blocks the export"))
        export_html = client.get("/bank/export").data.decode("utf-8")
        owner_select = export_html[export_html.index('id="owner"'):]
        owner_select = owner_select[:owner_select.index("</select>")]
        owner_keys = [k for k in re.findall(r'<option value="([^"]*)"', owner_select) if k]
        check("fixture: the export offers an Owning Entity", bool(owner_keys), owner_select[:300])
        if owner_keys:
            check_page("Monthly Export (month and owner checked)",
                       client.get("/bank/export", query_string={"year": 2026, "month": 8, "owner": owner_keys[0]}),
                       "bank-export", PAGE_LABEL, ("Download", "Transactions to reconcile"))
        check_page("Instructions", client.get("/bank/instructions"), "bank-instructions", PAGE_LABEL,
                   ("read-only page",))
        instructions = client.get("/bank/instructions").data.decode("utf-8")
        check("Instructions: still read-only (no form)", "<form" not in instructions)

        # The import session: a real upload, not confirmed.
        csrf = extract_csrf(client.get("/bank?year=2026&month=9").data)
        upload = client.post("/bank/upload", data={
            "files": (io.BytesIO(SEPTEMBER_CSV), "chase_0214_september.csv"),
            "csrf_token": csrf, "return_to": "import_review", "year": "2026", "month": "9",
        }, content_type="multipart/form-data")
        token = staged_token(upload)
        check("fixture: the upload opens an import session", token is not None, upload.headers.get("Location", ""))
        if token:
            check_page("Import session", client.get(f"/bank/import/{token}"), "bank-import-session", PAGE_LABEL,
                       ("Confirm Import", "Cancel import", "Pass 1"))
            client.post(f"/bank/upload/{token}/cancel", data={"csrf_token": csrf})
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    if failed:
        print("FAILED CHECKS:")
        for description in failed:
            print(f" - {description}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
