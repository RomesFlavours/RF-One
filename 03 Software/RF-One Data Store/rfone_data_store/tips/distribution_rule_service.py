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

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m


def create_rule(
    session: Session, *, restaurant_id: int, source_role_id: int, recipient_role_id: int,
    calculation_base: str, rate: Decimal, effective_from: datetime, effective_to: datetime | None = None,
    created_by: str | None = None,
    eligibility_mode: str = m.ELIGIBILITY_MODE_ACTIVE_AT_SETTLEMENT,
    distribution_method: str = m.DISTRIBUTION_METHOD_EQUAL,
    no_eligible_recipient_behavior: str = m.NO_ELIGIBLE_RECIPIENT_SOURCE_RETAINS,
    transaction_scope: str = m.TRANSACTION_SCOPE_ALL,
) -> m.TipDistributionRule:
    """Creates a new Tip Distribution Rule identity together with its first
    version (version_number 1). `is_active` defaults to True (task item
    #10) — a newly-created rule is live unless explicitly deactivated.

    TIP_DISTRIBUTION_ENGINE_001 §6: `eligibility_mode`/`distribution_method`/
    `no_eligible_recipient_behavior`/`transaction_scope` default to the only
    values the engine currently implements, so every existing caller (the
    Tips web UI, `seed_tip_distribution_rules.py`) keeps working unchanged."""

    _validate_calculation_base(calculation_base)
    _validate_eligibility_mode(eligibility_mode)
    _validate_distribution_method(distribution_method)
    _validate_no_eligible_recipient_behavior(no_eligible_recipient_behavior)
    _validate_transaction_scope(transaction_scope)

    rule = m.TipDistributionRule(restaurant_id=restaurant_id, is_active=True)
    session.add(rule)
    session.flush()

    session.add(
        m.TipDistributionRuleVersion(
            rule_id=rule.id, version_number=1, source_role_id=source_role_id, recipient_role_id=recipient_role_id,
            calculation_base=calculation_base, rate=rate, effective_from=effective_from, effective_to=effective_to,
            created_by=created_by, eligibility_mode=eligibility_mode, distribution_method=distribution_method,
            no_eligible_recipient_behavior=no_eligible_recipient_behavior, transaction_scope=transaction_scope,
        )
    )
    session.flush()
    return rule


def create_new_version(
    session: Session, rule_id: int, *, source_role_id: int, recipient_role_id: int, calculation_base: str,
    rate: Decimal, effective_from: datetime, effective_to: datetime | None = None, created_by: str | None = None,
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
    explicit "never rewrite historical rule versions")."""

    rule = session.get(m.TipDistributionRule, rule_id)
    if rule is None:
        raise ValueError(f"No TipDistributionRule with id {rule_id}")
    _validate_calculation_base(calculation_base)
    _validate_eligibility_mode(eligibility_mode)
    _validate_distribution_method(distribution_method)
    _validate_no_eligible_recipient_behavior(no_eligible_recipient_behavior)
    _validate_transaction_scope(transaction_scope)

    existing_versions = list_versions(session, rule_id)
    next_version_number = (existing_versions[-1].version_number + 1) if existing_versions else 1

    current_open_version = next(
        (v for v in reversed(existing_versions) if v.effective_to is None), None,
    )
    if current_open_version is not None:
        current_open_version.effective_to = effective_from

    new_version = m.TipDistributionRuleVersion(
        rule_id=rule_id, version_number=next_version_number, source_role_id=source_role_id,
        recipient_role_id=recipient_role_id, calculation_base=calculation_base, rate=rate,
        effective_from=effective_from, effective_to=effective_to, created_by=created_by,
        eligibility_mode=eligibility_mode, distribution_method=distribution_method,
        no_eligible_recipient_behavior=no_eligible_recipient_behavior, transaction_scope=transaction_scope,
    )
    session.add(new_version)
    session.flush()
    return new_version


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
    never guesses/falls back to the nearest version."""
    stmt = select(m.TipDistributionRuleVersion).where(
        m.TipDistributionRuleVersion.rule_id == rule_id,
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
def _validate_eligibility_mode(eligibility_mode: str) -> None:
    if eligibility_mode != m.ELIGIBILITY_MODE_ACTIVE_AT_SETTLEMENT:
        raise ValueError(
            f"Unknown or not-yet-implemented Eligibility Mode {eligibility_mode!r}; expected "
            f"{m.ELIGIBILITY_MODE_ACTIVE_AT_SETTLEMENT!r}"
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
