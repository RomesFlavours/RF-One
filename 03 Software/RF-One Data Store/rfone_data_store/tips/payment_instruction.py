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

from sqlalchemy import func, select
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
# CLOVER_MULTISITE_001: the attempt is durably recorded and the provider is being called; the outcome is
# not known until it is recorded. Never sent again from this state (awaiting reconciliation).
STATUS_SUBMITTING = "SUBMITTING"

# Failure classes — plus the two conditions specific to this pilot's own
# resolution step (no recipient reference on file, and Outcome Reopened by
# a later `reversed` observation).
FAILURE_RECIPIENT_NOT_CONFIGURED = "RECIPIENT_NOT_CONFIGURED"
FAILURE_SYNCHRONOUS_VALIDATION = "SYNCHRONOUS_VALIDATION"
FAILURE_DUPLICATE_PROTECTION = "DUPLICATE_PROTECTION"
FAILURE_PROVIDER_STATUS_FAILURE = "PROVIDER_STATUS_FAILURE"
FAILURE_PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
FAILURE_OUTCOME_REOPENED = "OUTCOME_REOPENED"
# CLOVER_MULTISITE_001: the provider gave no certain answer (timeout, unavailable, duplicate/idempotency
# collision): a payment may exist. Awaiting reconciliation; never retried as a new payment.
FAILURE_OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
# The provider refused the credentials: certainly no payment was created.
FAILURE_PROVIDER_AUTH_REJECTED = "PROVIDER_AUTH_REJECTED"

PRIORITY_CRITICAL = "CRITICAL"
PRIORITY_HIGH = "HIGH"
PRIORITY_MEDIUM = "MEDIUM"
PRIORITY_LOW = "LOW"

_TERMINAL_FAILURE_STATUSES = {"failed", "blocked", "cancelled"}
# Public name: the provider outcomes after which a new attempt cannot pay twice.
TERMINAL_FAILURE_STATUSES = frozenset(_TERMINAL_FAILURE_STATUSES)


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


def active_recipient_reference(
    session: Session, employee_id: int, *, connector_code: str,
) -> "m.EmployeeExternalPaymentAccount | None":
    """The recipient reference a submit would use now (public, read-only)."""
    return _active_recipient_reference(session, employee_id, connector_code=connector_code)


def mark_needs_attention(
    instruction: "m.TipPaymentInstruction", *, failure_class: str, reason: str, priority: str,
) -> None:
    instruction.status = STATUS_NEEDS_ATTENTION
    instruction.failure_class = failure_class
    instruction.reason_for_failure = reason
    instruction.priority = priority


# `submit_payment_instruction` (a provider call with no durable record of the attempt first) was removed
# by CLOVER_MULTISITE_001: every send goes through `prepare_submission` (committed) + `send_submission`.


class SubmissionRefused(ValueError):
    """A submission cannot be prepared (an attempt with an unknown outcome is still open)."""


def open_submission(session: Session, instruction_id: int) -> "m.TipPaymentSubmission | None":
    """The attempt of this instruction whose outcome is not known yet (PENDING or UNCERTAIN), if any."""
    return session.scalars(select(m.TipPaymentSubmission).where(
        m.TipPaymentSubmission.payment_instruction_id == instruction_id,
        m.TipPaymentSubmission.state.in_(m.TIP_SUBMISSION_OPEN_STATES))).first()


def latest_submission(session: Session, instruction_id: int) -> "m.TipPaymentSubmission | None":
    return session.scalars(select(m.TipPaymentSubmission).where(
        m.TipPaymentSubmission.payment_instruction_id == instruction_id)
        .order_by(m.TipPaymentSubmission.id.desc())).first()


