"""Wine lists of each Entity, versioned by effective date, and their prices.

* The Entity is the existing `LegalEntity` registry — read, never changed.
* The active version on a day is the one with the latest `effective_from`
  not after that day. Earlier versions are kept (read only); later ones can
  be prepared without replacing the active one early. One version per
  Entity per date.
* A row keeps the cost and the pricing parameters its calculated prices
  come from, and its applied prices separately. An applied price typed by
  hand is kept through recalculations until it is explicitly restored to
  the calculated one. Nothing here changes a saved price implicitly: a new
  catalog cost or a new configuration is only signalled, and adopted on
  request.
* Removing a row removes it from that version only, never the wine from the
  catalog.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .. import models as m
from . import catalog
from .pricing import PricingParameters, calculate_prices

STATUS_ACTIVE = "ACTIVE"
STATUS_FUTURE = "FUTURE"
STATUS_PAST = "PAST"

MODE_EMPTY = "EMPTY"
MODE_COPY_ACTIVE = "COPY_ACTIVE"

EXPORT_HEADER = (
    "Entity", "Effective from", "Category", "Type", "Label", "Producer", "Vintage", "Format (ml)",
    "Bottle price", "Glass price",
)


class WineListError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Pricing configuration
# ---------------------------------------------------------------------------


def get_settings(session: Session) -> m.WinePricingSettings:
    settings = session.get(m.WinePricingSettings, 1)
    if settings is None:  # the migration inserts it; never guess other values
        raise WineListError("The Wines pricing configuration is missing.")
    return settings


def current_parameters(session: Session) -> PricingParameters:
    s = get_settings(session)
    return PricingParameters(s.coefficient_a, s.log_base_b, s.glass_divisor_g)


def update_settings(session: Session, parameters: PricingParameters) -> m.WinePricingSettings:
    parameters.validate()
    s = get_settings(session)
    s.coefficient_a = parameters.coefficient_a
    s.log_base_b = parameters.log_base_b
    s.glass_divisor_g = parameters.glass_divisor_g
    session.flush()
    return s


def item_parameters(item: m.WineListItem) -> PricingParameters:
    return PricingParameters(item.coefficient_a, item.log_base_b, item.glass_divisor_g)


# ---------------------------------------------------------------------------
# Entities and versions
# ---------------------------------------------------------------------------


def list_entities(session: Session) -> list[m.LegalEntity]:
    return list(session.scalars(
        select(m.LegalEntity).where(m.LegalEntity.status == "ACTIVE").order_by(m.LegalEntity.legal_name)
    ).all())


def list_versions(session: Session, legal_entity_id: int) -> list[m.WineList]:
    """Newest effective date first."""
    return list(session.scalars(
        select(m.WineList).where(m.WineList.legal_entity_id == legal_entity_id)
        .order_by(m.WineList.effective_from.desc())
    ).all())


def active_version(session: Session, legal_entity_id: int, today: date) -> m.WineList | None:
    return session.scalars(
        select(m.WineList)
        .where(m.WineList.legal_entity_id == legal_entity_id, m.WineList.effective_from <= today)
        .order_by(m.WineList.effective_from.desc())
    ).first()


def version_status(version: m.WineList, active: m.WineList | None, today: date) -> str:
    if active is not None and version.id == active.id:
        return STATUS_ACTIVE
    return STATUS_FUTURE if version.effective_from > today else STATUS_PAST


def is_editable(session: Session, version: m.WineList, today: date) -> bool:
    """Previous versions are consulted, not changed."""
    active = active_version(session, version.legal_entity_id, today)
    return version_status(version, active, today) != STATUS_PAST


def _require_editable(session: Session, version: m.WineList, today: date) -> None:
    if not is_editable(session, version, today):
        raise WineListError("This Wine list version is no longer in effect and can only be consulted.")


def create_version(
    session: Session, *, legal_entity_id: int, effective_from: date | None, mode: str, today: date,
    account_id: int | None = None,
) -> m.WineList:
    entity = session.get(m.LegalEntity, legal_entity_id)
    if entity is None or entity.status != "ACTIVE":
        raise WineListError("Choose an active Entity.")
    if effective_from is None:
        raise WineListError("The effective date is required.")
    if mode not in (MODE_EMPTY, MODE_COPY_ACTIVE):
        raise WineListError("Choose an empty list or a copy of the current one.")
    duplicate = session.scalars(select(m.WineList).where(
        m.WineList.legal_entity_id == legal_entity_id, m.WineList.effective_from == effective_from,
    )).first()
    if duplicate is not None:
        raise WineListError(f"{entity.legal_name} already has a Wine list effective from {effective_from.isoformat()}.")

    source = None
    if mode == MODE_COPY_ACTIVE:
        source = active_version(session, legal_entity_id, today)
        if source is None:
            raise WineListError(f"{entity.legal_name} has no Wine list in effect today to copy.")

    version = m.WineList(
        legal_entity_id=legal_entity_id, effective_from=effective_from,
        copied_from_wine_list_id=source.id if source else None, created_by_account_id=account_id,
    )
    session.add(version)
    if source is not None:
        # An exact copy: same cost used, Value, parameters, calculated and
        # applied prices (manual ones stay manual).
        for item in source.items:
            version.items.append(m.WineListItem(
                wine_id=item.wine_id, cost_used=item.cost_used, value_factor=item.value_factor,
                sells_by_glass=item.sells_by_glass, coefficient_a=item.coefficient_a,
                log_base_b=item.log_base_b, glass_divisor_g=item.glass_divisor_g,
                calculated_bottle_price=item.calculated_bottle_price,
                calculated_glass_price=item.calculated_glass_price,
                applied_bottle_price=item.applied_bottle_price, applied_glass_price=item.applied_glass_price,
                bottle_price_manual=item.bottle_price_manual, glass_price_manual=item.glass_price_manual,
            ))
    session.flush()
    return version


def list_items(session: Session, wine_list_id: int) -> list[m.WineListItem]:
    items = session.scalars(
        select(m.WineListItem).where(m.WineListItem.wine_list_id == wine_list_id)
        .options(joinedload(m.WineListItem.wine).joinedload(m.Wine.wine_type))
    ).unique().all()
    order = {c: i for i, c in enumerate(m.WINE_CATEGORIES)}
    return sorted(items, key=lambda it: (
        order.get(it.wine.category, 9), it.wine.wine_type.standard_name.casefold(),
        it.wine.producer.casefold(), (it.wine.label_name or "").casefold(), it.wine.vintage_year or 0,
    ))


# ---------------------------------------------------------------------------
# Rows and prices
# ---------------------------------------------------------------------------


def _money(value: Decimal | int | None) -> Decimal | None:
    return None if value is None else Decimal(value).quantize(Decimal("0.01"))


def _validate_value(value: Decimal | None) -> Decimal:
    if value is None or value <= 0:
        raise WineListError("Value must be a positive number.")
    return value


def _validate_cost(cost: Decimal | None) -> Decimal | None:
    if cost is not None and cost < 0:
        raise WineListError("Cost cannot be negative. Leave it empty if it is not known yet.")
    return cost


def _validate_price(price: Decimal | None, label: str) -> Decimal | None:
    if price is not None and price <= 0:
        raise WineListError(f"{label} must be greater than 0, or left empty.")
    return _money(price)


@dataclass(frozen=True)
class PriceEdit:
    """What the person submitted for an applied price: `None` = left empty
    (follow the calculated price)."""
    value: Decimal | None


def _resolve_applied(
    calculated: int | None, submitted: PriceEdit | None, previous_applied: Decimal | None, was_manual: bool,
) -> tuple[Decimal | None, bool]:
    """(applied price, manual?) after a calculation.

    * submitted is None (no field sent: a recalculation) -> a manual price is
      kept, an automatic one follows the calculated price;
    * submitted empty -> follow the calculated price;
    * submitted equal to the previous applied price and not manual -> the
      person did not touch it: follow the calculated price;
    * otherwise the submitted price is applied; it is manual unless it
      equals the calculated price."""
    calc = _money(calculated)
    if submitted is None:
        return (previous_applied, True) if was_manual else (calc, False)
    if submitted.value is None:
        return calc, False
    new = _money(submitted.value)
    if not was_manual and previous_applied is not None and new == previous_applied:
        return calc, False
    return new, new != calc


def _apply_prices(item: m.WineListItem, *, bottle: PriceEdit | None = None, glass: PriceEdit | None = None) -> None:
    prices = calculate_prices(item.cost_used, item.value_factor, item_parameters(item),
                              sells_by_glass=item.sells_by_glass)
    item.calculated_bottle_price = prices.bottle
    item.applied_bottle_price, item.bottle_price_manual = _resolve_applied(
        prices.bottle, bottle, item.applied_bottle_price, item.bottle_price_manual,
    )
    if item.sells_by_glass:
        item.calculated_glass_price = prices.glass
        item.applied_glass_price, item.glass_price_manual = _resolve_applied(
            prices.glass, glass, item.applied_glass_price, item.glass_price_manual,
        )
    else:
        item.calculated_glass_price = None
        item.applied_glass_price = None
        item.glass_price_manual = False


def add_item(
    session: Session, version: m.WineList, *, wine_id: int | None, cost_used: Decimal | None,
    value_factor: Decimal | None, sells_by_glass: bool, applied_bottle: Decimal | None = None,
    applied_glass: Decimal | None = None, today: date,
) -> m.WineListItem:
    _require_editable(session, version, today)
    wine = session.get(m.Wine, wine_id) if wine_id else None
    if wine is None:
        raise WineListError("Choose a wine from the catalog.")
    already = session.scalars(select(m.WineListItem).where(
        m.WineListItem.wine_list_id == version.id, m.WineListItem.wine_id == wine.id,
    )).first()
    if already is not None:
        raise WineListError(f"{catalog.display_name(wine)} is already on this Wine list.")
    parameters = current_parameters(session)
    item = m.WineListItem(
        wine_list_id=version.id, wine_id=wine.id, cost_used=_validate_cost(cost_used),
        value_factor=_validate_value(value_factor), sells_by_glass=bool(sells_by_glass),
        coefficient_a=parameters.coefficient_a, log_base_b=parameters.log_base_b,
        glass_divisor_g=parameters.glass_divisor_g, bottle_price_manual=False, glass_price_manual=False,
    )
    _apply_prices(
        item,
        bottle=PriceEdit(_validate_price(applied_bottle, "Bottle price")),
        glass=PriceEdit(_validate_price(applied_glass, "Glass price")),
    )
    session.add(item)
    session.flush()
    return item


def update_item(
    session: Session, item: m.WineListItem, *, cost_used: Decimal | None, value_factor: Decimal | None,
    sells_by_glass: bool, applied_bottle: Decimal | None, applied_glass: Decimal | None, today: date,
) -> m.WineListItem:
    """Change the commercial data of one row. Prices are recalculated with
    the row's own parameters; hand-set applied prices are kept."""
    _require_editable(session, item.wine_list, today)
    item.cost_used = _validate_cost(cost_used)
    item.value_factor = _validate_value(value_factor)
    was_by_glass = item.sells_by_glass
    item.sells_by_glass = bool(sells_by_glass)
    if item.sells_by_glass and not was_by_glass:
        item.applied_glass_price, item.glass_price_manual = None, False
    _apply_prices(
        item,
        bottle=PriceEdit(_validate_price(applied_bottle, "Bottle price")),
        glass=PriceEdit(_validate_price(applied_glass, "Glass price")),
    )
    session.flush()
    return item


