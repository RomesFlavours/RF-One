"""Create the local BBC Wine database and fill it once.

- creates the PostgreSQL database `bbc_wine` on the local server (127.0.0.1)
- creates the tables and the starting data (app/seed.py)
- copies the wine catalog ("Availability") ONCE from the local RF-One database
  (read-only there). After that the two systems are independent.

Local settings (database URL, session key, admin password) are kept outside
OneDrive in %LOCALAPPDATA%\\BBC Wine\\local.json.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path

import psycopg2

LOCAL_DIR = Path(os.environ["LOCALAPPDATA"]) / "BBC Wine"
CONFIG = LOCAL_DIR / "local.json"
PG = dict(host="127.0.0.1", port=55571, user="rfone_local")
RFONE_DB = "rfone_employee_directory"
DB_NAME = "bbc_wine"


def config() -> dict:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    data = {"database_url": f"postgresql+psycopg2://{PG['user']}@{PG['host']}:{PG['port']}/{DB_NAME}",
            "secret_key": secrets.token_hex(32), "port": 5110,
            "admin_username": "admin", "admin_password": secrets.token_urlsafe(12)}
    CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def ensure_database():
    conn = psycopg2.connect(dbname="postgres", **PG)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if not cur.fetchone():
            cur.execute(f"CREATE DATABASE \"{DB_NAME}\" ENCODING 'UTF8' TEMPLATE template0")
            print(f"Created database {DB_NAME}")
    conn.close()


def main():
    cfg = config()
    ensure_database()
    os.environ["BBC_DATABASE_URL"] = cfg["database_url"]
    os.environ["BBC_SECRET_KEY"] = cfg["secret_key"]
    sys.path.insert(0, str(Path(__file__).parent / "app"))
    import app as web
    from seed import RFONE_WINES_SQL, seed

    def rfone_rows():
        conn = psycopg2.connect(dbname=RFONE_DB, **PG)
        conn.set_client_encoding("UTF8")
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute(RFONE_WINES_SQL)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.close()
        return rows

    web.init_db()
    with web.Session() as s:
        print(seed(s, cfg["admin_username"], cfg["admin_password"], rfone_rows))
    print(f"Local settings: {CONFIG}")


if __name__ == "__main__":
    main()
