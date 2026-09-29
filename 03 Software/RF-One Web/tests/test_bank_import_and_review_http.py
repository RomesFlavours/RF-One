#!/usr/bin/env python
"""HTTP test for Bank Import and Review (BANK_IMPORT_AND_REVIEW_001).

`/bank` is the monthly operational page — Import, Check Sources, Automatic
WHO, Review Missing — for one selected month; Instructions and Instruments
are separate tabs. This file pins down:

  A. the Bank tab order;
  B/C. the selected month: previous LOCAL calendar month by default, or
       the year/month asked for;
  D. the Import section lists the month's source files;
  E. Check Sources shows the same completeness facts as Monthly Sources;
  F/G/H. `return_to` brings Monthly and Instrument actions back to their
       page, changes nothing without it, and can never name an arbitrary
       address;
  I/J. Automatic WHO is read-only, WHO-only, and counts the persisted
       decisions;
  K/L. Review Missing uses the Export's unresolved definition and links to
       Review for the same month;
  M/N/O. Instructions and Instruments hold what moved off `/bank`, and the
       instrument actions still work;
  P. `/bank` does not depend on Classification.

Runs against a DISPOSABLE SQLite database created here and deleted at the
end.
"""

from __future__ import annotations

import io
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_import_review_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "import-review-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import bank_routes  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import export as export_service  # noqa: E402
from rfone_data_store.bank_reconciliation import monthly_source  # noqa: E402
from rfone_data_store.bank_reconciliation import receiver_candidates  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')

AUGUST_CSV = (
    "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
    "DEBIT,08/05/2026,US FOODS INVOICE 1001,-412.50,ACH_DEBIT,9000.00,\n"
    "DEBIT,08/12/2026,AMAZON MKTPLACE PMTS,-58.20,DEBIT_CARD,8941.80,\n"
    "DEBIT,08/20/2026,SYSCO FOODS 2231,-230.00,ACH_DEBIT,8711.80,\n"
).encode("utf-8")
JUNE_CSV = (
    "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
    "DEBIT,06/10/2026,JUNE ONLY VENDOR,-10.00,ACH_DEBIT,100.00,\n"
).encode("utf-8")

APPROVED_TABS = [
    "Import and Review", "Instructions", "Instruments", "Review Transactions",
    "Monthly Sources", "Monthly Export", "Classification",
]


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found"
    return match.group(1)


def tab_labels(html: str) -> list[str]:
    nav = html[html.index('<nav class="module-tabs"'):]
    nav = nav[:nav.index("</nav>")]
    return [re.sub(r"\s+", " ", label).strip()
            for label in re.findall(r'class="module-tab[^"]*"[^>]*>([^<]+)</a>', nav)]


def section(html: str, start_id: str, end_id: str | None) -> str:
    begin = html.index(f'id="{start_id}"')
    end = html.index(f'id="{end_id}"') if end_id else len(html)
    return html[begin:end]


