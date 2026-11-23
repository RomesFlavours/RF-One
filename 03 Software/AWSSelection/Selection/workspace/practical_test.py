"""Practical selection test: the last check of Selection before Send to Training.

Pino's rule (20 and 23 Nov 2026): Tatiana's approval must be based on the
practical selection test, and the candidate must also demonstrate knowledge
of the Menu and the FAQs. It does not have to be the candidate's last step.

Each result is a new row (append-only); the newest one counts. Send to Training
is refused unless the newest result is Approved. Candidates already sent to
Training are not affected.

The table is new and Selection-only: `schema.provision` creates it (no Alembic
change), like the other selection_workspace_ tables.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from rfone_data_store.models import Base
from rfone_data_store.selection import workspace_models as ps

APPROVED = "APPROVED"
NOT_APPROVED = "NOT_APPROVED"
RESULT_LABELS = {APPROVED: "Approved", NOT_APPROVED: "Not approved"}
MAX_NOTE = 2000


class PracticalTest(Base):
    __tablename__ = "selection_workspace_practical_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("selection_workspace_position_candidates.id"), nullable=False, index=True)
    test_date: Mapped[date] = mapped_column(Date, nullable=False)
    evaluator_name: Mapped[str] = mapped_column(String(255), nullable=False)    # who ran the test (Tatiana)
    result: Mapped[str] = mapped_column(String(16), nullable=False)             # APPROVED | NOT_APPROVED
    menu_faq_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)                     # attitude and behaviour
    recorded_by_account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_by_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False, default=ps.utcnow)


def history(db, pc_id):
    return list(db.scalars(select(PracticalTest).where(PracticalTest.position_candidate_id == pc_id)
                           .order_by(PracticalTest.id.desc())).all())


def current(db, pc_id):
    rows = history(db, pc_id)
    return rows[0] if rows else None


def approved(db, pc_id) -> bool:
    row = current(db, pc_id)
    return row is not None and row.result == APPROVED and row.menu_faq_ok


def validate(*, test_date: str, evaluator: str, result: str, menu_faq_ok: bool, note: str, today: date):
    """Returns (values, error). The error is a sentence for the page."""
    try:
        when = date.fromisoformat((test_date or "").strip())
    except ValueError:
        return None, "Enter the date of the practical test."
    if when > today:
        return None, "The practical test date can't be in the future."
    evaluator = (evaluator or "").strip()
    note = (note or "").strip()
    if not evaluator:
        return None, "Enter who ran the practical test."
    if result not in RESULT_LABELS:
        return None, "Choose Approved or Not approved."
    if not note:
        return None, "Add a short note on attitude and behaviour during the test."
    if len(note) > MAX_NOTE or len(evaluator) > 255:
        return None, "The note is too long."
    if result == APPROVED and not menu_faq_ok:
        return None, "Approved needs the Menu and FAQs box ticked: the candidate must demonstrate both."
    return {"test_date": when, "evaluator_name": evaluator, "result": result,
            "menu_faq_ok": bool(menu_faq_ok), "note": note}, None


def record(db, *, position, pc, actor, values, candidate_name):
    row = PracticalTest(position_candidate_id=pc.id, recorded_by_account_id=actor.id,
                        recorded_by_name=actor.name, **values)
    db.add(row)
    menu = "Menu and FAQs demonstrated" if values["menu_faq_ok"] else "Menu and FAQs not demonstrated"
    ps.log_event(db, position_id=position.id, position_candidate_id=pc.id, kind="PRACTICAL_TEST",
                 detail=(f"{candidate_name}: practical selection test {RESULT_LABELS[values['result']].lower()} "
                         f"by {values['evaluator_name']} on {values['test_date'].isoformat()}. {menu}. "
                         f"Note: {values['note']}"),
                 actor_id=actor.id, actor_name=actor.name)
    return row
