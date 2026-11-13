#!/usr/bin/env python
"""HTTP test for Split (BANK_SPLIT_ALLOCATION_001), on an ISOLATED, MIGRATED COPY of the local database.

The real Amazon order report (when present on this PC) is loaded into the copy; the page lists the linked
movements (certain / candidate), shows one movement with its products and the proposed lines, keeps an
incomplete split as a draft, refuses an unbalanced or unconfirmed split, writes a complete one as the movement's
allocations, and previews ONE QuickBooks Online Purchase with several lines. Nothing else changes.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)
_SOURCE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RF-One" / "Bank" / "rfone.db"
_CSV = Path(os.environ.get("RFONE_AMAZON_CSV", r"C:\Users\servi\Downloads\orders_from_20260101_to_20261026_20261026_1345 (1).csv"))
if not _SOURCE.exists() or not _CSV.exists():
    print("SKIPPED: no local Bank database or Amazon report to use.")
    sys.exit(0)
_FOLDER = tempfile.mkdtemp(prefix="rfone_split_")
atexit.register(shutil.rmtree, _FOLDER, ignore_errors=True)
_COPY = Path(_FOLDER) / "rfone.db"
_src = sqlite3.connect(f"file:{_SOURCE.as_posix()}?mode=ro", uri=True)
_dst = sqlite3.connect(_COPY)
_src.backup(_dst)
_dst.close()
_src.close()
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_COPY.as_posix()}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "split-test-secret"
os.environ["RFONE_BANK_SINGLE_ENGINE"] = "1"
os.environ["RFONE_BANK_GUIDED"] = "1"
os.environ["CBANK_BANK_DB"] = str(_COPY)
os.environ["CBANK_STORE_DIR"] = str(Path(_FOLDER) / "store")
os.environ["CBANK_AUTO_RUN"] = "0"
os.environ["CBANK_BANK_CODE_ROOT"] = str(Path(APP_DIR).parents[1])

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import bank_amazon  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
BANK_CSRF_RE = re.compile(r'<meta name="bank-csrf" content="([^"]+)"')


def preserved(db, but=()):
    return (sorted(tuple(r) for r in db.execute(select(m.FinancialTransaction.id, m.FinancialTransaction.amount_minor,
                                                       m.FinancialTransaction.explanation_id)).all()),
            db.scalar(select(func.count(m.BankTransactionExplanation.id))),
            sorted(tuple(r) for r in db.execute(select(m.BankAiRule.id, m.BankAiRule.status)).all()),
            sorted(tuple(r) for r in db.execute(select(m.BankWhoSourceClassification.occurrence_id,
                   m.BankWhoSourceClassification.payment_instrument_id, m.BankWhoSourceClassification.transaction_reason_id)).all()),
            sorted(tuple(r) for r in db.execute(select(m.BankTransactionAllocation.financial_transaction_id,
                   m.BankTransactionAllocation.amount_minor)).all() if r[0] not in but))


def main() -> int:
    passed, failed = [], []

    def check(description, condition, detail=""):
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f"   [{str(detail)[:400]}]"))

    with SessionFactory() as db:
        before = preserved(db)
        account_service.create_account(db, username="sp_operator", display_name="sp_operator", password="OperatorPass123!",
                                       status="ACTIVE", is_admin=False)
        db.commit()
        op = db.query(m.RFOneAccount).filter_by(username="sp_operator").one()
        account_service.set_domain_access(db, account_id=op.id, domain_code="BANK", enabled=True, role_code=None,
                                          scope=m.DOMAIN_ACCESS_SCOPE_ALL)
        bank_amazon.ingest(db, [dict(file_name=_CSV.name, content=_CSV.read_bytes())], op.id)
        db.commit()
    client = web_app.app.test_client()
    client.post("/login", data={"username": "sp_operator", "password": "OperatorPass123!",
                                "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})
    page = client.get("/bank/split").data.decode()
    csrf = BANK_CSRF_RE.search(page).group(1)
    check("1. page with breadcrumb; Split is in the Bank menu",
          'aria-current="page">Split' in page and "/bank/split" in client.get("/bank").data.decode())

    data = client.get("/bank/split/data").get_json()
    certain = [r for r in data["movements"] if r["link"] == "CERTAIN"]
    check("2. certain links (code + amount + date) kept apart from candidates",
          data["ok"] and data["counts"]["CERTAIN"] == len(certain) >= 1
          and all(r["link"] != "CANDIDATE" or any(x["code"] == "LINK_CANDIDATE" for x in r["reasons"]) for r in data["movements"]),
          data["counts"])
    fans = next((r for r in certain if r["items"] == 3), None)
    check("3. the three identical fan rows stay three rows on one movement", fans is not None, certain)
    tid = fans["id"]
    d = client.get(f"/bank/split/{tid}/data").get_json()
    p = d["proposal"]
    check("4. one line for the whole movement, never 3 × the order total",
          len(p["lines"]) == 1 and p["lines"][0]["amount_minor"] == d["movement"]["amount_minor"] == p["total_minor"]
          and p["difference_minor"] == 0 and len(p["lines"][0]["items"]) == 3, p)
    check("5. without the products' WHY the split is incomplete and says why",
          p["status"] == "INCOMPLETE" and [r["code"] for r in p["reasons"]] == ["ITEM_WHY_MISSING"], p["reasons"])
    check("6. WHOM follows the existing logic (Source owner at the date)", d["whom"] is not None, d["movement"])

    total = d["movement"]["amount_minor"]
    why_a, why_b = d["whys"][0]["id"], d["whys"][1]["id"]
    half = total // 2
    good = [dict(amount_minor=half, why_id=why_a, description="Fan 1", items=p["lines"][0]["items"][:1]),
            dict(amount_minor=total - half, why_id=why_b, description="Fans 2-3", items=p["lines"][0]["items"][1:])]
    bad = [dict(good[0]), dict(good[1], amount_minor=good[1]["amount_minor"] + 1)]
    chk = client.post(f"/bank/split/{tid}/check", data={"csrf_token": csrf, "lines": json.dumps(bad)}).get_json()
    check("7. a difference of one cent is shown, never absorbed",
          chk["status"] == "INCOMPLETE" and chk["difference_minor"] == -1 and any(r["code"] == "DIFFERENCE_UNEXPLAINED" for r in chk["reasons"]), chk)
    draft = client.post(f"/bank/split/{tid}/draft", data={"csrf_token": csrf, "lines": json.dumps(
        [dict(good[0], amount_minor=None), good[1]])}).get_json()
    d = client.get(f"/bank/split/{tid}/data").get_json()
    check("8. an incomplete split is kept as a draft; nothing is allocated",
          draft.get("ok") and d["draft"]["id"] == draft["draft_id"] and d["allocations"] == [], d["draft"])
    r1 = client.post(f"/bank/split/{tid}/confirm", data={"csrf_token": csrf, "lines": json.dumps(good)})
    r2 = client.post(f"/bank/split/{tid}/confirm", data={"csrf_token": csrf, "lines": json.dumps(bad), "confirm": "yes"})
    check("9. confirmation needs an explicit yes and an exact split", r1.status_code in (400, 409) and r2.status_code in (400, 409))
    r3 = client.post(f"/bank/split/{tid}/confirm", data={"csrf_token": csrf, "lines": json.dumps(good), "confirm": "yes",
                                                         "evidence_kind": "AMAZON_ORDER", "evidence_reference": ",".join(fans["codes"])}).get_json()
    d = client.get(f"/bank/split/{tid}/data").get_json()
    check("10. confirmed: two allocations, exact total, products kept on each line",
          r3.get("ok") and len(d["allocations"]) == 2 and sum(a["amount_minor"] for a in d["allocations"]) == total
          and [len(a["items"]) for a in d["allocations"]] == [1, 2] and d["allocation_state"]["difference_minor"] == 0, d["allocations"])
    q = client.get(f"/bank/split/qbo-preview?ids={tid}").get_json()
    item = q["purchases"][0]
    check("11. QBO preview: ONE Purchase, two lines, total = lines, blocked until the QBO accounts are mapped",
          len(q["purchases"]) == 1 and item["line_count"] == 2 and item["lines_minor"] == total
          and round(item["payload"]["TotalAmt"] * 100) == abs(total)
          and round(sum(x["Amount"] for x in item["payload"]["Line"]) * 100) == abs(total)
          and {b["code"] for b in item["blockers"]} == {"CATEGORY_NOT_MAPPED", "PAYMENT_ACCOUNT_NOT_MAPPED"}, item)
    no_token = client.post(f"/bank/split/{tid}/draft", data={"lines": json.dumps(good)})
    check("12. writes need the CSRF token", no_token.status_code in (400, 403, 409))
    with SessionFactory() as db:
        check("13. no other movement, decision, rule, classification or allocation changed", preserved(db, but=(tid,)) == before[:4] + (
            [x for x in before[4] if x[0] != tid],), "")

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
