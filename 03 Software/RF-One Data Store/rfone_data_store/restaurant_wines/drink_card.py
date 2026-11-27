"""Wines > Drink card (WINES_DRINK_CARD_001, Product Owner 2026-11-24).

The printable drink card of one site (a Restaurant `Location`):

  * wines   — the Wine list in effect today for the site's Entity
              (`Restaurant.legal_entity_id` of the Restaurant at that
              Location), with the applied bottle and glass prices;
  * texts   — one short English description per wine (shared by every
              site) and up to two dishes per wine and site, referenced as
              Kitchen recipes of the site's active menu, so the card always
              prints the dish's current name;
  * beers   — beers added to the card by hand.
  * waters  — mineral waters added to the card by hand.

Product Owner choices recorded on 2026-11-24 (`Decisioni RF1.md`): no beer
section; pairings are printed inside the description, as on the approved
Winter Park card ("…, ideal with braised beef."); the layout is similar to
that card.

An AI proposal never replaces what a person approved: an approved
description and the reviewed pairings of a wine at a site are kept as they
are when proposals are generated again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from .. import kitchen  # noqa: F401  (registers kitchen_recipes for the pairing foreign key)
from .. import models as m
from . import wine_lists

# Winter Park model: a bottle above this price shows no glass price.
GLASS_PRICE_BOTTLE_LIMIT = Decimal("100")
MAX_DESCRIPTION_LENGTH = 160
MAX_PAIRINGS = 2

SECTION_TITLES = {m.WINE_CATEGORY_RED: "RED WINES", m.WINE_CATEGORY_WHITE: "WHITE WINES", m.WINE_CATEGORY_ROSE: "ROSÉ"}

PAPER_PRESETS = {
    "HALF_LETTER": ("Half Letter 5.5 × 8.5 in", Decimal("5.5"), Decimal("8.5")),
    "LETTER": ("Letter 8.5 × 11 in", Decimal("8.5"), Decimal("11")),
    "LEGAL": ("Legal 8.5 × 14 in", Decimal("8.5"), Decimal("14")),
    "A5": ("A5 148 × 210 mm", Decimal("5.83"), Decimal("8.27")),
    "A4": ("A4 210 × 297 mm", Decimal("8.27"), Decimal("11.69")),
}

IMAGE_TYPES = {"image/png", "image/jpeg"}
PDF_TYPE = "application/pdf"     # accepted only for the graphic example (never printed)
MAX_IMAGE_BYTES = 4 * 1024 * 1024
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class DrinkCardError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------

@dataclass
class Site:
    location: m.Location
    restaurant: m.Restaurant | None
    entity: m.LegalEntity | None

    @property
    def name(self) -> str:
        return self.location.name


def list_sites(session: Session) -> list[Site]:
    """Every Location currently linked to a Restaurant, with that
    Restaurant's Entity (None when the Restaurant has none recorded)."""
    rows = session.execute(
        select(m.Location, m.Restaurant)
        .join(m.RestaurantLocation, m.RestaurantLocation.location_id == m.Location.id)
        .join(m.Restaurant, m.Restaurant.id == m.RestaurantLocation.restaurant_id)
        .where(m.RestaurantLocation.valid_to.is_(None))
        .order_by(m.Location.name)
    ).all()
    sites: dict[int, Site] = {}
    for location, restaurant in rows:
        if location.id in sites:
            continue
        entity = session.get(m.LegalEntity, restaurant.legal_entity_id) if restaurant.legal_entity_id else None
        sites[location.id] = Site(location, restaurant, entity)
    return list(sites.values())


def get_site(session: Session, location_id: int | None) -> Site | None:
    sites = list_sites(session)
    return next((s for s in sites if s.location.id == location_id), None) or (sites[0] if sites else None)


# ---------------------------------------------------------------------------
# Print settings
# ---------------------------------------------------------------------------