def prepare_submission(
    session: Session, instruction: "m.TipPaymentInstruction", *, restaurant_id: int, connector_code: str,
    account_id: str, actor: tuple[str, int | None, int | None], now: datetime, retry: bool = False,
) -> "m.TipPaymentSubmission | None":
    """CLOVER_MULTISITE_001 — records the attempt BEFORE the provider is called: operation identity
    (the row), restaurant and cycle, recipient reference and provider recipient, source account,
    amount, idempotency key, actor (`actor` = (actor_kind, account_id, acting_identity_id)) and time;
    the instruction becomes SUBMITTING. The caller COMMITS, then calls `send_submission`.

    Returns None (and marks the instruction) when no recipient is configured: nothing is sent.
    A retry gets a new idempotency key: the previous attempt is verified failed, so its key must not
    replay the failed transaction."""
    if open_submission(session, instruction.id) is not None:
        raise SubmissionRefused(
            f"Payment Instruction {instruction.id} has an attempt whose outcome is not known yet: it is "
            "awaiting reconciliation and is never sent again as a new payment.")
    reference = _active_recipient_reference(session, instruction.employee_id, connector_code=connector_code)
    if reference is None:
        mark_needs_attention(
            instruction, failure_class=FAILURE_RECIPIENT_NOT_CONFIGURED,
            reason=f"Employee {instruction.employee_id} has no active {connector_code} recipient reference on file.",
            priority=PRIORITY_HIGH,
        )
        return None
    key = build_idempotency_key(instruction.payment_cycle_id, instruction.employee_id, reference.id)
    if retry:
        attempts = session.scalar(select(func.count(m.TipPaymentSubmission.id)).where(
            m.TipPaymentSubmission.payment_instruction_id == instruction.id)) or 0
        key = f"{key}-R{attempts + 1}"
    actor_kind, actor_account_id, acting_identity_id = actor
    submission = m.TipPaymentSubmission(
        payment_instruction_id=instruction.id, payment_cycle_id=instruction.payment_cycle_id,
        restaurant_id=restaurant_id, employee_id=instruction.employee_id, provider=connector_code,
        provider_account_id=account_id, recipient_reference_id=reference.id,
        provider_recipient_id=reference.provider_recipient_id, amount_minor=instruction.amount_minor,
        idempotency_key=key, actor_kind=actor_kind, account_id=actor_account_id,
        acting_identity_id=acting_identity_id, requested_at=now, state=m.TIP_SUBMISSION_PENDING,
    )
    session.add(submission)
    instruction.status = STATUS_SUBMITTING
    instruction.provider = connector_code
    instruction.provider_account_id = account_id
    instruction.provider_recipient_id = reference.provider_recipient_id
    instruction.idempotency_key = key
    instruction.failure_class = None
    instruction.reason_for_failure = None
    instruction.priority = None
    session.flush()
    return submission


def send_submission(
    session: Session, submission: "m.TipPaymentSubmission", instruction: "m.TipPaymentInstruction",
    connector: "connector_svc.PaymentConnector",
) -> None:
    """Calls the provider for one durably recorded attempt and records the outcome on the attempt and
    the instruction (the caller commits). A certain refusal (credentials, validation) means no payment;
    anything without a certain answer leaves the attempt UNCERTAIN: awaiting reconciliation."""
    try:
        transaction = connector.create_transaction(
            account_id=submission.provider_account_id, recipient_id=submission.provider_recipient_id,
            amount=_amount_decimal(submission.amount_minor), payment_method="ach",
            idempotency_key=submission.idempotency_key,
        )
    except connector_svc.ConnectorAuthError as exc:
        _resolve(submission, m.TIP_SUBMISSION_REJECTED, f"Credentials refused: {exc}")
        mark_needs_attention(instruction, failure_class=FAILURE_PROVIDER_AUTH_REJECTED,
                             reason=f"Connector authentication failed (no payment created): {exc}",
                             priority=PRIORITY_CRITICAL)
        return
    except connector_svc.ConnectorDuplicateError as exc:
        _resolve(submission, m.TIP_SUBMISSION_UNCERTAIN, f"Duplicate/idempotency protection: {exc}")
        mark_needs_attention(instruction, failure_class=FAILURE_OUTCOME_UNKNOWN,
                             reason=("The provider reports an earlier or similar payment for this request: it may "
                                     f"already be paid. Awaiting reconciliation. {exc}"), priority=PRIORITY_HIGH)
        return
    except connector_svc.ConnectorValidationError as exc:
        _resolve(submission, m.TIP_SUBMISSION_REJECTED, f"Refused by the provider: {exc}")
        mark_needs_attention(instruction, failure_class=FAILURE_SYNCHRONOUS_VALIDATION, reason=str(exc),
                             priority=PRIORITY_HIGH)
        return
    except Exception as exc:  # noqa: BLE001 — unavailable, timeout, anything: the outcome is not known
        _resolve(submission, m.TIP_SUBMISSION_UNCERTAIN, f"No certain answer: {exc}")
        mark_needs_attention(instruction, failure_class=FAILURE_OUTCOME_UNKNOWN,
                             reason=("The provider gave no certain answer: the payment may have been made. "
                                     f"Awaiting reconciliation; it is never sent again as a new payment. {exc}"),
                             priority=PRIORITY_HIGH)
        return
    _resolve(submission, m.TIP_SUBMISSION_ACCEPTED, None)
    submission.provider_transaction_id = transaction.id
    submission.provider_status = transaction.status
    instruction.provider_transaction_id = transaction.id
    instruction.provider_status = transaction.status
    instruction.submitted_at = _utc_now()
    instruction.status = STATUS_SENT if transaction.status in ("pending", "sent") else STATUS_SUBMITTED
    instruction.failure_class = None
    instruction.reason_for_failure = None
    instruction.priority = None


def _resolve(submission: "m.TipPaymentSubmission", state: str, detail: str | None) -> None:
    submission.state = state
    submission.detail = detail
    submission.resolved_at = _utc_now()


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
