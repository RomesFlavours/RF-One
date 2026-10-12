"""Wine type registry: a standard name plus optional alternative names.

Every name of every type is a `WineTypeName` whose normalized key is unique
across ALL types, so "Pinot Gris" cannot become a second type once it is an
alternative name of "Pinot Grigio", and "pinot  grigio" cannot become a
second "Pinot Grigio". Many catalog wines may share one type.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models as m

MAX_NAME_LENGTH = 120

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'"})


def clean_name(raw: str | None) -> str:
    """Trimmed, single-spaced display form of a name."""
    return re.sub(r"\s+", " ", (raw or "").translate(_APOSTROPHES)).strip()


def name_key(raw: str | None) -> str:
    """Comparison key: accents, case, punctuation and spacing ignored
    ("Gewürztraminer" == "gewurztraminer", "Moscato D'Asti" == "moscato d asti")."""
    decomposed = unicodedata.normalize("NFKD", clean_name(raw))
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^0-9a-z]+", " ", without_accents.casefold()).strip()


class WineTypeError(ValueError):
    pass


def list_wine_types(session: Session) -> list[m.WineType]:
    return list(
        session.scalars(
            select(m.WineType).options(selectinload(m.WineType.names)).order_by(m.WineType.standard_name)
        ).all()
    )


def find_type_by_name(session: Session, raw: str | None) -> m.WineType | None:
    key = name_key(raw)
    if not key:
        return None
    row = session.scalars(select(m.WineTypeName).where(m.WineTypeName.name_key == key)).first()
    return row.wine_type if row is not None else None


def _validated_names(standard_name: str, aliases: list[str]) -> tuple[str, list[str]]:
    standard = clean_name(standard_name)
    if not standard:
        raise WineTypeError("The standard name is required.")
    seen = {name_key(standard)}
    cleaned: list[str] = []
    for alias in aliases:
        alias = clean_name(alias)
        key = name_key(alias)
        if not key or key in seen:
            continue  # blank or a repetition of a name already given: nothing to add
        seen.add(key)
        cleaned.append(alias)
    for name in [standard, *cleaned]:
        if len(name) > MAX_NAME_LENGTH:
            raise WineTypeError(f"{name!r} is longer than {MAX_NAME_LENGTH} characters.")
        if not name_key(name):
            raise WineTypeError(f"{name!r} is not a usable name.")
    return standard, cleaned


def _conflicts(session: Session, names: list[str], own_type_id: int | None) -> list[str]:
    messages = []
    for name in names:
        existing = session.scalars(select(m.WineTypeName).where(m.WineTypeName.name_key == name_key(name))).first()
        if existing is not None and existing.wine_type_id != own_type_id:
            owner = existing.wine_type.standard_name
            messages.append(f"{name!r} already identifies the wine type {owner!r}.")
    return messages


def create_wine_type(session: Session, *, standard_name: str, aliases: list[str] | None = None) -> m.WineType:
    standard, cleaned = _validated_names(standard_name, aliases or [])
    conflicts = _conflicts(session, [standard, *cleaned], None)
    if conflicts:
        raise WineTypeError(" ".join(conflicts))
    wine_type = m.WineType(standard_name=standard)
    wine_type.names.append(m.WineTypeName(name=standard, name_key=name_key(standard), is_standard=True))
    for alias in cleaned:
        wine_type.names.append(m.WineTypeName(name=alias, name_key=name_key(alias), is_standard=False))
    session.add(wine_type)
    session.flush()
    return wine_type


def update_wine_type(
    session: Session, wine_type: m.WineType, *, standard_name: str, aliases: list[str] | None = None,
) -> m.WineType:
    """Replace the type's names. Its wines are untouched (they reference the
    type, not a name)."""
    standard, cleaned = _validated_names(standard_name, aliases or [])
    conflicts = _conflicts(session, [standard, *cleaned], wine_type.id)
    if conflicts:
        raise WineTypeError(" ".join(conflicts))
    wanted = {name_key(standard): (standard, True), **{name_key(a): (a, False) for a in cleaned}}
    for row in list(wine_type.names):
        if row.name_key not in wanted:
            wine_type.names.remove(row)
    session.flush()  # free removed keys before re-adding them in another role
    present = {row.name_key: row for row in wine_type.names}
    for key, (name, is_standard) in wanted.items():
        row = present.get(key)
        if row is None:
            wine_type.names.append(m.WineTypeName(name=name, name_key=key, is_standard=is_standard))
        else:
            row.name = name
            row.is_standard = is_standard
    wine_type.standard_name = standard
    session.flush()
    return wine_type


# ---------------------------------------------------------------------------
# Initial load from Wine.xlsb, sheet "Base", column A (A3:A69, 67 types)
# ---------------------------------------------------------------------------

# Read from the Product Owner's `Wine.xlsb` (version of 2026-02-14). No
# spaces or duplicates were found. Only evident misspellings are corrected,
# and the spelling found in the workbook is kept as an alternative name so
# it is still recognised. No commercially distinct types are merged (e.g.
# Gavi / Gavi di Gavi, Prosecco / Prosecco Rosato, the Montepulciano
# variants stay separate). "Pinot Gris" is added as an alternative name of
# "Pinot Grigio", the example of the same type under two names given in the
# task.
REFERENCE_WINE_TYPES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Aglianico", ()),
    ("Amarone", ()),
    ("Barbaresco", ()),
    ("Barolo", ()),
    ("Blend", ()),
    ("Bolgheri", ()),
    ("Brachetto", ()),
    ("Brunello", ()),
    ("Cabernet Franc", ()),
    ("Cabernet Sauvignon", ()),
    ("Campi Taurasini", ()),
    ("Cannonau", ()),
    ("Capri Bianco", ()),
    ("Cerasuolo", ()),
    ("Chardonnay", ()),
    ("Chianti", ()),
    ("Chianti Classico", ()),
    ("Dolcetto", ()),
    ("Falanghina", ()),
    ("Fiano", ()),
    ("Friulano", ()),
    ("Gavi", ()),
    ("Gavi di Gavi", ("Gavi de Gavi",)),       # workbook: "Gavi de Gavi"
    ("Gewürztraminer", ()),
    ("Greco di Tufo", ()),
    ("Grillo", ()),
    ("Lagrein", ("Langrein",)),                # workbook: "Langrein" (its Wine List sheet spells "Lagrein")
    ("Lugana", ()),
    ("Malbec", ("Malbech",)),                  # workbook: "Malbech"
    ("Merlot", ()),
    ("Montepulciano", ()),
    ("Montepulciano Abruzzo", ()),
    ("Montepulciano Nobile", ()),
    ("Montepulciano Riserva", ()),
    ("Morellino di Scansano", ()),
    ("Moscato D'Asti", ()),
    ("Moscato Fizzy", ()),
    ("Nebbiolo", ()),
    ("Negroamaro", ()),
    ("Nerello Mascalese", ()),
    ("Nero D'Avola", ()),
    ("Pecorino", ()),
    ("Pinot Grigio", ("Pinot Gris",)),
    ("Pinot Nero", ()),
    ("Primitivo", ()),
    ("Primitivo Rosato", ()),
    ("Prosecco", ()),
    ("Prosecco Rosato", ()),
    ("Riesling", ()),
    ("Ripasso", ()),
    ("Roero Arneis", ("Roero Arnais",)),       # workbook: "Roero Arnais"
    ("Rosso Montalcino", ()),
    ("Rosso Veneto", ()),
    ("Sabbie dell'Etna", ()),
    ("Sagrantino di Montefalco", ()),
    ("Salice Salentino", ()),
    ("Sangiovese", ()),
    ("Sangue di Giuda", ()),
    ("Sauvignon Blanc", ()),
    ("Soave", ()),
    ("Supertuscany", ()),
    ("Syrah", ()),
    ("Valpolicella", ()),
    ("Verdicchio", ()),
    ("Vermentino", ()),
    ("Vernaccia", ()),
    ("Vino Cucina", ()),
)


@dataclass
class SeedReport:
    created: list[str] = field(default_factory=list)
    names_added: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def seed_reference_wine_types(
    session: Session, reference: tuple[tuple[str, tuple[str, ...]], ...] = REFERENCE_WINE_TYPES,
) -> SeedReport:
    """Load the reference types. Repeatable: a type already known under any
    of its names is completed with the names it lacks, never created again;
    a name already used by a DIFFERENT type is reported, never moved. Names
    edited by hand afterwards are kept."""
    report = SeedReport()
    for standard, aliases in reference:
        names = [standard, *aliases]
        existing = None
        for name in names:
            existing = find_type_by_name(session, name)
            if existing is not None:
                break
        if existing is None:
            create_wine_type(session, standard_name=standard, aliases=list(aliases))
            report.created.append(standard)
            continue
        added = False
        for name in names:
            found = find_type_by_name(session, name)
            if found is None:
                existing.names.append(m.WineTypeName(name=clean_name(name), name_key=name_key(name), is_standard=False))
                session.flush()
                report.names_added.append(f"{name} -> {existing.standard_name}")
                added = True
            elif found.id != existing.id:
                report.conflicts.append(f"{name!r} belongs to {found.standard_name!r}, expected {existing.standard_name!r}")
        if not added:
            report.unchanged.append(existing.standard_name)
    return report