def get_card(session: Session, site: Site) -> m.DrinkCard:
    card = session.scalars(select(m.DrinkCard).where(m.DrinkCard.location_id == site.location.id)).first()
    if card is None:
        card = m.DrinkCard(
            location_id=site.location.id, title="Wine List",
            heading=(site.restaurant.name if site.restaurant else None), subheading=site.location.name,
            footer_note="Glass of 6 fl oz · Bottles 750 mL", page_count=4,
            page_width_in=Decimal("5.5"), page_height_in=Decimal("8.5"),
            orientation=m.DRINK_CARD_ORIENTATION_PORTRAIT, corners_enabled=True, corner_leg_in=Decimal("1"),
            show_glass_price=True, ink_color="#2E3A1C", accent_color="#A0401C", line_color="#B08A5A",
        )
        session.add(card)
        session.flush()
    return card


def _text(value: str | None, limit: int) -> str | None:
    cleaned = " ".join((value or "").split())
    return cleaned[:limit] or None


def _decimal(value, label: str) -> Decimal:
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        raise DrinkCardError(f"{label} must be a number.") from None
    if not number.is_finite():
        raise DrinkCardError(f"{label} must be a number.")
    return number


def update_settings(session: Session, card: m.DrinkCard, form: dict) -> m.DrinkCard:
    """Apply the print settings typed in the page. Unknown or invalid values
    are refused with a message; nothing is saved then."""
    try:
        pages = int(str(form.get("page_count", "")).strip())
    except ValueError:
        raise DrinkCardError("Number of pages must be a whole number.") from None
    if not 1 <= pages <= 24:
        raise DrinkCardError("Number of pages must be between 1 and 24.")
    width = _decimal(form.get("page_width_in"), "Sheet width")
    height = _decimal(form.get("page_height_in"), "Sheet height")
    if not (Decimal("3") <= width <= Decimal("20") and Decimal("3") <= height <= Decimal("20")):
        raise DrinkCardError("Sheet width and height must be between 3 and 20 inches.")
    orientation = form.get("orientation", "")
    if orientation not in m.DRINK_CARD_ORIENTATIONS:
        raise DrinkCardError("Choose portrait or landscape.")
    corners = str(form.get("corners_enabled", "")) == "1"
    leg = _decimal(form.get("corner_leg_in") or "0", "Corner side")
    if leg < 0:
        raise DrinkCardError("Corner side cannot be negative.")
    if corners and leg <= 0:
        raise DrinkCardError("With free corners on, the corner side must be greater than zero.")
    short_side = min(width, height)
    if corners and leg * 2 >= short_side:
        raise DrinkCardError("The free corners are too large for this sheet.")
    colors = {}
    for key, label in (("ink_color", "Text colour"), ("accent_color", "Accent colour"), ("line_color", "Line colour")):
        value = (form.get(key) or "").strip()
        if not _COLOR.match(value):
            raise DrinkCardError(f"{label} must be a colour such as #2E3A1C.")
        colors[key] = value.upper()
    title = _text(form.get("title"), 80)
    if not title:
        raise DrinkCardError("The card title cannot be empty.")

    card.page_count = pages
    card.page_width_in = width
    card.page_height_in = height
    card.orientation = orientation
    card.corners_enabled = corners
    card.corner_leg_in = leg
    card.show_glass_price = str(form.get("show_glass_price", "")) == "1"
    if "print_paper_color" in form:
        card.print_paper_color = str(form.get("print_paper_color")) == "1"
    card.title = title
    card.heading = _text(form.get("heading"), 80)
    card.subheading = _text(form.get("subheading"), 80)
    card.footer_note = _text(form.get("footer_note"), 160)
    for key, value in colors.items():
        setattr(card, key, value)
    session.flush()
    return card


def set_glass_price_visible(session: Session, card: m.DrinkCard, visible: bool) -> None:
    card.show_glass_price = visible
    session.flush()


def set_paper_color_printed(session: Session, card: m.DrinkCard, printed: bool) -> None:
    """Print the background's paper colour, or white paper with the same
    drawings and decorations."""
    card.print_paper_color = printed
    session.flush()


# ---------------------------------------------------------------------------
# Kitchen: dishes of the site's active menu
# ---------------------------------------------------------------------------

@dataclass
class Dish:
    recipe_id: int
    name: str
    details: str = ""


