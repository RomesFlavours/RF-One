"""Versioned configuration and durable, per-action procedure executions."""
from datetime import datetime
from sqlalchemy import String,Integer,JSON,DateTime,ForeignKey,UniqueConstraint,func
from sqlalchemy.orm import Mapped,mapped_column
from rfone_data_store.models import Base

class AutomationItem(Base):
    __tablename__='selection_workspace_automation_items'
    code: Mapped[str]=mapped_column(String(64),primary_key=True)
    kind: Mapped[str]=mapped_column(String(16),nullable=False)
    version: Mapped[int]=mapped_column(Integer,nullable=False)
    # Legacy storage name; contains only the current configuration, no history.
    revisions: Mapped[list]=mapped_column(JSON,nullable=False)

class ActionRun(Base):
    __tablename__='selection_workspace_action_runs'
    __table_args__=(UniqueConstraint('position_candidate_id','action_code',name='uq_candidate_automation_action'),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    position_candidate_id: Mapped[int]=mapped_column(ForeignKey('selection_workspace_position_candidates.id'),nullable=False,index=True)
    action_code: Mapped[str]=mapped_column(ForeignKey(AutomationItem.code),nullable=False)
    action_snapshot: Mapped[dict]=mapped_column(JSON,nullable=False)
    procedure_snapshot: Mapped[dict]=mapped_column(JSON,nullable=False)
    status: Mapped[str]=mapped_column(String(16),nullable=False)
    steps: Mapped[list]=mapped_column(JSON,nullable=False)
    attempts: Mapped[list]=mapped_column(JSON,nullable=False)
    error: Mapped[str|None]=mapped_column(String(500),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime,nullable=False,server_default=func.now())
    completed_at: Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
