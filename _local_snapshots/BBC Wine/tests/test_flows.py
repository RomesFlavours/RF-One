"""End-to-end checks on a disposable database (created and dropped here).

Run: python tests/test_flows.py
"""

import csv
import io
import os
import re
import sys
from decimal import Decimal
from pathlib import Path

import psycopg2

PG = dict(host="127.0.0.1", port=55571, user="rfone_local")
TEST_DB = "bbc_wine_test_flows"


def admin_conn():
    c = psycopg2.connect(dbname="postgres", **PG)
    c.autocommit = True
    return c


def admin_sql(*statements):
    c = admin_conn()
    with c.cursor() as cur:
        for statement in statements:
            cur.execute(statement)
    c.close()


admin_sql(f'DROP DATABASE IF EXISTS "{TEST_DB}"', f"CREATE DATABASE \"{TEST_DB}\" TEMPLATE template0 ENCODING 'UTF8'")

os.environ.update(BBC_DATABASE_URL=f"postgresql+psycopg2://{PG['user']}@127.0.0.1:{PG['port']}/{TEST_DB}",
                  BBC_SECRET_KEY="test", BBC_LOCAL_AUTOLOGIN="1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import app as web  # noqa: E402
import models as m  # noqa: E402
from sqlalchemy import select  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

passed, failed = 0, []


def check(name, condition):
    global passed
    if condition:
        passed += 1
    else:
        failed.append(name)
        print("FAIL", name)


def token(client):
    with client.session_transaction() as s:
        s.setdefault("csrf", "tok")
        return s["csrf"]


def post(client, url, data):
    data = dict(data)
    data["csrf_token"] = token(client)
    return client.post(url, data=data)


def stock(wine_id, loc_id):
    with web.Session() as s:
        row = s.scalars(select(m.Stock).where(m.Stock.wine_id == wine_id, m.Stock.location_id == loc_id)).first()
        return row.bottles if row else 0


try:
    web.init_db()
    with web.Session() as s:
        s.add(m.Company(name="BBC WINE IMPORTS", license_number="WSL6803635", address="SARASOTA, FL",
                        payment_instructions="PLEASE PAY BY CHECK", invoice_terms_text="State beverage law"))
        a, b = m.Location(name="Sarasota"), m.Location(name="Miami")
        s.add_all([a, b])
        s.add(m.User(username="admin", full_name="Administrator", is_admin=True,
                     password_hash=generate_password_hash("adminpass1")))
        w1 = m.Wine(item_code="W0001", type_name="Cannonau", producer="Dorgali", vintage_year=2023, category="RED",
                    style="STILL", bottle_size_ml=750, bottles_per_case=12, price=Decimal("19.00"))
        w2 = m.Wine(item_code="W0002", type_name="Prosecco", producer="Casa", vintage_year=None, category="WHITE",
                    style="SPARKLING", bottle_size_ml=750, bottles_per_case=6, price=Decimal("12.50"))
        s.add_all([w1, w2])
        s.add(m.Customer(name="ROME'S FLAVOURS", bill_to="124 EAST MORSE BLVD", license_number="BEV5811917",
                         phone="407.951.8039", terms_days=10))
        s.commit()
        A, B, W1, W2 = a.id, b.id, w1.id, w2.id
        CUST = s.scalars(select(m.Customer)).first().id

    anon = web.app.test_client()
    check("Anonymous is sent to sign in", anon.get("/orders").status_code == 302)
    check("Wrong password refused", b"Wrong username" in anon.post("/login", data={"username": "admin", "password": "x"}).data)
    check("Login works", anon.post("/login", data={"username": "admin", "password": "adminpass1"}).status_code == 302)
    check("Local start refuses a non-loopback address",
          web.app.test_client().get("/local/start", environ_base={"REMOTE_ADDR": "10.0.0.5"}).status_code == 404)

    admin = web.app.test_client()
    check("Local start signs in", admin.get("/local/start?next=/inventory").status_code == 302)
    check("Inventory page", b"W0001" in admin.get("/inventory").data)
    check("POST without CSRF refused", admin.post(f"/inventory/wines/{W1}/stock", data={}).status_code == 400)
    post(admin, f"/inventory/wines/{W1}/stock", {"location_id": A, "bottles": "24", "note": ""})
    check("Adjustment needs a reason", stock(W1, A) == 0)
    post(admin, f"/inventory/wines/{W1}/stock", {"location_id": A, "bottles": "24", "note": "Physical count"})
    post(admin, f"/inventory/wines/{W2}/stock", {"location_id": B, "bottles": "6", "note": "Arrival"})
    check("Stock set", stock(W1, A) == 24 and stock(W2, B) == 6)
    check("Cases shown", b"2 cs" in admin.get("/inventory").data)

    def order_data(lines, **extra):
        data = {"customer_id": CUST, "order_date": "2026-03-04", "rep_user_id": "", "po_number": "PO1",
                "ship_via": "", "terms_days": "10", "discount_type": "AMT", "discount_value": "5", "notes": ""}
        data.update(extra)
        keys = ["line_wine", "line_location", "line_bottles", "line_price", "line_discount", "line_discount_type"]
        form = [(k, v) for k, v in data.items()]
        for line in lines:
            form += list(zip(keys, line))
        form.append(("csrf_token", token(admin)))
        return form

    from werkzeug.datastructures import MultiDict
    r = admin.post("/orders/new", data=MultiDict(order_data([(W1, A, "10", "19.00", "10", "PCT"),
                                                             (W2, B, "2", "12.50", "0", "PCT")])))
    check("Order saved", r.status_code == 302)
    order_id = int(re.search(r"/orders/(\d+)", r.headers["Location"]).group(1))
    check("Stock removed at once", stock(W1, A) == 14 and stock(W2, B) == 4)
    with web.Session() as s:
        o = s.get(m.Order, order_id)
        t = web.svc.order_totals(o)
        # 10 x 19 = 190 - 10% = 171; + 25 = 196; - 5 = 191
        check("Totals with line and order discount", t["subtotal"] == Decimal("196.00") and t["total"] == Decimal("191.00"))

    r = admin.post("/orders/new", data=MultiDict(order_data([(W1, A, "50", "19.00", "0", "PCT")])))
    check("Too many bottles refused", b"Not enough stock" in r.data)
    with web.Session() as s:
        check("Refused order not created", len(s.scalars(select(m.Order)).all()) == 1)
    check("Refused order leaves stock", stock(W1, A) == 14)

    r = admin.post(f"/orders/{order_id}/edit", data=MultiDict(order_data([(W1, A, "12", "19.00", "0", "PCT"),
                                                                          (W2, B, "6", "12.50", "0", "PCT")])))
    check("Order changed", r.status_code == 302)
    check("Change moves only the difference", stock(W1, A) == 12 and stock(W2, B) == 0)

    page = admin.get(f"/invoices/{order_id}").data.decode()
    check("Invoice has BBC and customer licenses", "WSL6803635" in page and "BEV5811917" in page)
    check("Invoice due date Net 10", "03/14/2026" in page and "Net 10" in page)
    check("Invoice total", "$298.00" in page)  # 228 + 75 - 5
    check("Invoice cases column", ">1<" in page.replace(" ", ""))

    body = admin.get("/qbo-export?from=2026-03-01&to=2026-03-31&download=1").data.decode()
    rows = list(csv.DictReader(io.StringIO(body)))
    check("QBO header", list(rows[0].keys())[0] == "InvoiceNo")
    check("QBO rows (2 wines + order discount)", len(rows) == 3 and rows[-1]["ItemAmount"] == "-5.00")
    check("QBO lines add up", sum(Decimal(r_["ItemAmount"]) for r_ in rows) == Decimal("298.00"))
    check("QBO date format", rows[0]["InvoiceDate"] == "03/04/2026" and rows[0]["DueDate"] == "03/14/2026")

    detail = admin.get(f"/customers/{CUST}").data.decode()
    check("Customer purchases", "W0001" in detail and "$298.00" in detail)

    r = post(admin, "/wine-lists/new", {"customer_id": CUST, "name": "Spring", "notes": ""})
    check("Wine list needs wines", b"Select at least one wine" in r.data)
    r = admin.post("/wine-lists/new", data=MultiDict([("customer_id", CUST), ("name", "Spring"), ("wine_id", W1),
                                                       ("wine_id", W2), ("csrf_token", token(admin))]))
    check("Wine list saved", r.status_code == 302)
    view = admin.get(r.headers["Location"]).data.decode()
    check("Wine list printable with prices", "$19.00" in view and "Print" in view and "Sparkling" in view)

    # A user with only View on Availability.
    post(admin, "/admin/users/new", {"full_name": "Mario Viewer", "username": "viewer", "password": "viewerpass",
                                     "active": "1", "fn_inventory": "1", "level_inventory": "view"})
    viewer = web.app.test_client()
    viewer.post("/login", data={"username": "viewer", "password": "viewerpass"})
    inv = viewer.get("/inventory").data
    check("Viewer sees availability", b"W0001" in inv)
    check("Viewer has no stock form or New wine", b"stock-form" not in inv and b"New wine" not in inv)
    check("Viewer cannot change stock", post(viewer, f"/inventory/wines/{W1}/stock",
                                             {"location_id": A, "bottles": "1", "note": "x"}).status_code == 403)
    check("Viewer cannot open wine editor", viewer.get(f"/inventory/wines/{W1}").status_code == 403)
    check("Viewer has no orders", viewer.get("/orders").status_code == 403)
    check("Viewer has no administration", viewer.get("/admin/users").status_code == 403)
    check("Viewer menu shows only Availability", b">Orders<" not in inv and b">Users<" not in inv)
    check("Stock untouched by viewer", stock(W1, A) == 12)

    r = post(admin, f"/orders/{order_id}/cancel", {})
    check("Cancel restores stock", stock(W1, A) == 24 and stock(W2, B) == 6)
    r = admin.get(f"/orders/{order_id}/edit")
    check("Cancelled order cannot be edited", r.status_code == 302)
    body = admin.get("/qbo-export?from=2026-03-01&to=2026-03-31&download=1").data.decode()
    check("Cancelled order not exported", body.count("\n") == 1)
    with web.Session() as s:
        moves = s.scalars(select(m.StockMovement).where(m.StockMovement.wine_id == W1)).all()
        check("Every change is in the movement log", [mv.reason for mv in moves] ==
              ["ADJUSTMENT", "ORDER", "ORDER_CHANGE", "ORDER_CANCEL"])
    check("Movements page", b"Order cancelled" in admin.get("/inventory/movements").data)

    for url in ["/orders", "/orders/new", "/customers", f"/customers/{CUST}/edit", "/customers/new", "/wine-lists",
                "/inventory/movements", "/inventory/wines/new", "/qbo-export", "/admin/company", "/admin/locations",
                "/admin/users", "/admin/users/new", f"/orders/{order_id}"]:
        check(f"Page opens {url}", admin.get(url).status_code == 200)
finally:
    web.engine.dispose()
    admin_sql(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')

print(f"{passed} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