def active_menu_name(session: Session, location_id: int) -> str | None:
    return session.execute(
        text("SELECT name FROM kitchen_menus WHERE location_id = :loc AND active AND NOT archived"),
        {"loc": location_id},
    ).scalar()


def menu_dishes(session: Session, location_id: int) -> list[Dish]:
    """The dishes of the site's active Kitchen menu, in menu order, each
    once. The name is the one the menu shows (its entry label), read live."""
    rows = session.execute(text(
        "SELECT e.recipe_id, e.label, r.name, r.description, r.taste, r.aroma, r.texture "
        "FROM kitchen_menu_entries e "
        "JOIN kitchen_menus k ON k.id = e.menu_id "
        "JOIN kitchen_recipes r ON r.id = e.recipe_id "
        "WHERE k.location_id = :loc AND k.active AND NOT k.archived AND e.recipe_id IS NOT NULL "
        "ORDER BY e.position"
    ), {"loc": location_id}).all()
    dishes: dict[int, Dish] = {}
    for recipe_id, label, recipe_name, description, taste, aroma, texture in rows:
        if recipe_id in dishes:
            continue
        name = (label or recipe_name or "").strip()
        notes = "; ".join(x.strip() for x in (description, taste, aroma, texture) if x and x.strip())
        dishes[recipe_id] = Dish(recipe_id, name, notes)
    if dishes:
        ingredients: dict[int, list[str]] = {rid: [] for rid in dishes}
        for recipe_id, ingredient, preparation in session.execute(text(
            "SELECT recipe_id, ingredient_reference, preparation_reference FROM kitchen_recipe_components "
            "WHERE recipe_id IN (" + ",".join(str(int(r)) for r in dishes) + ") ORDER BY recipe_id, position"
        )).all():
            name = (ingredient or preparation or "").strip()
            if name and len(ingredients[recipe_id]) < 15:
                ingredients[recipe_id].append(name)
        for recipe_id, dish in dishes.items():
            if ingredients[recipe_id]:
                dish.details = (dish.details + " | " if dish.details else "") + "Ingredients: " + ", ".join(ingredients[recipe_id])
    return list(dishes.values())


# ---------------------------------------------------------------------------
# The card's wines and their texts
# ---------------------------------------------------------------------------

@dataclass
class CardWine:
    wine: m.Wine
    name: str
    producer: str
    vintage: str
    bottle_price: Decimal | None
    glass_price: Decimal | None
    description: str
    description_approved: bool
    pairings: list[Dish] = field(default_factory=list)
    pairings_reviewed: bool = False
    removed_dishes: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.removed_dishes) or not self.description

    def printed_description(self) -> str:
        """The single line under the wine: the description with its pairings,
        as on the Winter Park card ("…, ideal with braised beef.")."""
        return _printed(self.description, [d.name for d in self.pairings if d.name])


def card_name(wine: m.Wine) -> str:
    return wine.wine_type.standard_name + (f" · {wine.label_name}" if wine.label_name else "")


def wine_list_in_effect(session: Session, site: Site, today: date) -> m.WineList | None:
    if site.entity is None:
        return None
    return wine_lists.active_version(session, site.entity.id, today)


