"""Persistent interview sessions, independent of any particular industry."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..models import Base


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('REQUESTED', 'IN_PROGRESS', 'COMPLETED')", name="ck_interview_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False, index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False, index=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("candidate_persons.id", name="fk_interview_person"), nullable=True, index=True)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    specialization: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transcript: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    results: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
