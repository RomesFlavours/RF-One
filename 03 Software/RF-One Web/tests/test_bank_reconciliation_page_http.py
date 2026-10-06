#!/usr/bin/env python
"""HTTP test for the Bank Reconciliation rows (BANK_RECONCILIATION_001), as they
live today in Review > Reconciled (BANK_TWO_STAGE_REVIEW_001). The standalone
`/bank/reconciliation` month page and its WHO modal are retired
(BANK_FINAL_CLEANUP_001): the page redirects, the WHO and WHY are chosen in
Select WHO / WHY (`/bank/transactions/<id>/who-why`). The original points,
on the current workflow:

   1-6   page: real monthly rows, month selector, Account/Card, Date,
         Description, signed Amount;
   7-16  WHO / WHY: automatic, human and missing WHO; the modal's real WHO
         data; WHY limited to the WHO's possible WHY; default proposed only;
         another allowed WHY; invalid pairs; the authoritative decision
         service; WHAT never exposed;
  17-18  the retired WHO route is gone; Select WHO / WHY moves a row to Reconciled;
  19-23  For Whom: bank-account and card defaults, change, persistence,
         cross-LLC;
  24-28  row confirmation and derived status;
  29-31  security;
  32-34  performance: one modal, no Classification, a realistic month.

Runs against a DISPOSABLE SQLite database created here and deleted at the end.
"""

