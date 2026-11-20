#!/usr/bin/env python
"""Real economic reporting configuration —
BANK_REPORTING_CONFIGURATION_001.

Proves, on a throwaway database:

* one ReportingGroup containing exactly N LEGAL reporting entities, and a
  consolidated P&L that counts each entity's allocations exactly once;
* destination (ship-to) evidence resolving an economic owner WITHOUT
  requiring the text to equal a reporting entity's name — scoped per
  supplier where the evidence is supplier-specific, ambiguous where it
  genuinely is, and silent where it knows nothing;
* WHO -> Supplier discovery that links on strong unique evidence, refuses
  on ambiguity or weak evidence, never links on amount, and never creates
  a Supplier.

Never touches AWS, RDS, the operational database, or a real bank file. No
Bank data is imported.
"""

from __future__ import annotations

import sys
from datetime import date, datetime

from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store.bank_reconciliation import destination_evidence as destinations
from rfone_data_store.bank_reconciliation import economic_allocation as alloc
from rfone_data_store.bank_reconciliation import economic_reporting as reporting
from rfone_data_store.bank_reconciliation import invoice_evidence as evidence
from rfone_data_store.bank_reconciliation import reporting_entity as entities
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)
from rfone_data_store.purchasing import repository as purchasing

import configure_reporting_structure as configurator

POSTING_DATE = date(2026, 4, 15)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            passed.append(description)
        else:
            failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    def raises(description: str, fn, fragment: str) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — the point is that something refused
            check(description, fragment.lower() in str(exc).lower(), detail=str(exc))
        else:
            check(description, False, detail="nothing was raised")

    url = resolve_test_database_url("bank_reporting_configuration")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)

    try:
        session_factory = create_session_factory(engine)
        with session_factory() as s:
            fx = _build_fixture(s)
            _test_configurator(s, fx, check)
            _test_reporting_group(s, fx, check)
            _test_destinations(s, fx, check, raises)
            _test_who_supplier(s, fx, check)
            s.rollback()
    finally:
        engine.dispose()

    print()
    print(f"Checks passed: {len(passed)}")
    print(f"Checks failed: {len(failed)}")
    if failed:
        print()
        for description in failed:
            print(f"  FAILED  {description}")
        return 1
    for description in passed:
        print(f"  ok  {description}")
    return 0


class Fixture:
    pass


def _build_fixture(s) -> Fixture:
    """A disposable stand-in for the real configuration: the same three
    Legal Entities, the same abbreviation conventions on the payment
    instruments, and a Restaurant whose legal entity is deliberately NOT
    set — exactly as the golden database has it."""
    fx = Fixture()

    fx.restaurant = m.Restaurant(name="Rome's Flavours - WP")
    s.add(fx.restaurant)
    s.flush()

    fx.aed = m.LegalEntity(legal_name="Angeli E Demoni, LLC", status="ACTIVE")
    fx.gelati = m.LegalEntity(legal_name="RF Gelati, LLC", status="ACTIVE")
    fx.md = m.LegalEntity(legal_name="RF Mount Dora, LLC", status="ACTIVE")
    s.add_all([fx.aed, fx.gelati, fx.md])
    s.flush()
    fx.legal_entity_count = s.scalar(select(func.count(m.LegalEntity.id)))

    for name, legal_entity in (
        ("WP-Checking", fx.aed),
        ("RFWP- Checking", fx.aed),
        ("RF Corporate", fx.gelati),
        ("RFMD Checking", fx.md),
        ("Amex", fx.aed),
    ):
        s.add(
            m.PaymentInstrument(
                instrument_type="BANK_ACCOUNT", display_name=name,
                legal_entity_id=legal_entity.id, status="ACTIVE",
            )
        )
    s.flush()
    fx.bank_aed = s.scalar(
        select(m.PaymentInstrument).where(m.PaymentInstrument.display_name == "WP-Checking")
    )
    fx.bank_gelati = s.scalar(
        select(m.PaymentInstrument).where(m.PaymentInstrument.display_name == "RF Corporate")
    )

    fx.why_food = s.scalar(
        select(m.BankTransactionReason).where(m.BankTransactionReason.code == "FOOD_PURCHASES")
    )
    fx.why_supplies = s.scalar(
        select(m.BankTransactionReason).where(
            m.BankTransactionReason.code == "RESTAURANT_OPERATING_SUPPLIES"
        )
    )

    fx.sup_prime = purchasing.get_or_create_supplier(s, fx.restaurant.id, "Prime Line Distributors")
    fx.sup_keith = purchasing.get_or_create_supplier(s, fx.restaurant.id, "Ben E. Keith Foods")
    fx.sup_costco = purchasing.get_or_create_supplier(s, fx.restaurant.id, "Costco Wholesale")
    purchasing.add_supplier_alias(
        s, supplier_id=fx.sup_prime.id, alias_name="PRIME LINE DISTRIBUTORS INVOICE",
        source="Phase 2 canonical cleanup",
    )
    fx.supplier_count = s.scalar(select(func.count(m.Supplier.id)))

    fx.occurrence_type = m.BankOccurrenceType(code="SUPPLIER", name="Supplier", status="ACTIVE")
    s.add(fx.occurrence_type)
    s.flush()
    return fx


