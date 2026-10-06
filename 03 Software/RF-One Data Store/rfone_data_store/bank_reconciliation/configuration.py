"""Bank Configuration — the one page where the WHAT, WHY and WHO vocabulary
and the reporting entities are maintained (BANK_CONFIGURATION_001).

Sources (accounts, cards, card settlement and cardholder, file-recognition
rules, deduplication) are maintained on the Source page and the completeness
control settings in Check Sources on Import and Review — never here
(BANK_FINAL_RELEASE_BLOCKERS_002, BANK_FINAL_CLEANUP_001).

Every business rule of that page lives here, not in its route or template.
Wherever a canonical service already owns a rule it is CALLED, never
copied: `classification` for WHAT / WHY / WHO, `why_catalog.associate` for
WHO -> WHY, `reporting_entity` and `legal_entity_service` for entities. What this module adds is only what
the page needs on top of them:

* WHAT means the canonical P&L posting category (decision D11): the WHAT
  block, the groups a WHAT is placed in and the WHAT a new WHY is given are
  P&L only. Balance Sheet accounts are accounting destinations, never WHAT;
  an existing WHY that settles on one keeps it and is labelled truthfully;
* a new WHAT takes its accounting metadata from the GROUP it is placed in
  (decision D4) — never guessed, refused when the group cannot give it;
* a new WHY gets a stable code generated from its name (D7);
* a new WHO is a COUNTERPARTY (D5);
* WHO -> served ReportingEntities (D1), stated by a human, never inferred;
* WHO-only recognition rules (D2): they recognise the WHO and store no WHY,
  because WHO never determines WHY;
* entities are shown and chosen by `ReportingEntity.name` (D8).

Every function flushes and never commits: the caller owns the transaction,
so a refused step leaves nothing half-written.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import legal_entity_service
from .. import models as m
from . import canonical_catalog
from . import classification
from . import recognition
from . import reporting_entity as reporting_entity_service
from . import why_catalog

# ---------------------------------------------------------------------------
# Vocabulary of the page
# ---------------------------------------------------------------------------

STATEMENT_LABELS = {"PROFIT_LOSS": "P&L", "BALANCE_SHEET": "Balance Sheet"}
PROFIT_LOSS = "PROFIT_LOSS"

# The page's three match words, mapped once onto the stored match types.
MATCH_TYPES = {
    "EXACT": recognition.EXACT_NORMALIZED_DESCRIPTION,
    "CONTAINS": recognition.CONTAINS_TEXT,
    "PREFIX": recognition.PREFIX,
}
MATCH_LABELS = {stored: word for word, stored in MATCH_TYPES.items()}

COUNTERPARTY_TYPE_CODE = "COUNTERPARTY"


def _status(active: bool) -> str:
    return "ACTIVE" if active else "INACTIVE"


def _slug(text: str) -> str:
    """ASCII, upper case, words joined by underscores — the shape every
    existing Why code and ReportingEntity code already has."""
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_").upper()


def _unique_code(session: Session, column, base: str, *, max_length: int = 64) -> str:
    base = base[:max_length - 4].rstrip("_") or "ITEM"
    candidate, suffix = base, 1
    while session.scalar(select(func.count()).where(column == candidate)):
        suffix += 1
        candidate = f"{base}_{suffix}"
    return candidate


# ---------------------------------------------------------------------------
# WHAT — BankAccountingClassification
# ---------------------------------------------------------------------------


def _require_what_row(session: Session, classification_id: int) -> "m.BankAccountingClassification":
    what = session.get(m.BankAccountingClassification, classification_id)
    if what is None:
        raise ValueError(f"WHAT {classification_id} does not exist.")
    if not what.is_posting_account or what.statement_type != PROFIT_LOSS:
        raise ValueError(
            f"{what.code} — {what.name} is not a P&L WHAT and is not edited here."
        )
    return what


def _require_group(session: Session, group_id: int | None) -> "m.BankAccountingClassification":
    """The group a WHAT is placed in, and the source of its accounting
    metadata (D4). Refused, never guessed, when it cannot supply them."""
    if group_id is None:
        raise ValueError("Choose the Group this WHAT belongs to.")
    group = session.get(m.BankAccountingClassification, group_id)
    if group is None:
        raise ValueError(f"Group {group_id} does not exist.")
    if group.node_type != "GROUP":
        raise ValueError(f"{group.code} — {group.name} is not a group.")
    if group.statement_type != PROFIT_LOSS:
        raise ValueError(
            f"{group.code} — {group.name} is a Balance Sheet group. A WHAT is a P&L category."
        )
    if not group.active:
        raise ValueError(f"Group {group.code} — {group.name} is inactive.")
    if group.statement_type is None or group.normal_balance is None:
        raise ValueError(
            f"Group {group.code} — {group.name} does not state its statement type and normal "
            "balance, so a WHAT placed in it would have no valid accounting meaning. "
            "Choose another group."
        )
    return group


def create_what(
    session: Session, *, code: str, name: str, group_id: int | None, active: bool = True,
) -> "m.BankAccountingClassification":
    """A new posting WHAT under `group_id`. Statement type and normal
    balance are the group's; it is a plain posting account — not contra,
    not review-sensitive — exactly like the importer's default."""
    group = _require_group(session, group_id)
    what = classification.create_accounting_classification(
        session, code=code, name=name, statement_type=group.statement_type,
        parent_id=group.id, node_type="POSTING", normal_balance=group.normal_balance,
        is_contra=False, review_sensitive=False,
    )
    if not active:
        classification.set_accounting_classification_active(
            session, classification_id=what.id, active=False,
        )
    return what


