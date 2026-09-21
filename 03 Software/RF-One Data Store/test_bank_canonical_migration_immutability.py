#!/usr/bin/env python
"""Migration immutability
(BANK_CANONICAL_MIGRATION_IMMUTABILITY_001).

The canonical accounting revisions used to read the LIVE catalog
definition at run time. That file is actively maintained — it has already
grown from 134 accounts to 136 — so the same revision chain produced a
different history depending on when it was run. Each revision now carries
its own frozen input.

This suite proves the separation holds, structurally and functionally:

* no canonical-accounting revision resolves a path into the live catalog
  package, and each reads only its own frozen snapshot;
* the chain still demonstrates 134 -> 134 with semantics -> 136;
* EDITING THE LIVE CSV DOES NOT CHANGE WHAT THE MIGRATIONS DO. The proof
  is a real one: the live CSV is temporarily replaced by a mutated
  version, a database is built from `base` to `head` against it, and the
  result is compared account by account with the unmutated run. The
  original bytes are restored in a `finally` and verified by digest.

Never touches AWS, RDS, a production database, or a real bank file.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import io
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import canonical_catalog as cc
from rfone_data_store.bank_reconciliation import what_catalog_import as wci
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    run_migrations_to_head,
)

PL = wci.PROFIT_LOSS
BS = wci.BALANCE_SHEET

HERE = Path(__file__).resolve().parent
VERSIONS = HERE / "migrations" / "versions"
MIGRATION_DATA = HERE / "migrations" / "migration_data"
LIVE_CATALOG = cc.CATALOG_PATH

# The revisions that seed or reshape canonical accounts.
CANONICAL_REVISIONS = {
    "b8d3f1a72c64": "b8d3f1a72c64_seed_canonical_restaurant_accounting_catalog.py",
    "c5f8b2e91a47": "c5f8b2e91a47_add_canonical_account_semantics.py",
    "d7a4c9e2f318": "d7a4c9e2f318_correct_equity_draws_and_split_asset_disposal.py",
}

# What each revision must leave behind, in account count.
EXPECTED_AT_REVISION = {
    "b8d3f1a72c64": 134,
    "c5f8b2e91a47": 134,
    "d7a4c9e2f318": 136,
}

FINAL_SEMANTICS = {
    "3400": (BS, "POSTING", cc.DEBIT, True, False),
    "8400": (PL, "GROUP", cc.CREDIT, False, False),
    "8410": (PL, "POSTING", cc.CREDIT, False, False),
    "8420": (PL, "POSTING", cc.DEBIT, False, False),
}


def _code_without_docstrings(path: Path) -> str:
    """The revision's executable source, with every docstring removed.

    A revision may DISCUSS the live catalog in prose — several explain why
    they no longer read it — and that prose must not be mistaken for a
    dependency on it."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            spans.append((first.lineno, first.end_lineno))
    lines = source.splitlines()
    kept = [
        line for index, line in enumerate(lines, start=1)
        if not any(start <= index <= end for start, end in spans)
    ]
    return "\n".join(kept)


def _account_fingerprint(session) -> list[tuple]:
    """Everything about the canonical accounts that a migration decides,
    ordered so two databases compare exactly."""
    rows = session.query(m.BankAccountingClassification).all()
    by_id = {row.id: row.code for row in rows}
    return sorted(
        (
            row.code, row.name, row.statement_type,
            by_id.get(row.parent_id), row.node_type, row.normal_balance,
            bool(row.is_contra), bool(row.review_sensitive), bool(row.active),
        )
        for row in rows
    )


