"""Hierarchical bank classification — WHO -> WHY -> WHAT
(BANK_RECONCILIATION_WHO_WHY_WHAT_001).

The one place the three-level chain is defined, validated and resolved:

* **WHAT** (`BankAccountingClassification`) — the final accounting
  classification, a Profit & Loss or Balance Sheet line.
* **WHY** (`BankTransactionReason`) — the economic reason a movement
  exists. Each WHY resolves to exactly one current WHAT.
* **WHO** (`BankOccurrence`) — the subject/receiver of the movement.
  Each WHO resolves to exactly one current default WHY, and inherits
  that WHY's WHAT.

Because the chain is stored on the vocabulary itself, a human
reconciling a transaction selects **only the WHO** — WHY and WHAT are
derived. The associations are configured once (Bank > Classification),
never re-selected per transaction.

No parallel model is introduced: `BankOccurrence`, `BankTransactionReason`
and the Kermali export mapping (`BankTransactionReasonExportMapping`)
are the existing canonical rows this module extends and reads. The
Kermali Food $/Oper/Deduct/What-label mapping is deliberately untouched
and keeps feeding the Kermali export columns exactly as before — WHAT is
the accounting statement line, a different and additional fact.

**Nothing here ever rewrites history.** These functions edit the CURRENT
vocabulary and its CURRENT associations only. Every already-confirmed
transaction keeps the immutable snapshot its decision row captured
(`recognition.py`), and changes to a chain apply to future
classifications; applying a changed chain to a historical transaction is
the explicit `Reclassify` action (`recognition.reclassify_transaction`),
which writes a new auditable decision rather than mutating the old one.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models as m

PROFIT_LOSS = "PROFIT_LOSS"
BALANCE_SHEET = "BALANCE_SHEET"
STATEMENT_TYPES = (PROFIT_LOSS, BALANCE_SHEET)

STATEMENT_TYPE_LABELS = {
    PROFIT_LOSS: "Profit & Loss",
    BALANCE_SHEET: "Balance Sheet",
}


# ---------------------------------------------------------------------------
# Chain resolution — the single definition of "complete"
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedChain:
    """WHO -> WHY -> WHAT as resolved from the CURRENT vocabulary.

    `blocking_reason` is None exactly when the chain is complete and
    usable for a new classification. When it is set it is a sentence a
    human can act on, never a status code — the Review modal shows it as
    the reason a WHO cannot be selected."""

    occurrence: "m.BankOccurrence"
    transaction_reason: "m.BankTransactionReason | None" = None
    accounting_classification: "m.BankAccountingClassification | None" = None
    blocking_reason: str | None = None

    @property
    def is_complete(self) -> bool:
        return self.blocking_reason is None


def resolve_chain(session: Session, occurrence: "m.BankOccurrence") -> ResolvedChain:
    """Resolve one WHO to its current WHY and WHAT, or state precisely why
    it cannot be used. Called before every new classification: an
    incomplete WHO is refused, never silently completed with a guess."""
    if occurrence.status != "ACTIVE":
        return ResolvedChain(
            occurrence,
            blocking_reason=(
                f"Who {occurrence.canonical_name!r} is INACTIVE and cannot be used for a new "
                "classification. Reactivate it in Bank > Classification, or choose another Who."
            ),
        )

    reason = (
        session.get(m.BankTransactionReason, occurrence.default_transaction_reason_id)
        if occurrence.default_transaction_reason_id is not None else None
    )
    if reason is None:
        return ResolvedChain(
            occurrence,
            blocking_reason=(
                f"Who {occurrence.canonical_name!r} has no default Why. Set one in "
                "Bank > Classification before using it in reconciliation."
            ),
        )
    if reason.status != "ACTIVE":
        return ResolvedChain(
            occurrence, transaction_reason=reason,
            blocking_reason=(
                f"Who {occurrence.canonical_name!r} points at the INACTIVE Why {reason.name!r}. "
                "Reactivate that Why, or point this Who at an active one, in Bank > Classification."
            ),
        )

    what = (
        session.get(m.BankAccountingClassification, reason.accounting_classification_id)
        if reason.accounting_classification_id is not None else None
    )
    if what is None:
        return ResolvedChain(
            occurrence, transaction_reason=reason,
            blocking_reason=(
                f"Why {reason.name!r} has no What (accounting classification). Assign one in "
                "Bank > Classification before using it in reconciliation."
            ),
        )
    if not what.active:
        return ResolvedChain(
            occurrence, transaction_reason=reason, accounting_classification=what,
            blocking_reason=(
                f"Why {reason.name!r} resolves to the INACTIVE What {what.code} — {what.name}. "
                "Reactivate it, or point the Why at an active What, in Bank > Classification."
            ),
        )
    if what.statement_type is None:
        return ResolvedChain(
            occurrence, transaction_reason=reason, accounting_classification=what,
            blocking_reason=(
                f"What {what.code} — {what.name} is incomplete: it has no statement type "
                "(Profit & Loss or Balance Sheet) yet. Complete it in Bank > Classification."
            ),
        )

    return ResolvedChain(occurrence, transaction_reason=reason, accounting_classification=what)


def resolve_chains(session: Session, occurrences: list["m.BankOccurrence"]) -> dict[int, ResolvedChain]:
    """`resolve_chain` for a list, keyed by Occurrence id — what the
    Review modal and the Classification page both render from."""
    return {occurrence.id: resolve_chain(session, occurrence) for occurrence in occurrences}


# ---------------------------------------------------------------------------
# WHAT — accounting classification CRUD
# ---------------------------------------------------------------------------


def _normalized_code(code: str | None) -> str:
    """A code is identity, so it is normalized once, here: trimmed and
    upper-cased. Two codes differing only by case are the same code."""
    normalized = (code or "").strip().upper()
    if not normalized:
        raise ValueError("A What requires a code.")
    if len(normalized) > 64:
        raise ValueError("A What code may be at most 64 characters.")
    return normalized


def _validated_statement_type(statement_type: str | None, *, required: bool) -> str | None:
    value = (statement_type or "").strip().upper() or None
    if value is not None and value not in STATEMENT_TYPES:
        raise ValueError(
            f"Statement type must be {PROFIT_LOSS} or {BALANCE_SHEET}, got {statement_type!r}."
        )
    if required and value is None:
        raise ValueError("A What requires a statement type: Profit & Loss or Balance Sheet.")
    return value


NODE_TYPES = ("GROUP", "POSTING", "POSTING_CATEGORY")
NORMAL_BALANCES = ("DEBIT", "CREDIT")


def _validated_node_type(node_type: str | None) -> str:
    value = (node_type or "").strip().upper() or "POSTING"
    if value not in NODE_TYPES:
        raise ValueError(f"Node type must be one of {', '.join(NODE_TYPES)}, got {node_type!r}.")
    return value


def _validated_normal_balance(normal_balance: str | None) -> str | None:
    """NULL is allowed and means "not stated" — the same explicit
    incompleteness `statement_type` carries for a legacy-migrated row.
    A made-up side is never better than an absent one."""
    value = (normal_balance or "").strip().upper() or None
    if value is not None and value not in NORMAL_BALANCES:
        raise ValueError(
            f"Normal balance must be {NORMAL_BALANCES[0]} or {NORMAL_BALANCES[1]}, "
            f"got {normal_balance!r}."
        )
    return value


def ancestor_ids(session: Session, classification_id: int) -> list[int]:
    """Every ancestor of a classification, nearest first. Walks with its
    own `seen` guard so a cycle that already exists in data (it cannot be
    created through this module) can never hang the caller."""
    ancestors: list[int] = []
    seen = {classification_id}
    current = session.get(m.BankAccountingClassification, classification_id)
    while current is not None and current.parent_id is not None:
        if current.parent_id in seen:
            break
        ancestors.append(current.parent_id)
        seen.add(current.parent_id)
        current = session.get(m.BankAccountingClassification, current.parent_id)
    return ancestors


def _validated_parent_id(
    session: Session, *, parent_id: int | None, classification_id: int | None,
) -> int | None:
    """`parent_id` must exist and must never create a cycle — neither the
    trivial self-parent nor a longer loop (A -> B -> A)."""
    if parent_id is None:
        return None
    parent = session.get(m.BankAccountingClassification, parent_id)
    if parent is None:
        raise ValueError(f"Parent What {parent_id} does not exist.")
    if classification_id is not None:
        if parent_id == classification_id:
            raise ValueError("A What cannot be its own parent.")
        if classification_id in ancestor_ids(session, parent_id):
            raise ValueError(
                "That parent would create a cycle in the What hierarchy "
                f"(What {classification_id} is already an ancestor of What {parent_id})."
            )
    return parent_id


def create_accounting_classification(
    session: Session, *, code: str, name: str, statement_type: str | None,
    parent_id: int | None = None, description: str | None = None, active: bool = True,
    node_type: str | None = None, normal_balance: str | None = None,
    is_contra: bool = False, review_sensitive: bool = False,
) -> "m.BankAccountingClassification":
    """A NEW What always states its statement side — only a legacy-migrated
    row is allowed to be incomplete, and a migration is the only thing that
    creates one."""
    normalized_code = _normalized_code(code)
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("A What requires a name.")

    existing = session.scalars(
        select(m.BankAccountingClassification)
        .where(m.BankAccountingClassification.code == normalized_code)
    ).first()
    if existing is not None:
        raise ValueError(f"A What with code {normalized_code!r} already exists ({existing.name!r}).")

    classification = m.BankAccountingClassification(
        code=normalized_code,
        name=clean_name,
        statement_type=_validated_statement_type(statement_type, required=True),
        parent_id=_validated_parent_id(session, parent_id=parent_id, classification_id=None),
        description=(description or "").strip() or None,
        active=active,
        node_type=_validated_node_type(node_type),
        normal_balance=_validated_normal_balance(normal_balance),
        is_contra=bool(is_contra),
        review_sensitive=bool(review_sensitive),
    )
    session.add(classification)
    session.flush()
    return classification


def update_accounting_classification(
    session: Session, *, classification_id: int, name: str, statement_type: str | None,
    parent_id: int | None = None, description: str | None = None,
    node_type: str | None = None, normal_balance: str | None = None,
    is_contra: bool | None = None, review_sensitive: bool | None = None,
) -> "m.BankAccountingClassification":
    """Editing never changes `code` — the code is the stable identity a
    historical decision snapshot refers to, and recycling it would make
    that history unreadable. Completing a legacy-migrated row (assigning
    its statement side) happens here, which is why `statement_type` is
    required by this function too."""
    classification = session.get(m.BankAccountingClassification, classification_id)
    if classification is None:
        raise ValueError(f"What {classification_id} does not exist.")

    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("A What requires a name.")

    classification.name = clean_name
    classification.statement_type = _validated_statement_type(statement_type, required=True)
    classification.parent_id = _validated_parent_id(
        session, parent_id=parent_id, classification_id=classification_id,
    )
    classification.description = (description or "").strip() or None
    # The four semantic fields are LEFT ALONE when the caller says nothing
    # about them: this function is also how `what_catalog_import` links a
    # parent, and that pass must not reset semantics the import just set.
    if node_type is not None:
        classification.node_type = _validated_node_type(node_type)
    if normal_balance is not None:
        classification.normal_balance = _validated_normal_balance(normal_balance)
    if is_contra is not None:
        classification.is_contra = bool(is_contra)
    if review_sensitive is not None:
        classification.review_sensitive = bool(review_sensitive)
    session.flush()
    return classification


def accounting_classification_usage(session: Session, classification_id: int) -> dict:
    """How this What is currently used. Deactivation is always allowed;
    physical deletion is refused whenever this is non-empty, which is why
    the two live in the same place."""
    reason_count = session.scalar(
        select(func.count(m.BankTransactionReason.id))
        .where(m.BankTransactionReason.accounting_classification_id == classification_id)
    ) or 0
    decision_count = session.scalar(
        select(func.count(m.BankTransactionExplanation.id))
        .where(m.BankTransactionExplanation.accounting_classification_id == classification_id)
    ) or 0
    child_count = session.scalar(
        select(func.count(m.BankAccountingClassification.id))
        .where(m.BankAccountingClassification.parent_id == classification_id)
    ) or 0
    return {
        "reason_count": reason_count,
        "decision_count": decision_count,
        "child_count": child_count,
        "in_use": bool(reason_count or decision_count or child_count),
    }


def accounting_classification_usages(session: Session) -> dict[int, dict]:
    """`accounting_classification_usage` for every What at once — three
    grouped counts instead of three counts per What
    (BANK_PERFORMANCE_N_PLUS_ONE_001). Same keys, same values."""
    def grouped(column):
        return dict(session.execute(
            select(column, func.count()).where(column.is_not(None)).group_by(column)
        ).all())

    reasons = grouped(m.BankTransactionReason.accounting_classification_id)
    decisions = grouped(m.BankTransactionExplanation.accounting_classification_id)
    children = grouped(m.BankAccountingClassification.parent_id)
    usages = {}
    for (classification_id,) in session.execute(select(m.BankAccountingClassification.id)):
        reason_count = reasons.get(classification_id, 0)
        decision_count = decisions.get(classification_id, 0)
        child_count = children.get(classification_id, 0)
        usages[classification_id] = {
            "reason_count": reason_count,
            "decision_count": decision_count,
            "child_count": child_count,
            "in_use": bool(reason_count or decision_count or child_count),
        }
    return usages


def set_accounting_classification_active(
    session: Session, *, classification_id: int, active: bool,
) -> "m.BankAccountingClassification":
    """Activate/deactivate — the ONLY retirement mechanism for a What.
    There is deliberately no delete: a What referenced by a Reason or by a
    historical decision must stay readable forever."""
    classification = session.get(m.BankAccountingClassification, classification_id)
    if classification is None:
        raise ValueError(f"What {classification_id} does not exist.")
    if active and classification.statement_type is None:
        raise ValueError(
            f"What {classification.code} cannot be activated while it has no statement type. "
            "Edit it and choose Profit & Loss or Balance Sheet first."
        )
    classification.active = active
    session.flush()
    return classification


def list_accounting_classifications(
    session: Session, *, search: str | None = None, include_inactive: bool = True,
) -> list["m.BankAccountingClassification"]:
    query = select(m.BankAccountingClassification)
    if not include_inactive:
        query = query.where(m.BankAccountingClassification.active.is_(True))
    term = (search or "").strip()
    if term:
        pattern = f"%{term}%"
        query = query.where(or_(
            m.BankAccountingClassification.code.ilike(pattern),
            m.BankAccountingClassification.name.ilike(pattern),
        ))
    return list(session.scalars(query.order_by(m.BankAccountingClassification.code)).all())


# ---------------------------------------------------------------------------
# WHY -> WHAT
# ---------------------------------------------------------------------------


def _require_usable_what(session: Session, accounting_classification_id: int | None) -> int:
    if accounting_classification_id is None:
        raise ValueError("A Why requires a What (accounting classification).")
    what = session.get(m.BankAccountingClassification, accounting_classification_id)
    if what is None:
        raise ValueError(f"What {accounting_classification_id} does not exist.")
    if not what.active:
        raise ValueError(f"What {what.code} — {what.name} is inactive and cannot be assigned to a Why.")
    if what.statement_type is None:
        raise ValueError(
            f"What {what.code} — {what.name} has no statement type yet and cannot be assigned to a Why."
        )
    if not what.is_posting_account:
        # A Why IS the automatic destination: every Who that leads to it
        # classifies there without a human looking again. A GROUP is a
        # reporting node, so letting one sit behind a Why would be exactly
        # the automatic classification onto a group that the catalog
        # forbids (BANK_ACCOUNTING_CLASSIFICATION_SEMANTICS_001 §6).
        raise ValueError(
            f"What {what.code} — {what.name} is a reporting group, not an account that can be "
            "posted to. Choose one of its accounts instead."
        )
    return what.id


def create_transaction_reason(
    session: Session, *, code: str, name: str, accounting_classification_id: int | None,
    description: str | None = None, status: str = "ACTIVE",
) -> "m.BankTransactionReason":
    """A new Why is refused without a What — the requirement that makes
    "select only the Who" safe, because every Who leads to a Why that
    already knows its accounting classification."""
    normalized_code = _normalized_code(code)
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("A Why requires a name.")
    if status not in ("ACTIVE", "INACTIVE"):
        raise ValueError(f"Why status must be ACTIVE or INACTIVE, got {status!r}.")

    existing = session.scalars(
        select(m.BankTransactionReason).where(m.BankTransactionReason.code == normalized_code)
    ).first()
    if existing is not None:
        raise ValueError(f"A Why with code {normalized_code!r} already exists ({existing.name!r}).")

    reason = m.BankTransactionReason(
        code=normalized_code,
        name=clean_name,
        description=(description or "").strip() or None,
        status=status,
        accounting_classification_id=_require_usable_what(session, accounting_classification_id),
    )
    session.add(reason)
    session.flush()
    return reason


def update_transaction_reason(
    session: Session, *, transaction_reason_id: int, name: str,
    accounting_classification_id: int | None, description: str | None = None,
) -> "m.BankTransactionReason":
    """Re-pointing a Why at another What affects FUTURE classifications
    only. Already-confirmed transactions keep their snapshot until a human
    explicitly Reclassifies them."""
    reason = session.get(m.BankTransactionReason, transaction_reason_id)
    if reason is None:
        raise ValueError(f"Why {transaction_reason_id} does not exist.")
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("A Why requires a name.")

    reason.name = clean_name
    reason.description = (description or "").strip() or None
    reason.accounting_classification_id = _require_usable_what(session, accounting_classification_id)
    session.flush()
    return reason


def set_transaction_reason_status(
    session: Session, *, transaction_reason_id: int, status: str,
) -> "m.BankTransactionReason":
    reason = session.get(m.BankTransactionReason, transaction_reason_id)
    if reason is None:
        raise ValueError(f"Why {transaction_reason_id} does not exist.")
    if status not in ("ACTIVE", "INACTIVE"):
        raise ValueError(f"Why status must be ACTIVE or INACTIVE, got {status!r}.")
    if status == "ACTIVE" and reason.accounting_classification_id is None:
        raise ValueError(
            f"Why {reason.name!r} cannot be activated without a What. Edit it and assign one first."
        )
    reason.status = status
    session.flush()
    return reason


def list_transaction_reasons(
    session: Session, *, search: str | None = None, include_inactive: bool = True,
) -> list["m.BankTransactionReason"]:
    query = select(m.BankTransactionReason)
    if not include_inactive:
        query = query.where(m.BankTransactionReason.status == "ACTIVE")
    term = (search or "").strip()
    if term:
        pattern = f"%{term}%"
        query = query.where(or_(
            m.BankTransactionReason.code.ilike(pattern),
            m.BankTransactionReason.name.ilike(pattern),
        ))
    return list(session.scalars(query.order_by(m.BankTransactionReason.name)).all())


# ---------------------------------------------------------------------------
# WHO -> WHY
# ---------------------------------------------------------------------------


def _require_usable_why(session: Session, transaction_reason_id: int | None) -> int | None:
    """Validate a Who's default Why, which is OPTIONAL.

    BANK_CANONICAL_WHY_AND_WHO_RELATIONSHIPS_001 §20 — a Who may have
    ZERO, one or many Whys, and the relationship is carried by
    `BankOccurrenceReasonAssociation`. Requiring a default here was a
    WHO -> one WHY constraint in all but name. What remains is a
    SUGGESTION: when set it is validated exactly as before; when absent
    the Who is simply a counterparty nobody has confirmed a purpose for
    yet, which is the ordinary state of a newly recognised payee."""
    if transaction_reason_id is None:
        return None
    reason = session.get(m.BankTransactionReason, transaction_reason_id)
    if reason is None:
        raise ValueError(f"Why {transaction_reason_id} does not exist.")
    if reason.status != "ACTIVE":
        raise ValueError(f"Why {reason.name!r} is inactive and cannot be a Who's default Why.")
    if reason.accounting_classification_id is None:
        raise ValueError(
            f"Why {reason.name!r} has no What yet and cannot be a Who's default Why. "
            "Assign its What first."
        )
    return reason.id


def create_occurrence(
    session: Session, *, canonical_name: str, occurrence_type_id: int,
    default_transaction_reason_id: int | None, optional_notes: str | None = None,
    status: str = "ACTIVE",
) -> "m.BankOccurrence":
    """A new Who is refused without a default Why — which is what lets the
    Review show one `Select Who` control and derive everything else."""
    clean_name = (canonical_name or "").strip()
    if not clean_name:
        raise ValueError("A Who requires a canonical name.")
    if status not in ("ACTIVE", "INACTIVE"):
        raise ValueError(f"Who status must be ACTIVE or INACTIVE, got {status!r}.")
    if session.get(m.BankOccurrenceType, occurrence_type_id) is None:
        raise ValueError(f"Who type {occurrence_type_id} does not exist.")

    existing = session.scalars(
        select(m.BankOccurrence).where(m.BankOccurrence.canonical_name == clean_name)
    ).first()
    if existing is not None:
        raise ValueError(f"A Who named {clean_name!r} already exists.")

    occurrence = m.BankOccurrence(
        canonical_name=clean_name,
        occurrence_type_id=occurrence_type_id,
        status=status,
        optional_notes=(optional_notes or "").strip() or None,
        default_transaction_reason_id=_require_usable_why(session, default_transaction_reason_id),
    )
    session.add(occurrence)
    session.flush()
    return occurrence


def update_occurrence(
    session: Session, *, occurrence_id: int, canonical_name: str, occurrence_type_id: int,
    default_transaction_reason_id: int | None, optional_notes: str | None = None,
) -> "m.BankOccurrence":
    """Both the Who's type and its canonical_name are preserved concepts —
    editable, never dropped, and `canonical_name` stays the unique human
    identity a historical decision snapshot recorded by value."""
    occurrence = session.get(m.BankOccurrence, occurrence_id)
    if occurrence is None:
        raise ValueError(f"Who {occurrence_id} does not exist.")
    clean_name = (canonical_name or "").strip()
    if not clean_name:
        raise ValueError("A Who requires a canonical name.")
    if session.get(m.BankOccurrenceType, occurrence_type_id) is None:
        raise ValueError(f"Who type {occurrence_type_id} does not exist.")

    clash = session.scalars(
        select(m.BankOccurrence).where(
            m.BankOccurrence.canonical_name == clean_name,
            m.BankOccurrence.id != occurrence_id,
        )
    ).first()
    if clash is not None:
        raise ValueError(f"A Who named {clean_name!r} already exists.")

    occurrence.canonical_name = clean_name
    occurrence.occurrence_type_id = occurrence_type_id
    occurrence.optional_notes = (optional_notes or "").strip() or None
    occurrence.default_transaction_reason_id = _require_usable_why(session, default_transaction_reason_id)
    session.flush()
    return occurrence


def set_occurrence_status(
    session: Session, *, occurrence_id: int, status: str,
) -> "m.BankOccurrence":
    """Activate/deactivate — the ONLY retirement mechanism for a Who. A Who
    already used by a decision or a recognition rule is never physically
    deleted."""
    occurrence = session.get(m.BankOccurrence, occurrence_id)
    if occurrence is None:
        raise ValueError(f"Who {occurrence_id} does not exist.")
    if status not in ("ACTIVE", "INACTIVE"):
        raise ValueError(f"Who status must be ACTIVE or INACTIVE, got {status!r}.")
    # No default-Why requirement for activation
    # (BANK_CANONICAL_WHY_AND_WHO_RELATIONSHIPS_001 §20): a Who may
    # legitimately have zero Whys until a human confirms one against a
    # real transaction, and refusing to activate it would be the
    # WHO -> one WHY constraint returning by the back door.
    occurrence.status = status
    session.flush()
    return occurrence


def list_occurrences(
    session: Session, *, search: str | None = None, include_inactive: bool = True,
) -> list["m.BankOccurrence"]:
    """Search covers the Who's own name and its TYPE's code/name — the
    "cercare per nome, alias e tipo" the Review modal needs. `canonical_name`
    is the Who's only stored alias today; when a dedicated alias model
    exists it is added here, not duplicated in the route."""
    query = select(m.BankOccurrence)
    if not include_inactive:
        query = query.where(m.BankOccurrence.status == "ACTIVE")
    term = (search or "").strip()
    if term:
        pattern = f"%{term}%"
        type_ids = select(m.BankOccurrenceType.id).where(or_(
            m.BankOccurrenceType.code.ilike(pattern),
            m.BankOccurrenceType.name.ilike(pattern),
        ))
        query = query.where(or_(
            m.BankOccurrence.canonical_name.ilike(pattern),
            m.BankOccurrence.occurrence_type_id.in_(type_ids),
        ))
    return list(session.scalars(query.order_by(m.BankOccurrence.canonical_name)).all())


def list_occurrence_types(session: Session) -> list["m.BankOccurrenceType"]:
    return list(session.scalars(
        select(m.BankOccurrenceType).order_by(m.BankOccurrenceType.name)
    ).all())