def card_wines(session: Session, site: Site, today: date) -> list[CardWine]:
    version = wine_list_in_effect(session, site, today)
    if version is None:
        return []
    items = wine_lists.list_items(session, version.id)
    wine_ids = [it.wine_id for it in items]
    descriptions = {
        d.wine_id: d for d in session.scalars(
            select(m.WineCardDescription).where(m.WineCardDescription.wine_id.in_(wine_ids))
        ).all()
    } if wine_ids else {}
    pairings: dict[int, list[m.WineCardPairing]] = {}
    if wine_ids:
        for p in session.scalars(
            select(m.WineCardPairing).where(
                m.WineCardPairing.location_id == site.location.id, m.WineCardPairing.wine_id.in_(wine_ids),
            ).order_by(m.WineCardPairing.position)
        ).all():
            pairings.setdefault(p.wine_id, []).append(p)
    reviewed = set(session.scalars(
        select(m.WineCardPairingReview.wine_id).where(m.WineCardPairingReview.location_id == site.location.id)
    ).all())
    dishes = {d.recipe_id: d for d in menu_dishes(session, site.location.id)}
    recipe_names = dict(session.execute(text("SELECT id, name FROM kitchen_recipes")).all()) if pairings else {}

    result = []
    for it in items:
        wine = it.wine
        desc = descriptions.get(wine.id)
        chosen, removed = [], []
        for p in pairings.get(wine.id, []):
            if p.recipe_id in dishes:
                chosen.append(dishes[p.recipe_id])
            else:
                removed.append(recipe_names.get(p.recipe_id) or f"recipe {p.recipe_id}")
        result.append(CardWine(
            wine=wine, name=card_name(wine), producer=wine.producer,
            vintage="" if wine.non_vintage else str(wine.vintage_year),
            bottle_price=it.applied_bottle_price,
            glass_price=it.applied_glass_price if it.sells_by_glass else None,
            description=desc.sentence if desc else "", description_approved=bool(desc and desc.approved),
            pairings=chosen, pairings_reviewed=wine.id in reviewed, removed_dishes=removed,
        ))
    return result


def printed_glass_price(card: m.DrinkCard, wine: CardWine) -> Decimal | None:
    """The glass price the card prints: none when the column is hidden, and
    — Winter Park model — none for a bottle above $100 ($100 itself keeps
    its glass price)."""
    if not card.show_glass_price or wine.glass_price is None:
        return None
    if wine.bottle_price is not None and wine.bottle_price > GLASS_PRICE_BOTTLE_LIMIT:
        return None
    return wine.glass_price


def _clean_description(value: str | None) -> str:
    cleaned = " ".join((value or "").split())
    if len(cleaned) > MAX_DESCRIPTION_LENGTH:
        raise DrinkCardError(f"The description can be at most {MAX_DESCRIPTION_LENGTH} characters.")
    return cleaned


def _set_pairings(session: Session, location_id: int, wine_id: int, recipe_ids: list[int], approved: bool) -> None:
    session.execute(delete(m.WineCardPairing).where(
        m.WineCardPairing.location_id == location_id, m.WineCardPairing.wine_id == wine_id,
    ))
    session.flush()
    for position, recipe_id in enumerate(recipe_ids[:MAX_PAIRINGS], start=1):
        session.add(m.WineCardPairing(
            location_id=location_id, wine_id=wine_id, position=position, recipe_id=recipe_id, approved=approved,
        ))
    session.flush()


def save_review(session: Session, site: Site, wine_id: int, description: str, recipe_ids: list[int]) -> None:
    """A person's review of one wine: the description and the chosen dishes
    (none, one or two) become approved and are kept by later proposals."""
    if session.get(m.Wine, wine_id) is None:
        raise DrinkCardError("This wine is no longer in the catalog.")
    menu = {d.recipe_id for d in menu_dishes(session, site.location.id)}
    unique: list[int] = []
    for rid in recipe_ids:
        if rid not in menu:
            raise DrinkCardError("A chosen dish is not on the site's active menu.")
        if rid not in unique:
            unique.append(rid)
    if len(unique) > MAX_PAIRINGS:
        raise DrinkCardError("Choose at most two dishes.")
    text_value = _clean_description(description)
    row = session.get(m.WineCardDescription, wine_id)
    if text_value:
        if row is None:
            row = m.WineCardDescription(wine_id=wine_id, sentence=text_value, approved=True)
            session.add(row)
        else:
            row.sentence, row.approved = text_value, True
    elif row is not None:
        session.delete(row)
    _set_pairings(session, site.location.id, wine_id, unique, approved=True)
    if session.get(m.WineCardPairingReview, (site.location.id, wine_id)) is None:
        session.add(m.WineCardPairingReview(location_id=site.location.id, wine_id=wine_id))
    session.flush()


