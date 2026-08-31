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
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
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
    supplier = m.Supplier(restaurant_id=restaurant_id, name=name, status="ACTIVE")
    session.add(supplier)
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
        invoice_quantity=purchase_line.quantity if purchase_line else None,
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
        invoice_quantity=purchase_line.quantity if purchase_line else None,
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
