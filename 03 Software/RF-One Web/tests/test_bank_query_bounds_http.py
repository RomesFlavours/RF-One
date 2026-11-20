"""Bank pages must not issue one query per transaction, Who, receiver group
or What (BANK_PERFORMANCE_N_PLUS_ONE_001).

Builds a realistic synthetic Bank state: several instruments and batches,
thousands of transactions, hundreds of Whos with aliases and Why
associations, hundreds of receiver groups with exact recognition rules,
human Why decisions, and cross-ledger matches (one of them on the same
instrument, which the batch review must count as invalid).

For each optimized path it checks that:
1. the business result equals the one the former per-row algorithm gives;
2. the page renders (200) and shows the expected business content;
3. the SQL statement count stays under a ceiling that does not grow with the
   data — checked by rendering again after the dataset has been doubled.

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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_bank_query_bounds_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "bank-query-bounds-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

from sqlalchemy import event, func, select  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.bank_reconciliation import classification as classification_service  # noqa: E402
from rfone_data_store.bank_reconciliation import receiver_candidates as rc  # noqa: E402
from rfone_data_store.bank_reconciliation import recognition  # noqa: E402
from rfone_data_store.bank_reconciliation import service as bank_service  # noqa: E402
from rfone_data_store.bank_reconciliation import why_catalog  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
STATEMENTS = [0]


@event.listens_for(Engine, "before_cursor_execute")
def _count(*_args, **_kwargs):
    STATEMENTS[0] += 1


def old_invalid_match_count(session, batch) -> int:
    """The former per-transaction algorithm, kept here as the oracle."""
    invalid = 0
    for txn in session.scalars(select(m.FinancialTransaction).where(
            m.FinancialTransaction.import_batch_id == batch.id)):
        for match in session.scalars(select(m.FinancialTransactionMatch).where(
                (m.FinancialTransactionMatch.transaction_a_id == txn.id)
                | (m.FinancialTransactionMatch.transaction_b_id == txn.id))):
            other_id = match.transaction_b_id if match.transaction_a_id == txn.id else match.transaction_a_id
            other = session.get(m.FinancialTransaction, other_id)
            if other is not None and other.payment_instrument_id == txn.payment_instrument_id:
                invalid += 1
    return invalid


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        account_service.create_account(s, username="perf_operator", display_name="Perf",
                                       password="PerfOperator123!", status="ACTIVE", is_admin=False)
        s.flush()
        operator = s.query(m.RFOneAccount).filter_by(username="perf_operator").one()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="BANK", enabled=True, role_code=None)
        entity = m.LegalEntity(legal_name="Perf LLC", status="ACTIVE")
        s.add(entity)
        s.flush()
        instruments = []
        for n, (kind, last) in enumerate((("BANK_ACCOUNT", "1001"), ("BANK_ACCOUNT", "1002"), ("CREDIT_CARD", "1003"))):
            inst = m.PaymentInstrument(legal_entity_id=entity.id, instrument_type=kind, display_name=f"Perf Instrument {n}",
                                       institution="CHASE", last_four=last, currency="USD")
            s.add(inst)
            instruments.append(inst)
        s.flush()
        whos_type = m.BankOccurrenceType(code="SUPPLIER", name="Supplier")
        s.add(whos_type)
        s.flush()
        reasons = s.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE")
                            .order_by(m.BankTransactionReason.id)).all()
        s.commit()
        seq = [0]

        def grow(batches: int, per_batch: int, payees: int, whos: int, tag: str) -> list:
            """Add one slice of realistic Bank state."""
            new_batches = []
            for b in range(batches):
                seq[0] += 1
                inst = instruments[b % 3]
                batch = m.BankImportBatch(detected_format="CHASE_BANK_ACCOUNT", original_file_name=f"{tag}-{b}.csv",
                                          raw_file_bytes=b"x", sha256=f"{seq[0]:064d}", status="NORMALIZED",
                                          payment_instrument_id=inst.id, date_range_start=date(2026, 5, 1),
                                          date_range_end=date(2026, 5, 31))
                s.add(batch)
                s.flush()
                new_batches.append(batch)
                rows = []
                for i in range(per_batch):
                    payee = f"{tag} PAYEE {(b * per_batch + i) % payees}"
                    rows.append(m.FinancialTransaction(
                        payment_instrument_id=inst.id, bank_source="CHASE_BANK_ACCOUNT", import_batch_id=batch.id,
                        posting_date=date(2026, 5, 1 + i % 28), description_original=payee,
                        description_normalized=payee, payee_normalized=payee, amount_minor=-(100 + i),
                        status="COMPLETED", duplicate_status="NONE", review_status="REQUIRES_REVIEW",
                        accounting_status="CANONICAL"))
                s.add_all(rows)
                s.flush()
            created = []
            for w in range(whos):
                who = m.BankOccurrence(canonical_name=f"{tag} Who {w}", occurrence_type_id=whos_type.id, status="ACTIVE")
                s.add(who)
                created.append(who)
            s.flush()
            for w, who in enumerate(created):
                for k in range(2):
                    s.add(m.BankOccurrenceAlias(occurrence_id=who.id, alias_text=f"{who.canonical_name} alias {k}",
                                                alias_key=f"{tag} WHO {w} ALIAS {k}", source_family="TEST"))
                s.add(m.BankOccurrenceReasonAssociation(occurrence_id=who.id,
                                                        transaction_reason_id=reasons[w % len(reasons)].id))
            s.flush()
            for p in range(0, payees, 3):  # exact rules for a third of the payees
                recognition.create_or_reuse_rule(
                    s, match_type=recognition.EXACT_NORMALIZED_DESCRIPTION, normalized_pattern=f"{tag} PAYEE {p}",
                    occurrence_id=created[p % whos].id, transaction_reason_id=reasons[0].id,
                    payment_instrument_id=None, direction=None, auto_apply_enabled=True,
                    created_from_transaction_id=None)
            txns = s.scalars(select(m.FinancialTransaction).where(
                m.FinancialTransaction.import_batch_id.in_([b.id for b in new_batches])).order_by(
                m.FinancialTransaction.id)).all()
            for t in txns[:: max(len(txns) // 150, 1)]:   # human Why decisions
                recognition.record_human_decision(s, recognition.HumanDecisionRequest(
                    transaction_id=t.id, occurrence_id=created[t.id % whos].id,
                    transaction_reason_id=reasons[t.id % 5].id, confirmed_by_account_id=None,
                    learn_description=False))
            # one match on the SAME instrument (invalid) and one across
            # instruments (valid); the schema orders every pair (a < b)
            s.add_all([
                m.FinancialTransactionMatch(transaction_a_id=txns[0].id, transaction_b_id=txns[3].id,
                                            match_method="HUMAN", matched_amount_minor=100),
                m.FinancialTransactionMatch(transaction_a_id=txns[1].id, transaction_b_id=txns[-1].id,
                                            match_method="HUMAN", matched_amount_minor=100),
            ])
            s.commit()
            return new_batches

        batches = grow(batches=6, per_batch=500, payees=600, whos=300, tag="A")

        # ---- 1. business equivalence with the former per-row algorithms -----
        def equivalence(label):
            all_batches = s.scalars(select(m.BankImportBatch)).all()
            new = {b.id: bank_service.compute_batch_review_state(s, b).invalid_match_count for b in all_batches}
            old = {b.id: old_invalid_match_count(s, b) for b in all_batches}
            check(f"{label}: invalid-match count per batch equals the former per-transaction algorithm "
                  f"(total {sum(new.values())})", new == old and sum(new.values()) > 0, f"{new} vs {old}")
            candidates = rc.build_candidates(s)
            check(f"{label}: summary from the page's candidates equals summary built on its own",
                  rc.summary(s, candidates) == rc.summary(s))
            rules = {r.normalized_pattern: r for r in s.scalars(select(m.BankRecognitionRule)).all()}
            suggested = [c for c in candidates if c.status == rc.STATUS_UNCLASSIFIED and c.payee_normalized in rules]
            check(f"{label}: every unclassified group with an exact rule gets that rule's Who as suggestion "
                  f"({len(suggested)} groups)",
                  suggested and all(c.suggested_occurrence_id == rules[c.payee_normalized].occurrence_id for c in suggested))
            whats = s.scalars(select(m.BankAccountingClassification)).all()
            check(f"{label}: bulk What usage equals the per-What usage for all {len(whats)} Whats",
                  classification_service.accounting_classification_usages(s)
                  == {w.id: classification_service.accounting_classification_usage(s, w.id) for w in whats})
            whos = s.scalars(select(m.BankOccurrence)).all()
            bulk = why_catalog.reasons_by_occurrence(s)
            check(f"{label}: bulk Who->Why map equals the per-Who query for all {len(whos)} Whos",
                  all([r.id for r in bulk.get(w.id, [])] == [r.id for r in why_catalog.reasons_for_occurrence(s, w.id)]
                      for w in whos))

        equivalence("3,000 transactions")

        # ---- 2/3. pages render, show content, and stay under a flat ceiling --
        client = web_app.app.test_client()
        csrf = CSRF_RE.search(client.get("/login").data.decode()).group(1)
        client.post("/login", data={"username": "perf_operator", "password": "PerfOperator123!", "csrf_token": csrf})
        # Ceilings far below the number of transactions, Whos or groups; the
        # doubled dataset must stay under the same ones.
        CEILINGS = {"/bank": 250, "/bank/classification": 150, "/bank/review": 700}

        def render(label):
            counts = {}
            for path, ceiling in CEILINGS.items():
                STATEMENTS[0] = 0
                response = client.get(path)
                counts[path] = STATEMENTS[0]
                body = response.data.decode("utf-8", "replace")
                check(f"{label}: GET {path} -> 200 with {counts[path]} SQL statements (ceiling {ceiling})",
                      response.status_code == 200 and counts[path] <= ceiling and "Traceback" not in body,
                      f"{response.status_code} {counts[path]}")
                if path == "/bank":
                    check(f"{label}: /bank lists the instruments", "Perf Instrument 0" in body and "Perf Instrument 2" in body)
                elif path == "/bank/classification":
                    check(f"{label}: /bank/classification shows receiver groups and Whos",
                          "PAYEE" in body and "Who 1" in body)
                else:
                    check(f"{label}: /bank/review shows transactions and the Who picker",
                          "PAYEE" in body and "who-picker" in body)
            return counts

        before = render("3,000 transactions")
        grow(batches=6, per_batch=500, payees=600, whos=300, tag="B")
        equivalence("6,000 transactions")
        after = render("6,000 transactions")
        for path in CEILINGS:
            check(f"{path}: statements do not grow with the data ({before[path]} -> {after[path]})",
                  after[path] <= before[path] + 20, f"{before[path]} -> {after[path]}")

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
