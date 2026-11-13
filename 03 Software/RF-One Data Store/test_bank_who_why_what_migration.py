#!/usr/bin/env python
"""Migration regression test for BANK_RECONCILIATION_WHO_WHY_WHAT_001.

Builds a throwaway SQLite database at the revision BEFORE this migration
(`b2f6c4a8d713`), fills it with synthetic LEGACY Bank data — Occurrences,
Reasons, Kermali export mappings carrying `what_label`, recognition rules
and confirmed decision rows with their historical snapshots — then runs
the migration and asserts:

* every legacy row survives, with every legacy value byte-identical;
* every distinct legacy `what_label` became one WHAT, explicitly
  INCOMPLETE (no invented statement type);
* WHO -> WHY is filled only where a single Why is the Who's whole history,
  and left NULL where it is not;
* historical decisions are linked to the WHAT migrated from the very
  label they themselves recorded, and their own Kermali snapshot values
  are untouched;
* no `financial_transactions` row is created, deleted or duplicated;
* the raw preservation layer is not touched;
* downgrade restores the previous schema and refuses to destroy an
  audited HUMAN_RECLASSIFIED decision.

Never touches AWS, RDS, a production database, or a real bank file.
"""

from __future__ import annotations

import os
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import sqlalchemy as sa  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

BEFORE_REVISION = "b2f6c4a8d713"
THIS_REVISION = "f1c7a94d6e02"


