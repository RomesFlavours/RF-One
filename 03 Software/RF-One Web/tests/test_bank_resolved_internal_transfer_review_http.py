"""Own-account transfers are resolved without a WHO (BANK_TWO_STAGE_REVIEW_001,
"Own-account movements are resolved without a WHO").

To Reconcile means "the business meaning is still unresolved", not "the WHO
field is empty". Proves, on a throwaway database, that:

* an ordinary transaction with no WHO (or only a recognizer proposal) stays
  To Reconcile;
* an own-account movement — STRUCTURAL WHO recognition (registered RF-One
  instrument) or a confirmed INTERNAL_TRANSFER match — is NOT To Reconcile
  and IS under Reconciled, with or without a decision, and the counts move
  by exactly those rows;
* an open duplicate question still keeps it To Reconcile;
* Reconciled shows it truthfully: no WHO invented, "Internal transfer · <other
  account>" instead of "No WHO yet", the existing WHY and WHAT, status Needs
  review;
* a description Rule over those rows ("ONLINE TRANSFER") writes no WHO on
  them, reports them as own-account transfers resolved without WHO, and says
  they are under Reconciled;
* a Rule over an ordinary WHO, a person's WHO + WHY + Confirm, and Confirmed
  status behave as before.

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
from rfone_data_store.bank_reconciliation import who_recognition as wr  # noqa: E402
from rfone_data_store.bank_reconciliation import why_catalog  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
AUG = date(2026, 8, 12)
MONTH = "year=2026&month=8"
ONLINE_RULE = "Dove nella descrizione trovi ONLINE TRANSFER il WHO è Online Transfer"
GORDON_RULE = "Dove nella descrizione trovi GORDON FOOD il WHO è Gordon Food Service"


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

        def tx(description, *, instrument=checking, structural_to=None, deterministic=None, why=None,
               duplicate="NONE"):
            seq[0] += 1
            t = m.FinancialTransaction(
                payment_instrument_id=instrument.id, bank_source="CHASE_BANK_ACCOUNT", import_batch_id=batch.id,
                posting_date=AUG, transaction_date=AUG, description_original=description,
                description_normalized=description, amount_minor=-1000 - seq[0], status="COMPLETED",
                duplicate_status=duplicate, review_status="REQUIRES_REVIEW", accounting_status="CANONICAL",
                fingerprint=f"own-transfer-{seq[0]}", classification="UNKNOWN")
            s.add(t)
            s.flush()
            if structural_to is not None:
                s.add(m.BankWhoRecognition(
                    financial_transaction_id=t.id, recognizer_version=wr.RECOGNIZER_VERSION, tier=wr.STRUCTURAL,
                    family=wr.F_INTERNAL_TRANSFER, parser_code="ONLINE_TRANSFER",
                    internal_payment_instrument_id=structural_to.id, referenced_last_four=structural_to.last_four,
                    evidence="registered RF-One instrument"))
            if deterministic is not None:
                s.add(m.BankWhoRecognition(
                    financial_transaction_id=t.id, recognizer_version=wr.RECOGNIZER_VERSION, tier=wr.DETERMINISTIC,
                    family="ACH_ORIGINATOR", parser_code="ACH", extracted_name=deterministic.canonical_name,
                    occurrence_id=deterministic.id, evidence="ach originator"))
            if why is not None:
                # The structural WHY engine's own RULE decision: a WHY and its
                # destination, deliberately no WHO.
                recognition._create_decision_row(
                    s, t, occurrence_id=None, transaction_reason_id=why.id, recognition_rule_id=None,
                    decision_source="RULE", decision_status="NEEDS_HUMAN_REVIEW", confidence="HIGH",
                    explanation_notes="structural WHY", accounting_classification_id=why.accounting_classification_id)
            s.flush()
            return t

        rows = {
            "no_who": tx("SOME UNKNOWN PAYEE 4477"),
            "proposal": tx("GORDON FOOD SERVICE ACH 01", deterministic=gordon),
            "transfer_why": tx("ONLINE TRANSFER TO CHK ...0002 TRANSACTION#: 1", structural_to=savings, why=transfer_why),
            "transfer_bare": tx("ONLINE TRANSFER TO CHK ...0002 TRANSACTION#: 2", structural_to=savings),
            "transfer_dup": tx("ONLINE TRANSFER TO CHK ...0002 TRANSACTION#: 3", structural_to=savings,
                               duplicate="CANDIDATE_DUPLICATE"),
            "matched_a": tx("TRANSFER OUT TO RESERVE"),
            "matched_b": tx("TRANSFER IN FROM CHECKING", instrument=savings),
            "manual": tx("CORNER HARDWARE 55"),
        }
        s.add(m.FinancialTransactionMatch(transaction_a_id=rows["matched_a"].id, transaction_b_id=rows["matched_b"].id,
                                          match_method="HUMAN", match_basis="test", matched_amount_minor=1007))
        s.commit()
        ids = {k: t.id for k, t in rows.items()}
        ids.update(gordon=gordon.id, food=food.id, entity=entity.id, savings=savings.id)
        transfer_keys = ("transfer_why", "transfer_bare")
        own_keys = transfer_keys + ("matched_a", "matched_b")
        check("setup: a transfer WHY with an accounting destination exists",
              transfer_why is not None and transfer_why.accounting_classification_id is not None)
        transfer_decision_before = {
            k: (e.occurrence_id, e.transaction_reason_id, e.accounting_classification_id) if e else None
            for k in own_keys
            for e in [recognition.get_current_explanation(s, financial_transaction_id=ids[k])]
        }
        explanations_before = s.scalar(select(func.count(m.BankTransactionExplanation.id)))

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
    check("1b. a recognizer proposal alone is still not a resolved WHO",
          in_to_reconcile(to_rec, "proposal") and not in_reconciled(rec, "proposal"))
    check("2. a recognised own-account transfer with no WHO is NOT To Reconcile (with or without a WHY)",
          not any(in_to_reconcile(to_rec, k) for k in transfer_keys))
    check("3. the same transfers ARE under Reconciled", all(in_reconciled(rec, k) for k in transfer_keys))
    check("3b. both sides of a confirmed INTERNAL_TRANSFER match are under Reconciled",
          in_reconciled(rec, "matched_a") and in_reconciled(rec, "matched_b")
          and not in_to_reconcile(to_rec, "matched_a"))
    check("3c. an own-account transfer whose duplicate question is open stays To Reconcile",
          in_to_reconcile(to_rec, "transfer_dup") and not in_reconciled(rec, "transfer_dup"))
    # 8 rows in scope; 0 WHO named; 4 own-account movements resolved.
    check("4. counts move by exactly the own-account rows and stay consistent",
          who_named == 0 and counts == {"to_reconcile": 4, "reconciled": 4}
          and sum(counts.values()) == len(rows)
          and "To Reconcile (4)" in to_rec and "Reconciled (4)" in rec, detail=str(counts))

    row_html = re.search(r'<tr id="t-%d".*?</tr>' % ids["transfer_why"], rec, re.S).group(0)
    bare_html = re.search(r'<tr id="t-%d".*?</tr>' % ids["transfer_bare"], rec, re.S).group(0)
    matched_html = re.search(r'<tr id="t-%d".*?</tr>' % ids["matched_a"], rec, re.S).group(0)
    check("5. Reconciled shows the transfer truthfully: the other own account, the existing WHY and WHAT",
          "Internal transfer · Reserve Savings" in row_html and "No WHO yet" not in row_html
          and str(escape(transfer_why.name)) in row_html and "data-what=" in row_html
          and "Internal transfer · Reserve Savings" in bare_html and "WHY needed" in bare_html
          and "Internal transfer (matched)" in matched_html,
          detail=f"{transfer_why.name!r}: {row_html[row_html.find('rp-who'):][:600]!r}")
    check("5b. its status is the truthful one (Needs review) and no WHO is shown on the row",
          'data-status="Needs review"' in row_html and "data-who=" not in row_html)
    check("5c. Reconciled help says own-account transfers need no WHO",
          "transfers between RF-One&#39;s own accounts, which need no WHO" in rec
          or "transfers between RF-One's own accounts, which need no WHO" in rec)

    # ------------------------------------------------------------------
    # The ONLINE TRANSFER Rule (6, 7)
    # ------------------------------------------------------------------
    csrf = CSRF_RE.search(to_rec).group(1)
    applied = client.post("/bank/who-rules/apply", headers={"X-Requested-With": "fetch"}, data={
        "csrf_token": csrf, "new_who_name": "Online Transfer", "instruction": ONLINE_RULE,
        "transaction_id": str(ids["transfer_bare"]), "return_to": f"/bank/review?{MONTH}"})
    body = applied.get_json() or {}
    after = client.get(body.get("redirect") or f"/bank/review?{MONTH}").data.decode()
    with SessionFactory() as s:
        decisions_after = {
            k: (e.occurrence_id, e.transaction_reason_id, e.accounting_classification_id) if e else None
            for k in own_keys
            for e in [recognition.get_current_explanation(s, financial_transaction_id=ids[k])]
        }
        online = s.scalars(select(m.BankOccurrence).where(m.BankOccurrence.canonical_name == "Online Transfer")).first()
        named_online = s.scalar(select(func.count(m.BankTransactionExplanation.id)).where(
            m.BankTransactionExplanation.occurrence_id == (online.id if online else -1)))
        explanations_after = s.scalar(select(func.count(m.BankTransactionExplanation.id)))
    check("6. the ONLINE TRANSFER Rule writes no WHO on own-account transfers (no fake WHO)",
          applied.status_code == 200 and body.get("ok") and named_online == 0
          and explanations_after == explanations_before, detail=str(body))
    check("6b. WHY and accounting destination of every own-account row are preserved",
          decisions_after == transfer_decision_before, detail=f"{transfer_decision_before} -> {decisions_after}")
    check("7. the Rule result reports them as resolved own-account transfers, under Reconciled — not failures",
          "Own-account transfers resolved without WHO" in after and "Own accounts, no WHO" not in after
          and re.search(r"Own-account transfers resolved without WHO</dt><dd>3</dd>", after) is not None
          and "are transfers between RF-One" in after and "View reconciled transactions" in after,
          detail=re.findall(r"Own-account[^<]*</dt><dd>\d+", after).__str__())
    check("7b. after the Rule the own-account rows are still out of To Reconcile, counts unchanged",
          not any(in_to_reconcile(after, k) for k in transfer_keys) and "To Reconcile (4)" in after)

    # ------------------------------------------------------------------
    # Unchanged behaviour (8-10)
    # ------------------------------------------------------------------
    csrf = CSRF_RE.search(after).group(1)
    gordon_apply = client.post("/bank/who-rules/apply", headers={"X-Requested-With": "fetch"}, data={
        "csrf_token": csrf, "occurrence_id": str(ids["gordon"]), "instruction": GORDON_RULE,
        "transaction_reason_id": [str(ids["food"])], "transaction_id": str(ids["proposal"]),
        "return_to": f"/bank/review?{MONTH}"})
    gordon_after = client.get(f"/bank/review?{MONTH}").data.decode()
    gordon_rec = client.get(f"/bank/review?{MONTH}&view=reconciled").data.decode()
    with SessionFactory() as s:
        proposal = recognition.get_current_explanation(s, financial_transaction_id=ids["proposal"])
    check("8. a Rule over an ordinary WHO still assigns it and moves the row to Reconciled",
          gordon_apply.status_code == 200 and proposal is not None and proposal.occurrence_id == ids["gordon"]
          and not in_to_reconcile(gordon_after, "proposal") and in_reconciled(gordon_rec, "proposal")
          and "WHO assigned to 1 transaction" in gordon_after,
          detail=str(gordon_apply.get_json()))

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
