#!/usr/bin/env python
"""Canonical catalog additions for the WHO/WHY import
(BANK_WHO_WHY_CANONICAL_CATALOG_001, Product Owner decisions D20–D23).

Proves, on throwaway databases:

* 7460 Municipal Utilities exists after migration, under the 7400 GROUP,
  as a valid P&L POSTING WHAT with its siblings' conventions;
* the four approved WHY resolve to their approved destinations — three
  Balance Sheet destinations with NO WHAT, and one P&L WHAT;
* the data migration a7c3e9d5f2b8 is idempotent, keeps an equivalent
  pre-existing row as it is, and refuses a conflicting one clearly;
* the live canonical files and the migrated database agree, and every
  catalog validator stays clean;
* no export mapping is invented and no generic "Incoming" WHY exists;
* there is exactly one Alembic head.

Never touches AWS, RDS, the operational database, or a real bank file.
"""

from __future__ import annotations

import importlib.util
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, func, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import canonical_catalog as cc
from rfone_data_store.bank_reconciliation import why_catalog as wc
from rfone_data_store.database import (
    cleanup_disposable_test_database_url,
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)

HERE = Path(__file__).resolve().parent
REVISION = "a7c3e9d5f2b8"
PREVIOUS = "b9e4c2a7d5f3"
MIGRATION = HERE / "migrations" / "versions" / f"{REVISION}_add_municipal_utilities_and_settlement_whys.py"

APPROVED = {
    "MERCHANT_CARD_SETTLEMENT": ("1210", "BALANCE_SHEET"),
    "GIFT_CARD_SETTLEMENT": ("2800", "BALANCE_SHEET"),
    "CASH_CHECK_DEPOSIT": ("1130", "BALANCE_SHEET"),
    "MUNICIPAL_UTILITIES": ("7460", "PROFIT_LOSS"),
}


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, ALEMBIC_DATABASE_URL_OVERRIDE=url, RFONE_DATABASE_URL=url)
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=str(HERE), env=env,
                          capture_output=True, text=True)


def _scratch_db(label: str) -> tuple[str, str]:
    fd, path = tempfile.mkstemp(suffix=".db", prefix=f"rfone_test_catalog_{label}_")
    os.close(fd)
    os.remove(path)
    return path, "sqlite:///" + path.replace("\\", "/")


