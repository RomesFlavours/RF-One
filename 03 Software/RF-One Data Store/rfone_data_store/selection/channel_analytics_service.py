"""Channel / Publication / Variant analytics (Task 5E Part F). Pure
read-only aggregation over data every other Task 5E/5D/5A service already
produces — never writes anything, never touches a live Publication/budget
(task §33's own "advisory only... do NOT automatically alter budget or
publications"). Cost metrics stay `None` whenever cost data is unavailable
(task §32) — never fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import missing_evidence_service as me_svc
from .core import job_posting_model as jpm
from .core import stage_model as stgm


@dataclass
class ChannelFunnelMetrics:
    publication_id: int
    channel_name: str
    placement_label: str
    job_posting_id: int
    variant_id: int
    variant_version: int
    session_id: int
    applications: int = 0
    passed_primary_screening: int = 0
    ready_for_phone_review: int = 0
    advanced_to_phone: int = 0
    phone_interview_reached: int = 0
    in_person_reached: int = 0
    hirable: int = 0
    cost_amount_cents: int | None = None
    cost_currency: str | None = None

    @property
    def cost_per_application(self) -> float | None:
        if self.cost_amount_cents is None or self.applications == 0:
            return None
        return self.cost_amount_cents / self.applications

    @property
    def cost_per_ready_for_phone_review(self) -> float | None:
        if self.cost_amount_cents is None or self.ready_for_phone_review == 0:
            return None
        return self.cost_amount_cents / self.ready_for_phone_review

    @property
    def cost_per_advance_to_phone(self) -> float | None:
        if self.cost_amount_cents is None or self.advanced_to_phone == 0:
            return None
        return self.cost_amount_cents / self.advanced_to_phone

    @property
    def cost_per_hirable(self) -> float | None:
        if self.cost_amount_cents is None or self.hirable == 0:
            return None
        return self.cost_amount_cents / self.hirable


def _application_reached_hirable(session: Session, application_id: int) -> bool:
    """Matches by name, the same honest, established convention
    `dossier_service._training_check_flags` already uses for a comparable
    "no dedicated boolean flag exists" situation — RF-One seeds its own
    example Outcome as "Hirable" (`industry/restaurant_templates.py`), a
    restaurant may rename it, so this is a best-effort signal, not an
    architectural guarantee."""

    stmt = (
        select(m.SelectionOutcomeDecision)
        .join(
            m.SelectionOutcomeDefinitionSnapshot,
            m.SelectionOutcomeDecision.outcome_definition_snapshot_id == m.SelectionOutcomeDefinitionSnapshot.id,
        )
        .where(m.SelectionOutcomeDecision.application_id == application_id)
    )
    return any("hirable" in (d.outcome_definition_snapshot.name or "").lower() for d in session.scalars(stmt).all())


def _application_ever_advanced_to_phone(session: Session, application_id: int) -> bool:
    stmt = select(m.ApplicationStageTransition).where(
        m.ApplicationStageTransition.application_id == application_id,
        m.ApplicationStageTransition.new_stage == stgm.PHONE_INTERVIEW,
    )
    return session.scalars(stmt).first() is not None


def _application_ever_advanced_to_in_person(session: Session, application_id: int) -> bool:
    stmt = select(m.ApplicationStageTransition).where(
        m.ApplicationStageTransition.application_id == application_id,
        m.ApplicationStageTransition.new_stage == stgm.IN_PERSON_PRACTICAL,
    )
    return session.scalars(stmt).first() is not None


def get_channel_funnel_metrics(
    session: Session, *, restaurant_id: int | None = None, session_id: int | None = None,
) -> list[ChannelFunnelMetrics]:
    """Task §31/§32 — one row per Publication/placement (never collapsed
    across placements — task 5D's own "do not collapse all Facebook
    traffic into one generic source" principle, extended here to metrics).
    `future READY FOR TRAINING`/`HIRED` are deliberately absent — task's
    own "do not require future-domain states to exist now"."""

    stmt = select(m.ChannelPublication)
    publications = list(session.scalars(stmt).all())

    rows: list[ChannelFunnelMetrics] = []
    for publication in publications:
        variant_version = session.get(m.JobPostingChannelVariantVersion, publication.variant_version_id)
        variant = session.get(m.JobPostingChannelVariant, variant_version.variant_id)
        job_posting = session.get(m.JobPosting, variant.job_posting_id)
        if restaurant_id is not None and job_posting.restaurant_id != restaurant_id:
            continue
        if session_id is not None and job_posting.session_id != session_id:
            continue
        channel = session.get(m.ChannelDefinition, publication.channel_id)

        applications = list(session.scalars(
            select(m.Application).where(m.Application.channel_publication_id == publication.id)
        ).all())

        row = ChannelFunnelMetrics(
            publication_id=publication.id, channel_name=channel.name if channel else "(unknown)",
            placement_label=publication.placement_label, job_posting_id=job_posting.id, variant_id=variant.id,
            variant_version=variant_version.version, session_id=job_posting.session_id,
            applications=len(applications), cost_amount_cents=publication.cost_amount_cents,
            cost_currency=publication.cost_currency,
        )
        for application in applications:
            run = session.scalars(
                select(m.PrimaryScreeningRun).where(m.PrimaryScreeningRun.application_id == application.id)
                .order_by(m.PrimaryScreeningRun.id.desc())
            ).first()
            if run is not None and not run.has_active_hard_disqualifier:
                row.passed_primary_screening += 1
            if me_svc.is_ready_for_phone_review(session, application.id):
                row.ready_for_phone_review += 1
            if _application_ever_advanced_to_phone(session, application.id):
                row.advanced_to_phone += 1
                row.phone_interview_reached += 1
            if _application_ever_advanced_to_in_person(session, application.id):
                row.in_person_reached += 1
            if _application_reached_hirable(session, application.id):
                row.hirable += 1
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Advisory recommendations (task §33/§34) — a simple, transparent heuristic;
# never a statistical model, never a write.
# ---------------------------------------------------------------------------

_MIN_VOLUME_FOR_A_DECISION = 5


def recommend_channel_actions(rows: list[ChannelFunnelMetrics]) -> list[dict]:
    """Advisory only (task §33) — returns `{publication_id, channel_name,
    placement_label, recommendation, rationale}` for each row; calling this
    never writes anything anywhere."""

    recommendations = []
    for row in rows:
        if row.applications == 0:
            recommendation, rationale = jpm.RECOMMEND_TEST, "No Applications yet — insufficient data to judge."
        elif row.applications < _MIN_VOLUME_FOR_A_DECISION:
            recommendation, rationale = (
                jpm.RECOMMEND_TEST,
                f"Only {row.applications} Application(s) so far — too little volume for a confident call yet.",
            )
        else:
            hirable_rate = row.hirable / row.applications
            ready_rate = row.ready_for_phone_review / row.applications
            if hirable_rate >= 0.15 or (row.hirable == 0 and ready_rate >= 0.5):
                recommendation, rationale = (
                    jpm.RECOMMEND_INCREASE,
                    f"Strong funnel quality ({row.hirable} Hirable / {row.applications} Applications).",
                )
            elif hirable_rate == 0 and ready_rate < 0.1:
                recommendation, rationale = (
                    jpm.RECOMMEND_REDUCE,
                    f"Weak funnel quality — only {row.ready_for_phone_review} of {row.applications} Applications "
                    "reached Ready for Phone Review.",
                )
            else:
                recommendation, rationale = jpm.RECOMMEND_MAINTAIN, "Funnel quality is in an unremarkable middle range."

        recommendations.append({
            "publication_id": row.publication_id, "channel_name": row.channel_name,
            "placement_label": row.placement_label, "recommendation": recommendation, "rationale": rationale,
        })
    return recommendations
