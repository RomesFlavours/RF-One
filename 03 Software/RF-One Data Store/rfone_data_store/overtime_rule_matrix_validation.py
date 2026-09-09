"""Automated synthetic tests for the Overtime Rule Matrix foundation
(Product Owner decision).

Mirrors the established `*_validation.py` pattern (see
`identity_authority_signature_validation.py`, `organization_validation.py`):
synthetic fixture, disposable database, always rolled back, never touches
real data. Constraint-violation scenarios use a nested SAVEPOINT
(`session.begin_nested()`) so a single expected `IntegrityError` does not
abort the whole validation transaction.

This suite proves only that the `OvertimeRule` model can represent
materially different rule shapes and rejects invalid data — it does NOT
test, and no code anywhere in this repository implements, actual overtime
calculation, hour detection, workweek/workday aggregation, weighted
regular-rate calculation, or overlap resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from . import models as m

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
            _test_representative_rule_shapes_and_effective_dating(session, result)
            _test_invalid_rules_rejected(session, result)
        finally:
            session.rollback()
    return result


def _expect_integrity_error(session: Session, build_row: "m.OvertimeRule") -> bool:
    """Adds `build_row` inside a nested SAVEPOINT, expecting `IntegrityError`
    on flush. Rolls back only the savepoint either way, so the outer
    validation transaction is never aborted. Returns True iff the expected
    error occurred (mirrors `organization_validation.py`'s
    `_expect_integrity_error` helper)."""
    savepoint = session.begin_nested()
    raised = False
    try:
        session.add(build_row)
        session.flush()
    except IntegrityError:
        raised = True
    finally:
        savepoint.rollback()
    return raised


# ---------------------------------------------------------------------------
# A/B/C/D/E/F. Representative, materially-different rule shapes can be
# persisted, including effective dating and historical versioning by
# distinct rule_code.
# ---------------------------------------------------------------------------


def _test_representative_rule_shapes_and_effective_dating(
    session: Session, result: ValidationResult
) -> None:
    # A/B — Federal weekly (task §17.A).
    federal_weekly = m.OvertimeRule(
        rule_code="US_FLSA_WEEKLY_OT",
        name="FLSA Federal Weekly Overtime",
        jurisdiction_level="FEDERAL",
        jurisdiction_code="US",
        rule_scope="WORKWEEK",
        threshold_hours=Decimal("40"),
        total_rate_multiplier=Decimal("1.50"),
        regular_rate_method="WEIGHTED_REGULAR_RATE",
        overlap_method="INDEPENDENT",
        effective_from=datetime(2020, 1, 1, tzinfo=UTC),
        status="ACTIVE",
    )
    session.add(federal_weekly)
    session.flush()
    result.check(
        "Federal WORKWEEK rule (US_FLSA_WEEKLY_OT, threshold_hours=40, multiplier=1.5) can be persisted",
        federal_weekly.id is not None
        and federal_weekly.rule_scope == "WORKWEEK"
        and federal_weekly.threshold_hours == Decimal("40")
        and federal_weekly.total_rate_multiplier == Decimal("1.50"),
    )

    # C — California daily overtime (task §17.B).
    ca_daily_ot = m.OvertimeRule(
        rule_code="CA_DAILY_OT_8",
        name="California Daily Overtime (8h)",
        jurisdiction_level="STATE",
        jurisdiction_code="CA",
        rule_scope="WORKDAY",
        threshold_hours=Decimal("8"),
        total_rate_multiplier=Decimal("1.50"),
        regular_rate_method="WEIGHTED_REGULAR_RATE",
        overlap_method="NON_STACKING_MAXIMUM",
        effective_from=datetime(2020, 1, 1, tzinfo=UTC),
        status="ACTIVE",
    )
    session.add(ca_daily_ot)
    session.flush()
    result.check(
        "California WORKDAY 8-hour / 1.5 rule (CA_DAILY_OT_8) can be persisted",
        ca_daily_ot.id is not None
        and ca_daily_ot.rule_scope == "WORKDAY"
        and ca_daily_ot.threshold_hours == Decimal("8")
        and ca_daily_ot.total_rate_multiplier == Decimal("1.50"),
    )

    # D — California daily double time (task §17.C).
    ca_daily_dt = m.OvertimeRule(
        rule_code="CA_DAILY_DT_12",
        name="California Daily Double Time (12h)",
        jurisdiction_level="STATE",
        jurisdiction_code="CA",
        rule_scope="WORKDAY",
        threshold_hours=Decimal("12"),
        total_rate_multiplier=Decimal("2.00"),
        regular_rate_method="WEIGHTED_REGULAR_RATE",
        overlap_method="NON_STACKING_MAXIMUM",
        effective_from=datetime(2020, 1, 1, tzinfo=UTC),
        status="ACTIVE",
    )
    session.add(ca_daily_dt)
    session.flush()
    result.check(
        "California WORKDAY 12-hour / 2.0 rule (CA_DAILY_DT_12) can be persisted",
        ca_daily_dt.id is not None
        and ca_daily_dt.rule_scope == "WORKDAY"
        and ca_daily_dt.threshold_hours == Decimal("12")
        and ca_daily_dt.total_rate_multiplier == Decimal("2.00"),
    )

    # A seventh-consecutive-day-style rule, to prove CONSECUTIVE_DAY /
    # threshold_day_number can also be represented (task §6).
    seventh_day = m.OvertimeRule(
        rule_code="CA_SEVENTH_DAY_OT",
        name="California Seventh Consecutive Day Overtime",
        jurisdiction_level="STATE",
        jurisdiction_code="CA",
        rule_scope="CONSECUTIVE_DAY",
        threshold_day_number=7,
        total_rate_multiplier=Decimal("1.50"),
        regular_rate_method="WEIGHTED_REGULAR_RATE",
        overlap_method="NON_STACKING_MAXIMUM",
        effective_from=datetime(2020, 1, 1, tzinfo=UTC),
        status="ACTIVE",
    )
    session.add(seventh_day)
    session.flush()
    result.check(
        "a CONSECUTIVE_DAY rule (threshold_day_number=7) can be persisted",
        seventh_day.id is not None
        and seventh_day.rule_scope == "CONSECUTIVE_DAY"
        and seventh_day.threshold_day_number == 7,
    )

    # E/F — effective dates persist, and two effective-dated "versions" of a
    # conceptual rule remain historically represented as distinct rows under
    # distinct rule_code values (no version column — task §17, model
    # docstring), closing the prior row's effective_to rather than
    # overwriting it.
    federal_weekly.effective_to = datetime(2023, 12, 31, tzinfo=UTC)
    session.flush()
    federal_weekly_v2 = m.OvertimeRule(
        rule_code="US_FLSA_WEEKLY_OT_2024",
        name="FLSA Federal Weekly Overtime (2024 revision)",
        jurisdiction_level="FEDERAL",
        jurisdiction_code="US",
        rule_scope="WORKWEEK",
        threshold_hours=Decimal("40"),
        total_rate_multiplier=Decimal("1.50"),
        regular_rate_method="WEIGHTED_REGULAR_RATE",
        overlap_method="INDEPENDENT",
        effective_from=datetime(2024, 1, 1, tzinfo=UTC),
        status="ACTIVE",
    )
    session.add(federal_weekly_v2)
    session.flush()

    reloaded_v1 = session.get(m.OvertimeRule, federal_weekly.id)
    result.check(
        "effective_from/effective_to persist, and a later conceptual revision is stored as a "
        "distinct rule_code row rather than overwriting the closed historical row",
        reloaded_v1.effective_from == datetime(2020, 1, 1, tzinfo=UTC)
        and reloaded_v1.effective_to == datetime(2023, 12, 31, tzinfo=UTC)
        and reloaded_v1.rule_code == "US_FLSA_WEEKLY_OT"
        and federal_weekly_v2.rule_code == "US_FLSA_WEEKLY_OT_2024"
        and federal_weekly_v2.effective_from == datetime(2024, 1, 1, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# G/H/I/J/K. Invalid rows are rejected.
# ---------------------------------------------------------------------------


def _test_invalid_rules_rejected(session: Session, result: ValidationResult) -> None:
    def base_kwargs(**overrides) -> dict:
        kwargs = dict(
            rule_code=f"TEST_INVALID_{overrides.get('_suffix', 'X')}",
            name="Invalid Test Rule",
            jurisdiction_level="FEDERAL",
            jurisdiction_code="US",
            rule_scope="WORKWEEK",
            threshold_hours=Decimal("40"),
            total_rate_multiplier=Decimal("1.50"),
            regular_rate_method="WEIGHTED_REGULAR_RATE",
            overlap_method="INDEPENDENT",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            status="ACTIVE",
        )
        overrides.pop("_suffix", None)
        kwargs.update(overrides)
        return kwargs

    result.check(
        "a total_rate_multiplier < 1 is rejected",
        _expect_integrity_error(
            session, m.OvertimeRule(**base_kwargs(_suffix="MULT", total_rate_multiplier=Decimal("0.90")))
        ),
    )
    result.check(
        "a negative threshold_hours is rejected",
        _expect_integrity_error(
            session, m.OvertimeRule(**base_kwargs(_suffix="HOURS", threshold_hours=Decimal("-1")))
        ),
    )
    result.check(
        "a threshold_day_number <= 0 is rejected",
        _expect_integrity_error(
            session,
            m.OvertimeRule(
                **base_kwargs(
                    _suffix="DAYNUM", rule_scope="CONSECUTIVE_DAY", threshold_hours=None,
                    threshold_day_number=0,
                )
            ),
        ),
    )
    result.check(
        "an effective_to before effective_from is rejected",
        _expect_integrity_error(
            session,
            m.OvertimeRule(
                **base_kwargs(
                    _suffix="RANGE",
                    effective_from=datetime(2026, 6, 1, tzinfo=UTC),
                    effective_to=datetime(2026, 1, 1, tzinfo=UTC),
                )
            ),
        ),
    )
    result.check(
        "an invalid jurisdiction_level value is rejected",
        _expect_integrity_error(
            session, m.OvertimeRule(**base_kwargs(_suffix="JURIS", jurisdiction_level="COUNTY"))
        ),
    )
    result.check(
        "an invalid rule_scope value is rejected",
        _expect_integrity_error(
            session, m.OvertimeRule(**base_kwargs(_suffix="SCOPE", rule_scope="MONTHLY"))
        ),
    )
    result.check(
        "an invalid regular_rate_method value is rejected",
        _expect_integrity_error(
            session,
            m.OvertimeRule(**base_kwargs(_suffix="RRM", regular_rate_method="AVERAGE_RATE")),
        ),
    )
    result.check(
        "an invalid overlap_method value is rejected",
        _expect_integrity_error(
            session, m.OvertimeRule(**base_kwargs(_suffix="OVERLAP", overlap_method="ADDITIVE"))
        ),
    )
    result.check(
        "an invalid status value is rejected",
        _expect_integrity_error(
            session, m.OvertimeRule(**base_kwargs(_suffix="STATUS", status="DRAFT"))
        ),
    )
    # US_FLSA_WEEKLY_OT was created by
    # `_test_representative_rule_shapes_and_effective_dating`, which
    # `run_validation` always runs first in this same session.
    result.check(
        "a duplicate rule_code is rejected",
        _expect_integrity_error(
            session,
            m.OvertimeRule(**base_kwargs(_suffix="DUPE", rule_code="US_FLSA_WEEKLY_OT")),
        ),
    )
