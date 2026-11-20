#!/usr/bin/env python
"""Builds the verifiable QuickBooks Online sample of ONE company (BANK_UPLOAD_AND_RECONCILE_001), on a DISPOSABLE
SQLite database deleted at the end. Nothing is sent anywhere; the ChatGPT stage is not used.

Six movements of "Sample Co, LLC" (checking ··1001, savings ··1002, card ··2001), uploaded as bank files and decided
through Bank's own services, then exported through the real pages:

  1 simple expense        checking  -42.50  Office Depot          -> Supplies
  2 expense, 2 categories card      -100.00 Costco                -> Supplies 60.00 + Cleaning 40.00 (one payment)
  3 card refund           card      +15.99  Home Depot return     -> Supplies
  4 deposit               checking  +250.00 Catering deposit      -> Catering income
  5 own-account transfer  checking  -500.00 / savings +500.00     -> ONE transfer, no expense
  6 card payment          checking  -300.00 / card +300.00        -> ONE transfer to the card, no expense

Writes to tests/qbo_sample/: the generated file (as downloaded), the preview (JSON), the Account List used, and
CHECKS.md with every check and its outcome. Exit code 1 when a check fails.
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
from collections import defaultdict
from datetime import date
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
sys.path.insert(0, APP_DIR)
_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
sys.path.insert(0, _DATA_STORE_DIR)
OUT = Path(BASE_DIR, "qbo_sample")

_FOLDER = tempfile.mkdtemp(prefix="rfoneweb_qbo_sample_")
_DB = os.path.join(_FOLDER, "rfone.db")
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_DB.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "qbo-sample-secret"
os.environ.update(RFONE_BANK_GUIDED="1", RFONE_BANK_SINGLE_ENGINE="1", CBANK_BANK_DB=_DB,
                  CBANK_STORE_DIR=os.path.join(_FOLDER, "store"), CBANK_AUTO_RUN="0",
                  CBANK_BANK_CODE_ROOT=str(Path(APP_DIR).parents[1]))

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import bank_work_routes  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import card_configuration, configuration as config_service, split_allocation  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
BANK = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
CARD = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
CHECKING = (BANK + "DEBIT,10/01/2026,OFFICE DEPOT 1182,-42.50,DEBIT_CARD,1957.50,\n"
            + "CREDIT,10/05/2026,CATERING DEPOSIT EVENT 7,250.00,ACH_CREDIT,2207.50,\n"
            + "DEBIT,10/08/2026,ONLINE TRANSFER TO SAV 1002,-500.00,ACCT_XFER,1707.50,\n"
            + "DEBIT,10/20/2026,CHASE CREDIT CRD AUTOPAY,-300.00,ACH_DEBIT,1407.50,\n")
SAVINGS = BANK + "CREDIT,10/08/2026,ONLINE TRANSFER FROM CHK 1001,500.00,ACCT_XFER,5500.00,\n"
CARDF = (CARD + "10/03/2026,10/03/2026,COSTCO WHSE 0123,Shopping,Sale,-100.00,\n"
         + "10/10/2026,10/10/2026,HOME DEPOT RETURN 44,Home,Return,15.99,\n"
         + "10/20/2026,10/20/2026,AUTOMATIC PAYMENT - THANK,,Payment,300.00,\n")
ACCOUNT_LIST = ("Sample Co, LLC\nAccount List\n\nFull name,Type,Detail type\n"
                "Chase Checking 1001,Bank,Checking\nChase Savings 1002,Bank,Savings\n"
                "Ink Card 2001,Credit Card,Credit Card\nSupplies,Expenses,Supplies & Materials\n"
                "Cleaning,Expenses,Repair & Maintenance\nCatering income,Income,Sales of Product Income\n")


def main() -> int:
    results = []

    def check(label, ok, detail=""):
        results.append((label, bool(ok), str(detail)[:300]))
        print(("  PASS  " if ok else "  FAIL  ") + label + ("" if ok else f"   [{detail}]"))

    with SessionFactory() as db:
        account_service.create_account(db, username="sample_op", display_name="sample_op", password="OperatorPass123!",
                                       status="ACTIVE", is_admin=False)
        db.commit()
        op = db.query(m.RFOneAccount).filter_by(username="sample_op").one()
        account_service.set_domain_access(db, account_id=op.id, domain_code="BANK", enabled=True, role_code=None)
        co = config_service.create_entity(db, name="Sample Co, LLC", legal_name="Sample Co, LLC")

        def source(name, kind, digits):
            i = m.PaymentInstrument(display_name=name, instrument_type=kind, institution="Chase", last_four=digits,
                                    status="ACTIVE", owner_reporting_entity_id=co.id if kind == "BANK_ACCOUNT" else None,
                                    effective_start_date=date(2026, 10, 1))
            db.add(i)
            db.flush()
            return i
        chk, sav, card = source("Checking", "BANK_ACCOUNT", "1001"), source("Savings", "BANK_ACCOUNT", "1002"), \
            source("Ink card", "CREDIT_CARD", "2001")
        card_configuration.assign_settlement_account(db, credit_card_payment_instrument_id=card.id,
                                                     settlement_bank_account_id=chk.id, valid_from=date(2026, 1, 1))
        why = {r.name: r for r in db.scalars(select(m.BankTransactionReason))}
        cleaning_what = db.scalar(select(m.BankAccountingClassification).where(
            m.BankAccountingClassification.node_type == "POSTING",
            m.BankAccountingClassification.name.like("%Cleaning%")))
        cleaning = next((r for r in why.values() if cleaning_what and r.accounting_classification_id == cleaning_what.id), None) \
            or config_service.create_why(db, name="Cleaning Supplies (sample)", description=None,
                                         what_id=cleaning_what.id if cleaning_what else None)
        catering_what = db.scalar(select(m.BankAccountingClassification).where(
            m.BankAccountingClassification.code == "4310"))           # Catering / Event Revenue
        catering = config_service.create_why(db, name="Catering Sales (sample)", description=None, what_id=catering_what.id)
        supplies = why["Restaurant Operating Supplies"]
        whos = {n: config_service.save_who(db, occurrence_id=None, name=n, active=True, reason_ids=[], default_reason_id=None,
                                           reporting_entity_ids=[]).id for n in ("OFFICE DEPOT", "COSTCO", "HOME DEPOT", "EVENT CLIENT")}
        db.commit()
        ids = dict(co=co.id, chk=chk.id, sav=sav.id, card=card.id, supplies=supplies.id, cleaning=cleaning.id,
                   catering=catering.id, **{f"who_{k}": v for k, v in whos.items()})

    client = web_app.app.test_client()
    client.post("/login", data={"username": "sample_op", "password": "OperatorPass123!",
                                "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})

    def csrf():
        return CSRF_RE.search(client.get("/bank/work").data.decode()).group(1)

    client.post("/bank/work/upload", content_type="multipart/form-data", data={"csrf_token": csrf(), "files": [
        (io.BytesIO(CHECKING.encode()), "Chase1001_Activity20261001_20261031_20261101.csv"),
        (io.BytesIO(SAVINGS.encode()), "Chase1002_Activity20261001_20261031_20261101.csv"),
        (io.BytesIO(CARDF.encode()), "Chase2001_Activity20261001_20261031_20261101.csv")]})

    with SessionFactory() as db:
        t = {x.description_original: x for x in db.scalars(select(m.FinancialTransaction))}
        check("6 movements uploaded as 8 bank rows (two transfers have two legs)", len(t) == 8, sorted(t))
        single = [("OFFICE DEPOT 1182", "OFFICE DEPOT", ids["supplies"]), ("HOME DEPOT RETURN 44", "HOME DEPOT", ids["supplies"]),
                  ("CATERING DEPOSIT EVENT 7", "EVENT CLIENT", ids["catering"])]
        out = bank_work_routes.confirm_proposals(db, [dict(txn_id=t[d].id, who_id=ids[f"who_{w}"], why_id=y)
                                                      for d, w, y in single], account_id=None, note="QBO sample")
        costco = t["COSTCO WHSE 0123"]
        split_allocation.confirm_split(db, costco.id, [
            dict(amount_minor=-6000, why_id=ids["supplies"], description="Paper goods and supplies", items=[]),
            dict(amount_minor=-4000, why_id=ids["cleaning"], description="Cleaning products", items=[])], account_id=None)
        from rfone_data_store.bank_reconciliation import recognition
        recognition.record_human_decision(db, recognition.HumanDecisionRequest(
            transaction_id=costco.id, occurrence_id=ids["who_COSTCO"], confirmed_by_account_id=None,
            transaction_reason_id=ids["supplies"], notes="QBO sample (split)", record_association=False))
        costco.review_status = "REVIEWED"
        for a, b, kind in (("ONLINE TRANSFER TO SAV 1002", "ONLINE TRANSFER FROM CHK 1001", "INTERNAL_TRANSFER"),
                           ("CHASE CREDIT CRD AUTOPAY", "AUTOMATIC PAYMENT - THANK", "CARD_SETTLEMENT")):
            if not db.scalar(select(m.FinancialTransactionMatch).where(m.FinancialTransactionMatch.transaction_a_id.in_([t[a].id, t[b].id]))):
                db.execute(text("insert into financial_transaction_matches(transaction_a_id, transaction_b_id, match_type, "
                                "match_method, matched_amount_minor, relationship) values (:a, :b, :k, 'ENGINE', :n, 'SAME_OWNER')"),
                           dict(a=t[a].id, b=t[b].id, k=kind, n=abs(t[a].amount_minor)))
        db.commit()
        check("decisions recorded through Bank's services", out["written"] == 3 and not out["skipped"], out)
        whats = {r.id: r.accounting_classification_id for r in db.scalars(select(m.BankTransactionReason))}

    def post(path, **data):
        return client.post(path, data=dict(csrf_token=csrf(), **data), follow_redirects=True).data.decode("utf-8")

    client.post("/bank/work/qbo/accounts", content_type="multipart/form-data", data={
        "csrf_token": csrf(), "company_id": ids["co"], "file": (io.BytesIO(ACCOUNT_LIST.encode()), "AccountList.csv")})
    for kind, local, name in [("PAYMENT_ACCOUNT", ids["chk"], "Chase Checking 1001"), ("PAYMENT_ACCOUNT", ids["sav"], "Chase Savings 1002"),
                              ("PAYMENT_ACCOUNT", ids["card"], "Ink Card 2001"), ("CATEGORY", whats[ids["supplies"]], "Supplies"),
                              ("CATEGORY", whats[ids["cleaning"]], "Cleaning"), ("CATEGORY", whats[ids["catering"]], "Catering income")]:
        post("/bank/work/qbo/map", company_id=ids["co"], kind=kind, local_id=local, name=name)

    preview = json.loads(client.get("/bank/work/qbo-preview.json").data)
    items = {i["description"]: i for i in preview["items"]}
    blocked = {d: [b["code"] for b in i["blockers"]] for d, i in items.items() if not i["ready"]}
    check("all 6 movements ready for Sample Co, LLC", preview["ready"] == 6 and not blocked, blocked)
    post("/bank/work/qbo/export", company_id=ids["co"], feeds_excluded="1")
    with SessionFactory() as db:
        batch = db.scalar(select(m.BankQboExportBatch))
        batch_id = batch.id
    content = client.get(f"/bank/work/qbo/files/{batch_id}").data.decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(content)))
    by_j = defaultdict(list)
    for r in rows:
        by_j[r["Journal No"]].append(r)

    def cents(v):
        return round(float(v) * 100) if v else 0

    entity = {i["description"]: i["entity"] for i in preview["items"]}
    check("6 journal entries, one per movement (the two legs of a transfer are ONE entry)", len(by_j) == 6, list(by_j))
    check("every entry balances: debits = credits", all(sum(cents(r["Debits"]) for r in rs) == sum(cents(r["Credits"]) for r in rs)
                                                        for rs in by_j.values()))
    check("exactly ONE line on the bank / card account per entry (one payment = one register line)",
          all(sum(r["Account Name"] in ("Chase Checking 1001", "Ink Card 2001", "Chase Savings 1002") for r in rs)
              == (2 if any("TRANSFER" in r["Description"] or "AUTOPAY" in r["Description"] for r in rs) else 1)
              for rs in by_j.values()))

    def lines(desc):
        j = f"RFB-{items[desc]['txn_id']}"
        return {(r["Account Name"], cents(r["Debits"]), cents(r["Credits"])) for r in by_j.get(j, [])}
    expect = {
        "OFFICE DEPOT 1182": {("Chase Checking 1001", 0, 4250), ("Supplies", 4250, 0)},
        "COSTCO WHSE 0123": {("Ink Card 2001", 0, 10000), ("Supplies", 6000, 0), ("Cleaning", 4000, 0)},
        "HOME DEPOT RETURN 44": {("Ink Card 2001", 1599, 0), ("Supplies", 0, 1599)},
        "CATERING DEPOSIT EVENT 7": {("Chase Checking 1001", 25000, 0), ("Catering income", 0, 25000)},
        "ONLINE TRANSFER TO SAV 1002": {("Chase Savings 1002", 50000, 0), ("Chase Checking 1001", 0, 50000)},
        "CHASE CREDIT CRD AUTOPAY": {("Ink Card 2001", 30000, 0), ("Chase Checking 1001", 0, 30000)},
    }
    for desc, want in expect.items():
        check(f"{desc}: {entity.get(desc)} — accounts, signs and amounts", lines(desc) == want, lines(desc))
    check("the transfer and the card payment touch no expense account (no duplicated expense)",
          not {a for d in ("ONLINE TRANSFER TO SAV 1002", "CHASE CREDIT CRD AUTOPAY") for a, _x, _y in lines(d)}
          & {"Supplies", "Cleaning", "Catering income"})
    check("API preview: Purchase, Purchase with 2 lines, Purchase Credit=true, Deposit, 2 Transfers",
          [entity[d] for d in expect] == ["Purchase", "Purchase", "Purchase", "Deposit", "Transfer", "Transfer"]
          and len(items["COSTCO WHSE 0123"]["payload"]["Line"]) == 2 and items["HOME DEPOT RETURN 44"]["payload"].get("Credit") is True,
          [entity.get(d) for d in expect])
    again = client.get(f"/bank/work/qbo/files/{batch_id}").data.decode("utf-8")
    with SessionFactory() as db:
        n_batches = db.scalar(select(m.BankQboExportBatch.id).order_by(m.BankQboExportBatch.id.desc()))
        status = db.get(m.BankQboExportBatch, batch_id).status
    check("a second download is the same file and creates no new batch; state stays 'generated'",
          again == content and n_batches == batch_id and status == "GENERATED")

    OUT.mkdir(exist_ok=True)
    (OUT / "QBO_journal_entries_Sample_Co_LLC.csv").write_text(content, encoding="utf-8", newline="")
    (OUT / "AccountList_Sample_Co_LLC.csv").write_text(ACCOUNT_LIST, encoding="utf-8", newline="")
    (OUT / "preview_Sample_Co_LLC.json").write_text(json.dumps(preview, indent=2, default=str), encoding="utf-8")
    ok = all(r[1] for r in results)
    (OUT / "CHECKS.md").write_text(
        "# QBO sample — Sample Co, LLC — checks\n\nGenerated by `tests/build_qbo_sample.py` on a disposable database. "
        "**QBO import not yet verified**: nothing was imported or sent to QuickBooks.\n\n| Check | Outcome |\n|---|---|\n"
        + "".join(f"| {label} | {'PASS' if passed else 'FAIL — ' + detail} |\n" for label, passed, detail in results),
        encoding="utf-8")
    print(f"\n{sum(r[1] for r in results)} passed, {sum(not r[1] for r in results)} failed. Files in {OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        try:
            from db import _engine
            _engine.dispose()
            if os.environ.get("QBO_SAMPLE_KEEP_DB"):     # a disposable copy for a visual check, never the work DB
                shutil.copyfile(_DB, os.environ["QBO_SAMPLE_KEEP_DB"])
            shutil.rmtree(_FOLDER, ignore_errors=True)
        except Exception:  # noqa: BLE001
            pass
    sys.exit(code)