def approve_all(session: Session, site: Site, today: date) -> int:
    """Approve every proposal currently shown for the site. Returns how many
    wines were approved. Pairings are approved only when they hold at least
    one dish: an empty pairing stays waiting for a proposal (a person can
    still choose "no dish" for one wine with its own review)."""
    count = 0
    for cw in card_wines(session, site, today):
        if cw.removed_dishes:
            continue  # a dish left the menu: the person must choose again
        changed = False
        desc = session.get(m.WineCardDescription, cw.wine.id)
        if desc is not None and not desc.approved:
            desc.approved = True
            changed = True
        if not cw.pairings_reviewed:
            pairings = session.scalars(select(m.WineCardPairing).where(
                m.WineCardPairing.location_id == site.location.id, m.WineCardPairing.wine_id == cw.wine.id,
            )).all()
            if pairings:
                for p in pairings:
                    p.approved = True
                session.add(m.WineCardPairingReview(location_id=site.location.id, wine_id=cw.wine.id))
                changed = True
        count += changed
    session.flush()
    return count


def _printed(sentence: str, dish_names: list[str]) -> str:
    sentence = (sentence or "").strip().rstrip(".").strip()
    if dish_names:
        dishes = " and ".join(dish_names)
        sentence = f"{sentence}, ideal with {dishes}" if sentence else f"Ideal with {dishes}"
    return sentence + "." if sentence else ""


def _lines(card: m.DrinkCard, description: str) -> int:
    from . import drink_card_pdf as pdf

    return pdf.description_lines(_spec(card, {}), description)


@dataclass
class Proposal:
    wine_id: int
    description: str
    recipe_ids: list[int]


def apply_proposals(session: Session, site: Site, proposals: list[Proposal], card: m.DrinkCard | None = None) -> int:
    """Store AI proposals, never over what a person approved: an approved
    description stays, reviewed pairings stay. Returns how many wines got
    at least one new proposal."""
    menu = {d.recipe_id: d.name for d in menu_dishes(session, site.location.id)}
    reviewed = set(session.scalars(
        select(m.WineCardPairingReview.wine_id).where(m.WineCardPairingReview.location_id == site.location.id)
    ).all())
    updated = 0
    for proposal in proposals:
        if session.get(m.Wine, proposal.wine_id) is None:
            continue
        touched = False
        text_value = " ".join((proposal.description or "").split())[:MAX_DESCRIPTION_LENGTH]
        row = session.get(m.WineCardDescription, proposal.wine_id)
        if text_value and (row is None or not row.approved):
            if row is None:
                session.add(m.WineCardDescription(wine_id=proposal.wine_id, sentence=text_value, approved=False))
            else:
                row.sentence = text_value
            touched = True
        if proposal.wine_id not in reviewed:
            ids = []
            for rid in proposal.recipe_ids:
                if rid in menu and rid not in ids:
                    ids.append(rid)
            if len(ids) > 1 and card is not None:
                # A second dish is kept only when it does not add a printed line.
                sentence = row.sentence if row is not None and row.approved else text_value
                one = _printed(sentence, [menu[ids[0]]])
                two = _printed(sentence, [menu[i] for i in ids[:2]])
                if _lines(card, two) > _lines(card, one):
                    ids = ids[:1]
            _set_pairings(session, site.location.id, proposal.wine_id, ids, approved=False)
            touched = True
        updated += touched
    session.flush()
    return updated


def forget_wine(session: Session, wine_id: int) -> None:
    """Remove every drink card text of a wine deleted from the catalog."""
    session.execute(delete(m.WineCardPairing).where(m.WineCardPairing.wine_id == wine_id))
    session.execute(delete(m.WineCardPairingReview).where(m.WineCardPairingReview.wine_id == wine_id))
    session.execute(delete(m.WineCardDescription).where(m.WineCardDescription.wine_id == wine_id))
    session.flush()


# ---------------------------------------------------------------------------
# Beers
# ---------------------------------------------------------------------------

def list_beers(session: Session, card: m.DrinkCard) -> list[m.DrinkCardBeer]:
    return list(session.scalars(
        select(m.DrinkCardBeer).where(m.DrinkCardBeer.drink_card_id == card.id)
        .order_by(m.DrinkCardBeer.position, m.DrinkCardBeer.id)
    ).all())


