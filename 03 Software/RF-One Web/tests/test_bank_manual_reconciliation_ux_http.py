#!/usr/bin/env python
"""HTTP-level test for the manual Bank reconciliation UX
(BANK_MANUAL_RECONCILIATION_UX_001).

The gap this closes: the server side of WHO -> WHY -> "+ New" was already
correct, but `bank_review.html` never wired it. The Why step existed as
markup that was permanently hidden, "+ New" did nothing, the catalog search
filtered nothing, and no `transaction_reason_id` was ever submitted.

The WHO + WHY decision is posted to the one manual path,
`/bank/transactions/<id>/who-why` (Select WHO / WHY,
BANK_MANUAL_WHO_WHY_001); the former `/bank/transactions/<id>/why` route is
retired (BANK_FINAL_CLEANUP_001). CSRF is enforced on it like on every other
writing Bank route.

Uses a disposable SQLite database that is deleted at the end. Never touches
a real bank file, AWS, or any production database, and never seeds fake
operational transactions beyond the two rows the flow itself needs.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date
from html import unescape

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_manual_recon_ux_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "manual-recon-ux-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import why_catalog  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def script_of(html: str) -> str:
    """Only the page's own inline controller, so a check for wiring cannot
    accidentally be satisfied by prose elsewhere on the page."""
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    return "\n".join(blocks)


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
        # ---------------------------------------------------------------
        # A clean Bank: canonical vocabulary only, no operational data.
        # ---------------------------------------------------------------
        with SessionFactory() as db:
            account_service.create_account(
                db, username="ux_operator", display_name="UX Operator",
                password="OperatorPass123!", status="ACTIVE", is_admin=False,
            )
            db.commit()
            operator = db.query(m.RFOneAccount).filter_by(username="ux_operator").one()
            account_service.set_domain_access(
                db, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None,
            )
            db.commit()

        client = web_app.app.test_client()
        resp = client.get("/login")
        client.post("/login", data={
            "username": "ux_operator", "password": "OperatorPass123!",
            "csrf_token": extract_csrf(resp.data),
        })

        # ---- 17. the page itself -------------------------------------
        review_resp = client.get("/bank/review")
        check("17. /bank/review returns 200", review_resp.status_code == 200,
              f"status={review_resp.status_code}")
        html = review_resp.data.decode("utf-8")
        js = script_of(html)

        # BANK_MANUAL_WHO_WHY_001 (Product Owner correction) replaced the
        # earlier popup this file pinned — its grouped catalog, "+ New" that
        # associated an existing catalog WHY, the derived-result line and the
        # learning checkbox. The popup is now "Select WHO / WHY": the WHO list,
        # then the chosen WHO's WHY, "+ Create New WHY" (a real WHY through
        # Configuration), Confirm and Cancel. Its controller is
        # static/js/bank-who-why.js; the behaviour is pinned in full by
        # test_bank_manual_who_why_http.py. The checks below keep this file's
        # numbering for the guarantees that still hold.
        js = client.get("/static/js/bank-who-why.js").data.decode("utf-8")

        # ---- 18. clean, empty Bank state renders a usable controller ---
        check(
            "18. on a clean empty Bank the page still renders its popup and no Jinja/500 error",
            "Traceback" not in html and "jinja2" not in html and 'id="who-picker"' in html
            and "bank-who-why.js" in html,
        )
        check(
            "18b. the controller guards its own absence instead of throwing "
            "(no popup, no modal controller -> early return)",
            'if (!overlay || !window.RFOneModal) { return; }' in js,
        )

        # ---- 1. no WHO -> WHY unavailable ------------------------------
        check(
            "1. with no WHO at all there is no WHY column (the popup says no WHO exists); "
            "otherwise the grouped WHY catalog is browsable as soon as the popup opens "
            "(BANK_WHY_NAVIGATION_GROUPS_001)",
            'id="why-picker"' not in html and "No WHO configured" in html
            and "Promise.all([loadWhos(), loadCatalog()])" in js,
        )
        check(
            "1b. opening the popup clears any WHY chosen before",
            "function clearWhy()" in js and "clearWhy();" in js.split("onOpen:", 1)[1].split("initialFocus", 1)[0],
        )
        check(
            "1c. Confirm requires BOTH a WHO and a WHY",
            "confirmButton.disabled = !(whoHidden.value && whyHidden.value)" in js,
        )
        check(
            "4/5. no WHY catalog is shipped in the page: WHY are loaded for the chosen WHO only",
            'data-whys-url-template="/bank/manual-reconciliation/whos/0/whys"' in html
            and "why-catalog-modal" not in html and "why-by-occurrence" not in html,
        )
        check(
            "8. no raw database id is displayed to the operator (ids are attributes only)",
            'data-reason-id' not in html,
        )
        check(
            "13. WHAT is never chosen in the popup (no WHAT control for the transaction; the only WHAT "
            "field belongs to Create New WHY, i.e. the definition of a new WHY)",
            'name="accounting_classification_id"' not in html
            and 'name="what_id"' not in html[html.index('id="who-picker-form"'):html.index("</form>", html.index('id="who-picker-form"'))]
            and html.count('name="what_id"') == html[html.index('id="why-create-form"'):].count('name="what_id"') == 1,
        )

        # ---- 15. CSRF --------------------------------------------------
        check(
            "15. the WHO/WHY form carries a CSRF token",
            'name="csrf_token"' in html,
        )
        check(
            "15b. Confirm posts to the WHO/WHY endpoint, built from an explicit placeholder",
            'data-action-template="/bank/transactions/0/who-why"' in html
            and 'actionTemplate.replace("/transactions/0/"' in js,
        )

        # ===============================================================
        # Behavioural half: exercise the real routes on real rows.
        # ===============================================================
        with SessionFactory() as db:
            instrument = m.PaymentInstrument(
                display_name="UX Test Checking", instrument_type="BANK_ACCOUNT",
                last_four="4321", status="ACTIVE",
            )
            db.add(instrument)
            db.flush()
            txn_a = m.FinancialTransaction(
                payment_instrument_id=instrument.id, posting_date=date(2026, 3, 2),
                description_original="AMAZON MARKETPLACE", amount_minor=-4200,
                bank_source="TEST", review_status="REQUIRES_REVIEW",
            )
            txn_b = m.FinancialTransaction(
                payment_instrument_id=instrument.id, posting_date=date(2026, 3, 3),
                description_original="AMAZON MARKETPLACE 2", amount_minor=-1900,
                bank_source="TEST", review_status="REQUIRES_REVIEW",
            )
            occ_type = db.scalars(select(m.BankOccurrenceType)).first()
            if occ_type is None:
                occ_type = m.BankOccurrenceType(code="SUPPLIER", name="Supplier", status="ACTIVE")
                db.add(occ_type)
                db.flush()
            who_amazon = m.BankOccurrence(
                canonical_name="Amazon", occurrence_type_id=occ_type.id, status="ACTIVE",
            )
            who_empty = m.BankOccurrence(
                canonical_name="Never Classified Co", occurrence_type_id=occ_type.id, status="ACTIVE",
            )
            db.add_all([txn_a, txn_b, who_amazon, who_empty])
            db.commit()
            txn_a_id, txn_b_id = txn_a.id, txn_b.id
            amazon_id, empty_id = who_amazon.id, who_empty.id

            # `is_profit_loss` is a derived property over the Why's
            # accounting destination, not a column, so the split is made in
            # Python rather than in SQL.
            actives = db.scalars(
                select(m.BankTransactionReason)
                .where(m.BankTransactionReason.status == "ACTIVE")
                .order_by(m.BankTransactionReason.id)
            ).all()
            pl_reason = next(r for r in actives if r.is_profit_loss)
            bs_reason = next(
                r for r in actives
                if not r.is_profit_loss and r.accounting_destination is not None
            )
            pl_id, bs_id = pl_reason.id, bs_reason.id
            pl_label, bs_label = pl_reason.resolution_label, bs_reason.resolution_label

        # ---- 2. WHO with zero WHY -> + New only -----------------------
        with SessionFactory() as db:
            check(
                "2. a Who with no association has an empty ordinary list (+ New is the only way on)",
                why_catalog.reasons_for_occurrence(db, empty_id) == [],
            )
        review = client.get("/bank/review").data.decode("utf-8")
        check(
            "2b. a WHO with no WHY yet still browses the whole grouped catalog (its own list only marks), "
            "and Create New WHY stays available",
            'id="why-picker-none"' in review and "+ Create New WHY" in review
            and client.get(f"/bank/manual-reconciliation/whos/{empty_id}/whys").get_json() == []
            and len(client.get("/bank/manual-reconciliation/why-catalog").get_json()["whys"]) > 0,
        )
        check(
            "14. the WHO's identity alone never resolves a WHY (nothing is auto-selected)",
            "autoSelect" not in js and "list.length === 1" not in js,
        )

        # ---- 15c. CSRF is enforced on the Why route --------------------
        no_csrf = client.post(f"/bank/transactions/{txn_a_id}/who-why", data={
            "occurrence_id": str(amazon_id), "transaction_reason_id": str(pl_id),
        })
        check(
            "15c. a Why post without CSRF is refused",
            no_csrf.status_code in (400, 403), f"status={no_csrf.status_code}",
        )
        with SessionFactory() as db:
            check(
                "15d. the refused post wrote nothing",
                why_catalog.reasons_for_occurrence(db, amazon_id) == [],
            )

        # ---- 11. P&L WHY derives WHAT ---------------------------------
        csrf = extract_csrf(client.get("/bank/review").data)
        ok = client.post(f"/bank/transactions/{txn_a_id}/who-why", data={
            "occurrence_id": str(amazon_id), "transaction_reason_id": str(pl_id),
            "csrf_token": csrf,
        }, follow_redirects=True)
        check("11. a Why post with CSRF succeeds", ok.status_code == 200, f"status={ok.status_code}")
        with SessionFactory() as db:
            txn = db.get(m.FinancialTransaction, txn_a_id)
            explanation = db.get(m.BankTransactionExplanation, txn.explanation_id) if txn.explanation_id else None
            check(
                "11b. the P&L Why is recorded on the transaction and its WHAT is derived, not chosen",
                explanation is not None
                and explanation.transaction_reason_id == pl_id
                and explanation.accounting_classification_id is not None,
                str(explanation and explanation.accounting_classification_id),
            )
            check("11c. the derived label is a WHAT", pl_label.startswith("WHAT:"), pl_label)
            # ---- 9/10. association created and additive ---------------
            first = [r.id for r in why_catalog.reasons_for_occurrence(db, amazon_id)]
            check("9c. selecting a Why created the WHO <-> WHY association", first == [pl_id], str(first))

        # ---- 12. non-P&L WHY derives an Accounting Destination --------
        csrf = extract_csrf(client.get("/bank/review").data)
        client.post(f"/bank/transactions/{txn_b_id}/who-why", data={
            "occurrence_id": str(amazon_id), "transaction_reason_id": str(bs_id),
            "csrf_token": csrf,
        }, follow_redirects=True)
        with SessionFactory() as db:
            txn = db.get(m.FinancialTransaction, txn_b_id)
            explanation = db.get(m.BankTransactionExplanation, txn.explanation_id) if txn.explanation_id else None
            check(
                "12. a non-P&L Why derives an Accounting Destination",
                explanation is not None and explanation.transaction_reason_id == bs_id
                and explanation.accounting_classification_id is not None,
            )
            check("12b. the derived label is an ACCOUNTING DESTINATION",
                  bs_label.startswith("ACCOUNTING DESTINATION:"), bs_label)
            both = sorted(r.id for r in why_catalog.reasons_for_occurrence(db, amazon_id))
            check(
                "10b. the second Why was ADDED — the first association still exists",
                both == sorted([pl_id, bs_id]), str(both),
            )
            # ---- 3/4. the ordinary list for this Who is exactly those --
            check(
                "3/4. the ordinary list holds exactly this Who's associations (one, then all of them)",
                len(both) == 2,
            )
            check(
                "16. the other transaction was not touched by the second decision",
                db.get(m.FinancialTransaction, txn_a_id).explanation_id is not None
                and db.get(m.BankTransactionExplanation,
                           db.get(m.FinancialTransaction, txn_a_id).explanation_id
                           ).transaction_reason_id == pl_id,
            )
            check(
                "14b. classifying Amazon never associated a Why with the untouched Who",
                why_catalog.reasons_for_occurrence(db, empty_id) == [],
            )

        # ---- 13c. WHAT cannot be posted independently ------------------
        csrf = extract_csrf(client.get("/bank/review").data)
        other_what = None
        with SessionFactory() as db:
            other_what = db.scalars(
                select(m.BankAccountingClassification)
                .where(m.BankAccountingClassification.id
                       != db.get(m.BankTransactionReason, pl_id).accounting_classification_id)
            ).first()
        client.post(f"/bank/transactions/{txn_a_id}/who-why", data={
            "occurrence_id": str(amazon_id), "transaction_reason_id": str(pl_id),
            "accounting_classification_id": str(other_what.id),
            "what_id": str(other_what.id),
            "csrf_token": csrf,
        }, follow_redirects=True)
        with SessionFactory() as db:
            txn = db.get(m.FinancialTransaction, txn_a_id)
            explanation = db.get(m.BankTransactionExplanation, txn.explanation_id)
            reason = db.get(m.BankTransactionReason, pl_id)
            check(
                "13c. a WHAT smuggled into the form is ignored — the Why's own mapping wins",
                explanation.accounting_classification_id == reason.accounting_classification_id,
                f"{explanation.accounting_classification_id} vs {reason.accounting_classification_id}",
            )

        # ---- 16. a Why decision touches only its own transaction -------
        with SessionFactory() as db:
            others = db.scalars(
                select(m.FinancialTransaction)
                .where(m.FinancialTransaction.id.notin_([txn_a_id, txn_b_id]))
            ).all()
            check("16b. no other transaction exists to have been affected", others == [])

        # ---- 19. the review page still renders with real rows ----------
        # BANK_TWO_STAGE_REVIEW_001 — a row whose WHO is resolved is listed
        # under Review > Reconciled, with its Who and Why on the row.
        final = client.get("/bank/review?view=reconciled")
        check("19. /bank/review still returns 200 with classified rows",
              final.status_code == 200, f"status={final.status_code}")
        check(
            "19b. the resolved row shows its Who and Why under Reconciled",
            # BANK_MANUAL_WHO_WHY_001 — WHY is its own column on Reconciled.
            f'id="t-{txn_a_id}"'.encode() in final.data and b'class="rp-who-name"' in final.data
            and b'class="rp-why-name"' in final.data,
        )

    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = _TEST_DB_PATH + suffix
            if os.path.exists(candidate):
                try:
                    os.remove(candidate)
                except OSError:
                    pass

    print()
    print(f"{len(passed)} passed, {len(failed)} failed.")
    if failed:
        print("FAILED CHECKS:")
        for c in failed:
            print(" -", c)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
