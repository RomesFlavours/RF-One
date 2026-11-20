#!/usr/bin/env python
"""Migrate the local Bank Reconciliation dataset (SQLite) to AWS PostgreSQL
(BANK_AWS_DATA_MIGRATION_DRY_RUN_001).

PREVIEW BY DEFAULT. Nothing is written unless `--apply` is given.

    # preview against the real target (read-only connection)
    python migrate_bank_to_postgres.py --target live --legal-entity-map 1=1,3=2,2=NEW
    # apply to a disposable database on the same RDS instance
    python migrate_bank_to_postgres.py --target rfone_pgval_20260925_x --legal-entity-map 1=1,3=2,2=NEW --apply
    # apply to the LIVE database: all three flags are required
    python migrate_bank_to_postgres.py --target live --legal-entity-map 1=1,3=2,2=NEW --apply --confirm-live

What it does
------------
* Opens the source SQLite database READ-ONLY (`mode=ro`).
* Resolves the target URL in-process from Secrets Manager (profile
  `rfone-dev-login`) and never prints it. Refuses an AWS account other than
  418674484214, and a database other than `rfone` (`--target live`) or a
  disposable `rfone_pgval_*` database.
* Refuses unless source and target are both at Alembic `e7b2c94d0f18`.
* Refuses unless every Bank table it would fill is EMPTY on the target — a
  second run is therefore a safe refusal, never a duplicate.
* Canonical catalogues are NOT copied: the WHAT catalogue and reason groups
  must be identical (id + code) on the target, and each WHY is re-pointed by
  its unique `code`. The Reconciliation control configuration must already
  hold the same Control Start / Validated Through, or be absent.
* Legal Entities are shared data and are matched ONLY through the explicit
  `--legal-entity-map` (local id = target id | NEW). Names are never guessed.
  A NEW entity is inserted with the target's own next id.
* Every other Bank row keeps its id (the target tables are empty, so ids
  cannot collide); sequences are advanced past the copied ids.
* One transaction. Before committing, every migrated table is compared with
  the source through a deterministic logical manifest (source rows with the
  FK maps applied vs. target rows). Any difference rolls everything back.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import create_engine, func, select, text

from rfone_data_store import models as m

EXPECTED_ACCOUNT = "418674484214"
EXPECTED_REVISION = "e7b2c94d0f18"
PROFILE, REGION, SECRET = "rfone-dev-login", "us-east-1", "rfone-tips/database-url"
LIVE_DB = "rfone"
DISPOSABLE_PREFIX = "rfone_pgval_"
DEFAULT_SOURCE = Path(__file__).resolve().parent / "data" / "rfone.db"

# Insert order respects every foreign key; financial_transactions.explanation_id
# (the one cycle) is written in a second pass once the explanations exist.
MIGRATE = (
    "reporting_groups",
    "reporting_entities",
    "reporting_entity_destination_aliases",
    "bank_occurrence_types",
    "payment_instruments",
    "bank_card_settlement_accounts",
    "bank_instrument_identity_audits",
    "bank_import_batches",
    "financial_transactions",
    "raw_bank_transactions",
    "bank_occurrences",
    "bank_occurrence_aliases",
    "bank_who_recognitions",
    "bank_transaction_explanations",
    "bank_monthly_source_periods",
    "bank_monthly_instrument_coverages",
    "bank_historical_instrument_candidates",
    "bank_historical_instrument_candidate_evidence",
)
# Bank tables that are empty locally but must also be empty on the target, so
# nothing partial from an earlier attempt can hide beside the migrated rows.
MUST_BE_EMPTY_TOO = (
    "bank_card_holder_assignments", "bank_evidence_bypass_authorizations",
    "bank_instrument_assignment_audits", "bank_invoice_matches",
    "bank_occurrence_reason_associations", "bank_occurrence_suppliers",
    "bank_recognition_rules", "bank_source_instrument_profiles",
    "bank_transaction_allocations", "bank_transaction_reason_export_mappings",
    "financial_transaction_matches",
)
CATALOGUE_IDENTICAL = {  # table -> natural-key columns that must match id-for-id
    "bank_accounting_classifications": ("id", "code", "parent_id", "statement_type"),
    "bank_reason_groups": ("id", "code"),
}
LEGAL_ENTITY_COLUMNS = {
    "payment_instruments": ("legal_entity_id",),
    "reporting_entities": ("legal_entity_id",),
    "bank_who_recognitions": ("internal_legal_entity_id",),
}
REASON_COLUMNS = {"bank_transaction_explanations": ("transaction_reason_id",),
                  "bank_occurrences": ("default_transaction_reason_id",)}


# Product Owner decision, 2026-09-25: local Angeli E Demoni, LLC -> AWS 1
# (RF-Winter Park); local RF Mount Dora, LLC -> AWS 2 (RF-Mount Dora); local
# RF Gelati, LLC -> a NEW AWS Legal Entity. AWS names are not changed.
APPROVED_LIVE_LEGAL_ENTITY_MAP = {1: 1, 3: 2, 2: None}
APPROVED_LIVE_LEGAL_ENTITY_NAMES = {1: "RF-Winter Park", 2: "RF-Mount Dora"}


class Refusal(Exception):
    pass


# --------------------------------------------------------------------------- target


def _secret_url() -> str:
    import boto3
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    account = session.client("sts").get_caller_identity()["Account"]
    if account != EXPECTED_ACCOUNT:
        raise Refusal(f"AWS account {account} is not the expected {EXPECTED_ACCOUNT}.")
    raw = session.client("secretsmanager").get_secret_value(SecretId=SECRET)["SecretString"].strip()
    try:
        data = json.loads(raw)
        raw = data.get("url") or data.get("DATABASE_URL") or next(
            v for v in data.values() if isinstance(v, str) and "://" in v)
    except (ValueError, StopIteration):
        pass
    return raw.strip()


def target_url(target: str) -> tuple[str, str]:
    live = _secret_url()
    parts = urlsplit(live)
    if parts.path.lstrip("/") != LIVE_DB:
        raise Refusal("The secret does not name the expected live database.")
    if target == "live":
        return live, LIVE_DB
    if not target.startswith(DISPOSABLE_PREFIX):
        raise Refusal(f"Target {target!r} is neither 'live' nor a disposable {DISPOSABLE_PREFIX}* database.")
    return urlunsplit((parts.scheme, parts.netloc, "/" + target, parts.query, parts.fragment)), target


# --------------------------------------------------------------------------- manifest


def _norm(value):
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, bytes):
        return hashlib.sha256(value).hexdigest()
    return value


def manifest(rows: list[dict], columns: list[str]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda r: r["id"]):
        digest.update(json.dumps([_norm(row[c]) for c in columns], default=str).encode())
    return digest.hexdigest()


# --------------------------------------------------------------------------- core


def parse_le_map(raw: str) -> dict[int, int | None]:
    result: dict[int, int | None] = {}
    for part in (raw or "").split(","):
        if not part.strip():
            continue
        local, _, remote = part.partition("=")
        result[int(local)] = None if remote.strip().upper() == "NEW" else int(remote)
    return result


def run(source: Path, target: str, le_map_raw: str, apply: bool) -> dict:
    report: dict = {"target": target, "mode": "APPLY" if apply else "PREVIEW"}
    src_engine = create_engine(f"sqlite:///file:{source.as_posix()}?mode=ro&uri=true")
    url, dbname = target_url(target)
    tgt_engine = create_engine(url, connect_args={"options": "-c timezone=UTC"})
    tables = m.Base.metadata.tables
    try:
        with src_engine.connect() as src, tgt_engine.connect() as tgt:
            if not apply:
                tgt.execute(text("SET TRANSACTION READ ONLY"))
            # --- guards --------------------------------------------------
            s_rev = src.execute(text("select version_num from alembic_version")).scalar()
            t_rev = tgt.execute(text("select version_num from alembic_version")).scalar()
            report["revisions"] = {"source": s_rev, "target": t_rev}
            if s_rev != EXPECTED_REVISION or t_rev != EXPECTED_REVISION:
                raise Refusal(f"Alembic revisions must both be {EXPECTED_REVISION}: source {s_rev}, target {t_rev}.")
            occupied = {t: tgt.execute(select(func.count()).select_from(tables[t])).scalar()
                        for t in MIGRATE + MUST_BE_EMPTY_TOO}
            occupied = {t: n for t, n in occupied.items() if n}
            if occupied:
                raise Refusal(f"Target Bank tables already hold rows — refusing rather than duplicating: {occupied}")

            for table, cols in CATALOGUE_IDENTICAL.items():
                s_rows = sorted(tuple(r) for r in src.execute(select(*[tables[table].c[c] for c in cols])))
                t_rows = sorted(tuple(r) for r in tgt.execute(select(*[tables[table].c[c] for c in cols])))
                if s_rows != t_rows:
                    raise Refusal(f"Catalogue {table} differs between source and target; it is not copied, so it must match.")
            reasons = tables["bank_transaction_reasons"]
            s_why = dict(src.execute(select(reasons.c.id, reasons.c.code)).all())
            t_why = {code: i for i, code in tgt.execute(select(reasons.c.id, reasons.c.code)).all()}
            missing = sorted(set(s_why.values()) - set(t_why))
            if missing:
                raise Refusal(f"WHY codes missing on the target: {missing}")
            why_map = {sid: t_why[code] for sid, code in s_why.items()}
            report["why_map_changed"] = {k: v for k, v in why_map.items() if k != v}

            cfg = tables["bank_reconciliation_control_configs"]
            s_cfg = src.execute(select(cfg.c.control_start_month, cfg.c.validated_through_month)).all()
            t_cfg = tgt.execute(select(cfg.c.control_start_month, cfg.c.validated_through_month)).all()
            if t_cfg and [tuple(r) for r in t_cfg] != [tuple(r) for r in s_cfg]:
                raise Refusal(f"Target control configuration {t_cfg} differs from source {s_cfg}.")
            report["control_config"] = {"source": [tuple(r) for r in s_cfg], "target": [tuple(r) for r in t_cfg],
                                        "action": "keep target (identical)" if t_cfg else "insert"}

            le = tables["legal_entities"]
            s_le = {r.id: r._mapping for r in src.execute(select(le))}
            t_le = {r.id: r._mapping for r in tgt.execute(select(le))}
            le_map = parse_le_map(le_map_raw)
            used = set()
            for t, cols in LEGAL_ENTITY_COLUMNS.items():
                for c in cols:
                    used |= {v for (v,) in src.execute(select(tables[t].c[c]).where(tables[t].c[c].is_not(None)).distinct())}
            if set(le_map) != set(s_le):
                raise Refusal(f"--legal-entity-map must name every local Legal Entity {sorted(s_le)}; got {sorted(le_map)}.")
            for local_id, remote_id in le_map.items():
                if remote_id is not None and remote_id not in t_le:
                    raise Refusal(f"Legal Entity map {local_id}={remote_id}: target id {remote_id} does not exist.")
            if dbname == LIVE_DB:
                for remote_id, name in APPROVED_LIVE_LEGAL_ENTITY_NAMES.items():
                    if remote_id not in t_le or t_le[remote_id]["legal_name"] != name:
                        raise Refusal(f"Live Legal Entity {remote_id} is no longer {name!r}; the approved map "
                                      "cannot be applied safely.")
            targets = [v for v in le_map.values() if v is not None]
            if len(targets) != len(set(targets)):
                raise Refusal("Two local Legal Entities map to the same target entity.")
            report["legal_entities"] = [
                {"local_id": lid, "local_name": s_le[lid]["legal_name"],
                 "target_id": rid, "target_name": t_le[rid]["legal_name"] if rid else "(NEW)",
                 "used_by_bank_rows": lid in used}
                for lid, rid in sorted(le_map.items())]

            # --- read source ---------------------------------------------
            source_rows = {t: [dict(r._mapping) for r in src.execute(select(tables[t]).order_by(tables[t].c.id))]
                           for t in MIGRATE}
            report["rows"] = {t: len(rows) for t, rows in source_rows.items()}
            report["pk_ranges"] = {t: ([rows[0]["id"], rows[-1]["id"]] if rows else None)
                                   for t, rows in source_rows.items()}

            if not apply:
                report["new_legal_entities"] = [s_le[l]["legal_name"] for l, r in le_map.items() if r is None]
                report["expected_after"] = {t: n for t, n in report["rows"].items()}
                report["result"] = "PREVIEW ONLY — nothing written"
                return report

        # --- apply: one transaction ------------------------------------
        with src_engine.connect() as src, tgt_engine.begin() as tgt:
            for local_id, remote_id in sorted(le_map.items()):
                if remote_id is None:
                    row = {k: v for k, v in s_le[local_id].items() if k != "id"}
                    le_map[local_id] = tgt.execute(le.insert().values(**row).returning(le.c.id)).scalar()
            report["legal_entity_map_final"] = dict(le_map)

            def transform(table: str, row: dict) -> dict:
                row = dict(row)
                for c in LEGAL_ENTITY_COLUMNS.get(table, ()):
                    if row.get(c) is not None:
                        row[c] = le_map[row[c]]
                for c in REASON_COLUMNS.get(table, ()):
                    if row.get(c) is not None:
                        row[c] = why_map[row[c]]
                if table == "financial_transactions":
                    row["explanation_id"] = None      # second pass
                return row

            expected = {t: [transform(t, r) for r in rows] for t, rows in source_rows.items()}
            for t in MIGRATE:
                rows = expected[t]
                for i in range(0, len(rows), 1000):
                    tgt.execute(tables[t].insert(), rows[i:i + 1000])
                if rows:
                    tgt.execute(text(f"select setval(pg_get_serial_sequence('{t}', 'id'), "
                                     f"(select max(id) from {t}))"))
            ft = tables["financial_transactions"]
            links = [(r["id"], r["explanation_id"], r["updated_at"])
                     for r in source_rows["financial_transactions"] if r["explanation_id"]]
            # `updated_at` is written explicitly: the model's onupdate would
            # otherwise stamp the migration time on every decided transaction.
            for fid, eid, updated_at in links:
                tgt.execute(ft.update().where(ft.c.id == fid).values(explanation_id=eid, updated_at=updated_at))
            links = [(fid, eid) for fid, eid, _ in links]
            for fid, eid in links:
                next(r for r in expected["financial_transactions"] if r["id"] == fid)["explanation_id"] = eid
            if not t_cfg and s_cfg:
                src_cfg = dict(src.execute(select(cfg)).first()._mapping)
                tgt.execute(cfg.insert().values(**src_cfg))

            # --- verify inside the transaction ---------------------------
            mismatches = {}
            for t in MIGRATE:
                cols = [c.name for c in tables[t].columns]
                actual = [dict(r._mapping) for r in tgt.execute(select(tables[t]))]
                if len(actual) != len(expected[t]) or manifest(actual, cols) != manifest(expected[t], cols):
                    by_id = {r["id"]: r for r in actual}
                    first = None
                    for row in sorted(expected[t], key=lambda r: r["id"]):
                        got = by_id.get(row["id"])
                        diff = [c for c in cols if got is None or _norm(row[c]) != _norm(got[c])]
                        if diff:
                            first = {"id": row["id"], "columns": diff,
                                     "expected": [repr(_norm(row[c]))[:80] for c in diff],
                                     "actual": [repr(_norm(got[c]))[:80] if got else None for c in diff]}
                            break
                    mismatches[t] = {"expected_rows": len(expected[t]), "actual_rows": len(actual), "first_difference": first}
            report["manifests"] = {t: manifest(expected[t], [c.name for c in tables[t].columns]) for t in MIGRATE}
            if mismatches:
                raise Refusal(f"Post-insert manifest mismatch, rolled back: {mismatches}")
            report["result"] = "APPLIED — committed"
            return report
    finally:
        src_engine.dispose()
        tgt_engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", required=True, help="'live' or a disposable rfone_pgval_* database name")
    parser.add_argument("--legal-entity-map", required=True, help="local=target|NEW, comma separated")
    parser.add_argument("--apply", action="store_true", help="write (default: preview only)")
    parser.add_argument("--confirm-live", action="store_true",
                        help="required, together with --target live and --apply, to write to the live database")
    parser.add_argument("--report", type=Path, help="write the JSON report here")
    args = parser.parse_args()
    # BANK_AWS_LIVE_DATA_MIGRATION_001 — the live database is written only
    # through an explicit three-part confirmation, and only with the Legal
    # Entity map the Product Owner approved (2026-09-25). Every other guard in
    # `run` applies unchanged.
    if args.target == "live" and args.apply:
        if not args.confirm_live:
            print("REFUSED: writing to the live database also requires --confirm-live.")
            return 2
        if parse_le_map(args.legal_entity_map) != APPROVED_LIVE_LEGAL_ENTITY_MAP:
            print(f"REFUSED: the live Legal Entity map must be the approved {APPROVED_LIVE_LEGAL_ENTITY_MAP}.")
            return 2
    elif args.confirm_live:
        print("REFUSED: --confirm-live is only meaningful with --target live --apply.")
        return 2
    try:
        report = run(args.source, args.target, args.legal_entity_map, args.apply)
        status = 0
    except Refusal as exc:
        report, status = {"target": args.target, "result": f"REFUSED: {exc}"}, 2
    text_report = json.dumps(report, indent=2, default=str)
    print(text_report)
    if args.report:
        args.report.write_text(text_report, encoding="utf-8")
    return status


if __name__ == "__main__":
    sys.exit(main())