from __future__ import annotations

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
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from werkzeug.datastructures import MultiDict  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import card_configuration  # noqa: E402
from rfone_data_store.bank_reconciliation import configuration as config_service  # noqa: E402
from rfone_data_store.bank_reconciliation import receiver_candidates  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
REC = "/bank/review?view=reconciled&year=2026&month=8"
TO_REC = "/bank/review?year=2026&month=8"


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

        def page(url=REC) -> str:
            return client.get(url).data.decode("utf-8")

        html = page()
        token = CSRF_RE.search(html).group(1)

        def post(path, data, *, with_token=True, who=None):
            pairs = list(data.items()) if isinstance(data, dict) else list(data)
            if with_token:
                pairs.append(("csrf_token", token))
            return (who or client).post(path, data=MultiDict(pairs))

        def who_why(txn_id, occurrence_id, reason_id, **kw):
            data = {"occurrence_id": occurrence_id, "return_to": REC}
            if reason_id is not None:
                data["transaction_reason_id"] = reason_id
            return post(f"/bank/transactions/{txn_id}/who-why", data, **kw)

        def confirm(txn_id, entity_id):
            return post(f"/bank/reconciliation/{txn_id}/confirm", {"for_whom_id": entity_id, "return_to": REC})

        def row(html_text, txn_id) -> str:
            start = html_text.index(f'<tr id="t-{txn_id}"')
            return html_text[start:html_text.index("</tr>", start)]

        def attr(row_html, name):
            match = re.search(rf'{name}="([^"]*)"', row_html)
            return match.group(1) if match else None

        def flashes_after(response) -> str:
            return page(response.headers.get("Location", REC)) if response.status_code == 302 else ""

        def rec_ids(html_text):
            return set(int(x) for x in re.findall(r'data-row-id="(\d+)"', html_text))

        # ================================================================ 1-6
        to_reconcile = page(TO_REC)
        check("1. Reconciled holds the month's rows whose WHO is resolved (automatic t1, human t3); rows "
              "with no WHO stay in To Reconcile; a confirmed duplicate and other months are excluded",
              rec_ids(html) == {ids["t1"], ids["t3"]}
              and f'data-transaction-id="{ids["t2"]}"' in to_reconcile
              and f'data-transaction-id="{ids["t6"]}"' in to_reconcile, str(rec_ids(html)))
        july = client.get("/bank/reconciliation?year=2026&month=7")
        bare = client.get("/bank/reconciliation")
        check("2. the retired standalone page redirects to Review > Reconciled, keeping the month",
              july.status_code == 302 and july.headers["Location"] == "/bank/review?view=reconciled&year=2026&month=7"
              and bare.status_code == 302 and bare.headers["Location"] == "/bank/review?view=reconciled",
              f"{july.headers.get('Location')} {bare.headers.get('Location')}")
        r1, r3 = row(html, ids["t1"]), row(html, ids["t3"])
        check("3. Account / Card is the human label with its last digits",
              "Alpha Checking ··1111" in r1 and f">{ids['checking']}<" not in r1)
        check("4. Date is compact and correct", ">Aug 5<" in r1 and 'title="2026-08-05"' in r1)
        check("5. Description is the original bank text", "GORDON FOOD SERVICE #1234 ORLANDO FL" in r1)
        check("6. Amount is signed", "−1,284.37" in r1 and "+4,317.55" in r3 and "rp-in" in r3)

        # ================================================================ 7-16
        why_names = {k: None for k in ("food", "sales")}
        with SessionFactory() as db:
            for k in why_names:
                why_names[k] = db.get(m.BankTransactionReason, ids[k]).name
        check("7. an automatic WHO is shown as suggested, with its WHY",
              "Gordon Food Service" in r1 and "suggested" in r1 and why_names["food"] in r1)
        check("8. a human WHO is shown as chosen by a person", "Clover" in r3 and "rp-src-person" in r3
              and why_names["sales"] in r3)
        check("9. a missing WHO is not in Reconciled: it is work for To Reconcile",
              f'id="t-{ids["t6"]}"' not in html and f'id="t-{ids["t2"]}"' not in html)

        with SessionFactory() as db:
            rules_before = db.scalar(select(func.count(m.BankRecognitionRule.id)))
        response = who_why(ids["t1"], ids["gfs"], ids["cleaning"])
        with SessionFactory() as db:
            t1 = db.get(m.FinancialTransaction, ids["t1"])
            current = db.get(m.BankTransactionExplanation, t1.explanation_id)
            allocations_t1 = db.scalar(select(func.count()).where(m.BankTransactionAllocation.financial_transaction_id == ids["t1"]))
            rules_after = db.scalar(select(func.count(m.BankRecognitionRule.id)))
        check("13. the operator can choose another WHY than the default, in Select WHO / WHY",
              current.transaction_reason_id == ids["cleaning"] and current.occurrence_id == ids["gfs"])
        bad_who = who_why(ids["t1"], 999999, ids["food"])
        inactive_who = who_why(ids["t1"], ids["retired"], ids["food"])
        with SessionFactory() as db:
            still = db.get(m.BankTransactionExplanation, db.get(m.FinancialTransaction, ids["t1"]).explanation_id)
        check("14. an unknown or inactive WHO is refused (nothing written)",
              still.id == current.id and bad_who.status_code == 302 and inactive_who.status_code == 302)
        check("15. the WHO + WHY decision persists through the authoritative human-decision service "
              "(HUMAN decision, confirmer recorded), does NOT confirm the row, learns no rule, and returns "
              "to the same row of Reconciled",
              current.decision_source == "HUMAN" and current.confirmed_by_account_id == ids["rc_operator"]
              and current.decision_status in ("HUMAN_CONFIRMED", "HUMAN_OVERRIDDEN")
              and allocations_t1 == 0 and rules_after == rules_before and response.status_code == 302
              and response.headers["Location"].endswith(f"{REC}#t-{ids['t1']}"),
              f"{current.decision_status} {allocations_t1} {response.headers.get('Location')}")

        # ================================================================ 17-18
        # BANK_FINAL_CLEANUP_001: the standalone page's WHO modal (with inline
        # Add WHO) is retired; WHO creation is the WHO Rule / Configuration.
        retired_who = post(f"/bank/reconciliation/{ids['t2']}/who", {"occurrence_id": ids["amazon"], "why_id": ids["office"]})
        with SessionFactory() as db:
            t2_decision = db.get(m.FinancialTransaction, ids["t2"]).explanation_id
        check("17. the retired standalone WHO route is gone and writes nothing",
              retired_who.status_code == 404 and t2_decision is None)
        who_why(ids["t2"], ids["amazon"], ids["office"])
        html = page()
        check("18. a WHO + WHY chosen in Select WHO / WHY moves the row to Reconciled",
              ids["t2"] in rec_ids(html) and "Amazon" in row(html, ids["t2"]))

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
        response = confirm(ids["t1"], ids["beta"])
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
        refused = confirm(ids["t6"], ids["alpha"])
        refused_msg = flashes_after(refused)
        with SessionFactory() as db:
            t6_allocations = db.scalar(select(func.count()).where(m.BankTransactionAllocation.financial_transaction_id == ids["t6"]))
        check("24. Confirm is refused without WHO / WHY (the server refuses, nothing written)",
              t6_allocations == 0 and "WHO" in refused_msg)
        check("25. Confirm persists a HUMAN, COMPLETE allocation for the whole amount with the decision's WHY",
              a.status == "COMPLETE" and a.decision_source == "HUMAN" and a.decided_by_account_id == ids["rc_operator"]
              and a.transaction_reason_id == ids["cleaning"] and 'data-status="Confirmed"' in row(html, ids["t1"]))

        who_why(ids["t1"], ids["gfs"], ids["cleaning"])
        with SessionFactory() as db:
            kept = db.scalar(select(func.count()).where(m.BankTransactionAllocation.financial_transaction_id == ids["t1"]))
        who_why(ids["t1"], ids["gfs"], ids["food"])
        with SessionFactory() as db:
            after_change = db.scalar(select(func.count()).where(m.BankTransactionAllocation.financial_transaction_id == ids["t1"]))
        check("26. changing WHO/WHY after confirmation reopens the row (re-stating the same WHO/WHY does not)",
              kept == 1 and after_change == 0 and 'data-status="Needs review"' in row(page(), ids["t1"]))

        confirm(ids["t1"], ids["alpha"])
        confirm(ids["t1"], ids["brand"])
        with SessionFactory() as db:
            restated = db.scalars(select(m.BankTransactionAllocation).where(
                m.BankTransactionAllocation.financial_transaction_id == ids["t1"])).all()
        reopened = post(f"/bank/reconciliation/{ids['t1']}/reopen", {"return_to": REC})
        with SessionFactory() as db:
            after_reopen = db.scalar(select(func.count()).where(m.BankTransactionAllocation.financial_transaction_id == ids["t1"]))
        check("27. a new For Whom takes effect only through a new Confirm; Reopen withdraws the confirmation",
              len(restated) == 1 and restated[0].reporting_entity_id == ids["brand"] and after_reopen == 0
              and reopened.status_code == 302)

        confirm(ids["t3"], ids["beta"])
        html = page()
        statuses = {k: attr(row(html, ids[k]), "data-status") for k in ("t1", "t2", "t3")}
        check("28. status derives from persisted facts: Confirmed / Needs review (a suggestion is never done)",
              statuses == {"t1": "Needs review", "t2": "Needs review", "t3": "Confirmed"}
              and f'id="t-{ids["t6"]}"' not in html, str(statuses))

        # ================================================================ 29-31
        outsider = web_app.app.test_client()
        outsider.post("/login", data={"username": "rc_outsider", "password": "OperatorPass123!",
                                      "csrf_token": CSRF_RE.search(outsider.get("/login").data.decode("utf-8")).group(1)})
        anon = web_app.app.test_client().get(REC)
        o_get = outsider.get(REC)
        o_post = outsider.post(f"/bank/transactions/{ids['t6']}/who-why",
                               data={"occurrence_id": ids["amazon"], "transaction_reason_id": ids["office"]})
        with SessionFactory() as db:
            t6_decision = db.get(m.FinancialTransaction, ids["t6"]).explanation_id
        check("29. BANK access is required (anonymous, non-BANK account refused; nothing written)",
              anon.status_code in (302, 401, 403) and o_get.status_code in (302, 403)
              and o_post.status_code in (302, 400, 403) and t6_decision is None)
        no_token = who_why(ids["t6"], ids["amazon"], ids["office"], with_token=False)
        with SessionFactory() as db:
            t6_decision = db.get(m.FinancialTransaction, ids["t6"]).explanation_id
        check("30. CSRF is required", no_token.status_code in (400, 403) and t6_decision is None)
        bad = [
            who_why(999999, ids["amazon"], ids["office"]),
            confirm(ids["t3"], 999999),
            confirm(ids["t3"], ids["gamma"]),
            who_why(ids["t6"], "abc", ids["office"]),
            who_why(ids["t6"], ids["retired"], ids["office"]),
        ]
        with SessionFactory() as db:
            t3_alloc = db.scalars(select(m.BankTransactionAllocation).where(
                m.BankTransactionAllocation.financial_transaction_id == ids["t3"])).all()
            t6_decision = db.get(m.FinancialTransaction, ids["t6"]).explanation_id
        check("31. invalid ids are refused: unknown transaction, unknown / inactive entity, "
              "non-numeric and inactive WHO; every refusal stays in the Review",
              all(r.status_code == 302 for r in bad) and len(t3_alloc) == 1
              and t3_alloc[0].reporting_entity_id == ids["beta"] and t6_decision is None
              and all(r.headers["Location"].startswith("/bank/review") for r in bad),
              str([(r.status_code, r.headers.get("Location")) for r in bad]))

        # ================================================================ 32-34
        html = page()
        check("32. one Select WHO / WHY popup for the whole page; the retired standalone WHO modal is gone",
              html.count('id="who-picker-search"') == 1 and 'id="rp-who-modal"' not in html)

        def refuse(*args, **kwargs):
            raise AssertionError("Classification must not run for Reconciliation")
        saved = receiver_candidates.build_candidates
        receiver_candidates.build_candidates = refuse
        try:
            get_ok = client.get(REC).status_code
            post_ok = who_why(ids["t6"], ids["amazon"], ids["office"]).status_code
        finally:
            receiver_candidates.build_candidates = saved
        check("33. no Classification call (GET and writes work with Classification disabled)",
              get_ok == 200 and post_ok == 302)

        with SessionFactory() as db:
            instruments = [db.get(m.PaymentInstrument, ids[k]) for k in ("checking", "operating", "card")]
            amazon_who = db.get(m.BankOccurrence, ids["amazon"])
            for i in range(450):
                t = m.FinancialTransaction(
                    payment_instrument_id=instruments[i % 3].id, bank_source="CHASE_BANK_ACCOUNT",
                    posting_date=date(2026, 6, 1 + i % 30), description_original=f"VENDOR {i} POS PURCHASE ORLANDO FL",
                    description_normalized=f"VENDOR {i}", amount_minor=-(1000 + i), status="COMPLETED",
                    duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                )
                db.add(t)
                db.flush()
                e = m.BankTransactionExplanation(financial_transaction_id=t.id, occurrence_id=amazon_who.id,
                                                 transaction_reason_id=ids["office"], decision_source="RULE",
                                                 decision_status="AUTO_APPLIED")
                db.add(e)
                db.flush()
                t.explanation_id = e.id
            for i in range(1200):
                db.add(m.BankOccurrence(canonical_name=f"Bulk Vendor {i:04d}", occurrence_type_id=amazon_who.occurrence_type_id, status="ACTIVE"))
            db.commit()
        started = time.perf_counter()
        june = client.get("/bank/review?view=reconciled&year=2026&month=6")
        elapsed = time.perf_counter() - started
        size_kb = len(june.data) / 1024
        print(f"        realistic month: 450 rows, 1,200+ WHO -> {elapsed * 1000:.0f} ms, {size_kb:.0f} KB")
        check("34. a realistic month (450 Reconciled rows, 1,200+ WHO) renders fast and compact",
              june.status_code == 200 and june.data.decode("utf-8").count('data-row-id="') == 450
              and elapsed < 3.0 and size_kb < 1536, f"{elapsed:.2f}s {size_kb:.0f}KB")
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
