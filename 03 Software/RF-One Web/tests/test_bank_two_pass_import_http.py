#!/usr/bin/env python
"""HTTP test for the two-pass Bank import (BANK_TWO_PASS_IMPORT_001).

Pass 1 sets the Sources — ONE "Complete Source" per row, the Source modal,
whose Save creates or completes the Source and links it to the file
(account from the NAME, layout from the content; nothing created until Save,
no duplicate, PayPal / Amazon too); Pass 2 reads
and checks the rows with ONE duplicate key — date + description + amount —
against stored transactions and the rest of the upload; the person decides
every flagged row; only Confirm writes, once, all or nothing. PayPal and
Amazon files are recognised and kept, never read by a bank parser.

Runs against a DISPOSABLE SQLite database and staging folder created here.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import date

import markupsafe

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_two_pass_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "two-pass-test-secret"
_STAGING_DIR = tempfile.mkdtemp(prefix="rfoneweb_two_pass_staging_")

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import configuration as config_service  # noqa: E402
from rfone_data_store.bank_reconciliation import import_session  # noqa: E402

web_app.app.config["BANK_IMPORT_STAGING_DIR"] = _STAGING_DIR
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
TOKEN_RE = re.compile(r"/bank/import/([0-9a-f]{32})")

CARD_WITH = "Card,Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
CARD_NO = "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
BANK = "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"

FILES = [
    # 0: card 3144 export carrying TWO in-file cards (2270, 3144), and a
    #    genuine same-day repeat inside the file (two coffees).
    ("Chase3144_Activity_20261007.csv", (CARD_WITH
        + "2270,10/01/2026,10/02/2026,STARBUCKS 123,Food,Sale,-5.00,\n"
        + "2270,10/01/2026,10/02/2026,STARBUCKS 123,Food,Sale,-5.00,\n"
        + "3144,10/03/2026,10/03/2026,HOME DEPOT 44,Home,Sale,-80.00,\n"
        + "3144,10/04/2026,10/04/2026,SHELL OIL 9,Gas,Sale,-40.00,\n").encode()),
    # 1: the SAME card in the other layout ("(1)" names no other account):
    #    the HOME DEPOT row repeats file 0 across layouts.
    ("Chase3144_Activity_20261007 (1).csv", (CARD_NO
        + "10/03/2026,10/03/2026,HOME DEPOT 44,Home,Sale,-80.00,\n"
        + "10/05/2026,10/05/2026,PUBLIX 1661,Groceries,Sale,-30.00,\n").encode()),
    # 2: a bank account, one row already stored, one unreadable row.
    ("Chase0214_Activity_20261007.csv", (BANK
        + "DEBIT,10/06/2026,ADP PAYROLL,-1000.00,ACH_DEBIT,5000.00,\n"
        + "CREDIT,10/07/2026,INTEREST PAYMENT,0.28,MISC_CREDIT,5000.28,\n"
        + "DEBIT,not-a-date,BROKEN ROW,,ACH_DEBIT,,\n").encode()),
    # 3: no account in the name -> the person chooses.
    ("statement.csv", (CARD_NO + "10/08/2026,10/08/2026,UNIQUE SHOP,Shop,Sale,-12.00,\n").encode()),
    ("Paypal.CSV", b"Date,Time,TimeZone,Name,Type,Status,Currency,Amount,Fees,Total,Exchange Rate,Receipt ID,Balance,Transaction ID,Item Title\n"
                   b"10/01/2026,10:00:00,PDT,ACME,Express Checkout Payment,Completed,USD,-9.00,0.00,-9.00,,,0.00,1AB,\n"),
    ("Amazon- orders.csv", b"Order ID,Order Date,ASIN,Title,Item Subtotal,Payment Amount\n112-1,10/01/2026,B01,Cup,9.00,9.00\n"),
    # 6: a layout nobody knows.
    ("contacts.csv", b"Name,Phone\nAlice,555\n"),
]


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}"
              + ("" if condition or not detail else f"   [{str(detail)[:300]}]"))

    try:
        with SessionFactory() as db:
            account_service.create_account(db, username="tp_operator", display_name="tp_operator",
                                           password="OperatorPass123!", status="ACTIVE", is_admin=False)
            db.commit()
            operator = db.query(m.RFOneAccount).filter_by(username="tp_operator").one()
            account_service.set_domain_access(db, account_id=operator.id, domain_code="BANK", enabled=True,
                                              role_code=None)
            # An existing Source with a transaction already stored.
            other = m.PaymentInstrument(display_name="Old Card", instrument_type="CREDIT_CARD",
                                        institution="Chase", last_four="9999", status="ACTIVE")
            db.add(other)
            db.flush()
            db.add(m.FinancialTransaction(
                payment_instrument_id=other.id, bank_source="CHASE_CREDIT_CARD_NO_CARD",
                posting_date=date(2026, 10, 6), description_original="ADP PAYROLL",
                description_normalized="ADP PAYROLL", amount_minor=-100000, status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW"))
            llc = config_service.create_entity(db, name="Test Owner, LLC", legal_name="Test Owner, LLC")
            db.commit()
            other_id = other.id
            llc_id = llc.id

        client = web_app.app.test_client()
        client.post("/login", data={"username": "tp_operator", "password": "OperatorPass123!",
                                    "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})

        def csrf():
            return CSRF_RE.search(client.get("/bank").data.decode()).group(1)

        def counts():
            with SessionFactory() as s:
                return (s.scalar(select(func.count(m.FinancialTransaction.id))),
                        s.scalar(select(func.count(m.BankImportBatch.id))),
                        s.scalar(select(func.count(m.PaymentInstrument.id))))

        before = counts()
        resp = client.post("/bank/upload", content_type="multipart/form-data", data={
            "csrf_token": csrf(), "files": [(io.BytesIO(c), n) for n, c in FILES]})
        token = TOKEN_RE.search(resp.headers.get("Location", "")).group(1)
        page = client.get(f"/bank/import/{token}").data.decode("utf-8")
        check("upload opens the import session (no rehearsal import, nothing written)",
              resp.status_code == 302 and counts() == before and "Pass 1 &mdash; Sources" in page)
        check("PayPal and Amazon are recognised and shown, with their importer declared missing",
              "PayPal activity (CSV)" in page and "Amazon Business orders report (CSV)" in page
              and page.count("Importer not available &mdash; file kept for a later import") == 4)

        def session_state():
            path = os.path.join(_STAGING_DIR, token, "manifest.json")
            return json.load(open(path, encoding="utf-8"))["two_pass"]

        # ---------------------------------------------------------- Pass 1
        # BANK_COMPLETE_SOURCE_ALL_ROWS_001 — every row: ONE "Complete Source"
        # (the ONE Source modal); a Source is written only by its Save.
        def row_of(page, i):
            start = page.index(f'id="file-{i}"')
            return page[start:page.index("</tr>", start)]

        def modal_post(url, fields, index, token_=None):
            """The Source modal's one Save, as the page's script sends it,
            for file `index` of the session."""
            data = dict(fields, csrf_token=csrf(), import_token=token_ or token, import_file_index=str(index))
            return client.post(url, data=data, headers={"X-Requested-With": "fetch"})

        def existing_fields(instrument_id, **extra):
            with SessionFactory() as s:
                i = s.get(m.PaymentInstrument, instrument_id)
                data = {"display_name": i.display_name, "instrument_type": i.instrument_type,
                        "institution": i.institution or "", "last_four": i.last_four or "",
                        "keep_external_account_identifier": "1", "currency": i.currency or "", "status": i.status}
            data.update(extra)
            return data

        rows = [row_of(page, i) for i in range(7)]
        check("every row — Source or not, PayPal and Amazon too — has ONE action: Complete Source",
              all(r.count(">Complete Source</button>") == 1 for r in rows)
              and "<select" not in page[page.index('id="pass-1"'):page.index('id="pass-2"')]
              and "/prepare" not in page and "/hold" not in page and "/assign" not in page, rows[4][-500:])
        check("the Source state and the importer state are shown apart",
              "Source not set" in rows[4] and "Importer not available &mdash; file kept for a later import" in rows[4]
              and "Source not set" in rows[0] and "Bank statement" in rows[0])
        check("a row without Source carries what its file states, for the modal",
              "data-source-file=" in rows[0] and "Chase credit card" in rows[0], rows[0][:600])
        check("opening the session (and the modal: a page script) writes no Source", counts() == before)

        resp = modal_post("/bank/instruments/new", import_session.source_prefill(
            "BANK", "Chase", "CREDIT_CARD", "3144"), 0)
        state = session_state()
        check("Save of a new Source from a file creates it and links it to that file",
              resp.get_json().get("ok") and state["files"][0]["status"] == "READY" and state["files"][0]["created"],
              resp.get_data(as_text=True)[:200])
        with SessionFactory() as s:
            card = s.get(m.PaymentInstrument, state["files"][0]["source_id"])
            card_fields = (card.institution, card.instrument_type, card.last_four, card.legal_entity_id,
                           card.owner_reporting_entity_id)
        check("the created Source holds only what the file states (no owner, no LLC invented)",
              card_fields == ("Chase", "CREDIT_CARD", "3144", None, None), str(card_fields))
        client.get(f"/bank/import/{token}")
        state = session_state()
        check("the '(1)' copy gets the Source just created (a suffix is not another account)",
              state["files"][1]["source_id"] == state["files"][0]["source_id"] and not state["files"][1]["created"])
        sources_before = counts()[2]
        resp = modal_post("/bank/instruments/new", import_session.source_prefill(
            "BANK", "Chase", "CREDIT_CARD", "3144"), 1)
        check("a second New Source for the same account is refused: no duplicate",
              resp.status_code == 400 and "already" in resp.get_json()["error"]
              and counts()[2] == sources_before, resp.get_data(as_text=True)[:200])
        resp = modal_post("/bank/instruments/new", import_session.source_prefill(
            "BANK", "Chase", "BANK_ACCOUNT", "0214"), 2)
        check("the bank account file gets its new Source the same way", resp.get_json().get("ok")
              and session_state()["files"][2]["status"] == "READY")
        resp = client.post(f"/bank/import/{token}/check", data={"csrf_token": csrf()})
        check("Pass 2 is refused until every bank file has its Source", session_state()["check"] is None)
        resp = modal_post(f"/bank/instruments/{other_id}/edit", existing_fields(other_id), 3)
        check("choosing an EXISTING Source in the modal links it to the file (no Source created)",
              resp.get_json().get("ok") and session_state()["files"][3]["source_id"] == other_id
              and counts()[2] == sources_before + 1)
        sources_before = counts()[2]
        resp = modal_post("/bank/instruments/new", {"display_name": "Amazon Business",
                                                    "instrument_type": "PURCHASE_PLATFORM",
                                                    "institution": "Amazon", "last_four": "1111"}, 3)
        check("a bank statement cannot take a purchase platform: refused, nothing created",
              resp.status_code == 400 and counts()[2] == sources_before
              and session_state()["files"][3]["source_id"] == other_id, resp.get_data(as_text=True)[:200])
        resp = modal_post("/bank/instruments/new", import_session.source_prefill("PAYPAL_ACTIVITY", None, None, None), 4)
        resp2 = modal_post("/bank/instruments/new", import_session.source_prefill(
            "AMAZON_BUSINESS_ORDERS", None, None, None), 5)
        state = session_state()
        page = client.get(f"/bank/import/{token}").data.decode("utf-8")
        check("PayPal and Amazon get their Source although their importer does not exist yet",
              resp.get_json().get("ok") and resp2.get_json().get("ok")
              and state["files"][4]["source_id"] and state["files"][5]["source_id"]
              and "Source incomplete" in row_of(page, 4) and "Importer not available &mdash; file kept for a later import" in row_of(page, 4)
              and "Source complete" in row_of(page, 5), resp2.get_data(as_text=True)[:200])
        check("their Source does not decide their leave-out: still to be confirmed (never automatic)",
              [state["files"][i]["status"] for i in (4, 5)] == ["IMPORTER_MISSING", "IMPORTER_MISSING"])
        gone = modal_post("/bank/instruments/new", import_session.source_prefill(
            "BANK", "Chase", "CREDIT_CARD", "7777"), 0, token_="0" * 32)
        check("a Save for a session that no longer exists is refused whole: no Source written",
              gone.status_code == 400 and counts()[2] == sources_before + 2, gone.get_data(as_text=True)[:200])
        state = session_state()
        check("Pass 1 complete: bank Sources set; PayPal / Amazon / unknown file await their leave-out",
              [f["status"] for f in state["files"]] == ["READY", "READY", "READY", "READY", "IMPORTER_MISSING",
                                                        "IMPORTER_MISSING", "UNRECOGNIZED"],
              str([f["status"] for f in state["files"]]))
        check("Pass 1 wrote only Sources: no transaction, no batch", counts()[:2] == before[:2])

        # ------------------------------------- Complete Source (BANK_COMPLETE_SOURCE_001)
        card_id, bank_id = state["files"][0]["source_id"], state["files"][2]["source_id"]
        page = client.get(f"/bank/import/{token}").data.decode("utf-8")
        check("every row with a Source, new or existing, offers Complete Source with its data (the ONE modal)",
              page.count(">Complete Source</button>") == 7 and page.count("data-source='") == 6
              and 'data-source-return="#file-3"' in page and 'id="source-dialog"' in page
              and 'id="source-file-choice"' in page)
        rows = {i: row_of(page, i) for i in range(4)}
        check("each row says what its Source misses (card: settlement account; account: owner)",
              "Source incomplete" in rows[0] and "Settlement / Funding account" in rows[0]
              and "Owning entity" in rows[2] and "Settlement / Funding account" in rows[3]
              and "Owning entity" not in rows[0], rows[2][-400:])
        client.post(f"/bank/import/{token}/check", data={"csrf_token": csrf()})
        check("Pass 2 is refused while a Source of an included file is incomplete",
              session_state()["check"] is None and "Complete every Source first" in page
              and 'data-action="check" disabled' in page)

        def source_save(instrument_id, **fields):
            """The Source modal's one Save on a row that has its Source."""
            index = next(f["index"] for f in session_state()["files"] if f["source_id"] == instrument_id)
            return modal_post(f"/bank/instruments/{instrument_id}/edit", existing_fields(instrument_id, **fields),
                              index)

        before_save = session_state()
        resp = source_save(bank_id, owner_entity=f"re:{llc_id}")
        page = client.get(f"/bank/import/{token}").data.decode("utf-8")
        row2 = row_of(page, 2)
        check("Save updates the row (now complete) and keeps the session and every choice made",
              resp.get_json()["ok"] and "Source complete" in row2 and "Missing" not in row2
              and session_state() == before_save, resp.get_data(as_text=True)[:200])
        for source_id in (card_id, other_id):
            source_save(source_id, settlement_bank_account_id=str(bank_id), settlement_valid_from="2026-01-01")
        page = client.get(f"/bank/import/{token}").data.decode("utf-8")
        check("every bank file's Source complete: Pass 1 done and Pass 2 enabled — PayPal's incomplete Source "
              "does not block",
              all("Source incomplete" not in row_of(page, i) for i in range(4))
              and "Source incomplete" in row_of(page, 4) and 'data-action="check" disabled' not in page)

        # ---------------------------------------------------------- Pass 2
        client.post(f"/bank/import/{token}/check", data={"csrf_token": csrf()})
        state = session_state()
        issues = {(i["file_index"], i["row_number"]): i for i in state["check"]["issues"]}
        files0 = state["check"]["files"][0]
        check("Chase3144: in-file identifiers 2270 and 3144 are kept as data and do not block",
              files0["in_file_identifiers"] == ["2270", "3144"] and files0["source"] == card.display_name
              and not any(i["kind"] == "UNREADABLE" for k, i in issues.items() if k[0] == 0))
        same_file = issues.get((0, 3))
        check("a same-day repeat inside one file is flagged against its earlier row, explained",
              same_file is not None and same_file["kind"] == "DUPLICATE_IN_UPLOAD"
              and same_file["match"]["row_number"] == 2 and "same file" in " ".join(same_file["differences"]))
        across = issues.get((1, 2))
        check("an overlap across Chase layouts is flagged with file, row, Source and the layout difference",
              across is not None and across["match"]["file"] == "Chase3144_Activity_20261007.csv"
              and across["match"]["row_number"] == 4 and any("layout" in d for d in across["differences"]))
        stored = issues.get((2, 2))
        check("a row already stored (on ANOTHER Source) is flagged: the key ignores Source and card",
              stored is not None and stored["kind"] == "DUPLICATE_STORED" and stored["match"]["source"] == "Old Card"
              and any("different Source" in d for d in stored["differences"]), str(stored))
        broken = issues.get((2, 4))
        check("an unreadable row is listed with a precise reason", broken is not None and broken["kind"] == "UNREADABLE")
        check("no other row is flagged", len(issues) == 4, str(sorted(issues)))
        page = client.get(f"/bank/import/{token}").data.decode("utf-8")
        check("the log shows each row with its decisions and the Confirm summary",
              "Confirm exclusion" in page and "Import anyway: distinct operation" in page
              # BANK_POSSIBLE_DUPLICATES_001: only the unreadable row must be decided.
              and 'id="import-confirm" disabled' in page and re.search(r'data-figure="unresolved">1<', page))

        # Confirm refused while rows are undecided: nothing written.
        resp = client.post(f"/bank/upload/{token}/confirm", data={"csrf_token": csrf()})
        check("Confirm is refused while rows are undecided, and nothing is written",
              resp.status_code == 302 and "/bank/import/" in resp.headers["Location"] and counts()[:2] == before[:2])
        decide = lambda key, decision: client.post(  # noqa: E731
            f"/bank/import/{token}/decide", data={"csrf_token": csrf(), "key": key, "decision": decision})
        decide(same_file["key"], "IMPORT_DISTINCT")
        decide(across["key"], "EXCLUDE")
        decide(stored["key"], "EXCLUDE")
        decide(broken["key"], "IMPORT_DISTINCT")  # refused for an unreadable row
        check("an unreadable row cannot be made importable by an override",
              broken["key"] not in session_state()["decisions"])
        decide(broken["key"], "EXCLUDE")
        page = client.get(f"/bank/import/{token}").data.decode("utf-8")
        log = page[page.index('id="files-left-out"'):page.index('id="files-left-out"') + 6000]
        check("the review log lists each file that cannot be imported, with its name and precise reason",
              "contacts.csv" in log and "Not a known layout" in log
              and str(markupsafe.escape(session_state()["files"][6]["note"])) in log
              and session_state()["files"][6]["note"] and "Paypal.CSV" in log and "Amazon- orders.csv" in log and log.count("Importer not available &mdash; file kept for a later import") == 2, log[:800])
        check("rows all decided, but no file left out automatically: Confirm stays closed",
              'id="import-confirm" disabled' in page and "3 file(s) cannot be imported now" in page
              and re.search(r'data-figure="leave_outs_open">3<', page))
        resp = client.post(f"/bank/upload/{token}/confirm", data={"csrf_token": csrf()})
        check("Confirm is refused on the server too while a leave-out is unconfirmed: nothing written",
              "/bank/import/" in resp.headers["Location"] and counts()[:2] == before[:2])
        leave = lambda index, decision="LEAVE_OUT": client.post(  # noqa: E731
            f"/bank/import/{token}/leave-out", data={"csrf_token": csrf(), "file_index": str(index), "decision": decision})
        for index in (4, 5, 6):
            leave(index)
        leave(6, "OPEN")
        check("a leave-out can be taken back in the log", session_state()["files"][6]["status"] == "UNRECOGNIZED")
        leave(6)
        state_left = session_state()
        check("confirmed in the log: PayPal / Amazon kept for a later import, the unknown file left out",
              [state_left["files"][i]["status"] for i in (4, 5, 6)] == ["HELD", "HELD", "EXCLUDED"])
        page = client.get(f"/bank/import/{token}").data.decode("utf-8")
        check("the Source of a file left out (PayPal, incomplete) does not block the other files",
              "Owning entity" in row_of(page, 4))
        check("all decided: Confirm enabled, summary counts shown",
              'id="import-confirm" disabled' not in page and re.search(r'data-figure="excluded">3<', page)
              and re.search(r'data-figure="distinct">1<', page) and re.search(r'data-figure="unresolved">0<', page))

        resp = client.post(f"/bank/upload/{token}/confirm", data={"csrf_token": csrf()})
        replay = client.post(f"/bank/upload/{token}/confirm", data={"csrf_token": csrf()})
        with SessionFactory() as s:
            txns = s.scalars(select(m.FinancialTransaction).order_by(m.FinancialTransaction.id)).all()
            new = [t for t in txns if t.import_batch_id is not None]
            coffees = [t for t in new if t.description_original == "STARBUCKS 123"]
            batches = s.scalars(select(m.BankImportBatch).order_by(m.BankImportBatch.id)).all()
            log0 = json.loads(batches[0].import_log)
            card_ids = {t.payment_instrument_id for t in new if t.import_batch_id in (batches[0].id, batches[1].id)}
        check("Confirm imports exactly the kept rows: 4 + 1 + 1 + 1 = 7 transactions in 4 batches",
              len(new) == 7 and len(batches) == 4, f"{len(new)} {len(batches)}")
        check("the authorized repeat is really saved, as a distinct operation",
              len(coffees) == 2 and {t.duplicate_status for t in coffees} == {"NONE", "CONFIRMED_DISTINCT"},
              str([t.duplicate_status for t in coffees]))
        check("both Chase3144 files went to their file's Source, whatever their in-file cards",
              card_ids == {card.id})
        check("the decisions are kept in the import log",
              log0["decisions"][0]["decision"] == "IMPORT_DISTINCT" and log0["decisions"][0]["row_number"] == 3)
        check("a replayed Confirm imports nothing again", replay.status_code == 302 and len(new) == 7)
        held = os.path.join(_STAGING_DIR, "held", token)
        kept_sources = json.load(open(os.path.join(held, "sources.json"), encoding="utf-8"))
        check("the PayPal and Amazon files are kept for their importer, with their Source, not imported",
              sorted(os.listdir(held)) == ["Amazon- orders.csv", "Paypal.CSV", "sources.json"]
              and kept_sources == {"Paypal.CSV": state["files"][4]["source_id"],
                                   "Amazon- orders.csv": state["files"][5]["source_id"]}, str(os.listdir(held)))
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
        shutil.rmtree(_STAGING_DIR, ignore_errors=True)

    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    if failed:
        print("FAILED CHECKS:")
        for description in failed:
            print(f"  - {description}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
