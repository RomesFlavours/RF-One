"""Tip Payment Instruction — RF-One's own canonical duplicate-payment guard
and Outcome Verification for paying out a Tip Payment Cycle through the
connector configured for that Restaurant (TASK_TIPS_CORE2_PILOT;
TASK_TIPS_COMPLETE_001 §10; STEP 12B integration; `01 Domains/Business
Domain/Restaurant/Tips/Tips Payment Execution.md`).

Consumes, never redefines, Core 2.0:
- Process Autonomy / completion requires a verified result, not a dispatched
  command (`00 Core/ConceptualArchitecture/11_...md` §3).
- Trigger recognition != execution authority; a recognized Missing Semantics
  gap is represented, never guessed (`13_...md` §3, §10).
- Attention Management's CRITICAL/HIGH/MEDIUM/LOW, contextually determined,
  never a fixed table (`12_...md` §3).

This module owns Payment Instruction identity/submission/outcome tracking
only — WHICH Employees/amounts end up in an instruction (aggregating
`TipEntitlement` rows across a Payment Cycle) is `payment_cycle_service.
start_payment_cycle`'s concern, not this module's; this module never reads
`TipEntitlement` or `TipDistributionCalculationRun` directly.

Provider-neutral by construction (STEP 12B Product Owner decision): every
function below takes a `connector: payment_connector.PaymentConnector`
(never a `MercuryClient` directly) and catches only
`payment_connector.PaymentConnectorError` subclasses — never a
Mercury-specific exception type. `payment_cycle_service.py`/
`payout_process.py`/`scheduler.py` resolve WHICH connector to pass in from
each Restaurant's own configured `connector_code`
(`tips/payment_connector.resolve_connector`); this module simply executes
against whichever connector it is given, exactly like it always executed
against whichever client was passed to it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import payment_connector as connector_svc

UTC = timezone.utc

STATUS_READY = "READY"
STATUS_SUBMITTED = "SUBMITTED"
STATUS_SENT = "SENT"
STATUS_OUTCOME_VERIFIED = "OUTCOME_VERIFIED"
STATUS_NEEDS_ATTENTION = "NEEDS_ATTENTION"
STATUS_CANCELLED = "CANCELLED"

# Failure classes — plus the two conditions specific to this pilot's own
# resolution step (no recipient reference on file, and Outcome Reopened by
# a later `reversed` observation).
FAILURE_RECIPIENT_NOT_CONFIGURED = "RECIPIENT_NOT_CONFIGURED"
FAILURE_SYNCHRONOUS_VALIDATION = "SYNCHRONOUS_VALIDATION"
FAILURE_DUPLICATE_PROTECTION = "DUPLICATE_PROTECTION"
FAILURE_PROVIDER_STATUS_FAILURE = "PROVIDER_STATUS_FAILURE"
FAILURE_PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
FAILURE_OUTCOME_REOPENED = "OUTCOME_REOPENED"

PRIORITY_CRITICAL = "CRITICAL"
PRIORITY_HIGH = "HIGH"
PRIORITY_MEDIUM = "MEDIUM"
PRIORITY_LOW = "LOW"

_TERMINAL_FAILURE_STATUSES = {"failed", "blocked", "cancelled"}


def build_idempotency_key(payment_cycle_id: int, employee_id: int, reference_id: int) -> str:
    """Deterministic from RF-One's own canonical Payment Instruction
    identity PLUS the specific recipient reference resolved at submit time
    — never random, never provider-influenced. Including `reference_id`
    (not just cycle+employee) is required by empirical Mercury sandbox
    behavior: resubmitting under the SAME key after the underlying
    `recipientId` changed (a corrected reference) returns HTTP 409, not a
    safe replay — see `models.TipPaymentInstruction.idempotency_key`. The
    SAME key is still reused on every retry against the SAME resolved
    reference (a transient-failure retry stays deduplicated); only a
    genuine reference correction derives a new key."""
    return f"RFONE-TIPS-CYCLE{payment_cycle_id}-EMP{employee_id}-REF{reference_id}"


def _active_recipient_reference(
    session: Session, employee_id: int, *, connector_code: str,
) -> "m.EmployeeExternalPaymentAccount | None":
    return session.scalars(
        select(m.EmployeeExternalPaymentAccount).where(
            m.EmployeeExternalPaymentAccount.employee_id == employee_id,
            m.EmployeeExternalPaymentAccount.provider == connector_code,
            m.EmployeeExternalPaymentAccount.is_active.is_(True),
        )
    ).first()


def mark_needs_attention(
    instruction: "m.TipPaymentInstruction", *, failure_class: str, reason: str, priority: str,
) -> None:
    instruction.status = STATUS_NEEDS_ATTENTION
    instruction.failure_class = failure_class
    instruction.reason_for_failure = reason
    instruction.priority = priority


def submit_payment_instruction(
    session: Session, instruction: "m.TipPaymentInstruction", connector: "connector_svc.PaymentConnector", *,
    account_id: str,
) -> None:
    """Submits exactly ONE Payment Instruction. Never touches any other
    instruction — a caller iterating a batch (`payment_cycle_service.py`)
    wraps each call independently so one failure can never block or roll
    back the others. Safe to call again on an instruction already in
    NEEDS_ATTENTION: the SAME idempotency_key is reused, so a retry after a
    transient provider failure is exactly the resubmission a connector's
    own duplicate protection is designed to make safe."""
    if instruction.status not in (STATUS_READY, STATUS_NEEDS_ATTENTION):
        return  # already submitted/terminal — never resubmit a SENT/OUTCOME_VERIFIED instruction.

    reference = _active_recipient_reference(
        session, instruction.employee_id, connector_code=connector.connector_code,
    )
    if reference is None:
        mark_needs_attention(
            instruction, failure_class=FAILURE_RECIPIENT_NOT_CONFIGURED,
            reason=(
                f"Employee {instruction.employee_id} has no active {connector.connector_code} recipient "
                f"reference on file."
            ),
            priority=PRIORITY_HIGH,
        )
        return

    instruction.provider = connector.connector_code
    instruction.provider_account_id = account_id
    # A key already derived from THIS SAME reference is reused as-is (a
    # transient-failure retry against the same recipient must stay
    # deduplicated); the reference changed since the last attempt (or none
    # was derived yet) derives a fresh one — see `build_idempotency_key`.
    if instruction.provider_recipient_id != reference.provider_recipient_id or instruction.idempotency_key is None:
        instruction.idempotency_key = build_idempotency_key(
            instruction.payment_cycle_id, instruction.employee_id, reference.id,
        )
    instruction.provider_recipient_id = reference.provider_recipient_id

    amount = _amount_decimal(instruction.amount_minor)
    try:
        transaction = connector.create_transaction(
            account_id=account_id, recipient_id=reference.provider_recipient_id, amount=amount,
            payment_method="ach", idempotency_key=instruction.idempotency_key,
        )
    except connector_svc.ConnectorAuthError as exc:
        mark_needs_attention(
            instruction, failure_class=FAILURE_PROVIDER_UNAVAILABLE,
            reason=f"Connector authentication failed: {exc}", priority=PRIORITY_CRITICAL,
        )
        return
    except connector_svc.ConnectorDuplicateError as exc:
        # Should not happen in normal operation — RF-One's own idempotency
        # check above is the primary guard. Seeing this means either a
        # genuine race, or an operator manually resubmitted outside this
        # code path; either way it is itself worth surfacing, not silently
        # treated as a benign no-op (a connector's own duplicate protection
        # is only a safety net — when it fires, RF-One's own guard should
        # be reviewed).
        mark_needs_attention(
            instruction, failure_class=FAILURE_DUPLICATE_PROTECTION,
            reason=f"Connector rejected this as a duplicate: {exc}", priority=PRIORITY_HIGH,
        )
        return
    except connector_svc.ConnectorValidationError as exc:
        mark_needs_attention(
            instruction, failure_class=FAILURE_SYNCHRONOUS_VALIDATION,
            reason=str(exc), priority=PRIORITY_HIGH,
        )
        return
    except connector_svc.ConnectorUnavailableError as exc:
        mark_needs_attention(
            instruction, failure_class=FAILURE_PROVIDER_UNAVAILABLE,
            reason=f"Connector unavailable: {exc}", priority=PRIORITY_MEDIUM,
        )
        return

    instruction.provider_transaction_id = transaction.id
    instruction.provider_status = transaction.status
    instruction.submitted_at = _utc_now()
    instruction.status = STATUS_SENT if transaction.status in ("pending", "sent") else STATUS_SUBMITTED
    instruction.failure_class = None
    instruction.reason_for_failure = None
    instruction.priority = None


def refresh_outcome(
    session: Session, instruction: "m.TipPaymentInstruction", connector: "connector_svc.PaymentConnector",
) -> None:
    """Polls the connector for this instruction's Transaction and updates
    the observed outcome. The ONLY state this pilot treats as a verified
    successful Outcome is `provider_status == 'sent'` AND `posted_at`
    populated — and even then, calling this again LATER can still flip a
    previously OUTCOME_VERIFIED instruction back to NEEDS_ATTENTION if the
    connector now reports `reversed` (Outcome Reopened)."""
    if instruction.provider_transaction_id is None:
        return  # nothing to poll yet.

    try:
        transaction = connector.get_transaction(instruction.provider_transaction_id)
    except connector_svc.ConnectorNotFoundError as exc:
        mark_needs_attention(
            instruction, failure_class=FAILURE_PROVIDER_UNAVAILABLE,
            reason=f"Connector transaction {instruction.provider_transaction_id} not found on read-back: {exc}",
            priority=PRIORITY_HIGH,
        )
        return
    except connector_svc.ConnectorUnavailableError as exc:
        # A transient read failure does NOT itself reopen a
        # previously-verified Outcome — it only means this particular
        # refresh attempt could not confirm anything new either way.
        mark_needs_attention(
            instruction, failure_class=FAILURE_PROVIDER_UNAVAILABLE,
            reason=f"Could not read back connector transaction status: {exc}", priority=PRIORITY_MEDIUM,
        )
        return

    instruction.provider_status = transaction.status
    instruction.posted_at = _parse_iso(transaction.posted_at)

    if transaction.status == "reversed":
        mark_needs_attention(
            instruction, failure_class=FAILURE_OUTCOME_REOPENED,
            reason=(
                "A Transaction previously observed sent has since been reversed — the prior Outcome is "
                "reopened; this Payment Instruction requires re-evaluation, not automatic resubmission."
            ),
            priority=PRIORITY_HIGH,
        )
        return

    if transaction.status in _TERMINAL_FAILURE_STATUSES:
        mark_needs_attention(
            instruction, failure_class=FAILURE_PROVIDER_STATUS_FAILURE,
            reason=transaction.reason_for_failure or f"Connector transaction status is {transaction.status!r}.",
            priority=PRIORITY_HIGH,
        )
        return

    if transaction.status == "sent" and instruction.posted_at is not None:
        instruction.status = STATUS_OUTCOME_VERIFIED
        instruction.failure_class = None
        instruction.reason_for_failure = None
        instruction.priority = None
        return

    # `pending`/`sent` with no `postedAt` yet: not a failure, not yet
    # verified — leave as SENT for a later refresh to re-check (never
    # presented as completed before verification).
    instruction.status = STATUS_SENT


def _amount_decimal(amount_minor: int) -> Decimal:
    return (Decimal(amount_minor) / Decimal(100)).quantize(Decimal("0.01"))


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class FundingCheckResult:
    required_minor: int
    available_minor: int
    sufficient: bool
    account_id: str | None = None
    reason: str | None = None


def check_funding(
    connector: "connector_svc.PaymentConnector", *, account_id: str, instructions: list["m.TipPaymentInstruction"],
) -> FundingCheckResult:
    """The connector's own available balance must cover the FULL batch
    total before ANY instruction in it is submitted. Funding the source
    account itself is out of scope — this only reads what the connector
    already reports as available right now."""
    required_minor = sum(i.amount_minor for i in instructions if i.status == STATUS_READY)
    accounts = {a.id: a for a in connector.get_accounts()}
    account = accounts.get(account_id)
    if account is None:
        return FundingCheckResult(
            required_minor=required_minor, available_minor=0, sufficient=False, account_id=account_id,
            reason=f"Source account {account_id} not found among {connector.connector_code} accounts.",
        )
    available_minor = int((account.available_balance * 100).to_integral_value())
    sufficient = available_minor >= required_minor
    return FundingCheckResult(
        required_minor=required_minor, available_minor=available_minor, sufficient=sufficient,
        account_id=account_id,
        reason=None if sufficient else (
            f"{connector.connector_code} available balance ({available_minor} minor units) is less than the "
            f"total READY Payment Instruction amount ({required_minor} minor units) for this batch."
        ),
    )