def update_what(
    session: Session, *, classification_id: int, name: str, group_id: int | None,
    active: bool,
) -> "m.BankAccountingClassification":
    """Rename, move to another group of the SAME statement, (de)activate.
    The code never changes. Its accounting metadata is kept: moving a WHAT
    across statements would change what every WHY using it means, so that
    is refused rather than silently re-derived."""
    what = _require_what_row(session, classification_id)
    if group_id != what.parent_id:
        group = _require_group(session, group_id)
        if group.statement_type != what.statement_type:
            raise ValueError(
                f"{what.code} is a {STATEMENT_LABELS.get(what.statement_type, 'statement-less')} "
                f"account; group {group.code} — {group.name} is "
                f"{STATEMENT_LABELS[group.statement_type]}. A WHAT cannot change statement here."
            )
    classification.update_accounting_classification(
        session, classification_id=what.id, name=name, statement_type=what.statement_type,
        parent_id=group_id, description=what.description,
    )
    if what.active != active:
        classification.set_accounting_classification_active(
            session, classification_id=what.id, active=active,
        )
    return what


# ---------------------------------------------------------------------------
# WHY — BankTransactionReason
# ---------------------------------------------------------------------------


def generate_reason_code(session: Session, name: str) -> str:
    """The Why code for a new Why (D7): its name in the existing code
    shape, made unique with a numeric suffix. Generated once, at creation —
    renaming the Why later never changes it."""
    base = _slug(name) or "WHY"
    return _unique_code(session, m.BankTransactionReason.code, base)


def create_why(
    session: Session, *, name: str, description: str | None, what_id: int | None,
    active: bool = True, reason_group_id: int | None = None,
) -> "m.BankTransactionReason":
    """`reason_group_id` places the new WHY in a navigation group
    (`BankReasonGroup`) — organisation only, no accounting effect. When given
    it must be an active group.

    BANK_WHY_WITHOUT_WHAT_001 — the WHAT is OPTIONAL: Bank reconciliation
    needs WHO + WHY, not bookkeeping. A WHY created without one has no
    accounting destination yet (never an invented one); when a WHAT is given
    it must be a P&L WHAT, exactly as before."""
    if not (name or "").strip():
        raise ValueError("A WHY requires a name.")
    if what_id is not None:
        _require_pl_what(session, what_id)
    if reason_group_id is not None:
        group = session.get(m.BankReasonGroup, reason_group_id)
        if group is None or not group.active:
            raise ValueError("Choose an active WHY group for the new WHY.")
    reason = classification.create_transaction_reason(
        session, code=generate_reason_code(session, name), name=name,
        accounting_classification_id=what_id, description=description,
        status=_status(active),
    )
    if reason_group_id is not None:
        reason.reason_group_id = reason_group_id
        session.flush()
    return reason