def _occurrence(s, fx, name: str) -> "m.BankOccurrence":
    row = m.BankOccurrence(
        canonical_name=name, occurrence_type_id=fx.occurrence_type.id, status="ACTIVE",
    )
    s.add(row)
    s.flush()
    return row


def _transaction(s, instrument, amount_minor: int, description: str) -> "m.FinancialTransaction":
    transaction = m.FinancialTransaction(
        payment_instrument_id=instrument.id,
        posting_date=POSTING_DATE,
        transaction_date=POSTING_DATE,
        description_original=description,
        amount_minor=amount_minor,
        status="COMPLETED",
        classification="UNKNOWN",
        accounting_status="CANONICAL",
    )
    s.add(transaction)
    s.flush()
    return transaction


# ---------------------------------------------------------------------------
# The configurator itself
# ---------------------------------------------------------------------------


def _test_configurator(s, fx, check) -> None:
    actions, findings = configurator.configure(s, apply=True)
    joined = "\n".join(findings)

    group = s.scalar(
        select(m.ReportingGroup).where(
            m.ReportingGroup.code == configurator.REPORTING_GROUP_CODE
        )
    )
    check(
        "the configurator creates exactly one ReportingGroup named ReportingGroup",
        group is not None
        and group.name == "ReportingGroup"
        and s.scalar(select(func.count(m.ReportingGroup.id))) == 1,
        detail=str(group and group.name),
    )
    fx.group = group

    entity_rows = list(
        s.scalars(select(m.ReportingEntity).order_by(m.ReportingEntity.code))
    )
    check(
        "it creates one LEGAL reporting entity per Legal Entity, and no VIRTUAL ones",
        len(entity_rows) == 3
        and all(e.is_legal for e in entity_rows)
        and not any(e.is_virtual for e in entity_rows),
        detail=str([(e.code, e.entity_type) for e in entity_rows]),
    )
    check(
        "each reporting entity is bound to the Legal Entity of the same legal name",
        all(e.legal_entity is not None and e.name == e.legal_entity.legal_name
            for e in entity_rows),
    )
    check(
        "all three belong to the one reporting group",
        all(e.reporting_group_id == group.id for e in entity_rows),
    )
    check(
        "no duplicate LegalEntity row was created",
        s.scalar(select(func.count(m.LegalEntity.id))) == fx.legal_entity_count,
    )
    check(
        "Restaurant.legal_entity_id is left untouched",
        s.get(m.Restaurant, fx.restaurant.id).legal_entity_id is None,
    )

    fx.re_aed = s.scalar(
        select(m.ReportingEntity).where(m.ReportingEntity.legal_entity_id == fx.aed.id)
    )
    fx.re_gelati = s.scalar(
        select(m.ReportingEntity).where(m.ReportingEntity.legal_entity_id == fx.gelati.id)
    )
    fx.re_md = s.scalar(
        select(m.ReportingEntity).where(m.ReportingEntity.legal_entity_id == fx.md.id)
    )

    # [6]/[7] the two location mappings, derived from evidence
    wp = destinations.resolve_destination(s, raw_value="Winter Park")
    md = destinations.resolve_destination(s, raw_value="Mount Dora")
    check(
        "[6] Winter Park evidence resolves to Angeli E Demoni",
        wp.is_resolved and wp.reporting_entity_id == fx.re_aed.id,
        detail=wp.explanation,
    )
    check(
        "[7] Mount Dora evidence resolves to RF Mount Dora",
        md.is_resolved and md.reporting_entity_id == fx.re_md.id,
        detail=md.explanation,
    )
    check(
        "[10] each mapping records the evidence that justified it",
        all(
            alias.evidence and "Payment Instrument" in alias.evidence
            for alias in destinations.list_destination_aliases(s)
        ),
    )
    check(
        "[10] and records that it rests on configuration, not on a document",
        all(
            alias.confirmation_source == m.DESTINATION_SOURCE_SYSTEM
            and "No document ship-to text" in alias.evidence
            for alias in destinations.list_destination_aliases(s)
        ),
    )

    # [9] RF Gelati gets no invented physical destination
    gelati_aliases = destinations.list_destination_aliases(
        s, reporting_entity_id=fx.re_gelati.id
    )
    check(
        "[9] no destination mapping is invented for RF Gelati",
        gelati_aliases == [],
    )
    check(
        "[9] and the reason is stated rather than left silent",
        "no physical ship-to is invented for it" in joined,
    )
    check(
        "the trading name is deliberately left unmapped at global scope",
        "a trading name" in joined
        and destinations.resolve_destination(
            s, raw_value="Rome's Flavours - WP",
        ).outcome == destinations.UNKNOWN,
    )
    check(
        "the configurator reports that no document carries a ship-to value",
        "Purchase documents carrying a ship-to value: 0" in joined,
    )

    # Idempotence: running it again changes nothing.
    before = (
        s.scalar(select(func.count(m.ReportingGroup.id))),
        s.scalar(select(func.count(m.ReportingEntity.id))),
        s.scalar(select(func.count(m.ReportingEntityDestinationAlias.id))),
    )
    configurator.configure(s, apply=True)
    after = (
        s.scalar(select(func.count(m.ReportingGroup.id))),
        s.scalar(select(func.count(m.ReportingEntity.id))),
        s.scalar(select(func.count(m.ReportingEntityDestinationAlias.id))),
    )
    check("the configurator is idempotent", before == after, detail=f"{before} -> {after}")


