"""Bank initial load: the cleaned local Bank, copied whole into an empty Bank schema on AWS (BANK_REINSTALL_001).

    # preview (default): counts and checks, nothing written
    python load_bank_initial_to_aws.py --local <path of the local rfone.db> --target-url postgresql://...
    # rehearsal on a disposable PostgreSQL database
    python load_bank_initial_to_aws.py --local <path> --target-url postgresql://localhost/... --apply
    # the initial load on the live database (RDS rfone-dev / rfone)
    python load_bank_initial_to_aws.py --local <path> --target live --apply --confirm-live

Product Owner decision (2026-10-17): for this FIRST release the local Bank is the authoritative source. Every
Bank row of the local working database is copied as it is — transactions, files and raw rows, Sources, WHO,
WHY and WHAT catalogs, decisions, For Whom (allocations and Reporting Entities), AI rules with their versions,
interpretations, previews and applications, monthly control, settings. Nothing is recomputed: no recognition,
no rule, no classification runs during the copy; ids are kept.

ONE time only. After this initial load the local database is never transferred to AWS again: later releases
carry code and migrations only, and the online data are preserved (BANK_REINSTALL_001, Infrastructure README).

Safety:
  * the local file is read from a COPY made here, upgraded to the reinstall revision on the copy only;
  * the target must be at Alembic revision c8e4b2a6f0d1 with all 46 Bank tables present and EMPTY: nothing is
    merged with older Bank data, nothing duplicated, and a second run is refused;
  * the only references to tables shared with other Domains are remapped by the Product Owner's maps (Legal
    Entities local 1->2, 2->1, 3->3; the local account `admin` -> AWS `rfone`); any other shared reference must be
    empty, otherwise the load refuses;
  * one REPEATABLE READ transaction; every check below must hold before COMMIT, otherwise ROLLBACK:
    row counts and a content hash of every Bank table equal to the local ones (remapped columns mapped back),
    totals per Source, decisions per WHO/WHY, and every table of the other Domains unchanged (row count and hash);
  * live only with --confirm-live, after the AWS account and the secret's database are checked.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import decimal
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile

import sqlalchemy as sa

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

EXPECTED_ACCOUNT = "418674484214"
REGION, SECRET = "us-east-1", "rfone-tips/database-url"
LIVE_DB = "rfone"
REVISION = "c8e4b2a6f0d1"

# The Product Owner's maps (BANK_AWS_DATA_TRANSFER_PLAN_001 §2, confirmed for this load): local id -> AWS.
LEGAL_ENTITY_MAP = {1: 2, 2: 1, 3: 3}
ACCOUNT_USERNAME_MAP = {"admin": "rfone"}


class Refusal(Exception):
    pass


def bank_tables() -> list[str]:
    """The 46 Bank tables, from the reinstall revision itself (one definition)."""
    import importlib.util
    path = os.path.join(HERE, "migrations", "versions", "c8e4b2a6f0d1_reinstall_bank.py")
    spec = importlib.util.spec_from_file_location("reinstall_bank", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return sorted(module.EXPECTED_COLUMNS)


def live_url(profile: str | None) -> str:
    import boto3
    session = boto3.Session(profile_name=profile, region_name=REGION)
    if session.client("sts").get_caller_identity()["Account"] != EXPECTED_ACCOUNT:
        raise Refusal("the AWS session is not account " + EXPECTED_ACCOUNT)
    url = session.client("secretsmanager").get_secret_value(SecretId=SECRET)["SecretString"].strip()
    if sa.engine.make_url(url).database != LIVE_DB:
        raise Refusal("the secret does not name the live database")
    return url


def local_copy(path: str) -> str:
    """A copy of the local database (SQLite backup API: consistent while Bank runs), upgraded to REVISION."""
    folder = tempfile.mkdtemp(prefix="bank_initial_load_")
    copy = os.path.join(folder, "rfone_local_copy.db")
    source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    target = sqlite3.connect(copy)
    source.backup(target)
    target.close()
    source.close()
    from alembic import command
    from alembic.config import Config
    cfg = Config(os.path.join(HERE, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(HERE, "migrations"))
    previous = os.environ.get("ALEMBIC_DATABASE_URL_OVERRIDE")
    os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = "sqlite:///" + copy.replace(os.sep, "/")
    os.environ.pop("RFONE_CONFIRM_REMOVE_BANK", None)          # never drop on the copy
    try:
        command.upgrade(cfg, REVISION)
    finally:
        if previous is None:
            os.environ.pop("ALEMBIC_DATABASE_URL_OVERRIDE", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL_OVERRIDE"] = previous
    return copy


def _a_cycle(graph: dict[str, set[str]]) -> set[str]:
    """One strongly connected group of more than one table (Tarjan), the smallest one."""
    index, low, stack, on, groups, counter = {}, {}, [], set(), [], [0]

    def visit(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in sorted(graph[v]):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            group = set()
            while True:
                w = stack.pop()
                on.discard(w)
                group.add(w)
                if w == v:
                    break
            groups.append(group)

    for v in sorted(graph):
        if v not in index:
            visit(v)
    cycles = [g for g in groups if len(g) > 1]
    if not cycles:
        raise Refusal("no load order and no cycle among the Bank tables")
    return min(cycles, key=lambda g: (len(g), sorted(g)))


def load_order(metadata: sa.MetaData, tables: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """Tables in an order where every reference points to a table already loaded; the references that cannot be
    ordered (a table pointing to itself, or a cycle) are loaded empty first and filled in a second pass."""
    bank = set(tables)
    deferred: dict[str, list[str]] = collections.defaultdict(list)
    edges = {t: set() for t in tables}
    for t in tables:
        for fk in metadata.tables[t].foreign_keys:
            ref = fk.column.table.name
            if ref == t:
                deferred[t].append(fk.parent.name)
            elif ref in bank:
                edges[t].add((ref, fk.parent.name))
    order, done = [], set()
    pending = set(tables)
    while pending:
        ready = sorted(t for t in pending if all(r in done for r, _c in edges[t]))
        if not ready:
            # A real cycle (a strongly connected group of pending tables): defer, in one of its tables, only its
            # references INSIDE the cycle, and only when they are nullable columns (loaded empty, filled in the
            # second pass).
            cycle = _a_cycle({t: {r for r, _c in edges[t] if r in pending} for t in pending})
            candidates = []
            for t in sorted(cycle):
                inside = [(r, c) for r, c in edges[t] if r in cycle]
                if all(metadata.tables[t].c[c].nullable for _r, c in inside):
                    candidates.append((len(inside), t, inside))
            if not candidates:
                raise Refusal(f"the Bank tables {sorted(cycle)} reference each other through required columns")
            _n, t, inside = min(candidates)
            for _r, column in inside:
                deferred[t].append(column)
            edges[t] = {(r, c) for r, c in edges[t] if (r, c) not in set(inside)}
            continue
        for t in ready:
            order.append(t)
            done.add(t)
            pending.discard(t)
    return order, dict(deferred)


def shared_references(metadata: sa.MetaData, tables: list[str]) -> dict[str, list[tuple[str, str]]]:
    """table -> [(column, shared table it references)] for the references outside Bank."""
    bank = set(tables)
    found = collections.defaultdict(list)
    for t in tables:
        for fk in metadata.tables[t].foreign_keys:
            if fk.column.table.name not in bank:
                found[t].append((fk.parent.name, fk.column.table.name))
    return dict(found)


def canonical(value):
    """A value as both databases give it back, for hashing."""
    if value is None:
        return None
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, dt.datetime):
        if value.tzinfo is not None:
            value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return value.isoformat(timespec="microseconds")
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value.normalize())
    if isinstance(value, float):
        return repr(round(value, 9))
    if isinstance(value, (bytes, bytearray, memoryview)):
        return hashlib.sha256(bytes(value)).hexdigest()
    return value


def table_hash(conn, table: sa.Table, unmap: dict[str, dict] | None = None) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    columns = sorted(c.name for c in table.columns)
    for row in conn.execute(sa.select(*[table.c[c] for c in columns]).order_by(*table.primary_key.columns)):
        values = dict(zip(columns, row))
        for column, mapping in (unmap or {}).items():
            if values[column] is not None:
                values[column] = mapping[values[column]]
        digest.update(json.dumps([canonical(values[c]) for c in columns], default=str).encode())
        count += 1
    return count, digest.hexdigest()


def other_tables_fingerprint(conn, bank: set[str]) -> dict[str, tuple[int, str]]:
    """Every table of the other Domains: row count and a hash of its rows (PostgreSQL)."""
    result = {}
    names = [r[0] for r in conn.execute(sa.text(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"))]
    for name in names:
        if name in bank:
            continue
        row = conn.execute(sa.text(
            f'SELECT count(*), md5(coalesce(string_agg(md5(t::text), \'\' ORDER BY md5(t::text)), \'\')) FROM "{name}" t'
        )).one()
        result[name] = (row[0], row[1])
    return result


def run(local_path: str, target_url: str, apply: bool) -> dict:
    from rfone_data_store import models as m
    metadata = m.Base.metadata
    tables = bank_tables()
    bank = set(tables)
    order, deferred = load_order(metadata, tables)
    shared = shared_references(metadata, tables)

    copy = local_copy(local_path)
    local = sa.create_engine("sqlite:///" + copy.replace(os.sep, "/"))
    target = sa.create_engine(target_url, isolation_level="REPEATABLE READ")
    report: dict = {"local_copy": copy, "target": target.url.render_as_string(hide_password=True),
                    "revision": REVISION, "tables": {}, "checks": []}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            raise Refusal(f"check failed: {name} {detail}")

    with local.connect() as L, target.connect() as T:
        tx = T.begin()
        try:
            # The local times are UTC without an offset (SQLite): read as UTC whatever the server's own time zone.
            T.execute(sa.text("SET LOCAL TIME ZONE 'UTC'"))
            check("local copy at the reinstall revision",
                  L.execute(sa.text("SELECT version_num FROM alembic_version")).scalars().all() == [REVISION])
            check("target at the reinstall revision",
                  T.execute(sa.text("SELECT version_num FROM alembic_version")).scalars().all() == [REVISION])
            existing = set(sa.inspect(T).get_table_names())
            check("all 46 Bank tables exist on the target", bank <= existing, str(sorted(bank - existing)))
            non_empty = {t: n for t in tables if (n := T.execute(sa.text(f'SELECT count(*) FROM "{t}"')).scalar())}
            check("every Bank table on the target is empty (no merge, no second run)", not non_empty, str(non_empty))

            # The shared references: remapped by the maps, or empty.
            accounts_local = dict(L.execute(sa.text("SELECT id, username FROM rfone_accounts")).all())
            accounts_target = {u: i for i, u in T.execute(sa.text("SELECT id, username FROM rfone_accounts")).all()}
            account_map = {}
            for local_id, username in accounts_local.items():
                aws_username = ACCOUNT_USERNAME_MAP.get(username)
                if aws_username is not None:
                    check(f"AWS account {aws_username!r} exists", aws_username in accounts_target)
                    account_map[local_id] = accounts_target[aws_username]
            legal_target = set(T.execute(sa.text("SELECT id FROM legal_entities")).scalars())
            check("the mapped Legal Entities exist on the target", set(LEGAL_ENTITY_MAP.values()) <= legal_target,
                  str(sorted(set(LEGAL_ENTITY_MAP.values()) - legal_target)))
            remap: dict[str, dict[str, dict]] = collections.defaultdict(dict)
            for t, refs in shared.items():
                for column, ref in refs:
                    used = set(L.execute(sa.text(f'SELECT DISTINCT "{column}" FROM "{t}" WHERE "{column}" IS NOT NULL')).scalars())
                    if not used:
                        continue
                    if ref == "legal_entities":
                        check(f"{t}.{column}: every Legal Entity has a mapping", used <= set(LEGAL_ENTITY_MAP),
                              str(sorted(used - set(LEGAL_ENTITY_MAP))))
                        remap[t][column] = LEGAL_ENTITY_MAP
                    elif ref == "rfone_accounts":
                        check(f"{t}.{column}: every account has a mapping", used <= set(account_map),
                              str(sorted(used - set(account_map))))
                        remap[t][column] = account_map
                    else:
                        check(f"{t}.{column} -> {ref} is empty locally (no map for {ref})", False, str(sorted(used)))

            before = other_tables_fingerprint(T, bank)

            # Copy: table by table, ids kept; references that cannot be ordered are filled in a second pass.
            second_pass: list[tuple[str, str, list[tuple]]] = []
            for t in order:
                table = metadata.tables[t]
                rows = [dict(r._mapping) for r in L.execute(sa.select(table).order_by(*table.primary_key.columns))]
                later = deferred.get(t, [])
                if later:
                    second_pass.append((t, later, [(r["id"], {c: r[c] for c in later}) for r in rows
                                                   if any(r[c] is not None for c in later)]))
                for r in rows:
                    for column, mapping in remap.get(t, {}).items():
                        if r[column] is not None:
                            r[column] = mapping[r[column]]
                    for column in later:
                        r[column] = None
                for start in range(0, len(rows), 1000):
                    T.execute(table.insert(), rows[start:start + 1000])
                report["tables"][t] = len(rows)
            # Second pass in blocks (one round trip per 1000 rows on RDS); the deferred columns are integer ids.
            from psycopg2.extras import execute_values
            cursor = T.connection.dbapi_connection.cursor()
            for t, columns, values in second_pass:
                if not values:
                    continue
                assignments = ", ".join(f'"{c}" = v."{c}"::integer' for c in columns)
                names = ", ".join(f'"{c}"' for c in columns)
                execute_values(cursor, f'UPDATE "{t}" AS t SET {assignments} FROM (VALUES %s) AS v(id, {names}) '
                                       f'WHERE t.id = v.id',
                               [(row_id, *[fields[c] for c in columns]) for row_id, fields in values], page_size=1000)

            # Sequences follow the copied ids.
            for t in tables:
                if "id" in metadata.tables[t].c:
                    T.execute(sa.text(f"SELECT setval(pg_get_serial_sequence('\"{t}\"', 'id'), "
                                      f"coalesce((SELECT max(id) FROM \"{t}\"), 0) + 1, false)"))

            # Checks before COMMIT.
            for t in tables:
                table = metadata.tables[t]
                unmap = {c: {v: k for k, v in mapping.items()} for c, mapping in remap.get(t, {}).items()}
                local_count, local_hash = table_hash(L, table)
                target_count, target_hash = table_hash(T, table, unmap)
                check(f"{t}: {local_count} rows, identical content", (local_count, local_hash) == (target_count, target_hash),
                      f"local {local_count} {local_hash[:12]} / target {target_count} {target_hash[:12]}")
            totals_sql = ("SELECT payment_instrument_id, count(*), coalesce(sum(amount_minor), 0) FROM financial_transactions "
                          "GROUP BY payment_instrument_id ORDER BY payment_instrument_id")
            local_totals = [tuple(r) for r in L.execute(sa.text(totals_sql))]
            target_totals = [tuple(r) for r in T.execute(sa.text(totals_sql))]
            check("movements and totals per Source", local_totals == target_totals)
            report["totals_per_source"] = local_totals
            decisions_sql = ("SELECT o.canonical_name, r.name, count(*) FROM financial_transactions f "
                             "JOIN bank_transaction_explanations e ON e.id = f.explanation_id "
                             "LEFT JOIN bank_occurrences o ON o.id = e.occurrence_id "
                             "LEFT JOIN bank_transaction_reasons r ON r.id = e.transaction_reason_id "
                             "GROUP BY o.canonical_name, r.name ORDER BY 1, 2")
            # Compared whatever the order (SQLite sorts NULL first, PostgreSQL last).
            def by_pair(rows_):
                return sorted((tuple(r) for r in rows_), key=lambda x: tuple("" if v is None else str(v) for v in x))
            local_decisions = by_pair(L.execute(sa.text(decisions_sql)))
            check("current decisions per WHO / WHY", local_decisions == by_pair(T.execute(sa.text(decisions_sql))),
                  f"{len(local_decisions)} WHO/WHY pairs")
            report["decisions"] = {"pairs": len(local_decisions), "decided": sum(r[2] for r in local_decisions)}
            after = other_tables_fingerprint(T, bank)
            changed = sorted(n for n in before if before[n] != after.get(n))
            check("every table of the other Domains unchanged", not changed and set(before) == set(after), str(changed))
            report["other_tables_checked"] = len(before)

            if apply:
                tx.commit()
                report["result"] = "COMMITTED"
            else:
                tx.rollback()
                report["result"] = "PREVIEW (rolled back, nothing written)"
        except Exception:
            tx.rollback()
            raise
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--local", required=True, help="path of the local Bank rfone.db (read through a copy)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--target", choices=["live"], help="the live database, from the AWS secret")
    g.add_argument("--target-url", help="a disposable PostgreSQL database (rehearsal)")
    p.add_argument("--profile", default=None, help="AWS profile for --target live (default: the current session)")
    p.add_argument("--apply", action="store_true", help="commit when every check holds")
    p.add_argument("--confirm-live", action="store_true", help="required with --target live --apply")
    p.add_argument("--report", help="write the JSON report here")
    args = p.parse_args()
    if args.target == "live":
        if args.apply and not args.confirm_live:
            raise SystemExit("--target live --apply needs --confirm-live")
        url = live_url(args.profile)
    else:
        url = args.target_url
        if sa.engine.make_url(url).database == LIVE_DB and "localhost" not in (sa.engine.make_url(url).host or ""):
            raise SystemExit("--target-url must not name the live database; use --target live")
    try:
        report = run(args.local, url, args.apply)
    except Refusal as exc:
        print(f"REFUSED: {exc}")
        return 2
    text = json.dumps(report, indent=1, default=str)
    if args.report:
        open(args.report, "w", encoding="utf-8").write(text)
    failed = [c for c in report["checks"] if not c["ok"]]
    print(f"{report['result']}: {sum(report['tables'].values())} rows in {len(report['tables'])} Bank tables; "
          f"{len(report['checks'])} checks, {len(failed)} failed; other Domains' tables checked: "
          f"{report.get('other_tables_checked')}")
    shutil.rmtree(os.path.dirname(report["local_copy"]), ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
