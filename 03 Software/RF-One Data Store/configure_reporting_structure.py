#!/usr/bin/env python
"""Apply RF-One's real economic reporting configuration
(BANK_REPORTING_CONFIGURATION_001).

Creates, idempotently:

* one ACTIVE `ReportingGroup` named `ReportingGroup`;
* one LEGAL `ReportingEntity` per existing `LegalEntity`, resolved by
  LEGAL NAME rather than by id;
* destination (ship-to) mappings ONLY where existing evidence in this
  database actually establishes them.

Deliberately a reviewable script and not a migration: this is mutable
configuration, and migrations in this repository carry schema, never
configuration data.

**Nothing is invented.** The destination mappings below are not a fixed
list — the script goes looking for the evidence and refuses to write a
mapping it cannot support. Every mapping it does write records the exact
evidence that justified it, so a reviewer can check the reasoning rather
than trust the outcome.

Dry-run by default. Pass `--apply` to write.

Never touches AWS, never imports Bank data, never modifies a LegalEntity,
a Restaurant, a PaymentInstrument, a settlement, a Supplier, a
PurchaseDocument or a PurchaseLine.
"""

from __future__ import annotations

import argparse
import re
import sys

from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import destination_evidence
from rfone_data_store.bank_reconciliation import reporting_entity as entities
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    get_database_url,
    redact_database_url,
)

REPORTING_GROUP_NAME = "ReportingGroup"
REPORTING_GROUP_CODE = "REPORTING_GROUP"

# The operating locations whose ship-to text RF-One may eventually see, and
# the abbreviation RF-One's own configuration uses for each. Nothing here
# asserts a relationship — each one is only a QUESTION the evidence search
# below has to answer, and an unanswered question produces no mapping.
LOCATION_CANDIDATES = (
    ("Winter Park", "WP"),
    ("Mount Dora", "MD"),
)


