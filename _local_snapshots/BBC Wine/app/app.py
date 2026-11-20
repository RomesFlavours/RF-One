"""BBC Wine — inventory, customer wine lists, orders, invoices and QBO export.

Configuration (environment):
  BBC_DATABASE_URL   SQLAlchemy URL of the PostgreSQL database (required)
  BBC_SECRET_KEY     Flask session key (required)
  BBC_LOCAL_AUTOLOGIN=1  only for the loopback local launcher: /local/start
                     signs in the first active administrator without a password.
"""

from __future__ import annotations

import os
import secrets
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import (Flask, Response, abort, flash, g, redirect, render_template, request, session, url_for)
from sqlalchemy import create_engine, func, or_, select
from sqlalchemy.orm import joinedload, selectinload, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash

import models as m
import services as svc
from services import RuleError

app = Flask(__name__)
app.secret_key = os.environ["BBC_SECRET_KEY"]
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("BBC_SECURE_COOKIES") == "1")
engine = create_engine(os.environ["BBC_DATABASE_URL"], pool_pre_ping=True, future=True)
Session = sessionmaker(engine, expire_on_commit=False)
LOCAL_AUTOLOGIN = os.environ.get("BBC_LOCAL_AUTOLOGIN") == "1"


def init_db():
    m.Base.metadata.create_all(engine)


# ---------------------------------------------------------------- request plumbing

@app.before_request
def open_session():
    g.db = Session()
    g.user = None
    uid = session.get("uid")
    if uid:
        user = g.db.get(m.User, uid)
        if user and user.active:
            g.user = user
    if request.method == "POST" and request.endpoint not in ("login",):
        if not secrets.compare_digest(request.form.get("csrf_token", ""), session.get("csrf", "-")):
            abort(400, "The form expired. Reload the page and try again.")


@app.teardown_request
def close_session(exc):
    db = g.pop("db", None)
    if db is not None:
        if exc:
            db.rollback()
        db.close()


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


@app.context_processor
def globals_for_templates():
    company = g.db.scalars(select(m.Company)).first() if hasattr(g, "db") else None
    return {"csrf_token": csrf_token, "user": g.get("user"), "company": company, "m": m,
            "may": may, "may_edit": may_edit, "money": svc.money, "cases": svc.cases_label}


@app.template_filter("usd")
def usd(value):
    return "" if value is None else f"${svc.money(value):,.2f}"


@app.template_filter("d")
def us_date(value):
    return value.strftime("%m/%d/%Y") if value else ""


def may(function: str) -> bool:
    return bool(g.user and g.user.level(function))


def may_edit(function: str) -> bool:
    return bool(g.user and g.user.level(function) == m.LEVEL_USER)


def needs(function: str | None = None, edit: bool = False):
    """Signed-in user with the function (and the User level for changes)."""
    def wrap(view):
        @wraps(view)
        def inner(*args, **kwargs):
            if g.user is None:
                return redirect(url_for("login", next=request.full_path))
            if function == "admin":
                if not g.user.is_admin:
                    abort(403)
            elif function and not may(function):
                abort(403)
            elif function and (edit or request.method == "POST") and not may_edit(function):
                abort(403)
            return view(*args, **kwargs)
        return inner
    return wrap


def text(name, limit=None):
    value = (request.form.get(name) or "").strip()
    return value[:limit] if limit else value


def optional(name, limit=None):
    return text(name, limit) or None


def as_int(value, label, minimum=None):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise RuleError(f"{label} must be a whole number.")
    if minimum is not None and number < minimum:
        raise RuleError(f"{label} must be at least {minimum}.")
    return number


def as_decimal(value, label, allow_empty=False):
    value = (value or "").strip().replace("$", "").replace(",", "")
    if not value:
        if allow_empty:
            return None
        return Decimal("0")
    try:
        return Decimal(value)
    except InvalidOperation:
        raise RuleError(f"{label} must be a number.")


def locations():
    return g.db.scalars(select(m.Location).where(m.Location.active).order_by(m.Location.id)).all()


def reps():
    return g.db.scalars(select(m.User).where(m.User.is_rep, m.User.active).order_by(m.User.full_name)).all()


