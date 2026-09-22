#!/usr/bin/env python
"""HTTP-level test for the manual Bank reconciliation UX
(BANK_MANUAL_RECONCILIATION_UX_001).

The gap this closes: the server side of WHO -> WHY -> "+ New" was already
correct, but `bank_review.html` never wired it. The Why step existed as
markup that was permanently hidden, "+ New" did nothing, the catalog search
filtered nothing, and no `transaction_reason_id` was ever submitted.

Two server defects surfaced while wiring it, and are pinned here too:

* `/bank/transactions/<id>/why` called a bare `current_account()`, a name
  that exists nowhere in `bank_routes.py`, so the route raised NameError on
  every request. Nothing reached it while the Why step was unwired.
* the same route performed no `require_csrf()`, unlike every other writing
  Bank route.

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

        # ---- 18. clean, empty Bank state renders a usable controller ---
        check(
            "18. on a clean empty Bank the page still renders its controller and no Jinja/500 error",
            "Traceback" not in html and "jinja2" not in html and "<script>" in html,
        )
        check(
            "18b. the controller guards its own absence instead of throwing "
            "(no Who list, no modal -> early return)",
            "if (!overlay || !window.RFOneModal) { return; }" in js,
        )

        # ---- 1. no WHO -> WHY unavailable ------------------------------
        check(
            "1. the Why step starts hidden and only appears once a Who is selected",
            'id="why-picker" hidden' in html and "whyPicker.hidden = false" in js,
        )
        check(
            "1b. clearing/absent Who hides the Why control and blanks the derived result",
            "function clearSelection()" in js
            and "if (whyPicker) { whyPicker.hidden = true; }" in js
            and "clearWhy();" in js,
        )
        check(
            "1c. Confirm requires BOTH a Who and a Why",
            "confirm.disabled = !(hidden.value && reasonHidden && reasonHidden.value)" in js,
        )
        check(
            "4/5. the full catalog is not shown before a Who exists",
            'id="why-catalog-modal" hidden' in html,
        )

        # ---- 3/5. management groups: modal only ------------------------
        with SessionFactory() as db:
            groups = why_catalog.groups(db)
            catalog = why_catalog.catalog_by_group(db)
            active_reasons = why_catalog.active_reasons(db)
            group_names = [g.name for g, _ in catalog if g is not None]
            reason_ids = [r.id for r in active_reasons]

        check("canonical vocabulary present: 14 management groups", len(groups) == 14, str(len(groups)))
        check("canonical vocabulary present: 77 active Why", len(active_reasons) == 77,
              str(len(active_reasons)))

        # The catalog modal region: from its own id up to the JSON island
        # that follows it. The ordinary step's list is the (JS-filled)
        # container, which must be free of group names in the markup.
        # Unescaped, because group names and account labels legitimately
        # contain "&" and Jinja escapes it — comparing raw names against
        # escaped markup would fail for a reason that has nothing to do
        # with the behaviour under test.
        catalog_block = unescape(
            html.split('id="why-catalog-modal"', 1)[-1].split('id="why-by-occurrence"', 1)[0]
        )
        why_picker_block = unescape(
            html.split('id="why-picker"', 1)[-1].split('id="why-catalog-modal"', 1)[0]
        )
        check(
            "5. management groups appear ONLY inside the + New modal, never in the ordinary step",
            all(name in catalog_block for name in group_names)
            and not any(name in why_picker_block for name in group_names),
            "missing from modal: %s | leaked into ordinary step: %s" % (
                [n for n in group_names if n not in catalog_block],
                [n for n in group_names if n in why_picker_block],
            ),
        )
        check(
            "6. management groups are rendered inside the modal, in catalog order",
            [n for n in group_names if n in catalog_block] == group_names,
        )
        check(
            "5b. the ordinary Why list is built only from this Who's associations, never from groups",
            "WHY_BY_OCCURRENCE[String(occurrenceId)]" in js and "reason_group" not in js,
        )

        # ---- 7. the modal holds every active canonical WHY -------------
        check(
            "7. the modal contains every active canonical Why",
            all(f'data-reason-id="{rid}"' in catalog_block for rid in reason_ids),
            f"{sum(1 for rid in reason_ids if f'data-reason-id=' + chr(34) + str(rid) + chr(34) in catalog_block)}/{len(reason_ids)}",
        )
        check(
            "8. no raw database id is displayed to the operator (ids are attributes only)",
            ">" + str(reason_ids[0]) + "<" not in catalog_block,
        )

        # ---- 8. search covers name, code, group, destination -----------
        with SessionFactory() as db:
            sample = db.get(m.BankTransactionReason, reason_ids[0])
            sample_group = db.get(m.BankReasonGroup, sample.reason_group_id) if sample.reason_group_id else None
            haystack_needles = [sample.name.lower(), sample.code.lower(),
                                sample.resolution_label.lower()]
            if sample_group:
                haystack_needles.append(sample_group.name.lower())
        row = re.search(r'<li class="why-option"\s+data-reason-id="%d"\s.*?</li>' % sample.id,
                        catalog_block, re.S)
        check(
            "8b. each catalog row's search haystack carries Why name, Why code, group name "
            "and the resolved account label",
            row is not None and all(n in row.group(0).lower() for n in haystack_needles),
            row.group(0)[:300] if row else "row not found",
        )
        check(
            "8c. the modal has its own search input and filter, separate from the Who search",
            'id="why-catalog-search"' in html and "function applyCatalogFilter()" in js
            and "li.dataset.haystack" in js,
        )
        check(
            "8d. filtering hides groups that have nothing left, and says when nothing matches",
            "group.hidden = !visible" in js and 'id="why-catalog-empty"' in html,
        )

        # ---- 9. + New opens/closes and refreshes the ordinary list -----
        check(
            "9. + New opens the catalog",
            'id="why-picker-new"' in html and "whyNewButton.addEventListener('click'" in js
            and "openCatalog()" in js,
        )
        check(
            "9b. choosing a catalog Why selects it, refreshes the short list and closes the modal",
            "renderKnownWhy(occurrenceId);" in js and "selectWhy(id);" in js
            and "closeCatalog();" in js,
        )
        check(
            "10. a second Why is ADDED to the Who's list, never replacing the first",
            "sessionAdded[occurrenceId].indexOf(id) === -1" in js
            and "sessionAdded[occurrenceId].push(id)" in js,
        )

        # ---- 13. WHAT is derived and read-only -------------------------
        check(
            "13. the derived outcome is shown read-only, with no control that edits it",
            'id="why-picker-result"' in html and "DERIVED &mdash; READ-ONLY" in html
            and 'name="accounting_classification_id"' not in html
            and 'name="what_id"' not in html,
        )
        check(
            "13b. the page states that a wrong Why -> What is fixed centrally, not per transaction",
            "never chosen per transaction" in html,
        )

        # ---- 15. CSRF --------------------------------------------------
        check(
            "15. the Who/Why form carries a CSRF token",
            'name="csrf_token"' in html,
        )
        check(
            "15b. Confirm posts to the Why endpoint, built from an explicit placeholder",
            "WHY_ACTION_TEMPLATE" in js and "/transactions/0/" in js
            and "ACTION_TEMPLATE.replace" in js,
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
            "2b. the page says an empty list is a legitimate state and points at + New",
            'id="why-picker-none"' in review and "No purpose has been confirmed for this Who yet" in review,
        )
        check(
            "14. the Who's identity alone never resolves a Why (nothing is auto-selected)",
            "sessionAdded = {};" in script_of(review) and "autoSelect" not in script_of(review),
        )

        # ---- 15c. CSRF is enforced on the Why route --------------------
        no_csrf = client.post(f"/bank/transactions/{txn_a_id}/why", data={
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
        ok = client.post(f"/bank/transactions/{txn_a_id}/why", data={
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
        client.post(f"/bank/transactions/{txn_b_id}/why", data={
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
        client.post(f"/bank/transactions/{txn_a_id}/why", data={
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
        final = client.get("/bank/review")
        check("19. /bank/review still returns 200 with classified rows",
              final.status_code == 200, f"status={final.status_code}")
        check(
            "19b. the resolved row shows Who / Why / What read-only",
            b"Who:" in final.data and b"Why:" in final.data and b"What:" in final.data,
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
