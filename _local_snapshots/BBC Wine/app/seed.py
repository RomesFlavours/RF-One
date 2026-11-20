"""Starting data shared by the local setup and the AWS setup. Never duplicates:
what already exists is left alone."""

from __future__ import annotations

from sqlalchemy import select
from werkzeug.security import generate_password_hash

import models as m

COMPANY = dict(
    name="BBC WINE IMPORTS",
    address="OFFICE & WAREHOUSE:\n1747 INDEPENDENCE BLVD #E10\nSARASOTA, FL 34234",
    license_number="WSL6803635",
    payment_instructions="PLEASE PAY BY CHECK\nFINTECH OR\nZELLE @239.537.7104",
    invoice_terms_text=(
        "Please examine goods before signing, all claims including breakage and/or shortage must be made at the "
        "time of receipt of shipment.\n"
        "State beverage law requires full payment of this invoice, without deductions, on or before the due date "
        "shown. Customer is responsible for reimbursement of reasonable attorney fees, collection costs, and court "
        "costs, in the event suite is filed to recover unpaid balance. BBC Wine Imports is entitled to file a suit "
        "for the gross total of this invoice including payment at regular price for goods received at no charge. "
        "No discount on free goods is allowed if invoices become delinquent."),
)

RFONE_WINES_SQL = """SELECT w.id, t.standard_name, w.producer, w.label_name, w.vintage_year, w.non_vintage,
       w.category, w.style, w.denomination, w.region, w.bottle_size_ml, w.cost_usd, w.availability, w.notes
FROM restaurant_wines w JOIN restaurant_wine_types t ON t.id = w.wine_type_id ORDER BY w.id"""


def seed(session, admin_username: str, admin_password: str, rfone_wine_rows) -> str:
    """rfone_wine_rows: a callable returning RF-One wine rows as dicts (RFONE_WINES_SQL)."""
    if session.scalars(select(m.Company)).first() is None:
        session.add(m.Company(**COMPANY))
    if session.scalars(select(m.Location)).first() is None:
        session.add(m.Location(name="Sarasota", address="1747 Independence Blvd #E10, Sarasota, FL 34234"))
    if session.scalars(select(m.User).where(m.User.username == admin_username)).first() is None:
        session.add(m.User(username=admin_username, full_name="Administrator", is_admin=True,
                           password_hash=generate_password_hash(admin_password)))
    if session.scalars(select(m.Customer)).first() is None:
        session.add(m.Customer(name="ROME'S FLAVOURS", bill_to="124 EAST MORSE BLVD\nWINTER PARK, FL 32789",
                               ship_to="124 EAST MORSE BLVD\nWINTER PARK, FL 32789", phone="407.951.8039",
                               license_number="BEV5811917", terms_days=10))
    session.commit()
    if session.scalars(select(m.Wine)).first() is not None:
        return "Wines already present: nothing copied"
    rows = rfone_wine_rows()
    for r in rows:
        session.add(m.Wine(
            item_code=f"W{r['id']:04d}", type_name=r["standard_name"], producer=r["producer"],
            label_name=r["label_name"], vintage_year=None if r["non_vintage"] else r["vintage_year"],
            category=r["category"], style=r["style"], denomination=r["denomination"], region=r["region"],
            bottle_size_ml=r["bottle_size_ml"], bottles_per_case=None, price=r["cost_usd"],
            availability=r["availability"], notes=r["notes"], source_ref=f"rfone:restaurant_wines:{r['id']}"))
    session.commit()
    return f"Copied {len(rows)} wines from RF-One Availability"
