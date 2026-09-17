#!/usr/bin/env python
"""Legacy Explanation -> canonical decision migration tests
(FINANCIAL_MODEL_CONVERGENCE_001, Phase 4B, migration `8ddfe6f314be`).

Uses ONLY synthetic legacy-shaped data — never a real/shared database.
Stops the schema at the Phase 4 head (`00e6783b630f`, before legacy
columns are retired), inserts synthetic legacy `bank_transaction_
explanations` rows and `financial_transactions.explanation_id`
references via raw SQL (mirroring exactly what the pre-4B schema looked
like), then runs ONLY the Phase 4B migration and verifies its
deterministic-only migration behavior: exact-name Occurrence matching,
no invented Reason, preserved snapshots, and no silent data loss.

Usage:
    python test_bank_reconciliation_decision_migration.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from rfone_data_store.database import (
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_session_factory,
    redact_database_url,
)
from rfone_data_store import models as m

_MODULE_DIR = Path(__file__).resolve().parent
_PHASE_4_HEAD = "00e6783b630f"
_PHASE_4B_HEAD = "8ddfe6f314be"


def _new_disposable_url(label: str) -> str:
    """Mirrors `database.create_disposable_test_database_url`'s naming
    convention (so `cleanup_disposable_test_database_url` still recognizes
    and removes it) WITHOUT that helper's own auto-migration-to-head side
    effect — this test needs to stop mid-chain at the Phase 4 head first."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix=f"rfone_test_{label}_")
    os.close(fd)
    os.remove(path)
    return f"sqlite:///{Path(path).as_posix()}"