@app.errorhandler(403)
def forbidden(e):
    return render_template("message.html", title="Not allowed",
                           message="Your account does not have access to this function."), 403


# ---------------------------------------------------------------- sign in

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = g.db.scalars(select(m.User).where(func.lower(m.User.username) == text("username").lower())).first()
        if user and user.active and user.password_hash and check_password_hash(user.password_hash,
                                                                               request.form.get("password", "")):
            session.clear()
            session["uid"] = user.id
            target = request.args.get("next") or ""
            return redirect(target if target.startswith("/") and not target.startswith("//") else url_for("home"))
        error = "Wrong username or password."
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/local/start")
def local_start():
    """Local launcher only: sign in the first active administrator, loopback only."""
    if not LOCAL_AUTOLOGIN or request.remote_addr not in ("127.0.0.1", "::1"):
        abort(404)
    admin = g.db.scalars(select(m.User).where(m.User.is_admin, m.User.active).order_by(m.User.id)).first()
    if admin is None:
        abort(404)
    session.clear()
    session["uid"] = admin.id
    target = request.args.get("next") or "/"
    return redirect(target if target.startswith("/") and not target.startswith("//") else "/")


@app.route("/")
@needs()
def home():
    for function, endpoint in (("orders", "orders"), ("inventory", "inventory"), ("customers", "customers"),
                               ("wine_lists", "wine_lists"), ("invoices", "qbo_export")):
        if may(function):
            return redirect(url_for(endpoint))
    if g.user.is_admin:
        return redirect(url_for("company_settings"))
    return render_template("message.html", title="No functions",
                           message="Your account has no functions yet. Ask an administrator.")


# ---------------------------------------------------------------- availability & inventory

@app.route("/inventory")
@needs("inventory")
def inventory():
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status") or ""
    stmt = select(m.Wine).options(selectinload(m.Wine.stocks)).order_by(m.Wine.type_name, m.Wine.producer,
                                                                        m.Wine.label_name)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(m.Wine.type_name.ilike(like), m.Wine.producer.ilike(like),
                              m.Wine.label_name.ilike(like), m.Wine.item_code.ilike(like),
                              m.Wine.region.ilike(like)))
    if status in m.AVAILABILITIES:
        stmt = stmt.where(m.Wine.availability == status)
    wines = g.db.scalars(stmt).all()
    return render_template("inventory.html", wines=wines, locations=locations(), q=q, status=status)


@app.route("/inventory/wines/new", methods=["GET", "POST"])
@app.route("/inventory/wines/<int:wine_id>", methods=["GET", "POST"])
@needs("inventory", edit=True)
def wine_edit(wine_id=None):
    wine = g.db.get(m.Wine, wine_id) if wine_id else m.Wine(category="RED", style="STILL", bottle_size_ml=750,
                                                             availability="AVAILABLE", bottles_per_case=12)
    if wine is None:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            vintage = optional("vintage_year")
            fields = dict(
                item_code=text("item_code", 30), type_name=text("type_name", 120), producer=text("producer", 160),
                label_name=optional("label_name", 200),
                vintage_year=as_int(vintage, "Vintage", 1900) if vintage else None,
                category=text("category"), style=text("style"), denomination=optional("denomination", 80),
                region=optional("region", 80), bottle_size_ml=as_int(text("bottle_size_ml"), "Bottle size", 1),
                bottles_per_case=as_int(text("bottles_per_case"), "Bottles per case", 1)
                if text("bottles_per_case") else None,
                price=as_decimal(text("price"), "Price", allow_empty=True),
                availability=text("availability"), notes=optional("notes"))
            if not fields["item_code"] or not fields["type_name"] or not fields["producer"]:
                raise RuleError("Item code, wine type and producer are required.")
            if fields["category"] not in m.CATEGORIES or fields["style"] not in m.STYLES \
                    or fields["availability"] not in m.AVAILABILITIES:
                raise RuleError("Choose category, style and availability.")
            if fields["price"] is not None and fields["price"] < 0:
                raise RuleError("The price cannot be negative.")
            clash = g.db.scalars(select(m.Wine).where(m.Wine.item_code == fields["item_code"])).first()
            if clash and clash is not wine:
                raise RuleError(f"Item code {fields['item_code']} is already used by {clash.display_name}.")
            for key, value in fields.items():
                setattr(wine, key, value)
            if wine.id is None:
                g.db.add(wine)
            g.db.commit()
            flash(f"Saved {wine.display_name}.")
            return redirect(url_for("inventory", _anchor=f"wine-{wine.id}"))
        except RuleError as exc:
            g.db.rollback()
            error = str(exc)
    return render_template("wine_edit.html", wine=wine, error=error)


