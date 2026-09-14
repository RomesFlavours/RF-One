"""Tip Payment Instruction — RF-One's own canonical duplicate-payment guard
and Outcome Verification for paying out a Tip Payment Cycle through Mercury
(TASK_TIPS_CORE2_PILOT; TASK_TIPS_COMPLETE_001 §10; `01 Domains/Business
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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..technical.connectors.mercury.client import (
    MercuryAuthError, MercuryClient, MercuryDuplicateProtectionError, MercuryNotFoundError,
    MercuryUnavailableError, MercuryValidationError,
)

UTC = timezone.utc

STATUS_READY = "READY"
STATUS_SUBMITTED = "SUBMITTED"
STATUS_SENT = "SENT"
STATUS_OUTCOME_VERIFIED = "OUTCOME_VERIFIED"
STATUS_NEEDS_ATTENTION = "NEEDS_ATTENTION"
STATUS_CANCELLED = "CANCELLED"

# Failure classes — task §11's A-E, plus the two conditions specific to this
# pilot's own resolution step (no recipient reference on file, and Outcome
# Reopened by a later `reversed` observation, task §10).
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

_MERCURY_TERMINAL_FAILURE_STATUSES = {"failed", "blocked", "cancelled"}


def build_idempotency_key(payment_cycle_id: int, employee_id: int, reference_id: int) -> str:
    """Deterministic from RF-One's own canonical Payment Instruction
    identity PLUS the specific recipient reference resolved at submit time
    — never random, never provider-influenced (task §5). Including
    `reference_id` (not just cycle+employee) is required by empirical
    Mercury sandbox behavior: resubmitting under the SAME key after the
    underlying `recipientId` changed (a corrected reference) returns HTTP
    409, not a safe replay — see `models.TipPaymentInstruction.
    idempotency_key`. The SAME key is still reused on every retry against
    the SAME resolved reference (a transient-failure retry stays
    deduplicated); only a genuine reference correction derives a new key.

    Keyed by `payment_cycle_id` (TASK_TIPS_COMPLETE_001 §4/§10), not a
    single `calculation_run_id` — one Payment Instruction may now aggregate
    entitlements from many calculation runs/Business Dates, so the Payment
    Cycle (not any one run) is this instruction's true, stable identity."""
    return f"RFONE-TIPS-CYCLE{payment_cycle_id}-EMP{employee_id}-REF{reference_id}"


