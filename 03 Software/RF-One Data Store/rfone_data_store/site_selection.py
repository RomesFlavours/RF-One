"""CLOVER_MULTISITE_001 — which restaurant site a page works on.

One shared resolution for every page that offers the WP/MD selector (Tips,
RF-One Web Clover Acquisition): the sites are the Restaurants with a current
Clover Location; the selected one determines every datum, calculation,
history and operation of the page. A site whose Clover Location (or its
merchant) is inactive is listed and marked inactive; it is not operational:
no acquisition, calculation or payment is started for it.

Restaurants without any Clover Location stay selectable only when no Clover
site exists at all (fixtures, a fresh database), so the original single-site
behaviour is preserved.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m


@dataclass(frozen=True)
class Site:
    restaurant_id: int
    name: str
    location_id: int | None
    active: bool

    @property
    def operational(self) -> bool:
        return self.active


def _location_active(location: m.Location, merchant: m.Merchant | None) -> bool:
    return location.active is not False and (merchant is None or merchant.active is not False)


def list_sites(session: Session) -> list[Site]:
    """Every selectable site, lowest Restaurant id first (the original default)."""
    rows = session.execute(
        select(m.Restaurant, m.Location, m.Merchant)
        .join(m.RestaurantLocation, m.RestaurantLocation.restaurant_id == m.Restaurant.id)
        .join(m.Location, m.Location.id == m.RestaurantLocation.location_id)
        .join(m.SourceSystem, m.SourceSystem.id == m.Location.source_system_id)
        .outerjoin(m.Merchant, m.Merchant.id == m.Location.merchant_id)
        .where(m.RestaurantLocation.valid_to.is_(None), m.SourceSystem.code == "CLOVER")
        .order_by(m.Restaurant.id, m.Location.id)
    ).all()
    sites: dict[int, Site] = {}
    for restaurant, location, merchant in rows:
        if restaurant.id not in sites:
            sites[restaurant.id] = Site(restaurant.id, restaurant.name, location.id, _location_active(location, merchant))
        elif not _location_active(location, merchant):
            sites[restaurant.id] = Site(restaurant.id, restaurant.name, sites[restaurant.id].location_id, False)
    if sites:
        return list(sites.values())
    return [Site(r.id, r.name, None, restaurant_is_operational(session, r.id))
            for r in session.scalars(select(m.Restaurant).order_by(m.Restaurant.id))]


def account_restaurant_ids(session: Session, account, domain_code: str) -> frozenset[int]:
    """The restaurants `account` may work on in `domain_code` — the ONE
    central per-company/per-site authorization of RF-One (CLOVER_MULTISITE_001,
    model approved by the Product Owner on 2026-11-21). Every site-aware page,
    operation and financial action asks here (directly or through
    `sites_for_account` / `financial_authorization`); no Domain keeps its own
    list of who sees which restaurant.

    1. No entry into the Domain (`rfone_web_session.account_may_enter_domain`)
       -> no restaurant.
    2. An RF-One administrator or owner -> every restaurant (already reaches
       every company in `access_profiles.company_ids_for_account`).
    3. A direct access with company scope ALL (every access that existed
       before this model) -> every restaurant: existing users keep their reach.
       With company scope SELECTED -> the restaurants of the chosen companies.
    4. Role profiles add the restaurants of the companies where the person is a
       current member with a role that opens this Domain
       (`access_profiles.profile_company_ids_for_domain`).
    RFGroup (a GROUP company) stands for every company — operational reach
    only; it grants no administrator role (that stays the access row's role).
    A restaurant without a legal entity is reached only by rules 2–3 ALL or a
    GROUP: never by guessing its company."""
    from . import rfone_web_session
    from . import access_profiles as profiles
    if account is None or not rfone_web_session.account_may_enter_domain(session, account, domain_code):
        return frozenset()
    every = frozenset(session.scalars(select(m.Restaurant.id)))
    if account.is_admin or account.is_owner:
        return every
    allowed: set[int] = set()
    direct = session.scalars(select(m.RFOneAccountDomainAccess).where(
        m.RFOneAccountDomainAccess.account_id == account.id,
        m.RFOneAccountDomainAccess.domain_code == domain_code,
        m.RFOneAccountDomainAccess.enabled.is_(True))).first()
    if direct is not None:
        if direct.company_scope != m.DOMAIN_COMPANY_SCOPE_SELECTED:
            return every
        allowed |= profiles.restaurant_ids_for_companies(
            session, profiles.domain_company_ids(session, account.id, domain_code))
    allowed |= profiles.restaurant_ids_for_companies(
        session, profiles.profile_company_ids_for_domain(session, account.id, domain_code))
    return frozenset(allowed & every)


def sites_for_account(session: Session, account, domain_code: str) -> list[Site]:
    """The selectable sites `account` may work on in `domain_code` (the
    selector of Tips, Clover Acquisition and Tips period validation): the
    sites of `list_sites` that `account_restaurant_ids` allows."""
    allowed = account_restaurant_ids(session, account, domain_code)
    return [site for site in list_sites(session) if site.restaurant_id in allowed]


def account_may_use_restaurant(session: Session, account, domain_code: str, restaurant_id: int | None) -> bool:
    return restaurant_id is not None and restaurant_id in account_restaurant_ids(session, account, domain_code)


def resolve_site(session: Session, *candidates: int | None, sites: list[Site] | None = None) -> Site | None:
    """The first valid candidate restaurant id (explicit request, then the
    remembered choice), else the first site. Never an unknown id, never a site
    outside `sites` when given (e.g. `sites_for_account`)."""
    sites = list_sites(session) if sites is None else sites
    by_id = {site.restaurant_id: site for site in sites}
    for candidate in candidates:
        if candidate is not None and candidate in by_id:
            return by_id[candidate]
    return sites[0] if sites else None


def restaurant_is_operational(session: Session, restaurant_id: int) -> bool:
    """False when any current Location of the Restaurant (or its merchant) is
    inactive — e.g. Mount Dora before activation. Used by every operational
    entry point (calculations, payment cycles, schedulers, acquisition)."""
    rows = session.execute(
        select(m.Location, m.Merchant)
        .join(m.RestaurantLocation, m.RestaurantLocation.location_id == m.Location.id)
        .outerjoin(m.Merchant, m.Merchant.id == m.Location.merchant_id)
        .where(m.RestaurantLocation.restaurant_id == restaurant_id, m.RestaurantLocation.valid_to.is_(None))
    ).all()
    return all(_location_active(location, merchant) for location, merchant in rows)


class SiteNotOperationalError(ValueError):
    """The site is inactive: no acquisition, calculation or payment for it."""


def require_operational(session: Session, restaurant_id: int) -> None:
    if not restaurant_is_operational(session, restaurant_id):
        raise SiteNotOperationalError(
            f"Restaurant #{restaurant_id} is not active yet: no calculation, payment or acquisition is started.")