# ---------------------------------------------------------------------------
# §12 — reporting group P&L
# ---------------------------------------------------------------------------


def _test_reporting_group(s, fx, check) -> None:
    members = entities.entities_in_group(s, reporting_group_id=fx.group.id)
    check(
        "[§12] the ReportingGroup contains exactly three reporting entities",
        len(members) == 3,
        detail=str([e.code for e in members]),
    )

    # One allocation per entity, all paid by the same Angeli E Demoni account
    # so the cross-entity behaviour is exercised too.
    txn_aed = _transaction(s, fx.bank_aed, -10_000, "AED OWN COST")
    alloc.set_allocations(
        s, financial_transaction_id=txn_aed.id,
        specs=[alloc.AllocationSpec(
            amount_minor=-10_000, reporting_entity_id=fx.re_aed.id,
            transaction_reason_id=fx.why_food.id,
        )],
    )
    txn_md = _transaction(s, fx.bank_aed, -20_000, "PAID FOR MOUNT DORA")
    md_allocation = alloc.set_allocations(
        s, financial_transaction_id=txn_md.id,
        specs=[alloc.AllocationSpec(
            amount_minor=-20_000, reporting_entity_id=fx.re_md.id,
            transaction_reason_id=fx.why_food.id,
        )],
    )[0]
    txn_gelati = _transaction(s, fx.bank_aed, -30_000, "PAID FOR GELATI")
    alloc.set_allocations(
        s, financial_transaction_id=txn_gelati.id,
        specs=[alloc.AllocationSpec(
            amount_minor=-30_000, reporting_entity_id=fx.re_gelati.id,
            transaction_reason_id=fx.why_supplies.id,
        )],
    )

    aed_pl = reporting.profit_and_loss_for_entity(s, reporting_entity_id=fx.re_aed.id)
    md_pl = reporting.profit_and_loss_for_entity(s, reporting_entity_id=fx.re_md.id)
    gelati_pl = reporting.profit_and_loss_for_entity(s, reporting_entity_id=fx.re_gelati.id)

    check(
        "[§12] an Angeli E Demoni allocation appears in the AeD P&L",
        aed_pl.total_minor == -10_000,
        detail=str(aed_pl.total_minor),
    )
    check(
        "[§12] an RF Mount Dora allocation appears in the MD P&L",
        md_pl.total_minor == -20_000,
        detail=str(md_pl.total_minor),
    )
    check(
        "[§12] an RF Gelati allocation appears in the RF Gelati P&L",
        gelati_pl.total_minor == -30_000,
        detail=str(gelati_pl.total_minor),
    )

    consolidated = reporting.consolidated_profit_and_loss(
        s, reporting_group_id=fx.group.id,
    )
    check(
        "[§12] the consolidated P&L contains all three, each exactly once",
        consolidated.total_minor == -60_000
        and consolidated.allocation_count == 3,
        detail=f"{consolidated.total_minor} / {consolidated.allocation_count}",
    )
    check(
        "[§12] the consolidated total equals the sum of its entities",
        consolidated.total_minor
        == aed_pl.total_minor + md_pl.total_minor + gelati_pl.total_minor,
    )

    positions = reporting.intercompany_positions(s)
    check(
        "[§12] cross-entity payer effects exist as Balance Sheet positions",
        len(positions) == 2
        and all(p.payer_legal_entity_id == fx.aed.id for p in positions)
        and all(p.due_from_code == "1610" and p.due_to_code == "2710" for p in positions),
        detail=str([(p.owner_legal_entity_id, p.amount_minor) for p in positions]),
    )
    check(
        "[§12] and never appear in any P&L",
        all(
            line.code not in ("1610", "2710")
            for report in (aed_pl, md_pl, gelati_pl, consolidated)
            for line in report.lines
        ),
    )
    check(
        "[§12] the payer's own P&L carries only what it economically bore",
        aed_pl.total_minor == -10_000 and md_allocation.is_cross_entity,
    )