def _build_and_fingerprint(label: str) -> list[tuple]:
    """A database created from `base`, migrated to `head`, fingerprinted."""
    handle, path = tempfile.mkstemp(prefix=f"rfone_immutability_{label}_", suffix=".db")
    os.close(handle)
    os.unlink(path)
    url = "sqlite:///" + path.replace("\\", "/")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as session:
            return _account_fingerprint(session)
    finally:
        engine.dispose()


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
        else:
            failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    print(f"Live canonical catalog: {LIVE_CATALOG.name}")
    print(f"Frozen migration data : {MIGRATION_DATA}")

    # =================================================================
    # 1. No historical revision reads the live canonical definition
    # =================================================================
    for revision, file_name in CANONICAL_REVISIONS.items():
        code = _code_without_docstrings(VERSIONS / file_name)
        check(
            f"1. {revision} does not name the live canonical catalog in its code",
            "RFONE_RESTAURANT_COA_V1.csv" not in code
            and f'"{LIVE_CATALOG.parent.name}"' not in code
            and f"'{LIVE_CATALOG.parent.name}'" not in code,
            detail=file_name,
        )
        check(
            f"1b. {revision} does not reach into the package holding it",
            "bank_reconciliation" not in code and "rfone_data_store" not in code,
            detail=file_name,
        )

    all_versions = sorted(VERSIONS.glob("*.py"))
    strays = [
        path.name for path in all_versions
        if "RFONE_RESTAURANT_COA_V1.csv" in _code_without_docstrings(path)
    ]
    check(
        "1c. NO Alembic revision at all reads the live canonical catalog",
        not strays, detail=str(strays),
    )

    # =================================================================
    # Each revision's frozen input is present, and is not the live file
    # =================================================================
    snapshots = sorted(path.name for path in MIGRATION_DATA.glob("*.csv"))
    check(
        "1d. the two snapshot revisions have a frozen input each, named after them",
        snapshots == [
            "b8d3f1a72c64_rfone_restaurant_coa_v1.csv",
            "c5f8b2e91a47_account_semantics.csv",
        ],
        detail=str(snapshots),
    )
    for name in snapshots:
        path = MIGRATION_DATA / name
        rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
        check(
            f"1e. {name} is frozen at the historical 134 accounts",
            len(rows) == 134, detail=f"{len(rows)} rows",
        )
        check(
            f"1f. {name} is a different file from the live canonical catalog",
            path.resolve() != LIVE_CATALOG.resolve()
            and path.read_bytes() != LIVE_CATALOG.read_bytes(),
        )
    check(
        "1g. d7a4c9e2f318 carries its four rows inline rather than adding a snapshot",
        "_CORRECTIONS" in (VERSIONS / CANONICAL_REVISIONS["d7a4c9e2f318"]).read_text(
            encoding="utf-8"
        ),
    )
    check(
        "1h. migration_data states its own immutability rule",
        "never edited" in (MIGRATION_DATA / "README.md").read_text(encoding="utf-8").lower(),
    )

    # =================================================================
    # 2-5. The chain reproduces the intended history, step by step
    # =================================================================
    handle, chain_path = tempfile.mkstemp(prefix="rfone_immutability_chain_", suffix=".db")
    os.close(handle)
    os.unlink(chain_path)
    chain_url = "sqlite:///" + chain_path.replace("\\", "/")
    environment = dict(os.environ, RFONE_DATABASE_URL=chain_url)

    def upgrade_to(revision: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", revision],
            cwd=str(HERE), env=environment, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def account_count() -> int:
        # Raw SQL, not the ORM: partway through the chain the table does not
        # yet have the columns today's model declares, and counting rows at a
        # historical revision must not depend on the current model.
        connection = sqlite3.connect(chain_path)
        try:
            return connection.execute(
                "SELECT count(*) FROM bank_accounting_classifications"
            ).fetchone()[0]
        finally:
            connection.close()

    labels = {
        "b8d3f1a72c64": "2. b8d3f1a72c64 alone produces exactly 134 historical accounts",
        "c5f8b2e91a47": "3. through c5f8b2e91a47 the catalog is still exactly 134",
        "d7a4c9e2f318": "4. through d7a4c9e2f318 the catalog is exactly 136",
    }
    for revision, expected in EXPECTED_AT_REVISION.items():
        upgrade_to(revision)
        found = account_count()
        check(labels[revision], found == expected, detail=f"{found} accounts")

    check(
        "4b. the chain itself demonstrates 134 -> 134 with semantics -> 136, so the "
        "history does not depend on today's catalog holding 136",
        EXPECTED_AT_REVISION["b8d3f1a72c64"] == 134
        and len(cc.catalog_rows()) == 136,
        detail=f"live catalog has {len(cc.catalog_rows())} accounts",
    )

    upgrade_to("head")
    engine = create_configured_engine(chain_url)
    try:
        with create_session_factory(engine)() as session:
            by_code = {
                row.code: row
                for row in session.query(m.BankAccountingClassification).all()
            }
            for code, expected in FINAL_SEMANTICS.items():
                row = by_code.get(code)
                actual = None if row is None else (
                    row.statement_type, row.node_type, row.normal_balance,
                    bool(row.is_contra), bool(row.review_sensitive),
                )
                check(
                    f"5. {code} ends the chain as {expected}",
                    actual == expected, detail=str(actual),
                )

            # =========================================================
            # 6. The runtime seed agrees with the migrated database
            # =========================================================
            outcome = cc.seed(session)
            session.commit()
            check(
                "6. the current canonical seed against the migrated database creates 0 "
                "accounts and reports 136 unchanged",
                not outcome.created and len(outcome.unchanged) == 136
                and not outcome.conflicts,
                detail=f"created={len(outcome.created)} unchanged={len(outcome.unchanged)}",
            )
            check(
                "6b. and the database validates against the current canonical definition",
                not cc.validate_hierarchy(session) and not cc.semantic_problems(session),
                detail="; ".join((cc.validate_hierarchy(session)
                                  + cc.semantic_problems(session))[:3]),
            )
    finally:
        engine.dispose()

    # =================================================================
    # 8. A fresh base -> head database matches the approved final state
    # =================================================================
    reference = _build_and_fingerprint("reference")
    check(
        "8. a completely fresh base -> head database holds the 136 approved accounts",
        len(reference) == 136,
        detail=f"{len(reference)} accounts",
    )
    check(
        "8b. and its canonical semantics are the approved final state",
        {
            row[0]: (row[2], row[4], row[5], row[6], row[7])
            for row in reference if row[0] in FINAL_SEMANTICS
        } == FINAL_SEMANTICS,
    )
    check(
        "8c. fresh and chain-upgraded databases are identical account by account",
        reference == _build_and_fingerprint("again"),
    )

    # =================================================================
    # 7. Editing the live CSV cannot change any historical migration
    # =================================================================
    original_bytes = LIVE_CATALOG.read_bytes()
    original_digest = hashlib.sha256(original_bytes).hexdigest()
    mutated = original_bytes.replace(
        b"PROFIT_LOSS,8410,Gain on Asset Disposal,8400,2,POSTING,CREDIT,FALSE,FALSE",
        b"PROFIT_LOSS,8410,Gain on Asset Disposal,8400,2,GROUP,DEBIT,TRUE,TRUE",
    ) + b"PROFIT_LOSS,9999,Invented Later,8000,1,POSTING,DEBIT,FALSE,FALSE\n"
    check(
        "7a. the mutation actually changes the live catalog (otherwise the proof is empty)",
        mutated != original_bytes,
    )

    mutated_fingerprint = None
    try:
        LIVE_CATALOG.write_bytes(mutated)
        mutated_fingerprint = _build_and_fingerprint("mutated")
    finally:
        LIVE_CATALOG.write_bytes(original_bytes)

    check(
        "7b. the live canonical catalog was restored byte for byte",
        hashlib.sha256(LIVE_CATALOG.read_bytes()).hexdigest() == original_digest,
        detail=hashlib.sha256(LIVE_CATALOG.read_bytes()).hexdigest()[:16],
    )
    check(
        "7c. a database migrated while the live catalog said something else is "
        "IDENTICAL — no historical migration read it",
        mutated_fingerprint == reference,
        detail="fingerprints differ" if mutated_fingerprint != reference else "",
    )
    check(
        "7d. in particular the invented 9999 account never reached the database",
        mutated_fingerprint is not None
        and not any(row[0] == "9999" for row in mutated_fingerprint),
    )
    check(
        "7e. and 8410 still carries the approved semantics, not the mutated ones",
        mutated_fingerprint is not None
        and next(
            (row[4], row[5], row[6], row[7])
            for row in mutated_fingerprint if row[0] == "8410"
        ) == ("POSTING", cc.CREDIT, False, False),
    )

    # =================================================================
    # 9. Downgrade / re-upgrade still works
    # =================================================================
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "b8d3f1a72c64"],
        cwd=str(HERE), env=environment, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    after_downgrade = account_count()
    check(
        "9a. downgrading back to b8d3f1a72c64 returns the historical 134 accounts",
        after_downgrade == 134, detail=f"{after_downgrade} accounts",
    )
    upgrade_to("head")
    check(
        "9b. re-upgrading to head returns exactly the approved final state",
        account_count() == 136,
    )
    engine = create_configured_engine(chain_url)
    try:
        with create_session_factory(engine)() as session:
            check(
                "9c. and the re-upgraded database is identical to a fresh one",
                _account_fingerprint(session) == reference,
            )
    finally:
        engine.dispose()

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