def save_beer(session: Session, card: m.DrinkCard, beer_id: int | None, form: dict) -> m.DrinkCardBeer:
    name = _text(form.get("name"), 120)
    beer_type = _text(form.get("beer_type"), 60)
    size = _text(form.get("size_label"), 40)
    if not name:
        raise DrinkCardError("Enter the name of the beer.")
    if not size:
        raise DrinkCardError("Enter the format, for example 12 oz bottle.")
    price = _decimal(form.get("price_usd") or "", "Price")
    if price < 0:
        raise DrinkCardError("The price cannot be negative.")
    if beer_id is None:
        beers = list_beers(session, card)
        beer = m.DrinkCardBeer(drink_card_id=card.id, position=(beers[-1].position + 1) if beers else 1,
                               name=name, beer_type=beer_type, size_label=size, price_usd=price)
        session.add(beer)
    else:
        beer = session.get(m.DrinkCardBeer, beer_id)
        if beer is None or beer.drink_card_id != card.id:
            raise DrinkCardError("This beer is no longer on the card.")
        beer.name, beer.beer_type, beer.size_label, beer.price_usd = name, beer_type, size, price
    session.flush()
    return beer


def delete_beer(session: Session, card: m.DrinkCard, beer_id: int) -> None:
    beer = session.get(m.DrinkCardBeer, beer_id)
    if beer is not None and beer.drink_card_id == card.id:
        session.delete(beer)
        session.flush()


# ---------------------------------------------------------------------------
# Mineral waters
# ---------------------------------------------------------------------------

def list_waters(session: Session, card: m.DrinkCard) -> list[m.DrinkCardWater]:
    return list(session.scalars(
        select(m.DrinkCardWater).where(m.DrinkCardWater.drink_card_id == card.id)
        .order_by(m.DrinkCardWater.position, m.DrinkCardWater.id)
    ).all())


def save_water(session: Session, card: m.DrinkCard, water_id: int | None, form: dict) -> m.DrinkCardWater:
    name = _text(form.get("name"), 120)
    size = _text(form.get("size_label"), 40)
    if not name:
        raise DrinkCardError("Enter the name of the water.")
    if not size:
        raise DrinkCardError("Enter the format, for example 750 mL.")
    price = _decimal(form.get("price_usd") or "", "Price")
    if price < 0:
        raise DrinkCardError("The price cannot be negative.")
    sparkling = str(form.get("sparkling", "")) == "1"
    if water_id is None:
        waters = list_waters(session, card)
        water = m.DrinkCardWater(drink_card_id=card.id, position=(waters[-1].position + 1) if waters else 1,
                                 name=name, size_label=size, price_usd=price, sparkling=sparkling)
        session.add(water)
    else:
        water = session.get(m.DrinkCardWater, water_id)
        if water is None or water.drink_card_id != card.id:
            raise DrinkCardError("This water is no longer on the card.")
        water.name, water.size_label, water.price_usd, water.sparkling = name, size, price, sparkling
    session.flush()
    return water


def delete_water(session: Session, card: m.DrinkCard, water_id: int) -> None:
    water = session.get(m.DrinkCardWater, water_id)
    if water is not None and water.drink_card_id == card.id:
        session.delete(water)
        session.flush()


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def card_images(session: Session, card: m.DrinkCard) -> dict[str, m.DrinkCardImage]:
    return {img.slot: img for img in session.scalars(
        select(m.DrinkCardImage).where(m.DrinkCardImage.drink_card_id == card.id)
    ).all()}


def _sniff_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"%PDF-"):
        return PDF_TYPE
    return None