def _require_pl_what(session: Session, what_id: int | None) -> None:
    """A WHY given a WHAT on this page gets a P&L WHAT (D11). The canonical
    `_require_usable_what` then applies its own checks on top."""
    if what_id is None:
        raise ValueError("A WHY requires a WHAT (accounting classification).")
    what = session.get(m.BankAccountingClassification, what_id)
    if what is None:
        raise ValueError(f"WHAT {what_id} does not exist.")
    if not what.is_what:
        kind = ("a Balance Sheet destination" if what.statement_type == "BALANCE_SHEET"
                else "not an active P&L posting category")
        raise ValueError(f"{what.code} — {what.name} is {kind}, not a WHAT. Choose a P&L WHAT.")


def update_why(
    session: Session, *, transaction_reason_id: int, name: str, description: str | None,
    what_id: int | None, active: bool,
) -> "m.BankTransactionReason":
    """Its destination changes ONLY when the operator chose a different one,
    and then only to a P&L WHAT (D11). Keeping the current destination —
    including a Balance Sheet destination an existing WHY settles on — leaves
    it exactly as it is: editing the name or description never reclassifies."""
    reason = session.get(m.BankTransactionReason, transaction_reason_id)
    if reason is None:
        raise ValueError(f"Why {transaction_reason_id} does not exist.")
    # Same destination — or none chosen for a WHY that has none yet
    # (BANK_WHY_WITHOUT_WHAT_001): only the name and description change.
    if what_id == reason.accounting_classification_id:
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("A Why requires a name.")
        reason.name = clean_name
        reason.description = (description or "").strip() or None
        session.flush()
    else:
        _require_pl_what(session, what_id)
        reason = classification.update_transaction_reason(
            session, transaction_reason_id=transaction_reason_id, name=name,
            accounting_classification_id=what_id, description=description,
        )
    if reason.status != _status(active):
        classification.set_transaction_reason_status(
            session, transaction_reason_id=reason.id, status=_status(active),
        )
    return reason


# ---------------------------------------------------------------------------
# WHO — BankOccurrence, its WHYs, its entities, its recognition rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleInput:
    """One row of the WHO modal's recognition-rule table."""
    rule_id: int | None
    pattern: str
    match: str          # EXACT | CONTAINS | PREFIX
    active: bool


def counterparty_type_id(session: Session) -> int:
    occurrence_type = session.scalar(
        select(m.BankOccurrenceType).where(m.BankOccurrenceType.code == COUNTERPARTY_TYPE_CODE)
    )
    if occurrence_type is None:
        raise ValueError(
            "The WHO type COUNTERPARTY does not exist in this database, so a new WHO cannot be "
            "created. It is part of the Bank seed data."
        )
    return occurrence_type.id


def _set_who_reasons(session: Session, occurrence: "m.BankOccurrence", reason_ids: list[int]) -> None:
    """Make the WHO's active possible WHYs exactly `reason_ids`. A pairing
    that is withdrawn is deactivated, never deleted; one already active is
    left alone (no confirmation is counted for a configuration save)."""
    existing = {
        row.transaction_reason_id: row
        for row in session.scalars(
            select(m.BankOccurrenceReasonAssociation)
            .where(m.BankOccurrenceReasonAssociation.occurrence_id == occurrence.id)
        )
    }
    wanted = set(reason_ids)
    for reason_id in wanted:
        row = existing.get(reason_id)
        if row is not None and row.active:
            continue
        reason = session.get(m.BankTransactionReason, reason_id)
        if reason is None:
            raise ValueError(f"WHY {reason_id} does not exist.")
        # A WHY needs no WHAT to be a WHO's possible WHY: Bank reconciliation
        # is WHO + WHY, bookkeeping is optional (BANK_WHY_WITHOUT_WHAT_001).
        if reason.status != "ACTIVE":
            raise ValueError(f"WHY {reason.name!r} is inactive and cannot be added to a WHO.")
        if row is not None:
            row.active = True
        else:
            why_catalog.associate(
                session, occurrence_id=occurrence.id, transaction_reason_id=reason_id,
                source="HUMAN",
            )
    for reason_id, row in existing.items():
        if reason_id not in wanted and row.active:
            row.active = False
    session.flush()