def _alembic_config(url: str) -> Config:
    cfg = Config(str(_MODULE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_MODULE_DIR / "migrations"))
    os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = url
    return cfg


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    url = _new_disposable_url("bank_reconciliation_decision_migration")
    print(f"Database URL: {redact_database_url(url)}")
    previous_override = os.environ.get("ALEMBIC_DATABASE_URL_OVERRIDE")

    try:
        cfg = _alembic_config(url)
        command.upgrade(cfg, _PHASE_4_HEAD)

        engine = create_configured_engine(url)
        try:
            with engine.connect() as conn:
                legal_entity_id = conn.execute(
                    text("INSERT INTO legal_entities (legal_name, status) VALUES ('Migration Test LLC', 'ACTIVE')")
                ).lastrowid
                instrument_id = conn.execute(
                    text(
                        "INSERT INTO payment_instruments "
                        "(legal_entity_id, instrument_type, display_name, status) "
                        "VALUES (:le, 'BANK_ACCOUNT', 'Migration Test Instrument', 'ACTIVE')"
                    ),
                    {"le": legal_entity_id},
                ).lastrowid

                # An existing canonical BankOccurrence a deterministic match should find.
                supplier_type_id = conn.execute(
                    text("INSERT INTO bank_occurrence_types (code, name, status) VALUES ('SUPPLIER', 'Supplier', 'ACTIVE')")
                ).lastrowid
                us_foods_occurrence_id = conn.execute(
                    text(
                        "INSERT INTO bank_occurrences (canonical_name, occurrence_type_id, status) "
                        "VALUES ('US Foods', :t, 'ACTIVE')"
                    ),
                    {"t": supplier_type_id},
                ).lastrowid

                # --- Transaction A: legacy explanation name MATCHES an existing
                # Occurrence -> deterministic occurrence match expected. -----------
                txn_a_id = conn.execute(
                    text(
                        "INSERT INTO financial_transactions "
                        "(payment_instrument_id, amount_minor, status, classification) "
                        "VALUES (:pi, -45000, 'UNKNOWN', 'UNKNOWN')"
                    ),
                    {"pi": instrument_id},
                ).lastrowid
                legacy_a_id = conn.execute(
                    text(
                        "INSERT INTO bank_transaction_explanations "
                        "(name, category, food_cost, operative, deductible, what_label, active) "
                        "VALUES ('US Foods', 'Food', 1, 0, 0, 'Food Supplier', 1)"
                    )
                ).lastrowid
                conn.execute(
                    text("UPDATE financial_transactions SET explanation_id = :e WHERE id = :t"),
                    {"e": legacy_a_id, "t": txn_a_id},
                )

                # --- Transaction B: legacy explanation name has NO matching
                # Occurrence -> occurrence must be left NULL, never fabricated. -----
                txn_b_id = conn.execute(
                    text(
                        "INSERT INTO financial_transactions "
                        "(payment_instrument_id, amount_minor, status, classification) "
                        "VALUES (:pi, -1500, 'UNKNOWN', 'UNKNOWN')"
                    ),
                    {"pi": instrument_id},
                ).lastrowid
                legacy_b_id = conn.execute(
                    text(
                        "INSERT INTO bank_transaction_explanations "
                        "(name, category, food_cost, operative, deductible, what_label, active) "
                        "VALUES ('Unknown Landscaping Co', NULL, 0, 1, 0, 'Grounds maintenance', 1)"
                    )
                ).lastrowid
                conn.execute(
                    text("UPDATE financial_transactions SET explanation_id = :e WHERE id = :t"),
                    {"e": legacy_b_id, "t": txn_b_id},
                )

                # --- Transaction C: no legacy explanation, but already has an
                # Expert System decision row with no pointer (Decision 6 backfill). --
                txn_c_id = conn.execute(
                    text(
                        "INSERT INTO financial_transactions "
                        "(payment_instrument_id, amount_minor, status, classification) "
                        "VALUES (:pi, -900, 'UNKNOWN', 'UNKNOWN')"
                    ),
                    {"pi": instrument_id},
                ).lastrowid
                expert_system_row_id = conn.execute(
                    text(
                        "INSERT INTO bank_transaction_explanations "
                        "(financial_transaction_id, decision_source, decision_status, confidence) "
                        "VALUES (:t, 'RULE', 'NEEDS_HUMAN_REVIEW', NULL)"
                    ),
                    {"t": txn_c_id},
                ).lastrowid

                conn.commit()
        finally:
            engine.dispose()

        # --- Run ONLY the Phase 4B migration. --------------------------------
        command.upgrade(cfg, _PHASE_4B_HEAD)

        engine = create_configured_engine(url)
        try:
            session_factory = create_session_factory(engine)
            with session_factory() as s:
                # --- 1. Deterministic legacy Occurrence migration works. -----------
                txn_a = s.get(m.FinancialTransaction, txn_a_id)
                decision_a = s.get(m.BankTransactionExplanation, txn_a.explanation_id)
                check(
                    "Deterministic legacy Occurrence migration matches an existing BankOccurrence",
                    decision_a.occurrence_id == us_foods_occurrence_id,
                )
                check(
                    "Migrated decision id differs from the retired legacy row id (a new canonical row was created)",
                    decision_a.id != legacy_a_id,
                )

                # --- 2. Legacy Kermali values preserved as snapshots. ---------------
                check(
                    "Legacy food_cost/operative/deductible/what_label preserved as snapshot (txn A)",
                    decision_a.food_cost_snapshot is True
                    and decision_a.operative_snapshot is False
                    and decision_a.deductible_snapshot is False
                    and decision_a.what_label_snapshot == "Food Supplier",
                )
                check(
                    "Legacy name preserved as occurrence_name_snapshot (txn A)",
                    decision_a.occurrence_name_snapshot == "US Foods",
                )

                # --- 3. No Reason is invented when absent. --------------------------
                check(
                    "No Reason is invented for a migrated legacy decision (txn A)",
                    decision_a.transaction_reason_id is None,
                )
                check(
                    "Migrated decision is left NEEDS_HUMAN_REVIEW (txn A)",
                    decision_a.decision_status == "NEEDS_HUMAN_REVIEW",
                )

                # --- 4. Ambiguous legacy row (no Occurrence match) remains HUMAN
                # review — never fabricated. -----------------------------------------
                txn_b = s.get(m.FinancialTransaction, txn_b_id)
                decision_b = s.get(m.BankTransactionExplanation, txn_b.explanation_id)
                check(
                    "No matching BankOccurrence -> occurrence_id left NULL, never fabricated (txn B)",
                    decision_b.occurrence_id is None,
                )
                check(
                    "Unmatched legacy row still left NEEDS_HUMAN_REVIEW (txn B)",
                    decision_b.decision_status == "NEEDS_HUMAN_REVIEW",
                )

                # --- 5. No known legacy export value is silently lost, even when
                # unmatched. ------------------------------------------------------
                check(
                    "Unmatched legacy row's known Kermali values still preserved as snapshot (txn B)",
                    decision_b.occurrence_name_snapshot == "Unknown Landscaping Co"
                    and decision_b.operative_snapshot is True
                    and decision_b.what_label_snapshot == "Grounds maintenance",
                )

                # --- Decision 6 backfill: txn C's pre-existing Expert System row
                # becomes the current pointer. ----------------------------------------
                txn_c = s.get(m.FinancialTransaction, txn_c_id)
                check(
                    "Pre-existing un-pointed Expert System decision is backfilled as current (txn C)",
                    txn_c.explanation_id == expert_system_row_id,
                )

                # --- 6. category is not propagated anywhere. -------------------------
                check(
                    "BankTransactionExplanation no longer has a category column",
                    not hasattr(m.BankTransactionExplanation, "category")
                    or "category" not in m.BankTransactionExplanation.__table__.columns,
                )

                # --- 7. active is not propagated to decision rows. --------------------
                check(
                    "BankTransactionExplanation no longer has an active column",
                    not hasattr(m.BankTransactionExplanation, "active")
                    or "active" not in m.BankTransactionExplanation.__table__.columns,
                )

        finally:
            engine.dispose()

    finally:
        if previous_override is None:
            os.environ.pop("ALEMBIC_DATABASE_URL_OVERRIDE", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = previous_override
        cleanup_disposable_test_database_url(url)

    print()
    print(f"{len(checks_passed)} passed, {len(checks_failed)} failed.")
    if checks_failed:
        print("FAILED CHECKS:")
        for c in checks_failed:
            print(" -", c)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