@app.route("/inventory/wines/<int:wine_id>/stock", methods=["POST"])
@needs("inventory", edit=True)
def stock_set(wine_id):
    wine = g.db.get(m.Wine, wine_id) or abort(404)
    try:
        location_id = as_int(text("location_id"), "Location")
        svc.set_stock(g.db, wine.id, location_id, as_int(text("bottles"), "Bottles", 0), text("note", 300),
                      g.user.id)
        g.db.commit()
        flash(f"Stock of {wine.display_name} updated.")
    except RuleError as exc:
        g.db.rollback()
        flash(str(exc), "error")
    return redirect(request.form.get("back") or url_for("inventory", _anchor=f"wine-{wine.id}"))


@app.route("/inventory/movements")
@needs("inventory")
def movements():
    wine_id = request.args.get("wine", type=int)
    stmt = select(m.StockMovement).options(joinedload(m.StockMovement.wine), joinedload(m.StockMovement.location),
                                           joinedload(m.StockMovement.user)).order_by(m.StockMovement.id.desc())
    wine = g.db.get(m.Wine, wine_id) if wine_id else None
    if wine:
        stmt = stmt.where(m.StockMovement.wine_id == wine.id)
    rows = g.db.scalars(stmt.limit(500)).all()
    return render_template("movements.html", rows=rows, wine=wine)


# ---------------------------------------------------------------- customers & purchases

@app.route("/customers")
@needs("customers")
def customers():
    q = (request.args.get("q") or "").strip()
    stmt = select(m.Customer).options(joinedload(m.Customer.rep)).order_by(m.Customer.name)
    if q:
        stmt = stmt.where(or_(m.Customer.name.ilike(f"%{q}%"), m.Customer.license_number.ilike(f"%{q}%")))
    return render_template("customers.html", rows=g.db.scalars(stmt).all(), q=q)


@app.route("/customers/new", methods=["GET", "POST"])
@app.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
@needs("customers", edit=True)
def customer_edit(customer_id=None):
    customer = g.db.get(m.Customer, customer_id) if customer_id else m.Customer(terms_days=10, active=True)
    if customer is None:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            name = text("name", 160)
            if not name:
                raise RuleError("The customer name is required.")
            clash = g.db.scalars(select(m.Customer).where(func.lower(m.Customer.name) == name.lower())).first()
            if clash and clash is not customer:
                raise RuleError(f"A customer named {clash.name} already exists.")
            rep_id = text("rep_user_id")
            customer.name = name
            customer.bill_to = optional("bill_to")
            customer.ship_to = optional("ship_to")
            customer.phone = optional("phone", 60)
            customer.email = optional("email", 160)
            customer.license_number = optional("license_number", 60)
            customer.terms_days = as_int(text("terms_days") or "0", "Terms", 0)
            customer.rep_user_id = int(rep_id) if rep_id else None
            customer.notes = optional("notes")
            customer.active = request.form.get("active") == "1"
            if customer.id is None:
                g.db.add(customer)
            g.db.commit()
            flash(f"Saved {customer.name}.")
            return redirect(url_for("customer_detail", customer_id=customer.id))
        except RuleError as exc:
            g.db.rollback()
            error = str(exc)
    return render_template("customer_edit.html", customer=customer, reps=reps(), error=error)