# ---------------------------------------------------------------------------
# §13 — destination resolution
# ---------------------------------------------------------------------------


def _test_destinations(s, fx, check, raises) -> None:
    # [1] an exact alias resolves to one entity
    alias = destinations.record_destination_alias(
        s, raw_value="WINTER PARK STORE", reporting_entity_id=fx.re_aed.id,
        evidence="Operator: this is the Winter Park kitchen's ship-to label.",
    )
    resolution = destinations.resolve_destination(s, raw_value="  winter park store  ")
    check(
        "[1] a destination alias resolves to exactly one reporting entity",
        resolution.is_resolved
        and resolution.reporting_entity_id == fx.re_aed.id
        and resolution.alias_id == alias.id,
        detail=resolution.explanation,
    )
    check(
        "[1] matching does not require equality with the entity's own name",
        alias.normalized_key == "WINTER PARK STORE"
        and alias.normalized_key != destinations.normalize_destination(fx.re_aed.name),
    )

    # [2] a supplier-scoped alias resolves for that supplier
    destinations.record_destination_alias(
        s, raw_value="ROME'S FLAVOURS", reporting_entity_id=fx.re_aed.id,
        supplier_id=fx.sup_prime.id,
        evidence="Prime Line addresses the Winter Park kitchen by its trading name.",
    )
    scoped = destinations.resolve_destination(
        s, raw_value="Rome's Flavours", supplier_id=fx.sup_prime.id,
    )
    check(
        "[2] a supplier-scoped alias resolves correctly for that supplier",
        scoped.is_resolved
        and scoped.reporting_entity_id == fx.re_aed.id
        and scoped.scope == m.DESTINATION_SCOPE_SUPPLIER,
        detail=scoped.explanation,
    )

    # [3] the same text can mean something else for a different supplier
    destinations.record_destination_alias(
        s, raw_value="ROME'S FLAVOURS", reporting_entity_id=fx.re_md.id,
        supplier_id=fx.sup_keith.id,
        evidence="Ben E. Keith ships to the Mount Dora kitchen under the same trading name.",
    )
    other = destinations.resolve_destination(
        s, raw_value="Rome's Flavours", supplier_id=fx.sup_keith.id,
    )
    check(
        "[3] the same text maps differently under a different supplier scope",
        other.is_resolved and other.reporting_entity_id == fx.re_md.id,
        detail=other.explanation,
    )
    check(
        "[3] neither supplier-scoped mapping leaks into the other",
        scoped.reporting_entity_id != other.reporting_entity_id,
    )

    # [4] without supplier context, that same text is ambiguous
    ambiguous = destinations.resolve_destination(s, raw_value="Rome's Flavours")
    check(
        "[4] the same text without supplier context is ambiguous, not guessed",
        ambiguous.needs_operator
        and ambiguous.reporting_entity_id is None
        and set(ambiguous.candidate_entity_ids) == {fx.re_aed.id, fx.re_md.id},
        detail=ambiguous.explanation,
    )

    # [5] an unknown destination produces no guess
    unknown = destinations.resolve_destination(
        s, raw_value="SOME WAREHOUSE NOBODY CONFIGURED",
    )
    check(
        "[5] an unknown destination produces no guess",
        unknown.outcome == destinations.UNKNOWN and unknown.reporting_entity_id is None,
        detail=unknown.explanation,
    )
    check(
        "[5] and an unknown destination is not reported as ambiguity",
        not unknown.needs_operator,
    )

    # A supplier-scoped mapping wins over a global one.
    destinations.record_destination_alias(
        s, raw_value="MAIN KITCHEN", reporting_entity_id=fx.re_aed.id,
        evidence="Operator: the main kitchen is the Winter Park site.",
    )
    destinations.record_destination_alias(
        s, raw_value="MAIN KITCHEN", reporting_entity_id=fx.re_md.id,
        supplier_id=fx.sup_costco.id,
        evidence="Costco's 'main kitchen' account is the Mount Dora site.",
    )
    narrow = destinations.resolve_destination(
        s, raw_value="Main Kitchen", supplier_id=fx.sup_costco.id,
    )
    broad = destinations.resolve_destination(s, raw_value="Main Kitchen")
    check(
        "the narrowest matching scope wins",
        narrow.reporting_entity_id == fx.re_md.id
        and broad.reporting_entity_id == fx.re_aed.id,
        detail=f"{narrow.reporting_entity_id} / {broad.reporting_entity_id}",
    )

    # Contradictions are refused rather than silently layered.
    raises(
        "a second meaning for the same key at the same scope is refused",
        lambda: destinations.record_destination_alias(
            s, raw_value="WINTER PARK STORE", reporting_entity_id=fx.re_md.id,
            evidence="Conflicting claim.",
        ),
        "already mapped",
    )
    raises(
        "a mapping without stated evidence is refused",
        lambda: destinations.record_destination_alias(
            s, raw_value="NO EVIDENCE HERE", reporting_entity_id=fx.re_aed.id, evidence="   ",
        ),
        "needs stated evidence",
    )

    # [8] a document with no destination text leaves FOR WHOM unresolved
    doc_blank = purchasing.record_purchase_document(
        s, supplier_id=fx.sup_prime.id,
        header={"document_number": "CFG-1", "document_type": "Invoice",
                "issue_date": datetime.combine(POSTING_DATE, datetime.min.time()),
                "total_amount_minor": 5_000, "destination_location": None},
        lines=[{"line_type": "PRODUCT", "raw_description": "FLOUR",
                "source_amount_minor": 5_000, "source_line_number": 1}],
    )
    blank = destinations.resolve_document_destination(s, purchase_document_id=doc_blank.id)
    check(
        "[8] a document with no destination evidence leaves FOR WHOM unresolved",
        blank.outcome == destinations.NO_EVIDENCE
        and evidence.resolve_owner_from_document_evidence(
            s, purchase_document_id=doc_blank.id,
        ) is None,
        detail=blank.explanation,
    )

    # A document WITH a mapped destination now resolves without the text
    # having to equal an entity name.
    doc_mapped = purchasing.record_purchase_document(
        s, supplier_id=fx.sup_prime.id,
        header={"document_number": "CFG-2", "document_type": "Invoice",
                "issue_date": datetime.combine(POSTING_DATE, datetime.min.time()),
                "total_amount_minor": 5_000, "destination_location": "Rome's Flavours"},
        lines=[{"line_type": "PRODUCT", "raw_description": "FLOUR",
                "source_amount_minor": 5_000, "source_line_number": 1}],
    )
    owner = evidence.resolve_owner_from_document_evidence(
        s, purchase_document_id=doc_mapped.id,
    )
    check(
        "a mapped ship-to now establishes the beneficiary from the document",
        owner is not None and owner.id == fx.re_aed.id,
        detail=str(owner and owner.name),
    )

    # An ambiguous document destination still refuses to answer.
    doc_ambiguous = purchasing.record_purchase_document(
        s, supplier_id=fx.sup_costco.id,
        header={"document_number": "CFG-3", "document_type": "Invoice",
                "issue_date": datetime.combine(POSTING_DATE, datetime.min.time()),
                "total_amount_minor": 5_000, "destination_location": "Rome's Flavours"},
        lines=[{"line_type": "PRODUCT", "raw_description": "FLOUR",
                "source_amount_minor": 5_000, "source_line_number": 1}],
    )
    check(
        "[4] a document whose destination is mapped for other suppliers only stays unresolved",
        evidence.resolve_owner_from_document_evidence(
            s, purchase_document_id=doc_ambiguous.id,
        ) is None,
    )

    # [9] RF Gelati needs explicit evidence or an operator
    check(
        "[9] RF Gelati has no destination mapping and cannot be reached by ship-to text",
        destinations.list_destination_aliases(
            s, reporting_entity_id=fx.re_gelati.id,
        ) == [],
    )
    gelati_alias = destinations.record_destination_alias(
        s, raw_value="RF GELATI CORPORATE OFFICE", reporting_entity_id=fx.re_gelati.id,
        evidence="Operator: corporate office deliveries belong to RF Gelati.",
    )
    check(
        "[9] RF Gelati becomes reachable only once an operator states the evidence",
        gelati_alias.confirmation_source == m.DESTINATION_SOURCE_HUMAN
        and destinations.resolve_destination(
            s, raw_value="RF Gelati Corporate Office",
        ).reporting_entity_id == fx.re_gelati.id,
    )

    # [10] audit survives deactivation
    destinations.deactivate_destination_alias(
        s, alias_id=gelati_alias.id, reason="Office closed; deliveries moved.",
    )
    check(
        "[10] a retired mapping is deactivated, not deleted, and keeps its audit",
        s.get(m.ReportingEntityDestinationAlias, gelati_alias.id) is not None
        and s.get(m.ReportingEntityDestinationAlias, gelati_alias.id).status == "INACTIVE"
        and "DEACTIVATED" in s.get(
            m.ReportingEntityDestinationAlias, gelati_alias.id,
        ).evidence,
    )
    check(
        "[10] and a retired mapping stops resolving",
        destinations.resolve_destination(
            s, raw_value="RF Gelati Corporate Office",
        ).outcome == destinations.UNKNOWN,
    )

    fx.unmapped_report = destinations.unmapped_document_destinations(s)
    check(
        "the unmapped worklist names the ambiguous document destination",
        # The normalizer turns punctuation into a separator, so "Rome's"
        # normalizes to "ROME S" — deterministic, and the same rule the
        # item-identity normalizer already applies.
        any(row["normalized_key"] == "ROME S FLAVOURS" for row in fx.unmapped_report),
        detail=str(fx.unmapped_report),
    )


