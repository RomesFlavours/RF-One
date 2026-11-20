"""Read-only SQLite workspace for category checks across Bank, RF-One and uploaded rows."""
import csv
import io
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from sqlalchemy import text


def quoted(value):
    return '"' + value.replace('"', '""') + '"'


def domain_connection():
    import psycopg2
    path = Path(os.environ["RFONE_DOMAIN_DATA"])
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    data_dir = path.parent / "postgres-data"
    if data_dir.is_dir():
        state = (data_dir / "postmaster.pid").read_text().splitlines()
        if Path(state[1]).resolve() != data_dir.resolve():
            raise ValueError("Il percorso del database locale dei domini è incoerente.")
        config["port"] = int(state[3])
    return psycopg2.connect(host=config["host"], port=config["port"], dbname=config["database"],
                            user=config["user"], password=config["password"], connect_timeout=5,
                            options="-c default_transaction_read_only=on")


def sources(db, *, warnings=None):
    catalog = {}
    for name, in db.execute(text("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'")):
        columns = [r[1] for r in db.execute(text("PRAGMA table_info(" + quoted(name) + ")"))]
        catalog["bank." + name] = columns
    if os.environ.get("RFONE_DOMAIN_DATA"):
        try:
            with closing(domain_connection()) as conn, conn.cursor() as cur:
                cur.execute("""SELECT table_schema,table_name,column_name FROM information_schema.columns
                               WHERE table_schema NOT IN ('pg_catalog','information_schema')
                               AND table_schema NOT LIKE 'pg_toast%' ORDER BY table_schema,table_name,ordinal_position""")
                for schema, table, column in cur:
                    catalog.setdefault("rf." + schema + "." + table, []).append(column)
        except Exception as exc:
            if warnings is None:
                raise ValueError("Il database dei domini RF-One non è raggiungibile.") from exc
            warnings.append("Il database dei domini RF-One non è raggiungibile.")
    for batch, name, in db.execute(text("SELECT id,original_file_name FROM bank_import_batches")):
        catalog[f"file.{batch}.{name}"] = []
    return catalog


def uploaded(db, source):
    batch = int(source.split(".", 2)[1])
    raw = db.execute(text("SELECT raw_fields FROM raw_bank_transactions WHERE import_batch_id=:id ORDER BY row_number"),
                     {"id": batch})
    rows = [json.loads(r[0]) for r in raw]
    if rows:
        return rows
    payload = db.execute(text("SELECT raw_file_bytes FROM bank_import_batches WHERE id=:id"), {"id":batch}).scalar()
    if not payload:
        return []
    if source.lower().endswith(".csv"):
        data = bytes(payload)
        try:
            decoded = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            decoded = data.decode("cp1252")
        dialect = csv.Sniffer().sniff(decoded[:8192], delimiters=",;\t|")
        return list(csv.DictReader(io.StringIO(decoded), dialect=dialect))
    raise ValueError("Per questo file non sono disponibili righe importate leggibili: " + source)


def bindings():
    return dict(who="", employee_id=None, description="", amount_minor=0, day="2000-01-01",
                transaction_id=0, source_id=None, prior_json="{}")


class Lookup:
    def __init__(self, db, step, catalog, *, populate):
        self.conn = sqlite3.connect(":memory:")
        try:
            self.prepare(db, step, catalog, populate)
        except Exception:
            self.conn.close()
            raise

    def prepare(self, db, step, catalog, populate):
        self.query = step.get("query", "").strip()
        selected = step.get("sources")
        if not isinstance(selected, list) or any(k not in catalog for k in selected):
            raise ValueError("Le fonti della verifica non sono disponibili.")
        if not self.query.lower().startswith(("select ", "select\n", "with ")):
            raise ValueError("La verifica richiede una ricerca SELECT.")
        self.conn.execute("PRAGMA trusted_schema=OFF")
        files = {}
        for index, key in enumerate(selected):
            alias = "s" + str(index+1)
            if key.startswith("file."):
                files[key] = uploaded(db, key)
                catalog[key] = list(dict.fromkeys(k for row in files[key] for k in row))
            if not catalog[key]:
                raise ValueError("Fonte senza colonne leggibili: " + key)
            cols = ",".join(quoted(c) for c in catalog[key])
            self.conn.execute(f"CREATE TABLE {alias} ({cols})")
        referenced = {}
        allowed_functions = set("abs avg cast coalesce count date datetime glob hex ifnull instr json_array_length json_extract julianday length like lower ltrim max min nullif printf replace round rtrim strftime substr sum total trim upper".split())

        def guard(op, arg, col, schema, caller):
            if op == sqlite3.SQLITE_READ:
                if arg not in {"s"+str(i+1) for i in range(len(selected))}:
                    return sqlite3.SQLITE_DENY
                referenced.setdefault(arg,set())
                if col:
                    referenced[arg].add(col)
                return sqlite3.SQLITE_OK
            if op == sqlite3.SQLITE_SELECT or (op == sqlite3.SQLITE_FUNCTION and col in allowed_functions):
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        self.conn.set_authorizer(guard)
        self.conn.execute("EXPLAIN QUERY PLAN " + self.query, bindings()).fetchall()
        if selected and not referenced:
            raise ValueError("La ricerca deve consultare almeno una fonte.")
        if populate:
            self.conn.set_authorizer(None)
            for alias, used in referenced.items():
                key = selected[int(alias[1:])-1]
                cols = [c for c in catalog[key] if c in used] or [catalog[key][0]]
                names = ",".join(map(quoted,cols))
                insert = f"INSERT INTO {alias} ({names}) VALUES (" + ",".join("?" for _ in cols) + ")"
                if key.startswith("bank."):
                    query = "SELECT "+names+" FROM "+quoted(key.split(".",1)[1])
                    self.conn.executemany(insert, db.connection().exec_driver_sql(query))
                elif key.startswith("file."):
                    self.conn.executemany(insert, ([row.get(c) for c in cols] for row in files[key]))
                else:
                    _, schema, table = key.split(".",2)
                    with closing(domain_connection()) as conn, conn.cursor(name="trial_lookup") as cur:
                        cur.execute("SELECT "+names+" FROM "+quoted(schema)+"."+quoted(table))
                        self.conn.executemany(insert, (tuple(self.scalar(v) for v in row) for row in cur))
            self.conn.set_authorizer(guard)
        self.conn.row_factory = sqlite3.Row

    @staticmethod
    def scalar(value):
        if value is None or isinstance(value,(int,float,str,bytes)):
            return value
        if isinstance(value,(dict,list)):
            return json.dumps(value, default=str)
        return str(value)

    def find(self, params):
        import time
        end = time.monotonic()+2
        self.conn.set_progress_handler(lambda: int(time.monotonic()>end), 10000)
        rows = self.conn.execute(self.query, params).fetchmany(2)
        return [dict(r) for r in rows]
