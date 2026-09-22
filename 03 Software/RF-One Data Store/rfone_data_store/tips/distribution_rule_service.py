"""Tip Distribution Rule — configuration-only service layer
(TIPS_DISTRIBUTION_RULES_001).

Implements ONLY the restaurant-configurable Source-Role -> Recipient-Role
tip-out rule and its version history, per `01 Domains/Business Domain/
Restaurant/Functional Specifications/TIP_DISTRIBUTION_ENGINE_FUNCTIONAL_
SPEC_001.md` §7-§9/§16.

Deliberately contains NO calculation, eligibility, or allocation logic —
no Gross Tip computation, no recipient-role payout distribution, no
Shift-based eligibility, no rounding. This module answers exactly two
kinds of question: "what rules exist" and "what did a rule's configuration
look like at a given moment" — nothing about what to DO with that
configuration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m


def create_rule(
    session: Session, *, restaurant_id: int, recipient_role_id: int,
    calculation_base: str, rate: Decimal, effective_from: datetime, effective_to: datetime | None = None,
    created_by: str | None = None, source_role_id: int | None = None,
    source_semantics: str = m.TIP_SOURCE_SEMANTICS_ROLE,
    eligibility_mode: str = m.ELIGIBILITY_MODE_ACTIVE_AT_SETTLEMENT,
    distribution_method: str = m.DISTRIBUTION_METHOD_EQUAL,
    no_eligible_recipient_behavior: str = m.NO_ELIGIBLE_RECIPIENT_SOURCE_RETAINS,
    transaction_scope: str = m.TRANSACTION_SCOPE_ALL,
) -> m.TipDistributionRule:
    """Creates a new Tip Distribution Rule identity together with its first
    version (version_number 1). `is_active` defaults to True (task item
    #10) — a newly-created rule is live unless explicitly deactivated.

    `source_semantics` defaults to `ROLE` (ORDER_SERVICE_OWNER_SOURCE_
    SEMANTICS_001) — every existing caller that only ever passed
    `source_role_id` (the Tips web UI, `seed_tip_distribution_rules.py`)
    keeps working unchanged. Pass `source_semantics=ORDER_SERVICE_OWNER`
    and leave `source_role_id` unset (`None`) for the other semantics — the
    Order-owning Employee (`Order.employee_id`) unconditionally qualifies as
    the source, regardless of their current RestaurantRole.

    TIP_DISTRIBUTION_ENGINE_001 §6: `eligibility_mode`/`distribution_method`/
    `no_eligible_recipient_behavior`/`transaction_scope` default to the only
    values the engine currently implements, so every existing caller keeps
    working unchanged."""

    _validate_calculation_base(calculation_base)
    _validate_eligibility_mode(eligibility_mode)
    _validate_distribution_method(distribution_method)
    _validate_no_eligible_recipient_behavior(no_eligible_recipient_behavior)
    _validate_transaction_scope(transaction_scope)
    _validate_source_semantics(source_semantics, source_role_id)
    if source_semantics == m.TIP_SOURCE_SEMANTICS_ROLE:
        _validate_role_belongs_to_restaurant(session, role_id=source_role_id, restaurant_id=restaurant_id, label="Source Role")
    _validate_role_belongs_to_restaurant(session, role_id=recipient_role_id, restaurant_id=restaurant_id, label="Recipient Role")

    rule = m.TipDistributionRule(restaurant_id=restaurant_id, is_active=True)
    session.add(rule)
    session.flush()

    session.add(
        m.TipDistributionRuleVersion(
            rule_id=rule.id, version_number=1, source_semantics=source_semantics, source_role_id=source_role_id,
            recipient_role_id=recipient_role_id,
            calculation_base=calculation_base, rate=rate, effective_from=effective_from, effective_to=effective_to,
            created_by=created_by, eligibility_mode=eligibility_mode, distribution_method=distribution_method,
            no_eligible_recipient_behavior=no_eligible_recipient_behavior, transaction_scope=transaction_scope,
        )
    )
    session.flush()
    return rule


def create_new_version(
    session: Session, rule_id: int, *, recipient_role_id: int, calculation_base: str,
    rate: Decimal, effective_from: datetime, effective_to: datetime | None = None, created_by: str | None = None,
    source_role_id: int | None = None, source_semantics: str = m.TIP_SOURCE_SEMANTICS_ROLE,
    eligibility_mode: str = m.ELIGIBILITY_MODE_ACTIVE_AT_SETTLEMENT,
    distribution_method: str = m.DISTRIBUTION_METHOD_EQUAL,
    no_eligible_recipient_behavior: str = m.NO_ELIGIBLE_RECIPIENT_SOURCE_RETAINS,
    transaction_scope: str = m.TRANSACTION_SCOPE_ALL,
) -> m.TipDistributionRuleVersion:
    """Task item #9/#11 — "editing a live rule": appends a NEW version row;
    the current open-ended version (the highest `version_number` with
    `effective_to IS NULL`), if any, has ONLY its own `effective_to` closed
    to this new version's `effective_from` — no other column on that prior
    row is ever touched, and no prior row is ever deleted (task's own
    explicit "never rewrite historical rule versions").

    `source_semantics` defaults to `ROLE` (see `create_rule`'s own
    docstring for the ORDER_SERVICE_OWNER_SOURCE_SEMANTICS_001 alternative)
    — every existing caller keeps working unchanged.

    TIPS_FINALIZED_PERIOD_CALCULATION_AND_REPORT_001 §7 replaces the old
    "close whichever version happens to be open-ended" step with the
    Product Owner's own rule, applied to EVERY existing version, in one
    pass (`_apply_temporal_replacement`):

      * a version that STARTED EARLIER becomes OLD and stops at this
        version's `effective_from`;
      * a version scheduled to start inside this version's coverage
        becomes CANCELLED, and never governs anything;
      * a version starting at or after this version's `effective_to`
        survives as ACTIVE — and when this version is open-ended there is
        no such date, so every later version is cancelled.

    The same pass runs whether the new version starts tomorrow or last
    week: inserting a backdated rule needs no special mechanism, which is
    the point ("Non creare meccanismi speciali o complicati soltanto per
    inserire una regola storica"). The previous code only ever closed the
    open-ended version, so backdating produced a window that ended before
    it began and left two versions both claiming the same days."""

    rule = session.get(m.TipDistributionRule, rule_id)
    if rule is None:
        raise ValueError(f"No TipDistributionRule with id {rule_id}")
    _validate_calculation_base(calculation_base)
    _validate_eligibility_mode(eligibility_mode)
    _validate_distribution_method(distribution_method)
    _validate_no_eligible_recipient_behavior(no_eligible_recipient_behavior)
    _validate_transaction_scope(transaction_scope)
    _validate_source_semantics(source_semantics, source_role_id)
    if source_semantics == m.TIP_SOURCE_SEMANTICS_ROLE:
        _validate_role_belongs_to_restaurant(
            session, role_id=source_role_id, restaurant_id=rule.restaurant_id, label="Source Role",
        )
    _validate_role_belongs_to_restaurant(
        session, role_id=recipient_role_id, restaurant_id=rule.restaurant_id, label="Recipient Role",
    )

    existing_versions = list_versions(session, rule_id)
    next_version_number = (existing_versions[-1].version_number + 1) if existing_versions else 1

    replaced = _apply_temporal_replacement(
        existing_versions, effective_from=effective_from, effective_to=effective_to,
    )

    new_version = m.TipDistributionRuleVersion(
        rule_id=rule_id, version_number=next_version_number, source_semantics=source_semantics,
        source_role_id=source_role_id,
        recipient_role_id=recipient_role_id, calculation_base=calculation_base, rate=rate,
        effective_from=effective_from, effective_to=effective_to, created_by=created_by,
        eligibility_mode=eligibility_mode, distribution_method=distribution_method,
        no_eligible_recipient_behavior=no_eligible_recipient_behavior, transaction_scope=transaction_scope,
        status=m.TIP_RULE_VERSION_STATUS_ACTIVE,
    )
    session.add(new_version)
    session.flush()
    new_version.replaced_versions = replaced  # transient; see the helper
    return new_version


def _apply_temporal_replacement(
    existing_versions: list[m.TipDistributionRuleVersion], *,
    effective_from: datetime, effective_to: datetime | None,
) -> dict[str, list[int]]:
    """§7 — the whole of the Product Owner's rule, and nothing else.

    Mutates each existing version's `status` (and, for an OLD one, its own
    `effective_to`) and returns `{"old": [ids], "cancelled": [ids]}` so the
    caller can report what entering this version did. A version's TERMS are
    never touched; that remains append-only.

    Returned as a plain dict and attached to the new version as a transient
    attribute rather than persisted: it is a description of this one
    operation for the operator who performed it, and the durable record of
    what happened is each affected row's own `status`."""
    old_ids: list[int] = []
    cancelled_ids: list[int] = []
    effective_from = _aware_utc(effective_from)
    effective_to = _aware_utc(effective_to)
    for version in existing_versions:
        version_from = _aware_utc(version.effective_from)
        version_to = _aware_utc(version.effective_to)
        if version_from < effective_from:
            # Started earlier: it governs up to the new version and stops.
            version.status = m.TIP_RULE_VERSION_STATUS_OLD
            if version_to is None or version_to > effective_from:
                version.effective_to = effective_from
            old_ids.append(version.id)
        elif effective_to is not None and version_from >= effective_to:
            # Starts after the new version ends: genuinely still to come.
            version.status = m.TIP_RULE_VERSION_STATUS_ACTIVE
        else:
            # Scheduled inside the new version's coverage (or the new
            # version is open-ended, so there is no "after"): it never
            # governs anything.
            version.status = m.TIP_RULE_VERSION_STATUS_CANCELLED
            cancelled_ids.append(version.id)
    return {"old": old_ids, "cancelled": cancelled_ids}


def _aware_utc(value: datetime | None) -> datetime | None:
    """Every effective date in this module is an instant in UTC, but SQLite
    hands back naive datetimes for a `DateTime(timezone=True)` column, so a
    stored value and a caller-supplied one cannot be compared directly.

    §7 compares effective dates for the first time (the previous code only
    ever assigned one), which is where that difference stopped being
    harmless: an unnormalized comparison raises `TypeError` mid-replacement,
    after some versions have already been re-statused. Naive values are read
    as UTC, matching how they were written."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def list_versions(session: Session, rule_id: int) -> list[m.TipDistributionRuleVersion]:
    """Every version of this Rule, oldest first — the permanent historical
    record (task item #11)."""
    stmt = (
        select(m.TipDistributionRuleVersion)
        .where(m.TipDistributionRuleVersion.rule_id == rule_id)
        .order_by(m.TipDistributionRuleVersion.version_number)
    )
    return list(session.scalars(stmt).all())


def get_version_effective_at(
    session: Session, rule_id: int, as_of: datetime,
) -> m.TipDistributionRuleVersion | None:
    """Task's own "historical periods must always remain reconstructable
    using the rule version that was effective at that time": the ONE
    version (if any) whose `[effective_from, effective_to)` window contains
    `as_of`. Returns `None` if no version was effective at that moment —
    never guesses/falls back to the nearest version.

    §7 — a CANCELLED version is excluded here, which is the entire
    practical meaning of cancelling it: it governs no moment in time, past
    or future. An OLD version is NOT excluded — it still governs its own
    closed window, so a period calculated before the rule changed
    reconstructs exactly as it did then."""
    stmt = select(m.TipDistributionRuleVersion).where(
        m.TipDistributionRuleVersion.rule_id == rule_id,
        m.TipDistributionRuleVersion.status != m.TIP_RULE_VERSION_STATUS_CANCELLED,
        m.TipDistributionRuleVersion.effective_from <= as_of,
        (m.TipDistributionRuleVersion.effective_to.is_(None)) | (m.TipDistributionRuleVersion.effective_to > as_of),
    )
    return session.scalars(stmt).first()


def get_rule(session: Session, rule_id: int) -> m.TipDistributionRule | None:
    return session.get(m.TipDistributionRule, rule_id)


def list_rules(
    session: Session, restaurant_id: int, *, active_only: bool = False,
) -> list[m.TipDistributionRule]:
    """Task item #2/business principle "a Restaurant may have multiple
    rules" — every Rule scoped to this Restaurant, optionally filtered to
    active ones only."""
    stmt = select(m.TipDistributionRule).where(m.TipDistributionRule.restaurant_id == restaurant_id)
    if active_only:
        stmt = stmt.where(m.TipDistributionRule.is_active.is_(True))
    stmt = stmt.order_by(m.TipDistributionRule.id)
    return list(session.scalars(stmt).all())


def set_active(session: Session, rule_id: int, is_active: bool) -> m.TipDistributionRule:
    """Task item #10 — activate/deactivate a Rule. A simple flag flip; never
    creates a new version and never touches any version's effective dates."""
    rule = session.get(m.TipDistributionRule, rule_id)
    if rule is None:
        raise ValueError(f"No TipDistributionRule with id {rule_id}")
    rule.is_active = is_active
    session.flush()
    return rule


def _validate_source_semantics(source_semantics: str, source_role_id: int | None) -> None:
    """ORDER_SERVICE_OWNER_SOURCE_SEMANTICS_001 — the exact same either/or
    the DB CHECK constraint enforces, checked here too so a caller gets a
    clear `ValueError` instead of a raw `IntegrityError`, exactly matching
    this module's existing convention for every other closed-vocabulary
    field."""
    if source_semantics not in m.TIP_SOURCE_SEMANTICS:
        raise ValueError(
            f"Unknown source_semantics {source_semantics!r}; expected one of {m.TIP_SOURCE_SEMANTICS}"
        )
    if source_semantics == m.TIP_SOURCE_SEMANTICS_ROLE and source_role_id is None:
        raise ValueError("source_role_id is required when source_semantics='ROLE'.")
    if source_semantics == m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER and source_role_id is not None:
        raise ValueError("source_role_id must not be set when source_semantics='ORDER_SERVICE_OWNER'.")


def _validate_role_belongs_to_restaurant(
    session: Session, *, role_id: int, restaurant_id: int, label: str,
) -> None:
    """Refuses to save a Rule/version referencing a Role that does not
    exist, or that belongs to a DIFFERENT Restaurant — re-checked here
    regardless of what the caller (the Tips web UI, or any other future
    caller) already filtered client-side, so a rule can never be saved
    with an invalid Role even by calling this service directly."""
    role = session.get(m.RestaurantRole, role_id)
    if role is None:
        raise ValueError(f"{label} {role_id} does not exist.")
    if role.restaurant_id != restaurant_id:
        raise ValueError(f"{label} {role_id} does not belong to this Restaurant.")


def _validate_calculation_base(calculation_base: str) -> None:
    if calculation_base not in m.TIP_DISTRIBUTION_CALCULATION_BASES:
        raise ValueError(
            f"Unknown Calculation Base {calculation_base!r}; expected one of "
            f"{m.TIP_DISTRIBUTION_CALCULATION_BASES}"
        )


# TIP_DISTRIBUTION_ENGINE_001 §6 — the rule STRUCTURE must not prevent a
# future Eligibility Mode/Distribution Method/No-Eligible-Recipient
# Behavior/Transaction Scope (spec §12/§13/§14/§11 each list more than one
# conceptual value), but only the one value per axis the engine actually
# implements today is accepted at rule-creation time — accepting a value the
# engine cannot compute would silently create a rule nothing can honor.
# Broadening these tuples is a code change, never a migration (plain string
# columns, no DB CheckConstraint).
_IMPLEMENTED_ELIGIBILITY_MODES = (
    m.ELIGIBILITY_MODE_ACTIVE_AT_SETTLEMENT,
    # TIPS_BRANCH_CONFIG_BUSINESS_DATE_AND_ELIGIBILITY_002 §5 — now the
    # authoritative rule, and genuinely implemented by the engine (both
    # modes are, unlike the single-value vocabularies alongside them).
    m.ELIGIBILITY_MODE_ACTIVE_AT_ORDER_OPEN,
)


def _validate_eligibility_mode(eligibility_mode: str) -> None:
    if eligibility_mode not in _IMPLEMENTED_ELIGIBILITY_MODES:
        raise ValueError(
            f"Unknown or not-yet-implemented Eligibility Mode {eligibility_mode!r}; expected one "
            f"of {', '.join(repr(x) for x in _IMPLEMENTED_ELIGIBILITY_MODES)}"
        )


def _validate_distribution_method(distribution_method: str) -> None:
    if distribution_method != m.DISTRIBUTION_METHOD_EQUAL:
        raise ValueError(
            f"Unknown or not-yet-implemented Distribution Method {distribution_method!r}; expected "
            f"{m.DISTRIBUTION_METHOD_EQUAL!r}"
        )


def _validate_no_eligible_recipient_behavior(no_eligible_recipient_behavior: str) -> None:
    if no_eligible_recipient_behavior != m.NO_ELIGIBLE_RECIPIENT_SOURCE_RETAINS:
        raise ValueError(
            f"Unknown or not-yet-implemented No-Eligible-Recipient Behavior "
            f"{no_eligible_recipient_behavior!r}; expected {m.NO_ELIGIBLE_RECIPIENT_SOURCE_RETAINS!r}"
        )


def _validate_transaction_scope(transaction_scope: str) -> None:
    if transaction_scope != m.TRANSACTION_SCOPE_ALL:
        raise ValueError(
            f"Unknown or not-yet-implemented Transaction Scope {transaction_scope!r}; expected "
            f"{m.TRANSACTION_SCOPE_ALL!r}"
        )
