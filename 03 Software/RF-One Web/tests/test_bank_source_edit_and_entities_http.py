#!/usr/bin/env python
"""HTTP test for the unified Source Edit and inline Entities
(BANK_SOURCE_EDIT_AND_ENTITIES_001).

One Edit per Source: the Source modal carries the general fields, the owner
(a company or a person) and, for a card, the settlement account and the
cardholder — one Save, atomic. "+ New Entity" creates a Company / LLC or a
Personal entity on top of the modal, reusing an equivalent active one. The
same Entity catalog feeds For Whom in Review Transactions.

Runs against a DISPOSABLE SQLite database created here and deleted at the end.
"""

from __future__ import annotations

import html as html_lib
import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_source_entities_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "source-entities-test-secret"

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
from rfone_data_store.bank_reconciliation import card_configuration  # noqa: E402
from rfone_data_store.bank_reconciliation import configuration as config_service  # noqa: E402
from rfone_data_store.bank_reconciliation import export as export_service  # noqa: E402
from rfone_data_store.bank_reconciliation import row_reconciliation  # noqa: E402
from rfone_data_store.bank_reconciliation import service as bank_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
FETCH = {"X-Requested-With": "fetch"}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}"
              + ("" if condition or not detail else f"   [{str(detail)[:300]}]"))

    try:
        # ------------------------------------------------------------ fixture
        ids: dict[str, int] = {}
        with SessionFactory() as db:
            account_service.create_account(db, username="se_operator", display_name="se_operator",
                                           password="OperatorPass123!", status="ACTIVE", is_admin=False)
            db.commit()
            operator = db.query(m.RFOneAccount).filter_by(username="se_operator").one()
            account_service.set_domain_access(db, account_id=operator.id, domain_code="BANK", enabled=True,
                                              role_code=None)
            angeli = config_service.create_entity(db, name="Angeli E Demoni, LLC", legal_name="Angeli E Demoni, LLC")
            dora = config_service.create_entity(db, name="RF Mount Dora, LLC", legal_name="RF Mount Dora, LLC")
            old = config_service.create_entity(db, name="Old Closed LLC", legal_name="Old Closed LLC", active=False)
            checking = bank_service.create_payment_instrument(
                db, institution="CHASE", display_name="WP-Checking", instrument_type="BANK_ACCOUNT",
                last_four="3376", legal_entity_id=angeli.legal_entity_id)
            dora_checking = bank_service.create_payment_instrument(
                db, institution="CHASE", display_name="RFMD Checking", instrument_type="BANK_ACCOUNT",
                last_four="4410", legal_entity_id=dora.legal_entity_id)
            card = bank_service.create_payment_instrument(
                db, institution="CHASE", display_name="Ink Card", instrument_type="CREDIT_CARD", last_four="1057")
            card_configuration.assign_settlement_account(
                db, credit_card_payment_instrument_id=card.id, settlement_bank_account_id=checking.id,
                valid_from=date(2026, 1, 1))
            t_checking = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 8, 5),
                description_original="ZELLE PAYMENT TO MARIA", description_normalized="ZELLE PAYMENT TO MARIA",
                amount_minor=-30000, status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW")
            db.add(t_checking)
            db.commit()
            ids.update(angeli=angeli.id, dora=dora.id, old=old.id, checking=checking.id,
                       dora_checking=dora_checking.id, card=card.id, t_checking=t_checking.id,
                       angeli_le=angeli.legal_entity_id, dora_le=dora.legal_entity_id)

        client = web_app.app.test_client()
        client.post("/login", data={"username": "se_operator", "password": "OperatorPass123!",
                                    "csrf_token": CSRF_RE.search(client.get("/login").data.decode()).group(1)})

        def page():
            return client.get("/bank/sources").data.decode("utf-8")

        def token():
            return CSRF_RE.search(page()).group(1)

        def owner_select(html):
            part = html[html.index('id="source-owner_entity"'):]
            return part[:part.index("</select>")]

        def counts():
            with SessionFactory() as s:
                return (s.scalar(select(func.count(m.ReportingEntity.id))),
                        s.scalar(select(func.count(m.LegalEntity.id))))

        def new_entity(name, kind, active="1"):
            return client.post("/bank/entities/new", headers=FETCH,
                               data={"csrf_token": token(), "name": name, "kind": kind, "active": active})

        def source_save(instrument_id, **fields):
            """The Source modal's one Save: the Source's current fields plus the changes."""
            with SessionFactory() as s:
                i = s.get(m.PaymentInstrument, instrument_id)
                data = {"display_name": i.display_name, "instrument_type": i.instrument_type,
                        "institution": i.institution or "", "last_four": i.last_four or "",
                        "keep_external_account_identifier": "1", "currency": i.currency or "", "status": i.status}
            data.update(fields)
            data["csrf_token"] = token()
            return client.post(f"/bank/instruments/{instrument_id}/edit", headers=FETCH, data=data)

        # ======================================================== BANK ACCOUNT 1-7
        html = page()
        with SessionFactory() as s:
            source_count = s.scalar(select(func.count(m.PaymentInstrument.id)))
        check("1. one Edit button per Source", html.count("data-source-edit") == source_count,
              f"{html.count('data-source-edit')} vs {source_count}")
        check("2. no Card settings button (no link to the former page)", "Card settings" not in html
              and f'href="/bank/instruments/{ids["card"]}/edit"' not in html)
        options = owner_select(html)
        check("3. Edit shows Owning Entity: the active companies, by name, without ids",
              'name="owner_entity"' in html and "Angeli E Demoni, LLC" in options and "RF Mount Dora, LLC" in options
              and options.index("Angeli E Demoni, LLC") < options.index("RF Mount Dora, LLC")
              and not re.search(r">\s*\d+\s*<", options))
        check("4. + New Entity is next to the owner, opening a dialog on top of the Source modal",
              'id="entity-new"' in html and 'id="entity-dialog"' in html
              and html.index('id="source-dialog"') < html.index('id="entity-dialog"'))

        before = counts()
        resp = new_entity("Personal — Pino", "PERSONAL")
        body = resp.get_json()
        with SessionFactory() as s:
            pino = s.scalars(select(m.ReportingEntity).where(m.ReportingEntity.name == "Personal — Pino")).one()
            ids["pino"] = pino.id
        check("5/16. Personal — Pino is created as a PERSONAL entity, with no LegalEntity",
              resp.status_code == 200 and body["ok"] and body["created"] and pino.entity_type == "PERSONAL"
              and pino.legal_entity_id is None and pino.status == "ACTIVE"
              and counts() == (before[0] + 1, before[1]), str(body))
        check("6. the dialog answers the new Entity's choice, which the modal selects at once",
              body["entity"] == {"value": f"re:{pino.id}", "label": "Personal — Pino", "kind": "Personal",
                                 "active": True})
        check("6. after a reload it is listed among the owners, under Personal",
              'label="Personal"' in owner_select(page())
              and f'<option value="re:{pino.id}">Personal — Pino</option>' in owner_select(page()))

        resp = client.post("/bank/instruments/new", headers=FETCH, data={
            "csrf_token": token(), "display_name": "Personal Checking", "instrument_type": "BANK_ACCOUNT",
            "institution": "CHASE", "last_four": "7001", "owner_entity": f"re:{pino.id}", "currency": "USD"})
        with SessionFactory() as s:
            personal = s.scalars(select(m.PaymentInstrument).where(
                m.PaymentInstrument.display_name == "Personal Checking")).one()
            ids["personal"] = personal.id
        check("7/12. a Source saves with Personal — Pino as its owner (a personal Source)",
              resp.get_json()["ok"] and personal.owner_reporting_entity_id == pino.id and personal.legal_entity_id is None)
        html = page()
        row = html[html.index(f'data-source-id="{personal.id}"'):]
        row = row[:row.index("</tr>")]
        check("7. the list shows the person as the owner", "Personal — Pino" in html_lib.unescape(row)
              and '<span class="cell-note">Personal</span>' in row)
        resp = source_save(ids["checking"], owner_entity=f"re:{pino.id}")
        with SessionFactory() as s:
            moved = s.get(m.PaymentInstrument, ids["checking"])
            owner_after = (moved.legal_entity_id, moved.owner_reporting_entity_id)
        resp_back = source_save(ids["checking"], owner_entity=f"re:{ids['angeli']}")
        with SessionFactory() as s:
            back = s.get(m.PaymentInstrument, ids["checking"])
        check("7. an existing bank account can move to a person and back to its company (one owner at a time)",
              resp.get_json()["ok"] and owner_after == (None, pino.id) and resp_back.get_json()["ok"]
              and (back.legal_entity_id, back.owner_reporting_entity_id) == (ids["angeli_le"], None))

        # ======================================================== CREDIT CARD 8-14
        html = page()
        card_row = html[html.index(f'data-source-id="{ids["card"]}"'):]
        card_row = card_row[:card_row.index("</tr>")]
        check("8. a card has one Edit button, no other action", card_row.count("data-source-edit") == 1
              and "Card settings" not in card_row and "<a " not in card_row.split('data-label="Actions"')[1])
        modal = html[html.index('id="source-dialog"'):]
        check("9. Edit shows the settlement / funding account (card only)",
              "Settlement / Funding account" in modal and 'name="settlement_bank_account_id"' in modal
              and 'data-source-only="CREDIT_CARD"' in modal)
        check("10. Edit shows the cardholder (card only)", 'name="cardholder"' in modal
              and 'name="cardholder_valid_from"' in modal)
        data = html_lib.unescape(re.search(r"data-source='([^']*)'", card_row).group(1))
        check("11. the card's owner is shown truthfully as derived from its settlement account",
              '"derived_owner": "Angeli E Demoni, LLC"' in data.replace('":"', '": "')
              and "derived from its settlement account" in open(
                  os.path.join(APP_DIR, "static", "js", "bank-source.js"), encoding="utf-8").read()
              and re.search(r'data-source-hide="[^"]*(?<![A-Z_])CREDIT_CARD(?![A-Z_])', modal) is not None)

        resp = source_save(ids["card"], settlement_bank_account_id=str(ids["dora_checking"]),
                           settlement_valid_from="2026-06-01", settlement_notes="moved to Mount Dora")
        with SessionFactory() as s:
            history = card_configuration.settlement_history(s, ids["card"])
            card = s.get(m.PaymentInstrument, ids["card"])
            derived = card_configuration.legal_entity_for(s, instrument=card, on_date=date(2026, 7, 1))
            derived_before = card_configuration.legal_entity_for(s, instrument=card, on_date=date(2026, 3, 1))
        check("12. a settlement change persists, with its history (the previous period closed, not lost)",
              resp.get_json()["ok"] and len(history) == 2 and history[0].settlement_bank_account_id == ids["dora_checking"]
              and history[1].valid_to == date(2026, 6, 1) and card.linked_instrument_id == ids["dora_checking"],
              str(resp.get_json()))
        check("28. ownership derivation unchanged: before / after the change date",
              derived.id == ids["dora_le"] and derived_before.id == ids["angeli_le"])

        resp = source_save(ids["card"], cardholder="other", cardholder_name="Giovanna Rossi",
                           cardholder_valid_from="2026-02-01")
        resp2 = source_save(ids["card"], cardholder="other", cardholder_name="Anthony Bianchi",
                            cardholder_valid_from="2026-07-01")
        with SessionFactory() as s:
            holders = card_configuration.cardholder_history(s, ids["card"])
        check("13. a cardholder change persists, with its history",
              resp.get_json()["ok"] and resp2.get_json()["ok"] and len(holders) == 2
              and holders[0].holder_display_name == "Anthony Bianchi" and holders[1].valid_to == date(2026, 7, 1))
        resp = source_save(ids["card"], status="INACTIVE")
        with SessionFactory() as s:
            inactive = s.get(m.PaymentInstrument, ids["card"]).status
        source_save(ids["card"], status="ACTIVE")
        with SessionFactory() as s:
            active_again = s.get(m.PaymentInstrument, ids["card"]).status
        check("14. Active / Inactive persists", resp.get_json()["ok"] and inactive == "INACTIVE"
              and active_again == "ACTIVE")
        resp = client.post("/bank/instruments/new", headers=FETCH, data={
            "csrf_token": token(), "display_name": "New Card", "instrument_type": "CREDIT_CARD",
            "institution": "CHASE", "last_four": "8800", "settlement_bank_account_id": str(ids["checking"]),
            "settlement_valid_from": "2026-01-01", "cardholder": "other", "cardholder_name": "Pino Rossi",
            "cardholder_valid_from": "2026-01-01"})
        with SessionFactory() as s:
            new_card = s.scalars(select(m.PaymentInstrument).where(m.PaymentInstrument.display_name == "New Card")).one()
            set_up = (card_configuration.current_settlement_account(s, new_card.id).id,
                      card_configuration.current_cardholder(s, new_card.id).holder_display_name)
        check("14b. a new card is created with its settlement account and cardholder in the same Save",
              resp.get_json()["ok"] and set_up == (ids["checking"], "Pino Rossi"))

        # ======================================================== ENTITY 15-19
        before = counts()
        resp = new_entity("RF Gelati, LLC", "COMPANY")
        with SessionFactory() as s:
            gelati = s.scalars(select(m.ReportingEntity).where(m.ReportingEntity.name == "RF Gelati, LLC")).one()
            gelati_legal = s.get(m.LegalEntity, gelati.legal_entity_id)
        check("15. a Company / LLC is created: a LegalEntity and its LEGAL entity",
              resp.get_json()["created"] and gelati.entity_type == "LEGAL" and gelati_legal.legal_name == "RF Gelati, LLC"
              and counts() == (before[0] + 1, before[1] + 1))
        before = counts()
        reused = [new_entity(name, kind).get_json() for name, kind in (
            ("PERSONAL - PINO", "PERSONAL"), ("Personal  Pino", "PERSONAL"), ("personal — pino", "COMPANY"),
            ("rf gelati llc", "COMPANY"))]
        check("17. an equivalent name is reused, never duplicated (dash / case / spaces / punctuation)",
              all(r["ok"] and not r["created"] for r in reused) and counts() == before
              and [r["entity"]["value"] for r in reused] == [f"re:{ids['pino']}"] * 3 + [f"re:{gelati.id}"], str(reused))
        refused = new_entity("old closed llc", "COMPANY").get_json()
        check("17. an equivalent INACTIVE entity is refused with the way back, not recreated",
              not refused["ok"] and "inactive" in refused["error"] and counts() == before)
        try:
            with SessionFactory() as s:
                config_service.create_entity(s, name="Personal-Pino", legal_name=None)
                s.commit()
            config_dup = False
        except ValueError:
            config_dup = True
        check("17. Configuration's own Entity creation uses the same protection", config_dup)
        html = page()
        review = client.get("/bank/review?year=2026&month=8").data.decode("utf-8")
        for_whom = review[review.index('name="for_whom_id"'):]
        for_whom = html_lib.unescape(for_whom[:for_whom.index("</select>")])
        check("18. inactive entities are not offered for normal selection (owner and For Whom)",
              "Old Closed LLC" not in owner_select(html) and "Old Closed LLC" not in for_whom)
        check("19/20. the same Entity list feeds For Whom: Personal — Pino is selectable there, no second record",
              "Personal — Pino" in for_whom and "RF Gelati, LLC" in for_whom and "Angeli E Demoni, LLC" in for_whom)

        # ======================================================== FOR WHOM 21-22
        resp = client.post(f"/bank/reconciliation/{ids['t_checking']}/for-whom", data={
            "csrf_token": token(), "for_whom_id": str(ids["pino"]), "return_to": "/bank/review?year=2026&month=8"})
        with SessionFactory() as s:
            allocation = s.scalars(select(m.BankTransactionAllocation).where(
                m.BankTransactionAllocation.financial_transaction_id == ids["t_checking"])).one()
            owner = s.get(m.PaymentInstrument, ids["checking"])
        check("21. For Whom may differ from the Source owner (Angeli's account, For Whom Personal — Pino)",
              resp.status_code == 302 and allocation.reporting_entity_id == ids["pino"]
              and owner.legal_entity_id == ids["angeli_le"])
        check("22. changing For Whom does not change the Source owner",
              owner.owner_reporting_entity_id is None and owner.legal_entity_id == ids["angeli_le"])

        # ======================================================== ATOMICITY 23-24
        with SessionFactory() as s:
            before_card = (s.get(m.PaymentInstrument, ids["card"]).display_name,
                           len(card_configuration.settlement_history(s, ids["card"])),
                           len(card_configuration.cardholder_history(s, ids["card"])))
        resp = source_save(ids["card"], display_name="Renamed Card", settlement_bank_account_id=str(ids["card"]),
                           settlement_valid_from="2026-09-01")
        with SessionFactory() as s:
            after_card = (s.get(m.PaymentInstrument, ids["card"]).display_name,
                          len(card_configuration.settlement_history(s, ids["card"])),
                          len(card_configuration.cardholder_history(s, ids["card"])))
        check("23. a card-specific failure rolls back the whole Source edit (name unchanged, nothing added)",
              resp.status_code == 400 and not resp.get_json()["ok"] and after_card == before_card,
              f"{resp.get_json()} {after_card}")
        resp = source_save(ids["card"], last_four="12", cardholder="other", cardholder_name="Someone Else",
                           cardholder_valid_from="2026-09-01", settlement_bank_account_id=str(ids["checking"]),
                           settlement_valid_from="2026-09-01")
        with SessionFactory() as s:
            after_general = (s.get(m.PaymentInstrument, ids["card"]).display_name,
                             len(card_configuration.settlement_history(s, ids["card"])),
                             len(card_configuration.cardholder_history(s, ids["card"])))
        check("24. a general Source failure changes no card setting (no settlement, no cardholder written)",
              resp.status_code == 400 and after_general == before_card, f"{resp.get_json()} {after_general}")

        # ======================================================== REGRESSION 25-28
        with SessionFactory() as s:
            result = bank_service.import_csv(
                s, file_bytes=("Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
                               "DEBIT,08/12/2026,US FOODS 1001,-41.00,ACH_DEBIT,900.00,\n").encode(),
                original_file_name="Chase3376_Activity_20260815.csv", uploaded_by_account_id=None)
            recognised = result.batch.payment_instrument_id
            s.rollback()
        check("25. Import Source recognition unchanged (a Chase####_Activity file resolves to its Source)",
              recognised == ids["checking"], str(recognised))
        with SessionFactory() as s:
            t = m.FinancialTransaction(
                payment_instrument_id=ids["personal"], bank_source="CHASE_BANK_ACCOUNT", posting_date=date(2026, 8, 9),
                description_original="PERSONAL ROW", description_normalized="PERSONAL ROW", amount_minor=-500,
                status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW")
            s.add(t)
            s.commit()
            kinds = {(b.kind, b.instrument_id) for b in export_service.compute_export_blockers(s, year=2026, month=8)}
            personal_txn = t
            defaults = (row_reconciliation.default_for_whom(s, s.get(m.PaymentInstrument, ids["checking"]), date(2026, 8, 5)),
                        row_reconciliation.default_for_whom(s, s.get(m.PaymentInstrument, ids["card"]), date(2026, 7, 1)),
                        row_reconciliation.default_for_whom(s, s.get(m.PaymentInstrument, ids["personal"]), personal_txn.posting_date))
        # BANK_EXPORT_BY_OWNER_001 — a person is a valid owner: a personal
        # Source has its own report and never blocks for lack of an LLC.
        check("26. Monthly Export Source blockers: neither a personal Source nor a company's is an owner blocker",
              (export_service.BLOCKER_NO_LEGAL_ENTITY, ids["personal"]) not in kinds
              and (export_service.BLOCKER_NO_LEGAL_ENTITY, ids["checking"]) not in kinds, str(kinds))
        check("27. For Whom defaults unchanged for companies (account -> its LLC, card -> settlement account's), "
              "and a personal Source defaults to its person",
              [d.id if d else None for d in defaults] == [ids["angeli"], ids["dora"], ids["pino"]],
              str([d.name if d else None for d in defaults]))

        # ======================================================== retired paths
        resp = client.get(f"/bank/instruments/{ids['card']}/edit")
        check("the former Card settings page opens the Source modal for that card",
              resp.status_code == 302 and resp.headers["Location"].endswith(f"/bank/sources?edit={ids['card']}"))
        check("no second writable path: the separate settlement / cardholder assign routes are gone",
              client.post(f"/bank/instruments/{ids['card']}/settlement", data={"csrf_token": token()}).status_code in (404, 405)
              and client.post(f"/bank/instruments/{ids['card']}/cardholder", data={"csrf_token": token()}).status_code in (404, 405))
        with SessionFactory() as s:
            row = card_configuration.settlement_history(s, ids["card"])[0]
        resp = client.post(f"/bank/instruments/{ids['card']}/settlement/{row.id}", headers=FETCH, data={
            "csrf_token": token(), "settlement_bank_account_id": str(ids["dora_checking"]),
            "valid_from": "2026-06-02", "notes": "corrected start"})
        with SessionFactory() as s:
            corrected = s.get(m.BankCardSettlementAccount, row.id)
        check("a past settlement period can still be corrected from the modal's history (kept, not deleted)",
              resp.get_json()["ok"] and corrected.valid_from == date(2026, 6, 2) and corrected.notes == "corrected start")
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