def set_image(session: Session, card: m.DrinkCard, slot: str, filename: str, data: bytes) -> m.DrinkCardImage:
    if slot not in m.DRINK_CARD_IMAGE_SLOTS:
        raise DrinkCardError("Unknown image position.")
    if not data:
        raise DrinkCardError("Choose an image file.")
    if len(data) > MAX_IMAGE_BYTES:
        raise DrinkCardError("The image is larger than 4 MB.")
    content_type = _sniff_type(data)
    if content_type == PDF_TYPE and slot != "REFERENCE":
        raise DrinkCardError("A PDF can be uploaded only as the graphic example: use a PNG or JPEG image.")
    if content_type not in IMAGE_TYPES and not (content_type == PDF_TYPE and slot == "REFERENCE"):
        raise DrinkCardError("Use a PNG or JPEG image (or a PDF for the graphic example).")
    image = card_images(session, card).get(slot)
    if image is None:
        image = m.DrinkCardImage(drink_card_id=card.id, slot=slot)
        session.add(image)
    image.filename = (filename or "image")[:200]
    image.content_type = content_type
    image.data = data
    session.flush()
    return image


def delete_image(session: Session, card: m.DrinkCard, slot: str) -> None:
    image = card_images(session, card).get(slot)
    if image is not None:
        session.delete(image)
        session.flush()


# ---------------------------------------------------------------------------
# The card itself
# ---------------------------------------------------------------------------

def _spec(card: m.DrinkCard, images: dict[str, bytes]):
    from . import drink_card_pdf as pdf

    return pdf.CardSpec(
        width_in=card.page_width_in, height_in=card.page_height_in,
        landscape=card.orientation == m.DRINK_CARD_ORIENTATION_LANDSCAPE, page_count=card.page_count,
        corners=card.corners_enabled, corner_leg_in=card.corner_leg_in, show_glass=card.show_glass_price,
        title=card.title, heading=card.heading, subheading=card.subheading, footer_note=card.footer_note,
        ink=card.ink_color, accent=card.accent_color, line=card.line_color, images=images,
        print_paper_color=card.print_paper_color is not False,
    )


@dataclass
class CardResult:
    pdf: bytes
    overflow: list[str]
    long_descriptions: list[str]
    pages_used: int
    page_count: int
    wine_count: int
    water_count: int
    beer_count: int = 0

    @property
    def exportable(self) -> bool:
        return not self.overflow


def build_card(session: Session, site: Site, card: m.DrinkCard, today: date, two_up: bool = False) -> CardResult:
    """Lay out and render the site's card. The preview shows this PDF and the
    export downloads the same bytes, so they always match. `two_up` puts two
    pages side by side on each sheet, for printing and cutting."""
    from . import drink_card_pdf as pdf

    wines = card_wines(session, site, today)
    sections: list[pdf.Section] = []
    for category in m.WINE_CATEGORIES:
        entries = []
        for cw in sorted((w for w in wines if w.wine.category == category), key=lambda w: (w.name.casefold(), w.producer.casefold())):
            detail = " · ".join(x for x in (cw.producer, cw.vintage) if x)
            entries.append(pdf.Entry(
                name=cw.name, detail=detail, description=cw.printed_description(),
                bottle=cw.bottle_price, glass=printed_glass_price(card, cw), key=f"wine-{cw.wine.id}",
            ))
        sections.append(pdf.Section(SECTION_TITLES[category], entries, glass_column=True))
    beers = list_beers(session, card)
    sections.append(pdf.Section("BEERS", [
        pdf.Entry(name=b.name, detail=" · ".join(x for x in (b.beer_type, b.size_label) if x),
                  description="", bottle=b.price_usd, key=f"beer-{b.id}")
        for b in beers
    ], glass_column=False, column_letters=False))
    waters = list_waters(session, card)
    sections.append(pdf.Section("MINERAL WATER", [
        pdf.Entry(name=w.name, detail=f"{'Sparkling' if w.sparkling else 'Still'} · {w.size_label}",
                  description="", bottle=w.price_usd, key=f"water-{w.id}")
        for w in waters
    ], glass_column=False, column_letters=False))
    images = {slot: img.data for slot, img in card_images(session, card).items() if slot != "REFERENCE"}
    spec = _spec(card, images)
    result = pdf.layout(spec, sections)
    return CardResult(
        pdf=pdf.render(spec, result, two_up=two_up), overflow=result.overflow, long_descriptions=result.long_descriptions,
        pages_used=result.pages_used, page_count=card.page_count, wine_count=len(wines), water_count=len(waters),
        beer_count=len(beers),
    )
