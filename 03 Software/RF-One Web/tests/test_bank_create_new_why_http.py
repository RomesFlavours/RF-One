"""Create New WHY — ONE shared flow for both reconciliation modals.

On a throwaway database migrated to head, proves that Select WHO / WHY and
the WHO Rule modal create a WHY through the SAME dialog, route and service
(`manual_reconciliation.create_why_for_who`): name and WHY group are
required for a new WHY, its WHAT is optional (BANK_WHY_WITHOUT_WHAT_001); a normalized existing name is reused, never
duplicated; the WHY is added to the WHO (only if missing) in the same
database transaction, which is rolled back whole on any failure; the WHY
comes back to the modal that asked for it (selected in Select WHO / WHY,
ticked as a Possible WHY in the Rule modal); Confirm and Apply then behave
exactly as before — the Rule still gives the WHO only, never a WHY.

The "Withdrawal" case uses a WHAT of this disposable database only: the
real WHAT of a Withdrawal is the Product Owner's decision.

Never touches a real bank file, AWS, or any production database.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_create_why_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-create-why-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from sqlalchemy import func, select  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import manual_reconciliation  # noqa: E402
from rfone_data_store.bank_reconciliation import why_catalog  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
AUG = date(2026, 8, 12)
REVIEW_AUG = "/bank/review?year=2026&month=8"
JS_DIR = os.path.join(APP_DIR, "static", "js")


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        account_service.create_account(s, username="newwhy", display_name="New Why",
                                       password="CreateNewWhy123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="newwhy").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        legal = m.LegalEntity(legal_name="New Why LLC", status="ACTIVE")
        s.add(legal)
        s.flush()
        s.add(m.ReportingEntity(code="RE_NEW_WHY", name="New Why", entity_type="LEGAL",
                                legal_entity_id=legal.id, status="ACTIVE"))
        checking = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                       display_name="New Why Checking", institution="CHASE", last_four="0031",
                                       currency="USD")
        s.add(checking)
        s.flush()
        batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="seed.csv",
                                  raw_file_bytes=b"x", sha256="8" * 64, status="NORMALIZED",
                                  payment_instrument_id=checking.id)
        s.add(batch)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()

        def who(name):
            o = m.BankOccurrence(canonical_name=name, occurrence_type_id=counterparty.id, status="ACTIVE",
                                 optional_notes="Canonical WHO.")
            s.add(o)
            s.flush()
            return o

        atm = who("Corner ATM")
        zeta = who("Zeta Exchange")
        seq = [0]

        def tx(description):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", import_batch_id=batch.id,
                posting_date=AUG, transaction_date=AUG, description_original=description,
                description_normalized=description, amount_minor=-2000 - seq[0], status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"newwhy-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            return t

        atm_tx = tx("ATM WITHDRAWAL CORNER ATM 0042").id
        zeta_txs = [tx(f"ZETA EXCHANGE FEE {i}").id for i in range(3)]
        existing_tx = tx("CORNER ATM BALANCE INQUIRY").id
        pickup_tx = tx("CORNER ATM CASH PICKUP 0007").id
        whats = manual_reconciliation.what_options(s)
        test_what_id, other_what_id = whats[0]["id"], whats[1]["id"]
        balance_sheet = s.scalars(select(m.BankAccountingClassification).where(
            m.BankAccountingClassification.statement_type == "BALANCE_SHEET")).first()
        groups = why_catalog.groups(s)
        group_a, group_b = groups[0], groups[-1]   # first and last alphabetically
        existing_why = s.scalars(select(m.BankTransactionReason).where(
            m.BankTransactionReason.status == "ACTIVE",
            m.BankTransactionReason.accounting_classification_id.is_not(None))
            .order_by(m.BankTransactionReason.id)).first()
        existing_why_id, existing_why_name = existing_why.id, existing_why.name
        s.commit()
        ids = {"atm": atm.id, "zeta": zeta.id}
        snapshot = lambda: {t.id: (t.amount_minor, t.posting_date, t.accounting_status)  # noqa: E731
                            for t in s.scalars(select(m.FinancialTransaction))}
        whats_before = {r.id: r.accounting_classification_id for r in s.scalars(select(m.BankTransactionReason))}
        money_before = snapshot()

    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "newwhy", "password": "CreateNewWhy123!", "csrf_token": csrf})
    review = client.get(REVIEW_AUG).data.decode()
    classification = client.get("/bank/classification").data.decode()
    csrf = CSRF_RE.search(review).group(1)

    def create(name, *, group=None, what=None, who_id=None):
        data = {"csrf_token": csrf, "name": name}
        if group is not None:
            data["group_id"] = str(group)
        if what is not None:
            data["what_id"] = str(what)
        if who_id is not None:
            data["occurrence_id"] = str(who_id)
        return client.post("/bank/whys/create", headers={"X-Requested-With": "fetch"}, data=data)

    def count_named(name):
        with SessionFactory() as s:
            return s.scalar(select(func.count(m.BankTransactionReason.id)).where(
                func.lower(m.BankTransactionReason.name) == name.lower()))

    def association(who_id, why_id):
        with SessionFactory() as s:
            row = s.scalars(select(m.BankOccurrenceReasonAssociation).where(
                m.BankOccurrenceReasonAssociation.occurrence_id == who_id,
                m.BankOccurrenceReasonAssociation.transaction_reason_id == why_id)).first()
            return (row.active, row.confirmation_count) if row else None

    why_js = open(os.path.join(JS_DIR, "bank-who-why.js"), encoding="utf-8").read()
    rule_js = open(os.path.join(JS_DIR, "bank-who-rule.js"), encoding="utf-8").read()
    create_js = open(os.path.join(JS_DIR, "bank-why-create.js"), encoding="utf-8").read()

    # ------------------------------------------------------------------
    # SHARED FLOW (1-5)
    # ------------------------------------------------------------------
    calls = []
    real_service = manual_reconciliation.create_why_for_who

    def spy(*args, **kwargs):
        calls.append(kwargs.get("occurrence_id"))
        return real_service(*args, **kwargs)

    manual_reconciliation.create_why_for_who = spy
    dialogs = [h.count('id="why-create-dialog"') for h in (review, classification)]
    check("1. both modals use the SAME dialog, route and service (one dialog per page, both modals call "
          "RFOneWhyCreate.open, neither posts a WHY itself)",
          dialogs == [1, 1] and all('data-create-url="/bank/whys/create"' in h for h in (review, classification))
          and "window.RFOneWhyCreate.open(" in why_js and "window.RFOneWhyCreate.open(" in rule_js
          and "/bank/whys/create" not in why_js + rule_js and "new_why_name" not in why_js
          and review.index('id="who-picker"') < review.index('id="why-create-dialog"')
          and review.index('id="who-rule-modal"') < review.index('id="why-create-dialog"'), str(dialogs))

    blank = create("   ", group=group_a.id, what=test_what_id, who_id=ids["atm"])
    check("2. WHY Name required (blank refused, nothing created)",
          blank.status_code == 400 and "name" in blank.get_json()["error"].lower() and count_named("") == 0)
    no_group = create("Withdrawal", what=test_what_id, who_id=ids["atm"])
    check("3. WHY Group required", no_group.status_code == 400 and "group" in no_group.get_json()["error"].lower()
          and count_named("Withdrawal") == 0)
    bs_what = create("Withdrawal", group=group_a.id, what=balance_sheet.id, who_id=ids["atm"]) if balance_sheet else None
    no_what = create("Cash Pickup Test", group=group_a.id, who_id=ids["atm"])
    with SessionFactory() as s:
        pickup = s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.name == "Cash Pickup Test")).first()
        pickup_state = (pickup.reason_group_id, pickup.accounting_classification_id, pickup.status) if pickup else None
    reconciled_pickup = client.post(f"/bank/transactions/{pickup_tx}/who-why", headers={"X-Requested-With": "fetch"},
                                    data={"csrf_token": csrf, "occurrence_id": str(ids["atm"]),
                                          "transaction_reason_id": str(pickup.id) if pickup else "",
                                          "return_to": REVIEW_AUG})
    with SessionFactory() as s:
        t = s.get(m.FinancialTransaction, pickup_tx)
        d = s.get(m.BankTransactionExplanation, t.explanation_id) if t.explanation_id else None
        pickup_decision = (d.occurrence_id, d.transaction_reason_id, d.accounting_classification_id, d.decision_source) if d else None
    check("4. WHAT optional — Name + Group create a WHY with no invented WHAT, usable at once to reconcile "
          "(WHO + WHY, WHAT stays empty); a Balance Sheet destination is still refused as a WHAT",
          no_what.status_code == 200 and pickup_state == (group_a.id, None, "ACTIVE")
          and reconciled_pickup.status_code == 200 and reconciled_pickup.get_json()["ok"]
          and pickup_decision == (ids["atm"], pickup.id, None, "HUMAN")
          and (bs_what is None or bs_what.status_code == 400) and count_named("Withdrawal") == 0,
          f"{no_what.status_code} {no_what.data[:200]} {pickup_state} {pickup_decision} {reconciled_pickup.data[:200]}")

    # ------------------------------------------------------------------
    # SELECT WHO / WHY — the Withdrawal case (6-10)
    # ------------------------------------------------------------------
    popup = review[review.index('id="who-picker"'):review.index('id="why-create-dialog"')]
    check("6. Create New WHY is available in Select WHO / WHY and opens the shared dialog with the chosen WHO "
          "and the selected group",
          'id="why-picker-create"' in popup and "+ Create New WHY" in popup
          and "whoId: whoHidden.value" in why_js and "groupId: currentGroup" in why_js)
    saved = create("Withdrawal", group=group_a.id, what=test_what_id, who_id=ids["atm"])
    body = saved.get_json()
    with SessionFactory() as s:
        withdrawal = s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.name == "Withdrawal")).one()
        w = (withdrawal.id, withdrawal.reason_group_id, withdrawal.accounting_classification_id, withdrawal.status)
    # BANK_FINAL_RELEASE_BLOCKERS_002: creating the WHY offers it to the WHO
    # but is not a confirmation (0); the Confirm below is the one confirmation.
    check("7. saved: the WHY exists in the chosen group with the chosen WHAT, and is added to the WHO "
          "(not yet confirmed: count 0)",
          saved.status_code == 200 and body["ok"] and not body["reused"] and body["associated"]
          and w == (body["why"]["id"], group_a.id, test_what_id, "ACTIVE")
          and association(ids["atm"], w[0]) == (True, 0) and calls and calls[-1] == ids["atm"], str(body))
    on_saved = why_js[why_js.index("function openCreate"):why_js.index("// ---------------------------------------------------------- open/close")]
    check("8. back in the popup the new WHY is SELECTED, in its group, and counted as used with the WHO",
          "selectWhy(why.id)" in on_saved and "associatedCache[whoHidden.value][why.id] = true" in on_saved
          and body["why"]["group_id"] == group_a.id and body["why"]["group_name"] == group_a.name)
    check("9. it returns to the SAME popup: the dialog is stacked on it (no navigation, no reload), Cancel "
          "only closes the dialog",
          "redirect" not in body and "location" not in create_js and "modal.close();" in create_js
          and "data-modal-close>Cancel" in review[review.index('id="why-create-dialog"'):]
          and "z-index: 60" in open(os.path.join(APP_DIR, "static", "css", "rf-one.css"), encoding="utf-8").read())
    confirmed = client.post(f"/bank/transactions/{atm_tx}/who-why", headers={"X-Requested-With": "fetch"},
                            data={"csrf_token": csrf, "occurrence_id": str(ids["atm"]),
                                  "transaction_reason_id": str(w[0]), "return_to": REVIEW_AUG})
    with SessionFactory() as s:
        t = s.get(m.FinancialTransaction, atm_tx)
        decision = s.get(m.BankTransactionExplanation, t.explanation_id)
        d = (decision.occurrence_id, decision.transaction_reason_id, decision.decision_source)
    check("10. Confirm works afterwards: the transaction gets WHO + the new WHY (HUMAN)",
          confirmed.status_code == 200 and confirmed.get_json()["ok"] and d == (ids["atm"], w[0], "HUMAN"), str(d))
    check("10b. create WHY + use it in the same reconciliation = ONE confirmation (confirmation_count 1, not 2)",
          association(ids["atm"], w[0]) == (True, 1), str(association(ids["atm"], w[0])))

    # ------------------------------------------------------------------
    # DUPLICATE (5)
    # ------------------------------------------------------------------
    again = create("  wIthdrawal   ", group=group_b.id, what=other_what_id, who_id=ids["zeta"])
    again_body = again.get_json()
    check("5. a normalized duplicate name reuses the existing WHY (no second record, group/WHAT untouched, "
          "added to the new WHO, 'Existing WHY found — reused.')",
          again.status_code == 200 and again_body["reused"] and again_body["why"]["id"] == w[0]
          and again_body["message"] == "Existing WHY found — reused." and count_named("Withdrawal") == 1
          and again_body["associated"] and association(ids["zeta"], w[0]) == (True, 0)
          and again_body["why"]["group_id"] == group_a.id, str(again_body))
    count_before = association(ids["atm"], w[0])
    same_who = create("WITHDRAWAL", who_id=ids["atm"])
    check("5b. reusing for a WHO that already has the WHY adds nothing (no double count)",
          same_who.status_code == 200 and same_who.get_json()["reused"] and not same_who.get_json()["associated"]
          and association(ids["atm"], w[0]) == count_before, f"{count_before} -> {association(ids['atm'], w[0])}")

    # ------------------------------------------------------------------
    # RULE MODAL (11-16)
    # ------------------------------------------------------------------
    rule_modal = classification[classification.index('id="who-rule-modal"'):classification.index('id="why-create-dialog"')]
    check("11. Create New WHY is available in the Rule modal (Possible WHY), groups carry their id",
          'id="who-rule-why-create"' in rule_modal and "+ Create New WHY" in rule_modal
          and re.search(r'class="who-rule-why-group" open data-group="[^"]+" data-group-id="\d+"', rule_modal) is not None
          and "whoId: whoId.value" in rule_js)
    rule_why = create("Exchange Commission Test", group=group_b.id, what=test_what_id, who_id=ids["zeta"])
    rb = rule_why.get_json()
    check("12. from the Rule modal the WHY is created through the same route and added to the WHO",
          rule_why.status_code == 200 and rb["ok"] and not rb["reused"] and rb["associated"]
          and association(ids["zeta"], rb["why"]["id"]) == (True, 0) and calls[-1] == ids["zeta"], str(rb))
    page = client.get("/bank/classification").data.decode()
    modal = page[page.index('id="who-rule-modal"'):page.index('id="why-create-dialog"')]
    group_block = re.search(rf'data-group-id="{group_b.id}">(.*?)</details>', modal, re.S)
    names = re.findall(r'<span>([^<]+)</span></label>', group_block.group(1)) if group_block else []
    check("13. the new WHY appears in its group, in alphabetical place (and the dialog inserts it there "
          "without a reload)",
          "Exchange Commission Test" in names and names == sorted(names, key=str.casefold)
          and "function boxFor(why)" in rule_js and "byText(l.textContent.trim(), why.name) > 0" in rule_js, str(names))
    summary = client.get(f"/bank/who-rules/who/{ids['zeta']}").get_json()
    check("14. it is a Possible WHY of the WHO (ticked when the modal opens; ticked at once on Save)",
          rb["why"]["id"] in summary["possible_why_ids"] and "box.checked = true" in rule_js)
    applied = client.post("/bank/who-rules/apply", headers={"X-Requested-With": "fetch"}, data={
        "csrf_token": csrf, "occurrence_id": ids["zeta"],
        "instruction": "Dove nella descrizione trovi ZETA EXCHANGE il WHO è Zeta Exchange",
        "transaction_reason_id": [rb["why"]["id"]], "return_to": "/bank/classification#who-classification"})
    with SessionFactory() as s:
        given = [s.get(m.BankTransactionExplanation, s.get(m.FinancialTransaction, i).explanation_id) for i in zeta_txs]
    check("15. the Rule still gives the WHO only: matching transactions get Zeta Exchange and NO WHY",
          applied.status_code == 200 and applied.get_json()["ok"]
          and all(d is not None and d.occurrence_id == ids["zeta"] and d.transaction_reason_id is None for d in given),
          applied.data.decode()[:200])
    rule_create = rule_js[rule_js.index("function openCreate"):rule_js.index("// A Manual Only WHO takes no WHO Rule")]
    check("16. the Rule text, the WHO and the other ticks are kept: the dialog opens on top and touches only "
          "the WHY list (no form reset, no instruction change, no reload)",
          "instruction" not in rule_create and "form.reset" not in rule_create and "location" not in rule_create
          and "form.reset" not in create_js.split("var modal = ")[0])

    # ------------------------------------------------------------------
    # ATOMICITY (17-19)
    # ------------------------------------------------------------------
    real_associate = manual_reconciliation.why_catalog.associate

    def broken_associate(*args, **kwargs):
        real_associate(*args, **kwargs)
        raise ValueError("Simulated failure while adding the WHY to the WHO.")

    with SessionFactory() as s:
        reasons_before = s.scalar(select(func.count(m.BankTransactionReason.id)))
        associations_before = s.scalar(select(func.count(m.BankOccurrenceReasonAssociation.id)))
    manual_reconciliation.why_catalog.associate = broken_associate
    try:
        failed_save = create("Atomic Test WHY", group=group_a.id, what=test_what_id, who_id=ids["atm"])
    finally:
        manual_reconciliation.why_catalog.associate = real_associate
    with SessionFactory() as s:
        reasons_after = s.scalar(select(func.count(m.BankTransactionReason.id)))
        associations_after = s.scalar(select(func.count(m.BankOccurrenceReasonAssociation.id)))
        orphans = s.scalar(select(func.count(m.BankTransactionReason.id)).where(
            m.BankTransactionReason.status == "ACTIVE",
            (m.BankTransactionReason.reason_group_id.is_(None)) | (m.BankTransactionReason.accounting_classification_id.is_(None)),
            m.BankTransactionReason.name.in_(["Withdrawal", "Exchange Commission Test", "Atomic Test WHY"])))
    check("17. a failure rolls the WHY back (it was created, then the association failed: nothing remains)",
          failed_save.status_code == 400 and "Simulated failure" in failed_save.get_json()["error"]
          and count_named("Atomic Test WHY") == 0 and reasons_after == reasons_before)
    check("18. a failure rolls the association back", associations_after == associations_before)
    bad_who = create("Orphan Test WHY", group=group_a.id, what=test_what_id, who_id=999999)
    check("19. no orphan WHY: an invalid WHO creates nothing; every created WHY has its group and WHAT",
          bad_who.status_code == 400 and count_named("Orphan Test WHY") == 0 and orphans == 0)

    # ------------------------------------------------------------------
    # REGRESSION (20-24)
    # ------------------------------------------------------------------
    picked = client.post(f"/bank/transactions/{existing_tx}/who-why", headers={"X-Requested-With": "fetch"},
                         data={"csrf_token": csrf, "occurrence_id": str(ids["atm"]),
                               "transaction_reason_id": str(existing_why_id), "return_to": REVIEW_AUG})
    with SessionFactory() as s:
        t = s.get(m.FinancialTransaction, existing_tx)
        decision = s.get(m.BankTransactionExplanation, t.explanation_id)
    check("20. choosing an existing WHY is unchanged (decision recorded, WHY added to the WHO on Confirm)",
          picked.status_code == 200 and decision.transaction_reason_id == existing_why_id
          and association(ids["atm"], existing_why_id) == (True, 1))
    catalog = client.get("/bank/manual-reconciliation/why-catalog").get_json()
    named = [g["name"] for g in catalog["groups"] if g["id"] is not None]
    check("21. grouped WHY UI unchanged: three columns, groups alphabetical, the new WHY listed under its group",
          popup.count('class="ww-col ') == 3 and named == sorted(named, key=str.casefold)
          and any(x["id"] == w[0] and x["group_id"] == group_a.id for x in catalog["whys"]))
    via_confirm = client.post(f"/bank/transactions/{existing_tx}/who-why", headers={"X-Requested-With": "fetch"},
                              data={"csrf_token": csrf, "occurrence_id": str(ids["atm"]),
                                    "new_why_name": " withdrawal ", "return_to": REVIEW_AUG})
    check("22. manual reconciliation unchanged: Confirm with a WHY name still works and goes through the same "
          "creation (the existing WHY is reused, no duplicate)",
          via_confirm.status_code == 200 and count_named("Withdrawal") == 1
          and "_create_or_reuse_why(session, new_why)" in open(manual_reconciliation.__file__, encoding="utf-8").read())
    with SessionFactory() as s:
        rules = s.scalars(select(m.BankRecognitionRule).where(m.BankRecognitionRule.occurrence_id == ids["zeta"])).all()
    check("23. Rule behaviour unchanged (Apply saved one WHO rule, WHY only associated)",
          len(rules) == 1 and rules[0].transaction_reason_id is None and rules[0].status == "ACTIVE")
    with SessionFactory() as s:
        whats_after = {r.id: r.accounting_classification_id for r in s.scalars(select(m.BankTransactionReason))}
        money_after = {t.id: (t.amount_minor, t.posting_date, t.accounting_status)
                       for t in s.scalars(select(m.FinancialTransaction))}
    check("24. accounting unchanged: no existing WHY changed its WHAT, every amount / date / accounting status "
          "is as it was",
          all(whats_after[k] == v for k, v in whats_before.items()) and money_after == money_before)

    manual_reconciliation.create_why_for_who = real_service
    print(f"\n{len(passed)} passed, {len(failed)} failed.")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
