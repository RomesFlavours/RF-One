"""AI Consistency Review — service BOUNDARY only (TASK_ORG_CHART_ADMIN_PAGE
§16).

Task §16 is explicit about what is and is not authorized here: "NON
implementare una AI generale se richiede nuovo runtime... Se oggi è
possibile usare in modo pulito l'infrastruttura AI esistente, è consentito
creare un test/admin analysis service. Altrimenti creare solo: dati
strutturati; service boundary; test harness."

This repository DOES have one existing LLM abstraction
(`rfone_data_store.selection.parsing.ai_client.generate_json`), but it is
Selection-Domain-owned code (its own docstring: "No such abstraction exists
yet elsewhere in the repository... this is the first one" — i.e. never
promoted to shared/cross-Domain status). Importing a Domain's internal
module from this cross-Domain Foundation would invert the dependency
direction every other module in this Foundation deliberately avoids (no
Domain package is imported anywhere else here either) — so this is treated
as "no clean, existing, shared AI infrastructure to call," per task §16's
own fallback instruction. NOTHING here calls any AI provider.

What this module DOES provide: a structured request payload built entirely
from `organizational_coverage_check_service`'s own output — exactly the
"scope incompleti, ownership mancanti, sovrapposizioni, responsabilità
senza backup, trigger scoperti" data a future Cognito/AI capability would
need — so that capability, once it exists, only has to consume this
function's output, never re-derive it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session

from . import organizational_coverage_check_service as coverage_svc


class AIConsistencyReviewNotAvailable(Exception):
    """Raised by `run_ai_consistency_review` — always, today. No shared,
    cross-Domain AI infrastructure exists to call (see module docstring).
    Callers must not treat this as an error to work around; it is the
    correct, honest current state."""


@dataclass(frozen=True)
class AIConsistencyReviewRequest:
    """The exact structured payload a future Cognito/AI consistency-review
    capability would receive — built once here so that capability's own
    future implementation does not need to re-derive it from raw tables."""

    coverage_summary: dict
    gaps: list[dict]
    positions_missing_required_backup: list[dict]
    unresolved_attention_items: list[dict]


def build_ai_consistency_review_request(session: Session) -> AIConsistencyReviewRequest:
    """PREPARED FOR COGNITO — pure data assembly, no AI call. Safe to call
    today (e.g. from the ADMIN/TEST harness) to inspect exactly what a
    future AI reviewer would see."""
    result = coverage_svc.run_organizational_coverage_check(session)
    gaps = [
        {
            "domain": e.domain, "module": e.module, "process_name": e.process_name, "phase": e.phase,
            "status": e.status, "detail": e.detail,
            "owner_position": e.owner_position.name if e.owner_position else None,
        }
        for e in result.entries if e.status != coverage_svc.STATUS_FULLY_COVERED
    ]
    return AIConsistencyReviewRequest(
        coverage_summary=result.counts,
        gaps=gaps,
        positions_missing_required_backup=[{"id": p.id, "name": p.name} for p in result.positions_missing_required_backup],
        unresolved_attention_items=[
            {"id": a.id, "priority": a.priority, "reason": a.reason} for a in result.unresolved_attention_items
        ],
    )


def run_ai_consistency_review(session: Session) -> AIConsistencyReviewRequest:
    """NOT YET IMPLEMENTED. Raises `AIConsistencyReviewNotAvailable`
    unconditionally — see module docstring for why. Kept as a distinct
    function (rather than only `build_ai_consistency_review_request`) so a
    future implementation's call sites (the ADMIN/TEST harness included)
    already exist and only need this one function's body replaced."""
    raise AIConsistencyReviewNotAvailable(
        "No shared, cross-Domain AI infrastructure exists yet for this Foundation to call. "
        "build_ai_consistency_review_request() can still be used to inspect the structured payload "
        "a future Cognito/AI reviewer would receive."
    )