def _set_who_entities(
    session: Session, occurrence: "m.BankOccurrence", reporting_entity_ids: list[int],
) -> None:
    existing = {
        row.reporting_entity_id: row
        for row in session.scalars(
            select(m.BankOccurrenceReportingEntity)
            .where(m.BankOccurrenceReportingEntity.occurrence_id == occurrence.id)
        )
    }
    wanted = set(reporting_entity_ids)
    for entity_id in wanted:
        row = existing.get(entity_id)
        if row is not None and row.active:
            continue
        entity = session.get(m.ReportingEntity, entity_id)
        if entity is None:
            raise ValueError(f"Entity {entity_id} does not exist.")
        if entity.status != "ACTIVE":
            raise ValueError(f"Entity {entity.name!r} is inactive and cannot be served by a WHO.")
        if row is not None:
            row.active = True
        else:
            session.add(m.BankOccurrenceReportingEntity(
                occurrence_id=occurrence.id, reporting_entity_id=entity_id, active=True,
            ))
    for entity_id, row in existing.items():
        if entity_id not in wanted and row.active:
            row.active = False
    session.flush()


def _who_rules(session: Session, occurrence_id: int) -> list["m.BankRecognitionRule"]:
    """The WHO's description rules — the ones that recognise it. MEMO rules
    carry purpose wording, not identity, and are not edited here."""
    return list(session.scalars(
        select(m.BankRecognitionRule)
        .where(
            m.BankRecognitionRule.occurrence_id == occurrence_id,
            m.BankRecognitionRule.match_field == recognition.DESCRIPTION,
        )
        .order_by(m.BankRecognitionRule.id)
    ))


def _set_who_rules(session: Session, occurrence: "m.BankOccurrence", rules: list[RuleInput]) -> None:
    """Create, edit and (de)activate the WHO's recognition rules.

    A new rule is WHO-only (D2): DESCRIPTION scope, `determines_purpose`
    false, no WHY stored, no instrument or direction scope. A rule removed
    from the list is DEACTIVATED, never deleted — decisions may already
    cite it. A pattern that another WHO already recognises with the same
    match is refused: the two rules would contradict each other."""
    current = {rule.id: rule for rule in _who_rules(session, occurrence.id)}
    seen: set[tuple[str, str]] = set()
    kept: set[int] = set()
    for item in rules:
        pattern = recognition.normalize_description_for_recognition(item.pattern)
        if not pattern:
            raise ValueError("A recognition rule needs a text or code pattern.")
        match_type = MATCH_TYPES.get((item.match or "").upper())
        if match_type is None:
            raise ValueError(f"Match must be Exact, Contains or Prefix, got {item.match!r}.")
        if (match_type, pattern) in seen:
            raise ValueError(f"The rule {MATCH_LABELS[match_type].title()} {pattern!r} is listed twice.")
        seen.add((match_type, pattern))

        if item.active:
            clash = session.scalar(
                select(m.BankRecognitionRule).where(
                    m.BankRecognitionRule.match_type == match_type,
                    m.BankRecognitionRule.normalized_pattern == pattern,
                    m.BankRecognitionRule.match_field == recognition.DESCRIPTION,
                    m.BankRecognitionRule.status == "ACTIVE",
                    m.BankRecognitionRule.occurrence_id != occurrence.id,
                )
            )
            if clash is not None:
                other = session.get(m.BankOccurrence, clash.occurrence_id)
                raise ValueError(
                    f"{MATCH_LABELS[match_type].title()} {pattern!r} already recognises WHO "
                    f"{other.canonical_name if other else clash.occurrence_id!r}. One text cannot "
                    "recognise two WHOs; change or deactivate that rule first."
                )

        if item.rule_id is not None:
            rule = current.get(item.rule_id)
            if rule is None:
                raise ValueError(f"Recognition rule {item.rule_id} does not belong to this WHO.")
            rule.match_type = match_type
            rule.normalized_pattern = pattern
            if item.active:
                rule.status = "ACTIVE"
            elif rule.status == "ACTIVE":
                rule.status = "INACTIVE"
            kept.add(rule.id)
        else:
            session.add(m.BankRecognitionRule(
                match_type=match_type, normalized_pattern=pattern,
                match_field=recognition.DESCRIPTION, determines_purpose=False,
                payment_instrument_id=None, direction=None,
                occurrence_id=occurrence.id, transaction_reason_id=None,
                priority=0, status=_status(item.active), auto_apply_enabled=True,
                human_confirmations=0, created_from_transaction_id=None,
            ))
    for rule_id, rule in current.items():
        if rule_id not in kept and rule.status == "ACTIVE":
            rule.status = "INACTIVE"
    session.flush()


