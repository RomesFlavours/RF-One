"""Replace ALL Bank data on AWS with the frozen local copy (Product Owner, 2026-10-14) — not a merge.

    python replace_bank_on_aws_with_local.py --local <frozen copy> --target rfone_pgval_x --apply      # rehearsal
    python replace_bank_on_aws_with_local.py --local <frozen copy> --target live --apply --confirm-live

Scope: the Bank tables only — every `bank_*` table plus financial_transactions, raw_bank_transactions,
payment_instruments, reporting_entities, reporting_groups, reporting_entity_destination_aliases. After the run
each of them holds exactly the local rows, with the LOCAL ids; sequences are set past them.

Shared tables are never deleted or changed: rfone_accounts, legal_entities, acting_identities, employees,
suppliers, source_systems, purchase_documents. A Bank column that points to one of them is re-pointed:
Legal Entities 1->2, 2->1, 3->3 (same companies, AWS names unchanged, decision of 2026-09-25 / plan §2) and the
only local account `admin` -> AWS `rfone` (the Product Owner). Any other non-null reference is refused.

Safety: one transaction; the Bank tables are locked against writes (EXCLUSIVE: reads keep working) for its whole
length; every table compared row by row with the local copy, every Bank foreign key checked, the other tables
checked unchanged — all before COMMIT, otherwise ROLLBACK. Restore: the RDS snapshot taken before the run.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

import sqlalchemy as sa

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from transfer_bank_2026_to_aws import Refusal, local_copy, target_url, REVISION  # noqa: E402

CORE = ["financial_transactions", "raw_bank_transactions", "payment_instruments", "reporting_entities",
        "reporting_groups", "reporting_entity_destination_aliases"]
LEGAL_ENTITY_MAP = {1: 2, 2: 1, 3: 3}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([+-]\d{2}:?\d{2}|Z)?)?$")
ACCOUNT_MAP_BY_NAME = ("admin", "rfone")


def bank_tables(conn) -> list[str]:
    names = [t for t in sa.inspect(conn).get_table_names() if t.startswith("bank_")] + CORE
    return sorted(names)


def foreign_keys(conn, tables):
    out = []
    for t in tables:
        for fk in sa.inspect(conn).get_foreign_keys(t):
            out.append((t, fk["constrained_columns"][0], fk["referred_table"], fk["referred_columns"][0]))
    return out


def digest(conn, table) -> str:
    h = hashlib.sha256()
    for r in conn.execute(sa.text(f'SELECT * FROM "{table}" ORDER BY 1')):
        h.update(repr(tuple(r)).encode())
    return h.hexdigest()


def norm(v):
    """One comparable form for a SQLite and a PostgreSQL value."""
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (bytes, memoryview)):
        return hashlib.sha256(bytes(v)).hexdigest()
    if isinstance(v, datetime.datetime):
        if v.tzinfo is not None:
            v = v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return ("dt", v.isoformat(sep=" "))
    if isinstance(v, datetime.date):
        return ("d", v.isoformat())
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True)
    if isinstance(v, str):
        if v[:1] in "[{":
            try:
                return json.dumps(json.loads(v), sort_keys=True)
            except ValueError:
                return v
        if DATE_RE.match(v):
            try:
                if len(v) == 10:
                    return ("d", datetime.date.fromisoformat(v).isoformat())
                d = datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
                return norm(d)
            except ValueError:
                return v
        return v
    if hasattr(v, "as_integer_ratio") and not isinstance(v, int):
        return float(v)
    return v


def history_key(table: str, column: str, value):
    """bank_ai_rule_interpretations.cache_key holds 64 characters on PostgreSQL; a local reset
    (BANK_RULES_RESET_001) suffixed invalidated keys beyond that. Such a row is kept as history under a key that can
    never match a lookup (lookups are 64 hex digits) — the one value that cannot be copied as it is."""
    if table == "bank_ai_rule_interpretations" and column == "cache_key" and isinstance(value, str) and len(value) > 64:
        return "x" + hashlib.sha256(value.encode()).hexdigest()[:63]
    return value


def run(local_path: str, target: str, apply: bool) -> dict:
    import sqlite3
    copy = local_copy(local_path)
    L = sqlite3.connect(copy)
    L.row_factory = sqlite3.Row
    if L.execute("select version_num from alembic_version").fetchone()[0] != REVISION:
        raise Refusal("the local copy is not at the release revision")
    report = {"target": target, "applied": False, "checks": [], "tables": {}}
    engine = sa.create_engine(target_url(target))
    with engine.connect() as A:
        tr = A.begin()
        try:
            if [r[0] for r in A.execute(sa.text("select version_num from alembic_version"))] != [REVISION]:
                raise Refusal("AWS is not at the release revision")
            tables = bank_tables(A)
            local_tables = {r[0] for r in L.execute("select name from sqlite_master where type='table'")}
            missing = [t for t in tables if t not in local_tables]
            if missing:
                raise Refusal(f"Bank tables missing in the local copy: {missing}")
            fks = foreign_keys(A, tables)
            shared = [(t, c, d) for t, c, d, _ in fks if d not in tables]
            # who/what the shared references are
            local_accounts = [r["username"] for r in L.execute("select username from rfone_accounts")]
            if local_accounts != [ACCOUNT_MAP_BY_NAME[0]]:
                raise Refusal(f"local accounts are not the single expected 'admin': {local_accounts}")
            local_admin = L.execute("select id from rfone_accounts").fetchone()[0]
            aws_admin = A.execute(sa.text("select id from rfone_accounts where username=:u"),
                                  {"u": ACCOUNT_MAP_BY_NAME[1]}).scalar()
            remap = {}
            for t, c, d in shared:
                if d == "rfone_accounts":
                    remap[(t, c)] = {local_admin: aws_admin}
                elif d == "legal_entities":
                    remap[(t, c)] = LEGAL_ENTITY_MAP
                else:
                    n = L.execute(f'select count(*) from "{t}" where "{c}" is not null').fetchone()[0]
                    if n:
                        raise Refusal(f"{t}.{c} -> {d}: {n} local row(s) point to a shared table with no mapping")
            others = [t for t in sa.inspect(A).get_table_names() if t not in tables and t != "alembic_version"]
            others_before = {t: digest(A, t) for t in others}

            # no write to Bank during the replacement (reads keep working)
            A.execute(sa.text("LOCK TABLE " + ", ".join(f'"{t}"' for t in tables) + " IN EXCLUSIVE MODE"))
            A.execute(sa.text("SET LOCAL session_replication_role = replica"))
            md = sa.MetaData()
            md.reflect(A, only=tables)
            before_counts = {t: A.execute(sa.text(f'select count(*) from "{t}"')).scalar() for t in tables}
            for t in tables:
                A.execute(sa.text(f'DELETE FROM "{t}"'))
            for t in tables:
                table = md.tables[t]
                cols = [c.name for c in table.columns]
                types = {c.name: c.type for c in table.columns}
                local_cols = {r[1] for r in L.execute(f'pragma table_info("{t}")')}
                rows = []
                for r in L.execute(f'select * from "{t}"'):
                    row = {}
                    for c in cols:
                        v = r[c] if c in local_cols else None
                        if (t, c) in remap and v is not None:
                            if v not in remap[(t, c)]:
                                raise Refusal(f"{t}.{c} = {v}: no mapping to the shared table")
                            v = remap[(t, c)][v]
                        if v is not None and isinstance(types[c], sa.Boolean):
                            v = bool(v)
                        rekeyed = history_key(t, c, v)
                        if rekeyed != v:
                            report["interpretation_keys_rekeyed_as_history"] = \
                                report.get("interpretation_keys_rekeyed_as_history", 0) + 1
                        row[c] = rekeyed
                    rows.append(row)
                for i in range(0, len(rows), 2000):
                    A.execute(table.insert(), rows[i:i + 2000])
                report["tables"][t] = {"aws_before": before_counts[t], "after": len(rows)}
            for t in tables:
                if "id" in md.tables[t].columns:
                    seq = A.execute(sa.text("select pg_get_serial_sequence(:t,'id')"), {"t": t}).scalar()
                    if seq:
                        A.execute(sa.text(f'select setval(:s, coalesce((select max(id) from "{t}"), 0) + 1, false)'),
                                  {"s": seq})

            def check(name, ok, detail=""):
                report["checks"].append({"check": name, "ok": bool(ok), "detail": str(detail)[:400]})

            # contents: every Bank table equals the local one, row by row (shared references re-pointed)
            diff = []
            for t in tables:
                cols = [c.name for c in md.tables[t].columns]
                local_cols = {r[1] for r in L.execute(f'pragma table_info("{t}")')}
                key = cols[0]
                want = []
                for r in L.execute(f'select * from "{t}"'):
                    want.append(tuple(norm(history_key(t, c, remap.get((t, c), {}).get(r[c], r[c])))
                                      if c in local_cols else None for c in cols))
                got = [tuple(norm(v) for v in r) for r in A.execute(sa.text(
                    "select " + ",".join(f'"{c}"' for c in cols) + f' from "{t}"'))]
                if sorted(want, key=repr) != sorted(got, key=repr):
                    w = {x[0]: x for x in want}
                    g = {x[0]: x for x in got}
                    cols_diff = sorted({c for k in w if k in g for c, a, b in zip(cols, w[k], g[k]) if a != b})
                    sample = next(((c, a, b) for k in w if k in g for c, a, b in zip(cols, w[k], g[k]) if a != b), None)
                    diff.append((t, len(want), len(got), cols_diff[:6], repr(sample)[:160]))
            check("every Bank table equals the local copy, row by row", not diff, diff[:5])
            dangling = []
            for t, c, d, dc in fks:
                n = A.execute(sa.text(f'select count(*) from "{t}" x where x."{c}" is not null and not exists '
                                      f'(select 1 from "{d}" y where y."{dc}" = x."{c}")')).scalar()
                if n:
                    dangling.append((t, c, d, n))
            check("every Bank foreign key resolves (Bank and shared tables)", not dangling, dangling[:10])
            check("other Domains and shared tables unchanged",
                  all(digest(A, t) == h for t, h in others_before.items()),
                  [t for t, h in others_before.items() if digest(A, t) != h][:10])
            report["shared_references_remapped"] = sorted(f"{t}.{c}" for t, c in remap)
            report["rows"] = {"aws_before": sum(before_counts.values()),
                              "after": sum(v["after"] for v in report["tables"].values())}
            if not all(c["ok"] for c in report["checks"]):
                print(json.dumps([c for c in report["checks"] if not c["ok"]], indent=1, default=str))
                raise Refusal("a check failed: " + "; ".join(c["check"] for c in report["checks"] if not c["ok"]))
            if apply:
                tr.commit()
                report["applied"] = True
            else:
                tr.rollback()
        except Exception:
            tr.rollback()
            raise
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--local", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--confirm-live", action="store_true")
    a = p.parse_args()
    if a.target == "live" and a.apply and not a.confirm_live:
        print("REFUSED: writing to the live database also requires --confirm-live.")
        return 2
    try:
        report = run(a.local, a.target, a.apply)
    except Refusal as exc:
        print("REFUSED:", exc)
        return 2
    print(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