def _alembic_config(database_url: str) -> Config:
    """`migrations/env.py` resolves the URL itself and honours
    `ALEMBIC_DATABASE_URL_OVERRIDE` — the same mechanism
    `test_bank_reconciliation_decision_migration.py` already uses to keep a
    migration test entirely inside its own throwaway SQLite file."""
    config = Config(os.path.join(BASE_DIR, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(BASE_DIR, "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = database_url
    return config


def _seed_legacy(engine: sa.Engine) -> dict:
    """Synthetic pre-migration data, written with raw SQL against the OLD
    schema on purpose — `models.py` already describes the NEW one, so using
    the ORM here would not exercise a genuine legacy database."""
    ids: dict = {}
    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO legal_entities (legal_name, status) VALUES ('Legacy LLC', 'ACTIVE')"
        ))
        legal_entity_id = conn.execute(sa.text("SELECT id FROM legal_entities")).scalar_one()

        conn.execute(
            sa.text(
                "INSERT INTO payment_instruments (legal_entity_id, instrument_type, display_name, status) "
                "VALUES (:le, 'BANK_ACCOUNT', 'Legacy Checking', 'ACTIVE')"
            ),
            {"le": legal_entity_id},
        )
        instrument_id = conn.execute(sa.text("SELECT id FROM payment_instruments")).scalar_one()
        ids["instrument_id"] = instrument_id

        conn.execute(sa.text(
            "INSERT INTO bank_occurrence_types (code, name, status) VALUES ('SUPPLIER', 'Supplier', 'ACTIVE')"
        ))
        type_id = conn.execute(sa.text("SELECT id FROM bank_occurrence_types")).scalar_one()

        for name in ("US Foods", "Sysco", "Ambiguous Party"):
            conn.execute(
                sa.text(
                    "INSERT INTO bank_occurrences (canonical_name, occurrence_type_id, status) "
                    "VALUES (:n, :t, 'ACTIVE')"
                ),
                {"n": name, "t": type_id},
            )
        occurrences = dict(conn.execute(sa.text("SELECT canonical_name, id FROM bank_occurrences")).fetchall())
        ids["occurrences"] = occurrences

        for code, name in (
            ("SUPPLIER_INVOICE_PAYMENT", "Supplier Invoice Payment"),
            ("PAYROLL", "Payroll"),
            ("UNMAPPED_REASON", "Unmapped Reason"),
        ):
            conn.execute(
                sa.text(
                    "INSERT INTO bank_transaction_reasons (code, name, status) VALUES (:c, :n, 'ACTIVE')"
                ),
                {"c": code, "n": name},
            )
        reasons = dict(conn.execute(sa.text("SELECT code, id FROM bank_transaction_reasons")).fetchall())
        ids["reasons"] = reasons

        # Two Reasons share one label -> exactly ONE WHAT must be created.
        for reason_code, food, oper, deduct, label in (
            ("SUPPLIER_INVOICE_PAYMENT", 1, 0, 0, "Food Supplier"),
            ("PAYROLL", 0, 1, 1, "Food Supplier"),
            ("UNMAPPED_REASON", 0, 1, 0, None),
        ):
            conn.execute(
                sa.text(
                    "INSERT INTO bank_transaction_reason_export_mappings "
                    "(bank_transaction_reason_id, food_cost, operative, deductible, what_label) "
                    "VALUES (:r, :f, :o, :d, :l)"
                ),
                {"r": reasons[reason_code], "f": food, "o": oper, "d": deduct, "l": label},
            )

        # A recognition rule — part of the WHO -> WHY evidence.
        conn.execute(
            sa.text(
                "INSERT INTO bank_recognition_rules "
                "(match_type, normalized_pattern, occurrence_id, transaction_reason_id, priority, "
                " status, auto_apply_enabled, human_confirmations, human_contradictions) "
                "VALUES ('EXACT_NORMALIZED_DESCRIPTION', 'US FOODS INVOICE', :o, :r, 0, 'ACTIVE', 1, 1, 0)"
            ),
            {"o": occurrences["US Foods"], "r": reasons["SUPPLIER_INVOICE_PAYMENT"]},
        )

        # Three transactions, each with one confirmed decision.
        specs = [
            ("US FOODS INVOICE", -41250, "US Foods", "SUPPLIER_INVOICE_PAYMENT", "Food Supplier", 1, 0, 0),
            ("SYSCO ORDER 88", -10000, "Sysco", "PAYROLL", "Food Supplier", 0, 1, 1),
            ("MYSTERY CHARGE", -500, "Ambiguous Party", "UNMAPPED_REASON", None, 0, 1, 0),
        ]
        txn_ids = {}
        for description, amount, who, why, label, food, oper, deduct in specs:
            conn.execute(
                sa.text(
                    "INSERT INTO financial_transactions "
                    "(payment_instrument_id, bank_source, posting_date, description_original, "
                    " amount_minor, classification, status) "
                    "VALUES (:i, 'CHASE_BANK_ACCOUNT', '2026-05-05', :d, :a, 'UNKNOWN', 'COMPLETED')"
                ),
                {"i": instrument_id, "d": description, "a": amount},
            )
            txn_id = conn.execute(
                sa.text("SELECT id FROM financial_transactions WHERE description_original = :d"),
                {"d": description},
            ).scalar_one()
            txn_ids[description] = txn_id
            conn.execute(
                sa.text(
                    "INSERT INTO bank_transaction_explanations "
                    "(financial_transaction_id, occurrence_id, transaction_reason_id, decision_source, "
                    " decision_status, confidence, explanation_notes, occurrence_name_snapshot, "
                    " food_cost_snapshot, operative_snapshot, deductible_snapshot, what_label_snapshot) "
                    "VALUES (:t, :o, :r, 'HUMAN', 'HUMAN_CONFIRMED', 'HIGH', 'legacy', :n, :f, :op, :d, :l)"
                ),
                {
                    "t": txn_id, "o": occurrences[who], "r": reasons[why], "n": who,
                    "f": food, "op": oper, "d": deduct, "l": label,
                },
            )
            explanation_id = conn.execute(
                sa.text(
                    "SELECT id FROM bank_transaction_explanations WHERE financial_transaction_id = :t"
                ),
                {"t": txn_id},
            ).scalar_one()
            conn.execute(
                sa.text("UPDATE financial_transactions SET explanation_id = :e WHERE id = :t"),
                {"e": explanation_id, "t": txn_id},
            )

        # "Ambiguous Party" gets a SECOND decision with a DIFFERENT Why, so
        # its default Why is genuinely not determinable and must stay NULL.
        conn.execute(
            sa.text(
                "INSERT INTO bank_transaction_explanations "
                "(financial_transaction_id, occurrence_id, transaction_reason_id, decision_source, "
                " decision_status, explanation_notes) "
                "VALUES (:t, :o, :r, 'HUMAN', 'HUMAN_OVERRIDDEN', 'legacy second opinion')"
            ),
            {
                "t": txn_ids["MYSTERY CHARGE"], "o": occurrences["Ambiguous Party"],
                "r": reasons["PAYROLL"],
            },
        )

        # Raw preservation layer — must be byte-identical afterwards.
        conn.execute(
            sa.text(
                "INSERT INTO bank_import_batches "
                "(detected_format, payment_instrument_id, original_file_name, raw_file_bytes, sha256, "
                " row_count, status) "
                "VALUES ('CHASE_BANK_ACCOUNT', :i, 'legacy.csv', :b, 'deadbeef', 1, 'NORMALIZED')"
            ),
            {"i": instrument_id, "b": b"Details,Posting Date\nDEBIT,05/05/2026\n"},
        )
        ids["txn_ids"] = txn_ids
    return ids


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="rfone_who_why_what_migration_")
    os.close(fd)
    os.remove(db_path)
    database_url = f"sqlite:///{db_path.replace(os.sep, '/')}"
    config = _alembic_config(database_url)
    engine = sa.create_engine(database_url)

    try:
        command.upgrade(config, BEFORE_REVISION)
        ids = _seed_legacy(engine)

        with engine.begin() as conn:
            txn_count_before = conn.execute(sa.text("SELECT COUNT(*) FROM financial_transactions")).scalar_one()
            decision_count_before = conn.execute(
                sa.text("SELECT COUNT(*) FROM bank_transaction_explanations")
            ).scalar_one()
            raw_bytes_before = conn.execute(sa.text("SELECT raw_file_bytes FROM bank_import_batches")).scalar_one()
            mappings_before = conn.execute(sa.text(
                "SELECT bank_transaction_reason_id, food_cost, operative, deductible, what_label "
                "FROM bank_transaction_reason_export_mappings ORDER BY id"
            )).fetchall()

        command.upgrade(config, THIS_REVISION)

        with engine.begin() as conn:
            # --- no loss, no duplication ---------------------------------
            check(
                "no FinancialTransaction is created, deleted or duplicated by the migration",
                conn.execute(sa.text("SELECT COUNT(*) FROM financial_transactions")).scalar_one()
                == txn_count_before,
            )
            check(
                "every historical decision row survives (append-only history intact)",
                conn.execute(sa.text("SELECT COUNT(*) FROM bank_transaction_explanations")).scalar_one()
                == decision_count_before,
            )
            check(
                "the raw preservation layer is byte-identical after the migration",
                conn.execute(sa.text("SELECT raw_file_bytes FROM bank_import_batches")).scalar_one()
                == raw_bytes_before,
            )
            check(
                "the Kermali export mapping rows are left exactly as they were",
                conn.execute(sa.text(
                    "SELECT bank_transaction_reason_id, food_cost, operative, deductible, what_label "
                    "FROM bank_transaction_reason_export_mappings ORDER BY id"
                )).fetchall() == mappings_before,
            )

            # --- legacy what_label -> WHAT --------------------------------
            whats = conn.execute(sa.text(
                "SELECT code, name, statement_type, active FROM bank_accounting_classifications"
            )).fetchall()
            check(
                "two Reasons sharing one legacy what_label produce exactly ONE What",
                len(whats) == 1, detail=repr(whats),
            )
            check(
                "the migrated What keeps the legacy label as its name and a stable derived code",
                bool(whats) and whats[0][0] == "LEGACY_FOOD_SUPPLIER" and whats[0][1] == "Food Supplier",
                detail=repr(whats),
            )
            check(
                "the migrated What is explicitly INCOMPLETE — no statement type is invented",
                bool(whats) and whats[0][2] is None,
            )

            linked = dict(conn.execute(sa.text(
                "SELECT code, accounting_classification_id FROM bank_transaction_reasons"
            )).fetchall())
            check(
                "both Reasons that used the legacy label are linked to that one What",
                linked["SUPPLIER_INVOICE_PAYMENT"] is not None
                and linked["SUPPLIER_INVOICE_PAYMENT"] == linked["PAYROLL"],
            )
            check(
                "a Reason with no legacy label is left explicitly without a What, never guessed",
                linked["UNMAPPED_REASON"] is None,
            )

            # --- WHO -> WHY, only when determinable -----------------------
            defaults = dict(conn.execute(sa.text(
                "SELECT canonical_name, default_transaction_reason_id FROM bank_occurrences"
            )).fetchall())
            check(
                "a Who whose whole history used one Why gets that Why as its default",
                defaults["US Foods"] == ids["reasons"]["SUPPLIER_INVOICE_PAYMENT"],
            )
            check(
                "a Who known only from one decision still resolves to that single Why",
                defaults["Sysco"] == ids["reasons"]["PAYROLL"],
            )
            check(
                "a Who with two different Whys in its history is left explicitly incomplete",
                defaults["Ambiguous Party"] is None,
            )

            # --- historical decision snapshots ----------------------------
            decisions = conn.execute(sa.text(
                "SELECT e.what_label_snapshot, e.accounting_classification_code_snapshot, "
                "       e.accounting_classification_name_snapshot, e.accounting_statement_type_snapshot, "
                "       e.transaction_reason_name_snapshot, e.food_cost_snapshot, e.operative_snapshot, "
                "       e.deductible_snapshot, e.occurrence_name_snapshot "
                "FROM bank_transaction_explanations e "
                "JOIN financial_transactions t ON t.id = e.financial_transaction_id "
                "WHERE t.description_original = 'US FOODS INVOICE'"
            )).fetchall()
            check("the US Foods decision is still a single historical row", len(decisions) == 1)
            if decisions:
                row = decisions[0]
                check(
                    "the historical Kermali snapshot is untouched (label and Food/Oper/Deduct)",
                    row[0] == "Food Supplier" and row[5] == 1 and row[6] == 0 and row[7] == 0
                    and row[8] == "US Foods",
                )
                check(
                    "the historical decision is linked to the What migrated from its own recorded label",
                    row[1] == "LEGACY_FOOD_SUPPLIER" and row[2] == "Food Supplier",
                )
                check(
                    "no statement type is invented for a historical decision",
                    row[3] is None,
                )
                check(
                    "the Why name snapshot is backfilled from the Reason it recorded",
                    row[4] == "Supplier Invoice Payment",
                )

            unlabelled = conn.execute(sa.text(
                "SELECT e.accounting_classification_code_snapshot "
                "FROM bank_transaction_explanations e "
                "JOIN financial_transactions t ON t.id = e.financial_transaction_id "
                "WHERE t.description_original = 'MYSTERY CHARGE' ORDER BY e.id"
            )).fetchall()
            check(
                "a decision that recorded no label is left without a What, never guessed",
                all(row[0] is None for row in unlabelled),
            )

            # --- the widened status vocabulary really applies -------------
            conn.execute(sa.text(
                "UPDATE bank_transaction_explanations SET decision_status = 'HUMAN_RECLASSIFIED' "
                "WHERE id = (SELECT MIN(id) FROM bank_transaction_explanations)"
            ))
        check("the widened decision-status vocabulary accepts HUMAN_RECLASSIFIED", True)

        # --- downgrade refuses to destroy an audited reclassification -----
        refused = False
        try:
            command.downgrade(config, BEFORE_REVISION)
        except Exception as exc:  # noqa: BLE001 — the refusal is the assertion
            refused = "HUMAN_RECLASSIFIED" in str(exc)
        check("downgrade refuses to silently rewrite an audited HUMAN_RECLASSIFIED decision", refused)

        with engine.begin() as conn:
            conn.execute(sa.text(
                "UPDATE bank_transaction_explanations SET decision_status = 'HUMAN_CONFIRMED' "
                "WHERE decision_status = 'HUMAN_RECLASSIFIED'"
            ))
        command.downgrade(config, BEFORE_REVISION)

        with engine.begin() as conn:
            inspector = sa.inspect(conn)
            check(
                "downgrade removes the What table",
                "bank_accounting_classifications" not in inspector.get_table_names(),
            )
            explanation_columns = {c["name"] for c in inspector.get_columns("bank_transaction_explanations")}
            check(
                "downgrade removes only the columns this migration added",
                "accounting_classification_id" not in explanation_columns
                and "what_label_snapshot" in explanation_columns,
            )
            check(
                "downgrade preserves every historical decision row and its Kermali values",
                conn.execute(sa.text(
                    "SELECT COUNT(*) FROM bank_transaction_explanations WHERE what_label_snapshot = 'Food Supplier'"
                )).scalar_one() == 2,
            )
            check(
                "downgrade preserves every FinancialTransaction",
                conn.execute(sa.text("SELECT COUNT(*) FROM financial_transactions")).scalar_one()
                == txn_count_before,
            )

    finally:
        engine.dispose()
        os.environ.pop("ALEMBIC_DATABASE_URL_OVERRIDE", None)
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = db_path + suffix
            if os.path.exists(candidate):
                try:
                    os.remove(candidate)
                except OSError:
                    pass

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