def save_who(
    session: Session, *, occurrence_id: int | None, name: str, active: bool,
    reason_ids: list[int], default_reason_id: int | None,
    reporting_entity_ids: list[int], rules: list[RuleInput],
) -> "m.BankOccurrence":
    """Create (`occurrence_id` None) or edit a WHO with everything the modal
    shows. The default WHY, when given, must be one of the possible WHYs:
    a WHY withdrawn from the WHO can no longer be its default. A WHO may
    have no WHY at all — it is then a recognised counterparty whose
    purpose is always decided per transaction."""
    reason_ids = list(dict.fromkeys(reason_ids))
    if default_reason_id is not None and default_reason_id not in reason_ids:
        raise ValueError("The default WHY must be one of this WHO's possible WHY.")

    if occurrence_id is None:
        occurrence = classification.create_occurrence(
            session, canonical_name=name, occurrence_type_id=counterparty_type_id(session),
            default_transaction_reason_id=None, status=_status(active),
        )
    else:
        occurrence = session.get(m.BankOccurrence, occurrence_id)
        if occurrence is None:
            raise ValueError(f"WHO {occurrence_id} does not exist.")
        classification.update_occurrence(
            session, occurrence_id=occurrence.id, canonical_name=name,
            occurrence_type_id=occurrence.occurrence_type_id,
            default_transaction_reason_id=occurrence.default_transaction_reason_id
            if occurrence.default_transaction_reason_id in reason_ids else None,
            optional_notes=occurrence.optional_notes,
        )
        if occurrence.status != _status(active):
            classification.set_occurrence_status(
                session, occurrence_id=occurrence.id, status=_status(active),
            )

    _set_who_reasons(session, occurrence, reason_ids)
    if occurrence.default_transaction_reason_id != default_reason_id:
        classification.update_occurrence(
            session, occurrence_id=occurrence.id, canonical_name=occurrence.canonical_name,
            occurrence_type_id=occurrence.occurrence_type_id,
            default_transaction_reason_id=default_reason_id,
            optional_notes=occurrence.optional_notes,
        )
    _set_who_entities(session, occurrence, list(dict.fromkeys(reporting_entity_ids)))
    _set_who_rules(session, occurrence, rules)
    return occurrence


# ---------------------------------------------------------------------------
# Support — entities
# ---------------------------------------------------------------------------


def _assert_entity_name_free(session: Session, name: str, *, exclude_id: int | None) -> None:
    query = select(m.ReportingEntity).where(func.lower(m.ReportingEntity.name) == name.lower())
    if exclude_id is not None:
        query = query.where(m.ReportingEntity.id != exclude_id)
    if session.scalar(query) is not None:
        raise ValueError(f"An entity named {name!r} already exists.")


def create_entity(
    session: Session, *, name: str, legal_name: str | None, active: bool = True,
) -> "m.ReportingEntity":
    """With a legal name: a real LLC — a LegalEntity and its one LEGAL
    ReportingEntity. Without: a VIRTUAL entity, which never creates a
    LegalEntity. No perimeter is assumed for it."""
    name = (name or "").strip()
    legal_name = (legal_name or "").strip()
    if not name:
        raise ValueError("The entity name is required.")
    _assert_entity_name_free(session, name, exclude_id=None)
    code = _unique_code(session, m.ReportingEntity.code, "RE_" + (_slug(name) or "ENTITY"))
    if legal_name:
        legal = legal_entity_service.create_legal_entity(session, legal_name=legal_name)
        entity = reporting_entity_service.create_legal_entity_reporting_entity(
            session, code=code, name=name, legal_entity_id=legal.id,
        )
    else:
        entity = reporting_entity_service.create_virtual_entity(session, code=code, name=name)
    if not active:
        entity.status = "INACTIVE"
        session.flush()
    return entity