def _active_recipient_reference(session: Session, employee_id: int) -> "m.EmployeeExternalPaymentAccount | None":
    return session.scalars(
        select(m.EmployeeExternalPaymentAccount).where(
            m.EmployeeExternalPaymentAccount.employee_id == employee_id,
            m.EmployeeExternalPaymentAccount.provider == "MERCURY",
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
    session: Session, instruction: "m.TipPaymentInstruction", client: MercuryClient, *, account_id: str,
) -> None:
    """Submits exactly ONE Payment Instruction. Never touches any other
    instruction — a caller iterating a batch (`payout_process.py`) wraps
    each call independently so one failure can never block or roll back the
    others (task §9). Safe to call again on an instruction already in
    NEEDS_ATTENTION: the SAME idempotency_key is reused, so a retry after a
    transient provider failure is exactly the resubmission Mercury's own
    duplicate protection is designed to make safe."""
    if instruction.status not in (STATUS_READY, STATUS_NEEDS_ATTENTION):
        return  # already submitted/terminal — never resubmit a SENT/OUTCOME_VERIFIED instruction.

    reference = _active_recipient_reference(session, instruction.employee_id)
    if reference is None:
        mark_needs_attention(
            instruction, failure_class=FAILURE_RECIPIENT_NOT_CONFIGURED,
            reason=f"Employee {instruction.employee_id} has no active Mercury recipient reference on file.",
            priority=PRIORITY_HIGH,
        )
        return

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
        transaction = client.create_transaction(
            account_id=account_id, recipient_id=reference.provider_recipient_id, amount=amount,
            payment_method="ach", idempotency_key=instruction.idempotency_key,
        )
    except MercuryAuthError as exc:
        mark_needs_attention(
            instruction, failure_class=FAILURE_PROVIDER_UNAVAILABLE,
            reason=f"Mercury authentication failed: {exc}", priority=PRIORITY_CRITICAL,
        )
        return
    except MercuryDuplicateProtectionError as exc:
        # Should not happen in normal operation — RF-One's own idempotency
        # check above is the primary guard. Seeing this means either a
        # genuine race, or an operator manually resubmitted outside this
        # code path; either way it is itself worth surfacing, not silently
        # treated as a benign no-op (task §5's "Mercury duplicate protection
        # is only a safety net" cuts both ways: when it fires, RF-One's own
        # guard should be reviewed).
        mark_needs_attention(
            instruction, failure_class=FAILURE_DUPLICATE_PROTECTION,
            reason=f"Mercury rejected this as a duplicate: {exc}", priority=PRIORITY_HIGH,
        )
        return
    except MercuryValidationError as exc:
        mark_needs_attention(
            instruction, failure_class=FAILURE_SYNCHRONOUS_VALIDATION,
            reason=str(exc), priority=PRIORITY_HIGH,
        )
        return
    except MercuryUnavailableError as exc:
        mark_needs_attention(
            instruction, failure_class=FAILURE_PROVIDER_UNAVAILABLE,
            reason=f"Mercury unavailable: {exc}", priority=PRIORITY_MEDIUM,
        )
        return

    instruction.provider_transaction_id = transaction.id
    instruction.provider_status = transaction.status
    instruction.submitted_at = _utc_now()
    instruction.status = STATUS_SENT if transaction.status in ("pending", "sent") else STATUS_SUBMITTED
    instruction.failure_class = None
    instruction.reason_for_failure = None
    instruction.priority = None


def refresh_outcome(session: Session, instruction: "m.TipPaymentInstruction", client: MercuryClient) -> None:
    """Polls Mercury for this instruction's Transaction and updates the
    observed outcome (task §10). The ONLY state this pilot treats as a
    verified successful Outcome is `provider_status == 'sent'` AND
    `posted_at` populated — and even then, calling this again LATER can
    still flip a previously OUTCOME_VERIFIED instruction back to
    NEEDS_ATTENTION if Mercury now reports `reversed` (Outcome Reopened,
    task §10's explicit non-immutability requirement)."""
    if instruction.provider_transaction_id is None:
        return  # nothing to poll yet.

    try:
        transaction = client.get_transaction(instruction.provider_transaction_id)
    except MercuryNotFoundError as exc:
        mark_needs_attention(
            instruction, failure_class=FAILURE_PROVIDER_UNAVAILABLE,
            reason=f"Mercury transaction {instruction.provider_transaction_id} not found on read-back: {exc}",
            priority=PRIORITY_HIGH,
        )
        return
    except (MercuryAuthError, MercuryUnavailableError) as exc:
        # A transient read failure does NOT itself reopen a
        # previously-verified Outcome — it only means this particular
        # refresh attempt could not confirm anything new either way.
        mark_needs_attention(
            instruction, failure_class=FAILURE_PROVIDER_UNAVAILABLE,
            reason=f"Could not read back Mercury transaction status: {exc}", priority=PRIORITY_MEDIUM,
        )
        return

    instruction.provider_status = transaction.status
    instruction.posted_at = _parse_iso(transaction.posted_at)

    if transaction.status == "reversed":
        mark_needs_attention(
            instruction, failure_class=FAILURE_OUTCOME_REOPENED,
            reason=(
                "Mercury Transaction previously observed sent has since been reversed — the prior Outcome is "
                "reopened; this Payment Instruction requires re-evaluation, not automatic resubmission."
            ),
            priority=PRIORITY_HIGH,
        )
        return

    if transaction.status in _MERCURY_TERMINAL_FAILURE_STATUSES:
        mark_needs_attention(
            instruction, failure_class=FAILURE_PROVIDER_STATUS_FAILURE,
            reason=transaction.reason_for_failure or f"Mercury transaction status is {transaction.status!r}.",
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
    # verified — leave as SENT for a later refresh to re-check (task §10:
    # never presented as completed before verification).
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


def check_funding(client: MercuryClient, *, account_id: str, instructions: list["m.TipPaymentInstruction"]) -> FundingCheckResult:
    """Task §8 — Mercury `availableBalance` must cover the FULL batch total
    before ANY instruction in it is submitted. Chase -> Mercury funding
    itself is out of scope (External Funding Dependency, task §9 of the
    Mercury discovery task) — this only reads what Mercury already reports
    as available right now."""
    required_minor = sum(i.amount_minor for i in instructions if i.status == STATUS_READY)
    accounts = {a.id: a for a in client.get_accounts()}
    account = accounts.get(account_id)
    if account is None:
        return FundingCheckResult(
            required_minor=required_minor, available_minor=0, sufficient=False, account_id=account_id,
            reason=f"Source account {account_id} not found among Mercury accounts.",
        )
    available_minor = int((account.available_balance * 100).to_integral_value())
    sufficient = available_minor >= required_minor
    return FundingCheckResult(
        required_minor=required_minor, available_minor=available_minor, sufficient=sufficient,
        account_id=account_id,
        reason=None if sufficient else (
            f"Mercury availableBalance ({available_minor} minor units) is less than the total READY Payment "
            f"Instruction amount ({required_minor} minor units) for this batch."
        ),
    )