def summary_row(html: str) -> list[str]:
    """The six Monthly Sources summary figures, in page order."""
    at = html.index("<th>Missing / unresolved</th>")
    body = html[at:html.index("</tbody>", at)]
    return [re.sub(r"<[^>]+>", "", cell).strip() for cell in re.findall(r"<td>(.*?)</td>", body)]


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
        # ------------------------------------------------------------ fixture
        with SessionFactory() as db:
            account_service.create_account(
                db, username="ir_operator", display_name="Import Review Operator",
                password="OperatorPass123!", status="ACTIVE", is_admin=False,
            )
            db.commit()
            operator = db.query(m.RFOneAccount).filter_by(username="ir_operator").one()
            operator_id = operator.id
            account_service.set_domain_access(
                db, account_id=operator_id, domain_code="BANK", enabled=True, role_code=None,
            )
            checking = m.PaymentInstrument(
                display_name="Chase Checking 0214", instrument_type="BANK_ACCOUNT",
                institution="CHASE", last_four="0214", status="ACTIVE",
                effective_start_date=date(2026, 1, 1),
            )
            savings = m.PaymentInstrument(
                display_name="Chase Savings 5555", instrument_type="BANK_ACCOUNT",
                institution="CHASE", last_four="5555", status="ACTIVE",
                effective_start_date=date(2026, 1, 1),
            )
            idle = m.PaymentInstrument(
                display_name="Idle Card 9999", instrument_type="CREDIT_CARD",
                institution="CHASE", last_four="9999", status="ACTIVE",
                effective_start_date=date(2026, 1, 1),
            )
            db.add_all([checking, savings, idle])
            db.flush()
            monthly_source.set_control_start(db, year=2026, month=1, account_id=operator_id)
            db.commit()
            checking_id, savings_id, idle_id = checking.id, savings.id, idle.id

        client = web_app.app.test_client()
        client.post("/login", data={
            "username": "ir_operator", "password": "OperatorPass123!",
            "csrf_token": extract_csrf(client.get("/login").data),
        })

        # ------------------------------------------------ A — tab order
        page = client.get("/bank")
        html = page.data.decode("utf-8")
        check("A. /bank responds 200", page.status_code == 200, str(page.status_code))
        check("A. the Bank tabs are exactly the approved order",
              tab_labels(html) == APPROVED_TABS, str(tab_labels(html)))
        check("A. the same order on every Bank page",
              all(tab_labels(client.get(p).data.decode("utf-8")) == APPROVED_TABS
                  for p in ("/bank/instructions", "/bank/instruments", "/bank/review",
                            "/bank/monthly", "/bank/export")))

        # ------------------------------------ B — previous LOCAL month
        today_utc = datetime.now(timezone.utc).date()
        first = today_utc.replace(day=1)
        expected_year, expected_month = (first.year - 1, 12) if first.month == 1 else (first.year, first.month - 1)
        expected_label = date(expected_year, expected_month, 1).strftime("%B %Y")
        check("B. with no month asked for, /bank shows the previous calendar month",
              f'<h2 class="bank-month-title">{expected_label}</h2>' in html, expected_label)

        class _FixedNow(datetime):
            fixed = datetime(2026, 10, 1, 2, 0, tzinfo=timezone.utc)

            @classmethod
            def now(cls, tz=None):
                return cls.fixed if tz is None else cls.fixed.astimezone(tz)

        real_datetime = bank_routes.datetime
        bank_routes.datetime = _FixedNow
        try:
            new_york = bank_routes._previous_local_month("America/New_York")
            utc_based = bank_routes._previous_local_month(None)
        finally:
            bank_routes.datetime = real_datetime
        check("B. the previous month is taken from the Location's local date, not UTC "
              "(2026-10-01 02:00 UTC is still 30 September in New York -> August)",
              new_york == (2026, 8) and utc_based == (2026, 9), f"{new_york} {utc_based}")

        # ----------------------------------- C — explicit month selection
        html_aug = client.get("/bank?year=2026&month=8").data.decode("utf-8")
        check("C. an explicit year/month is shown",
              '<h2 class="bank-month-title">August 2026</h2>' in html_aug)
        check("C. previous / next navigation keeps to calendar months",
              'href="/bank?year=2026&amp;month=7"' in html_aug
              and 'href="/bank?year=2026&amp;month=9"' in html_aug)
        html_bad = client.get("/bank?year=2026&month=13").data.decode("utf-8")
        check("C. an impossible month falls back to the default month",
              f'<h2 class="bank-month-title">{expected_label}</h2>' in html_bad)

        # ------------------------------ upload through the page (+ return_to)
        csrf = extract_csrf(client.get("/bank?year=2026&month=8").data)
        resp = client.post("/bank/upload", data={
            "files": (io.BytesIO(AUGUST_CSV), "chase_0214_august.csv"),
            "payment_instrument_id": str(checking_id), "csrf_token": csrf,
            "return_to": "import_review", "year": "2026", "month": "8",
        }, content_type="multipart/form-data")
        check("F. an upload from Import and Review returns to the same month",
              resp.status_code == 302 and resp.headers["Location"] == "/bank?year=2026&month=8",
              resp.headers.get("Location", ""))
        resp = client.post("/bank/upload", data={
            "files": (io.BytesIO(JUNE_CSV), "chase_5555_june.csv"),
            "payment_instrument_id": str(savings_id), "csrf_token": csrf,
        }, content_type="multipart/form-data")
        check("G. an upload without return_to redirects exactly as before",
              resp.status_code == 302 and resp.headers["Location"] == "/bank",
              resp.headers.get("Location", ""))

        # --------------------------------------- D — month-relevant batches
        html_aug = client.get("/bank?year=2026&month=8").data.decode("utf-8")
        import_part = section(html_aug, "step-import", "step-sources")
        check("D. the August file is listed in the Import section for August",
              "chase_0214_august.csv" in import_part)
        check("D. the June file is not listed for August (it needs no action)",
              "chase_5555_june.csv" not in import_part)
        html_jun = client.get("/bank?year=2026&month=6").data.decode("utf-8")
        check("D. the June file is listed for June",
              "chase_5555_june.csv" in section(html_jun, "step-import", "step-sources"))
        html_all = client.get("/bank?year=2026&month=8&batches=all").data.decode("utf-8")
        all_part = section(html_all, "step-import", "step-sources")
        check("D. the all-files view lists every source file",
              "chase_0214_august.csv" in all_part and "chase_5555_june.csv" in all_part)

        # ----------------------------- E — same completeness facts as Monthly
        monthly_html = client.get("/bank/monthly?year=2026&month=8").data.decode("utf-8")
        sources_part = section(html_aug, "step-sources", "step-who")
        with SessionFactory() as db:
            period = monthly_source.get_period(db, 2026, 8)
            report = monthly_source.evaluate(db, period)
            period_id = period.id
            expected_row = [str(report.expected), str(report.received),
                            str(report.resolved_without_file), str(report.not_expected),
                            str(report.needs_confirmation), str(report.missing_unresolved)]
            idle_coverage_id = db.scalars(
                select(m.BankMonthlyInstrumentCoverage.id).where(
                    m.BankMonthlyInstrumentCoverage.period_id == period_id,
                    m.BankMonthlyInstrumentCoverage.payment_instrument_id == idle_id,
                )
            ).one()
        check("E. Check Sources shows the same six figures as Monthly Sources",
              summary_row(sources_part) == summary_row(monthly_html) == expected_row,
              f"{summary_row(sources_part)} {summary_row(monthly_html)} {expected_row}")
        check("E. the unexplained idle card is named as a blocker on /bank",
              "Idle Card 9999" in sources_part and "cannot be completed yet" in sources_part)
        check("E. Control Start / Validated Through are configured only on Monthly Sources",
              'name="control_start_date"' not in html_aug
              and 'name="validated_through_month"' not in html_aug
              and 'name="control_start_date"' in monthly_html)
        check("E. the Monthly forms rendered inside /bank carry return_to=import_review",
              sources_part.count('name="return_to" value="import_review"') >= 2)
        check("E. the same forms on Monthly Sources carry no return_to",
              'name="return_to"' not in monthly_html)

        # ------------------------------- F/G/H — Monthly return_to behaviour
        csrf = extract_csrf(client.get("/bank?year=2026&month=8").data)
        resolve_url = f"/bank/monthly/{period_id}/coverage/{idle_coverage_id}/resolve"
        clear_url = f"/bank/monthly/{period_id}/coverage/{idle_coverage_id}/clear"
        resp = client.post(resolve_url, data={
            "csrf_token": csrf, "resolution": "SOURCE_FILE_MISSING", "return_to": "import_review",
        })
        check("F. a resolution recorded from /bank returns to /bank for the same month",
              resp.status_code == 302 and resp.headers["Location"] == "/bank?year=2026&month=8",
              resp.headers.get("Location", ""))
        resp = client.post(clear_url, data={"csrf_token": csrf})
        check("G. the same action from Monthly Sources keeps its redirect exactly",
              resp.status_code == 302
              and resp.headers["Location"] == "/bank/monthly?year=2026&month=8",
              resp.headers.get("Location", ""))
        resp = client.post(f"/bank/monthly/{period_id}/complete", data={
            "csrf_token": csrf, "return_to": "import_review",
        })
        check("F. Complete Month from /bank returns to /bank for the same month",
              resp.headers.get("Location") == "/bank?year=2026&month=8",
              resp.headers.get("Location", ""))
        resp = client.post("/bank/monthly/select", data={
            "csrf_token": csrf, "year": "2026", "month": "3", "return_to": "import_review",
        })
        check("F. opening a month from /bank returns to /bank for that month",
              resp.headers.get("Location") == "/bank?year=2026&month=3",
              resp.headers.get("Location", ""))
        resp = client.post("/bank/monthly/select", data={
            "csrf_token": csrf, "year": "2026", "month": "4",
        })
        check("G. opening a month from Monthly Sources keeps its redirect exactly",
              resp.headers.get("Location") == "/bank/monthly?year=2026&month=4",
              resp.headers.get("Location", ""))

        hostile = ["https://evil.example/", "//evil.example", "/bank/../evil", "javascript:alert(1)",
                   "IMPORT_REVIEW", "import_review ", "instruments/../../x", " "]
        locations = []
        for value in hostile:
            r = client.post(clear_url, data={"csrf_token": csrf, "return_to": value})
            locations.append(r.headers.get("Location", ""))
        check("H. an unsupported return_to value never becomes the redirect target",
              all(loc == "/bank/monthly?year=2026&month=8" or loc == "/bank?year=2026&month=8"
                  for loc in locations) and not any("evil" in loc or "javascript" in loc
                                                   for loc in locations),
              str(locations))
        check("H. only the exact value import_review is accepted (upper-case or padded "
              "variants are refused)",
              locations[4] == locations[5] == "/bank/monthly?year=2026&month=8", str(locations[4:6]))
        r = client.post("/bank/monthly/select", data={
            "csrf_token": csrf, "year": "2101", "month": "2", "return_to": "import_review",
        })
        check("H. a month outside the page's range lands on /bank itself, with no month",
              r.headers.get("Location") == "/bank", r.headers.get("Location", ""))
        r = client.post("/bank/instruments/new", data={
            "csrf_token": csrf, "institution": "CHASE", "display_name": "Hostile Return Card",
            "instrument_type": "CREDIT_CARD", "return_to": "https://evil.example/",
        })
        check("H. an Instrument action with a foreign return_to keeps its own redirect",
              r.headers.get("Location") == "/bank", r.headers.get("Location", ""))

        # ------------------------------------------------ WHO fixture
        with SessionFactory() as db:
            txns = {t.description_original: t for t in db.scalars(
                select(m.FinancialTransaction).where(
                    m.FinancialTransaction.payment_instrument_id == checking_id))}
            occ_type = m.BankOccurrenceType(code="SUPPLIER", name="Supplier")
            db.add(occ_type)
            db.flush()
            us_foods = m.BankOccurrence(canonical_name="US Foods", occurrence_type_id=occ_type.id,
                                        status="ACTIVE")
            amazon = m.BankOccurrence(canonical_name="Amazon", occurrence_type_id=occ_type.id,
                                      status="ACTIVE")
            db.add_all([us_foods, amazon])
            db.flush()
            recognition.record_human_decision(db, recognition.HumanDecisionRequest(
                transaction_id=txns["US FOODS INVOICE 1001"].id, occurrence_id=us_foods.id,
                confirmed_by_account_id=operator_id, learn_description=False,
            ))
            reason_id = db.scalars(select(m.BankTransactionReason.id)).first()
            amazon_txn = txns["AMAZON MKTPLACE PMTS"]
            recognition.create_or_reuse_rule(
                db, match_type=recognition.EXACT_NORMALIZED_DESCRIPTION,
                normalized_pattern=recognition.normalize_description_for_recognition(
                    amazon_txn.description_original),
                occurrence_id=amazon.id, transaction_reason_id=reason_id,
                payment_instrument_id=None, direction=None, auto_apply_enabled=True,
                created_from_transaction_id=None,
            )
            recognition.redecide_for_transaction(db, amazon_txn)
            db.commit()

        # ----------------------------------- I/J — Automatic WHO section
        html_aug = client.get("/bank?year=2026&month=8").data.decode("utf-8")
        who_part = section(html_aug, "step-who", "step-review")
        check("I. the Automatic WHO section has no form and no action",
              "<form" not in who_part and 'method="post"' not in who_part)
        check("I. the Automatic WHO section never mentions WHY or WHAT",
              not re.search(r"\b(why|what)\b", re.sub(r"<[^>]+>", " ", who_part), re.I),
              re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", who_part))[:300])
        check("I. bulk authorization is stated as pending a functional decision",
              "Bulk authorization &mdash; pending functional decision" in who_part)
        shown = {k: int(v) for k, v in re.findall(
            r'data-who-count="(\w+)">(\d+)<', who_part)}
        with SessionFactory() as db:
            scope = export_service.in_scope_transactions(db, 2026, 8)
            expected = {"learned_rule": 0, "human": 0, "other_automatic": 0, "missing": 0}
            for t in scope:
                e = db.get(m.BankTransactionExplanation, t.explanation_id) if t.explanation_id else None
                if e is None or e.occurrence_id is None:
                    expected["missing"] += 1
                elif e.decision_source == "HUMAN":
                    expected["human"] += 1
                elif e.recognition_rule_id is not None:
                    expected["learned_rule"] += 1
                else:
                    expected["other_automatic"] += 1
        check("J. the WHO counts equal the persisted current decisions",
              shown.get("learned_rule") == expected["learned_rule"] == 1
              and shown.get("human") == expected["human"] == 1
              and shown.get("missing") == expected["missing"] == 1
              and shown.get("other_automatic", 0) == expected["other_automatic"] == 0,
              f"shown={shown} expected={expected}")

        # ------------------------------------ K/L — Review Missing section
        review_part = section(html_aug, "step-review", None)
        shown_unresolved = int(re.search(r"data-unresolved-count>(\d+)<", review_part).group(1))
        with SessionFactory() as db:
            unresolved = export_service.unresolved_transactions(db, year=2026, month=8)
            missing_who = [b for b in export_service.compute_export_blockers(db, year=2026, month=8)
                           if b.reason.startswith("Missing Who:")]
        check("K. Review Missing counts the Export's unresolved transactions",
              shown_unresolved == len(unresolved) == len(missing_who) == 3,
              f"{shown_unresolved} {len(unresolved)} {len(missing_who)}")
        check("L. the Review links keep the selected year and month",
              who_part.count('href="/bank/review?year=2026&amp;month=8"') == 1
              and review_part.count('href="/bank/review?year=2026&amp;month=8"') == 1)
        review = client.get("/bank/review?year=2026&month=8")
        check("L. the linked Review opens on that month's transactions",
              review.status_code == 200 and b"AMAZON MKTPLACE PMTS" in review.data
              and b"JUNE ONLY VENDOR" not in review.data)

        # --------------------------------------------- M — Instructions
        instructions = client.get("/bank/instructions")
        text = instructions.data.decode("utf-8")
        check("M. /bank/instructions responds 200", instructions.status_code == 200)
        check("M. Instructions is read-only (no form)", "<form" not in text)
        for phrase in ("What source files to load", "Import</strong>", "Check Sources</strong>",
                       "Automatic WHO</strong>", "Review Missing</strong>",
                       "One question only", "never closes or deactivates",
                       "Controlled</strong>", "Historical</strong>", "Provisional</strong>",
                       "WHO means identity, not purpose", "Manual review",
                       "Saved source rules", "Accounting deduplication",
                       "No raw row is ever deleted"):
            check(f"M. Instructions explains: {phrase}", phrase in text)
        check("M. the long explanations are no longer on the operational pages",
              all(p not in html_aug and p not in monthly_html
                  for p in ("One question only", "No raw row is ever deleted",
                            "kept permanently for historical audit")))
        check("M. POST to /bank/instructions is not allowed",
              client.post("/bank/instructions", data={"csrf_token": csrf}).status_code == 405)

        # ------------------------------------------------ N — Instruments
        instruments_html = client.get("/bank/instruments").data.decode("utf-8")
        for heading in ("<h2>Payment Instruments</h2>", "<h3>Add a Payment Instrument</h3>",
                        "<h2>Saved source rules</h2>", "<h2>Instrument assignment history</h2>",
                        "<h2>Accounting deduplication</h2>"):
            check(f"N. Instruments shows {heading}", heading in instruments_html)
            check(f"N. /bank no longer shows {heading}", heading not in html_aug)
        check("N. Instruments forms return to Instruments",
              instruments_html.count('name="return_to" value="instruments"') >= 2)

        # ------------------------------------- O — instrument actions work
        csrf = extract_csrf(instruments_html.encode("utf-8"))
        r = client.post("/bank/instruments/new", data={
            "csrf_token": csrf, "institution": "CHASE", "display_name": "Chase Card 1234",
            "instrument_type": "CREDIT_CARD", "last_four": "1234", "return_to": "instruments",
        })
        check("O. adding an instrument from Instruments returns to Instruments",
              r.headers.get("Location") == "/bank/instruments", r.headers.get("Location", ""))
        check("O. the instrument was created and is listed",
              "Chase Card 1234" in client.get("/bank/instruments").data.decode("utf-8"))
        r = client.post("/bank/instruments/new", data={
            "csrf_token": csrf, "institution": "CHASE", "display_name": "Chase Card 5678",
            "instrument_type": "CREDIT_CARD", "last_four": "5678",
        })
        check("O. without return_to the add action keeps its old redirect (/bank)",
              r.headers.get("Location") == "/bank", r.headers.get("Location", ""))
        r = client.post("/bank/accounting-dedup/recompute", data={
            "csrf_token": csrf, "return_to": "instruments",
        })
        check("O. recompute deduplication from Instruments returns to Instruments",
              r.headers.get("Location") == "/bank/instruments", r.headers.get("Location", ""))
        edit_html = client.get(f"/bank/instruments/{checking_id}/edit").data.decode("utf-8")
        check("O. the edit page belongs to Instruments and saves back to it",
              "module-tab is-active" in edit_html
              and re.search(r'module-tab is-active"\s+href="/bank/instruments"', edit_html) is not None
              and 'name="return_to" value="instruments"' in edit_html,
              "")

        # ------------------------------------------ P — no Classification
        def refuse(*_args, **_kwargs):
            raise AssertionError("build_candidates must not run for /bank")

        original = receiver_candidates.build_candidates
        receiver_candidates.build_candidates = refuse
        try:
            resp = client.get("/bank?year=2026&month=8")
        finally:
            receiver_candidates.build_candidates = original
        body = resp.data.decode("utf-8")
        check("P. /bank renders without ever building Classification candidates",
              resp.status_code == 200, str(resp.status_code))
        main_content = body[body.index("</nav>", body.index('<nav class="module-tabs"')):]
        check("P. no Classification content or link inside /bank (only the tab)",
              "/bank/classification" not in main_content and "Receiver" not in main_content)
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
