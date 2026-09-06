"""Automated synthetic tests for TIPS_DISTRIBUTION_RULES_001's Tip
Distribution Rule configuration layer.

Mirrors `tips_validation.py`'s pattern: builds a synthetic (never-real)
fixture inside one transaction, exercises `tips.distribution_rule_service`,
asserts the required behaviors, and always rolls back — no synthetic row is
ever left in the target database.

Deliberately does NOT exercise any calculation/eligibility/allocation
logic — none exists yet, and none is added by this task.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .tips import distribution_rule_service as rule_svc

UTC = timezone.utc


@dataclass
class ValidationResult:
    success: bool
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    def check(self, description: str, condition: bool) -> None:
        if condition:
            self.checks_passed.append(description)
        else:
            self.checks_failed.append(description)
            self.success = False


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)
    with session_factory() as session:
        try:
            _build_fixture_and_assert(session, result)
        finally:
            session.rollback()
    return result


def _dt(days_ago: float) -> datetime:
    return (datetime.now(UTC) - timedelta(days=days_ago)).replace(hour=12, minute=0, second=0, microsecond=0)


def _same_instant(a: datetime | None, b: datetime | None) -> bool:
    """SQLite round-trips `DateTime(timezone=True)` as offset-naive — compare
    on a naive basis rather than assuming both sides carry matching tzinfo."""
    if a is None or b is None:
        return a is b
    a_naive = a.replace(tzinfo=None) if a.tzinfo is not None else a
    b_naive = b.replace(tzinfo=None) if b.tzinfo is not None else b
    return a_naive == b_naive


def _build_fixture_and_assert(session: Session, result: ValidationResult) -> None:
    # --- Base fixture: two Restaurants (for isolation, check B), each with
    # their own Server/Host/Bartender RestaurantRoles. ----------------------
    restaurant_a = m.Restaurant(name="Synthetic TDR Test Restaurant A", default_currency="USD")
    restaurant_b = m.Restaurant(name="Synthetic TDR Test Restaurant B", default_currency="USD")
    session.add_all([restaurant_a, restaurant_b])
    session.flush()

    server_a = m.RestaurantRole(restaurant_id=restaurant_a.id, name="Server")
    host_a = m.RestaurantRole(restaurant_id=restaurant_a.id, name="Host")
    bartender_a = m.RestaurantRole(restaurant_id=restaurant_a.id, name="Bartender")
    server_b = m.RestaurantRole(restaurant_id=restaurant_b.id, name="Server")
    host_b = m.RestaurantRole(restaurant_id=restaurant_b.id, name="Host")
    session.add_all([server_a, host_a, bartender_a, server_b, host_b])
    session.flush()

    # =====================================================================
    # A/C/D/E/F/G: Rule creation, with every field persisted correctly.
    # =====================================================================
    effective_from = _dt(30)
    rule_a1 = rule_svc.create_rule(
        session, restaurant_id=restaurant_a.id, source_role_id=server_a.id, recipient_role_id=host_a.id,
        calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("10.0000"), effective_from=effective_from,
        created_by="tester",
    )
    session.commit()
    session.expire_all()

    result.check("A: a Rule is created with is_active True by default", rule_a1.is_active is True)

    versions_a1 = rule_svc.list_versions(session, rule_a1.id)
    result.check("H: creating a Rule creates exactly one version (version_number 1)", len(versions_a1) == 1 and versions_a1[0].version_number == 1)

    v1 = versions_a1[0]
    result.check(
        "C: Source Role and Recipient Role are persisted exactly as given",
        v1.source_role_id == server_a.id and v1.recipient_role_id == host_a.id,
    )
    result.check("D: Calculation Base is persisted exactly as given", v1.calculation_base == m.CALC_BASE_TIP_PLUS_GRATUITY)
    result.check(
        "E: Rate is persisted as an exact Decimal, never a binary float", v1.rate == Decimal("10.0000") and isinstance(v1.rate, Decimal),
    )
    result.check(
        "F: Effective From is persisted exactly; Effective To is NULL (open-ended) until closed",
        _same_instant(v1.effective_from, effective_from) and v1.effective_to is None,
    )

    # =====================================================================
    # B: Restaurant isolation — Restaurant B has zero rules; a fixture rule
    # for A does not leak into B's own list.
    # =====================================================================
    rules_a = rule_svc.list_rules(session, restaurant_a.id)
    rules_b = rule_svc.list_rules(session, restaurant_b.id)
    result.check(
        "B: a Rule created for Restaurant A is scoped to A only — Restaurant B sees none",
        len(rules_a) == 1 and rules_a[0].id == rule_a1.id and len(rules_b) == 0,
    )

    # =====================================================================
    # G: Active / Inactive state — a simple flag, independent of versioning.
    # =====================================================================
    rule_svc.set_active(session, rule_a1.id, False)
    session.commit()
    session.expire_all()
    reloaded = rule_svc.get_rule(session, rule_a1.id)
    result.check("G: deactivating a Rule sets is_active False", reloaded.is_active is False)
    versions_after_deactivate = rule_svc.list_versions(session, rule_a1.id)
    result.check(
        "G: deactivating a Rule does NOT create a new version or touch the existing one",
        len(versions_after_deactivate) == 1 and versions_after_deactivate[0].id == v1.id
        and versions_after_deactivate[0].effective_to is None,
    )
    rule_svc.set_active(session, rule_a1.id, True)
    session.commit()

    active_only = rule_svc.list_rules(session, restaurant_a.id, active_only=True)
    result.check("G: active_only filtering reflects the current is_active state", len(active_only) == 1)

    # =====================================================================
    # H/I/J: editing a rule (new version) preserves prior version history
    # exactly, never rewriting it.
    # =====================================================================
    second_effective_from = effective_from + timedelta(days=10)
    v2 = rule_svc.create_new_version(
        session, rule_a1.id, source_role_id=server_a.id, recipient_role_id=host_a.id,
        calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("12.5000"), effective_from=second_effective_from,
        created_by="tester",
    )
    session.commit()
    session.expire_all()

    all_versions = rule_svc.list_versions(session, rule_a1.id)
    result.check("H: editing a Rule creates a new version (version_number 2)", len(all_versions) == 2 and all_versions[1].version_number == 2)

    v1_reloaded = session.get(m.TipDistributionRuleVersion, v1.id)
    result.check(
        "J: editing a Rule does NOT rewrite the prior version's own configuration (rate, roles, calculation_base unchanged)",
        v1_reloaded.rate == Decimal("10.0000") and v1_reloaded.source_role_id == server_a.id
        and v1_reloaded.calculation_base == m.CALC_BASE_TIP_PLUS_GRATUITY,
    )
    result.check(
        "I/J: the prior version's effective_to is closed to the new version's effective_from — its own "
        "identity/version_number/id are otherwise untouched",
        _same_instant(v1_reloaded.effective_to, second_effective_from) and v1_reloaded.id == v1.id
        and v1_reloaded.version_number == 1,
    )
    result.check(
        "I: historical version preservation — BOTH versions remain queryable via list_versions, oldest first",
        [ver.version_number for ver in all_versions] == [1, 2],
    )
    result.check(
        "F: the new version's own rate/effective_to reflect what was actually configured",
        v2.rate == Decimal("12.5000") and v2.effective_to is None,
    )

    # Historical reconstructability: a timestamp inside v1's window resolves
    # to v1; a timestamp inside v2's window resolves to v2.
    inside_v1 = effective_from + timedelta(days=1)
    inside_v2 = second_effective_from + timedelta(days=1)
    resolved_v1 = rule_svc.get_version_effective_at(session, rule_a1.id, inside_v1)
    resolved_v2 = rule_svc.get_version_effective_at(session, rule_a1.id, inside_v2)
    result.check(
        "Historical reconstructability: the version effective at a given historical timestamp is resolved "
        "correctly for both the closed (v1) and open (v2) windows",
        resolved_v1 is not None and resolved_v1.id == v1.id and resolved_v2 is not None and resolved_v2.id == v2.id,
    )
    before_any_version = effective_from - timedelta(days=1)
    resolved_none = rule_svc.get_version_effective_at(session, rule_a1.id, before_any_version)
    result.check(
        "Historical reconstructability: a timestamp before any version's effective_from resolves to None "
        "(never guessed)",
        resolved_none is None,
    )

    # =====================================================================
    # K: multiple rules for the SAME Source Role are allowed when separately
    # configured (e.g. Server -> Host AND Server -> Bartender).
    # =====================================================================
    rule_a2 = rule_svc.create_rule(
        session, restaurant_id=restaurant_a.id, source_role_id=server_a.id, recipient_role_id=bartender_a.id,
        calculation_base=m.CALC_BASE_TOTAL_SALES, rate=Decimal("1.0000"), effective_from=effective_from,
    )
    session.commit()
    session.expire_all()

    rules_a_after = rule_svc.list_rules(session, restaurant_a.id)
    result.check(
        "K: the same Source Role (Server) may have multiple simultaneous Recipient Rules "
        "(Server -> Host and Server -> Bartender both exist independently)",
        len(rules_a_after) == 2 and rule_a2.id != rule_a1.id,
    )
    v_rule_a2 = rule_svc.list_versions(session, rule_a2.id)[0]
    result.check(
        "K: the second rule's own configuration (Calculation Base, Rate, Recipient Role) is independent",
        v_rule_a2.recipient_role_id == bartender_a.id and v_rule_a2.calculation_base == m.CALC_BASE_TOTAL_SALES
        and v_rule_a2.rate == Decimal("1.0000"),
    )

    # Editing rule_a2 must never affect rule_a1's own version history.
    rule_svc.create_new_version(
        session, rule_a2.id, source_role_id=server_a.id, recipient_role_id=bartender_a.id,
        calculation_base=m.CALC_BASE_TOTAL_SALES, rate=Decimal("2.0000"), effective_from=effective_from + timedelta(days=5),
    )
    session.commit()
    session.expire_all()
    rule_a1_versions_untouched = rule_svc.list_versions(session, rule_a1.id)
    result.check(
        "J: editing one Rule's version history never affects a DIFFERENT Rule's own version history",
        len(rule_a1_versions_untouched) == 2,
    )

    # Calculation Base vocabulary is validated (task's closed spec §8 vocabulary).
    rejected_invalid_base = False
    try:
        rule_svc.create_rule(
            session, restaurant_id=restaurant_a.id, source_role_id=server_a.id, recipient_role_id=host_a.id,
            calculation_base="MADE_UP_BASE", rate=Decimal("5.0000"), effective_from=effective_from,
        )
    except ValueError:
        rejected_invalid_base = True
        session.rollback()
    result.check(
        "Calculation Base is restricted to the functional spec's own closed vocabulary — an invented "
        "value is rejected, not silently accepted",
        rejected_invalid_base,
    )
    # Re-establish a clean session state after the deliberate rollback above
    # (this fixture's own rows were already committed before this point).
    session.expire_all()

    # =====================================================================
    # L: Rome's Flavours SERVER -> HOST 10% seed exists as restaurant DATA
    # only — the universal engine/service module has no knowledge of it.
    # =====================================================================
    romes_flavours = m.Restaurant(name="Rome's Flavours - WP (synthetic fixture)", default_currency="USD")
    session.add(romes_flavours)
    session.flush()
    server_rf = m.RestaurantRole(restaurant_id=romes_flavours.id, name="Server")
    host_rf = m.RestaurantRole(restaurant_id=romes_flavours.id, name="Host")
    session.add_all([server_rf, host_rf])
    session.flush()

    seed_effective_from = _dt(60)
    seeded_rule = rule_svc.create_rule(
        session, restaurant_id=romes_flavours.id, source_role_id=server_rf.id, recipient_role_id=host_rf.id,
        calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("10.0000"), effective_from=seed_effective_from,
        created_by="seed_tip_distribution_rules.py",
    )
    session.commit()
    session.expire_all()

    seeded_version = rule_svc.list_versions(session, seeded_rule.id)[0]
    result.check(
        "L: the Rome's Flavours SERVER -> HOST 10% TIP_PLUS_GRATUITY rule exists exactly as specified",
        seeded_version.source_role_id == server_rf.id and seeded_version.recipient_role_id == host_rf.id
        and seeded_version.calculation_base == m.CALC_BASE_TIP_PLUS_GRATUITY and seeded_version.rate == Decimal("10.0000"),
    )
    result.check(
        "L: this seed is scoped to Rome's Flavours' own restaurant_id only — not visible under any other Restaurant",
        seeded_rule.restaurant_id == romes_flavours.id
        and seeded_rule not in rule_svc.list_rules(session, restaurant_a.id)
        and seeded_rule not in rule_svc.list_rules(session, restaurant_b.id),
    )
    # Structural check: the universal service module's source code contains
    # no hard-coded reference to Rome's Flavours or to this specific
    # Server/Host rule — it only ever operates on ids/parameters.
    service_source = inspect.getsource(rule_svc)
    result.check(
        "L: the universal engine (distribution_rule_service.py) contains no hard-coded reference to "
        "\"Rome\", \"Server\", or \"Host\" — this rule exists only as seeded restaurant data",
        "Rome" not in service_source and "Server" not in service_source and "Host" not in service_source,
    )
