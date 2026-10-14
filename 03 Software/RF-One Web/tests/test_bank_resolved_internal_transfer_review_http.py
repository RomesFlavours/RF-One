"""Own-account transfers are resolved without a WHO (BANK_TWO_STAGE_REVIEW_001,
"Own-account movements are resolved without a WHO").

To Reconcile means "the business meaning is still unresolved", not "the WHO
field is empty". Proves, on a throwaway database, that:

* an ordinary transaction with no WHO stays To Reconcile;
* an own-account movement — a confirmed INTERNAL_TRANSFER match — is NOT To
  Reconcile and IS under Reconciled, with or without a decision, and the
  counts move by exactly those rows;
* an open duplicate question still keeps it To Reconcile;
* Reconciled shows it truthfully: no WHO invented, "Internal transfer
  (matched)" instead of "No WHO yet", the existing WHY and WHAT, status Needs
  review;
* a person's WHO + WHY + Confirm, and Confirmed status behave as before.

BANK_RULES_RESET_001 retired the simple WHO Rule (POST /bank/who-rules/apply):
the former checks 6-8 (the ONLINE TRANSFER and Gordon Rules) went with it.

BANK_OLD_RULES_REMOVAL_001 removed the structural WHO recognitions: a
STRUCTURAL BankWhoRecognition no longer makes a row an own-account movement,
only a confirmed INTERNAL_TRANSFER match does. The transfer rows (with a WHY,
bare, with an open duplicate question) are therefore re-expressed as one side
of such a match, each with its counterpart on the savings account; checks 2,
3, 3c, 5, 5b and 10 keep their intent on those rows. Check 1b (a DETERMINISTIC
recognizer proposal alone is not a resolved WHO) went with the recognizer.
Check 4's counts follow the new fixture (10 rows: 3 To Reconcile, 7
Reconciled) and check 5 expects the label the product now shows, "Internal
transfer (matched)", instead of "Internal transfer · <other account>".

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_resolved_transfer_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-resolved-transfer-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from markupsafe import escape  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import deterministic_rules  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.bank_reconciliation import reconciliation_status  # noqa: E402
from rfone_data_store.bank_reconciliation import review_queues  # noqa: E402
from rfone_data_store.bank_reconciliation import row_reconciliation  # noqa: E402
from rfone_data_store.bank_reconciliation import why_catalog  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
AUG = date(2026, 8, 12)
MONTH = "year=2026&month=8"


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="own_transfer", display_name="Own Transfer",
                                       password="OwnTransfer123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="own_transfer").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        deterministic_rules.seed_structural_reasons(s, strict=False)
        legal = m.LegalEntity(legal_name="Own Transfer LLC", status="ACTIVE")
        s.add(legal)
        s.flush()
        entity = m.ReportingEntity(code="RE_OWN_TRANSFER", name="Own Transfer", entity_type="LEGAL",
                                   legal_entity_id=legal.id, status="ACTIVE")
        checking = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                       display_name="Main Checking", institution="CHASE", last_four="0001",
                                       currency="USD")
        savings = m.PaymentInstrument(legal_entity_id=legal.id, instrument_type="BANK_ACCOUNT",
                                      display_name="Reserve Savings", institution="CHASE", last_four="0002",
                                      currency="USD")
        s.add_all([entity, checking, savings])
        s.flush()
        batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name="seed.csv",
                                  raw_file_bytes=b"x", sha256="7" * 64, status="NORMALIZED",
                                  payment_instrument_id=checking.id)
        s.add(batch)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()
        food = s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE",
                                                               m.BankTransactionReason.name.ilike("%food%"))
                         .order_by(m.BankTransactionReason.id)).first()
        transfer_why = s.scalars(select(m.BankTransactionReason).where(
            m.BankTransactionReason.status == "ACTIVE",
            m.BankTransactionReason.accounting_classification_id.is_not(None),
            m.BankTransactionReason.name.ilike("%transfer%")).order_by(m.BankTransactionReason.id)).first()
        gordon = m.BankOccurrence(canonical_name="Gordon Food Service", occurrence_type_id=counterparty.id,
                                  status="ACTIVE", optional_notes="Canonical WHO.")
        s.add(gordon)
        s.flush()
        why_catalog.associate(s, occurrence_id=gordon.id, transaction_reason_id=food.id, source="HUMAN")
        seq = [0]

        def tx(description, *, instrument=checking, why=None, duplicate="NONE"):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=instrument.id, bank_source="CHASE_BANK_ACCOUNT", import_batch_id=batch.id,
                posting_date=AUG, transaction_date=AUG, description_original=description,
                description_normalized=description, amount_minor=-1000 - seq[0], status="COMPLETED",
                duplicate_status=duplicate, review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"own-transfer-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            if why is not None:
                # The structural WHY engine's own RULE decision: a WHY and its
                # destination, deliberately no WHO.
                recognition._create_decision_row(
                    s, t, occurrence_id=None, transaction_reason_id=why.id, decision_source="RULE", decision_status="NEEDS_HUMAN_REVIEW", confidence="HIGH",
                    explanation_notes="structural WHY", accounting_classification_id=why.accounting_classification_id)
            s.flush()
            return t

        # BANK_OLD_RULES_REMOVAL_001: an own-account movement is ONLY a
        # confirmed INTERNAL_TRANSFER match now, so every transfer row is one
        # side of such a match, with its other side on the savings account.
        rows = {
            "no_who": tx("SOME UNKNOWN PAYEE 4477"),
            "transfer_why": tx("ONLINE TRANSFER TO CHK ...0002 TRANSACTION#: 1", why=transfer_why),
            "transfer_why_in": tx("ONLINE TRANSFER FROM CHK ...0001 TRANSACTION#: 1", instrument=savings),
            "transfer_bare": tx("ONLINE TRANSFER TO CHK ...0002 TRANSACTION#: 2"),
            "transfer_bare_in": tx("ONLINE TRANSFER FROM CHK ...0001 TRANSACTION#: 2", instrument=savings),
            "transfer_dup": tx("ONLINE TRANSFER TO CHK ...0002 TRANSACTION#: 3", duplicate="CANDIDATE_DUPLICATE"),
            "transfer_dup_in": tx("ONLINE TRANSFER FROM CHK ...0001 TRANSACTION#: 3", instrument=savings),
            "matched_a": tx("TRANSFER OUT TO RESERVE"),
            "matched_b": tx("TRANSFER IN FROM CHECKING", instrument=savings),
            "manual": tx("CORNER HARDWARE 55"),
        }
        for a_key, b_key in (("transfer_why", "transfer_why_in"), ("transfer_bare", "transfer_bare_in"),
                             ("transfer_dup", "transfer_dup_in"), ("matched_a", "matched_b")):
            s.add(m.FinancialTransactionMatch(transaction_a_id=rows[a_key].id, transaction_b_id=rows[b_key].id,
                                              match_method="HUMAN", match_basis="test",
                                              matched_amount_minor=-rows[a_key].amount_minor))
        s.commit()
        ids = {k: t.id for k, t in rows.items()}
        ids.update(gordon=gordon.id, food=food.id, entity=entity.id, savings=savings.id)
        transfer_keys = ("transfer_why", "transfer_bare")
        check("setup: a transfer WHY with an accounting destination exists",
              transfer_why is not None and transfer_why.accounting_classification_id is not None)

        # Counts with the former "WHO named" criterion, for the movement check.
        who_named = s.scalar(select(func.count(m.FinancialTransaction.id)).outerjoin(
            m.BankTransactionExplanation, m.BankTransactionExplanation.id == m.FinancialTransaction.explanation_id)
            .where(m.BankTransactionExplanation.occurrence_id.is_not(None)))
        counts = review_queues.counts(s, review_queues.ReviewFilters(year=2026, month=8))

    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "own_transfer", "password": "OwnTransfer123!", "csrf_token": csrf})

    def in_to_reconcile(html, key):
        return f'data-transaction-id="{ids[key]}"' in html

    def in_reconciled(html, key):
        return f'id="t-{ids[key]}"' in html

    to_rec = client.get(f"/bank/review?{MONTH}").data.decode()
    rec = client.get(f"/bank/review?{MONTH}&view=reconciled").data.decode()

    check("1. an ordinary transaction with no WHO stays To Reconcile",
          in_to_reconcile(to_rec, "no_who") and not in_reconciled(rec, "no_who"))
    # Check 1b (a recognizer proposal alone is not a resolved WHO) went with
    # BANK_OLD_RULES_REMOVAL_001: the WHO recognizer no longer exists.
    check("2. a matched own-account transfer with no WHO is NOT To Reconcile (with or without a WHY)",
          not any(in_to_reconcile(to_rec, k) for k in transfer_keys))
    check("3. the same transfers ARE under Reconciled", all(in_reconciled(rec, k) for k in transfer_keys))
    check("3b. both sides of a confirmed INTERNAL_TRANSFER match are under Reconciled",
          in_reconciled(rec, "matched_a") and in_reconciled(rec, "matched_b")
          and not in_to_reconcile(to_rec, "matched_a"))
    check("3c. an own-account transfer whose duplicate question is open stays To Reconcile",
          in_to_reconcile(to_rec, "transfer_dup") and not in_reconciled(rec, "transfer_dup"))
    # 10 rows in scope; 0 WHO named; 7 own-account movements resolved (the
    # 8th matched row, transfer_dup, still has its duplicate question open).
    check("4. counts move by exactly the own-account rows and stay consistent",
          who_named == 0 and counts == {"to_reconcile": 3, "reconciled": 7}
          and sum(counts.values()) == len(rows)
          and "To Reconcile (3)" in to_rec and "Reconciled (7)" in rec, detail=str(counts))

    row_html = re.search(r'<tr id="t-%d".*?</tr>' % ids["transfer_why"], rec, re.S).group(0)
    bare_html = re.search(r'<tr id="t-%d".*?</tr>' % ids["transfer_bare"], rec, re.S).group(0)
    matched_html = re.search(r'<tr id="t-%d".*?</tr>' % ids["matched_a"], rec, re.S).group(0)
    check("5. Reconciled shows the transfer truthfully: an internal transfer, the existing WHY and WHAT",
          "Internal transfer (matched)" in row_html and "No WHO yet" not in row_html
          and str(escape(transfer_why.name)) in row_html and "data-what=" in row_html
          and "Internal transfer (matched)" in bare_html and "WHY needed" in bare_html
          and "Internal transfer (matched)" in matched_html,
          detail=f"{transfer_why.name!r}: {row_html[row_html.find('rp-who'):][:600]!r}")
    check("5b. its status is the truthful one (Needs review) and no WHO is shown on the row",
          'data-status="Needs review"' in row_html and "data-who=" not in row_html)
    check("5c. Reconciled help says own-account transfers need no WHO",
          "transfers between RF-One&#39;s own accounts, which need no WHO" in rec
          or "transfers between RF-One's own accounts, which need no WHO" in rec)

    # ------------------------------------------------------------------
    # Unchanged behaviour (9-10). The former Rule checks 6-8 are retired
    # with the simple WHO Rule (BANK_RULES_RESET_001).
    # ------------------------------------------------------------------

    with SessionFactory() as s:
        row_reconciliation.record_who(s, transaction_id=ids["manual"], occurrence_id=ids["gordon"],
                                      reason_id=ids["food"], account_id=None)
        s.commit()
        row_reconciliation.confirm_row(s, transaction_id=ids["manual"], reporting_entity_id=ids["entity"],
                                       account_id=None)
        s.commit()
        statuses = reconciliation_status.statuses_for(
            s, [s.get(m.FinancialTransaction, ids[k]) for k in ("manual", "transfer_why", "transfer_bare")])
        refused = None
        try:
            row_reconciliation.confirm_row(s, transaction_id=ids["transfer_why"], reporting_entity_id=ids["entity"],
                                           account_id=None)
        except ValueError as exc:
            refused = str(exc)
        s.rollback()
    manual_rec = client.get(f"/bank/review?{MONTH}&view=reconciled").data.decode()
    check("9. a person's WHO + WHY + Confirm still moves the row to Reconciled as Confirmed",
          statuses[ids["manual"]] == reconciliation_status.CONFIRMED and in_reconciled(manual_rec, "manual"))
    check("10. Confirmed / Needs review semantics unchanged: an own-account row is Needs review and "
          "Confirm still requires a WHO",
          statuses[ids["transfer_why"]] == reconciliation_status.NEEDS_REVIEW
          and statuses[ids["transfer_bare"]] == reconciliation_status.NEEDS_REVIEW
          and refused is not None and "WHO" in refused, detail=str(refused))

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
