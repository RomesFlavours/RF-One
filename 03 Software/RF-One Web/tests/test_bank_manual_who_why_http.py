"""Manual WHO + WHY reconciliation and Rule recognition (BANK_MANUAL_WHO_WHY_001).

Proves, on a throwaway database, that:

* a saved WHO Rule ("description contains TABLE TOP LINEN -> WHO TABLE TOP
  LINEN") gives the WHO to every matching transaction — every description
  form, every month, and future imports — so they leave To Reconcile and
  appear in Reconciled with no WHY invented; and the Rule modal can always
  be sent (no silent native `required` blocker);
* "Select WHO / WHY" reconciles ONE transaction by hand: the full
  alphabetical list of ACTIVE WHO (aliases searchable), the WHY of the chosen
  WHO only, Confirm only with WHO + WHY, a HUMAN decision, no rule created —
  and the transaction moves to Reconciled;
* "Create New WHY" creates a real WHY through the Bank Configuration service,
  associates it with the WHO and uses it — atomically: a refusal leaves no
  WHY behind;
* Reconciled shows WHO, WHY and WHAT on the row; the WHY is edited there
  (WHAT derived again from the new WHY), the row stays Reconciled and no
  Rule changes;
* the creatable-WHO Rule, Classification, Standards, Export and the WHO/WHY
  invariant are unchanged.

Never touches a real bank file, AWS, or any production database.
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_manual_who_why_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-manual-who-why-secret"

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
from rfone_data_store.bank_reconciliation import configuration as config_service  # noqa: E402
from rfone_data_store.bank_reconciliation import export as export_service  # noqa: E402
from rfone_data_store.bank_reconciliation import manual_reconciliation  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.bank_reconciliation import reconciliation_status  # noqa: E402
from rfone_data_store.bank_reconciliation import service as bank_service  # noqa: E402
from rfone_data_store.bank_reconciliation import why_catalog  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
AUG, JUL, SEP = date(2026, 8, 12), date(2026, 7, 9), date(2026, 9, 3)
TTL_RULE = "description contains TABLE TOP LINEN → WHO TABLE TOP LINEN"
REVIEW_AUG = "/bank/review?year=2026&month=8"
RECONCILED_AUG = "/bank/review?view=reconciled&year=2026&month=8"


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="who_why", display_name="Who Why",
                                       password="ManualWhoWhy123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="who_why").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        legal = m.LegalEntity(legal_name="Who Why LLC", status="ACTIVE")
        s.add(legal)
        s.flush()
        s.add(m.ReportingEntity(code="RE_WHO_WHY", name="Who Why", entity_type="LEGAL",
                                legal_entity_id=legal.id, status="ACTIVE"))
        checking = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                       display_name="Who Why Checking", institution="CHASE", last_four="0007",
                                       currency="USD")
        s.add(checking)
        s.flush()
        batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="seed.csv",
                                  raw_file_bytes=b"x", sha256="7" * 64, status="NORMALIZED",
                                  payment_instrument_id=checking.id)
        s.add(batch)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        active_whys = s.scalars(select(m.BankTransactionReason).where(
            m.BankTransactionReason.status == "ACTIVE",
            m.BankTransactionReason.accounting_classification_id.is_not(None)).order_by(m.BankTransactionReason.id)).all()
        why_a, why_b = active_whys[0], next(r for r in active_whys
                                            if r.accounting_classification_id != active_whys[0].accounting_classification_id)

        def who(name, status="ACTIVE"):
            o = m.BankOccurrence(canonical_name=name, occurrence_type_id=counterparty.id, status=status,
                                 optional_notes="Canonical WHO from the WHO/WHY import.")
            s.add(o)
            s.flush()
            return o

        ttl = who("TABLE TOP LINEN")
        sysco = who("Sysco")
        zeta = who("zeta Plumbing")
        acme = who("Acme Supplies")
        inactive = who("Old Vendor", status="INACTIVE")
        s.add(m.BankOccurrenceAlias(occurrence_id=acme.id, alias_text="ACME SUP 0042", alias_key="ACME SUP 0042",
                                    source_family="CARD_MERCHANT", source="HUMAN"))
        for reason in (why_a, why_b):
            why_catalog.associate(s, occurrence_id=sysco.id, transaction_reason_id=reason.id, source="HUMAN")
        seq = [0]

        def tx(description, day=AUG, amount=-1000):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=checking.id, bank_source="CHASE_BANK_ACCOUNT", import_batch_id=batch.id,
                posting_date=day, transaction_date=day, description_original=description,
                description_normalized=description, amount_minor=amount - seq[0], status="COMPLETED",
                duplicate_status="NONE", review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"who-why-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            return t

        ttl_aug = {
            "plain": tx("TABLE TOP LINEN"),
            "ach": tx("TABLE TOP LINEN ACH"),
            "orig": tx("ORIG CO NAME:TABLE TOP LINEN        ORIG ID:1900922218 DESC DATE:260804 CO ENTRY DESCR:MON"),
            "monday": tx("MONDAY ACHSEC:CCD    TRACE#:021000020001 TABLE TOP LINEN IND ID:1"),
            "mixed": tx("Table Top Linen weekly service"),
        }
        ttl_jul = tx("ORIG CO NAME:TABLE TOP LINEN        ORIG ID:1900922218 DESC DATE:260707", day=JUL)
        ttl_sep = tx("ORIG CO NAME:TABLE TOP LINEN        ORIG ID:1900922218 DESC DATE:260901", day=SEP)
        manual = tx("SOME UNKNOWN PAYEE 4401")
        new_why_row = tx("SOME UNKNOWN PAYEE 4402")
        failing_row = tx("SOME UNKNOWN PAYEE 4403")
        edit_row = tx("SYSCO ORLANDO 2211")
        s.commit()
        ids = {k: t.id for k, t in ttl_aug.items()}
        ids.update(jul=ttl_jul.id, sep=ttl_sep.id, manual=manual.id, new_why=new_why_row.id, failing=failing_row.id,
                   edit=edit_row.id, ttl=ttl.id, sysco=sysco.id, zeta=zeta.id, acme=acme.id, inactive=inactive.id,
                   why_a=why_a.id, why_b=why_b.id, why_a_what=why_a.accounting_classification_id,
                   why_b_what=why_b.accounting_classification_id, checking=checking.id)
        standards_before = s.scalar(select(func.count(m.BankReconciliationStandard.id)))

    client = web_app.app.test_client()
    client.get("/login")
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "who_why", "password": "ManualWhoWhy123!", "csrf_token": csrf})
    review = client.get(REVIEW_AUG).data.decode()
    csrf = CSRF_RE.search(review).group(1)

    def in_to(html, key):
        return f'class="who-picker-open"' in html and f'data-transaction-id="{ids[key]}"' in html

    def in_rec(html, key):
        return f'id="t-{ids[key]}"' in html

    def decision(key):
        with SessionFactory() as s:
            e = recognition.get_current_explanation(s, financial_transaction_id=ids[key])
            return (e.occurrence_id, e.transaction_reason_id, e.decision_source,
                    e.accounting_classification_id) if e else (None, None, None, None)

    def rules():
        with SessionFactory() as s:
            return sorted(s.execute(select(m.BankRecognitionRule.id, m.BankRecognitionRule.normalized_pattern,
                                           m.BankRecognitionRule.occurrence_id, m.BankRecognitionRule.status,
                                           m.BankRecognitionRule.transaction_reason_id)).all())

    # ------------------------------------------------------------------
    # RULE RECOGNITION — TABLE TOP LINEN (1-5)
    # ------------------------------------------------------------------
    modal_html = review.split('id="who-rule-modal"', 1)[1].split("</form>", 1)[0]
    rule_js = client.get("/static/js/bank-who-rule.js").data.decode()
    check("0. the Rule modal can always be sent: no native `required` blocker, the modal's own message instead",
          not re.search(r'<textarea[^>]*id="who-rule-instruction"[^>]*required', modal_html)
          and 'showError("Write the rule.")' in rule_js and "Dove nella descrizione trovi \" + data.name" in rule_js)
    check("0b. before the Rule every TABLE TOP LINEN form is To Reconcile",
          all(in_to(review, k) for k in ttl_aug))
    applied = client.post("/bank/who-rules/apply", headers={"X-Requested-With": "fetch"}, data={
        "csrf_token": csrf, "occurrence_id": str(ids["ttl"]), "instruction": TTL_RULE,
        "transaction_id": str(ids["orig"]), "return_to": REVIEW_AUG})
    check("1a. the Rule is saved from Review", applied.status_code == 200 and applied.get_json()["ok"],
          detail=str(applied.get_json()))
    check("1. the Rule gives the WHO to every existing matching form (plain, ACH, ORIG CO NAME, MONDAY ACHSEC:CCD, mixed case)",
          all(decision(k)[0] == ids["ttl"] for k in ttl_aug), detail=str({k: decision(k) for k in ttl_aug}))
    check("2. the Rule works across months (July and September)",
          decision("jul")[0] == ids["ttl"] and decision("sep")[0] == ids["ttl"])
    with SessionFactory() as s:
        upload = bank_service.import_csv(
            s, file_bytes=("Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
                           'DEBIT,10/06/2026,"ORIG CO NAME:TABLE TOP LINEN        ORIG ID:1900922218 DESC DATE:261006",'
                           "-636.47,ACH_DEBIT,1000.00,,\n").encode(),
            original_file_name="chase0007_future_ttl.csv", uploaded_by_account_id=None,
            payment_instrument_id=ids["checking"])
        s.commit()
        future = s.scalars(select(m.FinancialTransaction).where(
            m.FinancialTransaction.import_batch_id == upload.batch.id)).one()
        future_decision = recognition.get_current_explanation(s, financial_transaction_id=future.id)
        future_id = future.id
    oct_rec = client.get("/bank/review?view=reconciled&year=2026&month=10").data.decode()
    check("3. a future import is recognised by the Rule and goes straight to Reconciled",
          future_decision is not None and future_decision.occurrence_id == ids["ttl"] and f'id="t-{future_id}"' in oct_rec)
    after = client.get(REVIEW_AUG).data.decode()
    rec = client.get(RECONCILED_AUG).data.decode()
    check("4. the Rule moves the WHO-resolved rows out of To Reconcile and into Reconciled",
          not any(f'data-transaction-id="{ids[k]}"' in after for k in ttl_aug) and all(in_rec(rec, k) for k in ttl_aug))
    with SessionFactory() as s:
        ttl_whys = why_catalog.reasons_for_occurrence(s, ids["ttl"])
    check("5. the Rule invents no WHY: every recognised row has no WHY, the WHO gained no possible WHY",
          all(decision(k)[1] is None for k in list(ttl_aug) + ["jul", "sep"]) and ttl_whys == []
          and re.search(r'<tr id="t-%d".*?WHY needed' % ids["plain"], rec, re.S) is not None)
    check("5b. a Rule-resolved row is Needs review on Reconciled and never returns to To Reconcile for its WHY",
          f'id="t-{ids["plain"]}"' in rec and 'data-status="Needs review"' in re.search(
              r'<tr id="t-%d"[^>]*>' % ids["plain"], rec).group(0))
    rules_after_rule = rules()

    # ------------------------------------------------------------------
    # MANUAL POPUP (6-14)
    # ------------------------------------------------------------------
    popup = after.split('id="who-picker"', 1)[1]
    check("6a. the popup is 'Select WHO / WHY' with WHO list, WHY step, Create New WHY, Confirm and Cancel only",
          ">Select WHO / WHY<" in popup and 'id="who-picker-list"' in popup and 'id="why-picker"' in popup
          and "+ Create New WHY" in popup and 'id="who-picker-confirm" disabled' in popup and 'id="who-picker-cancel"' in popup)
    check("6b. removed from the popup: WHAT choice, For Whom, Learn this description, Rule, Standard, explanations",
          all(token not in popup.split("</form>", 1)[0] for token in (
              "learn_description", "Learn this description", "who-picker-rule", "For whom", "Standard",
              "why-catalog-modal", "DERIVED", "Who &rarr; Why &rarr; What")))
    started = time.perf_counter()
    whos_response = client.get("/bank/manual-reconciliation/whos")
    who_list_secs = time.perf_counter() - started
    whos = whos_response.get_json()
    names = [w["name"] for w in whos]
    check("6. the WHO list holds every ACTIVE WHO, alphabetical (case-insensitive), no inactive WHO",
          names == sorted(names, key=str.casefold) and "Old Vendor" not in names
          and {"TABLE TOP LINEN", "Sysco", "zeta Plumbing", "Acme Supplies"} <= set(names))
    acme_entry = next(w for w in whos if w["id"] == ids["acme"])
    js = client.get("/static/js/bank-who-why.js").data.decode()
    check("7. WHO search: name and aliases are searchable, filtered as the operator types",
          "ACME SUP 0042" in acme_entry.get("aliases", "") and 'whoSearch.addEventListener("input", filterWhos)' in js)
    check("8. choosing a WHO marks it selected (tick and bar) and resolves to the canonical WHO id",
          "button.classList.toggle(\"is-selected\", on)" in js and "whoHidden.value = String(who.id)" in js)
    started = time.perf_counter()
    sysco_whys = client.get(f"/bank/manual-reconciliation/whos/{ids['sysco']}/whys").get_json()
    why_list_secs = time.perf_counter() - started
    zeta_whys = client.get(f"/bank/manual-reconciliation/whos/{ids['zeta']}/whys").get_json()
    check("9. the WHY list loads for the chosen WHO only — its WHY, with their WHAT; none for a WHO without WHY",
          sorted(w["id"] for w in sysco_whys) == sorted([ids["why_a"], ids["why_b"]])
          and all(w["what"] for w in sysco_whys) and zeta_whys == [])
    check("9b. a WHY is never selected for the operator, even when the WHO has one",
          "selectWhy(keepWhyId)" in js and "list.length === 1" not in js)
    refused = client.post(f"/bank/transactions/{ids['manual']}/who-why", headers={"X-Requested-With": "fetch"},
                          data={"csrf_token": csrf, "occurrence_id": str(ids["sysco"]), "return_to": REVIEW_AUG})
    check("10. Confirm without a WHY is disabled in the popup and refused by the server",
          "confirmButton.disabled = !(whoHidden.value && whyHidden.value)" in js and refused.status_code == 400
          and decision("manual")[0] is None)
    # BANK_WHY_NAVIGATION_GROUPS_001 — any active WHY may be chosen for any
    # WHO: choosing one the WHO does not have yet adds the association.
    off_list = client.post(f"/bank/transactions/{ids['manual']}/who-why", headers={"X-Requested-With": "fetch"},
                           data={"csrf_token": csrf, "occurrence_id": str(ids["acme"]),
                                 "transaction_reason_id": str(ids["why_a"]), "return_to": REVIEW_AUG})
    with SessionFactory() as s:
        acme_whys = {r.id for r in why_catalog.reasons_for_occurrence(s, ids["acme"])}
    check("10b. a WHY that is not yet one of the WHO's WHY is accepted, and the association is added",
          off_list.status_code == 200 and decision("manual")[:2] == (ids["acme"], ids["why_a"])
          and ids["why_a"] in acme_whys, detail=str(off_list.get_json()))
    started = time.perf_counter()
    confirmed = client.post(f"/bank/transactions/{ids['manual']}/who-why", headers={"X-Requested-With": "fetch"},
                            data={"csrf_token": csrf, "occurrence_id": str(ids["sysco"]),
                                  "transaction_reason_id": str(ids["why_a"]), "return_to": REVIEW_AUG})
    confirm_secs = time.perf_counter() - started
    check("11. Confirm with WHO + WHY succeeds", confirmed.status_code == 200 and confirmed.get_json()["ok"],
          detail=str(confirmed.get_json()))
    who_id, why_id, source, what_id = decision("manual")
    check("12. manual Confirm saves the WHO, as a HUMAN decision", who_id == ids["sysco"] and source == "HUMAN")
    check("13. manual Confirm saves the WHY, and WHAT is derived from it",
          why_id == ids["why_a"] and what_id == ids["why_a_what"])
    after_manual = client.get(REVIEW_AUG).data.decode()
    started = time.perf_counter()
    rec_manual = client.get(RECONCILED_AUG).data.decode()
    reconciled_secs = time.perf_counter() - started
    check("14. the transaction leaves To Reconcile and appears in Reconciled",
          f'data-transaction-id="{ids["manual"]}"' not in after_manual and in_rec(rec_manual, "manual"))
    check("14b. manual Confirm creates no recognition Rule", rules() == rules_after_rule)

    # ------------------------------------------------------------------
    # CREATE NEW WHY (15-19)
    # ------------------------------------------------------------------
    calls = []
    real_create = config_service.create_why

    def counting_create_why(*args, **kwargs):
        calls.append(kwargs.get("name"))
        return real_create(*args, **kwargs)

    manual_reconciliation.config_service.create_why = counting_create_why
    create_data = client.get("/bank/manual-reconciliation/whats").get_json()
    whats = create_data["whats"]
    nav_groups = client.get("/bank/manual-reconciliation/why-catalog").get_json()["groups"]
    group_id = next(g["id"] for g in nav_groups if g["name"] == "Maintenance, Repairs & Cleaning")
    no_group = client.post(f"/bank/transactions/{ids['new_why']}/who-why", headers={"X-Requested-With": "fetch"},
                           data={"csrf_token": csrf, "occurrence_id": str(ids["zeta"]),
                                 "new_why_name": "Emergency Plumbing Repairs", "new_why_what_id": str(whats[0]["id"]),
                                 "return_to": REVIEW_AUG})
    created = client.post(f"/bank/transactions/{ids['new_why']}/who-why", headers={"X-Requested-With": "fetch"},
                          data={"csrf_token": csrf, "occurrence_id": str(ids["zeta"]),
                                "new_why_name": "Emergency Plumbing Repairs", "new_why_what_id": str(whats[0]["id"]),
                                "new_why_group_id": str(group_id), "return_to": REVIEW_AUG})
    with SessionFactory() as s:
        new_reason = s.scalars(select(m.BankTransactionReason).where(
            m.BankTransactionReason.name == "Emergency Plumbing Repairs")).one_or_none()
        associated = new_reason is not None and s.scalar(select(func.count(m.BankOccurrenceReasonAssociation.id)).where(
            m.BankOccurrenceReasonAssociation.occurrence_id == ids["zeta"],
            m.BankOccurrenceReasonAssociation.transaction_reason_id == new_reason.id,
            m.BankOccurrenceReasonAssociation.active.is_(True)))
        new_reason_id = new_reason.id if new_reason else None
        new_reason_what = new_reason.accounting_classification_id if new_reason else None
        new_reason_group = new_reason.reason_group_id if new_reason else None
    check("15. Create New WHY works from the popup, in the WHY group chosen (a group is required)",
          no_group.status_code == 400 and "WHY group" in no_group.get_json()["error"]
          and created.status_code == 200 and created.get_json()["ok"]
          and new_reason_id is not None and new_reason_group == group_id, detail=str(created.get_json()))
    configuration_page = client.get("/bank/configuration").data.decode()
    check("16. the Bank Configuration service created it (same service, real WHY with its WHAT, listed in Configuration)",
          calls == ["Emergency Plumbing Repairs"] and new_reason_what == whats[0]["id"]
          and "Emergency Plumbing Repairs" in configuration_page)
    check("17. the WHO -> WHY association exists", associated == 1)
    check("18. the new WHY is the WHY of this transaction",
          decision("new_why")[:3] == (ids["zeta"], new_reason_id, "HUMAN"))
    with SessionFactory() as s:
        reasons_before = s.scalar(select(func.count(m.BankTransactionReason.id)))
    bad_what = client.post(f"/bank/transactions/{ids['failing']}/who-why", headers={"X-Requested-With": "fetch"},
                           data={"csrf_token": csrf, "occurrence_id": str(ids["zeta"]),
                                 "new_why_name": "Orphan Candidate One", "new_why_what_id": "", "return_to": REVIEW_AUG})
    bad_tx = client.post("/bank/transactions/999999/who-why", headers={"X-Requested-With": "fetch"},
                         data={"csrf_token": csrf, "occurrence_id": str(ids["zeta"]),
                               "new_why_name": "Orphan Candidate Two", "new_why_what_id": str(whats[0]["id"]),
                               "new_why_group_id": str(group_id), "return_to": REVIEW_AUG})
    with SessionFactory() as s:
        reasons_after = s.scalar(select(func.count(m.BankTransactionReason.id)))
        orphans = s.scalar(select(func.count(m.BankTransactionReason.id)).where(
            m.BankTransactionReason.name.in_(["Orphan Candidate One", "Orphan Candidate Two"])))
    check("19. no orphan WHY after a failure (missing WHAT; failure after the WHY was created)",
          bad_what.status_code == 400 and bad_tx.status_code == 400 and orphans == 0
          and reasons_after == reasons_before and decision("failing")[0] is None)
    # A name that already IS a WHY is reused, never created a second time.
    with SessionFactory() as s:
        why_a_name = s.get(m.BankTransactionReason, ids["why_a"]).name
    calls.clear()
    reused = client.post(f"/bank/transactions/{ids['failing']}/who-why", headers={"X-Requested-With": "fetch"},
                         data={"csrf_token": csrf, "occurrence_id": str(ids["zeta"]),
                               "new_why_name": "  " + why_a_name.upper() + " ", "new_why_what_id": "",
                               "return_to": REVIEW_AUG})
    with SessionFactory() as s:
        same_name = s.scalar(select(func.count(m.BankTransactionReason.id)).where(
            func.lower(m.BankTransactionReason.name) == why_a_name.lower()))
        zeta_whys = {r.id for r in why_catalog.reasons_for_occurrence(s, ids["zeta"])}
    check("19b. Create New WHY with the name of an existing WHY reuses it: no duplicate WHY, associated, used",
          reused.status_code == 200 and calls == [] and same_name == 1 and ids["why_a"] in zeta_whys
          and decision("failing")[:2] == (ids["zeta"], ids["why_a"])
          and any(w["name"] == why_a_name for w in create_data["whys"])
          and "existingNamed(" in client.get("/static/js/bank-why-create.js").data.decode(),
          detail=str(reused.get_json()))
    manual_reconciliation.config_service.create_why = real_create

    # ------------------------------------------------------------------
    # RECONCILED (20-25)
    # ------------------------------------------------------------------
    with SessionFactory() as s:
        manual_reconciliation.reconcile_who_why(s, transaction_id=ids["edit"], occurrence_id=ids["sysco"],
                                                reason_id=ids["why_a"], account_id=None)
        s.commit()
    rec = client.get(RECONCILED_AUG).data.decode()
    row = re.search(r'<tr id="t-%d".*?</tr>' % ids["edit"], rec, re.S).group(0)
    with SessionFactory() as s:
        why_a_name = s.get(m.BankTransactionReason, ids["why_a"]).name
        why_b_name = s.get(m.BankTransactionReason, ids["why_b"]).name
        what_b = s.get(m.BankAccountingClassification, ids["why_b_what"])
    check("20. Reconciled shows the WHO on the row", re.search(r'class="rp-who-name">Sysco', row) is not None)
    check("21. Reconciled shows the WHY on the row", f'<span class="rp-why-name">{why_a_name}</span>' in row)
    check("21b. Reconciled shows WHAT and For Whom columns, and a Rule-resolved row says WHY needed",
          "<th>WHY</th><th>WHAT</th><th>For whom</th>" in rec and 'class="rp-what"' in row and "WHY needed" in rec)
    check("22. the WHY is editable from the row (same popup, WHO and WHY preselected)",
          re.search(r'data-cell="why".*?class="btn-secondary rp-btn rp-edit who-picker-open"[^>]*data-current-occurrence-id="%d" data-current-reason-id="%d"'
                    % (ids["sysco"], ids["why_a"]), row, re.S) is not None
          and rec.count('id="who-picker"') == 1 and "bank-who-why.js" in rec)
    rules_before_edit = rules()
    edited = client.post(f"/bank/transactions/{ids['edit']}/who-why", headers={"X-Requested-With": "fetch"},
                         data={"csrf_token": csrf, "occurrence_id": str(ids["sysco"]),
                               "transaction_reason_id": str(ids["why_b"]), "return_to": RECONCILED_AUG})
    rec_after = client.get(RECONCILED_AUG).data.decode()
    row_after = re.search(r'<tr id="t-%d".*?</tr>' % ids["edit"], rec_after, re.S)
    _, why_now, _, what_now = decision("edit")
    check("23. changing the WHY saves it and derives WHAT from the new WHY",
          edited.status_code == 200 and edited.get_json()["redirect"].endswith(f"#t-{ids['edit']}")
          and why_now == ids["why_b"] and what_now == ids["why_b_what"]
          and row_after is not None and why_b_name in row_after.group(0) and what_b.name in row_after.group(0))
    check("24. the Rule is unchanged by WHY edits", rules() == rules_before_edit)
    check("25. the row remains Reconciled", row_after is not None
          and f'data-transaction-id="{ids["edit"]}"' not in client.get(REVIEW_AUG).data.decode())
    wrong_who = client.post(f"/bank/transactions/{ids['edit']}/who-why", headers={"X-Requested-With": "fetch"},
                            data={"csrf_token": csrf, "occurrence_id": str(ids["zeta"]),
                                  "transaction_reason_id": str(ids["why_b"]), "return_to": RECONCILED_AUG})
    with SessionFactory() as s:
        zeta_now = {r.id for r in why_catalog.reasons_for_occurrence(s, ids["zeta"])}
    check("25b. changing the WHO keeps any active WHY valid: saved, and the WHY is added to the new WHO's WHY",
          wrong_who.status_code == 200 and decision("edit")[:2] == (ids["zeta"], ids["why_b"])
          and ids["why_b"] in zeta_now, detail=str(wrong_who.get_json()))

    # ------------------------------------------------------------------
    # REGRESSION (26-30)
    # ------------------------------------------------------------------
    created_who = client.post("/bank/who-rules/apply", headers={"X-Requested-With": "fetch"}, data={
        "csrf_token": csrf, "new_who_name": "Brand New Linen Co", "instruction":
        "Dove nella descrizione trovi BRAND NEW LINEN il WHO è Brand New Linen Co", "return_to": REVIEW_AUG})
    with SessionFactory() as s:
        brand = s.scalars(select(m.BankOccurrence).where(m.BankOccurrence.canonical_name == "Brand New Linen Co")).one_or_none()
    check("26. the creatable-WHO Rule still works", created_who.status_code == 200 and created_who.get_json()["ok"]
          and brand is not None)
    classification = client.get("/bank/classification")
    check("27. Classification still works (Rule button and modal)", classification.status_code == 200
          and b'class="who-rule-open"' in classification.data and b'id="who-rule-modal"' in classification.data)
    with SessionFactory() as s:
        standards_after = s.scalar(select(func.count(m.BankReconciliationStandard.id)))
        in_scope = export_service.in_scope_transactions(s, 2026, 8)
        statuses = reconciliation_status.statuses_for(s, in_scope)
        unresolved = {t.id for t in export_service.unresolved_transactions(s, year=2026, month=8)}
        description_rules_with_purpose = s.scalar(select(func.count(m.BankRecognitionRule.id)).where(
            m.BankRecognitionRule.match_field == recognition.DESCRIPTION,
            m.BankRecognitionRule.determines_purpose.is_(True)))
        rules_with_why = s.scalar(select(func.count(m.BankRecognitionRule.id)).where(
            m.BankRecognitionRule.transaction_reason_id.is_not(None)))
    check("28. Standards unchanged", standards_after == standards_before)
    check("29. Export semantics unchanged: a WHO + WHY row without For Whom is Needs review and still blocks the export",
          statuses[ids["manual"]] == reconciliation_status.NEEDS_REVIEW and ids["manual"] in unresolved
          and all(st in reconciliation_status.EXPORTABLE for tid, st in statuses.items() if tid not in unresolved))
    check("30. WHO/WHY invariant: no rule determines a purpose or names a WHY",
          not description_rules_with_purpose and not rules_with_why)

    print(f"  WHO list: {who_list_secs * 1000:.0f} ms ({len(whos)} WHO, {len(whos_response.data) / 1024:.1f} KB); "
          f"WHY list: {why_list_secs * 1000:.0f} ms; Confirm: {confirm_secs * 1000:.0f} ms; "
          f"Reconciled page: {reconciled_secs * 1000:.0f} ms")
    print()
    print(f"{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            from db import _engine
            _engine.dispose()
            os.remove(_TEST_DB_PATH)
        except Exception:  # noqa: BLE001 — best-effort cleanup of the throwaway file
            pass
