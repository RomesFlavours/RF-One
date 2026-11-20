"""One-off AWS setup, run as an ECS task with the released image.

Creates on the RDS server a separate database `bbc_wine` owned by its own
login role `bbc_wine_app` (no access to RF-One's database), creates the
tables, writes the starting data and copies the wines ONCE from RF-One's
AWS Wines Availability (read-only query). Safe to run again.

Environment:
  RFONE_DATABASE_URL  RDS administrator URL (RF-One's secret), used only here
  BBC_DB_PASSWORD     password of bbc_wine_app (same as in the bbc-wine secret)
  BBC_ADMIN_PASSWORD  password of the BBC Wine `admin` user
"""

import os
import sys

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import make_url

admin_url = make_url(os.environ["RFONE_DATABASE_URL"])
password = os.environ["BBC_DB_PASSWORD"]
conn_args = dict(host=admin_url.host, port=admin_url.port or 5432, user=admin_url.username,
                 password=admin_url.password, sslmode="require")

c = psycopg2.connect(dbname=admin_url.database, **conn_args)
c.autocommit = True
with c.cursor() as cur:
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'bbc_wine_app'")
    if cur.fetchone():
        cur.execute(sql.SQL("ALTER ROLE bbc_wine_app WITH LOGIN PASSWORD {}").format(sql.Literal(password)))
    else:
        cur.execute(sql.SQL("CREATE ROLE bbc_wine_app WITH LOGIN PASSWORD {}").format(sql.Literal(password)))
        print("Created role bbc_wine_app")
    cur.execute(sql.SQL("GRANT bbc_wine_app TO {}").format(sql.Identifier(admin_url.username)))
    cur.execute("SELECT 1 FROM pg_database WHERE datname = 'bbc_wine'")
    if not cur.fetchone():
        cur.execute("CREATE DATABASE bbc_wine OWNER bbc_wine_app ENCODING 'UTF8' TEMPLATE template0")
        print("Created database bbc_wine")
    cur.execute("REVOKE ALL ON DATABASE bbc_wine FROM PUBLIC")
    cur.execute("GRANT CONNECT, TEMP ON DATABASE bbc_wine TO bbc_wine_app")
    cur.execute(f"REVOKE CONNECT ON DATABASE {admin_url.database} FROM bbc_wine_app")


def rfone_rows():
    # The catalog shipped with the image (copied from RF-One's Wines Availability
    # in the Product Owner's local environment) wins over RF-One's AWS table.
    seed_file = "/app/wines_seed.json"
    if os.path.exists(seed_file):
        import json
        from decimal import Decimal
        rows = json.load(open(seed_file, encoding="utf-8"))
        for r in rows:
            r["cost_usd"] = Decimal(r["cost_usd"]) if r["cost_usd"] is not None else None
        return rows
    from seed import RFONE_WINES_SQL
    with c.cursor() as cur:  # a SELECT only: RF-One's data is never changed
        cur.execute(RFONE_WINES_SQL)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


app_url = admin_url.set(username="bbc_wine_app", password=password, database="bbc_wine",
                        query={"sslmode": "require"})
os.environ["BBC_DATABASE_URL"] = app_url.render_as_string(hide_password=False)
os.environ.setdefault("BBC_SECRET_KEY", "setup-only")
sys.path.insert(0, "/app")
import app as web  # noqa: E402
from seed import seed  # noqa: E402

web.init_db()
with web.Session() as s:
    import models as m
    from sqlalchemy import delete, func, select
    if os.environ.get("BBC_REPLACE_WINES") == "1":
        used = (s.scalar(select(func.count()).select_from(m.OrderLine)) or 0) +                (s.scalar(select(func.count()).select_from(m.WineListItem)) or 0) +                (s.scalar(select(func.count()).select_from(m.StockMovement)) or 0)
        if used:
            print("Wines are already used by orders, lists or stock: catalog NOT replaced")
        else:
            s.execute(delete(m.Stock))
            s.execute(delete(m.Wine))
            s.commit()
            print("Empty catalog replaced")
    print(seed(s, "admin", os.environ["BBC_ADMIN_PASSWORD"], rfone_rows))
    print("Wines in bbc_wine:", s.scalar(select(func.count()).select_from(m.Wine)))
c.close()
print("BBC setup complete")
