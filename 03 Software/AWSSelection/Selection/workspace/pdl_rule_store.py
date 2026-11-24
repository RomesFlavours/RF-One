"""Confirmed requirements/priority rules, owned by a configured PDL."""
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, func, select, inspect, text
from sqlalchemy.orm import Mapped, mapped_column
from rfone_data_store.models import Base
from .role_catalog import JobRole


class PDLRule(Base):
    __tablename__ = "selection_workspace_pdl_rules"
    __table_args__ = (
        CheckConstraint("section IN ('requirements','priorities')", name="ck_pdl_rule_section"),
        CheckConstraint("weight BETWEEN 1 AND 100", name="ck_pdl_rule_weight"),
        CheckConstraint("overrides_rule_id IS NULL OR role_code IS NOT NULL",name="ck_pdl_rule_override_scope"),
        Index("ix_pdl_rule_role_section", "role_code", "section"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_code: Mapped[str] = mapped_column(ForeignKey(JobRole.code), nullable=True)
    overrides_rule_id: Mapped[int|None] = mapped_column(ForeignKey("selection_workspace_pdl_rules.id"),nullable=True)
    section: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    condition: Mapped[dict] = mapped_column(JSON, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    conversation: Mapped[list] = mapped_column(JSON, nullable=False)
    proposal_key: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def initialize(engine):
    """Explicit, additive local setup; never a production/AWS migration."""
    if engine.dialect.name != "sqlite" and (engine.url.host, engine.url.port, engine.url.database) != ("127.0.0.1", 55436, "rfone_aws_copy"):
        raise RuntimeError("PDL rules setup requires the canonical local database.")
    PDLRule.__table__.create(engine, checkfirst=True)
    columns={c['name']:c for c in inspect(engine).get_columns(PDLRule.__tablename__)}
    with engine.begin() as db:
        if not columns['role_code']['nullable']:
            if engine.dialect.name!='postgresql':raise RuntimeError('Upgrade requires PostgreSQL or a fresh disposable SQLite database.')
            db.execute(text('ALTER TABLE selection_workspace_pdl_rules ALTER COLUMN role_code DROP NOT NULL'))
        if 'overrides_rule_id' not in columns:
            db.execute(text('ALTER TABLE selection_workspace_pdl_rules ADD COLUMN overrides_rule_id INTEGER NULL REFERENCES selection_workspace_pdl_rules(id)'))
        db.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_pdl_active_override ON selection_workspace_pdl_rules (role_code,overrides_rule_id) WHERE is_active AND overrides_rule_id IS NOT NULL'))


def list_rules(db, code):
    return list(db.scalars(select(PDLRule).where(PDLRule.role_code == code).order_by(PDLRule.id)))


def is_natural(rule):
    return isinstance(rule.condition,dict) and rule.condition.get('op')=='natural_language'


def effective(db,code):
    rows=list(db.scalars(select(PDLRule).where(PDLRule.is_active.is_(True),
        (PDLRule.role_code.is_(None)) | (PDLRule.role_code==code)).order_by(PDLRule.id)))
    general=[r for r in rows if r.role_code is None and is_natural(r)]
    local=[r for r in rows if r.role_code==code and code is not None and is_natural(r)]
    overrides={r.overrides_rule_id:r for r in local if r.overrides_rule_id is not None}
    return [overrides.get(r.id,r) for r in general]+[r for r in local if r.overrides_rule_id is None]


def entries(db,code):
    if code is None:
        return [{'rule':r,'origin':'Generale','base':None} for r in list_rules(db,None) if is_natural(r)]
    roots={r.id:r for r in list_rules(db,None)}
    return [{'rule':r,'origin':'Generale' if r.role_code is None else 'Generale modificata' if r.overrides_rule_id else 'Specifica',
        'base':roots.get(r.overrides_rule_id)} for r in effective(db,code)]


def validate_target(db,code,target_id,*,lock=False):
    if target_id is None:return None
    if code is None or type(target_id) is not int:raise ValueError('Solo una PDL specifica può sostituire una regola generale.')
    query=select(PDLRule).where(PDLRule.id==target_id)
    if lock:query=query.with_for_update()
    target=db.scalar(query)
    if not target or target.role_code is not None or not target.is_active or not is_natural(target):raise ValueError('La regola generale da sostituire non è attiva o non esiste.')
    return target
