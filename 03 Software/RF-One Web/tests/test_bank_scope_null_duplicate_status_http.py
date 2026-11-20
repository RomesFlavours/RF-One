#!/usr/bin/env python
"""Bank month scope and NULL `duplicate_status` (BANK_SCOPE_NULL_DUPLICATE_001).

Only a transaction a human CONFIRMED as a duplicate leaves a month's scope.
A NULL `duplicate_status` — rows loaded before the duplicate flow set 'NONE'
on every import — is "never judged a duplicate" and stays in scope. The
defect this pins down: `duplicate_status != 'CONFIRMED_DUPLICATE'` is NULL,
not TRUE, in SQL, so those rows silently vanished from the Monthly Export
and from Import and Review.

  A. NULL stays in scope;
  B. 'NONE' stays in scope;
  C. 'CONFIRMED_DUPLICATE' is excluded;
  D. the Monthly Export and /bank use the same scope;
  E. the unresolved-settlement path follows the same NULL rule.

Runs against a DISPOSABLE SQLite database created here and deleted at the
end.
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_scope_null_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "scope-null-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import accounting_dedup  # noqa: E402
from rfone_data_store.bank_reconciliation import export as export_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
AUGUST_CSV = (
    "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
    "DEBIT,08/03/2026,VENDOR NULL STATUS,-11.00,ACH_DEBIT,900.00,\n"
    "DEBIT,08/04/2026,VENDOR NONE STATUS,-12.00,ACH_DEBIT,888.00,\n"
    "DEBIT,08/05/2026,VENDOR CONFIRMED DUP,-13.00,ACH_DEBIT,875.00,\n"
).encode("utf-8")


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

    try:
        with SessionFactory() as db:
            account_service.create_account(
                db, username="scope_operator", display_name="Scope Operator",
                password="OperatorPass123!", status="ACTIVE", is_admin=False,
            )
            db.commit()
            operator_id = db.query(m.RFOneAccount).filter_by(username="scope_operator").one().id
            account_service.set_domain_access(
                db, account_id=operator_id, domain_code="BANK", enabled=True, role_code=None,
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
            "username": "scope_operator", "password": "OperatorPass123!",
            "csrf_token": extract_csrf(client.get("/login").data),
        })
        client.post("/bank/upload", data={
            "files": (io.BytesIO(AUGUST_CSV), "chase_0214_august.csv"),
            "payment_instrument_id": str(checking_id), "csrf_token": extract_csrf(client.get("/bank").data),
        }, content_type="multipart/form-data")

        # The three states of duplicate_status, set directly: NULL as left by
        # the historical bulk load, 'NONE' as set by every normal import,
        # and a human-confirmed duplicate.
        with SessionFactory() as db:
            rows = {t.description_original: t for t in db.scalars(select(m.FinancialTransaction))}
            null_row, none_row, dup_row = (rows["VENDOR NULL STATUS"], rows["VENDOR NONE STATUS"],
                                           rows["VENDOR CONFIRMED DUP"])
            null_row.duplicate_status = None
            none_row.duplicate_status = "NONE"
            dup_row.duplicate_status = "CONFIRMED_DUPLICATE"
            db.commit()
            ids = {"null": null_row.id, "none": none_row.id, "dup": dup_row.id}

            scope = {t.id for t in export_service.in_scope_transactions(db, 2026, 8)}
            check("A. duplicate_status NULL stays in the month's scope", ids["null"] in scope)
            check("B. duplicate_status 'NONE' stays in the month's scope", ids["none"] in scope)
            check("C. duplicate_status 'CONFIRMED_DUPLICATE' is excluded", ids["dup"] not in scope)

            unresolved = {t.id for t in export_service.unresolved_transactions(db, year=2026, month=8)}
            check("A/B. the NULL and 'NONE' rows are counted as still needing review",
                  {ids["null"], ids["none"]} <= unresolved and ids["dup"] not in unresolved,
                  str(sorted(unresolved)))
            blockers = export_service.compute_export_blockers(db, year=2026, month=8)
            blocked_ids = {int(x) for b in blockers
                           for x in re.findall(r"transaction id=(\d+)", b.reason)}
            check("D. the Monthly Export blocks on exactly the same transactions",
                  blocked_ids == unresolved, f"{sorted(blocked_ids)} vs {sorted(unresolved)}")

            # E. The unresolved-settlement path, with the same three states.
            for key in ("null", "none", "dup"):
                db.get(m.FinancialTransaction, ids[key]).accounting_status = (
                    accounting_dedup.UNRESOLVED_NO_SETTLEMENT_ACCOUNT)
            db.flush()
            settlement = {t.id for t in export_service._unresolved_settlement_transactions(db, 2026, 8)}
            check("E. unresolved settlement keeps NULL and 'NONE', excludes the confirmed duplicate",
                  ids["null"] in settlement and ids["none"] in settlement and ids["dup"] not in settlement,
                  str(sorted(settlement)))
            db.rollback()

        # D. /bank shows the same scope and the same unresolved count.
        html = client.get("/bank?year=2026&month=8").data.decode("utf-8")
        who = html[html.index('id="step-who"'):html.index('id="step-review"')]
        who_total = sum(int(v) for v in re.findall(r'data-who-count="\w+">(\d+)<', who))
        shown_unresolved = int(re.search(r"data-unresolved-count>(\d+)<", html).group(1))
        check("D. /bank Automatic WHO covers the Export's in-scope transactions (2)",
              who_total == len(scope) == 2, f"{who_total} vs {len(scope)}")
        check("D. /bank Review Missing equals the Export's unresolved count (2)",
              shown_unresolved == len(unresolved) == 2, f"{shown_unresolved} vs {len(unresolved)}")
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
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