@app.route("/customers/<int:customer_id>")
@needs("customers")
def customer_detail(customer_id):
    customer = g.db.get(m.Customer, customer_id) or abort(404)
    start = request.args.get("from") or ""
    end = request.args.get("to") or ""
    stmt = (select(m.Order).options(selectinload(m.Order.lines)).where(m.Order.customer_id == customer.id)
            .order_by(m.Order.order_date.desc(), m.Order.id.desc()))
    try:
        if start:
            stmt = stmt.where(m.Order.order_date >= date.fromisoformat(start))
        if end:
            stmt = stmt.where(m.Order.order_date <= date.fromisoformat(end))
    except ValueError:
        flash("Dates must be valid.", "error")
    orders = g.db.scalars(stmt).all()
    open_orders = [o for o in orders if o.status == m.ORDER_OPEN]
    by_wine = {}
    for order in open_orders:
        for line, t in zip(order.lines, svc.order_totals(order)["lines"]):
            row = by_wine.setdefault(line.item_code, {"description": line.description, "bottles": 0,
                                                      "amount": Decimal("0"), "last": order.order_date,
                                                      "per_case": line.bottles_per_case})
            row["bottles"] += line.bottles
            row["amount"] += t["net"]
            row["last"] = max(row["last"], order.order_date)
    totals = {o.id: svc.order_totals(o) for o in orders}
    purchased = sorted(by_wine.items(), key=lambda kv: -kv[1]["bottles"])
    return render_template("customer_detail.html", customer=customer, orders=orders, totals=totals,
                           purchased=purchased, start=start, end=end,
                           grand=sum((totals[o.id]["total"] for o in open_orders), Decimal("0")))


# ---------------------------------------------------------------- customer wine lists

@app.route("/wine-lists")
@needs("wine_lists")
def wine_lists():
    rows = g.db.scalars(select(m.WineList).options(joinedload(m.WineList.customer), selectinload(m.WineList.items))
                        .order_by(m.WineList.created_on.desc(), m.WineList.id.desc())).all()
    return render_template("wine_lists.html", rows=rows)


@app.route("/wine-lists/new", methods=["GET", "POST"])
@app.route("/wine-lists/<int:list_id>/edit", methods=["GET", "POST"])
@needs("wine_lists", edit=True)
def wine_list_edit(list_id=None):
    wine_list = g.db.get(m.WineList, list_id) if list_id else m.WineList()
    if wine_list is None:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            name = text("name", 160)
            customer_id = text("customer_id")
            if not name or not customer_id:
                raise RuleError("Choose the customer and give the list a name.")
            wine_ids = {int(v) for v in request.form.getlist("wine_id") if v.isdigit()}
            if not wine_ids:
                raise RuleError("Select at least one wine.")
            wine_list.name = name
            wine_list.customer_id = int(customer_id)
            wine_list.notes = optional("notes")
            keep = [item for item in wine_list.items if item.wine_id in wine_ids]
            wine_list.items[:] = keep
            have = {item.wine_id for item in keep}
            for wine_id in sorted(wine_ids - have):
                wine_list.items.append(m.WineListItem(wine_id=wine_id))
            if wine_list.id is None:
                g.db.add(wine_list)
            g.db.commit()
            flash(f"Saved wine list {wine_list.name}.")
            return redirect(url_for("wine_list_view", list_id=wine_list.id))
        except RuleError as exc:
            g.db.rollback()
            error = str(exc)
    customers_ = g.db.scalars(select(m.Customer).where(m.Customer.active).order_by(m.Customer.name)).all()
    wines = g.db.scalars(select(m.Wine).options(selectinload(m.Wine.stocks))
                         .order_by(m.Wine.type_name, m.Wine.producer, m.Wine.label_name)).all()
    selected = {item.wine_id for item in wine_list.items}
    if request.method == "POST":
        selected = {int(v) for v in request.form.getlist("wine_id") if v.isdigit()}
    preset = request.args.get("customer", type=int)
    return render_template("wine_list_edit.html", wine_list=wine_list, customers=customers_, wines=wines,
                           selected=selected, error=error, preset=preset)


@app.route("/wine-lists/<int:list_id>")
@needs("wine_lists")
def wine_list_view(list_id):
    wine_list = g.db.get(m.WineList, list_id) or abort(404)
    groups = {}
    for item in sorted(wine_list.items, key=lambda i: (i.wine.category, i.wine.type_name, i.wine.producer)):
        groups.setdefault(m.CATEGORIES.get(item.wine.category, item.wine.category), []).append(item.wine)
    return render_template("wine_list_view.html", wine_list=wine_list, groups=groups)