def _run_revision_again(url: str) -> None:
    """Execute a7c3e9d5f2b8.upgrade() a second time on a database already at head."""
    spec = importlib.util.spec_from_file_location("rev_a7c3", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                module.upgrade()
    finally:
        engine.dispose()


def _snapshot(url: str) -> tuple:
    connection = sqlite3.connect(url[len("sqlite:///"):])
    try:
        return (
            connection.execute("SELECT id, code, name, statement_type, parent_id, node_type, normal_balance, "
                               "is_contra, review_sensitive, active, description FROM "
                               "bank_accounting_classifications ORDER BY id").fetchall(),
            connection.execute("SELECT id, code, name, description, status, accounting_classification_id, "
                               "reason_group_id FROM bank_transaction_reasons ORDER BY id").fetchall(),
        )
    finally:
        connection.close()


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
            print(f"  PASS  {description}")
        else:
            failed.append(description)
            print(f"  FAIL  {description}" + (f" ({detail})" if detail else ""))

    url = resolve_test_database_url("who_why_canonical_catalog")
    print(f"Database: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as s:
            accounts = {a.code: a for a in s.scalars(select(m.BankAccountingClassification))}
            a7460 = accounts.get("7460")
            # ---------------------------------------------------------- 1-3
            check("1. 7460 exists after migration", a7460 is not None)
            parent = s.get(m.BankAccountingClassification, a7460.parent_id) if a7460 else None
            check("2. 7460 sits under 7400 Utilities", parent is not None and parent.code == "7400")
            siblings = [accounts[c] for c in ("7410", "7420", "7430", "7440", "7450")]
            check("3. 7460 is a valid P&L POSTING WHAT with its siblings' conventions",
                  a7460 is not None and a7460.statement_type == "PROFIT_LOSS" and a7460.node_type == "POSTING"
                  and a7460.normal_balance == "DEBIT" and not a7460.is_contra and not a7460.review_sensitive
                  and a7460.active and a7460.is_what and a7460 in cc.what_catalog(s)
                  and all((x.statement_type, x.node_type, x.normal_balance, bool(x.is_contra),
                           bool(x.review_sensitive)) == ("PROFIT_LOSS", "POSTING", "DEBIT", False, False)
                          for x in siblings))
            check("3b. 7400 is still the Utilities GROUP and is not a WHAT",
                  accounts["7400"].node_type == "GROUP" and accounts["7400"].name == "Utilities"
                  and not accounts["7400"].is_what)
            check("3c. 7460 is named 'Municipal Utilities'", a7460 is not None and a7460.name == "Municipal Utilities")

            # ---------------------------------------------------------- 4-7
            reasons = {r.code: r for r in s.scalars(select(m.BankTransactionReason))}
            for number, (code, (account, statement)) in zip((4, 5, 6, 7), APPROVED.items()):
                reason = reasons.get(code)
                dest = reason.accounting_classification if reason else None
                if statement == "BALANCE_SHEET":
                    ok = (dest is not None and dest.code == account and reason.what is None
                          and reason.accounting_destination is dest and not reason.is_profit_loss)
                else:
                    ok = (dest is not None and dest.code == account and reason.what is dest
                          and reason.accounting_destination is None and reason.is_profit_loss)
                check(f"{number}. {code} -> {account} ({'Balance Sheet, no WHAT' if statement == 'BALANCE_SHEET' else 'P&L WHAT'})",
                      ok and reason.status == "ACTIVE" and reason.reason_group_id is not None,
                      detail=f"{dest.code if dest else None}")
            groups = {r.code: r.reason_group.code for r in reasons.values() if r.reason_group}
            check("7b. the three settlements are Money Movements, Municipal Utilities is Utilities",
                  [groups.get(c) for c in APPROVED] == ["MONEY_MOVEMENT"] * 3 + ["UTILITIES"])
            check("7c. no generic 'Incoming' WHY exists",
                  not any("INCOMING" in c or r.name.strip().casefold() == "incoming" for c, r in reasons.items()))
            check("7d. no Food Cost / Operative / Deductable export mapping is invented for the four WHY",
                  not any(reasons[c].export_mapping for c in APPROVED))

            # ---------------------------------------------------------- 10
            check("10. canonical catalog validators stay clean",
                  not wc.catalog_problems(s) and not cc.validate_hierarchy(s)
                  and not cc.semantic_problems(s) and not cc.what_catalog_problems(s),
                  detail="; ".join((wc.catalog_problems(s) + cc.validate_hierarchy(s)
                                    + cc.semantic_problems(s) + cc.what_catalog_problems(s))[:3]))
            account_seed = cc.seed(s)
            why_seed = wc.seed(s)
            s.commit()
            check("10b. the live canonical files agree with the migrated database "
                  "(seeding creates nothing and finds no conflict)",
                  not account_seed.created and not account_seed.conflicts
                  and not why_seed.reasons_created and not why_seed.conflicts,
                  detail=f"{account_seed.created} {why_seed.reasons_created} {why_seed.conflicts}")
            check("10c. the catalogs now hold 137 accounts and 81 WHY",
                  len(cc.catalog_rows()) == 137 and len(wc.catalog_rows()) == 81
                  and s.scalar(select(func.count(m.BankAccountingClassification.id))) == 137
                  and s.scalar(select(func.count(m.BankTransactionReason.id))) == 81)
    finally:
        engine.dispose()

    # -------------------------------------------------------------- 8
    before = _snapshot(url)
    _run_revision_again(url)
    check("8. running a7c3e9d5f2b8 again changes nothing (idempotent)", _snapshot(url) == before)

    # -------------------------------------------------------------- 9 / equivalence
    path, scratch = _scratch_db("conflict_why")
    try:
        result = _alembic(scratch, "upgrade", PREVIOUS)
        connection = sqlite3.connect(path)
        bank_1110 = connection.execute("SELECT id FROM bank_accounting_classifications WHERE code='1110'").fetchone()[0]
        connection.execute("INSERT INTO bank_transaction_reasons (code, name, status, accounting_classification_id) "
                           "VALUES ('MERCHANT_CARD_SETTLEMENT', 'Something else', 'ACTIVE', ?)", (bank_1110,))
        connection.commit()
        connection.close()
        result = _alembic(scratch, "upgrade", "head")
        connection = sqlite3.connect(path)
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        connection.close()
        check("9. a conflicting pre-existing WHY code fails clearly and is not re-pointed",
              result.returncode != 0 and "never silently re-pointed" in (result.stderr + result.stdout)
              and "MERCHANT_CARD_SETTLEMENT" in (result.stderr + result.stdout) and revision == PREVIOUS,
              detail=f"rc={result.returncode} revision={revision}")
    finally:
        os.path.exists(path) and os.remove(path)

    path, scratch = _scratch_db("conflict_account")
    try:
        _alembic(scratch, "upgrade", PREVIOUS)
        connection = sqlite3.connect(path)
        parent = connection.execute("SELECT id FROM bank_accounting_classifications WHERE code='7400'").fetchone()[0]
        connection.execute("INSERT INTO bank_accounting_classifications (code, name, statement_type, parent_id, "
                           "active, node_type, is_contra, review_sensitive, normal_balance) VALUES "
                           "('7460', 'Something Else', 'PROFIT_LOSS', ?, 1, 'POSTING', 0, 0, 'DEBIT')", (parent,))
        connection.commit()
        connection.close()
        result = _alembic(scratch, "upgrade", "head")
        check("9b. a conflicting pre-existing 7460 fails clearly and is not redefined",
              result.returncode != 0 and "never silently redefined" in (result.stderr + result.stdout),
              detail=f"rc={result.returncode}")
    finally:
        os.path.exists(path) and os.remove(path)

    path, scratch = _scratch_db("equivalent")
    try:
        _alembic(scratch, "upgrade", PREVIOUS)
        connection = sqlite3.connect(path)
        parent = connection.execute("SELECT id FROM bank_accounting_classifications WHERE code='7400'").fetchone()[0]
        connection.execute("INSERT INTO bank_accounting_classifications (code, name, statement_type, parent_id, "
                           "description, active, node_type, is_contra, review_sensitive, normal_balance) VALUES "
                           "('7460', 'Municipal Utilities', 'PROFIT_LOSS', ?, 'created earlier by an approved import', "
                           "1, 'POSTING', 0, 0, 'DEBIT')", (parent,))
        a7460 = connection.execute("SELECT id FROM bank_accounting_classifications WHERE code='7460'").fetchone()[0]
        group = connection.execute("SELECT id FROM bank_reason_groups WHERE code='UTILITIES'").fetchone()[0]
        connection.execute("INSERT INTO bank_transaction_reasons (code, name, description, status, "
                           "accounting_classification_id, reason_group_id) VALUES ('MUNICIPAL_UTILITIES', "
                           "'Municipal Utilities', 'created earlier by an approved import', 'ACTIVE', ?, ?)",
                           (a7460, group))
        connection.commit()
        connection.close()
        result = _alembic(scratch, "upgrade", "head")
        connection = sqlite3.connect(path)
        kept = connection.execute("SELECT description FROM bank_accounting_classifications WHERE code='7460'").fetchone()[0]
        kept_why = connection.execute("SELECT description, accounting_classification_id FROM bank_transaction_reasons "
                                      "WHERE code='MUNICIPAL_UTILITIES'").fetchone()
        counts = (connection.execute("SELECT count(*) FROM bank_accounting_classifications WHERE code='7460'").fetchone()[0],
                  connection.execute("SELECT count(*) FROM bank_transaction_reasons WHERE code IN "
                                     "('MERCHANT_CARD_SETTLEMENT','GIFT_CARD_SETTLEMENT','CASH_CHECK_DEPOSIT',"
                                     "'MUNICIPAL_UTILITIES')").fetchone()[0])
        connection.close()
        check("9c. an equivalent pre-existing 7460 / WHY is kept exactly as it was, and the rest is added",
              result.returncode == 0 and kept == "created earlier by an approved import"
              and kept_why == ("created earlier by an approved import", a7460) and counts == (1, 4),
              detail=f"rc={result.returncode} {counts} {result.stderr[-300:]}")

        result = _alembic(scratch, "downgrade", PREVIOUS)
        connection = sqlite3.connect(path)
        left = connection.execute("SELECT count(*) FROM bank_transaction_reasons WHERE code IN "
                                  "('MERCHANT_CARD_SETTLEMENT','GIFT_CARD_SETTLEMENT','CASH_CHECK_DEPOSIT',"
                                  "'MUNICIPAL_UTILITIES')").fetchone()[0]
        connection.close()
        check("9d. downgrade removes the unreferenced rows", result.returncode == 0 and left == 0,
              detail=f"rc={result.returncode} left={left}")
    finally:
        os.path.exists(path) and os.remove(path)

    # -------------------------------------------------------------- 11
    heads = ScriptDirectory.from_config(Config(str(HERE / "alembic.ini"))).get_heads()
    check("11. exactly one Alembic head, and it is a7c3e9d5f2b8", heads == [REVISION], detail=str(heads))

    cleanup_disposable_test_database_url(url)
    print()
    print(f"{len(passed)} passed, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