def update_entity(
    session: Session, *, reporting_entity_id: int, name: str, legal_name: str | None,
    active: bool,
) -> "m.ReportingEntity":
    """Rename, correct the LLC's legal name, (de)activate. The LegalEntity
    link itself never changes here, and a virtual entity never becomes an
    LLC."""
    entity = session.get(m.ReportingEntity, reporting_entity_id)
    if entity is None:
        raise ValueError(f"Entity {reporting_entity_id} does not exist.")
    name = (name or "").strip()
    legal_name = (legal_name or "").strip()
    if not name:
        raise ValueError("The entity name is required.")
    _assert_entity_name_free(session, name, exclude_id=entity.id)
    if entity.legal_entity_id is None:
        if legal_name:
            raise ValueError(
                f"{entity.name!r} is a virtual entity: it has no legal name and never becomes an LLC."
            )
    else:
        if not legal_name:
            raise ValueError("An LLC keeps its legal name; it cannot be emptied.")
        legal = session.get(m.LegalEntity, entity.legal_entity_id)
        legal_entity_service.update_legal_entity(
            session, legal, legal_name=legal_name, status=legal.status,
        )
    entity.name = name
    entity.status = _status(active)
    session.flush()
    return entity


# ---------------------------------------------------------------------------
# Cardholder candidates — used by the Source page's Card settings
# ---------------------------------------------------------------------------


def cardholder_candidates(session: Session) -> list[dict]:
    """Real people a cardholder can be linked to: HUMAN_USER identities
    first, then employees not already represented by an identity of the
    same name. A SYSTEM identity is never a valid holder."""
    identities = session.scalars(
        select(m.ActingIdentity)
        .where(m.ActingIdentity.is_active.is_(True), m.ActingIdentity.kind == "HUMAN_USER")
        .order_by(m.ActingIdentity.display_name)
    ).all()
    employees = session.scalars(
        select(m.Employee)
        .where((m.Employee.active.is_(True)) | (m.Employee.active.is_(None)))
        .order_by(m.Employee.display_name)
    ).all()
    candidates = [
        {"kind": m.CARD_HOLDER_KIND_ACTING_IDENTITY, "id": identity.id,
         "name": identity.display_name, "source": "RF-One identity"}
        for identity in identities
    ]
    seen = {(c["name"] or "").strip().casefold() for c in candidates}
    for employee in employees:
        name = (employee.display_name or "").strip()
        if name and name.casefold() in seen:
            continue
        candidates.append({"kind": m.CARD_HOLDER_KIND_EMPLOYEE, "id": employee.id,
                           "name": name or f"Employee {employee.id}", "source": "Employee"})
        if name:
            seen.add(name.casefold())
    return candidates


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------


