"""Purchasing persistence repository (TASK_PURCHASING_004).

This is the ONLY supported way to write Purchasing data. It is the layer
that enforces the historical-integrity invariants the Domain documents
(Purchasing/BusinessRules.md, Rules 2, 11, 23, 36; Purchasing/DataDictionary.md,
"Attribute Principles") wherever a single-table CheckConstraint cannot
express them:

- No function here updates a `PurchaseDocument`'s or `PurchaseLine`'s
  source-fact columns once inserted (only `PurchaseDocument.status`, a
  business-processing flag, not a source fact, is ever updated in place).
- No function here updates a `ReceivingLine` once inserted. A REJECT/RETURN
  decision never rewrites it — it creates an `ExpectedSupplierCredit`
  instead (Rule 36, "Rejection Preserves Historical Reality").
- A `SupplierProduct` correction (`update_supplier_product_classification`)
  updates only that row — it never touches a `PurchaseLine` already
  recorded under the prior classification, because
  `PurchaseLine.economic_classification` is captured as its own snapshot at
  insert time, not looked up live from `SupplierProduct` (see
  `record_purchase_document` below).
- `set_configured_expectation` never edits an existing row's
  `acceptable_configurations` — it inserts a new ACTIVE row and marks the
  prior one SUPERSEDED, preserving the approval history (Rule 23).

Derived values (Effective Product Cost, allocation shares, category totals,
Reconciliation Outcome, Expected Supplier Credit's Recognized/Outstanding
Amount) are computed on demand by functions in this module or in
`reconciliation.py` — none of them is a column this module writes to.

Ownership note (Align legacy Invoice Intake with Purchased): `PurchaseDocument`
and `PurchaseLine` are the Purchase Fact — capture + normalize + publish —
that `01 Domains/Shared Domains/Purchased/README.md` (a Shared Domain) now
canonically owns; this module remains their only writer, unchanged. Restaurant/
Purchasing (`01 Domains/Business Domain/Restaurant/Purchasing/`) no longer
needs to be invoked to create one — it consumes this output for its own,
still Purchasing-owned concerns (Purchase Order, Configured Expectation,
Physical Receiving, Reconciliation, Alerts, Expected Supplier Credit — all
still implemented in this same module, unchanged). See "Purchased output"
below for the read-side functions Purchased's functional model (NORMALIZED/
HUMAN, non-goods cost allocation) adds on top of this unchanged write path.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from .reconciliation import ReconciliationInput, compute_reconciliation_outcome, describe_outcome

UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Supplier / Supplier Product
# ---------------------------------------------------------------------------


def get_or_create_supplier(session: Session, restaurant_id: int, name: str) -> m.Supplier:
    existing = session.scalars(
        select(m.Supplier).where(m.Supplier.restaurant_id == restaurant_id, m.Supplier.name == name)
    ).first()
    if existing is not None:
        return existing

    # A `name` that is a known ALIAS of an already-canonical Supplier
    # ("Purchased Supplier Training Phase 2", §9: reuse the alias
    # mechanism -- "NON creare un secondo Supplier duplicato se
    # evitabile") resolves to that same Supplier, never a new duplicate.
    alias_match = session.scalars(
        select(m.Supplier)
        .join(m.SupplierAlias, m.SupplierAlias.supplier_id == m.Supplier.id)
        .where(m.Supplier.restaurant_id == restaurant_id, m.SupplierAlias.alias_name == name)
    ).first()
    if alias_match is not None:
        return alias_match

    supplier = m.Supplier(restaurant_id=restaurant_id, name=name, status="ACTIVE")
    session.add(supplier)
    session.flush()
    return supplier


def add_supplier_alias(session: Session, supplier_id: int, alias_name: str, source: str | None = None) -> m.SupplierAlias:
    """Records `alias_name` as a known historical/source name for this
    Supplier (Task requirement 9: "canonical supplier + known source
    aliases"). Idempotent — returns the existing row unchanged if this
    exact (supplier_id, alias_name) pair is already on file, never a
    duplicate alias row."""

    existing = session.scalars(
        select(m.SupplierAlias).where(
            m.SupplierAlias.supplier_id == supplier_id, m.SupplierAlias.alias_name == alias_name
        )
    ).first()
    if existing is not None:
        return existing
    alias = m.SupplierAlias(supplier_id=supplier_id, alias_name=alias_name, source=source)
    session.add(alias)
    session.flush()
    return alias


def list_supplier_aliases(session: Session, supplier_id: int) -> list[m.SupplierAlias]:
    return list(
        session.scalars(
            select(m.SupplierAlias).where(m.SupplierAlias.supplier_id == supplier_id).order_by(m.SupplierAlias.id)
        ).all()
    )


def rename_supplier_canonical(
    session: Session, supplier_id: int, new_name: str, *, source: str | None = None
) -> m.Supplier:
    """Task requirement 8/10 ("Correggi il Supplier canonico esistente...
    NON cancellare il vecchio valore... mantieni la referential
    integrity"). Renames `Supplier.name` IN PLACE — same `id`, so every
    existing `PurchaseDocument.supplier_id` foreign key stays valid without
    touching a single `PurchaseDocument`/`PurchaseLine` row, and no amount
    or FK ever changes — and records the OLD name as a `SupplierAlias`
    before overwriting it, so `get_or_create_supplier()` still resolves the
    old spelling to this exact same Supplier afterward. Idempotent:
    renaming to the name the Supplier already has is a no-op (the old name
    is only ever recorded as an alias when it genuinely differs from the
    new one), so this is safe to call more than once."""

    supplier = session.get(m.Supplier, supplier_id)
    if supplier is None:
        raise ValueError(f"No Supplier with id={supplier_id!r}")
    old_name = supplier.name
    if old_name == new_name:
        return supplier
    add_supplier_alias(session, supplier_id, old_name, source=source or "previous canonical name")
    supplier.name = new_name
    session.flush()
    return supplier


def get_or_create_supplier_product(
    session: Session,
    supplier_id: int,
    supplier_code: str | None,
    supplier_name: str | None = None,
    packaging: str | None = None,
) -> tuple[m.SupplierProduct, bool]:
    """Implements "Supplier Product memory" (Purchasing/EntityDefinitions.md,
    "Supplier Product"): a known (Supplier, Supplier Item Code) pair reuses
    the existing row and its confirmed classification/mapping; a new pair
    creates a candidate, unclassified until a human confirms it. Returns
    `(supplier_product, created)`.
    """

    if supplier_code is not None:
        existing = session.scalars(
            select(m.SupplierProduct).where(
                m.SupplierProduct.supplier_id == supplier_id,
                m.SupplierProduct.supplier_code == supplier_code,
            )
        ).first()
        if existing is not None:
            return existing, False

    candidate = m.SupplierProduct(
        supplier_id=supplier_id,
        supplier_code=supplier_code,
        supplier_name=supplier_name,
        packaging=packaging,
        economic_classification=None,
        ingredient_id=None,
    )
    session.add(candidate)
    session.flush()
    return candidate, True


def update_supplier_product_classification(
    session: Session,
    supplier_product_id: int,
    economic_classification: str | None = None,
    ingredient_id: int | None = None,
) -> m.SupplierProduct:
    """A human-confirmed correction to Supplier Product memory. Updates
    memory going forward only — see the module docstring. Every
    `PurchaseLine.economic_classification` already recorded under the prior
    value is untouched."""

    supplier_product = session.get(m.SupplierProduct, supplier_product_id)
    if supplier_product is None:
        raise ValueError(f"Unknown SupplierProduct id={supplier_product_id}")
    if economic_classification is not None:
        supplier_product.economic_classification = economic_classification
    if ingredient_id is not None:
        supplier_product.ingredient_id = ingredient_id
    session.flush()
    return supplier_product


# ---------------------------------------------------------------------------
# Purchase Order / Purchase Order Line (minimal — see EntityDefinitions.md)
# ---------------------------------------------------------------------------


def create_purchase_order(
    session: Session,
    supplier_id: int,
    lines: list[dict[str, Any]],
    order_date: datetime | None = None,
) -> m.PurchaseOrder:
    order = m.PurchaseOrder(supplier_id=supplier_id, order_date=order_date, status="OPEN")
    session.add(order)
    session.flush()
    for line in lines:
        session.add(
            m.PurchaseOrderLine(
                purchase_order_id=order.id,
                supplier_product_id=line.get("supplier_product_id"),
                item_description=line.get("item_description"),
                quantity=Decimal(str(line["quantity"])),
            )
        )
    session.flush()
    return order


# ---------------------------------------------------------------------------
# Purchase Document / Purchase Line
# ---------------------------------------------------------------------------


def record_purchase_document(
    session: Session,
    supplier_id: int,
    header: dict[str, Any],
    lines: list[dict[str, Any]],
    purchase_order_id: int | None = None,
) -> m.PurchaseDocument:
    """Inserts one immutable Purchase Document plus its Purchase Lines
    (Rule 1, Rule 2). `header` keys map 1:1 to `PurchaseDocument` columns
    (Purchasing/DataDictionary.md); absent keys stay Unknown (NULL), never
    defaulted (Purchasing/EntityDefinitions.md, "Purchase Document").

    Each PRODUCT line dict may include `supplier_item_code` (resolved/
    created via `get_or_create_supplier_product`) and an explicit
    `economic_classification` override; if omitted, the line inherits the
    Supplier Product's current confirmed classification as its OWN snapshot
    at insert time (Purchasing/DataDictionary.md: EconomicClassification "a
    persisted fact, not a derived value"). An unresolved/unclassified
    PRODUCT line generates a Validation Log entry rather than a guess
    (Rule 13).
    """

    document = m.PurchaseDocument(
        supplier_id=supplier_id,
        purchase_order_id=purchase_order_id,
        document_number=header.get("document_number"),
        document_type=header.get("document_type", "Invoice"),
        issue_date=header.get("issue_date"),
        delivery_date=header.get("delivery_date"),
        destination_location=header.get("destination_location"),
        customer_account_reference=header.get("customer_account_reference"),
        acquisition_method=header.get("acquisition_method"),
        currency=header.get("currency"),
        total_amount_minor=header.get("total_amount_minor"),
        payment_terms=header.get("payment_terms"),
        status=header.get("status", "RECORDED"),
        source_reference=header.get("source_reference"),
        source_provenance=header.get("source_provenance"),
    )
    session.add(document)
    session.flush()

    for line in lines:
        line_type = line["line_type"]
        supplier_product_id = None
        economic_classification = None

        if line_type == "PRODUCT":
            if line.get("supplier_product_id") is not None:
                supplier_product_id = line["supplier_product_id"]
            elif line.get("supplier_item_code") is not None:
                supplier_product, created = get_or_create_supplier_product(
                    session,
                    supplier_id=supplier_id,
                    supplier_code=line.get("supplier_item_code"),
                    supplier_name=line.get("raw_description"),
                    packaging=line.get("pack_size"),
                )
                supplier_product_id = supplier_product.id
                if created or supplier_product.economic_classification is None:
                    add_validation_log_entry(
                        session,
                        purchase_document_id=document.id,
                        severity="WARNING",
                        message=(
                            f"Unknown or unclassified Supplier Product "
                            f"(supplier_id={supplier_id}, code={line.get('supplier_item_code')!r})"
                        ),
                        suggested_action="Confirm merchandise/economic classification and, if applicable, Ingredient mapping.",
                    )

            economic_classification = line.get("economic_classification")
            if economic_classification is None and supplier_product_id is not None:
                supplier_product = session.get(m.SupplierProduct, supplier_product_id)
                if supplier_product is not None:
                    economic_classification = supplier_product.economic_classification

        purchase_line = m.PurchaseLine(
            purchase_document_id=document.id,
            line_type=line_type,
            source_line_number=line.get("source_line_number"),
            raw_description=line["raw_description"],
            source_amount_minor=line.get("source_amount_minor"),
            supplier_product_id=supplier_product_id,
            supplier_item_code=line.get("supplier_item_code"),
            supplier_category_code=line.get("supplier_category_code"),
            source_section=line.get("source_section"),
            manufacturer_code=line.get("manufacturer_code"),
            brand=line.get("brand"),
            quantity=_decimal_or_none(line.get("quantity")),
            purchase_unit=line.get("purchase_unit"),
            pack_count=line.get("pack_count"),
            pack_size=line.get("pack_size"),
            product_variant=line.get("product_variant"),
            grade=line.get("grade"),
            unit_price_minor=line.get("unit_price_minor"),
            economic_classification=economic_classification,
        )
        session.add(purchase_line)

    session.flush()
    return document


def _decimal_or_none(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


# ---------------------------------------------------------------------------
# Configured Expectation / Previous Purchase / Configuration deviation Alert
# ---------------------------------------------------------------------------

_CONFIGURATION_FIELDS = ("pack_count", "pack_size", "purchase_unit", "brand", "product_variant", "grade")


def _configuration_of(line: m.PurchaseLine) -> dict[str, Any]:
    return {field: getattr(line, field) for field in _CONFIGURATION_FIELDS}


def get_active_configured_expectation(session: Session, supplier_product_id: int) -> m.ConfiguredExpectation | None:
    return session.scalars(
        select(m.ConfiguredExpectation).where(
            m.ConfiguredExpectation.supplier_product_id == supplier_product_id,
            m.ConfiguredExpectation.status == "ACTIVE",
        )
    ).first()


def set_configured_expectation(
    session: Session,
    supplier_product_id: int,
    acceptable_configurations: list[dict[str, Any]],
    approved_by_employee_id: int | None = None,
) -> m.ConfiguredExpectation:
    """Rule 23: changes only prospectively. Never edits a prior row; marks
    it SUPERSEDED and inserts a new ACTIVE one."""

    previous = get_active_configured_expectation(session, supplier_product_id)
    if previous is not None:
        previous.status = "SUPERSEDED"

    expectation = m.ConfiguredExpectation(
        supplier_product_id=supplier_product_id,
        acceptable_configurations=acceptable_configurations,
        status="ACTIVE",
        approved_by_employee_id=approved_by_employee_id,
    )
    session.add(expectation)
    session.flush()
    return expectation


def get_previous_purchase_line(
    session: Session, supplier_id: int, supplier_product_id: int, exclude_purchase_line_id: int | None = None
) -> m.PurchaseLine | None:
    """Priority-2 fallback (Rule 20): the most recent prior PRODUCT Purchase
    Line for the same Supplier + Supplier Product, purely observational."""

    query = (
        select(m.PurchaseLine)
        .join(m.PurchaseDocument, m.PurchaseLine.purchase_document_id == m.PurchaseDocument.id)
        .where(
            m.PurchaseDocument.supplier_id == supplier_id,
            m.PurchaseLine.supplier_product_id == supplier_product_id,
            m.PurchaseLine.line_type == "PRODUCT",
        )
        .order_by(m.PurchaseLine.id.desc())
    )
    if exclude_purchase_line_id is not None:
        query = query.where(m.PurchaseLine.id != exclude_purchase_line_id)
    return session.scalars(query).first()


def detect_configuration_deviation(session: Session, purchase_line_id: int) -> m.PurchasingAlert | None:
    """Rule 20: compares the line's observed configuration against the
    Configured Expectation (priority 1) or the previous purchase (priority
    2, fallback). Raises a CONFIGURATION_DEVIATION Alert when neither
    matches; returns None for a known, coherent line (no Alert — Design
    Principles, "known and coherent purchases process automatically")."""

    line = session.get(m.PurchaseLine, purchase_line_id)
    if line is None or line.line_type != "PRODUCT" or line.supplier_product_id is None:
        return None

    observed = _configuration_of(line)
    expectation = get_active_configured_expectation(session, line.supplier_product_id)

    if expectation is not None:
        basis = "CONFIGURED_EXPECTATION"
        acceptable = expectation.acceptable_configurations
        matches = any(_configuration_matches(observed, accepted) for accepted in acceptable)
        expected_configuration: dict[str, Any] | list[dict[str, Any]] = acceptable
    else:
        previous_line = get_previous_purchase_line(
            session, line.purchase_document.supplier_id, line.supplier_product_id, exclude_purchase_line_id=line.id
        )
        if previous_line is None:
            return None  # nothing to compare against yet
        basis = "PREVIOUS_PURCHASE"
        previous_configuration = _configuration_of(previous_line)
        matches = _configuration_matches(observed, previous_configuration)
        expected_configuration = previous_configuration

    if matches:
        return None

    alert = m.PurchasingAlert(
        trigger="CONFIGURATION_DEVIATION",
        purchase_document_id=line.purchase_document_id,
        purchase_line_id=line.id,
        supplier_product_id=line.supplier_product_id,
        comparison_basis=basis,
        expected_configuration=expected_configuration,
        observed_configuration=observed,
        status="OPEN",
    )
    session.add(alert)
    session.flush()
    return alert


def _configuration_matches(observed: dict[str, Any], reference: dict[str, Any]) -> bool:
    for field in _CONFIGURATION_FIELDS:
        ref_value = reference.get(field)
        if ref_value is None:
            continue  # an un-set reference field never causes a mismatch
        if observed.get(field) != ref_value:
            return False
    return True


def decide_configuration_alert(
    session: Session,
    alert_id: int,
    decision: str,
    employee_id: int | None = None,
    new_acceptable_configuration: dict[str, Any] | None = None,
) -> m.PurchasingAlert:
    """Rule 23/24. `decision` in {ACCEPT_THIS_PURCHASE_ONLY,
    ACCEPT_AS_ALTERNATIVE, CHANGE_EXPECTATION, MODULE_CAPABILITY_GAP}. The
    Configured Expectation is updated prospectively for the ADD/CHANGE
    cases only — ACCEPT_THIS_PURCHASE_ONLY and MODULE_CAPABILITY_GAP leave
    it untouched (worked example, Rule 23)."""

    valid_decisions = {
        "ACCEPT_THIS_PURCHASE_ONLY",
        "ACCEPT_AS_ALTERNATIVE",
        "CHANGE_EXPECTATION",
        "MODULE_CAPABILITY_GAP",
    }
    if decision not in valid_decisions:
        raise ValueError(f"Invalid CONFIGURATION_DEVIATION decision: {decision!r}")

    alert = session.get(m.PurchasingAlert, alert_id)
    if alert is None or alert.trigger != "CONFIGURATION_DEVIATION":
        raise ValueError(f"Alert id={alert_id} is not an open CONFIGURATION_DEVIATION alert")

    if decision in ("ACCEPT_AS_ALTERNATIVE", "CHANGE_EXPECTATION") and alert.supplier_product_id is not None:
        observed = alert.observed_configuration or {}
        if decision == "ACCEPT_AS_ALTERNATIVE":
            expectation = get_active_configured_expectation(session, alert.supplier_product_id)
            existing = list(expectation.acceptable_configurations) if expectation is not None else []
            existing.append(new_acceptable_configuration or observed)
            set_configured_expectation(session, alert.supplier_product_id, existing, employee_id)
        else:  # CHANGE_EXPECTATION
            set_configured_expectation(
                session, alert.supplier_product_id, [new_acceptable_configuration or observed], employee_id
            )

    alert.human_decision = decision
    alert.decided_by_employee_id = employee_id
    alert.decided_at = _now()
    alert.status = "CLOSED"  # the decision itself is the required response (Rule 22)
    session.flush()
    return alert


# ---------------------------------------------------------------------------
# Physical Receiving
# ---------------------------------------------------------------------------


def start_receiving(
    session: Session,
    supplier_id: int,
    receiving_timestamp: datetime,
    capture_method: str,
    purchase_order_id: int | None = None,
    purchase_document_id: int | None = None,
    location_id: int | None = None,
    receiving_user_employee_id: int | None = None,
    source_provenance: str | None = None,
) -> m.ReceivingRecord:
    record = m.ReceivingRecord(
        supplier_id=supplier_id,
        purchase_order_id=purchase_order_id,
        purchase_document_id=purchase_document_id,
        location_id=location_id,
        receiving_user_employee_id=receiving_user_employee_id,
        receiving_timestamp=receiving_timestamp,
        capture_method=capture_method,
        source_provenance=source_provenance,
        status="IN_PROGRESS",
    )
    session.add(record)
    session.flush()
    return record


def add_receiving_line(session: Session, receiving_record_id: int, line: dict[str, Any]) -> m.ReceivingLine:
    """A Receiving Line with no `purchase_order_line_id` is an
    Extra/Unexpected Item by definition (`ReceivingLine`'s CheckConstraint
    then requires `photo_evidence`) — never a separate flag/entity."""

    receiving_line = m.ReceivingLine(
        receiving_record_id=receiving_record_id,
        purchase_order_line_id=line.get("purchase_order_line_id"),
        purchase_line_id=line.get("purchase_line_id"),
        supplier_product_id=line.get("supplier_product_id"),
        raw_description=line.get("raw_description"),
        observed_quantity=Decimal(str(line["observed_quantity"])),
        observed_pack_count=line.get("observed_pack_count"),
        observed_pack_size=line.get("observed_pack_size"),
        observed_unit=line.get("observed_unit"),
        observed_brand=line.get("observed_brand"),
        observed_variant=line.get("observed_variant"),
        observed_grade=line.get("observed_grade"),
        damaged_quantity=_decimal_or_none(line.get("damaged_quantity")),
        photo_evidence=line.get("photo_evidence"),
        capture_method=line.get("capture_method"),
    )
    session.add(receiving_line)
    session.flush()
    return receiving_line


def complete_receiving(session: Session, receiving_record_id: int) -> m.ReceivingRecord:
    """Rule 32: completion never waits for Alert resolution — this function
    only flips `status`, regardless of any OPEN `PurchasingAlert` linked to
    this record's lines."""

    record = session.get(m.ReceivingRecord, receiving_record_id)
    if record is None:
        raise ValueError(f"Unknown ReceivingRecord id={receiving_record_id}")
    record.status = "COMPLETED"
    session.flush()
    return record


def _effective_invoice_quantity(session: Session, purchase_line: m.PurchaseLine | None) -> Decimal | None:
    """The Human-Review-effective invoice quantity for one Purchase Line
    (Task "Make Effective Purchased View canonical for all consumers" —
    Restaurant/Purchasing's own three-way reconciliation must not compare a
    physical receipt against a `quantity` a reviewer has since corrected).
    Resolves through the same `resolve_latest_field_corrections()`/
    `effective_field_value()` pair `get_purchased_lines_with_allocation()`
    uses — no second merge implementation. Falls back to the raw,
    immutable column when there is no override, or when a corrected value
    cannot be parsed as a number."""

    if purchase_line is None:
        return None
    latest_corrections = resolve_latest_field_corrections(session, purchase_line.purchase_document_id)
    effective = effective_field_value(latest_corrections, purchase_line.id, "quantity", purchase_line.quantity)
    if not isinstance(effective, str):
        return effective
    try:
        return Decimal(effective.strip())
    except InvalidOperation:
        return purchase_line.quantity


def reconcile_receiving_line(session: Session, receiving_line_id: int) -> list[str]:
    """Rule 26/33 — derived on demand, never persisted (see reconciliation.py)."""

    receiving_line = session.get(m.ReceivingLine, receiving_line_id)
    if receiving_line is None:
        raise ValueError(f"Unknown ReceivingLine id={receiving_line_id}")

    order_line = (
        session.get(m.PurchaseOrderLine, receiving_line.purchase_order_line_id)
        if receiving_line.purchase_order_line_id
        else None
    )
    purchase_line = (
        session.get(m.PurchaseLine, receiving_line.purchase_line_id) if receiving_line.purchase_line_id else None
    )

    identity_substituted_vs_order = bool(
        order_line
        and order_line.supplier_product_id
        and receiving_line.supplier_product_id
        and order_line.supplier_product_id != receiving_line.supplier_product_id
    )
    identity_substituted_vs_invoice = bool(
        purchase_line
        and purchase_line.supplier_product_id
        and receiving_line.supplier_product_id
        and purchase_line.supplier_product_id != receiving_line.supplier_product_id
    )

    inputs = ReconciliationInput(
        order_quantity=order_line.quantity if order_line else None,
        invoice_quantity=_effective_invoice_quantity(session, purchase_line),
        received_quantity=receiving_line.observed_quantity,
        damaged_quantity=receiving_line.damaged_quantity,
        is_extra_item=receiving_line.purchase_order_line_id is None,
        identity_substituted_vs_order=identity_substituted_vs_order,
        identity_substituted_vs_invoice=identity_substituted_vs_invoice,
    )
    return compute_reconciliation_outcome(inputs)


def raise_receiving_discrepancy_alert(
    session: Session,
    receiving_line_id: int,
    outcomes: list[str],
    responsible_user_employee_id: int | None = None,
) -> m.PurchasingAlert | None:
    """Returns None for a clean MATCH (no Alert needed); otherwise raises a
    RECEIVING_DISCREPANCY Alert (Rule 29, 30, 34)."""

    if outcomes == ["MATCH"]:
        return None

    receiving_line = session.get(m.ReceivingLine, receiving_line_id)
    if receiving_line is None:
        raise ValueError(f"Unknown ReceivingLine id={receiving_line_id}")

    order_line = (
        session.get(m.PurchaseOrderLine, receiving_line.purchase_order_line_id)
        if receiving_line.purchase_order_line_id
        else None
    )
    purchase_line = (
        session.get(m.PurchaseLine, receiving_line.purchase_line_id) if receiving_line.purchase_line_id else None
    )
    inputs = ReconciliationInput(
        order_quantity=order_line.quantity if order_line else None,
        invoice_quantity=_effective_invoice_quantity(session, purchase_line),
        received_quantity=receiving_line.observed_quantity,
        damaged_quantity=receiving_line.damaged_quantity,
    )

    alert = m.PurchasingAlert(
        trigger="RECEIVING_DISCREPANCY",
        purchase_document_id=purchase_line.purchase_document_id if purchase_line else None,
        purchase_line_id=receiving_line.purchase_line_id,
        supplier_product_id=receiving_line.supplier_product_id,
        purchase_order_line_id=receiving_line.purchase_order_line_id,
        receiving_record_id=receiving_line.receiving_record_id,
        receiving_line_id=receiving_line.id,
        reconciliation_context=describe_outcome(outcomes, inputs),
        responsible_user_employee_id=responsible_user_employee_id,
        status="OPEN",
    )
    session.add(alert)
    session.flush()
    return alert


def decide_receiving_alert(
    session: Session,
    alert_id: int,
    decision: str,
    employee_id: int | None = None,
    rejected_quantity: Decimal | None = None,
    expected_amount_minor: int | None = None,
) -> tuple[m.PurchasingAlert, m.ExpectedSupplierCredit | None]:
    """Rule 35/36. `decision` in {ACCEPT, REJECT_RETURN}. REJECT_RETURN on
    already-invoiced merchandise (the Alert has a `purchase_line_id`)
    creates an Expected Supplier Credit (Rule 37); the Receiving Line itself
    is never rewritten (Rule 36) — this function updates only the Alert and,
    when applicable, inserts a new ExpectedSupplierCredit row."""

    if decision not in ("ACCEPT", "REJECT_RETURN"):
        raise ValueError(f"Invalid RECEIVING_DISCREPANCY decision: {decision!r}")

    alert = session.get(m.PurchasingAlert, alert_id)
    if alert is None or alert.trigger != "RECEIVING_DISCREPANCY":
        raise ValueError(f"Alert id={alert_id} is not a RECEIVING_DISCREPANCY alert")

    alert.human_decision = decision
    alert.decided_by_employee_id = employee_id
    alert.decided_at = _now()

    credit: m.ExpectedSupplierCredit | None = None
    if decision == "REJECT_RETURN" and alert.purchase_line_id is not None:
        if rejected_quantity is None or expected_amount_minor is None:
            raise ValueError("REJECT_RETURN on already-invoiced merchandise requires rejected_quantity and expected_amount_minor")
        credit = create_expected_supplier_credit(
            session,
            alert_id=alert.id,
            purchase_document_id=alert.purchase_document_id,
            purchase_line_id=alert.purchase_line_id,
            rejected_quantity=rejected_quantity,
            expected_amount_minor=expected_amount_minor,
        )
        # The Alert stays open in spirit until the credit resolves, but its
        # own required response (the decision) is complete — closure of the
        # underlying supplier issue is tracked on the credit (Rule 40), not
        # by re-opening/holding this Alert row indefinitely.
        alert.status = "DECIDED"
    else:
        alert.status = "CLOSED"

    session.flush()
    return alert, credit


# ---------------------------------------------------------------------------
# Expected Supplier Credit
# ---------------------------------------------------------------------------


def create_expected_supplier_credit(
    session: Session,
    alert_id: int,
    purchase_document_id: int,
    purchase_line_id: int,
    rejected_quantity: Decimal,
    expected_amount_minor: int,
) -> m.ExpectedSupplierCredit:
    credit = m.ExpectedSupplierCredit(
        alert_id=alert_id,
        purchase_document_id=purchase_document_id,
        purchase_line_id=purchase_line_id,
        rejected_quantity=rejected_quantity,
        expected_amount_minor=expected_amount_minor,
        status="OPEN",
    )
    session.add(credit)
    session.flush()
    return credit


def get_expected_supplier_credit_amounts(session: Session, expected_supplier_credit_id: int) -> tuple[int, int]:
    """Rule 38 — derived, never persisted. Returns
    `(recognized_amount_minor, outstanding_amount_minor)`."""

    credit = session.get(m.ExpectedSupplierCredit, expected_supplier_credit_id)
    if credit is None:
        raise ValueError(f"Unknown ExpectedSupplierCredit id={expected_supplier_credit_id}")
    # Queried directly (never via the `credit_references` relationship
    # collection) so a reference inserted earlier in the same still-open
    # Session is always picked up — the collection can otherwise stay
    # stale once loaded, since this module's Sessions use
    # `expire_on_commit=False` (`database.py`).
    recognized = session.scalar(
        select(func.coalesce(func.sum(m.SupplierCreditReference.applied_amount_minor), 0)).where(
            m.SupplierCreditReference.expected_supplier_credit_id == credit.id
        )
    )
    outstanding = credit.expected_amount_minor - recognized
    return recognized, outstanding


def link_supplier_credit(
    session: Session,
    expected_supplier_credit_id: int,
    applied_amount_minor: int,
    purchase_document_id: int | None = None,
    purchase_line_id: int | None = None,
    note: str | None = None,
) -> m.ExpectedSupplierCredit:
    """Rule 38/39. Records one recognized Supplier credit fact and
    recomputes `status` (never storing Recognized/Outstanding Amount
    themselves) — OPEN while nothing is recognized yet, PARTIALLY_RESOLVED
    while `0 < recognized < expected`, RESOLVED once `recognized >=
    expected`. No arbitrary expiration is ever applied (Rule 40)."""

    credit = session.get(m.ExpectedSupplierCredit, expected_supplier_credit_id)
    if credit is None:
        raise ValueError(f"Unknown ExpectedSupplierCredit id={expected_supplier_credit_id}")

    session.add(
        m.SupplierCreditReference(
            expected_supplier_credit_id=credit.id,
            purchase_document_id=purchase_document_id,
            purchase_line_id=purchase_line_id,
            applied_amount_minor=applied_amount_minor,
            note=note,
        )
    )
    session.flush()

    recognized, outstanding = get_expected_supplier_credit_amounts(session, credit.id)
    if outstanding <= 0:
        credit.status = "RESOLVED"
        credit.resolved_at = _now()
    elif recognized > 0:
        credit.status = "PARTIALLY_RESOLVED"
    else:
        credit.status = "OPEN"

    session.flush()
    return credit


# ---------------------------------------------------------------------------
# Alert acknowledgement (shared by both triggers)
# ---------------------------------------------------------------------------


def acknowledge_alert(session: Session, alert_id: int, employee_id: int | None = None) -> m.PurchasingAlert:
    alert = session.get(m.PurchasingAlert, alert_id)
    if alert is None:
        raise ValueError(f"Unknown PurchasingAlert id={alert_id}")
    if alert.status == "OPEN":
        alert.status = "ACKNOWLEDGED"
    if employee_id is not None:
        alert.responsible_user_employee_id = employee_id
    session.flush()
    return alert


# ---------------------------------------------------------------------------
# Purchased output (Align legacy Invoice Intake with Purchased)
#
# `PurchaseDocument`/`PurchaseLine` above are the Purchase Fact Purchased
# (`01 Domains/Shared Domains/Purchased/README.md`) owns: capture + normalize
# + publish. These three functions expose that fact the way Purchased's
# README requires -- non-goods cost allocated onto goods lines, and a
# NORMALIZED/HUMAN functional state -- without adding any new column: the
# functional state is derived from the existing `PurchasingValidationLogEntry`
# mechanism (an OPEN WARNING/ERROR entry against a Document/Line IS that
# Document/Line's HUMAN state), and the allocation is computed on demand,
# consistent with this schema's existing "Persist Facts -- Derive
# Calculations" convention (Effective Product Cost, Reconciliation Outcome).
# Restaurant/Purchasing (and any other Business Domain) consumes this output;
# it does not own it.
# ---------------------------------------------------------------------------


def find_purchase_documents_by_number(
    session: Session, supplier_id: int, document_number: str
) -> list[m.PurchaseDocument]:
    """Every existing Purchase Document sharing the same (Supplier, Document
    Number) identity -- the identity Purchased's duplicate-handling rule
    compares against (Purchased/README.md, "Duplicate handling"). Returns an
    empty list for a blank `document_number` (too weak an identity to compare
    on)."""

    if not document_number:
        return []
    return list(
        session.scalars(
            select(m.PurchaseDocument).where(
                m.PurchaseDocument.supplier_id == supplier_id,
                m.PurchaseDocument.document_number == document_number,
            )
        )
    )


def get_document_functional_status(session: Session, purchase_document_id: int) -> str:
    """NORMALIZED / HUMAN (Purchased/README.md, "NORMALIZED / HUMAN") for one
    Purchase Document -- derived, never stored. HUMAN whenever an OPEN
    WARNING/ERROR `PurchasingValidationLogEntry` references this document;
    NORMALIZED otherwise. An OPEN INFORMATION-severity entry (e.g. "this
    document is a correction of #123") never forces HUMAN by itself."""

    open_issues = session.scalar(
        select(func.count(m.PurchasingValidationLogEntry.id)).where(
            m.PurchasingValidationLogEntry.purchase_document_id == purchase_document_id,
            m.PurchasingValidationLogEntry.status == "OPEN",
            m.PurchasingValidationLogEntry.severity.in_(("WARNING", "ERROR")),
        )
    )
    return "HUMAN" if open_issues else "NORMALIZED"


def get_line_functional_status(session: Session, purchase_line_id: int) -> str:
    """Same rule as `get_document_functional_status`, scoped to one Purchase
    Line (Purchased Line's own NORMALIZED/HUMAN state, Purchased/README.md,
    "Purchased Line -- minimum conceptual data")."""

    open_issues = session.scalar(
        select(func.count(m.PurchasingValidationLogEntry.id)).where(
            m.PurchasingValidationLogEntry.purchase_line_id == purchase_line_id,
            m.PurchasingValidationLogEntry.status == "OPEN",
            m.PurchasingValidationLogEntry.severity.in_(("WARNING", "ERROR")),
        )
    )
    return "HUMAN" if open_issues else "NORMALIZED"


def get_purchased_lines_with_allocation(session: Session, purchase_document_id: int) -> list[dict[str, Any]]:
    """Purchased's canonical output view of one Purchase Document's PRODUCT
    (goods) lines (Purchased/README.md, "Non-goods cost allocation"):
    freight/delivery/fuel-surcharge/handling/tax-not-directly-attributable
    and similar non-goods amounts -- recorded here as SURCHARGE/DISCOUNT
    `PurchaseLine` rows, signed exactly as disclosed by the source -- are
    apportioned across the PRODUCT lines in proportion to each PRODUCT
    line's own EFFECTIVE amount, never persisted as their own standalone
    Purchased Line. The raw SURCHARGE/DISCOUNT rows are never deleted or
    hidden -- they remain in the database as source evidence (README: "the
    raw/source representation can continue to conserve them") -- this
    function only adds the allocated view on top.

    ("Make Effective Purchased View canonical for all consumers"): every
    amount this function allocates on is first passed through
    `effective_field_value()` against the latest `PurchasedFieldCorrection`
    for that line's `"line_amount"` field, if any -- a Human Review
    correction to a line's amount changes the allocation base and every
    downstream `allocated_amount_minor` this function returns, exactly like
    it already changes `human_review.effective_document_view()`'s own
    displayed `line_amount`. Both consumers resolve corrections through the
    same `resolve_latest_field_corrections()`/`effective_field_value()`
    pair below -- there is only one merge implementation. The immutable
    `source_amount_minor` column is still returned alongside, for callers
    that need the original, uncorrected source-evidence figure.

    When the document has no PRODUCT lines at all, no allocation base
    exists; each non-goods amount is left unallocated (`allocated_non_goods_minor`
    stays 0 for -- there being no PRODUCT line to attach it to), matching
    the README's own "an invoice with no goods lines at all" open edge case.
    """

    document = session.get(m.PurchaseDocument, purchase_document_id)
    if document is None:
        raise ValueError(f"Unknown PurchaseDocument id={purchase_document_id}")

    latest_corrections = resolve_latest_field_corrections(session, purchase_document_id)
    added_line_ids = human_added_line_ids(session, purchase_document_id)

    def _effective_amount_minor(line: "m.PurchaseLine") -> int | None:
        effective = effective_field_value(latest_corrections, line.id, "line_amount", line.source_amount_minor)
        # `effective_field_value()` returns either the untouched `original`
        # argument (already an int/None here -- no override exists) or a
        # human-typed correction string (an override exists) -- only the
        # latter needs parsing back into minor units.
        return _parse_money_minor_text(effective) if isinstance(effective, str) else effective

    # A manually-added line (Task "Close Purchased Human Review Reliability
    # Gaps" §3/§5) is a genuine PRODUCT/SURCHARGE/DISCOUNT `PurchaseLine`
    # row like any other -- `document.lines` already includes it, so it
    # participates in `product_lines`/`non_goods_total`/`goods_total` below
    # with no special-casing of the allocation formula itself (Task: "NON
    # duplicare formule"). `human_added` on the output row only flags it
    # for display/audit -- it changes no number.
    product_lines = sorted(
        (line for line in document.lines if line.line_type == "PRODUCT"), key=lambda line: line.id
    )
    non_goods_total = sum(
        (_effective_amount_minor(line) or 0) for line in document.lines if line.line_type in ("SURCHARGE", "DISCOUNT")
    )
    goods_total = sum((_effective_amount_minor(line) or 0) for line in product_lines)

    output: list[dict[str, Any]] = []
    allocated_so_far = 0
    for index, line in enumerate(product_lines):
        line_amount = _effective_amount_minor(line) or 0
        if goods_total > 0:
            if index == len(product_lines) - 1:
                # The last line absorbs any rounding remainder, so the sum of
                # allocated shares always reconciles exactly to non_goods_total.
                share = non_goods_total - allocated_so_far
            else:
                share = round(non_goods_total * line_amount / goods_total)
                allocated_so_far += share
        else:
            share = 0
        output.append(
            {
                "purchase_line_id": line.id,
                "raw_description": line.raw_description,
                "source_amount_minor": line.source_amount_minor,
                "effective_amount_minor": line_amount,
                "allocated_non_goods_minor": share,
                "allocated_amount_minor": line_amount + share,
                "functional_status": get_line_functional_status(session, line.id),
                "human_added": line.id in added_line_ids,
            }
        )
    return output


def _parse_money_minor_text(value: str | None) -> int | None:
    """Tolerant parse of a Human Review corrected money string (e.g.
    `"12.34"`, possibly with stray formatting a reviewer typed) into integer
    minor units -- mirrors `purchased_bridge._parse_money_minor()`'s own
    tolerance without this lower-layer module importing InvoiceIntake."""

    if value is None:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if cleaned in ("", "-", "."):
        return None
    try:
        return int((Decimal(cleaned) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None


# ---------------------------------------------------------------------------
# Add Missing Line (Task "Close Purchased Human Review Reliability Gaps",
# §3): the one way Purchased Human Review may add a Purchase Line the
# original OCR/parser extraction never created at all. ADDITIVE, never a
# rewrite -- see `models.PurchasedLineAddition`'s own docstring for why a
# genuine new `PurchaseLine` row plus a matching audit row (not a schema
# change to `purchase_lines` itself) is the mechanism.
# ---------------------------------------------------------------------------


def human_added_line_ids(session: Session, purchase_document_id: int) -> set[int]:
    """Every `PurchaseLine.id` on this document that was added via Human
    Review rather than the original extraction -- the one place every
    consumer (allocation, Effective Purchased View, the review UI) checks
    to tell an added line apart from source evidence."""

    return set(
        session.scalars(
            select(m.PurchasedLineAddition.purchase_line_id).where(
                m.PurchasedLineAddition.purchase_document_id == purchase_document_id
            )
        ).all()
    )


def list_line_additions(session: Session, purchase_document_id: int) -> list[m.PurchasedLineAddition]:
    """Full ADD_LINE audit history for one document, oldest first (Task §3:
    "Preserva audit: reviewer, timestamp, action = ADD_LINE")."""

    return list(
        session.scalars(
            select(m.PurchasedLineAddition)
            .where(m.PurchasedLineAddition.purchase_document_id == purchase_document_id)
            .order_by(m.PurchasedLineAddition.id)
        ).all()
    )


def add_manual_purchase_line(
    session: Session,
    purchase_document_id: int,
    *,
    added_by: str,
    line_type: str = "PRODUCT",
    raw_description: str,
    quantity: Decimal | None = None,
    purchase_unit: str | None = None,
    unit_price_minor: int | None = None,
    source_amount_minor: int | None = None,
) -> tuple[m.PurchaseLine, bool]:
    """Adds a Purchase Line the original OCR/parser extraction never
    created (Task §3) -- a brand-new, genuine `PurchaseLine` row (so it
    participates in `get_purchased_lines_with_allocation()`/the Effective
    Purchased View exactly like any other line, Task §4/§5) plus its own
    `PurchasedLineAddition` audit row. Never touches any EXISTING
    `PurchaseDocument`/`PurchaseLine` row -- purely additive, same
    discipline `record_field_correction` already follows for field-level
    corrections.

    Returns `(line, created)`. Idempotent re-submission guard (Task §9,
    test 15, "no duplicate lines on repeated submit"): a second call for
    the SAME document with the exact same `line_type` + `raw_description` +
    `source_amount_minor` as an already-HUMAN-ADDED line reuses that line
    instead of inserting a duplicate (e.g. a reviewer's browser
    double-submitting the same form) -- `created` is `False` in that case.
    An original (non-human-added) line with coincidentally identical values
    is never matched here: only rows already recorded in
    `purchased_line_additions` for this document are considered, so a
    genuinely blank source-evidence line whose text happens to match is
    never mistaken for a prior manual addition."""

    document = session.get(m.PurchaseDocument, purchase_document_id)
    if document is None:
        raise ValueError(f"Unknown PurchaseDocument id={purchase_document_id}")
    if line_type not in ("PRODUCT", "SURCHARGE", "DISCOUNT"):
        raise ValueError(f"Invalid line_type {line_type!r}; must be PRODUCT/SURCHARGE/DISCOUNT")
    if not raw_description or not raw_description.strip():
        raise ValueError("raw_description is required to add a Purchase Line")

    existing = session.scalars(
        select(m.PurchaseLine)
        .join(m.PurchasedLineAddition, m.PurchasedLineAddition.purchase_line_id == m.PurchaseLine.id)
        .where(
            m.PurchasedLineAddition.purchase_document_id == purchase_document_id,
            m.PurchaseLine.line_type == line_type,
            m.PurchaseLine.raw_description == raw_description,
            m.PurchaseLine.source_amount_minor == source_amount_minor,
        )
    ).first()
    if existing is not None:
        return existing, False

    line = m.PurchaseLine(
        purchase_document_id=purchase_document_id,
        line_type=line_type,
        raw_description=raw_description,
        source_amount_minor=source_amount_minor,
        quantity=quantity if line_type == "PRODUCT" else None,
        purchase_unit=purchase_unit if line_type == "PRODUCT" else None,
        unit_price_minor=unit_price_minor if line_type == "PRODUCT" else None,
    )
    session.add(line)
    session.flush()
    session.add(m.PurchasedLineAddition(purchase_document_id=purchase_document_id, purchase_line_id=line.id, added_by=added_by))
    session.flush()
    # This module's sessions use `expire_on_commit=False` (database.py) --
    # `document`'s own `.lines` collection, if already loaded earlier in
    # THIS session (e.g. a caller that read the document before adding a
    # line), would otherwise keep returning the pre-addition snapshot for
    # the rest of the session's lifetime, since `session.get()` returns the
    # identity-mapped instance rather than re-querying. Expiring just this
    # relationship (not the whole object) guarantees the next access -- by
    # this caller or another, e.g. `get_purchased_lines_with_allocation()`
    # re-fetching the same document later in a long-lived session -- sees
    # the newly added line, without forcing an unnecessary reload of every
    # other already-loaded attribute.
    session.expire(document, ["lines"])
    return line, True


# ---------------------------------------------------------------------------
# Validation Log
# ---------------------------------------------------------------------------


def add_validation_log_entry(
    session: Session,
    purchase_document_id: int,
    severity: str,
    message: str,
    purchase_line_id: int | None = None,
    suggested_action: str | None = None,
) -> m.PurchasingValidationLogEntry:
    entry = m.PurchasingValidationLogEntry(
        purchase_document_id=purchase_document_id,
        purchase_line_id=purchase_line_id,
        severity=severity,
        message=message,
        suggested_action=suggested_action,
        status="OPEN",
    )
    session.add(entry)
    session.flush()
    return entry


def close_validation_log_entry(
    session: Session, entry_id: int, *, human_decision: str, status: str = "CLOSED"
) -> m.PurchasingValidationLogEntry:
    """Moves one `PurchasingValidationLogEntry` OPEN -> `status` (Task
    "Purchased Human Review", requirement 7: HUMAN -> NORMALIZED once
    review resolves what made it HUMAN in the first place) — never touches
    `message`/`suggested_action` (models.py, "Rule 13"). This is what lets
    `get_document_functional_status()`/`get_line_functional_status()`
    naturally return NORMALIZED again once every OPEN WARNING/ERROR
    referencing a document (or its lines) has been closed — no third
    functional state is introduced anywhere by this."""

    if status not in ("APPROVED", "REJECTED", "CLOSED"):
        raise ValueError(f"Invalid resolution status {status!r}; must be APPROVED/REJECTED/CLOSED")
    entry = session.get(m.PurchasingValidationLogEntry, entry_id)
    if entry is None:
        raise ValueError(f"No PurchasingValidationLogEntry with id={entry_id!r}")
    entry.status = status
    entry.human_decision = human_decision
    entry.resolved_at = _now()
    session.flush()
    return entry


# ---------------------------------------------------------------------------
# Human Review (Task "Purchased Human Review + Supplier Format Training UI")
#
# `PurchasedFieldCorrection` (models.py) is purely additive — it NEVER
# overwrites a `PurchaseDocument`/`PurchaseLine` column. These functions are
# its only reader/writer; `03 Software/InvoiceIntake/human_review.py` is the
# orchestration layer on top (effective-value merging, re-validation,
# closing out Validation Log entries, Supplier+Format training
# observation) — kept in InvoiceIntake because it needs
# `purchased_bridge._validate_extracted_fields` (the SAME validation
# function used at initial save, reused rather than reimplemented — Task:
# "NON aggiungere nuove euristiche parser") and `supplier_format_training.py`.
# ---------------------------------------------------------------------------


def record_field_correction(
    session: Session,
    *,
    purchase_document_id: int,
    field_name: str,
    classification: str,
    reviewed_by: str,
    purchase_line_id: int | None = None,
    original_value: str | None = None,
    corrected_value: str | None = None,
) -> m.PurchasedFieldCorrection:
    if classification not in ("CORRECT", "INCORRECT", "UNREAD", "AMBIGUOUS"):
        raise ValueError(f"Invalid classification {classification!r}")
    if classification == "INCORRECT" and not (corrected_value and corrected_value.strip()):
        # "Close Purchased Human Review Reliability Gaps" §7, Field Review
        # Semantics: "INCORRECT -> richiede corrected value" -- unlike
        # AMBIGUOUS/UNREAD (which may legitimately stay unresolved when the
        # source is genuinely illegible), classifying a field INCORRECT
        # asserts a specific, known-better value exists; without one this
        # is a malformed review action, rejected outright rather than
        # silently accepted as a no-op.
        raise ValueError("classification='INCORRECT' requires a non-blank corrected_value")
    correction = m.PurchasedFieldCorrection(
        purchase_document_id=purchase_document_id,
        purchase_line_id=purchase_line_id,
        field_name=field_name,
        classification=classification,
        original_value=original_value,
        corrected_value=corrected_value,
        reviewed_by=reviewed_by,
    )
    session.add(correction)
    session.flush()
    return correction


def list_field_corrections(session: Session, purchase_document_id: int) -> list[m.PurchasedFieldCorrection]:
    """Full history, oldest first — the audit trail (Task requirement 17).
    Callers wanting only the CURRENT/effective value per field should take
    the LAST row per (purchase_line_id, field_name) — see
    `latest_field_corrections()`/`resolve_latest_field_corrections()`
    below, the one shared reduction every consumer of Purchased uses."""

    return list(
        session.scalars(
            select(m.PurchasedFieldCorrection)
            .where(m.PurchasedFieldCorrection.purchase_document_id == purchase_document_id)
            .order_by(m.PurchasedFieldCorrection.id)
        ).all()
    )


# ---------------------------------------------------------------------------
# Effective Purchased View ("Make Effective Purchased View canonical for all
# consumers"): the ONE merge implementation -- original, immutable
# PurchaseDocument/PurchaseLine columns plus the latest additive
# PurchasedFieldCorrection per field -- every consumer of Purchased output
# builds on, instead of each reading raw columns and/or reimplementing its
# own "latest correction wins" reduction. Used by:
#   - `get_purchased_lines_with_allocation()` above (non-goods allocation
#     base, per-line effective amount);
#   - `reconcile_receiving_line()`/`raise_receiving_discrepancy_alert()`
#     below (effective invoice quantity for three-way reconciliation);
#   - `03 Software/InvoiceIntake/human_review.py`'s `effective_document_view()`
#     (header/line display values, re-validation).
# `PurchaseDocument`/`PurchaseLine` themselves are never mutated by any of
# this -- the merge is always computed on read (Task requirement: "Ma il
# valore CANONICO CONSUMABILE è sempre il valore effettivo risultante dal
# merge").
# ---------------------------------------------------------------------------


def latest_field_corrections(
    corrections: list[m.PurchasedFieldCorrection],
) -> dict[tuple[int | None, str], m.PurchasedFieldCorrection]:
    """Reduces an oldest-first correction history (`list_field_corrections()`'s
    own contract) to the single latest row per (purchase_line_id,
    field_name). Pure/no I/O — for a caller that already holds the full
    history (e.g. `human_review.py`'s own `view["corrections"]`) and would
    otherwise re-query it via `resolve_latest_field_corrections()` below."""

    latest: dict[tuple[int | None, str], m.PurchasedFieldCorrection] = {}
    for correction in corrections:
        latest[(correction.purchase_line_id, correction.field_name)] = correction
    return latest


def resolve_latest_field_corrections(
    session: Session, purchase_document_id: int
) -> dict[tuple[int | None, str], m.PurchasedFieldCorrection]:
    """Convenience wrapper: fetch + reduce in one call, for a caller that
    does not already hold the document's full correction history."""

    return latest_field_corrections(list_field_corrections(session, purchase_document_id))


def correction_overrides_value(correction: m.PurchasedFieldCorrection | None) -> bool:
    """True only when `correction` is an actual value override — a bare
    `CORRECT` confirmation never carries a `corrected_value`
    (`record_field_correction` always stores `None` for it), so it is never
    treated as an override; the original value stands confirmed as-is."""

    return correction is not None and correction.classification != "CORRECT" and correction.corrected_value is not None


def effective_field_value(
    latest: dict[tuple[int | None, str], m.PurchasedFieldCorrection],
    purchase_line_id: int | None,
    field_name: str,
    original: Any,
) -> Any:
    """The Human-Review-effective value for one field: the latest
    correction's `corrected_value` when it actually overrides the original
    (`correction_overrides_value()`); otherwise whatever was ALREADY
    effective at the moment that latest (non-overriding) record was
    submitted — its own `original_value` snapshot — falling back to the
    caller-supplied `original` only when no correction exists at all, or
    when that snapshot itself is `None`.

    Bug fix ("Purchased Operator Review Test on Real Invoices", found by
    actually driving a two-step real review: correct a field, then later
    submit a bare `CORRECT` confirmation on that SAME field). Before this
    fix, a later non-overriding record (a `CORRECT` confirmation, or an
    `AMBIGUOUS`/`UNREAD` left with no `corrected_value`) always fell back
    to `original` — the RAW column value — silently discarding an earlier
    real correction's effect the instant any later record for that field
    carried no override of its own. `record_field_correction` always
    snapshots the then-current effective value into `original_value`
    (`human_review.submit_field_review()`'s own `original_value =
    view["header_effective"][field_name]`/line equivalent), so that
    snapshot — not the raw column — is the correct fallback: a later
    confirmation must confirm/leave what a reviewer actually SAW and
    accepted, never silently un-correct it.

    A caller may pass either a display string (`human_review.py`) or a raw
    typed value (a `PurchaseLine` column, e.g. `quantity`/
    `source_amount_minor`) as `original` — only the override branch and a
    correction's own `original_value` are ever a `str`
    (`PurchasedFieldCorrection` columns)."""

    correction = latest.get((purchase_line_id, field_name))
    if correction is None:
        return original
    if correction_overrides_value(correction):
        return correction.corrected_value
    return correction.original_value if correction.original_value is not None else original


def list_human_review_queue(session: Session, restaurant_id: int, *, limit: int = 200) -> list[m.PurchaseDocument]:
    """Every `PurchaseDocument` for this Restaurant currently in the HUMAN
    functional state, most recently created first (Task requirement 2:
    "Ordina prioritariamente per: più recenti"). A small local-scale query
    (Python-side status filter, not a SQL EXISTS) — proportionate to this
    prototype's real data volumes, same simplicity convention the rest of
    this module already follows."""

    candidates = list(
        session.scalars(
            select(m.PurchaseDocument)
            .join(m.Supplier, m.PurchaseDocument.supplier_id == m.Supplier.id)
            .where(m.Supplier.restaurant_id == restaurant_id)
            .order_by(m.PurchaseDocument.created_at.desc())
            .limit(limit)
        ).all()
    )
    return [doc for doc in candidates if get_document_functional_status(session, doc.id) == "HUMAN"]


def list_sibling_documents(session: Session, purchase_document_id: int) -> list[m.PurchaseDocument]:
    """Every OTHER `PurchaseDocument` that came from the exact same source
    file as this one (Task requirement 3, "Multi-invoice visibility") —
    matched by `source_reference`'s own page-range-suffix convention
    (`"<file>#p<range>"`, `invoice_splitter.py`) so a Prime Line-style
    4-invoice batch shows all 4 review records together, not just the one
    being viewed. A document whose `source_reference` carries no `#`
    suffix (not a split batch) has no siblings by definition."""

    document = session.get(m.PurchaseDocument, purchase_document_id)
    if document is None or not document.source_reference or "#" not in document.source_reference:
        return []
    supplier = session.get(m.Supplier, document.supplier_id)
    file_prefix = document.source_reference.split("#", 1)[0]
    siblings = session.scalars(
        select(m.PurchaseDocument)
        .join(m.Supplier, m.PurchaseDocument.supplier_id == m.Supplier.id)
        .where(
            m.Supplier.restaurant_id == supplier.restaurant_id,
            m.PurchaseDocument.source_reference.like(f"{file_prefix}#%"),
            m.PurchaseDocument.id != purchase_document_id,
        )
    ).all()
    return list(siblings)
