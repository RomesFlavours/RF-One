"""Free search in Review > To Reconcile and Reconciled (BANK_REVIEW_SEARCH_001).

Proves, on a throwaway database, that `q`:

* matches, partially and case-insensitively, ONLY the description, the
  current WHO name, the current WHY name and the Source name;
* is literal (`%`, `_`, `*`, apostrophes), outer spaces ignored, empty = no
  search;
* is ANDed with month and Source, on the whole filtered set — before the row
  limit — with the count and the per-currency total of every result, each
  transaction once;
* says "No transactions match your search" and keeps search and filters;
* is kept by the tabs, the filters and the actions, and × clears only it.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_review_search_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-review-search-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from html import unescape  # noqa: E402

from sqlalchemy import select  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.bank_reconciliation import review_queues  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
AUG, SEP = date(2026, 8, 12), date(2026, 9, 3)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    try:
        with SessionFactory() as s:
            account_service.create_account(s, username="searcher", display_name="Searcher",
                                           password="SearchPass123!", status="ACTIVE", is_admin=False)
            s.flush()
            operator = s.query(m.RFOneAccount).filter_by(username="searcher").one()
            account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True,
                                              role_code=None)
            legal = m.LegalEntity(legal_name="Search LLC", status="ACTIVE")
            s.add(legal)
            s.flush()
            usd = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                      display_name="Alpha Checking", institution="CHASE", last_four="0001", currency="USD")
            eur = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                      display_name="Beta Euro Account", institution="CHASE", last_four="0002", currency="EUR")
            s.add_all([usd, eur])
            s.flush()
            batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="seed.csv",
                                      raw_file_bytes=b"x", sha256="5" * 64, status="NORMALIZED",
                                      payment_instrument_id=usd.id)
            s.add(batch)
            s.flush()
            counterparty = s.scalars(select(m.BankOccurrenceType).where(
                m.BankOccurrenceType.code == "COUNTERPARTY")).one()
            who = m.BankOccurrence(canonical_name="Zeta Linen Service", occurrence_type_id=counterparty.id,
                                   status="ACTIVE")
            s.add(who)
            s.flush()
            why = s.scalars(select(m.BankTransactionReason).where(
                m.BankTransactionReason.status == "ACTIVE").order_by(m.BankTransactionReason.id)).first()
            seq = [0]

            def tx(description, amount, *, source=usd, day=AUG, with_who=False):
                seq[0] += 1
                t = m.FinancialTransaction(
                    payment_instrument_id=source.id, bank_source="CHASE_BANK_ACCOUNT", import_batch_id=batch.id,
                    posting_date=day, transaction_date=day, description_original=description,
                    description_normalized=description, amount_minor=amount, status="COMPLETED",
                    duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                    fingerprint=f"search-{seq[0]}", classification="UNKNOWN")
                s.add(t)
                s.flush()
                if with_who:
                    # Two decisions in its history: the current one counts, once.
                    for _ in range(2):
                        recognition._create_decision_row(
                            s, t, occurrence_id=who.id, transaction_reason_id=why.id, recognition_rule_id=None,
                            decision_source="RULE", decision_status="NEEDS_HUMAN_REVIEW", confidence=None,
                            explanation_notes="seed", accounting_classification_id=why.accounting_classification_id,
                            accounting_destination_source=m.DESTINATION_SOURCE_WHY)
                return t

            rows = {
                "paypal": tx("PAYPAL *TRUTHFINDER", -1999),
                "percent": tx("50% OFF STORE", -500),
                "under": tx("ACH_DEBIT VENDOR", -700),
                "apos": tx("O'NEIL HARDWARE", -1200),
                "star": tx("SQ *COFFEE", -350),
                "euro": tx("CAFE PARIS", -2000, source=eur),
                "linen": tx("CARD 4411 PURCHASE", -3300, with_who=True),
                "linen2": tx("CARD 4412 PURCHASE", 1300, source=eur, with_who=True),
                "sep": tx("PAYPAL *TRUTHFINDER", -999, day=SEP),
            }
            # 520 newer rows push a needle beyond the 500-row limit.
            for i in range(520):
                tx(f"FILLER ROW {i}", -1, day=date(2026, 8, 28))
            rows["needle"] = tx("HIDDEN NEEDLE DEEP", -4242, day=date(2026, 8, 1))
            s.commit()
            ids = {k: t.id for k, t in rows.items()}
            ids.update(usd=usd.id, eur=eur.id, who=who.id, why=why.id)
            why_name = why.name

        client = web_app.app.test_client()
        csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
        client.post("/login", data={"username": "searcher", "password": "SearchPass123!", "csrf_token": csrf})

        def get(view, **args):
            args = {k: v for k, v in args.items() if v is not None}
            return unescape(client.get("/bank/review", query_string=dict(view=view, **args)).data.decode())

        def row_ids(html):
            return {int(x) for x in re.findall(r'data-transaction-id="(\d+)"', html)}

        def count(html):
            found = re.search(r'data-search-count="(\d+)"', html)
            return int(found.group(1)) if found else None

        # ---------------------------------------------------------- basics
        plain = get("to_reconcile", year=2026, month=8)
        check("1. no search: the page is as before (no search result line), with the search field",
              count(plain) is None and 'placeholder="Description, WHO, WHY, Source"' in plain
              and ">Search transactions<" in plain and ">Search</button>" in plain)
        html = get("to_reconcile", q="  paypal *truth  ")
        check("2. partial, case-insensitive, outer spaces ignored (both PayPal rows, all months)",
              {ids["paypal"], ids["sep"]} <= row_ids(html) and count(html) == 2
              and 'value="paypal *truth"' in html, str(count(html)))

        # ------------------------------------------------- the four fields
        check("3a. description", count(get("to_reconcile", q="hardware")) == 1)
        check("3b. WHO name (Reconciled)", count(get("reconciled", q="zeta linen")) == 2
              and {ids["linen"], ids["linen2"]} <= row_ids(get("reconciled", q="zeta linen")))
        check("3c. WHY name (Reconciled)", count(get("reconciled", q=why_name[2:-1].lower())) == 2, why_name)
        check("3d. Source name", count(get("to_reconcile", q="beta euro")) == 1
              and ids["euro"] in row_ids(get("to_reconcile", q="beta euro")))
        check("3e. nothing outside the four fields (the bank_source code, an amount)",
              count(get("to_reconcile", q="CHASE_BANK")) == 0 and count(get("to_reconcile", q="19.99")) == 0)

        # ----------------------------------------------------------- literal
        check("4a. % is literal", count(get("to_reconcile", q="50%")) == 1
              and count(get("to_reconcile", q="%")) == 1)
        check("4b. _ is literal", count(get("to_reconcile", q="_")) == 1
              and count(get("to_reconcile", q="ACH_D")) == 1)
        check("4c. apostrophe and * are literal", count(get("to_reconcile", q="o'neil")) == 1
              and count(get("to_reconcile", q="sq *c")) == 1 and count(get("to_reconcile", q="sq c")) == 0)

        # ------------------------------------------------------ with filters
        check("5a. AND with the month", count(get("to_reconcile", q="truthfinder", year=2026, month=9)) == 1
              and row_ids(get("to_reconcile", q="truthfinder", year=2026, month=9)) == {ids["sep"]})
        check("5b. AND with the Source", count(get("to_reconcile", q="cafe", payment_instrument_id=ids["usd"])) == 0
              and count(get("to_reconcile", q="cafe", payment_instrument_id=ids["eur"])) == 1)
        html = get("to_reconcile", q="needle")
        check("5c. the whole filtered set is searched, before the 500-row limit",
              ids["needle"] in row_ids(html) and ids["needle"] not in row_ids(get("to_reconcile")))

        # ------------------------------------------------- count and totals
        html = get("reconciled", q="purchase")
        check("6. count and total per currency over all results, each transaction once",
              count(html) == 2 and 'data-search-total="USD">-33.00<' in html
              and 'data-search-total="EUR">13.00<' in html, html[html.find("review-search-result"):][:400])
        with SessionFactory() as s:
            summary = review_queues.search_summary(s, review_queues.TO_RECONCILE,
                                                   review_queues.ReviewFilters(search="filler"))
        check("6b. the total counts every result, not only the rows shown",
              summary["count"] == 520 and summary["totals"] == [{"currency": "USD", "count": 520, "total_minor": -520}],
              str(summary))

        # -------------------------------------------------------- no result
        html = get("reconciled", q="no such thing", year=2026, month=8, payment_instrument_id=ids["usd"])
        check("7. no result: the message, with search and filters still shown",
              "No transactions match your search" in html and 'value="no such thing"' in html
              and f'<option value="{ids["usd"]}" selected' in html and 'name="year" value="2026"' in html)

        # --------------------------------------------- kept / cleared search
        html = get("to_reconcile", q="paypal", year=2026, month=8, payment_instrument_id=ids["usd"])
        clear = re.search(r'class="review-search-clear"[^>]*href="([^"]+)"', html)
        clear_args = parse_qs(urlparse(clear.group(1)).query) if clear else {}
        check("8. × clears only the search: month and Source kept",
              clear is not None and "q" not in clear_args and clear_args.get("year") == ["2026"]
              and clear_args.get("payment_instrument_id") == [str(ids["usd"])], str(clear_args))
        tabs = re.findall(r'class="review-tab[^"]*"\s+href="([^"]+)"', html)
        check("9a. the tabs and the filter form keep the search",
              tabs and all("q=paypal" in t for t in tabs) and '<input type="hidden" name="q" value="paypal">' in html)
        resp = client.post(f"/bank/transactions/{ids['paypal']}/who-why", data={
            "csrf_token": CSRF_RE.search(html).group(1), "occurrence_id": str(ids["who"]),
            "transaction_reason_id": str(ids["why"]),
            "return_to": f"/bank/review?view=to_reconcile&year=2026&month=8&q=paypal"})
        check("9b. after an action the page comes back with the search", "q=paypal" in resp.headers.get("Location", ""),
              resp.headers.get("Location", ""))
        check("10. the search writes nothing (only the action above changed one row)",
              count(get("reconciled", q="truthfinder")) == 1)
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
