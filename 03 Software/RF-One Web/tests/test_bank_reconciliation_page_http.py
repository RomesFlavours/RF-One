#!/usr/bin/env python
"""HTTP test for the real Bank Reconciliation page (BANK_RECONCILIATION_001).

Thirty-four numbered points, as specified by the Product Owner:

   1-6   page: real monthly rows, month selector, Account/Card, Date,
         Description, signed Amount;
   7-16  WHO / WHY: automatic, human and missing WHO; the modal's real WHO
         data; WHY limited to the WHO's possible WHY; default proposed only;
         another allowed WHY; invalid pairs; the authoritative decision
         service; WHAT never exposed;
  17-18  inline Add WHO through the Configuration service;
  19-23  For Whom: bank-account and card defaults, change, persistence,
         cross-LLC;
  24-28  row confirmation and derived status;
  29-31  security;
  32-34  performance: one modal, no Classification, a realistic month.

Runs against a DISPOSABLE SQLite database created here and deleted at the end.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_bank_recon_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-recon-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
import bank_routes  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from werkzeug.datastructures import MultiDict  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import card_configuration  # noqa: E402
from rfone_data_store.bank_reconciliation import configuration as config_service  # noqa: E402
from rfone_data_store.bank_reconciliation import receiver_candidates  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
AUG = "/bank/reconciliation?year=2026&month=8"


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
            print(f"  PASS  {description}")
        else:
            failed.append(description)
            print(f"  FAIL  {description}" + (f"   [{str(detail)[:300]}]" if detail else ""))

    try:
        # ------------------------------------------------------------ fixture
        ids: dict[str, int] = {}
        with SessionFactory() as db:
            for username, bank in (("rc_operator", True), ("rc_outsider", False)):
                account_service.create_account(
                    db, username=username, display_name=username, password="OperatorPass123!",
                    status="ACTIVE", is_admin=False,
                )
                db.commit()
                account = db.query(m.RFOneAccount).filter_by(username=username).one()
                ids[username] = account.id
                if bank:
                    account_service.set_domain_access(
                        db, account_id=account.id, domain_code="BANK", enabled=True, role_code=None,
                    )
            alpha = config_service.create_entity(db, name="Alpha", legal_name="Alpha Foods, LLC")
            beta = config_service.create_entity(db, name="Beta", legal_name="Beta Gelato, LLC")
            brand = config_service.create_entity(db, name="Brand X", legal_name="")
            gamma = config_service.create_entity(db, name="Gamma", legal_name="Gamma Old, LLC", active=False)
            checking = m.PaymentInstrument(display_name="Alpha Checking", instrument_type="BANK_ACCOUNT",
                                           institution="CHASE", last_four="1111",
                                           legal_entity_id=alpha.legal_entity_id, status="ACTIVE")
            operating = m.PaymentInstrument(display_name="Beta Operating", instrument_type="BANK_ACCOUNT",
                                            institution="CHASE", last_four="2222",
                                            legal_entity_id=beta.legal_entity_id, status="ACTIVE")
            # The card's OWN entity is Beta; its settlement account is Alpha's.
            card = m.PaymentInstrument(display_name="Ink Card", instrument_type="CREDIT_CARD",
                                       institution="CHASE", last_four="3333",
                                       legal_entity_id=beta.legal_entity_id, status="ACTIVE")
            db.add_all([checking, operating, card])
            db.flush()
            card_configuration.assign_settlement_account(
                db, credit_card_payment_instrument_id=card.id, settlement_bank_account_id=checking.id,
                valid_from=date(2026, 1, 1),
            )
            whys = db.scalars(select(m.BankTransactionReason).join(
                m.BankAccountingClassification,
                m.BankAccountingClassification.id == m.BankTransactionReason.accounting_classification_id,
            ).where(m.BankAccountingClassification.statement_type == "PROFIT_LOSS",
                    m.BankTransactionReason.status == "ACTIVE").order_by(m.BankTransactionReason.id).limit(4)).all()
            food, cleaning, office, sales = (w.id for w in whys)
            gfs = config_service.save_who(db, occurrence_id=None, name="Gordon Food Service", active=True,
                                          reason_ids=[food, cleaning], default_reason_id=food,
                                          reporting_entity_ids=[alpha.id], rules=[])
            amazon = config_service.save_who(db, occurrence_id=None, name="Amazon", active=True,
                                             reason_ids=[office], default_reason_id=office,
                                             reporting_entity_ids=[], rules=[])
            clover = config_service.save_who(db, occurrence_id=None, name="Clover", active=True,
                                             reason_ids=[sales], default_reason_id=sales,
                                             reporting_entity_ids=[beta.id], rules=[])
            retired = config_service.save_who(db, occurrence_id=None, name="Retired Vendor", active=False,
                                              reason_ids=[], default_reason_id=None,
                                              reporting_entity_ids=[], rules=[])

            def txn(instrument, day, text, minor, month=8, duplicate=None):
                t = m.FinancialTransaction(
                    payment_instrument_id=instrument.id, bank_source="CHASE_BANK_ACCOUNT",
                    posting_date=date(2026, month, day), description_original=text,
                    description_normalized=text, amount_minor=minor, status="COMPLETED",
                    duplicate_status=duplicate, review_status="REQUIRES_REVIEW",
                )
                db.add(t)
                db.flush()
                return t
            t1 = txn(checking, 5, "GORDON FOOD SERVICE #1234 ORLANDO FL", -128437)
            t2 = txn(card, 6, "AMAZON.COM*2K4LM7Q20 AMZN.COM/BILL WA", -8994)
            t3 = txn(operating, 10, "CLOVER DEPOSIT 080926 RF", 431755)
            t4 = txn(checking, 20, "JULY ONLY VENDOR", -1000, month=7)
            t5 = txn(checking, 21, "CONFIRMED DUPLICATE ROW", -2000, duplicate="CONFIRMED_DUPLICATE")
            t6 = txn(checking, 22, "ZELLE PAYMENT TO MARIA LOPEZ", -30000)
            # An automatic decision (RULE) on t1, a human one on t3.
            auto = m.BankTransactionExplanation(
                financial_transaction_id=t1.id, occurrence_id=gfs.id, transaction_reason_id=food,
                decision_source="RULE", decision_status="AUTO_APPLIED",
            )
            db.add(auto)
            db.flush()
            t1.explanation_id = auto.id
            db.commit()
            from rfone_data_store.bank_reconciliation import recognition
            recognition.record_human_decision(db, recognition.HumanDecisionRequest(
                transaction_id=t3.id, occurrence_id=clover.id, transaction_reason_id=sales,
                confirmed_by_account_id=ids["rc_operator"], learn_description=False,
            ))
            db.commit()
            ids.update(alpha=alpha.id, beta=beta.id, brand=brand.id, gamma=gamma.id,
                       checking=checking.id, operating=operating.id, card=card.id,
                       food=food, cleaning=cleaning, office=office, sales=sales,
                       gfs=gfs.id, amazon=amazon.id, clover=clover.id, retired=retired.id,
                       t1=t1.id, t2=t2.id, t3=t3.id, t4=t4.id, t5=t5.id, t6=t6.id)

        client = web_app.app.test_client()
        client.post("/login", data={
            "username": "rc_operator", "password": "OperatorPass123!",
            "csrf_token": CSRF_RE.search(client.get("/login").data.decode("utf-8")).group(1),
        })

        def page(url=AUG) -> str:
            return client.get(url).data.decode("utf-8")

        html = page()
        token = CSRF_RE.search(html).group(1)

        def post(path, data, *, with_token=True, who=None):
            pairs = list(data.items()) if isinstance(data, dict) else list(data)
            if with_token:
                pairs.append(("csrf_token", token))
            return (who or client).post(path, data=MultiDict(pairs))

        def row(html_text, txn_id) -> str:
            start = html_text.index(f'<tr id="t-{txn_id}"')
            return html_text[start:html_text.index("</tr>", start)]

        def attr(row_html, name):
            match = re.search(rf'{name}="([^"]*)"', row_html)
            return match.group(1) if match else None

        def catalog(html_text):
            return json.loads(re.search(r'<script type="application/json" id="rp-data">(.*?)</script>',
                                        html_text, re.S).group(1))

        def flashes_after(response) -> str:
            return page(response.headers.get("Location", AUG)) if response.status_code == 302 else ""

        # ================================================================ 1-6
        row_ids = set(int(x) for x in re.findall(r'data-row-id="(\d+)"', html))
        check("1. the month's real FinancialTransaction rows render (confirmed duplicate and other "
              "months excluded; a NULL duplicate status kept)",
              row_ids == {ids["t1"], ids["t2"], ids["t3"], ids["t6"]}, str(row_ids))
        july = set(int(x) for x in re.findall(r'data-row-id="(\d+)"', page("/bank/reconciliation?year=2026&month=7")))
        original = bank_routes._previous_local_month
        bank_routes._previous_local_month = lambda tz: (2026, 7)
        try:
            default_rows = set(int(x) for x in re.findall(r'data-row-id="(\d+)"', page("/bank/reconciliation")))
        finally:
            bank_routes._previous_local_month = original
        check("2. the month selector works (?year&month) and the default is the previous local month",
              july == {ids["t4"]} and default_rows == {ids["t4"]} and "July 2026" in page("/bank/reconciliation?year=2026&month=7")
              and 'href="/bank/reconciliation?year=2026&amp;month=7"' in html,
              f"{july} {default_rows}")
        r1, r2, r3, r6 = (row(html, ids[k]) for k in ("t1", "t2", "t3", "t6"))
        check("3. Account / Card is the human label with its last digits",
              "Alpha Checking ··1111" in r1 and "Ink Card ··3333" in r2 and f">{ids['checking']}<" not in r1)
        check("4. Date is compact and correct", ">Aug 5<" in r1 and 'title="2026-08-05"' in r1)
        check("5. Description is the original bank text", "GORDON FOOD SERVICE #1234 ORLANDO FL" in r1)
        check("6. Amount is signed", "−1,284.37" in r1 and "+4,317.55" in r3 and "rp-in" in r3)

        # ================================================================ 7-16
        why_names = {k: None for k in ("food", "sales")}
        with SessionFactory() as db:
            for k in why_names:
                why_names[k] = db.get(m.BankTransactionReason, ids[k]).name
        check("7. an automatic WHO is shown as suggested, with its WHY underneath",
              "Gordon Food Service" in r1 and "suggested" in r1 and why_names["food"] in r1)
        check("8. a human WHO is shown as chosen by a person", "Clover" in r3 and "rp-src-person" in r3
              and why_names["sales"] in r3)
        check("9. a missing WHO is shown as such", "No WHO yet" in r6 and "No WHO yet" in r2)
        data = catalog(html)
        names = {w["name"] for w in data["whos"]}
        check("10. the WHO modal uses the real WHO records: active ones, not the inactive one",
              {"Gordon Food Service", "Amazon", "Clover"} <= names and "Retired Vendor" not in names)
        gfs_entry = next(w for w in data["whos"] if w["id"] == ids["gfs"])
        check("11. the WHY list is the WHO's configured possible WHY",
              sorted(gfs_entry["whys"]) == sorted([ids["food"], ids["cleaning"]]), str(gfs_entry))
        check("12. the WHO's default WHY is sent as the proposal", gfs_entry.get("default_why") == ids["food"])

        with SessionFactory() as db:
            rules_before = db.scalar(select(func.count(m.BankRecognitionRule.id)))
        response = post(f"/bank/reconciliation/{ids['t1']}/who", {"occurrence_id": ids["gfs"], "why_id": ids["cleaning"]})
        with SessionFactory() as db:
            t1 = db.get(m.FinancialTransaction, ids["t1"])
            current = db.get(m.BankTransactionExplanation, t1.explanation_id)
            allocations_t1 = db.scalar(select(func.count()).where(m.BankTransactionAllocation.financial_transaction_id == ids["t1"]))
            rules_after = db.scalar(select(func.count(m.BankRecognitionRule.id)))
        check("13. the operator can choose another allowed WHY than the default",
              current.transaction_reason_id == ids["cleaning"] and current.occurrence_id == ids["gfs"])

        bad_pair = post(f"/bank/reconciliation/{ids['t1']}/who", {"occurrence_id": ids["gfs"], "why_id": ids["office"]})
        bad_pair_msg = flashes_after(bad_pair)
        bad_who = post(f"/bank/reconciliation/{ids['t1']}/who", {"occurrence_id": 999999, "why_id": ""})
        with SessionFactory() as db:
            still = db.get(m.BankTransactionExplanation, db.get(m.FinancialTransaction, ids["t1"]).explanation_id)
        check("14. a WHY that is not one of the WHO's possible WHY, and an unknown WHO, are refused "
              "(nothing written)",
              still.id == current.id and "not one of" in bad_pair_msg and bad_who.status_code == 302)
        check("15. Confirm WHO persists through the authoritative human-decision service "
              "(HUMAN decision, confirmer recorded) and does NOT confirm the row or learn a rule",
              current.decision_source == "HUMAN" and current.confirmed_by_account_id == ids["rc_operator"]
              and current.decision_status in ("HUMAN_CONFIRMED", "HUMAN_OVERRIDDEN")
              and allocations_t1 == 0 and rules_after == rules_before and response.status_code == 302
              and response.headers["Location"].endswith(f"/bank/reconciliation?year=2026&month=8#t-{ids['t1']}"),
              f"{current.decision_status} {allocations_t1} {response.headers.get('Location')}")
        html = page()
        compact = html[html.index('<tbody id="rp-body">'):html.index("</tbody>", html.index('<tbody id="rp-body">'))]
        check("16. WHAT is not exposed on the compact rows (no WHAT label, accounting code or statement)",
              "WHAT" not in compact and "accounting_classification" not in html and "PROFIT_LOSS" not in html)

        # ================================================================ 17-18
        response = post(f"/bank/reconciliation/{ids['t2']}/who", [
            ("new_who", "1"), ("new_name", "Office Depot"), ("new_why_ids", ids["office"]),
            ("new_why_ids", ids["cleaning"]), ("new_default_why_id", ids["office"]),
            ("new_entity_ids", ids["alpha"]), ("why_id", ids["cleaning"]),
        ])
        with SessionFactory() as db:
            depot = db.scalar(select(m.BankOccurrence).where(m.BankOccurrence.canonical_name == "Office Depot"))
            depot_type = db.get(m.BankOccurrenceType, depot.occurrence_type_id).code if depot else None
            depot_whys = set(db.scalars(select(m.BankOccurrenceReasonAssociation.transaction_reason_id).where(
                m.BankOccurrenceReasonAssociation.occurrence_id == depot.id))) if depot else set()
            depot_entities = set(db.scalars(select(m.BankOccurrenceReportingEntity.reporting_entity_id).where(
                m.BankOccurrenceReportingEntity.occurrence_id == depot.id))) if depot else set()
            t2_decision = db.get(m.BankTransactionExplanation, db.get(m.FinancialTransaction, ids["t2"]).explanation_id)
        check("17. inline Add WHO creates a real COUNTERPARTY WHO through the Configuration service "
              "(possible WHY, default, entities served) and records it on the transaction",
              depot is not None and depot_type == "COUNTERPARTY"
              and depot_whys == {ids["office"], ids["cleaning"]} and depot.default_transaction_reason_id == ids["office"]
              and depot_entities == {ids["alpha"]} and t2_decision.occurrence_id == depot.id
              and t2_decision.transaction_reason_id == ids["cleaning"])
        ids["depot"] = depot.id
        html = page()
        check("18. the new WHO is immediately selectable (in the modal's catalog) and shown on its row",
              any(w["id"] == ids["depot"] for w in catalog(html)["whos"]) and "Office Depot" in row(html, ids["t2"]))

        # ================================================================ 19-23
        r1, r2 = row(html, ids["t1"]), row(html, ids["t2"])
        check("19. Bank Account default For Whom = the account's owning entity",
              attr(r1, "data-default") == str(ids["alpha"]))
        check("20. Credit Card default For Whom = the settlement account's entity, not the card's own",
              attr(r2, "data-default") == str(ids["alpha"]) and ids["alpha"] != ids["beta"])
        options = re.findall(r'<option value="(\d+)"', r1)
        check("21. the operator can choose any active domain entity (the WHO's served entities do not "
              "filter the list)",
              {str(ids["alpha"]), str(ids["beta"]), str(ids["brand"])} <= set(options)
              and str(ids["gamma"]) not in options)
        response = post(f"/bank/reconciliation/{ids['t1']}/confirm", {"for_whom_id": ids["beta"]})
        with SessionFactory() as db:
            allocations = db.scalars(select(m.BankTransactionAllocation).where(
                m.BankTransactionAllocation.financial_transaction_id == ids["t1"])).all()
            a = allocations[0] if allocations else None
        check("22. For Whom is persisted as the allocation's ReportingEntity",
              len(allocations) == 1 and a.reporting_entity_id == ids["beta"] and a.amount_minor == -128437)
        check("23. cross-LLC: Alpha's account paying for Beta derives the intercompany consequence",
              a is not None and a.payer_legal_entity_id is not None and a.intercompany_outcome == "CROSS_ENTITY", a and a.intercompany_outcome)

        # ================================================================ 24-28
        html = page()
        r6 = row(html, ids["t6"])
        refused = post(f"/bank/reconciliation/{ids['t6']}/confirm", {"for_whom_id": ids["alpha"]})
        refused_msg = flashes_after(refused)
        with SessionFactory() as db:
            t6_allocations = db.scalar(select(func.count()).where(m.BankTransactionAllocation.financial_transaction_id == ids["t6"]))
        check("24. Confirm is unavailable without WHO / WHY / For Whom (button disabled; the server refuses)",
              re.search(r'data-action="confirm" disabled', r6) is not None and t6_allocations == 0
              and "WHO" in refused_msg)
        check("25. Confirm persists a HUMAN, COMPLETE allocation for the whole amount with the decision's WHY",
              a.status == "COMPLETE" and a.decision_source == "HUMAN" and a.decided_by_account_id == ids["rc_operator"]
              and a.transaction_reason_id == ids["cleaning"] and 'data-status="Confirmed"' in row(html, ids["t1"]))

        post(f"/bank/reconciliation/{ids['t1']}/who", {"occurrence_id": ids["gfs"], "why_id": ids["cleaning"]})
        with SessionFactory() as db:
            kept = db.scalar(select(func.count()).where(m.BankTransactionAllocation.financial_transaction_id == ids["t1"]))
        post(f"/bank/reconciliation/{ids['t1']}/who", {"occurrence_id": ids["gfs"], "why_id": ids["food"]})
        with SessionFactory() as db:
            after_change = db.scalar(select(func.count()).where(m.BankTransactionAllocation.financial_transaction_id == ids["t1"]))
        check("26. changing WHO/WHY after confirmation reopens the row (re-stating the same WHO/WHY does not)",
              kept == 1 and after_change == 0 and 'data-status="Needs review"' in row(page(), ids["t1"]))

        post(f"/bank/reconciliation/{ids['t1']}/confirm", {"for_whom_id": ids["alpha"]})
        post(f"/bank/reconciliation/{ids['t1']}/confirm", {"for_whom_id": ids["brand"]})
        with SessionFactory() as db:
            restated = db.scalars(select(m.BankTransactionAllocation).where(
                m.BankTransactionAllocation.financial_transaction_id == ids["t1"])).all()
        reopened = post(f"/bank/reconciliation/{ids['t1']}/reopen", {})
        with SessionFactory() as db:
            after_reopen = db.scalar(select(func.count()).where(m.BankTransactionAllocation.financial_transaction_id == ids["t1"]))
        check("27. a new For Whom takes effect only through a new Confirm; Reopen withdraws the confirmation",
              len(restated) == 1 and restated[0].reporting_entity_id == ids["brand"] and after_reopen == 0
              and reopened.status_code == 302)

        post(f"/bank/reconciliation/{ids['t3']}/confirm", {"for_whom_id": ids["beta"]})
        html = page()
        statuses = {k: attr(row(html, ids[k]), "data-status") for k in ("t1", "t2", "t3", "t6")}
        check("28. status derives from persisted facts: Confirmed / Needs review (a suggestion is never done)",
              statuses == {"t1": "Needs review", "t2": "Needs review", "t3": "Confirmed", "t6": "Needs review"}, str(statuses))

        # ================================================================ 29-31
        outsider = web_app.app.test_client()
        outsider.post("/login", data={"username": "rc_outsider", "password": "OperatorPass123!",
                                      "csrf_token": CSRF_RE.search(outsider.get("/login").data.decode("utf-8")).group(1)})
        anon = web_app.app.test_client().get(AUG)
        o_get = outsider.get(AUG)
        o_post = outsider.post(f"/bank/reconciliation/{ids['t6']}/who", data={"occurrence_id": ids["amazon"]})
        with SessionFactory() as db:
            t6_decision = db.get(m.FinancialTransaction, ids["t6"]).explanation_id
        check("29. BANK access is required (anonymous, non-BANK account refused; nothing written)",
              anon.status_code in (302, 401, 403) and o_get.status_code in (302, 403)
              and o_post.status_code in (302, 400, 403) and t6_decision is None)
        no_token = post(f"/bank/reconciliation/{ids['t6']}/who", {"occurrence_id": ids["amazon"]}, with_token=False)
        with SessionFactory() as db:
            t6_decision = db.get(m.FinancialTransaction, ids["t6"]).explanation_id
        check("30. CSRF is required", no_token.status_code in (400, 403) and t6_decision is None)
        bad = [
            post("/bank/reconciliation/999999/who", {"occurrence_id": ids["amazon"]}),
            post(f"/bank/reconciliation/{ids['t3']}/confirm", {"for_whom_id": 999999}),
            post(f"/bank/reconciliation/{ids['t3']}/confirm", {"for_whom_id": ids["gamma"]}),
            post(f"/bank/reconciliation/{ids['t6']}/who", {"occurrence_id": "abc"}),
            post(f"/bank/reconciliation/{ids['t6']}/who", {"occurrence_id": ids["retired"]}),
        ]
        with SessionFactory() as db:
            t3_alloc = db.scalars(select(m.BankTransactionAllocation).where(
                m.BankTransactionAllocation.financial_transaction_id == ids["t3"])).all()
            t6_decision = db.get(m.FinancialTransaction, ids["t6"]).explanation_id
        check("31. invalid ids are refused: unknown transaction, unknown / inactive entity, "
              "non-numeric and inactive WHO",
              all(r.status_code == 302 for r in bad) and len(t3_alloc) == 1
              and t3_alloc[0].reporting_entity_id == ids["beta"] and t6_decision is None
              and all("/bank/reconciliation" in r.headers["Location"] for r in bad))

        # ================================================================ 32-34
        html = page()
        check("32. one reusable WHO modal; WHO options are not rendered per row",
              html.count('id="rp-who-modal"') == 1 and "rp-who-option\"" not in html.split("<script")[0]
              and html.count('name="csrf_token"') == 1)

        def refuse(*args, **kwargs):
            raise AssertionError("Classification must not run for Reconciliation")
        saved = receiver_candidates.build_candidates
        receiver_candidates.build_candidates = refuse
        try:
            get_ok = client.get(AUG).status_code
            post_ok = post(f"/bank/reconciliation/{ids['t6']}/who", {"occurrence_id": ids["amazon"], "why_id": ids["office"]}).status_code
        finally:
            receiver_candidates.build_candidates = saved
        check("33. no Classification call (GET and writes work with Classification disabled)",
              get_ok == 200 and post_ok == 302)

        with SessionFactory() as db:
            instruments = [db.get(m.PaymentInstrument, ids[k]) for k in ("checking", "operating", "card")]
            for i in range(450):
                db.add(m.FinancialTransaction(
                    payment_instrument_id=instruments[i % 3].id, bank_source="CHASE_BANK_ACCOUNT",
                    posting_date=date(2026, 6, 1 + i % 30), description_original=f"VENDOR {i} POS PURCHASE ORLANDO FL",
                    description_normalized=f"VENDOR {i}", amount_minor=-(1000 + i), status="COMPLETED",
                    duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                ))
            for i in range(1200):
                db.add(m.BankOccurrence(canonical_name=f"Bulk Vendor {i:04d}", occurrence_type_id=db.get(m.BankOccurrence, ids["gfs"]).occurrence_type_id, status="ACTIVE"))
            db.commit()
        started = time.perf_counter()
        june = client.get("/bank/reconciliation?year=2026&month=6")
        elapsed = time.perf_counter() - started
        size_kb = len(june.data) / 1024
        print(f"        realistic month: 450 rows, 1,200+ WHO -> {elapsed * 1000:.0f} ms, {size_kb:.0f} KB")
        check("34. a realistic month (450 rows, 1,200+ WHO) renders fast and compact",
              june.status_code == 200 and june.data.decode("utf-8").count('data-row-id="') == 450
              and elapsed < 3.0 and size_kb < 1024, f"{elapsed:.2f}s {size_kb:.0f}KB")
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