def remove_item(session: Session, item: m.WineListItem, *, today: date) -> None:
    """Remove the row from its version only. The catalog wine stays."""
    _require_editable(session, item.wine_list, today)
    session.delete(item)
    session.flush()


def catalog_cost_changed(item: m.WineListItem) -> bool:
    catalog_cost = item.wine.cost_usd
    return catalog_cost is not None and catalog_cost != item.cost_used


def parameters_changed(item: m.WineListItem, current: PricingParameters) -> bool:
    return item_parameters(item) != current


def adopt_catalog_cost(session: Session, item: m.WineListItem, *, today: date) -> m.WineListItem:
    """Take the catalog's current cost and recalculate. Manual applied
    prices are kept."""
    _require_editable(session, item.wine_list, today)
    if item.wine.cost_usd is None:
        raise WineListError("The catalog has no cost for this wine.")
    item.cost_used = item.wine.cost_usd
    _apply_prices(item)
    session.flush()
    return item


def adopt_current_parameters(session: Session, item: m.WineListItem, *, today: date) -> m.WineListItem:
    _require_editable(session, item.wine_list, today)
    p = current_parameters(session)
    item.coefficient_a, item.log_base_b, item.glass_divisor_g = p.coefficient_a, p.log_base_b, p.glass_divisor_g
    _apply_prices(item)
    session.flush()
    return item