@app.route("/wine-lists/<int:list_id>/delete", methods=["POST"])
@needs("wine_lists", edit=True)
def wine_list_delete(list_id):
    wine_list = g.db.get(m.WineList, list_id) or abort(404)
    g.db.delete(wine_list)
    g.db.commit()
    flash("Wine list deleted.")
    return redirect(url_for("wine_lists"))


# ---------------------------------------------------------------- orders

@app.route("/orders")
@needs("orders")
def orders():
    status = request.args.get("status") or m.ORDER_OPEN
    stmt = (select(m.Order).options(joinedload(m.Order.customer), joinedload(m.Order.rep),
                                    selectinload(m.Order.lines)).order_by(m.Order.id.desc()))
    if status in (m.ORDER_OPEN, m.ORDER_CANCELLED):
        stmt = stmt.where(m.Order.status == status)
    rows = g.db.scalars(stmt.limit(300)).all()
    return render_template("orders.html", rows=rows, totals={o.id: svc.order_totals(o) for o in rows},
                           status=status)


def _order_form_lines():
    wine_ids = request.form.getlist("line_wine")
    out = []
    for i, wine_id in enumerate(wine_ids):
        if not wine_id:
            continue
        row = i + 1
        out.append(svc.LineInput(
            wine_id=as_int(wine_id, f"Line {row} wine"),
            location_id=as_int(request.form.getlist("line_location")[i], f"Line {row} location"),
            bottles=as_int(request.form.getlist("line_bottles")[i], f"Line {row} bottles", 1),
            unit_price=as_decimal(request.form.getlist("line_price")[i], f"Line {row} price"),
            discount_type=request.form.getlist("line_discount_type")[i] if
            request.form.getlist("line_discount_type")[i] in (m.DISCOUNT_PERCENT, m.DISCOUNT_AMOUNT)
            else m.DISCOUNT_PERCENT,
            discount_value=as_decimal(request.form.getlist("line_discount")[i], f"Line {row} discount")))
    return out


@app.route("/orders/new", methods=["GET", "POST"])
@app.route("/orders/<int:order_id>/edit", methods=["GET", "POST"])
@needs("orders", edit=True)
def order_edit(order_id=None):
    order = g.db.get(m.Order, order_id) if order_id else None
    if order_id and order is None:
        abort(404)
    if order is not None and order.status != m.ORDER_OPEN:
        flash("A cancelled order cannot be changed.", "error")
        return redirect(url_for("order_view", order_id=order.id))
    error = None
    form_lines = None
    if request.method == "POST":
        try:
            customer = g.db.get(m.Customer, as_int(text("customer_id") or "0", "Customer"))
            if customer is None:
                raise RuleError("Choose the customer.")
            target = order or m.Order(created_by_id=g.user.id, status=m.ORDER_OPEN)
            target.customer_id = customer.id
            target.order_date = date.fromisoformat(text("order_date")) if text("order_date") else date.today()
            rep_id = text("rep_user_id")
            target.rep_user_id = int(rep_id) if rep_id else None
            target.po_number = optional("po_number", 60)
            target.ship_via = optional("ship_via", 60)
            target.terms_days = as_int(text("terms_days") or "0", "Terms", 0)
            target.discount_type = text("discount_type") if text("discount_type") in (
                m.DISCOUNT_PERCENT, m.DISCOUNT_AMOUNT) else m.DISCOUNT_PERCENT
            target.discount_value = as_decimal(text("discount_value"), "Order discount")
            target.notes = optional("notes")
            lines = _order_form_lines()
            form_lines = lines
            with g.db.no_autoflush:
                svc.save_order(g.db, target, lines, g.user.id)
            g.db.commit()
            flash(f"Order {target.id} saved. Stock updated.")
            return redirect(url_for("order_view", order_id=target.id))
        except (RuleError, ValueError) as exc:
            g.db.rollback()
            error = str(exc) if isinstance(exc, RuleError) else "Check the dates and numbers in the order."
            if order is not None:
                order = g.db.get(m.Order, order.id)
    customers_ = g.db.scalars(select(m.Customer).where(m.Customer.active).order_by(m.Customer.name)).all()
    wines = g.db.scalars(select(m.Wine).options(selectinload(m.Wine.stocks))
                         .order_by(m.Wine.type_name, m.Wine.producer, m.Wine.label_name)).all()
    # Stock shown to the rep = what is on the shelf plus what this order already holds.
    held = {}
    if order is not None:
        for line in order.lines:
            held[(line.wine_id, line.location_id)] = held.get((line.wine_id, line.location_id), 0) + line.bottles
    catalog = {w.id: {"name": w.display_name, "code": w.item_code, "size": w.bottle_size_ml,
                      "price": str(w.price) if w.price is not None else "", "case": w.bottles_per_case,
                      "stock": {loc.id: w.stock_at(loc.id) + held.get((w.id, loc.id), 0) for loc in locations()}}
               for w in wines}
    if form_lines is not None:
        initial = [{"wine": l.wine_id, "location": l.location_id, "bottles": l.bottles, "price": str(l.unit_price),
                    "dtype": l.discount_type, "discount": str(l.discount_value)} for l in form_lines]
    elif order is not None:
        initial = [{"wine": l.wine_id, "location": l.location_id, "bottles": l.bottles, "price": str(l.unit_price),
                    "dtype": l.discount_type, "discount": str(l.discount_value)} for l in order.lines]
    else:
        initial = []
    customer_info = {c.id: {"terms": c.terms_days, "rep": c.rep_user_id or ""} for c in customers_}
    return render_template("order_edit.html", order=order, customers=customers_, wines=wines, catalog=catalog,
                           locations=locations(), reps=reps(), initial=initial, error=error,
                           customer_info=customer_info, form=request.form if request.method == "POST" else None,
                           today=date.today().isoformat(), preset=request.args.get("customer", type=int))


