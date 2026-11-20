"""One editable interview observation template per job role and workplace."""
from sqlalchemy import Integer, String, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from rfone_data_store.models import Base


class ObservationTemplate(Base):
    __tablename__ = 'selection_workspace_observation_templates'
    __table_args__ = (UniqueConstraint('role_code', 'location_key', name='uq_observations_role_location'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    location_key: Mapped[str] = mapped_column(String(200), nullable=False)
    location_label: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    items: Mapped[list] = mapped_column(JSON, nullable=False)