def restore_calculated(session: Session, item: m.WineListItem, *, today: date) -> m.WineListItem:
    """Explicitly drop hand-set applied prices in favour of the calculated ones."""
    _require_editable(session, item.wine_list, today)
    item.bottle_price_manual = False
    item.glass_price_manual = False
    _apply_prices(item)
    session.flush()
    return item


# ---------------------------------------------------------------------------
# Export (for the printed list: no cost, Value or internal notes)
# ---------------------------------------------------------------------------


def _price_text(price: Decimal | None) -> str:
    if price is None:
        return ""
    return str(int(price)) if price == price.to_integral_value() else f"{price:.2f}"


def export_rows(session: Session, version: m.WineList) -> list[tuple[str, ...]]:
    rows = []
    for item in list_items(session, version.id):
        wine = item.wine
        rows.append((
            version.legal_entity.legal_name,
            version.effective_from.isoformat(),
            catalog.CATEGORY_LABELS.get(wine.category, wine.category),
            wine.wine_type.standard_name,
            wine.label_name or "",
            wine.producer,
            wine.vintage_label,
            str(wine.bottle_size_ml),
            _price_text(item.applied_bottle_price),
            _price_text(item.applied_glass_price) if item.sells_by_glass else "",
        ))
    return rows


def export_csv(session: Session, version: m.WineList) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(EXPORT_HEADER)
    writer.writerows(export_rows(session, version))
    return buffer.getvalue()
