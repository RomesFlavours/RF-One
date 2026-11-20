"""Tips Validation Mode — MANUAL vs AUTOMATIC
(TIPS_FINALIZED_PERIOD_CALCULATION_AND_REPORT_001 §16).

A Restaurant-scoped setting answering ONE question: may a calculated Tips
period become definitive without a person validating it?

  MANUAL     no. A human identified through the RF-One login (§15) must
             validate the period first. THE DEFAULT, in every direction.
  AUTOMATIC  yes, provided the single monetary control of §11 passes.

§16 asked for a SEPARATE configuration and explicitly forbade reusing an
existing setting that already means something else. The candidate it would
have been reused from is `TipsCalculationScheduleConfig.review_mode`, whose
own AUDIT/AUTOMATIC values decide "which report the UI puts in front of the
operator after a calculation" (`tips/review_mode_service.py` — a purely
presentational toggle, by its own docstring). Those two AUTOMATICs mean
nothing like each other: one skips a report, the other skips a human
approving money. Sharing the column would have made a UI preference quietly
finalize payroll.

So this module owns its own table (`TipsValidationModeConfig`) and nothing
else reads or writes it. The two services are unrelated by design, and a
Restaurant may sit on any combination of the two.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

UTC = timezone.utc


def get_config(session: Session, *, restaurant_id: int) -> "m.TipsValidationModeConfig | None":
    """The Restaurant's configuration row, or `None` if it has never been
    set. `None` is a meaningful answer here, not a missing one — see
    `get_validation_mode`."""
    return session.scalars(
        select(m.TipsValidationModeConfig).where(
            m.TipsValidationModeConfig.restaurant_id == restaurant_id
        )
    ).first()


def get_validation_mode(session: Session, *, restaurant_id: int) -> str:
    """The Restaurant's current Validation Mode.

    Defaults to MANUAL whenever no configuration row exists. This default
    is the safe direction and it is deliberately the ONLY direction a
    default ever goes: nothing in Tips resolves to AUTOMATIC by omission,
    by inheritance from another Restaurant, or by falling back from an
    unreadable value. Finalizing money without a person is only ever the
    result of somebody explicitly choosing it."""
    config = get_config(session, restaurant_id=restaurant_id)
    if config is None or config.validation_mode not in m.TIPS_VALIDATION_MODES:
        return m.TIPS_VALIDATION_MODE_MANUAL
    return config.validation_mode


def is_automatic(session: Session, *, restaurant_id: int) -> bool:
    return get_validation_mode(session, restaurant_id=restaurant_id) == (
        m.TIPS_VALIDATION_MODE_AUTOMATIC
    )


def set_validation_mode(
    session: Session, *, restaurant_id: int, validation_mode: str,
    updated_by_account_id: int | None = None,
) -> m.TipsValidationModeConfig:
    """Set the Restaurant's Validation Mode, creating the row on first use.

    Rejects any value outside the closed vocabulary with a `ValueError`
    rather than storing it and letting `get_validation_mode` quietly read
    it back as MANUAL — a setting that does not take effect must fail
    loudly, not appear to have been accepted.

    `updated_by_account_id` is an `RFOneAccount` id (§15). Switching a
    Restaurant to AUTOMATIC means deciding that nobody will sign off its
    payroll figures, which is exactly the kind of decision that should
    carry a name."""
    if validation_mode not in m.TIPS_VALIDATION_MODES:
        raise ValueError(
            f"Unknown Tips Validation Mode {validation_mode!r}; expected one of "
            f"{', '.join(repr(x) for x in m.TIPS_VALIDATION_MODES)}"
        )
    config = get_config(session, restaurant_id=restaurant_id)
    if config is None:
        config = m.TipsValidationModeConfig(restaurant_id=restaurant_id)
        session.add(config)
    config.validation_mode = validation_mode
    config.updated_by_account_id = updated_by_account_id
    config.updated_at = datetime.now(UTC)
    session.flush()
    return config