@app.route("/orders/<int:order_id>")
@needs("orders")
def order_view(order_id):
    order = g.db.get(m.Order, order_id) or abort(404)
    return render_template("order_view.html", order=order, totals=svc.order_totals(order), due=svc.due_date(order))


@app.route("/orders/<int:order_id>/cancel", methods=["POST"])
@needs("orders", edit=True)
def order_cancel(order_id):
    order = g.db.get(m.Order, order_id) or abort(404)
    try:
        svc.cancel_order(g.db, order, g.user.id)
        g.db.commit()
        flash(f"Order {order.id} cancelled. Its bottles are back in stock.")
    except RuleError as exc:
        g.db.rollback()
        flash(str(exc), "error")
    return redirect(url_for("order_view", order_id=order_id))


# ---------------------------------------------------------------- invoices & QBO

@app.route("/invoices/<int:order_id>")
@needs("invoices")
def invoice(order_id):
    order = g.db.get(m.Order, order_id) or abort(404)
    return render_template("invoice.html", order=order, totals=svc.order_totals(order), due=svc.due_date(order))


@app.route("/qbo-export")
@needs("invoices")
def qbo_export():
    start = request.args.get("from") or date.today().replace(day=1).isoformat()
    end = request.args.get("to") or date.today().isoformat()
    try:
        d1, d2 = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        d1, d2 = date.today().replace(day=1), date.today()
        start, end = d1.isoformat(), d2.isoformat()
    rows = g.db.scalars(select(m.Order).options(joinedload(m.Order.customer), selectinload(m.Order.lines))
                        .where(m.Order.status == m.ORDER_OPEN, m.Order.order_date >= d1, m.Order.order_date <= d2)
                        .order_by(m.Order.id)).all()
    if request.args.get("download"):
        body = svc.qbo_invoices_csv(rows)
        return Response(body, mimetype="text/csv", headers={
            "Content-Disposition": f'attachment; filename="qbo-invoices-{start}-to-{end}.csv"'})
    return render_template("qbo_export.html", rows=rows, totals={o.id: svc.order_totals(o) for o in rows},
                           start=start, end=end)


# ---------------------------------------------------------------- administration

