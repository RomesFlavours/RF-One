"""Minimal, standalone Legal Entity management service.

`LegalEntity` is the canonical juridical/employing entity (`01 Domains/
Cross Domain/Personnel Management/Compensation/
COMPENSATION_AND_INCOME_COMPOSITION_001.md` §3) — never Restaurant, Brand,
or Corporate. This service is deliberately separate from Compensation:
Compensation only ever reads existing `LegalEntity` rows (to scope a
`CompensationPreparationRun`); this is the one place that creates/updates
them. Lives at the top level of `rfone_data_store`, not inside any Domain
package, mirroring `rfone_account_service.py`'s own placement (Core
Principle 21: no Domain owns an independent identity/authority mechanism —
Legal Entity is a cross-cutting structural concept, not Compensation's
own).

This is intentionally minimal — name and status only, matching the
`LegalEntity` model's own current, deliberately narrow field set (no tax
ID/EIN, payroll-provider, or ownership field — see that model's own
docstring in `models.py`)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m

VALID_STATUSES = ("ACTIVE", "INACTIVE")


def list_legal_entities(session: Session) -> list[m.LegalEntity]:
    return list(session.scalars(select(m.LegalEntity).order_by(m.LegalEntity.legal_name)).all())


def get_legal_entity(session: Session, legal_entity_id: int) -> m.LegalEntity | None:
    return session.get(m.LegalEntity, legal_entity_id)


def _validate(legal_name: str, status: str) -> str:
    legal_name = (legal_name or "").strip()
    if not legal_name:
        raise ValueError("Legal Entity name is required.")
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status {status!r} — expected one of {VALID_STATUSES}.")
    return legal_name


def create_legal_entity(session: Session, *, legal_name: str, status: str = "ACTIVE") -> m.LegalEntity:
    legal_name = _validate(legal_name, status)
    entity = m.LegalEntity(legal_name=legal_name, status=status)
    session.add(entity)
    session.flush()
    return entity


def update_legal_entity(
    session: Session, entity: m.LegalEntity, *, legal_name: str, status: str,
) -> m.LegalEntity:
    legal_name = _validate(legal_name, status)
    entity.legal_name = legal_name
    entity.status = status
    session.flush()
    return entity
