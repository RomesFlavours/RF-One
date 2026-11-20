"""Catalog of purchasable wines ("Availability").

What can be bought, from whom, at what cost — never physical stock. A wine
whose cost is not known yet is catalogued with `cost_usd` NULL, which is
not the same as a cost of 0.

The same wine is not catalogued twice: type, producer, label, vintage and
bottle format (normalized) identify it. Different labels of one type are
different wines and are always allowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from .. import models as m
from .wine_types import clean_name, name_key

DEFAULT_BOTTLE_SIZE_ML = 750
MIN_VINTAGE_YEAR = 1900
MAX_VINTAGE_YEAR = 2100

CATEGORY_LABELS = {m.WINE_CATEGORY_RED: "Red", m.WINE_CATEGORY_WHITE: "White", m.WINE_CATEGORY_ROSE: "Rosé"}
STYLE_LABELS = {m.WINE_STYLE_STILL: "Still", m.WINE_STYLE_FRIZZANTE: "Frizzante", m.WINE_STYLE_SPARKLING: "Sparkling"}
AVAILABILITY_LABELS = {
    m.WINE_AVAILABILITY_AVAILABLE: "Available",
    m.WINE_AVAILABILITY_INCOMING: "Incoming",
    m.WINE_AVAILABILITY_UNAVAILABLE: "Not available",
}


class WineCatalogError(ValueError):
    pass


class DuplicateWineError(WineCatalogError):
    def __init__(self, message: str, existing_wine_id: int):
        super().__init__(message)
        self.existing_wine_id = existing_wine_id


@dataclass
class WineInput:
    wine_type_id: int | None
    producer: str
    label_name: str | None
    vintage_year: int | None
    non_vintage: bool
    category: str
    style: str
    denomination: str | None
    region: str | None
    bottle_size_ml: int | None
    supplier_name: str | None
    cost_usd: Decimal | None
    cost_date: date | None
    availability: str
    notes: str | None


def identity_key(wine_type_id: int, producer: str, label_name: str | None, vintage_year: int | None,
                 non_vintage: bool, bottle_size_ml: int) -> str:
    vintage = "NV" if non_vintage else str(vintage_year)
    return "|".join([str(wine_type_id), name_key(producer), name_key(label_name), vintage, str(bottle_size_ml)])


def display_name(wine: m.Wine) -> str:
    """"Amarone - Domini Veneti - Label - 2021": the workbook's own naming,
    with the label when there is one."""
    parts = [wine.wine_type.standard_name, wine.producer]
    if wine.label_name:
        parts.append(wine.label_name)
    parts.append(wine.vintage_label)
    return " - ".join(parts)


def _optional(text: str | None, limit: int, label: str) -> str | None:
    value = clean_name(text)
    if len(value) > limit:
        raise WineCatalogError(f"{label} is longer than {limit} characters.")
    return value or None


def _validated(session: Session, data: WineInput) -> dict:
    errors = []
    wine_type = session.get(m.WineType, data.wine_type_id) if data.wine_type_id else None
    if wine_type is None:
        errors.append("Wine type is required.")
    producer = clean_name(data.producer)
    if not producer:
        errors.append("Producer is required.")
    if data.non_vintage:
        vintage_year = None
    elif data.vintage_year is None:
        errors.append("Vintage is required, or mark the wine as non-vintage.")
        vintage_year = None
    elif not MIN_VINTAGE_YEAR <= data.vintage_year <= MAX_VINTAGE_YEAR:
        errors.append(f"Vintage must be between {MIN_VINTAGE_YEAR} and {MAX_VINTAGE_YEAR}.")
        vintage_year = None
    else:
        vintage_year = data.vintage_year
    if data.category not in m.WINE_CATEGORIES:
        errors.append("Category is required (red, white or rosé).")
    if data.style not in m.WINE_STYLES:
        errors.append("Style is required (still, frizzante or sparkling).")
    if data.availability not in m.WINE_AVAILABILITIES:
        errors.append("Availability is required.")
    size = data.bottle_size_ml if data.bottle_size_ml is not None else DEFAULT_BOTTLE_SIZE_ML
    if size <= 0:
        errors.append("Bottle format must be a positive number of ml.")
    if data.cost_usd is not None and data.cost_usd < 0:
        errors.append("Cost cannot be negative. Leave it empty if it is not known yet.")
    if errors:
        raise WineCatalogError(" ".join(errors))
    return {
        "wine_type_id": wine_type.id,
        "producer": producer[:160],
        "label_name": _optional(data.label_name, 200, "Label name"),
        "vintage_year": vintage_year,
        "non_vintage": bool(data.non_vintage),
        "category": data.category,
        "style": data.style,
        "denomination": _optional(data.denomination, 80, "Denomination"),
        "region": _optional(data.region, 80, "Region"),
        "bottle_size_ml": size,
        "supplier_name": _optional(data.supplier_name, 160, "Supplier"),
        "cost_usd": data.cost_usd,
        "cost_date": data.cost_date if data.cost_usd is not None else None,
        "availability": data.availability,
        "notes": (data.notes or "").strip() or None,
    }


def _check_duplicate(session: Session, key: str, own_id: int | None) -> None:
    existing = session.scalars(select(m.Wine).where(m.Wine.identity_key == key)).first()
    if existing is not None and existing.id != own_id:
        raise DuplicateWineError(
            f"This wine is already in the catalog: {display_name(existing)}, "
            f"{existing.bottle_size_ml} ml. Edit that one instead.",
            existing.id,
        )


def create_wine(session: Session, data: WineInput) -> m.Wine:
    fields = _validated(session, data)
    key = identity_key(fields["wine_type_id"], fields["producer"], fields["label_name"], fields["vintage_year"],
                       fields["non_vintage"], fields["bottle_size_ml"])
    _check_duplicate(session, key, None)
    wine = m.Wine(identity_key=key, **fields)
    session.add(wine)
    session.flush()
    return wine


def update_wine(session: Session, wine: m.Wine, data: WineInput) -> m.Wine:
    """Catalog changes never touch Wine list rows: a list keeps the cost it
    used and only signals that the catalog cost changed."""
    fields = _validated(session, data)
    key = identity_key(fields["wine_type_id"], fields["producer"], fields["label_name"], fields["vintage_year"],
                       fields["non_vintage"], fields["bottle_size_ml"])
    _check_duplicate(session, key, wine.id)
    for name, value in fields.items():
        setattr(wine, name, value)
    wine.identity_key = key
    session.flush()
    return wine


def list_wines(session: Session, query: str | None = None) -> list[m.Wine]:
    stmt = select(m.Wine).options(joinedload(m.Wine.wine_type)).join(m.WineType, m.WineType.id == m.Wine.wine_type_id)
    words = clean_name(query).split()
    for word in words:
        like = f"%{word}%"
        type_ids = select(m.WineTypeName.wine_type_id).where(m.WineTypeName.name.ilike(like))
        stmt = stmt.where(or_(
            m.Wine.wine_type_id.in_(type_ids),
            m.Wine.producer.ilike(like),
            m.Wine.label_name.ilike(like),
            m.Wine.denomination.ilike(like),
            m.Wine.region.ilike(like),
            m.Wine.supplier_name.ilike(like),
            m.Wine.notes.ilike(like),
        ))
    stmt = stmt.order_by(m.WineType.standard_name, m.Wine.producer, m.Wine.label_name, m.Wine.vintage_year)
    return list(session.scalars(stmt).unique().all())


def known_supplier_names(session: Session) -> list[str]:
    rows = session.scalars(
        select(m.Wine.supplier_name).where(m.Wine.supplier_name.is_not(None)).distinct().order_by(m.Wine.supplier_name)
    ).all()
    return [r for r in rows if r]