def configuration_view(session: Session) -> dict:
    """Everything the page renders, as plain JSON-able values, read with a
    fixed number of queries whatever the number of WHOs."""
    classifications = session.scalars(
        select(m.BankAccountingClassification).order_by(m.BankAccountingClassification.code)
    ).all()
    by_id = {c.id: c for c in classifications}
    groups = [
        {"id": c.id, "label": f"{c.code} — {c.name}", "active": c.active,
         "statement": STATEMENT_LABELS.get(c.statement_type, "")}
        for c in classifications if c.node_type == "GROUP" and c.statement_type == PROFIT_LOSS
    ]
    whats = []
    for c in classifications:
        # WHAT = P&L posting categories only (D11), inactive ones included
        # so they can be reactivated; Balance Sheet accounts are never WHAT.
        if c.node_type == "GROUP" or c.statement_type != PROFIT_LOSS:
            continue
        parent = by_id.get(c.parent_id)
        whats.append({
            "id": c.id, "code": c.code, "name": c.name,
            "group_id": c.parent_id, "group": parent.name if parent is not None else "",
            "statement": STATEMENT_LABELS.get(c.statement_type, ""), "active": c.active,
            "assignable": c.is_what,
        })

    def destination(classification_id):
        """How a WHY's destination is shown: a P&L WHAT as "code — name";
        anything else truthfully as what it is, never as a WHAT."""
        target = by_id.get(classification_id)
        if target is None:
            return {"kind": "NONE", "label": "—"}
        if target.statement_type == PROFIT_LOSS and target.node_type != "GROUP":
            return {"kind": "WHAT", "label": f"{target.code} — {target.name}"}
        if target.statement_type == "BALANCE_SHEET":
            return {"kind": "BALANCE_SHEET", "label": f"Balance Sheet destination — {target.name}"}
        return {"kind": "OTHER", "label": f"{target.code} — {target.name} (not a WHAT)"}

    whys = [
        {"id": r.id, "code": r.code, "name": r.name, "description": r.description or "",
         "what": r.accounting_classification_id, "active": r.status == "ACTIVE",
         "destination": destination(r.accounting_classification_id)}
        for r in session.scalars(select(m.BankTransactionReason).order_by(m.BankTransactionReason.name))
    ]
    why_count_by_destination: dict[int, int] = {}
    for why in whys:
        if why["what"] is not None:
            why_count_by_destination[why["what"]] = why_count_by_destination.get(why["what"], 0) + 1
    # Read-only, through the canonical service the Classification page
    # already uses for the same list.
    balance_sheet_destinations = [
        {"id": d.id, "code": d.code, "name": d.name,
         "group": by_id[d.parent_id].name if d.parent_id in by_id else "",
         "why_count": why_count_by_destination.get(d.id, 0)}
        for d in canonical_catalog.accounting_destinations(session)
    ]

    reasons_by_who: dict[int, list[int]] = {}
    for occurrence_id, reason_id in session.execute(
        select(m.BankOccurrenceReasonAssociation.occurrence_id,
               m.BankOccurrenceReasonAssociation.transaction_reason_id)
        .where(m.BankOccurrenceReasonAssociation.active.is_(True))
    ):
        reasons_by_who.setdefault(occurrence_id, []).append(reason_id)
    entities_by_who: dict[int, list[int]] = {}
    for occurrence_id, entity_id in session.execute(
        select(m.BankOccurrenceReportingEntity.occurrence_id,
               m.BankOccurrenceReportingEntity.reporting_entity_id)
        .where(m.BankOccurrenceReportingEntity.active.is_(True))
    ):
        entities_by_who.setdefault(occurrence_id, []).append(entity_id)
    rules_by_who: dict[int, list[dict]] = {}
    for rule in session.scalars(
        select(m.BankRecognitionRule)
        .where(m.BankRecognitionRule.match_field == recognition.DESCRIPTION)
        .order_by(m.BankRecognitionRule.id)
    ):
        rules_by_who.setdefault(rule.occurrence_id, []).append({
            "id": rule.id, "pattern": rule.normalized_pattern,
            "match": MATCH_LABELS.get(rule.match_type, rule.match_type).title(),
            "active": rule.status == "ACTIVE", "status": rule.status,
        })
    whos = [
        {"id": o.id, "name": o.canonical_name, "whys": reasons_by_who.get(o.id, []),
         "default_why": o.default_transaction_reason_id,
         "entities": entities_by_who.get(o.id, []), "rules": rules_by_who.get(o.id, []),
         "active": o.status == "ACTIVE"}
        for o in session.scalars(select(m.BankOccurrence).order_by(m.BankOccurrence.canonical_name))
    ]

    legal_names = dict(session.execute(select(m.LegalEntity.id, m.LegalEntity.legal_name)).all())
    entities = [
        {"id": e.id, "name": e.name, "legal_name": legal_names.get(e.legal_entity_id, ""),
         "legal": e.legal_entity_id is not None, "active": e.status == "ACTIVE"}
        for e in session.scalars(select(m.ReportingEntity).order_by(m.ReportingEntity.name))
    ]

    return {
        "whats": whats, "groups": groups, "whys": whys,
        "balance_sheet_destinations": balance_sheet_destinations, "whos": whos, "entities": entities,
    }
