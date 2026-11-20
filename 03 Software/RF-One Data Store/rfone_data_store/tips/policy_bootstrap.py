"""Shared Tip source-evidence helper.

TIPS_LEGACY_ENGINE_RETIREMENT_001: this module used to also host the legacy
`TipPolicy`/`TipPolicyComponent` configuration-bootstrap write path
(`configure_location_tip_policy`/`ComponentSpec`/`PolicyBootstrapResult`),
used only by the now-retired `configure_rome_flavours_tip_policy.py` CLI and
the now-retired `tips/engine.py`. That write path has been removed — the
canonical Tip Distribution Engine (`tips/distribution_engine.py`) reads
`TipDistributionRule`/`TipDistributionRuleVersion` (`tips/
distribution_rule_service.py`) instead, never `TipPolicy`. Only
`earliest_tip_evidence_at` remains: a generic, engine-agnostic fact query
still used by `seed_tip_distribution_rules.py` to derive a Rule's
`effective_from` from real Tip evidence.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m


def earliest_tip_evidence_at(session: Session, *, location_id: int) -> datetime | None:
    """The earliest `Payment.created_at` for which a real `PaymentTip` (with
    a non-null amount) exists at this Location — the earliest instant a
    configuration covering this Location could legitimately apply to any
    real evidence. Returns `None` when no such evidence exists yet (e.g. a
    Location with no recorded Tips at all)."""
    return session.scalar(
        select(m.Payment.created_at)
        .join(m.Order, m.Order.id == m.Payment.order_id)
        .join(m.PaymentTip, m.PaymentTip.payment_id == m.Payment.id)
        .where(
            m.Order.location_id == location_id,
            m.PaymentTip.amount.is_not(None),
        )
        .order_by(m.Payment.created_at.asc())
        .limit(1)
    )