def _entity_code(legal_name: str) -> str:
    """A stable, readable code derived from the legal name."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", legal_name).strip("_").upper()
    return f"RE_{cleaned}"


def _tokens(text: str | None) -> list[str]:
    if not text:
        return []
    return re.sub(r"[^A-Za-z0-9]+", " ", text).upper().split()


def _mentions(text: str | None, location: str, abbreviation: str) -> bool:
    """Whether this text names the location.

    Three precise forms, never a loose substring scan: the full location
    name, the bare abbreviation as its own word, or the abbreviation
    suffixed onto an RF-prefixed token (RFWP, RFMD). Matching "MD" as a
    plain substring would hit unrelated words, which is exactly the kind of
    coincidence that puts a cost on the wrong company."""
    tokens = _tokens(text)
    if not tokens:
        return False
    location_tokens = _tokens(location)
    joined = " ".join(tokens)
    if " ".join(location_tokens) in joined:
        return True
    if abbreviation.upper() in tokens:
        return True
    return any(
        token.startswith("RF") and token[2:] == abbreviation.upper() for token in tokens
    )


def _evidence_for_location(session, location: str, abbreviation: str) -> dict:
    """Which Legal Entity, if any, this database says the location belongs to.

    Two independent kinds of evidence, both already in RF-One and neither
    of them a guess:

    * a Legal Entity whose own LEGAL NAME contains the location;
    * a Payment Instrument whose name carries the location or RF-One's own
      abbreviation for it, and which belongs to a Legal Entity.

    A conclusion is reached only when every piece of evidence points at the
    SAME Legal Entity. Two candidates means ambiguity, and ambiguity means
    no mapping."""
    supported: dict[int, list[str]] = {}

    for legal_entity in session.scalars(select(m.LegalEntity).order_by(m.LegalEntity.id)):
        if _mentions(legal_entity.legal_name, location, abbreviation):
            supported.setdefault(legal_entity.id, []).append(
                f"Legal Entity {legal_entity.legal_name!r} is itself named after {location}"
            )

    for instrument in session.scalars(
        select(m.PaymentInstrument).order_by(m.PaymentInstrument.id)
    ):
        if instrument.legal_entity_id is None:
            continue
        if not _mentions(instrument.display_name, location, abbreviation):
            continue
        owner = session.get(m.LegalEntity, instrument.legal_entity_id)
        supported.setdefault(instrument.legal_entity_id, []).append(
            f"Payment Instrument {instrument.display_name!r} belongs to "
            f"{owner.legal_name if owner else 'an unnamed Legal Entity'}"
        )

    # Restaurants and Locations are recorded as context. They are never on
    # their own sufficient here: `Restaurant.legal_entity_id` is NULL in
    # this database and this task must not set it (§4), so a restaurant
    # name can corroborate a conclusion but cannot reach one.
    context: list[str] = []
    for restaurant in session.scalars(select(m.Restaurant).order_by(m.Restaurant.id)):
        if _mentions(restaurant.name, location, abbreviation):
            owner = (
                session.get(m.LegalEntity, restaurant.legal_entity_id)
                if restaurant.legal_entity_id
                else None
            )
            context.append(
                f"Restaurant {restaurant.name!r} (legal entity: "
                f"{owner.legal_name if owner else 'NOT SET'})"
            )

    return {"supported": supported, "context": context}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Write the configuration. Without it the script only reports what it would do.",
    )
    args = parser.parse_args()

    url = get_database_url()
    print(f"Database URL: {redact_database_url(url)}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN (nothing will be written)'}")
    print()

    engine = create_configured_engine(url)
    try:
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            created, findings = configure(session, apply=args.apply)
            if args.apply:
                session.commit()
            else:
                session.rollback()
    finally:
        engine.dispose()

    print()
    print("=" * 70)
    for line in created:
        print(line)
    print()
    for line in findings:
        print(line)
    return 0


def configure(session, *, apply: bool) -> tuple[list[str], list[str]]:
    """Apply (or plan) the configuration. Returns what changed and what was
    deliberately left alone."""
    actions: list[str] = []
    findings: list[str] = []

    # --- 1. The reporting group ------------------------------------------
    group = session.scalar(
        select(m.ReportingGroup).where(m.ReportingGroup.code == REPORTING_GROUP_CODE)
    )
    if group is None:
        if apply:
            group = entities.create_reporting_group(
                session,
                code=REPORTING_GROUP_CODE,
                name=REPORTING_GROUP_NAME,
                description=(
                    "The RF-One economic reporting perimeter. Product Owner decision "
                    "(BANK_REPORTING_CONFIGURATION_001 §2). Not a Corporate: see "
                    "ReportingGroup's own docstring."
                ),
            )
            actions.append(f"CREATED ReportingGroup {group.name!r} (id {group.id})")
        else:
            actions.append(f"WOULD CREATE ReportingGroup {REPORTING_GROUP_NAME!r}")
    else:
        actions.append(f"ReportingGroup {group.name!r} already exists (id {group.id})")

    # --- 2. One LEGAL reporting entity per Legal Entity -------------------
    legal_entities = list(
        session.scalars(select(m.LegalEntity).order_by(m.LegalEntity.legal_name))
    )
    for legal_entity in legal_entities:
        existing = entities.reporting_entity_for_legal_entity(
            session, legal_entity_id=legal_entity.id
        )
        if existing is not None:
            actions.append(
                f"ReportingEntity for {legal_entity.legal_name!r} already exists "
                f"({existing.code})"
            )
            continue
        if not apply or group is None:
            actions.append(
                f"WOULD CREATE LEGAL ReportingEntity {legal_entity.legal_name!r}"
            )
            continue
        entity = entities.create_legal_entity_reporting_entity(
            session,
            code=_entity_code(legal_entity.legal_name),
            name=legal_entity.legal_name,
            legal_entity_id=legal_entity.id,
            reporting_group_id=group.id,
            description=(
                "LEGAL reporting entity: its P&L is this Legal Entity's P&L "
                "(BANK_REPORTING_CONFIGURATION_001 §3)."
            ),
        )
        actions.append(
            f"CREATED LEGAL ReportingEntity {entity.name!r} ({entity.code}) -> "
            f"LegalEntity {legal_entity.id}"
        )

    # --- 3. Destination mappings, only where evidence supports them -------
    findings.append("DESTINATION EVIDENCE")
    findings.append("-" * 70)

    ship_to_values = session.execute(
        select(m.PurchaseDocument.destination_location, m.PurchaseDocument.id).where(
            m.PurchaseDocument.destination_location.is_not(None)
        )
    ).all()
    document_count = session.scalar(
        select(m.PurchaseDocument.id).order_by(m.PurchaseDocument.id.desc()).limit(1)
    )
    findings.append(
        f"Purchase documents carrying a ship-to value: {len(ship_to_values)} "
        f"(highest document id seen: {document_count})"
    )
    if not ship_to_values:
        findings.append(
            "  No document in this database records a destination at all, so NO mapping can "
            "be created from document evidence. Nothing is invented to fill that gap."
        )
    else:
        for value, document_id in ship_to_values:
            findings.append(f"  document {document_id}: {value!r}")

    for location, abbreviation in LOCATION_CANDIDATES:
        evidence = _evidence_for_location(session, location, abbreviation)
        supported = evidence["supported"]
        findings.append("")
        findings.append(f"{location}:")
        for note in evidence["context"]:
            findings.append(f"  context   {note}")
        for legal_entity_id, reasons in sorted(supported.items()):
            for reason in reasons:
                findings.append(f"  evidence  {reason}")

        if len(supported) != 1:
            findings.append(
                f"  RESULT    no mapping created — evidence points at {len(supported)} "
                "Legal Entities, which is not a conclusion."
            )
            continue

        legal_entity_id = next(iter(supported))
        entity = entities.reporting_entity_for_legal_entity(
            session, legal_entity_id=legal_entity_id
        )
        if entity is None:
            # In a dry run the reporting entities have not been written, so
            # name the Legal Entity the mapping WOULD point at rather than
            # reporting a failure that only exists because nothing was saved.
            owner = session.get(m.LegalEntity, legal_entity_id)
            findings.append(
                f"  RESULT    WOULD CREATE global mapping -> "
                f"{owner.legal_name if owner else legal_entity_id!r} "
                "(its reporting entity is created earlier in the same run)"
                if not apply
                else "  RESULT    no mapping created — the reporting entity does not exist."
            )
            continue

        existing = session.scalar(
            select(m.ReportingEntityDestinationAlias).where(
                m.ReportingEntityDestinationAlias.normalized_key
                == destination_evidence.normalize_destination(location),
                m.ReportingEntityDestinationAlias.supplier_id.is_(None),
            )
        )
        if existing is not None:
            findings.append(f"  RESULT    mapping already exists -> {entity.name!r}")
            continue

        evidence_text = (
            f"{location} resolves to {entity.name!r} on existing RF-One configuration: "
            + "; ".join(reason for reasons in supported.values() for reason in reasons)
            + ". No document ship-to text was available to corroborate this; "
            "no payer, supplier, historical majority or item category was consulted."
        )
        if not apply:
            findings.append(f"  RESULT    WOULD CREATE global mapping -> {entity.name!r}")
            continue

        alias = destination_evidence.record_destination_alias(
            session,
            raw_value=location,
            reporting_entity_id=entity.id,
            evidence=evidence_text,
            confirmation_source=m.DESTINATION_SOURCE_SYSTEM,
        )
        findings.append(
            f"  RESULT    CREATED global mapping {alias.raw_value!r} -> {entity.name!r}"
        )

    findings.append("")
    findings.append("LEFT DELIBERATELY UNMAPPED")
    findings.append("-" * 70)
    findings.append(
        "  RF Gelati, LLC — no physical ship-to is invented for it (§9). It receives "
        "allocations from explicit document evidence or an operator decision."
    )
    for restaurant in session.scalars(select(m.Restaurant).order_by(m.Restaurant.id)):
        findings.append(
            f"  {restaurant.name!r} — a trading name. A global mapping from a trading name "
            "would claim it means the same entity on every source's paperwork, which no "
            "evidence supports. Map it per supplier when a real document uses it."
        )
    return actions, findings


if __name__ == "__main__":
    sys.exit(main())
