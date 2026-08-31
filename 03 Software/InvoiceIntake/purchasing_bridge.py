"""Bridge from InvoiceIntake's OCR/review output to the canonical RF-One
Purchasing persistence layer (TASK_PURCHASING_004).

Before this task, `excel_store.py` was the only persistence InvoiceIntake
had — a reduced, ad hoc subset of `01 Domains/Restaurant/Purchasing/
DataDictionary.md` written straight to an Excel workbook. This module
replaces that role: the reviewed header/lines the user confirms in
`review.html` are mapped onto the canonical `PurchaseDocument`/`PurchaseLine`
model and written through `rfone_data_store.purchasing.repository`, the
same persistence module Physical Receiving uses. `excel_store.py` itself is
untouched and still available as a secondary export/debugging capability
(`app.py` calls both, but only this module's result is the canonical
PurchaseDocumentId shown to the user) — see `03 Software/RF-One Data
Store/PURCHASING.md`.

This module deliberately does NOT invent facts the OCR/parser did not
extract: an unparsed date or amount is passed through as `None` (Unknown),
never defaulted, matching Purchasing/EntityDefinitions.md's "extract what
the source knows; do not invent what the source does not know."
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import (  # noqa: E402
    create_configured_engine,
    create_session_factory,
    get_database_url,
    run_migrations_to_head,
)
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.purchasing import repository as repo  # noqa: E402

UTC = timezone.utc

_DATE_FORMATS = ("%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y", "%Y-%m-%d")

_SURCHARGE_KEYWORDS = ("surcharge", "delivery fee", "fuel", "service fee", "environmental fee")
_DISCOUNT_KEYWORDS = ("discount", "credit", "rebate", "bonus")


def guess_line_type(description: str) -> str:
    """Best-effort default only — the review screen lets the user correct
    it before anything is saved, consistent with "human validation always
    prevails" (`01 Domains/Restaurant/Purchasing/BusinessRules.md`,
    Design Principles)."""

    lowered = (description or "").lower()
    if any(keyword in lowered for keyword in _SURCHARGE_KEYWORDS):
        return "SURCHARGE"
    if any(keyword in lowered for keyword in _DISCOUNT_KEYWORDS):
        return "DISCOUNT"
    return "PRODUCT"


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None  # unparsed -> Unknown, never guessed


def _parse_money_minor(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", str(raw))
    if cleaned in ("", "-", "."):
        return None
    try:
        return int((Decimal(cleaned) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None


def _parse_decimal(raw: str | None) -> Decimal | None:
    if raw is None or raw == "":
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", str(raw))
    if cleaned in ("", "-", "."):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _get_or_create_default_restaurant(session) -> int:
    """InvoiceIntake has no restaurant-selection UI yet (out of scope for
    this task — see PURCHASING.md, "Remaining gaps"). Reuses the single
    existing `Restaurant` row when there is exactly one (the normal case for
    this repository's current single-restaurant data), otherwise creates a
    clearly-labeled placeholder row rather than guessing which one applies.
    """

    from sqlalchemy import select

    restaurants = session.scalars(select(m.Restaurant)).all()
    if len(restaurants) == 1:
        return restaurants[0].id
    for restaurant in restaurants:
        if restaurant.name == "InvoiceIntake Default Restaurant":
            return restaurant.id
    placeholder = m.Restaurant(name="InvoiceIntake Default Restaurant")
    session.add(placeholder)
    session.flush()
    return placeholder.id


def save_purchase_document(header: dict, lines: list[dict], source_file: str) -> int:
    """Maps InvoiceIntake's reviewed header/lines onto the canonical model
    and persists them. Returns the new `PurchaseDocumentId`.

    `header` keys (from `app.py`'s `/save` route): supplier_name,
    document_number, document_type, issue_date, acquisition_method,
    currency, total_amount.
    `lines` items: description, quantity, unit, unit_price, line_amount,
    line_type (added by the review form; defaults to PRODUCT if absent).
    """

    url = get_database_url()
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        restaurant_id = _get_or_create_default_restaurant(session)
        supplier_name = header.get("supplier_name") or "Unknown Supplier"
        supplier = repo.get_or_create_supplier(session, restaurant_id, supplier_name)

        document_header = {
            "document_number": header.get("document_number") or None,
            "document_type": header.get("document_type") or "Invoice",
            "issue_date": _parse_date(header.get("issue_date")),
            "acquisition_method": header.get("acquisition_method") or None,
            "currency": header.get("currency") or None,
            "total_amount_minor": _parse_money_minor(header.get("total_amount")),
            "status": "RECORDED",
            "source_reference": source_file or None,
            "source_provenance": (
                f"InvoiceIntake upload; raw issue_date as read: {header.get('issue_date')!r}"
                if header.get("issue_date") and _parse_date(header.get("issue_date")) is None
                else "InvoiceIntake upload"
            ),
        }

        repository_lines = []
        for line in lines:
            description = (line.get("description") or "").strip()
            quantity = _parse_decimal(line.get("quantity"))
            unit_price_minor = _parse_money_minor(line.get("unit_price"))
            line_amount_minor = _parse_money_minor(line.get("line_amount"))
            if not description and quantity is None and unit_price_minor is None and line_amount_minor is None:
                continue  # a fully blank review row, never persisted

            line_type = line.get("line_type") or guess_line_type(description)
            repository_lines.append(
                {
                    "line_type": line_type,
                    "raw_description": description or "(no description)",
                    "source_amount_minor": line_amount_minor,
                    "quantity": quantity if line_type == "PRODUCT" else None,
                    "purchase_unit": (line.get("unit") or None) if line_type == "PRODUCT" else None,
                    "unit_price_minor": unit_price_minor if line_type == "PRODUCT" else None,
                }
            )

        document = repo.record_purchase_document(session, supplier.id, document_header, repository_lines)
        session.commit()
        return document.id
