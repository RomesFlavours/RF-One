"""Manual reconciliation of ONE transaction: WHO + WHY (BANK_MANUAL_WHO_WHY_001).

The Review's "Select WHO / WHY" popup — used on To Reconcile and on
Reconciled — has one purpose: a person states, for THIS transaction, who the
counterparty is and what the money was for. It is the counterpart of the
Rule, never a substitute for it:

    Rule                 teaches recognition: description pattern -> WHO.
                         Never chooses a WHY for any transaction.
    Select WHO / WHY     reconciles one transaction: WHO + WHY, a HUMAN
                         decision. Never creates a recognition rule.

Nothing here is a second implementation of an existing concept:

* the decision is `row_reconciliation.record_who` — the HUMAN decision of
  the Reconciliation rows (WHAT derived from the WHY, no description
  learning, a changed row loses its acceptance and is Needs review again);
* a new WHY is `configuration.create_why` — the Bank Configuration service,
  with its own rules (a name and a P&L WHAT), here also its navigation
  group (`BankReasonGroup`, required by the popup). A name that already IS
  an active WHY is never created twice: that WHY is reused (Configuration
  would otherwise accept a second WHY with the same name under a suffixed
  code — a parallel definition);
* the WHY offered are the WHOLE active catalog, grouped
  (`why_navigation_catalog`, BANK_WHY_NAVIGATION_GROUPS_001); the WHO's own
  WHY (`why_catalog.reasons_for_occurrence`) are only marked. Choosing one
  the WHO does not have yet adds the WHO -> WHY association
  (`why_catalog.associate`).

A new WHY is created in the SAME database transaction as the decision it
is chosen for: if anything refuses, the caller rolls back and no WHY is
left behind without the transaction that asked for it.

Every function flushes and never commits.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import configuration as config_service
from . import row_reconciliation
from . import why_catalog


@dataclass(frozen=True)
class NewWhy:
    """A WHY the operator creates from the popup: its name and the navigation
    group it is filed under (both required; the group has no accounting
    effect), and — optionally — its WHAT. Bank reconciliation needs WHO + WHY,
    not bookkeeping (BANK_WHY_WITHOUT_WHAT_001)."""
    name: str
    what_id: int | None = None
    group_id: int | None = None


def active_who_list(session: Session) -> list[dict]:
    """Every ACTIVE WHO, alphabetical, for the popup's list: id, name and —
    only when it has any — its aliases as one search string. Aliases help
    the search; choosing always gives the canonical WHO. One query for the
    WHO, one for the aliases, whatever their number."""
    whos = session.execute(
        select(m.BankOccurrence.id, m.BankOccurrence.canonical_name)
        .where(m.BankOccurrence.status == "ACTIVE")
    ).all()
    active_ids = {who_id for who_id, _ in whos}
    aliases: dict[int, set[str]] = {}
    for occurrence_id, text in session.execute(
        select(m.BankOccurrenceAlias.occurrence_id, m.BankOccurrenceAlias.alias_text)
    ):
        if occurrence_id in active_ids and text:
            aliases.setdefault(occurrence_id, set()).add(text)
    result = []
    for who_id, name in sorted(whos, key=lambda row: (row[1] or "").casefold()):
        entry = {"id": who_id, "name": name}
        extra = sorted(a for a in aliases.get(who_id, ()) if a.casefold() != (name or "").casefold())
        if extra:
            entry["aliases"] = " · ".join(extra)
        result.append(entry)
    return result


def whys_for_who(session: Session, occurrence_id: int) -> list[dict]:
    """The WHY currently available for this WHO — its active possible WHY,
    by name — each with the accounting outcome it resolves to."""
    who = session.get(m.BankOccurrence, occurrence_id)
    if who is None or who.status != "ACTIVE":
        raise ValueError("This WHO does not exist or is not active.")
    return [{"id": reason.id, "name": reason.name, "what": reason.resolution_label}
            for reason in why_catalog.reasons_for_occurrence(session, occurrence_id)]


def why_navigation_catalog(session: Session) -> dict:
    """The whole active WHY catalog for the popup's WHY GROUP and WHY
    columns, fetched once per page: the navigation groups
    (`BankReasonGroup`, alphabetical — `why_catalog.groups`) and every active WHY —
    its group, and the WHAT or Balance Sheet destination it resolves to, when it
    has one (a WHY needs none: BANK_WHY_WITHOUT_WHAT_001). A WHY in no active group is listed under a
    trailing "Other" entry (id null) rather than hidden. Groups organise; they
    never decide anything about accounting."""
    groups = why_catalog.groups(session)
    active_group_ids = {g.id for g in groups}
    whys = []
    for reason in why_catalog.active_reasons(session):
        group_id = reason.reason_group_id if reason.reason_group_id in active_group_ids else None
        whys.append({"id": reason.id, "name": reason.name, "what": reason.resolution_label,
                     "group_id": group_id})
    counts: dict[int | None, int] = {}
    for why in whys:
        counts[why["group_id"]] = counts.get(why["group_id"], 0) + 1
    result = [{"id": g.id, "name": g.name, "count": counts.get(g.id, 0)} for g in groups]
    if counts.get(None):
        result.append({"id": None, "name": "Other", "count": counts[None]})
    return {"groups": result, "whys": whys}


def catalog_whys(session: Session) -> list[dict]:
    """Every active WHY, by name — what
    "Create New WHY" suggests as the operator types, so an existing purpose
    is reused instead of being created again."""
    return [{"name": reason.name, "what": reason.resolution_label}
            for reason in why_catalog.active_reasons(session)]


def existing_why_named(session: Session, name: str) -> "m.BankTransactionReason | None":
    """The active WHY already called `name` (case and spacing ignored), if any."""
    wanted = " ".join((name or "").split()).casefold()
    if not wanted:
        return None
    for reason in session.scalars(select(m.BankTransactionReason).where(m.BankTransactionReason.status == "ACTIVE")):
        if " ".join((reason.name or "").split()).casefold() == wanted:
            return reason
    return None


def what_options(session: Session) -> list[dict]:
    """The P&L WHAT a new WHY may be given — the same set Bank Configuration
    offers (`configuration.create_why` refuses anything else)."""
    return [{"id": c.id, "label": f"{c.code} — {c.name}"}
            for c in session.scalars(
                select(m.BankAccountingClassification).order_by(m.BankAccountingClassification.code))
            if c.is_what]


# ---------------------------------------------------------------------------
# Create New WHY — the ONE flow behind both reconciliation modals
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CreatedWhy:
    """What "Create New WHY" did: the WHY (new or reused), whether it was
    reused, and whether the WHO -> WHY association was added by this call."""
    reason: "m.BankTransactionReason"
    reused: bool
    associated: bool


def create_why_options(session: Session) -> dict:
    """Everything the shared "Create New WHY" dialog needs, in one answer:
    the WHY groups (alphabetical, `why_catalog.groups`), the P&L WHAT a new
    WHY may take (`what_options`), and the existing WHY names (so the dialog
    can say early that a name will be reused)."""
    return {
        "groups": [{"id": g.id, "name": g.name} for g in why_catalog.groups(session)],
        "whats": what_options(session),
        "whys": [{"id": r.id, "name": r.name, "group_id": r.reason_group_id, "what": r.resolution_label}
                 for r in why_catalog.active_reasons(session)],
    }


def _create_or_reuse_why(session: Session, new_why: NewWhy) -> tuple["m.BankTransactionReason", bool]:
    """A WHY named `new_why.name`: the active WHY already called so (case and
    spacing ignored) is reused unchanged; otherwise it is created through the
    Configuration service (`configuration.create_why`: a name and a P&L
    WHAT) in the WHY group chosen. Returns (WHY, reused)."""
    name = " ".join((new_why.name or "").split())
    if not name:
        raise ValueError("Write the name of the new WHY.")
    reason = existing_why_named(session, name)
    if reason is not None:
        return reason, True
    if new_why.group_id is None:
        raise ValueError("Choose the WHY group of the new WHY.")
    reason = config_service.create_why(
        session, name=name, description=None, what_id=new_why.what_id, active=True,
        reason_group_id=new_why.group_id,
    )
    return reason, False


def create_why_for_who(session: Session, *, new_why: NewWhy, occurrence_id: int | None) -> CreatedWhy:
    """"Create New WHY" from either reconciliation modal (Select WHO / WHY or
    the WHO Rule): the WHY — created, or the existing one of the same name
    reused — and, when a WHO is given, its WHO -> WHY association, added only
    if missing (an existing one is left as it is). Creating the WHY is not a
    confirmation: the association starts at 0 and the Confirm or Apply that
    uses it counts the one human confirmation (BANK_FINAL_RELEASE_BLOCKERS_002). Nothing is decided for any transaction here: Select WHO / WHY
    still records its decision on Confirm, and a WHO Rule still never
    chooses a WHY.

    One database transaction for all of it: flushes, never commits — the
    caller commits on success and rolls everything back on any refusal, so no
    WHY is left without its group, WHAT or association."""
    who = None
    if occurrence_id is not None:
        who = session.get(m.BankOccurrence, occurrence_id)
        if who is None or who.status != "ACTIVE":
            raise ValueError("The WHO of this WHY is not an active WHO.")
    reason, reused = _create_or_reuse_why(session, new_why)
    associated = False
    if who is not None:
        current = session.scalars(select(m.BankOccurrenceReasonAssociation).where(
            m.BankOccurrenceReasonAssociation.occurrence_id == who.id,
            m.BankOccurrenceReasonAssociation.transaction_reason_id == reason.id)).first()
        if current is None or not current.active:
            why_catalog.associate(session, occurrence_id=who.id, transaction_reason_id=reason.id,
                                  confirm=False)
            associated = True
    return CreatedWhy(reason=reason, reused=reused, associated=associated)


def reconcile_who_why(
    session: Session, *, transaction_id: int, occurrence_id: int | None, reason_id: int | None,
    account_id: int | None, new_why: NewWhy | None = None,
) -> "m.BankTransactionExplanation":
    """Record the WHO and the WHY a person chose for THIS transaction.

    Both are required. The WHY may be ANY active WHY of the catalog: when it
    is not yet one of the WHO's possible WHY, the person choosing it here is
    what confirms it: the HUMAN decision records the WHO -> WHY association
    (`why_catalog.associate`, one row per pair — a second choice of the same
    WHY counts one more confirmation on it, as every human decision always
    has) in the same database transaction. With `new_why` the WHY is first created
    through the Configuration service, in the navigation group chosen — or,
    when an active WHY already has that name, that WHY is reused unchanged.
    No recognition rule is created and no description is learned."""
    if occurrence_id is None:
        raise ValueError("Choose the WHO of this transaction.")
    who = session.get(m.BankOccurrence, occurrence_id)
    if who is None or who.status != "ACTIVE":
        raise ValueError("Choose an active WHO for this transaction.")
    if new_why is not None:
        # The same creation as "Create New WHY" (`_create_or_reuse_why`) —
        # one implementation, whichever way the WHY reaches this decision.
        reason, _reused = _create_or_reuse_why(session, new_why)
        reason_id = reason.id
    if reason_id is None:
        raise ValueError("Choose the WHY of this transaction.")
    reason = session.get(m.BankTransactionReason, reason_id)
    if reason is None or reason.status != "ACTIVE":
        raise ValueError("Choose an active WHY for this transaction.")
    # The HUMAN decision records the WHO -> WHY association itself
    # (`recognition.record_human_decision` -> `why_catalog.associate`), so a
    # WHY the WHO did not have yet is associated exactly once.
    return row_reconciliation.record_who(
        session, transaction_id=transaction_id, occurrence_id=who.id, reason_id=reason_id,
        account_id=account_id, any_active_why=True,
    )