# ---------------------------------------------------------------------------
# §14 — WHO <-> Supplier
# ---------------------------------------------------------------------------


def _test_who_supplier(s, fx, check) -> None:
    supplier_count_before = s.scalar(select(func.count(m.Supplier.id)))

    # [11] a unique exact supplier-name match
    who_keith = _occurrence(s, fx, "Ben E. Keith Foods")
    proposal = evidence.propose_supplier_link_for_occurrence(
        s, occurrence_id=who_keith.id, auto_link=True,
    )
    check(
        "[11] a unique exact supplier name links the counterparty",
        proposal.outcome == evidence.LINK_PROPOSED
        and proposal.supplier_id == fx.sup_keith.id
        and proposal.candidates[0].match_kind == evidence.MATCH_CANONICAL_NAME,
        detail=proposal.explanation,
    )
    check(
        "[11] and the link is persisted",
        evidence.supplier_ids_for_occurrence(
            s, occurrence_id=who_keith.id,
        ) == [fx.sup_keith.id],
    )

    # [12] a SupplierAlias match
    who_prime = _occurrence(s, fx, "PRIME LINE DISTRIBUTORS INVOICE")
    alias_proposal = evidence.propose_supplier_link_for_occurrence(
        s, occurrence_id=who_prime.id, auto_link=True,
    )
    check(
        "[12] a SupplierAlias match links to the canonical supplier",
        alias_proposal.outcome == evidence.LINK_PROPOSED
        and alias_proposal.supplier_id == fx.sup_prime.id
        and alias_proposal.candidates[0].match_kind == evidence.MATCH_SUPPLIER_ALIAS,
        detail=alias_proposal.explanation,
    )

    # [13] ambiguous names produce no automatic link
    twin_a = purchasing.get_or_create_supplier(s, fx.restaurant.id, "Twin Vendor")
    twin_restaurant = m.Restaurant(name="Second Restaurant")
    s.add(twin_restaurant)
    s.flush()
    twin_b = purchasing.get_or_create_supplier(s, twin_restaurant.id, "Twin Vendor")
    who_twin = _occurrence(s, fx, "Twin Vendor")
    twin_proposal = evidence.propose_supplier_link_for_occurrence(
        s, occurrence_id=who_twin.id, auto_link=True,
    )
    check(
        "[13] two suppliers matching the same name produce no automatic link",
        twin_proposal.outcome == evidence.LINK_NEEDS_OPERATOR
        and twin_proposal.supplier_id is None
        and len(twin_proposal.candidates) == 2
        and {c.supplier_id for c in twin_proposal.candidates} == {twin_a.id, twin_b.id},
        detail=twin_proposal.explanation,
    )
    check(
        "[13] and nothing was written for the ambiguous counterparty",
        evidence.supplier_ids_for_occurrence(s, occurrence_id=who_twin.id) == [],
    )

    # A weak, too-short name is refused even when it matches exactly.
    purchasing.get_or_create_supplier(s, fx.restaurant.id, "I")
    who_short = _occurrence(s, fx, "I")
    short_proposal = evidence.propose_supplier_link_for_occurrence(
        s, occurrence_id=who_short.id, auto_link=True,
    )
    check(
        "a name too short to identify anybody is not linked automatically",
        short_proposal.outcome == evidence.LINK_NEEDS_OPERATOR
        and evidence.supplier_ids_for_occurrence(s, occurrence_id=who_short.id) == [],
        detail=short_proposal.explanation,
    )

    # [14] no supplier at all
    who_unknown = _occurrence(s, fx, "Florida Department of Revenue")
    no_match = evidence.propose_supplier_link_for_occurrence(
        s, occurrence_id=who_unknown.id, auto_link=True,
    )
    check(
        "[14] a counterparty with no matching supplier stays valid and unlinked",
        no_match.outcome == evidence.LINK_NO_MATCH
        and s.get(m.BankOccurrence, who_unknown.id) is not None
        and evidence.supplier_ids_for_occurrence(s, occurrence_id=who_unknown.id) == [],
        detail=no_match.explanation,
    )

    # [15] discovery never creates a Supplier
    check(
        "[15] no Supplier duplicate was created by any discovery attempt",
        s.scalar(select(func.count(m.Supplier.id))) == supplier_count_before + 3,
        detail=str(s.scalar(select(func.count(m.Supplier.id)))),
    )
    check(
        "[15] and the unmatched counterparty produced no Supplier of its own",
        s.scalar(
            select(func.count(m.Supplier.id)).where(
                m.Supplier.name == "Florida Department of Revenue"
            )
        ) == 0,
    )

    # [16] amount alone never links
    _transaction(s, fx.bank_aed, -30_274, "PAYMENT MATCHING AN INVOICE TOTAL")
    still_unlinked = evidence.propose_supplier_link_for_occurrence(
        s, occurrence_id=who_unknown.id, auto_link=True,
    )
    check(
        "[16] an amount that matches an invoice total never links a counterparty",
        still_unlinked.outcome == evidence.LINK_NO_MATCH
        and evidence.supplier_ids_for_occurrence(s, occurrence_id=who_unknown.id) == [],
    )
    check(
        "[16] candidate search consults names and aliases only",
        evidence.find_supplier_candidates(s, name="30274") == []
        and evidence.find_supplier_candidates(s, name="Ben E. Keith Foods") != [],
    )

    # [17] an operator-confirmed link persists
    confirmed = evidence.confirm_supplier_link(
        s, occurrence_id=who_twin.id, supplier_id=twin_a.id,
        notes="Operator: this is the Winter Park Twin Vendor account.",
    )
    check(
        "[17] an operator-confirmed link persists and is recorded as HUMAN",
        confirmed.link_source == "HUMAN"
        and evidence.supplier_ids_for_occurrence(
            s, occurrence_id=who_twin.id,
        ) == [twin_a.id],
    )

    # [18] later transactions reuse the confirmed link
    reuse = evidence.propose_supplier_link_for_occurrence(
        s, occurrence_id=who_twin.id, auto_link=True,
    )
    check(
        "[18] a later run reuses the confirmed link instead of re-deciding",
        reuse.outcome == evidence.LINK_ALREADY_LINKED
        and reuse.supplier_id == twin_a.id
        and len(evidence.supplier_ids_for_occurrence(s, occurrence_id=who_twin.id)) == 1,
        detail=reuse.explanation,
    )
    check(
        "[18] the confirmed link is what invoice matching would read",
        evidence.supplier_ids_for_occurrence(s, occurrence_id=who_twin.id) == [twin_a.id],
    )


if __name__ == "__main__":
    sys.exit(main())
