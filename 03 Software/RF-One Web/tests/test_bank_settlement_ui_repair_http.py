#!/usr/bin/env python
"""HTTP-level test for the settlement UI unification and the modal repair
(BANK_SETTLEMENT_UI_AND_MODAL_REPAIR_001).

The defects this pins down, so they cannot come back:

* the page offered BOTH a legacy `Settles to` select and the Settlement
  Account panel, so the same fact had two homes and only one of them fed
  accounting;
* a legacy post wrote `linked_instrument_id` directly instead of going
  through the historized service;
* the modal overlay was toggled with `hidden` while its CSS set
  `display: flex`, so it never hid — a full-screen backdrop stayed over
  the page and made it look frozen;
* the Select Who form action was built with a regex that never matched,
  so every confirmation posted to transaction 0;
* an empty candidate list rendered as a blank panel with a dead Confirm
  button instead of saying what was missing.

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_settlement_repair_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "settlement-repair-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
FULL_ACCOUNT_NUMBER = "5544332211009988"


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
        else:
            failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    try:
        with SessionFactory() as s:
            account_service.create_account(
                s, username="repair_operator", display_name="Repair Operator",
                password="OperatorPass123!", status="ACTIVE", is_admin=False,
            )
            account_service.create_account(
                s, username="no_bank", display_name="No Bank",
                password="NoBankPass123!", status="ACTIVE", is_admin=False,
            )
            entity = m.LegalEntity(legal_name="Repair UI LLC", status="ACTIVE")
            s.add(entity)
            # Only a SYSTEM identity exists — exactly the QA shape that made
            # the old cardholder form look blank while still offering a
            # nonsensical choice.
            s.add(m.ActingIdentity(kind="SYSTEM", display_name="RF-One System"))
            s.commit()
            operator = s.query(m.RFOneAccount).filter_by(username="repair_operator").one()
            account_service.set_domain_access(
                s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None,
            )
            s.commit()
            entity_id = entity.id

        client = web_app.app.test_client()
        resp = client.get("/login")
        client.post("/login", data={
            "username": "repair_operator", "password": "OperatorPass123!",
            "csrf_token": extract_csrf(resp.data),
        })

        resp = client.get("/bank")
        csrf = extract_csrf(resp.data)
        client.post("/bank/instruments/new", data={
            "institution": "CHASE", "display_name": "Repair Checking",
            "instrument_type": "BANK_ACCOUNT", "legal_entity_id": str(entity_id),
            "external_account_identifier": FULL_ACCOUNT_NUMBER, "csrf_token": csrf,
        })
        client.post("/bank/instruments/new", data={
            "institution": "CHASE", "display_name": "Repair Card",
            "instrument_type": "CREDIT_CARD", "last_four": "1057", "csrf_token": csrf,
        })
        with SessionFactory() as s:
            checking_id = s.query(m.PaymentInstrument).filter_by(
                display_name="Repair Checking").one().id
            card_id = s.query(m.PaymentInstrument).filter_by(display_name="Repair Card").one().id

        # =================================================================
        # A. One canonical settlement control
        # =================================================================
        page = client.get(f"/bank/instruments/{card_id}/edit").data
        check(
            "A1. a credit card no longer shows the legacy 'Settles to' select",
            b'name="linked_instrument_id"' not in page,
        )
        check(
            "A2. it shows the canonical Settlement Account section instead",
            b"Settlement account" in page and b"settlement_bank_account_id" in page,
        )
        check(
            "A3. the page states the configuration status up front",
            b"Missing settlement account" in page,
        )

        bank_page = client.get(f"/bank/instruments/{checking_id}/edit").data
        check(
            "A4. a bank account offers no settlement account control at all",
            b"settlement_bank_account_id" not in bank_page
            and b"not applicable" in bank_page,
        )

        # A5. A legacy post must still be routed through the canonical service.
        csrf = extract_csrf(page)
        resp = client.post(f"/bank/instruments/{card_id}/edit", data={
            "display_name": "Repair Card", "institution": "CHASE",
            "instrument_type": "CREDIT_CARD", "last_four": "1057",
            "legal_entity_id": "", "currency": "USD",
            "linked_instrument_id": str(checking_id), "status": "ACTIVE",
            "csrf_token": csrf,
        })
        check("A5. a legacy post is accepted", resp.status_code in (302, 303))
        with SessionFactory() as s:
            historized = s.query(m.BankCardSettlementAccount).filter_by(
                credit_card_payment_instrument_id=card_id).all()
            card = s.get(m.PaymentInstrument, card_id)
            check(
                "A5b. it created a HISTORIZED row, not just the legacy column",
                len(historized) == 1
                and historized[0].settlement_bank_account_id == checking_id,
                detail=f"rows={len(historized)}",
            )
            check(
                "A5c. the legacy column is kept in step as a projection",
                card.linked_instrument_id == checking_id,
            )

        # A6. Guards.
        page = client.get(f"/bank/instruments/{card_id}/edit").data
        resp = client.post(f"/bank/instruments/{card_id}/settlement", data={
            "settlement_bank_account_id": str(card_id),
            "valid_from": "2026-01-01", "csrf_token": extract_csrf(page),
        })
        with SessionFactory() as s:
            check(
                "A6. a card cannot settle to itself",
                s.query(m.BankCardSettlementAccount).filter_by(
                    credit_card_payment_instrument_id=card_id,
                    settlement_bank_account_id=card_id).count() == 0,
            )

        # =================================================================
        # D. Modal mechanics
        # =================================================================
        review = client.get("/bank/review").data
        page = client.get(f"/bank/instruments/{card_id}/edit").data

        check(
            "D1. the shared modal controller is loaded for every page",
            b"rf-one-modal.js" in page and b"rf-one-modal.js" in review,
        )
        check(
            "D2. every overlay starts hidden AND aria-hidden",
            page.count(b'class="org-modal-overlay" hidden aria-hidden="true"') >= 1
            and review.count(b'class="org-modal-overlay" hidden aria-hidden="true"') >= 1,
        )
        check(
            "D3. exactly one Who modal instance exists on the Review page",
            review.count(b'id="who-picker"') == 1,
        )
        check(
            "D4. exactly one Cardholder modal instance exists on the edit page",
            page.count(b'id="cardholder-modal"') == 1,
        )
        check(
            "D5. both modals expose X and Cancel through the shared close hook",
            page.count(b"data-modal-close") >= 2 and review.count(b"data-modal-close") >= 2,
        )

        with open(
            os.path.join(APP_DIR, "static", "css", "rf-one.css"), encoding="utf-8"
        ) as handle:
            css = handle.read()
        check(
            "D6. the root cause is fixed: `hidden` now beats the overlay's display rule",
            "[hidden] { display: none !important; }" in css,
        )
        check(
            "D7. the page behind an open modal cannot scroll, and the panel fits the viewport",
            "body.modal-open { overflow: hidden; }" in css and "max-height: calc(100vh" in css,
        )

        with open(
            os.path.join(APP_DIR, "static", "js", "rf-one-modal.js"), encoding="utf-8"
        ) as handle:
            js = handle.read()
        check(
            "D8. Escape is bound at document level, so it works wherever focus is",
            'document.addEventListener("keydown"' in js and '"Escape"' in js,
        )
        check(
            "D9. closing restores focus to the trigger and releases the page",
            "lastTrigger.focus()" in js and 'classList.remove("modal-open")' in js,
        )
        check(
            "D10. a backdrop click closes only when press and release are both on it",
            "pressedOnBackdrop" in js,
        )
        check(
            "D11. open/close leave no residual overlay — close always re-sets hidden",
            'overlay.setAttribute("hidden", "")' in js,
        )

        # =================================================================
        # F. Select Who modal
        # =================================================================
        check(
            "F1. the transaction id is substituted by an explicit placeholder, not a regex "
            "that silently never matches",
            b"/transactions/0/" in review and b"ACTION_TEMPLATE.replace" in review,
        )
        check(
            "F2. with no Who configured the modal says so",
            b"No Who configured" in review,
        )
        check(
            "F3. it links to the Classification tab",
            b"/bank/classification" in review,
        )
        check(
            "F4. no unusable Confirm button is rendered when nothing can be selected",
            b'id="who-picker-confirm"' not in review,
        )
        check(
            "F5. the modal can still be closed",
            b'id="who-picker-cancel"' in review,
        )

        # With a real Who, the control comes back.
        with SessionFactory() as s:
            what = m.BankAccountingClassification(
                code="OPEX", name="Operating expenses", statement_type="PROFIT_LOSS")
            s.add(what)
            s.flush()
            why = m.BankTransactionReason(
                code="SUPPLIER", name="Supplier payment",
                accounting_classification_id=what.id)
            kind = m.BankOccurrenceType(code="SUPPLIER", name="Supplier")
            s.add_all([why, kind])
            s.flush()
            s.add(m.BankOccurrence(
                canonical_name="US Foods", occurrence_type_id=kind.id,
                default_transaction_reason_id=why.id))
            s.add(m.FinancialTransaction(
                payment_instrument_id=card_id, bank_source="CHASE_CREDIT_CARD_WITH_CARD",
                posting_date=date(2026, 5, 5), description_original="US FOODS INC",
                description_normalized="US FOODS INC", amount_minor=-1000,
                status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW"))
            s.commit()

        review = client.get("/bank/review").data
        check(
            "F6. with a Who configured, search and Confirm are rendered again",
            b'id="who-picker-search"' in review and b'id="who-picker-confirm"' in review
            and b"US Foods" in review,
        )
        check(
            "F7. the empty state is gone once a Who exists",
            b"No Who configured" not in review,
        )

        # =================================================================
        # E. Cardholder modal
        # =================================================================
        page = client.get(f"/bank/instruments/{card_id}/edit").data
        check(
            "E1. with no person in the database the modal says so rather than showing blank",
            b"No linked people available" in page,
        )
        check(
            "E2. a SYSTEM identity is never offered as a cardholder",
            b"RF-One System" not in page,
        )
        check(
            "E3. UNLINKED_PERSON stays available by typing a name",
            b'name="holder_display_name"' in page and b'value="UNLINKED_PERSON"' in page,
        )

        csrf = extract_csrf(page)
        resp = client.post(f"/bank/instruments/{card_id}/cardholder", data={
            "holder_kind": "UNLINKED_PERSON", "holder_display_name": "Repair Test Holder",
            "valid_from": "2026-01-01", "csrf_token": csrf,
        })
        check("E4. an unlinked person can be saved", resp.status_code in (302, 303))
        page = client.get(f"/bank/instruments/{card_id}/edit").data
        check(
            "E5. the page reflects the new holder and its history",
            b"Repair Test Holder" in page and b"Cardholder: Repair Test Holder" in page,
        )

        # Real people appear once they exist, without duplicating one human.
        with SessionFactory() as s:
            s.add(m.ActingIdentity(kind="HUMAN_USER", display_name="Giulia Rossi"))
            s.commit()
        page = client.get(f"/bank/instruments/{card_id}/edit").data
        check(
            "E6. a real HUMAN_USER identity is offered, with its source named",
            b"Giulia Rossi" in page and b"RF-One identity" in page,
        )
        check(
            "E7. the empty state disappears once a real person exists",
            b"No linked people available" not in page,
        )

        # =================================================================
        # G. UX, security, responsiveness
        # =================================================================
        check(
            "G1. the full account number is never rendered",
            FULL_ACCOUNT_NUMBER.encode() not in page
            and FULL_ACCOUNT_NUMBER.encode() not in client.get("/bank").data,
        )
        check(
            "G2. the page uses the wide, no-horizontal-scroll Bank layout",
            b"wrap-wide" in page,
        )
        check(
            "G3. the edit page carries the Bank module navigation",
            b"Import &amp; Instruments" in page and b"Classification" in page,
        )

        ungated = web_app.app.test_client()
        resp = ungated.get("/login")
        ungated.post("/login", data={
            "username": "no_bank", "password": "NoBankPass123!",
            "csrf_token": extract_csrf(resp.data),
        })
        check(
            "G4. the settlement route stays behind the BANK domain gate",
            ungated.post(f"/bank/instruments/{card_id}/settlement").status_code == 403,
        )
        check(
            "G5. a settlement post without CSRF is refused",
            client.post(f"/bank/instruments/{card_id}/settlement", data={
                "settlement_bank_account_id": str(checking_id), "valid_from": "2026-02-01",
            }).status_code in (400, 403),
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
