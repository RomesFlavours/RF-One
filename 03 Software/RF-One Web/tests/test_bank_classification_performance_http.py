"""Bank > Classification stays fast at production size (BANK_SIMPLE_WHO_RULE_001).

Builds a synthetic dataset shaped like production after the canonical
WHO/WHY import — 1,324 WHO (1,159 active, 165 INACTIVE merged fragments),
1,852 aliases, 12,678 transactions with their WHO recognitions, 921 current
decisions — and checks that the initial Classification GET:

* answers well inside gunicorn's 60 s timeout: under 2 s here;
* stays under 300 KB of HTML;
* issues a bounded number of SQL statements, independent of the data;
* never builds receiver candidates over every transaction.

Then measures one Apply on the same dataset. Never touches a real bank file,
AWS, or any production database.
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_bank_classification_perf_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-classification-perf-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from sqlalchemy import event, func, insert, select  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import receiver_candidates  # noqa: E402
from rfone_data_store.bank_reconciliation import who_recognition as wr  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
STATEMENTS = [0]
WHO_TOTAL, WHO_INACTIVE, ALIASES, TRANSACTIONS, DECISIONS = 1324, 165, 1852, 12678, 921
RECOGNIZED = "Recognised by who-v1 from the bank's own text (CARD_MERCHANT). Identity only."


@event.listens_for(Engine, "before_cursor_execute")
def _count(*_args, **_kwargs):
    STATEMENTS[0] += 1


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + (f" ({detail})" if detail else ""))

    build_start = time.perf_counter()
    with SessionFactory() as s:
        account_service.create_account(s, username="perf_rule_operator", display_name="Perf",
                                       password="PerfRuleOperator123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="perf_rule_operator").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        entity = m.LegalEntity(legal_name="Perf Rule LLC", status="ACTIVE")
        s.add(entity)
        s.flush()
        card = m.PaymentInstrument(legal_entity_id=entity.id, instrument_type="CREDIT_CARD", display_name="Perf Card",
                                   institution="CHASE", last_four="4242", currency="USD")
        s.add(card)
        s.flush()
        batch = m.BankImportBatch(detected_format="CHASE_CREDIT_CARD_WITH_CARD", original_file_name="perf.csv",
                                  raw_file_bytes=b"x", sha256="2" * 64, status="NORMALIZED",
                                  payment_instrument_id=card.id)
        s.add(batch)
        s.flush()
        counterparty = s.scalars(select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == "COUNTERPARTY")).one()

        s.execute(insert(m.BankOccurrence), [
            {"canonical_name": f"VENDOR {n:04d} STORE {n % 37}", "occurrence_type_id": counterparty.id,
             "status": "INACTIVE" if n < WHO_INACTIVE else "ACTIVE", "optional_notes": RECOGNIZED,
             "category_capability": "UNKNOWN"}
            for n in range(WHO_TOTAL)
        ])
        who_ids = s.scalars(select(m.BankOccurrence.id).order_by(m.BankOccurrence.id)).all()
        active_ids = who_ids[WHO_INACTIVE:]
        s.execute(insert(m.BankOccurrenceAlias), [
            {"occurrence_id": active_ids[n % len(active_ids)], "alias_text": f"VENDOR ALIAS {n:05d}",
             "alias_key": f"VENDOR ALIAS {n:05d}", "source_family": "MERGED_WHO_NAME" if n < WHO_INACTIVE else "CARD_MERCHANT",
             "source": "HUMAN" if n < WHO_INACTIVE else "PARSER"}
            for n in range(ALIASES)
        ])
        s.execute(insert(m.FinancialTransaction), [
            {"payment_instrument_id": card.id, "bank_source": "CHASE_CREDIT_CARD_WITH_CARD", "import_batch_id": batch.id,
             "posting_date": date(2026, 1 + n % 8, 1 + n % 28), "transaction_date": date(2026, 1 + n % 8, 1 + n % 28),
             "description_original": f"VENDOR {active_ids[n % len(active_ids)] % 10000:04d} STORE ORLANDO FL",
             "description_normalized": "x", "amount_minor": -(100 + n), "status": "COMPLETED",
             "duplicate_status": "NONE", "review_status": "REQUIRES_REVIEW", "accounting_status": "CANONICAL",
             "fingerprint": f"perf-{n}", "classification": "UNKNOWN"}
            for n in range(TRANSACTIONS)
        ])
        tx_ids = s.scalars(select(m.FinancialTransaction.id).order_by(m.FinancialTransaction.id)).all()
        s.execute(insert(m.BankWhoRecognition), [
            {"financial_transaction_id": tx_id, "recognizer_version": wr.RECOGNIZER_VERSION,
             "tier": wr.DETERMINISTIC, "family": "CARD_MERCHANT", "parser_code": "CARD_DESCRIPTOR",
             "occurrence_id": active_ids[n % len(active_ids)], "evidence": "card statement merchant descriptor"}
            for n, tx_id in enumerate(tx_ids)
        ])
        s.execute(insert(m.BankTransactionExplanation), [
            {"financial_transaction_id": tx_ids[n], "occurrence_id": active_ids[n % len(active_ids)],
             "decision_source": "RULE", "decision_status": "AUTO_APPLIED", "explanation_notes": "perf",
             "accounting_destination_source": "WHY"}
            for n in range(DECISIONS)
        ])
        for explanation_id, tx_id in s.execute(select(m.BankTransactionExplanation.id,
                                                      m.BankTransactionExplanation.financial_transaction_id)).all():
            s.execute(m.FinancialTransaction.__table__.update().where(
                m.FinancialTransaction.id == tx_id).values(explanation_id=explanation_id))
        s.commit()
        shape = (s.scalar(select(func.count(m.BankOccurrence.id))),
                 s.scalar(select(func.count(m.BankOccurrence.id)).where(m.BankOccurrence.status == "ACTIVE")),
                 s.scalar(select(func.count(m.BankOccurrenceAlias.id))),
                 s.scalar(select(func.count(m.FinancialTransaction.id))))
        target_who = s.get(m.BankOccurrence, active_ids[0]).canonical_name
    print(f"  dataset built in {time.perf_counter() - build_start:.1f}s: WHO={shape[0]} active={shape[1]} "
          f"aliases={shape[2]} transactions={shape[3]}")
    check("the dataset has production's shape (1,324 WHO, 1,159 active, 1,852 aliases, 12,678 transactions)",
          shape == (WHO_TOTAL, WHO_TOTAL - WHO_INACTIVE, ALIASES, TRANSACTIONS))

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Classification must not build receiver candidates over every transaction")

    original_build = receiver_candidates.build_candidates
    receiver_candidates.build_candidates = forbidden

    client = web_app.app.test_client()
    csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
    client.post("/login", data={"username": "perf_rule_operator", "password": "PerfRuleOperator123!",
                                "csrf_token": csrf})

    timings, sizes, statements = [], [], []
    for _ in range(3):
        STATEMENTS[0] = 0
        start = time.perf_counter()
        resp = client.get("/bank/classification")
        timings.append(time.perf_counter() - start)
        sizes.append(len(resp.data))
        statements.append(STATEMENTS[0])
    print(f"  GET /bank/classification: {', '.join(f'{t:.3f}s' for t in timings)}; "
          f"{sizes[-1] / 1024:.1f} KB; {statements[-1]} SQL statements")
    check("40. the initial Classification GET at production size answers 200 in under 2 s",
          resp.status_code == 200 and max(timings[1:]) < 2.0, detail=f"{max(timings):.3f}s")
    check("41. its HTML is under 300 KB", sizes[-1] < 300 * 1024, detail=f"{sizes[-1] / 1024:.1f} KB")
    check("42. no timeout risk: a bounded statement count, receiver candidates never built",
          statements[-1] <= 40, detail=f"{statements[-1]} statements")
    STATEMENTS[0] = 0
    start = time.perf_counter()
    searched = client.get("/bank/classification?q=VENDOR%2001&page=2")
    print(f"  GET /bank/classification?q=...&page=2: {time.perf_counter() - start:.3f}s, "
          f"{len(searched.data) / 1024:.1f} KB, {STATEMENTS[0]} SQL statements")
    check("42b. a search and a later page are as bounded", searched.status_code == 200 and STATEMENTS[0] <= 40)
    receiver_candidates.build_candidates = original_build

    page = resp.data.decode()
    csrf = CSRF_RE.search(page).group(1)
    with SessionFactory() as s:
        who_id = s.scalars(select(m.BankOccurrence.id).where(m.BankOccurrence.canonical_name == target_who)).one()
    pattern = " ".join(target_who.split(" ")[:2])
    start = time.perf_counter()
    applied = client.post("/bank/who-rules/apply", headers={"X-Requested-With": "fetch"}, data={
        "csrf_token": csrf, "occurrence_id": str(who_id), "return_to": "/bank/classification",
        "instruction": f'Dove nella descrizione trovi "{pattern}" il WHO è {target_who}'})
    elapsed = time.perf_counter() - start
    print(f"  POST Apply (contains {pattern!r}) on 12,678 transactions: {elapsed:.2f}s -> {applied.get_json()}")
    check("Apply on the production-size dataset completes well inside the request timeout",
          applied.status_code == 200 and applied.get_json()["ok"] and elapsed < 30, detail=f"{elapsed:.2f}s")

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
