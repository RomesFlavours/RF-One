#!/usr/bin/env python
"""HTTP test for Upload and Reconcile (BANK_UPLOAD_AND_RECONCILE_001), on a DISPOSABLE SQLite database.

The whole daily path with no month chosen: a mixed upload, files settled one by one, repeated and fuller files
without duplicates (three identical purchases kept); completeness from the files actually received (declared and
inferred periods, a Source without history, an opening not proven by the first movement, a whole month without
file, a missing statement between two declared ones, no future days asked, Amazon dependency) with traced factual
answers; the one gate refusing every secondary endpoint until the data are ready; the real engine; the internet
research (Rules -> text -> internet, WHO kept, generic WHO, provider error and resumption without repeating calls,
answers not reused when the catalog changes, authorization asked first); two quadratures; proposals confirmed
without touching a person's decision; QuickBooks Online (chart, reusable correspondences, purchases, deposit,
refund, transfer once, journal-entry file, duplicates and changes after export); permissions and How Works.
The ChatGPT adapter is replaced by a local fake: nothing leaves this PC.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

_FOLDER = tempfile.mkdtemp(prefix="rfoneweb_upload_reconcile_")
_DB = os.path.join(_FOLDER, "rfone.db")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_DB.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "upload-reconcile-test-secret"
os.environ.update(RFONE_BANK_GUIDED="1", RFONE_BANK_SINGLE_ENGINE="1", CBANK_BANK_DB=_DB,
                  CBANK_STORE_DIR=os.path.join(_FOLDER, "store"), CBANK_AUTO_RUN="0", CBANK_WHO_WHY="1",
                  CBANK_BANK_CODE_ROOT=str(Path(APP_DIR).parents[1]))

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import bank_chatgpt  # noqa: E402
import bank_work_routes  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select, text  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import (card_configuration, configuration as config_service,  # noqa: E402
                                                  intake, recognition)
from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
CARD = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
BANK = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
AMAZON = "Order Date,Order ID,Title,ASIN,Charge Identifier,Payment Date,Order Net Total\n"
FANS = "".join("09/12/2026,09/12/2026,AMAZON MKTPL*AB12CD34E,Home,Sale,-95.41,\n" for _ in range(3))
CARD_SEP = (CARD + "09/02/2026,09/02/2026,STARBUCKS 12,Food,Sale,-5.00,\n" + FANS
            + "09/25/2026,09/25/2026,AUTOMATIC PAYMENT - THANK,,Payment,200.00,\n"
            + "09/28/2026,09/28/2026,HOME DEPOT 44,Home,Sale,-80.00,\n")
CARD_SEP_OCT = (CARD_SEP + "10/02/2026,10/02/2026,PUBLIX 1661,Groceries,Sale,-30.00,\n"
                + "10/03/2026,10/03/2026,HOME DEPOT 44 RETURN,Home,Return,15.99,\n"
                + "10/04/2026,10/04/2026,AMAZON MKTPL*ZZ99YY88X,Home,Sale,-12.00,\n")
BANK_SEP = (BANK + "DEBIT,09/01/2026,ADP PAYROLL,-1000.00,ACH_DEBIT,5000.00,\n"
            + "DEBIT,09/25/2026,CHASE CREDIT CRD AUTOPAY,-200.00,ACH_DEBIT,4800.00,\n"
            + "CREDIT,09/30/2026,INTEREST PAYMENT,0.28,MISC_CREDIT,4800.28,\n")
BANK_OCT_BROKEN = (BANK + "DEBIT,10/03/2026,ADP PAYROLL,-1000.00,ACH_DEBIT,3800.28,\n"
                   + "DEBIT,not-a-date,BROKEN ROW,,ACH_DEBIT,,\n")
BUSINESS_AUG = BANK + "DEBIT,08/01/2026,RENT AUGUST,-900.00,ACH_DEBIT,100.00,\nDEBIT,08/10/2026,FEE,-5.00,FEE,95.00,\n"
BUSINESS_OCT = BANK + "DEBIT,10/05/2026,FEE,-5.00,FEE,90.00,\n"
RESERVE_A = BANK + "CREDIT,09/03/2026,DEPOSIT A,10.00,ACH_CREDIT,10.00,\n"
RESERVE_B = BANK + "CREDIT,09/22/2026,DEPOSIT B,10.00,ACH_CREDIT,20.00,\n"
RESERVE_GAP = BANK + "CREDIT,09/17/2026,DEPOSIT C,10.00,ACH_CREDIT,30.00,\n"
AMAZON_SEP = (AMAZON + "".join("09/10/2026,111-7130700-7696250,Ceiling fan,B0FAN,AB12CD34E,09/12/2026,286.23\n"
                               for _ in range(3)))
AMAZON_OCT = AMAZON + "10/03/2026,112-0000000-0000001,Light bulbs,B0BULB,ZZ99YY88X,10/04/2026,12.00\n"
QBO_ACCOUNT_LIST = ("Account List\nTest Co, LLC\n\nAccount,Type,Detail type,Description,Balance\n"
                    "Chase Checking,Bank,Checking,,\nInk Card,Credit Card,Credit Card,,\n"
                    "Supplies,Expenses,Supplies & Materials,,\nInterest earned,Other Income,Interest Earned,,\n"
                    "Meals,Expenses,Entertainment Meals,,\n")


class FakeChatGPT:
    """Stands for the ChatGPT adapter: answers from the masked descriptions, can fail on demand, counts calls."""

    def __init__(self, ids):
        self.ids, self.calls, self.fail_next = ids, 0, 0

    def __call__(self, prompt, *, web_research=False):
        assert web_research, "the internet stage asks for web search"
        self.calls += 1
        if self.fail_next:
            self.fail_next -= 1
            raise AIProviderUnavailable("ChatGPT did not complete the response.")
        payload = json.loads(prompt.rsplit("\n", 1)[1])
        out = []
        for mv in payload["movements"]:
            d, base = mv["description"], dict(id=mv["id"], reasoning="fake", missing_information=[])
            if mv.get("recognised_who"):
                out.append(dict(base, outcome="WHO_IDENTIFIED", who=mv["recognised_who"], who_certainty="CERTAIN",
                                nature_code="OTHER", nature_confidence="HIGH", why_id=self.ids["supplies"],
                                why_confidence="HIGH", sources=[dict(title="Home Depot", url="https://www.homedepot.com")]))
            elif "STARBUCKS" in d:
                out.append(dict(base, outcome="GENERIC", generic_who="Coffee shop — merchant not verified",
                                who_certainty="PROBABLE", nature_code="DINING", nature_confidence="HIGH",
                                why_id=None, why_confidence="LOW", sources=[]))
            elif "PUBLIX" in d:
                out.append(dict(base, outcome="WHO_IDENTIFIED", who="PUBLIX SUPER MARKETS", who_certainty="CERTAIN",
                                nature_code="OTHER", nature_confidence="HIGH", why_id=self.ids["supplies"],
                                why_confidence="HIGH", sources=[dict(title="Publix", url="https://www.publix.com/")]))
            else:
                out.append(dict(base, outcome="UNRESOLVED", who=None, who_certainty="UNKNOWN", nature_code="UNKNOWN",
                                nature_confidence="LOW", why_id=None, why_confidence="LOW", sources=[]))
        return dict(movements=out)


def main() -> int:
    passed, failed = [], []

    def check(description, condition, detail=""):
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f"   [{str(detail)[:600]}]"))

    with SessionFactory() as db:
        for name in ("ur_operator", "ur_review_only"):
            account_service.create_account(db, username=name, display_name=name, password="OperatorPass123!",
                                           status="ACTIVE", is_admin=False)
        db.commit()
        op = db.query(m.RFOneAccount).filter_by(username="ur_operator").one()
        account_service.set_domain_access(db, account_id=op.id, domain_code="BANK", enabled=True, role_code=None)
        ro = db.query(m.RFOneAccount).filter_by(username="ur_review_only").one()
        account_service.set_domain_access(db, account_id=ro.id, domain_code="BANK", enabled=True, role_code=None,
                                          scope=m.DOMAIN_ACCESS_SCOPE_SELECTED, item_codes=["review"])
        llc = config_service.create_entity(db, name="Test Co, LLC", legal_name="Test Co, LLC")

        def account(name, kind, digits):
            i = m.PaymentInstrument(display_name=name, instrument_type=kind, institution="Chase", last_four=digits,
                                    status="ACTIVE", owner_reporting_entity_id=llc.id if kind == "BANK_ACCOUNT" else None)
            db.add(i)
            db.flush()
            return i
        bank, card, savings = account("Chase checking", "BANK_ACCOUNT", "0214"), account("Ink card", "CREDIT_CARD", "3144"), \
            account("Chase savings", "BANK_ACCOUNT", "7129")
        business, reserve = account("Business account", "BANK_ACCOUNT", "5555"), account("Reserve", "BANK_ACCOUNT", "6666")
        card_configuration.assign_settlement_account(db, credit_card_payment_instrument_id=card.id,
                                                     settlement_bank_account_id=bank.id, valid_from=date(2026, 1, 1))
        meals_what = db.scalar(select(m.BankAccountingClassification).where(m.BankAccountingClassification.code == "7950"))
        meals = config_service.create_why(db, name="Business Meals & Entertainment", description=None, what_id=meals_what.id)
        supplies = db.scalar(select(m.BankTransactionReason).where(m.BankTransactionReason.name == "Restaurant Operating Supplies"))
        interest = db.scalar(select(m.BankTransactionReason).where(m.BankTransactionReason.name == "Bank Interest Income"))
        who = config_service.save_who(db, occurrence_id=None, name="HOME DEPOT", active=True, reason_ids=[],
                                      default_reason_id=None, reporting_entity_ids=[])
        db.commit()
        ids = dict(bank=bank.id, card=card.id, savings=savings.id, business=business.id, reserve=reserve.id, op=op.id,
                   supplies=supplies.id, interest=interest.id, meals=meals.id, home_depot=who.id, llc=llc.id)

    def login(user):
        c = web_app.app.test_client()
        c.post("/login", data={"username": user, "password": "OperatorPass123!",
                               "csrf_token": CSRF_RE.search(c.get("/login").data.decode()).group(1)})
        return c

    client = login("ur_operator")

    def page(path="/bank/work"):
        return client.get(path).data.decode("utf-8")

    def csrf():
        return CSRF_RE.search(page()).group(1)

    def upload(*files):
        return client.post("/bank/work/upload", content_type="multipart/form-data",
                           data={"csrf_token": csrf(), "files": [(io.BytesIO(c.encode()), n) for n, c in files]})

    def by_name(name):
        with SessionFactory() as s:
            return [dict(json.loads(r.payload), id=r.id) for r in bank_work_routes._files(s)
                    if json.loads(r.payload)["file_name"] == name]

    def txns(source_id=None):
        with SessionFactory() as s:
            q = select(m.FinancialTransaction.id, m.FinancialTransaction.description_original,
                       m.FinancialTransaction.amount_minor, m.FinancialTransaction.explanation_id,
                       m.FinancialTransaction.review_status)
            if source_id:
                q = q.where(m.FinancialTransaction.payment_instrument_id == source_id)
            return sorted(tuple(r) for r in s.execute(q).all())

    def gaps():
        with SessionFactory() as s:
            return {(g.kind, g.source_id): g for g in intake.completeness(s).gaps}

    def count_engine_runs():
        with SessionFactory() as s:
            return s.execute(text("select count(*) from bank_engine_runs")).scalar()

    def answer(source_id, fact, start, end=None):
        return client.post("/bank/work/facts", data=dict(csrf_token=csrf(), source_id=source_id, fact=fact,
                                                         start=start.isoformat(), end=(end or start).isoformat()))

    # ------------------------------------------------------------- A. the page, no month, How Works
    html = page()
    check("A. Upload and Reconcile is the first Bank tab; no month, period or session selector",
          'href="/bank/work"' in html and 'name="month"' not in html and 'name="year"' not in html)
    check("A. How Works opens this page's own section", 'data-how-works="upload-and-reconcile"' in html
          and '/bank/how-it-works#upload-and-reconcile' in html)
    guide = page("/bank/how-it-works")
    check("A. the guide explains blocks, AI, saving and the real state of the export", all(x in guide for x in (
        'id="upload-and-reconcile"', 'id="quickbooks-online"', "never choose a month", "no later day is asked",
        "researches on the internet", "nothing is applied twice", "Import journal entries", "There is no button to",
        'id="work-research-authorization"', "never reused for a company", "Everything is per company",
        "Copy as proposals", 'id="qbo-states"', "does <strong>not</strong> prove", "Import confirmed",
        "Accepted by the QBO API</td><td>Not available", "<em>excluded</em>, not added")))

    # ------------------------------------------------------------- B. mixed upload
    upload(("Chase0214_Activity_sep.csv", BANK_SEP), ("Chase3144_Activity_sep.csv", CARD_SEP),
           ("orders_from_20260901_to_20260930.csv", AMAZON_SEP),
           ("statement.csv", CARD + "09/15/2026,09/15/2026,UNIQUE SHOP,Shop,Sale,-12.00,\n"),
           ("contacts.csv", "Name,Phone\nAlice,555\n"),
           ("Paypal.CSV", "Date,Time,TimeZone,Name,Type,Status,Currency,Amount,Fees,Total,Exchange Rate,Receipt ID,"
                          "Balance,Transaction ID,Item Title\n10/01/2026,10:00:00,PDT,ACME,Express Checkout Payment,"
                          "Completed,USD,-9.00,0.00,-9.00,,,0.00,1AB,\n"),
           ("Chase5555_Activity_aug.csv", BUSINESS_AUG), ("Chase5555_Activity_oct.csv", BUSINESS_OCT),
           ("Chase6666_Activity20260901_20260915_20261001.csv", RESERVE_A),
           ("Chase6666_Activity20260920_20260930_20261001.csv", RESERVE_B))
    states = {n: by_name(n)[0]["state"] for n in ("Chase0214_Activity_sep.csv", "Chase3144_Activity_sep.csv",
              "orders_from_20260901_to_20260930.csv", "statement.csv", "contacts.csv", "Paypal.CSV")}
    check("B. each file recognised and settled as far as Bank can alone", states == {
        "Chase0214_Activity_sep.csv": "INTEGRATED", "Chase3144_Activity_sep.csv": "INTEGRATED",
        "orders_from_20260901_to_20260930.csv": "AMAZON_LOADED", "statement.csv": "NEEDS_SOURCE",
        "contacts.csv": "NOT_RECOGNIZED", "Paypal.CSV": "KEPT_ASIDE"}, states)
    check("B. three identical purchases in one file are three movements",
          len([t for t in txns(ids["card"]) if "AB12CD34E" in t[1]]) == 3)

    # ------------------------------------------------------------- C. the one gate, on every path
    runs_before = count_engine_runs()
    client.post("/bank/work/reconcile", data={"csrf_token": csrf()})
    r2 = client.post("/bank/configuration/recalculate", data={"csrf_token": csrf()})
    r3 = client.post("/bank/amazon", data={"csrf_token": csrf()})
    token = re.search(r'cbank-token" content="([^"]+)"', page("/bank/reconcile/")).group(1)
    r4 = client.post("/bank/reconcile/api/runs", data={"kind": "all"}, headers={"X-CBank-Token": token})
    r5 = client.post("/bank/reconcile/api/runs/1/investigate", data={"txn_ids": "1"}, headers={"X-CBank-Token": token})
    r6 = client.post("/bank/flow/runs", data={"csrf_token": csrf()})
    with SessionFactory() as s:
        no_run = bank_work_routes.run_view(s) is None
    check("C. not ready: every way to start automatic processing is refused server side, nothing runs",
          r2.status_code == 302 and "/bank/work" in r2.headers["Location"] and r3.status_code == 302
          and "/bank/work" in r3.headers["Location"] and r4.status_code == 409 and r5.status_code == 409
          and r6.status_code == 409 and count_engine_runs() == runs_before and no_run,
          (r2.status_code, r3.status_code, r4.status_code, r5.status_code, r6.status_code, r4.data[:200]))
    check("C. reading and configuration stay open", client.get("/bank/configuration").status_code == 200
          and client.get("/bank/reconcile/").status_code == 200 and client.get("/bank/review").status_code == 200)

    # ------------------------------------------------------------- D. files settled, repeated and fuller files
    client.post(f"/bank/work/files/{by_name('contacts.csv')[0]['id']}/remove", data={"csrf_token": csrf()})
    client.post(f"/bank/work/files/{by_name('statement.csv')[0]['id']}/source",
                data={"csrf_token": csrf(), "source_id": ids["card"]})
    check("D. a file without account gets its Source and is integrated", by_name("statement.csv")[0]["state"] == "INTEGRATED")
    before = txns()
    upload(("Chase3144_Activity_sep (1).csv", CARD_SEP))
    check("D. the same file again adds nothing", txns() == before)
    upload(("Chase3144_Activity_sep_oct.csv", CARD_SEP_OCT))
    new = sorted(t[1] for t in txns() if t not in before)
    check("D. a fuller file adds only what was missing; three purchases stay three",
          new == ["AMAZON MKTPL*ZZ99YY88X", "HOME DEPOT 44 RETURN", "PUBLIX 1661"]
          and len([t for t in txns() if "AB12CD34E" in t[1]]) == 3 and all(t in txns() for t in before), new)

    # ------------------------------------------------------------- E. completeness from the real files
    g = gaps()
    with SessionFactory() as s:
        c = intake.completeness(s)
        cov = {sc.source_id: sc for sc in c.sources}
    check("E. work starts on the first day any file covers", c.window_start == date(2026, 8, 1), c.window_start)
    check("E. a Source without history is asked about, not called incomplete or unused",
          (intake.GAP_NO_FILES, ids["savings"]) in g)
    check("E. the first movement does not prove the opening: a Source whose files begin a month later is asked",
          (intake.GAP_START_UNKNOWN, ids["bank"]) in g and (intake.GAP_START_UNKNOWN, ids["card"]) in g, list(g))
    pm = g.get((intake.GAP_POSSIBLE_MISSING, ids["business"]))
    check("E. a movement in August does not cover the month: a whole month without file is asked",
          pm is not None and (pm.start, pm.end) == (date(2026, 8, 11), date(2026, 10, 4)), pm and (pm.start, pm.end))
    ms = g.get((intake.GAP_MISSING_STATEMENT, ids["reserve"]))
    check("E. periods stated in the file name prove a missing statement between them",
          ms is not None and (ms.start, ms.end) == (date(2026, 9, 16), date(2026, 9, 19))
          and [fp.basis for fp in cov[ids["reserve"]].files] == ["DECLARED", "DECLARED"])
    check("E. no future day is asked: each Source is required only up to its own files",
          cov[ids["bank"]].required_to == date(2026, 9, 30) and cov[ids["reserve"]].required_to == date(2026, 9, 30)
          and any(u.get("tail") and u["source_id"] == ids["reserve"] for u in c.uncertainties)
          and all(x.end <= cov[x.source_id].required_to for x in c.gaps if x.source_id in (ids["bank"], ids["reserve"])))
    check("E. the October Amazon charge needs a report", (intake.GAP_AMAZON_REPORT, None) in g)
    html = page()
    check("E. each gap is a concrete request with dates, reason and factual answers",
          "Upload the Reserve ··6666 statement for 16 Sep 2026 – 19 Sep 2026." in html
          and "There were no movements in these dates" in html and "In use only since 01 Sep 2026" in html)

    answer(ids["bank"], "IN_USE_SINCE", date(2026, 9, 1))
    answer(ids["card"], "NO_MOVEMENTS", date(2026, 8, 1), date(2026, 9, 1))
    answer(ids["savings"], "NOT_IN_USE", c.window_start, date(2026, 10, 4))
    answer(ids["business"], "NO_MOVEMENTS", date(2026, 8, 11), date(2026, 10, 4))
    answer(ids["reserve"], "IN_USE_SINCE", date(2026, 9, 1))
    with SessionFactory() as s:
        facts = intake.facts(s)
        start_written = s.get(m.PaymentInstrument, ids["bank"]).effective_start_date
    check("E. answers are kept with who and when; 'in use since' sets the Source's start date",
          len(facts) == 5 and all(f["account_id"] == ids["op"] and f["at"] for f in facts)
          and start_written == date(2026, 9, 1))
    batch_id = by_name("Chase0214_Activity_sep.csv")[0]["batch_id"]
    client.post("/bank/work/facts", data=dict(csrf_token=csrf(), source_id=ids["bank"], fact="STATEMENT_PERIOD",
                                              batch_id=batch_id, start="2026-09-05", end="2026-09-30"))
    client.post("/bank/work/facts", data=dict(csrf_token=csrf(), source_id=ids["bank"], fact="STATEMENT_PERIOD",
                                              batch_id=batch_id, start="2026-09-01", end="2026-09-30"))
    with SessionFactory() as s:
        basis = next(fp.basis for sc in intake.completeness(s).sources for fp in sc.files if fp.batch_id == batch_id)
        n_facts = len(intake.facts(s))
    check("E. a file's statement period can be confirmed (it must contain its movements)",
          basis == "CONFIRMED" and n_facts == 6, (basis, n_facts))
    upload(("Chase6666_Activity20260916_20260919_20261001.csv", RESERVE_GAP))
    upload(("Chase0214_Activity_oct.csv", BANK_OCT_BROKEN))
    oct_file = by_name("Chase0214_Activity_oct.csv")[0]
    check("E. unreadable rows stop the file until the person decides", oct_file["state"] == "UNREADABLE_ROWS")
    client.post(f"/bank/work/files/{oct_file['id']}/leave-out", data={"csrf_token": csrf()})
    check("E. left out on request: the readable rows are integrated",
          by_name("Chase0214_Activity_oct.csv")[0]["state"] == "INTEGRATED")
    remaining = gaps()
    check("E. after the answers and files only the Amazon report is missing",
          set(remaining) == {(intake.GAP_AMAZON_REPORT, None)}, [(k, v.start, v.end) for k, v in remaining.items()])
    upload(("orders_from_20261001_to_20261031.csv", AMAZON_OCT))
    html = page()
    check("E. ready: 'Data ready for reconciliation', button enabled",
          "Data ready for reconciliation" in html and not re.search(r'class="btn-primary"\s+disabled', html))
    check("E. no circular block: every movement is still unclassified", all(t[3] is None for t in txns()))

    # ------------------------------------------------------------- F. run without authorization
    def run_and_wait():
        client.post("/bank/work/reconcile", data={"csrf_token": csrf()})
        run = None
        for _ in range(600):
            with SessionFactory() as s:
                run = bank_work_routes.run_view(s)
            if run and run["status"] not in ("QUEUED", "RUNNING"):
                return run
            time.sleep(0.5)
        return run

    fake = FakeChatGPT(ids)
    real_generate = bank_chatgpt.generate_json
    bank_chatgpt.generate_json = fake
    try:
        html = page()
        check("F. before the first run the page asks the authorization, listing exactly what would be sent",
              "Internet research needs your authorization" in html and "the movement date" in html
              and "amounts, account numbers" in html)
        run = run_and_wait()
        check("F. without authorization the run completes, says so, and calls nobody",
              run["status"] == "DONE" and fake.calls == 0
              and any("waits for your authorization" in w for w in run.get("warnings", [])), run)
        check("F. the movements it would research are listed as 'not authorized', not as unresolved",
              "Internet research not authorized" in page())
        client.post("/bank/work/research/authorize", data={"csrf_token": csrf(), "authorize": "yes"})
        consent = json.loads(Path(_FOLDER, "bank-chat-provider-consent.json").read_text(encoding="utf-8"))
        check("F. the authorization is recorded with who, when and the scope", consent["web_research"]["allowed"]
              and consent["web_research"]["authorized_by"] == ids["op"] and "masked" in consent["web_research"]["scope"])

        # ------------------------------------------------------------- G. research, provider error, resumption
        fake.fail_next = 1
        run = run_and_wait()
        first_calls = fake.calls
        with SessionFactory() as s:
            res = bank_work_routes.bank_work_research.latest_results(s, run.get("engine_run_id"))
        check("G. a provider failure is recorded as such, never as an unresolved case",
              run["status"] == "DONE" and res["counts"].get("PROVIDER_ERROR", 0) >= 1
              and any("did not answer" in w for w in run.get("warnings", [])), (run, res and res["counts"]))
        run = run_and_wait()
        second_calls = fake.calls - first_calls
        with SessionFactory() as s:
            res = bank_work_routes.bank_work_research.latest_results(s, run.get("engine_run_id"))
            by_desc = {s.get(m.FinancialTransaction, int(tid)).description_original: r for tid, r in res["results"].items()}
        check("G. started again: only the failed request is repeated", second_calls == 1
              and not res["counts"].get("PROVIDER_ERROR"), (first_calls, second_calls, res["counts"]))
        check("G. WHO unknown -> identified on the internet with a public source, WHY from the evidence",
              by_desc.get("PUBLIX 1661", {}).get("outcome") == "WHO_IDENTIFIED"
              and by_desc["PUBLIX 1661"]["why_id"] == ids["supplies"] and by_desc["PUBLIX 1661"]["sources"], by_desc.get("PUBLIX 1661"))
        check("G. WHO known without WHY -> researched with the WHO kept",
              by_desc.get("HOME DEPOT 44", {}).get("who_kept") and by_desc["HOME DEPOT 44"]["who_id"] == ids["home_depot"]
              and by_desc["HOME DEPOT 44"]["why_id"] == ids["supplies"], by_desc.get("HOME DEPOT 44"))
        check("G. dining with a company Source -> generic WHO, Business Meals & Entertainment (approved policy)",
              by_desc.get("STARBUCKS 12", {}).get("outcome") == "GENERIC_WHO"
              and by_desc["STARBUCKS 12"]["why_id"] == ids["meals"], by_desc.get("STARBUCKS 12"))
        check("G. evidence insufficient -> unresolved, left for a person",
              by_desc.get("UNIQUE SHOP", {}).get("outcome") == "UNRESOLVED", by_desc.get("UNIQUE SHOP"))
        calls = fake.calls
        run_and_wait()
        check("G. a repeated run reuses every answer: no new call", fake.calls == calls, (calls, fake.calls))
        with SessionFactory() as s:
            config_service.create_why(s, name="Test new WHY", description=None, what_id=None)
            s.commit()
        run_and_wait()
        check("G. a changed WHY catalog makes the answers stale: asked again", fake.calls > calls)
        research = bank_work_routes.bank_work_research
        stub = type("ThreeStages", (), {"INSTRUCTIONS": "same instructions"})
        facts = dict(id=1, date="2026-09-02", description="STARBUCKS", direction="money out", source_type="card",
                     source_owner_kind="LEGAL", candidate_whos=[])
        ctx = dict(owner_id=ids["llc"], owner_kind="LEGAL", known_whos=[], rules=dict(why_mode=None))

        def fp(f=None, **kw):
            return research._fingerprint(stub, dict(facts, **(f or {})), [], dict(ctx, **kw))
        check("G. an answer is reused only in the same context: owner (company/person), WHO mode, rules, direction",
              fp() == fp(f=dict(id=99, date="2026-10-01"))
              and len({fp(), fp(owner_id=7, owner_kind="PERSONAL"), fp(owner_id=7), fp(rules=dict(why_mode="MULTIPLE")),
                       fp(rules=dict(why_mode=None, why_open_reason="WHY_RULES_CONFLICT")), fp(f=dict(direction="money in")),
                       fp(known_whos=["STARBUCKS"])}) == 7)
        calls = fake.calls
        with SessionFactory() as s:
            s.add(m.BankWhoWhyMode(occurrence_id=ids["home_depot"], why_mode="MULTIPLE"))
            s.commit()
        run_and_wait()
        mode_calls = fake.calls - calls
        with SessionFactory() as s:
            s.query(m.BankWhoWhyMode).delete()
            s.commit()
        run_and_wait()
        check("G. a changed WHO mode does not reuse the answer; back to the previous mode the kept answer is reused",
              mode_calls >= 1 and fake.calls == calls + mode_calls, (calls, mode_calls, fake.calls))

        # ------------------------------------------------------------- H. states and quadratures
        with SessionFactory() as s:
            view = bank_work_routes.results_view(s, intake.completeness(s))
        check("H. two quadratures, each adding up to the total",
              view["quadrature_final"] and view["quadrature_who"] and sum(view["states"].values()) == view["total"]
              and sum(view["origins"].values()) == view["total"] and view["origins"].get("internet", 0) >= 1
              and view["origins"].get("generic", 0) >= 1, (view["states"], view["origins"], view["total"]))
        html = page()
        check("H. the page shows both counts and says a proposal is recorded only when confirmed",
              "Where the WHO comes from" in html and "Final state" in html and "is a proposal" in html)
        publix = next(gr for gr in view["groups"] if gr["who"] == "PUBLIX SUPER MARKETS")
        generic = next(gr for gr in view["groups"] if gr["reason"] == "RESEARCH_GENERIC")
        check("H. a generic WHO is not confirmable as it is (the person chooses the WHO)",
              generic["confirmable"] == 0 and publix["confirmable"] == 1)
        client.post("/bank/work/confirm", data=dict(csrf_token=csrf(), scope="group", group=publix["key"],
                                                    engine_run_id=view["run"]["id"], confirm="yes"))
        with SessionFactory() as s:
            t = s.scalar(select(m.FinancialTransaction).where(m.FinancialTransaction.description_original == "PUBLIX 1661"))
            e = s.get(m.BankTransactionExplanation, t.explanation_id) if t.explanation_id else None
            who_name = s.get(m.BankOccurrence, e.occurrence_id).canonical_name if e else None
            n_alloc = s.scalar(select(func.count()).select_from(m.BankTransactionAllocation).where(
                m.BankTransactionAllocation.financial_transaction_id == t.id))
        check("H. confirming a research proposal records the decision (new WHO created, WHY, WHAT, allocation)",
              e is not None and e.decision_source == "HUMAN" and e.transaction_reason_id == ids["supplies"]
              and who_name == "PUBLIX SUPER MARKETS" and "internet research" in (e.explanation_notes or "") and n_alloc == 1)
        client.post("/bank/work/confirm", data=dict(csrf_token=csrf(), scope="group", group=publix["key"],
                                                    engine_run_id=view["run"]["id"], confirm="yes"))
        with SessionFactory() as s:
            again = (s.get(m.FinancialTransaction, t.id).explanation_id, s.scalar(select(func.count()).select_from(
                m.BankTransactionAllocation).where(m.BankTransactionAllocation.financial_transaction_id == t.id)))
        check("H. confirming the same proposal twice applies it once", again == (e.id, 1), again)
        hd = next(gr for gr in view["groups"] if gr["reason"] == "RESEARCH_WHY")
        client.post("/bank/work/confirm", data=dict(csrf_token=csrf(), scope="group", group=hd["key"],
                                                    engine_run_id=view["run"]["id"], confirm="yes"))
        with SessionFactory() as s:
            view2 = bank_work_routes.results_view(s, intake.completeness(s))
        check("H. once confirmed they count as decided at once", view2["states"].get("decided", 0) >= 2
              and view2["quadrature_final"], view2["states"])
    finally:
        bank_chatgpt.generate_json = real_generate

    # ------------------------------------------------------------- I. automatic proposals and protection
    with SessionFactory() as s:
        refund = next(t for t in txns(ids["bank"]) if t[1] == "ADP PAYROLL")[0]
        interest = next(t for t in txns(ids["bank"]) if t[1] == "INTEREST PAYMENT")[0]
        unique = next(t for t in txns(ids["card"]) if t[1] == "UNIQUE SHOP")[0]
        chase = config_service.save_who(s, occurrence_id=None, name="CHASE BANK", active=True, reason_ids=[],
                                        default_reason_id=None, reporting_entity_ids=[])
        recognition.record_human_decision(s, recognition.HumanDecisionRequest(
            transaction_id=unique, occurrence_id=ids["home_depot"], confirmed_by_account_id=ids["op"],
            transaction_reason_id=ids["supplies"]))
        decided = s.get(m.FinancialTransaction, unique).explanation_id
        base = dict(currency="USD", source="x", exceptions=[], protected=None, split=None, status="RECONCILED")
        results = [dict(base, txn_id=refund, date="2026-09-01", description="ADP PAYROLL", amount_minor=-100000,
                        who_id=ids["home_depot"], who_name="HOME DEPOT", why_id=ids["supplies"], why="Supplies",
                        who_method="NAME/ALIAS"),
                   dict(base, txn_id=interest, date="2026-09-30", description="INTEREST PAYMENT", amount_minor=28,
                        who_id=chase.id, who_name="CHASE BANK", why_id=ids["interest"], why="Bank Interest Income",
                        who_method="RULE"),
                   dict(base, txn_id=unique, date="2026-09-15", description="UNIQUE SHOP", amount_minor=-1200,
                        who_id=chase.id, who_name="CHASE BANK", why_id=ids["interest"], why="x", who_method="RULE")]
        s.execute(text("insert into bank_engine_runs(created_at,label,scope_json,summary_json) values "
                       "('2026-11-03T12:00:00+00:00','Whole history','{}','{}')"))
        test_run = s.execute(text("select max(id) from bank_engine_runs")).scalar()
        for r in results:
            s.execute(text("insert into bank_engine_results(run_id,financial_transaction_id,status,payload_json) "
                           "values (:r,:t,'RECONCILED',:p)"), dict(r=test_run, t=r["txn_id"], p=json.dumps(r)))
        s.commit()
    html = page()
    check("I. automatic proposals are offered with their effect first, without the movement a person decided",
          "Confirm 2 automatic proposal(s)" in html, re.findall(r"Confirm \d+ automatic", html))
    client.post("/bank/work/confirm", data=dict(csrf_token=csrf(), scope="automatic", engine_run_id=test_run - 1, confirm="yes"))
    with SessionFactory() as s:
        untouched = s.get(m.FinancialTransaction, refund).explanation_id is None
    check("I. a confirmation made on older results is refused", untouched)
    client.post("/bank/work/confirm", data=dict(csrf_token=csrf(), scope="automatic", engine_run_id=test_run, confirm="yes"))
    with SessionFactory() as s:
        ok = all(s.get(m.FinancialTransaction, t).explanation_id for t in (refund, interest))
        still = s.get(m.FinancialTransaction, unique).explanation_id == decided
    check("I. confirmed proposals are recorded; the person's decision is untouched", ok and still)

    # ------------------------------------------------------------- J. QuickBooks Online, per company
    qb = bank_work_routes.qbo_books
    with SessionFactory() as s:
        second = config_service.create_entity(s, name="Second Co, LLC", legal_name="Second Co, LLC")
        s.get(m.PaymentInstrument, ids["reserve"]).owner_reporting_entity_id = second.id
        deposit_a = s.scalar(select(m.FinancialTransaction).where(m.FinancialTransaction.description_original == "DEPOSIT A"))
        chase_who = s.scalar(select(m.BankOccurrence).where(m.BankOccurrence.canonical_name == "CHASE BANK"))
        bank_work_routes.confirm_proposals(s, [dict(txn_id=deposit_a.id, who_id=chase_who.id, why_id=ids["interest"])],
                                           account_id=ids["op"], note="test")
        supplies_what = s.get(m.BankTransactionReason, ids["supplies"]).accounting_classification_id
        # A correspondence made before they were per company (the old global table): never attributed to a company.
        s.execute(text("insert into bank_qbo_account_maps(kind, local_id, qbo_account_id, qbo_account_name, status) "
                       "values ('CATEGORY', :w, NULL, 'Supplies', 'GLOBAL_LEGACY')"), dict(w=supplies_what))
        s.commit()
        ids.update(second=second.id, deposit_a=deposit_a.id)

    def post_qbo(path, **data):
        return client.post(path, data=dict(csrf_token=csrf(), **data), follow_redirects=True).data.decode("utf-8")

    qbo = page(f"/bank/work/qbo?company={ids['llc']}")
    check("J. the QBO page is per company and separates preview, generated file, confirmed import and API",
          'data-how-works="quickbooks-online"' in qbo and "File generated" in qbo and "Import confirmed" in qbo
          and "Accepted by the QBO API" in qbo and "Intuit Developer app" in qbo and "Second Co, LLC" in qbo)
    client.post("/bank/work/qbo/accounts", content_type="multipart/form-data",
                data={"csrf_token": csrf(), "company_id": ids["llc"], "file": (io.BytesIO(b"Name,Phone\nA,1\n"), "x.csv")})
    client.post("/bank/work/qbo/accounts", content_type="multipart/form-data",
                data={"csrf_token": csrf(), "company_id": ids["llc"], "file": (io.BytesIO(QBO_ACCOUNT_LIST.encode()), "AccountList.csv")})
    with SessionFactory() as s:
        chart = {a.name: (a.account_type, a.qbo_account_id, a.reporting_entity_id) for a in s.scalars(select(m.BankQboAccount))}
    check("J. the Account List goes into ONE company's chart (names and types, no invented Id); a wrong file is refused",
          chart.get("Ink Card") == ("Credit Card", None, ids["llc"]) and len(chart) == 5, chart)
    with SessionFactory() as s:
        publix = s.scalar(select(m.FinancialTransaction.id).where(m.FinancialTransaction.description_original == "PUBLIX 1661"))
        legacy_only = qb.plan(s, [publix])["items"][0]
    check("J. an old correspondence for no company is never used: the movement still needs this company's",
          any(b["code"] == "CATEGORY_NOT_MAPPED" for b in legacy_only["blockers"]), legacy_only["blockers"])
    qbo = page(f"/bank/work/qbo?company={ids['llc']}")
    check("J. only the correspondences this company's movements need are asked, with the old one as a suggestion",
          "Source: Ink card" in qbo and "Source: Chase checking" in qbo and "Source: Business account" not in qbo
          and "previous correspondence for no company" in qbo and "Source: Reserve" not in qbo)
    wrong = post_qbo("/bank/work/qbo/map", company_id=ids["llc"], kind="PAYMENT_ACCOUNT", local_id=ids["card"], name="Chase Checking")
    check("J. a correspondence of the wrong type is refused", "must be of type Credit Card" in wrong)
    other = post_qbo("/bank/work/qbo/map", company_id=ids["second"], kind="PAYMENT_ACCOUNT", local_id=ids["reserve"],
                     name="Chase Checking")
    check("J. an account of another company's chart is refused", "another company" in other, other[-300:])
    with SessionFactory() as s:
        what_ids = {a.accounting_classification_id for a in s.scalars(select(m.BankTransactionAllocation))}
        what_codes = {w.id: w.code for w in s.scalars(select(m.BankAccountingClassification).where(
            m.BankAccountingClassification.id.in_(what_ids)))}
    for kind, local, name in [("PAYMENT_ACCOUNT", ids["card"], "Ink Card"), ("PAYMENT_ACCOUNT", ids["bank"], "Chase Checking")] + \
            [("CATEGORY", w, "Interest earned" if code == "8100" else "Supplies") for w, code in what_codes.items()]:
        client.post("/bank/work/qbo/map", data=dict(csrf_token=csrf(), company_id=ids["llc"], kind=kind, local_id=local, name=name))

    # Second Co: its own chart; Test Co's correspondences copied only as proposals, verified in Second Co's chart.
    client.post("/bank/work/qbo/accounts", content_type="multipart/form-data", data={
        "csrf_token": csrf(), "company_id": ids["second"],
        "file": (io.BytesIO(b"Account List\nSecond Co, LLC\nAccount,Type\nReserve Bank,Bank\nSupplies,Expenses\n"
                            b"Interest income,Other Income\n"), "AccountList2.csv")})
    copied = post_qbo("/bank/work/qbo/copy", company_id=ids["second"], from_company_id=ids["llc"])
    with SessionFactory() as s:
        proposals = {r.qbo_account_name: r for r in s.scalars(select(m.BankQboAccountMap).where(
            m.BankQboAccountMap.reporting_entity_id == ids["second"]))}
        blocked = qb.plan(s, [ids["deposit_a"]])["items"][0]
    check("J. copying from another company creates proposals only (no Source account), used for nothing yet",
          "copied as proposals" in copied and proposals and all(r.status == "PROPOSED" and r.kind == "CATEGORY"
                                                                 for r in proposals.values())
          and any(b["code"] == "MAP_PROPOSED" for b in blocked["blockers"]), [b["code"] for b in blocked["blockers"]])
    refused = post_qbo(f"/bank/work/qbo/map/{proposals['Interest earned'].id}/verify", company_id=ids["second"])
    accepted = post_qbo(f"/bank/work/qbo/map/{proposals['Supplies'].id}/verify", company_id=ids["second"])
    check("J. a proposal is verified in the destination chart: refused when the account is not there, accepted when it is",
          "not in this company" in refused and "Proposal verified" in accepted)
    post_qbo("/bank/work/qbo/map", company_id=ids["second"], kind="CATEGORY", local_id=proposals["Interest earned"].local_id,
             name="Interest income")
    post_qbo("/bank/work/qbo/map", company_id=ids["second"], kind="PAYMENT_ACCOUNT", local_id=ids["reserve"], name="Reserve Bank")

    with SessionFactory() as s:
        out_leg = next(t for t in txns(ids["bank"]) if t[1] == "CHASE CREDIT CRD AUTOPAY")[0]
        in_leg = next(t for t in txns(ids["card"]) if t[1] == "AUTOMATIC PAYMENT - THANK")[0]
        engine_matched = bool(s.scalar(select(m.FinancialTransactionMatch).where(
            m.FinancialTransactionMatch.transaction_a_id.in_([out_leg, in_leg]))))
        if not engine_matched:   # the pair as the engine records it, when it did not pair them here
            s.execute(text("insert into financial_transaction_matches(transaction_a_id, transaction_b_id, match_type, "
                           "match_method, matched_amount_minor, relationship) values (:a, :b, 'CARD_SETTLEMENT', 'ENGINE', "
                           "20000, 'SAME_OWNER')"), dict(a=out_leg, b=in_leg))
            s.commit()
        business = s.get(m.PaymentInstrument, ids["business"])
        business.owner_reporting_entity_id = None          # the company of its movements becomes undeterminable
        s.flush()
        plan = qb.plan(s, bank_work_routes.qbo_scope(s, intake.completeness(s)))
        s.rollback()
    items = {i["txn_id"]: i for i in plan["items"]}
    by_desc = {i["description"]: i for i in plan["items"]}
    transfer = [i for i in plan["items"] if i["entity"] == "Transfer"]
    check("J. expense, card refund, deposit and ONE transfer for the two legs of the card payment",
          by_desc["PUBLIX 1661"]["entity"] == "Purchase" and by_desc["PUBLIX 1661"]["ready"]
          and by_desc["HOME DEPOT 44 RETURN"]["entity"] == "Purchase" and by_desc["HOME DEPOT 44 RETURN"]["payload"].get("Credit") is True
          and by_desc["INTEREST PAYMENT"]["entity"] == "Deposit" and by_desc["INTEREST PAYMENT"]["ready"]
          and len(transfer) == 1 and transfer[0]["ready"] and in_leg not in items,
          [(i["description"], i["entity"], [b["code"] for b in i["blockers"]]) for i in plan["items"]])
    check("J. each movement belongs to one company: Second Co's deposit uses Second Co's accounts",
          by_desc["DEPOSIT A"]["owner_id"] == ids["second"] and by_desc["DEPOSIT A"]["ready"]
          and {ln["account"] for ln in by_desc["DEPOSIT A"]["lines"]} == {"Reserve Bank", "Interest income"},
          by_desc["DEPOSIT A"])
    rent = by_desc["RENT AUGUST"]
    check("J. a movement whose company cannot be determined is blocked with the reason",
          any(b["code"] == "NO_OWNER" and "Business account: no owner configured" in b["detail"] for b in rent["blockers"]),
          rent["blockers"])
    check("J. movements not reconciled yet are blocked with their reason", any(
        b["code"] == "NOT_CONFIRMED" for b in by_desc["STARBUCKS 12"]["blockers"]))
    check("J. lines balance to the cent, signs preserved", all(
        sum(x["debit"] for x in i["lines"]) == sum(x["credit"] for x in i["lines"]) for i in plan["items"] if i["ready"])
        and by_desc["INTEREST PAYMENT"]["lines"][0]["debit"] == 28)

    nofeeds = post_qbo("/bank/work/qbo/export", company_id=ids["llc"])
    check("J. no file without the statement that the bank-feed items will be excluded (journal entries cannot be matched)",
          "excluded (not added)" in nofeeds)
    with SessionFactory() as s:
        before_batches = s.scalar(select(func.count(m.BankQboExportBatch.id)))
    generated = post_qbo("/bank/work/qbo/export", company_id=ids["llc"], feeds_excluded="1")
    with SessionFactory() as s:
        batch = s.scalar(select(m.BankQboExportBatch).order_by(m.BankQboExportBatch.id.desc()))
        exported = s.scalar(select(func.count(m.BankQboExport.id)))
        sent = s.scalar(select(func.count(m.BankQboExport.id)).where(m.BankQboExport.status == "SENT"))
        batch_id, batch_status, downloads0 = batch.id, batch.status, batch.download_count
    test_co_ready = sum(1 for i in plan["items"] if i["ready"] and i["owner_id"] == ids["llc"])
    check("J. generating makes ONE batch of ONE company, state 'generated' (not downloaded, not imported)",
          before_batches == 0 and batch_status == "GENERATED" and downloads0 == 0 and "File generated" in generated
          and exported == test_co_ready and sent == 0, (batch_status, exported, test_co_ready))
    confirm_early = post_qbo(f"/bank/work/qbo/files/{batch_id}/confirm", company_id=ids["llc"])
    check("J. an import cannot be confirmed for a file never downloaded", "never downloaded" in confirm_early)
    first = client.get(f"/bank/work/qbo/files/{batch_id}").data.decode("utf-8")
    second_dl = client.get(f"/bank/work/qbo/files/{batch_id}").data.decode("utf-8")
    with SessionFactory() as s:
        after = (s.scalar(select(func.count(m.BankQboExportBatch.id))), s.scalar(select(func.count(m.BankQboExport.id))),
                 s.get(m.BankQboExportBatch, batch_id).download_count, s.get(m.BankQboExportBatch, batch_id).status)
    check("J. downloading again gives the same file and creates no new batch or export",
          first == second_dl and after == (1, exported, 2, "GENERATED"), after)
    rows = list(csv.DictReader(io.StringIO(first)))
    journals = {r["Journal No"] for r in rows}
    check("J. the file is QBO's journal-entry import of that company only: one entry per movement, debits = credits",
          rows and list(rows[0]) == ["Journal No", "Journal Date", "Account Name", "Debits", "Credits", "Description"]
          and all(round(sum(float(r["Debits"] or 0) for r in rows if r["Journal No"] == j), 2)
                  == round(sum(float(r["Credits"] or 0) for r in rows if r["Journal No"] == j), 2) for j in journals)
          and len(journals) == test_co_ready and f"RFB-{ids['deposit_a']}" not in journals
          and not {r["Account Name"] for r in rows} & {"Reserve Bank", "Interest income"}, first[:400])
    again = post_qbo("/bank/work/qbo/export", company_id=ids["llc"], feeds_excluded="1")
    check("J. a second generation for the same company finds nothing to export", "No movement of Test Co, LLC is ready" in again)

    post_qbo("/bank/work/qbo/export", company_id=ids["second"], feeds_excluded="1")
    with SessionFactory() as s:
        b2 = s.scalar(select(m.BankQboExportBatch).where(m.BankQboExportBatch.reporting_entity_id == ids["second"]))
        b2_id, b2_moves = b2.id, json.loads(b2.movements_json)
    check("J. Second Co's movement goes into Second Co's own file", [x["txn_id"] for x in b2_moves] == [ids["deposit_a"]])
    no_reason = post_qbo(f"/bank/work/qbo/files/{b2_id}/withdraw", company_id=ids["second"], reason="")
    withdrawn = post_qbo(f"/bank/work/qbo/files/{b2_id}/withdraw", company_id=ids["second"], reason="import failed in QBO")
    with SessionFactory() as s:
        free = qb.plan(s, [ids["deposit_a"]])["items"][0]
    check("J. a file not imported can be withdrawn only with a reason; its movements become exportable again",
          "Say why" in no_reason and "withdrawn" in withdrawn and free["ready"], free["blockers"])
    post_qbo("/bank/work/qbo/export", company_id=ids["second"], feeds_excluded="1")
    with SessionFactory() as s:
        b3 = s.scalar(select(m.BankQboExportBatch).order_by(m.BankQboExportBatch.id.desc()))
        b3_journal = json.loads(b3.movements_json)[0]["journal_no"]
        statuses = [b.status for b in s.scalars(select(m.BankQboExportBatch).order_by(m.BankQboExportBatch.id))]
    check("J. re-exported in a NEW file with the same journal number; the withdrawn file stays in the history",
          b3_journal == f"RFB-{ids['deposit_a']}" and statuses == ["GENERATED", "WITHDRAWN", "GENERATED"], statuses)

    confirmed = post_qbo(f"/bank/work/qbo/files/{batch_id}/confirm", company_id=ids["llc"], note="imported 2026-11-03")
    late = post_qbo(f"/bank/work/qbo/files/{batch_id}/withdraw", company_id=ids["llc"], reason="x")
    check("J. the import is confirmed by a person; a confirmed file can no longer be withdrawn",
          "import in QuickBooks confirmed" in confirmed and "imported in QBO (confirmed by a person)" in confirmed
          and "Only a generated file" in late)
    with SessionFactory() as s:
        t = s.scalar(select(m.FinancialTransaction).where(m.FinancialTransaction.description_original == "PUBLIX 1661"))
        a = s.scalar(select(m.BankTransactionAllocation).where(m.BankTransactionAllocation.financial_transaction_id == t.id))
        a.description = "changed after export"
        s.get(m.PaymentInstrument, ids["reserve"]).owner_reporting_entity_id = ids["llc"]
        s.flush()
        changed = qb.plan(s, [t.id, ids["deposit_a"]])["items"]
        s.rollback()
    check("J. a change after the export (lines, or the company) is reported, never exported again",
          all(i["blockers"][-1]["code"] == "CHANGED_AFTER_EXPORT" and not i["ready"] for i in changed)
          and "exported for Second Co, LLC" in next(i for i in changed if i["txn_id"] == ids["deposit_a"])["blockers"][-1]["detail"],
          [i["blockers"] for i in changed])
    preview = json.loads(client.get("/bank/work/qbo-preview.json").data)
    check("J. the preview is labelled a preview", preview["kind"].startswith("PREVIEW"))

    # ------------------------------------------------------------- K. permissions and navigation
    limited = login("ur_review_only")
    check("K. an account limited to other Bank items does not get the new page by default",
          limited.get("/bank/work").status_code == 403 and limited.get("/bank/work/qbo").status_code == 403
          and limited.post("/bank/work/reconcile").status_code == 403)
    check("K. the Bank guide stays readable", limited.get("/bank/how-it-works").status_code == 200)
    instructions = page("/bank/instructions")
    check("K. Instructions point to the daily path and the guide", "/bank/work" in instructions
          and "/bank/how-it-works#upload-and-reconcile" in instructions)
    check("K. Import and Review (by month) stays reachable", client.get("/bank").status_code == 200)

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        import gc
        import db as web_db
        web_db._engine.dispose()
        for name, module in list(sys.modules.items()):
            if name == "cbank.legacy":
                for factory in [module._Session, *module._Writers.values()]:
                    if factory is not None:
                        factory.kw["bind"].dispose()
        gc.collect()
        shutil.rmtree(_FOLDER, ignore_errors=True)
    sys.exit(code)
