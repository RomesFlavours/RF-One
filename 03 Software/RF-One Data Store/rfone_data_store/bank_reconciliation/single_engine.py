"""One reconciliation engine (Bank unification Phase 3A, BANK_UNIFICATION_PHASE3_PLAN_001 §5).

When the process enables it (`RFONE_BANK_SINGLE_ENGINE=1`, set by "Avvia Bank"), the engine of
`cbank/engine.py` is the ONLY automatic reconciliation: it records its results in `bank_engine_results`
and its matches in `financial_transaction_matches`. The old automatic paths are switched off, their code
kept:

* classification during the CSV import (operative AI rules, two-pass planner) — `ai_rule_operations`;
* the automatic transfer match at import — `matching.on_financial_transaction_acquired`;
* the background import worker and the WHO identification worker — RF-One Web;
* AI rule / profile "Apply" to transactions and the legacy reconciliation runs.

`install()` adds the safety net behind those switches: with the single engine on, a NEW decision row
(`bank_transaction_explanations` / `bank_transaction_allocations`) that does not come from a person is
refused, whatever path tries to write it. Human decisions (`decision_source` HUMAN) stay available and
protected. A rollback of an earlier application restores rows it recorded and is allowed
(`session.info["bank_restore"] = True`).

Off (tests, other deployments): nothing changes.
"""

from __future__ import annotations

import os

from sqlalchemy import event
from sqlalchemy.orm import Session

from .. import models as m

MESSAGE = ("The old automatic reconciliation is switched off: the single engine (Guided Reconciliation) "
           "reconciles automatically. Human decisions remain available.")


class LegacyEngineDisabled(ValueError):
    pass


def enabled() -> bool:
    return os.environ.get("RFONE_BANK_SINGLE_ENGINE") == "1"


def refuse(what: str) -> None:
    """For a legacy automatic action a person starts (Apply, run): a clear refusal, nothing written."""
    if enabled():
        raise LegacyEngineDisabled(f"{what}: {MESSAGE}")


def _before_flush(session: Session, flush_context, instances) -> None:
    if not enabled() or session.info.get("bank_restore"):
        return
    for obj in session.new:
        if isinstance(obj, (m.BankTransactionExplanation, m.BankTransactionAllocation)) \
                and (obj.decision_source or "") != "HUMAN":
            raise LegacyEngineDisabled(f"Automatic {obj.__tablename__} write refused: {MESSAGE}")


def install() -> None:
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)
