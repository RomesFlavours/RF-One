"""Review lists: sort by Instrument, Date, Description, Amount (BANK_REVIEW_SORT_001).

Proves, on a throwaway database, that the server sorts To Reconcile and
Reconciled after the filters and BEFORE the 500-row limit; Amount as a signed
number (-1000, -20, 0, 5, 100), texts case-insensitively, dates as dates;
missing values last; equal values in a stable id order; invalid parameters
fall back to the default order without an error; counts and the search
totals do not change; the headers are links that keep the search and the
filters, and the tabs / filter and search forms keep the sort; Source is not
sortable.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date
from html import unescape
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_review_sort_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-review-sort-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from sqlalchemy import select  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.bank_reconciliation import review_queues  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    try:
        with SessionFactory() as s:
            account_service.create_account(s, username="sorter", display_name="Sorter",
                                           password="SortPass123!", status="ACTIVE", is_admin=False)
            s.flush()
            operator = s.query(m.RFOneAccount).filter_by(username="sorter").one()
            account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True,
                                              role_code=None)
            legal = m.LegalEntity(legal_name="Sort LLC", status="ACTIVE")
            s.add(legal)
            s.flush()
            zulu = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                       display_name="zulu Checking", institution="CHASE", last_four="0001", currency="USD")
            alpha = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                        display_name="Alpha Savings", institution="CHASE", last_four="0002", currency="USD")
            s.add_all([zulu, alpha])
            s.flush()
            batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="seed.csv",
                                      raw_file_bytes=b"x", sha256="2" * 64, status="NORMALIZED",
                                      payment_instrument_id=zulu.id)
            s.add(batch)
            s.flush()
            counterparty = s.scalars(select(m.BankOccurrenceType).where(
                m.BankOccurrenceType.code == "COUNTERPARTY")).one()
            who = m.BankOccurrence(canonical_name="Sorted WHO", occurrence_type_id=counterparty.id, status="ACTIVE")
            s.add(who)
            s.flush()
            seq = [0]

            def tx(description, amount, day, source=zulu, with_who=False):
                seq[0] += 1
                t = m.FinancialTransaction(
                    payment_instrument_id=source.id, bank_source="CHASE_BANK_ACCOUNT", import_batch_id=batch.id,
                    posting_date=day, transaction_date=day, description_original=description,
                    description_normalized=description, amount_minor=amount, status="COMPLETED",
                    duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                    fingerprint=f"sort-{seq[0]}", classification="UNKNOWN")
                s.add(t)
                s.flush()
                if with_who:
                    recognition._create_decision_row(
                        s, t, occurrence_id=who.id, transaction_reason_id=None, decision_source="RULE", decision_status="NEEDS_HUMAN_REVIEW", confidence=None,
                        explanation_notes="seed", accounting_destination_source=m.DESTINATION_SOURCE_WHY)
                return t

            # The five amounts, oldest first so the default order would push
            # them past the 500-row limit.
            sortme = {a: tx(f"SORTME {d}", a, date(2026, 8, i + 1), source=alpha if i % 2 else zulu).id
                      for i, (a, d) in enumerate(((100, "cherry"), (-20, "Banana"), (5, "apple"),
                                                  (0, "date"), (-1000, "Elder")))}
            tie_a = tx("SORTME tie", 5, date(2026, 8, 10)).id
            empty = tx("", 7, date(2026, 8, 11)).id
            for i in range(520):
                tx(f"FILLER {i}", -1, date(2026, 8, 28))
            reconciled = [tx(f"RECON {n}", a, date(2026, 8, 15 + i), with_who=True).id
                          for i, (n, a) in enumerate((("b", 30), ("a", -40), ("c", 10)))]
            s.commit()

        client = web_app.app.test_client()
        csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
        client.post("/login", data={"username": "sorter", "password": "SortPass123!", "csrf_token": csrf})

        def get(view="to_reconcile", **args):
            return unescape(client.get("/bank/review", query_string=dict(view=view, **args)).data.decode())

        def order(html, view="to_reconcile"):
            attr = r'<tr id="t-(\d+)"' if view == "to_reconcile" else r'<tr[^>]*id="t-(\d+)"'
            return [int(x) for x in re.findall(attr, html)]

        def amounts_of(html):
            return [int(round(float(x) * 100)) for x in re.findall(r'class="col-amount">(-?[\d.]+)<', html)]

        page = get(q="SORTME")
        check("1. Instrument, Date, Description, Amount are links; Source is not",
              all(f'data-sort="{k}"' in page for k in ("instrument", "date", "description", "amount"))
              and "<th>Source</th>" in page and 'data-sort="source"' not in page)
        asc = get(q="SORTME", sort="amount", dir="asc")
        desc = get(q="SORTME", sort="amount", dir="desc")
        check("2. Amount ascending is numeric with its sign: -1000, -20, 0, 5, 5, 100",
              amounts_of(asc) == [-1000, -20, 0, 5, 5, 100], str(amounts_of(asc)))
        check("3. Amount descending is the reverse", amounts_of(desc) == [100, 5, 5, 0, -20, -1000], str(amounts_of(desc)))
        five_asc = [i for i in order(asc) if i in (sortme[5], tie_a)]
        five_desc = [i for i in order(desc) if i in (sortme[5], tie_a)]
        check("4. equal values keep a stable id order", five_asc == sorted(five_asc) and five_desc == sorted(five_desc, reverse=True))
        check("5. the arrow and aria-sort follow the order; the next click on Amount goes descending",
              'aria-sort="ascending"' in asc and "↑" in asc and 'aria-sort="descending"' in desc and "↓" in desc
              and re.search(r'data-sort="amount"\s+href="[^"]*dir=desc', asc) is not None)
        names = re.findall(r'class="col-description">([^<]*)<', get(q="SORTME", sort="description", dir="asc"))
        check("6. Description A–Z without case: apple, Banana, cherry, date, Elder, tie",
              names == ["SORTME apple", "SORTME Banana", "SORTME cherry", "SORTME date", "SORTME Elder", "SORTME tie"], str(names))
        dates = re.findall(r'class="col-date">([^<]*)<', get(q="SORTME", sort="date", dir="asc"))
        check("7. Date oldest first, chronologically", dates == sorted(dates) and dates[0] == "2026-08-01", str(dates))
        inst = re.findall(r'class="source-name">([^<]*)<', get(q="SORTME", sort="instrument", dir="asc"))
        check("8. Instrument A–Z without case (Alpha before zulu)", inst == sorted(inst, key=str.casefold)
              and inst[0] == "Alpha Savings", str(inst))
        with SessionFactory() as s:
            every = review_queues.ReviewFilters()
            all_desc = [t.id for t in review_queues.queue(s, review_queues.TO_RECONCILE, every, limit=10000,
                                                          sort="description", direction="desc")]
            all_asc = [t.id for t in review_queues.queue(s, review_queues.TO_RECONCILE, every, limit=10000,
                                                         sort="description", direction="asc")]
        check("9. a missing description is last in both directions", all_desc[-1] == empty and all_asc[-1] == empty)
        top = order(get(sort="amount", dir="desc"))
        check("10. sorted on the server BEFORE the 500-row limit: the oldest row, amount 100, comes first",
              len(top) == 500 and top[0] == sortme[100] and sortme[100] not in order(get())[:500])
        default = order(get())
        bad = get(sort="id; DROP TABLE x", dir="up")
        check("11. invalid parameters: the default order, no error, no arrow",
              order(bad) == default and "↑" not in bad and "↓" not in bad)
        tabs_plain = re.findall(r'class="review-tab[^"]*"[^>]*>([^<]*)<', get(month=8, year=2026))
        tabs_sorted = re.findall(r'class="review-tab[^"]*"[^>]*>([^<]*)<', get(month=8, year=2026, sort="amount", dir="desc"))
        sum_plain = re.search(r'data-search-count="(\d+)"', get(q="SORTME"))
        sum_sorted = re.search(r'data-search-count="(\d+)"', get(q="SORTME", sort="amount", dir="desc"))
        check("12. sorting does not change counts or the search totals",
              tabs_plain == tabs_sorted and sum_plain.group(1) == sum_sorted.group(1) == "6", str((tabs_plain, tabs_sorted)))
        page = get(q="SORTME", year=2026, month=8, payment_instrument_id=1, sort="date", dir="asc")
        link = re.search(r'data-sort="amount"\s+href="([^"]+)"', page).group(1)
        args = parse_qs(urlparse(link).query)
        tabs = re.findall(r'class="review-tab[^"]*"\s+href="([^"]+)"', page)
        check("13. a header keeps the search and the filters; tabs, Filter and Search keep the sort",
              args.get("q") == ["SORTME"] and args.get("month") == ["8"] and args.get("payment_instrument_id") == ["1"]
              and all("sort=date" in t and "dir=asc" in t for t in tabs)
              and page.count('<input type="hidden" name="sort" value="date">') == 2)
        rec = get("reconciled", sort="amount", dir="asc")
        check("14. Reconciled sorts the same way (amount ascending: -40, 10, 30)",
              [i for i in order(rec, "reconciled") if i in reconciled] == [reconciled[1], reconciled[2], reconciled[0]]
              and 'data-sort="instrument"' in rec, str(order(rec, "reconciled")))
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
