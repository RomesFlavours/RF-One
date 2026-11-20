#!/usr/bin/env python
"""Migration test for BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001
(revision `a4e2f8c15b73`).

Two paths, both required by the task:

1. **From an EXISTING database** — migrate to the revision before this one,
   fill it with synthetic legacy Bank data (instruments, batches, raw rows,
   transactions carrying human duplicate decisions), then apply this
   migration and assert that nothing is lost, nothing is rewritten, and the
   new columns are left NULL so an un-recomputed database keeps behaving
   exactly as it did.
2. **From an EMPTY database** — migrate straight to head and assert the new
   tables, columns, constraints and partial indexes all exist.

Also asserts the downgrade is clean and the upgrade is re-appliable.

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

BEFORE_REVISION = "f1c7a94d6e02"
THIS_REVISION = "a4e2f8c15b73"


def _alembic_config(database_url: str) -> Config:
    config = Config(os.path.join(BASE_DIR, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(BASE_DIR, "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = database_url
    return config


def _new_db() -> tuple[str, str]:
    fd, path = tempfile.mkstemp(suffix=".db", prefix="rfone_card_dedup_migration_")
    os.close(fd)
    os.remove(path)
    return path, f"sqlite:///{path.replace(os.sep, '/')}"


def _cleanup(path: str) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = path + suffix
        if os.path.exists(candidate):
            try:
                os.remove(candidate)
            except OSError:
                pass


def _seed_legacy(engine: sa.Engine) -> dict:
    """Synthetic pre-migration data, written with raw SQL against the OLD
    schema on purpose — `models.py` already describes the new one."""
    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO legal_entities (legal_name, status) VALUES ('Legacy LLC', 'ACTIVE')"
        ))
        entity_id = conn.execute(sa.text("SELECT id FROM legal_entities")).scalar_one()

        for name, kind, last_four in (
            ("Legacy Checking", "BANK_ACCOUNT", "0214"),
            ("Legacy Card", "CREDIT_CARD", "1057"),
        ):
            conn.execute(
                sa.text(
                    "INSERT INTO payment_instruments "
                    "(legal_entity_id, instrument_type, display_name, institution, last_four, status) "
                    "VALUES (:e, :k, :n, 'CHASE', :l, 'ACTIVE')"
                ),
                {"e": entity_id, "k": kind, "n": name, "l": last_four},
            )
        instruments = dict(conn.execute(
            sa.text("SELECT display_name, id FROM payment_instruments")
        ).fetchall())

        conn.execute(
            sa.text(
                "INSERT INTO bank_import_batches "
                "(detected_format, payment_instrument_id, original_file_name, raw_file_bytes, "
                " sha256, row_count, status) "
                "VALUES ('CHASE_CREDIT_CARD_WITH_CARD', :i, 'legacy.csv', :b, 'legacy-sha', 2, 'NORMALIZED')"
            ),
            {"i": instruments["Legacy Card"], "b": b"Card,Transaction Date\n1057,05/05/2026\n"},
        )
        batch_id = conn.execute(sa.text("SELECT id FROM bank_import_batches")).scalar_one()

        specs = [
            ("US FOODS INC #4821", -41250, "NONE"),
            ("US FOODS INC #4821", -41250, "CONFIRMED_DISTINCT"),
            ("SYSCO CORP #99", -10000, "CONFIRMED_DUPLICATE"),
        ]
        for row_number, (description, amount, duplicate_status) in enumerate(specs, start=1):
            conn.execute(
                sa.text(
                    "INSERT INTO financial_transactions "
                    "(payment_instrument_id, bank_source, posting_date, description_original, "
                    " description_normalized, amount_minor, classification, status, "
                    " import_batch_id, source_row_number, duplicate_status, review_status) "
                    "VALUES (:i, 'CHASE_CREDIT_CARD_WITH_CARD', '2026-05-05', :d, :d, :a, "
                    " 'UNKNOWN', 'COMPLETED', :b, :r, :ds, 'REQUIRES_REVIEW')"
                ),
                {
                    "i": instruments["Legacy Card"], "d": description, "a": amount,
                    "b": batch_id, "r": row_number, "ds": duplicate_status,
                },
            )
            conn.execute(
                sa.text(
                    "INSERT INTO raw_bank_transactions "
                    "(import_batch_id, row_number, raw_fields, row_fingerprint, parse_status) "
                    "VALUES (:b, :r, :f, :fp, 'PARSED')"
                ),
                {
                    "b": batch_id, "r": row_number,
                    "f": '{"Description": "%s"}' % description,
                    "fp": f"fp-{row_number}",
                },
            )
    return {"batch_id": batch_id, "instruments": instruments}


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
        else:
            failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    # =====================================================================
    # 25a. Migration from an EXISTING database
    # =====================================================================
    path, url = _new_db()
    config = _alembic_config(url)
    engine = sa.create_engine(url)
    try:
        command.upgrade(config, BEFORE_REVISION)
        _seed_legacy(engine)

        with engine.begin() as conn:
            before = {
                "transactions": conn.execute(
                    sa.text("SELECT COUNT(*) FROM financial_transactions")
                ).scalar_one(),
                "raw": conn.execute(
                    sa.text("SELECT COUNT(*) FROM raw_bank_transactions")
                ).scalar_one(),
                "raw_bytes": conn.execute(
                    sa.text("SELECT raw_file_bytes FROM bank_import_batches")
                ).scalar_one(),
                "raw_fields": conn.execute(
                    sa.text("SELECT row_number, raw_fields FROM raw_bank_transactions ORDER BY row_number")
                ).fetchall(),
                "duplicate_status": conn.execute(
                    sa.text("SELECT id, duplicate_status FROM financial_transactions ORDER BY id")
                ).fetchall(),
                "amounts": conn.execute(
                    sa.text("SELECT id, amount_minor, posting_date, description_original "
                            "FROM financial_transactions ORDER BY id")
                ).fetchall(),
            }

        command.upgrade(config, THIS_REVISION)

        with engine.begin() as conn:
            check(
                "25a. no transaction and no raw row is created or deleted by the migration",
                conn.execute(sa.text("SELECT COUNT(*) FROM financial_transactions")).scalar_one()
                == before["transactions"]
                and conn.execute(sa.text("SELECT COUNT(*) FROM raw_bank_transactions")).scalar_one()
                == before["raw"],
            )
            check(
                "the raw preservation layer is byte-identical",
                conn.execute(sa.text("SELECT raw_file_bytes FROM bank_import_batches")).scalar_one()
                == before["raw_bytes"]
                and conn.execute(sa.text(
                    "SELECT row_number, raw_fields FROM raw_bank_transactions ORDER BY row_number"
                )).fetchall() == before["raw_fields"],
            )
            check(
                "existing human duplicate decisions are untouched",
                conn.execute(sa.text(
                    "SELECT id, duplicate_status FROM financial_transactions ORDER BY id"
                )).fetchall() == before["duplicate_status"],
            )
            check(
                "every amount, date and description survives unchanged",
                conn.execute(sa.text(
                    "SELECT id, amount_minor, posting_date, description_original "
                    "FROM financial_transactions ORDER BY id"
                )).fetchall() == before["amounts"],
            )
            new_values = conn.execute(sa.text(
                "SELECT accounting_status, accounting_dedup_key, accounting_settlement_account_id, "
                "       payee_normalized, accounting_canonical_transaction_id "
                "FROM financial_transactions"
            )).fetchall()
            check(
                "the new columns are left NULL — nothing is backfilled on a guess",
                all(all(value is None for value in row) for row in new_values),
                detail=repr(new_values),
            )
            check(
                "the two new tables exist and are empty — no association is invented",
                conn.execute(
                    sa.text("SELECT COUNT(*) FROM bank_card_settlement_accounts")
                ).scalar_one() == 0
                and conn.execute(
                    sa.text("SELECT COUNT(*) FROM bank_card_holder_assignments")
                ).scalar_one() == 0,
            )

        # An un-recomputed database keeps exporting exactly what it did.
        sys.path.insert(0, BASE_DIR)
        os.environ["RFONE_DATABASE_URL"] = url
        from rfone_data_store.bank_reconciliation import accounting_dedup  # noqa: E402

        with engine.begin() as conn:
            statuses = [
                r[0] for r in conn.execute(
                    sa.text("SELECT accounting_status FROM financial_transactions")
                ).fetchall()
            ]
        check(
            "a NULL accounting_status means 'not yet recomputed' and stays accounting-visible",
            all(status is None for status in statuses)
            and accounting_dedup.ACCOUNTING_VISIBLE_STATUSES == (accounting_dedup.CANONICAL,),
        )

        # Downgrade / re-upgrade round trip on the SAME populated database.
        command.downgrade(config, BEFORE_REVISION)
        with engine.begin() as conn:
            inspector = sa.inspect(conn)
            columns = {c["name"] for c in inspector.get_columns("financial_transactions")}
            check(
                "downgrade removes only what this migration added",
                "accounting_status" not in columns
                and "duplicate_status" in columns
                and "bank_card_settlement_accounts" not in inspector.get_table_names()
                and "bank_card_holder_assignments" not in inspector.get_table_names(),
            )
            check(
                "downgrade preserves every transaction and raw row",
                conn.execute(sa.text("SELECT COUNT(*) FROM financial_transactions")).scalar_one()
                == before["transactions"]
                and conn.execute(sa.text("SELECT COUNT(*) FROM raw_bank_transactions")).scalar_one()
                == before["raw"],
            )
            check(
                "downgrade preserves the human duplicate decisions",
                conn.execute(sa.text(
                    "SELECT id, duplicate_status FROM financial_transactions ORDER BY id"
                )).fetchall() == before["duplicate_status"],
            )
        command.upgrade(config, THIS_REVISION)
        with engine.begin() as conn:
            check(
                "the migration is re-appliable after a downgrade",
                "accounting_status" in {
                    c["name"] for c in sa.inspect(conn).get_columns("financial_transactions")
                },
            )
    finally:
        engine.dispose()
        _cleanup(path)

    # =====================================================================
    # 25b. Migration from an EMPTY database
    # =====================================================================
    path, url = _new_db()
    config = _alembic_config(url)
    engine = sa.create_engine(url)
    try:
        command.upgrade(config, "head")
        with engine.begin() as conn:
            inspector = sa.inspect(conn)
            tables = set(inspector.get_table_names())
            check(
                "25b. an empty database migrates straight to head with both new tables",
                "bank_card_settlement_accounts" in tables
                and "bank_card_holder_assignments" in tables,
            )
            columns = {c["name"] for c in inspector.get_columns("financial_transactions")}
            check(
                "every accounting-deduplication column exists",
                {
                    "payee_normalized", "payee_normalization_version", "accounting_dedup_key",
                    "accounting_status", "accounting_canonical_transaction_id",
                    "accounting_dedup_reason", "accounting_settlement_account_id",
                }.issubset(columns),
            )
            indexes = {
                r[0] for r in conn.execute(
                    sa.text("SELECT name FROM sqlite_master WHERE type='index'")
                ).fetchall()
            }
            check(
                "the one-open-assignment partial indexes exist for both new tables",
                "ux_bcsa_one_open_per_card" in indexes and "ux_bcha_one_open_per_card" in indexes,
            )

            # The partial index must allow history (a closed row beside an open
            # one) and refuse two open rows.
            conn.execute(sa.text(
                "INSERT INTO legal_entities (legal_name, status) VALUES ('Empty LLC', 'ACTIVE')"
            ))
            conn.execute(sa.text(
                "INSERT INTO payment_instruments (instrument_type, display_name, status) "
                "VALUES ('BANK_ACCOUNT', 'Acct', 'ACTIVE'), ('CREDIT_CARD', 'Card', 'ACTIVE')"
            ))
            acct_id, card_id = [
                r[0] for r in conn.execute(
                    sa.text("SELECT id FROM payment_instruments ORDER BY id")
                ).fetchall()
            ]
            conn.execute(
                sa.text(
                    "INSERT INTO bank_card_settlement_accounts "
                    "(credit_card_payment_instrument_id, settlement_bank_account_id, valid_from, valid_to) "
                    "VALUES (:c, :a, '2025-01-01', '2026-01-01'), (:c, :a, '2026-01-01', NULL)"
                ),
                {"c": card_id, "a": acct_id},
            )
        check("a closed period may coexist with an open one (real history is allowed)", True)

        second_open_refused = False
        try:
            with engine.begin() as conn:
                conn.execute(
                    sa.text(
                        "INSERT INTO bank_card_settlement_accounts "
                        "(credit_card_payment_instrument_id, settlement_bank_account_id, valid_from) "
                        "VALUES (:c, :a, '2026-06-01')"
                    ),
                    {"c": card_id, "a": acct_id},
                )
        except Exception:  # noqa: BLE001 — the refusal IS the assertion
            second_open_refused = True
        check(
            "a SECOND open settlement assignment for the same card is refused by the database",
            second_open_refused,
        )

        self_settlement_refused = False
        try:
            with engine.begin() as conn:
                conn.execute(
                    sa.text(
                        "INSERT INTO bank_card_settlement_accounts "
                        "(credit_card_payment_instrument_id, settlement_bank_account_id, valid_from) "
                        "VALUES (:c, :c, '2027-01-01')"
                    ),
                    {"c": card_id},
                )
        except Exception:  # noqa: BLE001
            self_settlement_refused = True
        check(
            "a card settling to itself is refused by the database",
            self_settlement_refused,
        )
    finally:
        engine.dispose()
        _cleanup(path)
        os.environ.pop("ALEMBIC_DATABASE_URL_OVERRIDE", None)

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