@app.route("/admin/company", methods=["GET", "POST"])
@needs("admin")
def company_settings():
    company = g.db.scalars(select(m.Company)).first() or m.Company(name="")
    if request.method == "POST":
        company.name = text("name", 160) or company.name
        company.address = optional("address")
        company.phone = optional("phone", 60)
        company.email = optional("email", 160)
        company.license_number = optional("license_number", 60)
        company.payment_instructions = optional("payment_instructions")
        company.invoice_terms_text = optional("invoice_terms_text")
        if company.id is None:
            g.db.add(company)
        g.db.commit()
        flash("Company data saved.")
        return redirect(url_for("company_settings"))
    return render_template("company.html", c=company)


@app.route("/admin/locations", methods=["GET", "POST"])
@needs("admin")
def locations_page():
    if request.method == "POST":
        loc_id = text("id")
        loc = g.db.get(m.Location, int(loc_id)) if loc_id else m.Location()
        name = text("name", 120)
        if not name:
            flash("The location name is required.", "error")
            return redirect(url_for("locations_page"))
        clash = g.db.scalars(select(m.Location).where(func.lower(m.Location.name) == name.lower())).first()
        if clash and clash is not loc:
            flash(f"A location named {clash.name} already exists.", "error")
            return redirect(url_for("locations_page"))
        loc.name, loc.address = name, optional("address")
        loc.active = request.form.get("active") == "1" or loc.id is None
        if loc.id is None:
            g.db.add(loc)
        g.db.commit()
        flash(f"Location {loc.name} saved.")
        return redirect(url_for("locations_page"))
    rows = g.db.scalars(select(m.Location).order_by(m.Location.id)).all()
    stock = dict(g.db.execute(select(m.Stock.location_id, func.sum(m.Stock.bottles)).group_by(m.Stock.location_id)).all())
    return render_template("locations.html", rows=rows, stock=stock)


@app.route("/admin/users")
@needs("admin")
def users():
    rows = g.db.scalars(select(m.User).options(selectinload(m.User.permissions)).order_by(m.User.full_name)).all()
    return render_template("users.html", rows=rows)


@app.route("/admin/users/new", methods=["GET", "POST"])
@app.route("/admin/users/<int:user_id>", methods=["GET", "POST"])
@needs("admin")
def user_edit(user_id=None):
    target = g.db.get(m.User, user_id) if user_id else m.User(active=True)
    if target is None:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            username = text("username", 60)
            full_name = text("full_name", 120)
            if not username or not full_name:
                raise RuleError("Username and full name are required.")
            clash = g.db.scalars(select(m.User).where(func.lower(m.User.username) == username.lower())).first()
            if clash and clash is not target:
                raise RuleError(f"The username {username} is already used.")
            password = request.form.get("password") or ""
            if target.id is None and len(password) < 8:
                raise RuleError("Give the new user a password of at least 8 characters.")
            if password and len(password) < 8:
                raise RuleError("The password must have at least 8 characters.")
            make_admin = request.form.get("is_admin") == "1"
            make_active = request.form.get("active") == "1"
            if target is g.user and (not make_admin or not make_active):
                raise RuleError("You cannot remove your own administrator access or deactivate yourself.")
            target.username, target.full_name = username, full_name
            target.is_admin, target.is_rep, target.active = make_admin, request.form.get("is_rep") == "1", make_active
            if password:
                target.password_hash = generate_password_hash(password)
            wanted = {}
            for function in m.FUNCTIONS:
                if request.form.get(f"fn_{function}") == "1":
                    level = request.form.get(f"level_{function}")
                    wanted[function] = level if level in m.LEVELS else m.LEVEL_USER
            target.permissions[:] = [p for p in target.permissions if p.function in wanted]
            for p in target.permissions:
                p.level = wanted.pop(p.function)
            for function, level in wanted.items():
                target.permissions.append(m.Permission(function=function, level=level))
            if target.id is None:
                g.db.add(target)
            g.db.commit()
            flash(f"Saved user {target.full_name}.")
            return redirect(url_for("users"))
        except RuleError as exc:
            g.db.rollback()
            error = str(exc)
    granted = {p.function: p.level for p in target.permissions}
    return render_template("user_edit.html", target=target, granted=granted, error=error)


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=int(os.environ.get("BBC_PORT", "5110")))
