"""Generic Channel / Publication / Tracking Link service (Task 5E §5/§8-§11).
Builds ONLY the generic container and manual-publication/tracking-link
seams — no provider-specific logic for Indeed/Facebook/LinkedIn/etc. is
implemented here (task §8/§35); a future connector owns that.
"""

from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .core import job_posting_model as jpm

DEFAULT_CHANNEL_NAMES = (
    "Indeed", "ZipRecruiter", "LinkedIn", "Facebook", "Instagram", "X / Twitter", "Company Website",
    "Branch Website", "Craigslist", "Local Hospitality Job Board", "Community Group", "QR / Direct Traffic", "Other",
)


# ---------------------------------------------------------------------------
# Channel container (task §5/§8/§9) — generic capability description only;
# no code here calls a real provider API.
# ---------------------------------------------------------------------------

def seed_default_channels(session: Session, *, restaurant_id: int | None) -> dict[str, int]:
    existing = {
        c.name: c.id for c in session.scalars(
            select(m.ChannelDefinition).where(m.ChannelDefinition.restaurant_id == restaurant_id)
        ).all()
    }
    result: dict[str, int] = dict(existing)
    for order, name in enumerate(DEFAULT_CHANNEL_NAMES):
        if name in existing:
            continue
        channel = m.ChannelDefinition(restaurant_id=restaurant_id, name=name, is_connected=False, display_order=order)
        session.add(channel)
        session.flush()
        result[name] = channel.id
    return result


def create_channel(
    session: Session, *, restaurant_id: int | None, name: str, is_connected: bool = False,
    supports_publish: bool = False, supports_update: bool = False, supports_pause: bool = False,
    supports_stop: bool = False, supports_metrics: bool = False, supports_cost_tracking: bool = False,
    is_paid: bool = False, default_acquisition_source_id: int | None = None,
) -> m.ChannelDefinition:
    channel = m.ChannelDefinition(
        restaurant_id=restaurant_id, name=name, is_connected=is_connected, supports_publish=supports_publish,
        supports_update=supports_update, supports_pause=supports_pause, supports_stop=supports_stop,
        supports_metrics=supports_metrics, supports_cost_tracking=supports_cost_tracking, is_paid=is_paid,
        default_acquisition_source_id=default_acquisition_source_id,
    )
    session.add(channel)
    session.flush()
    return channel


def list_channels(session: Session, *, restaurant_id: int | None = None, active_only: bool = True) -> list[m.ChannelDefinition]:
    stmt = select(m.ChannelDefinition).order_by(m.ChannelDefinition.display_order)
    if restaurant_id is not None:
        stmt = stmt.where(m.ChannelDefinition.restaurant_id == restaurant_id)
    if active_only:
        stmt = stmt.where(m.ChannelDefinition.is_active.is_(True))
    return list(session.scalars(stmt).all())


def get_channel(session: Session, channel_id: int) -> m.ChannelDefinition | None:
    return session.get(m.ChannelDefinition, channel_id)


# ---------------------------------------------------------------------------
# Publication / placement (task §9/§10/§11) — manual recording; a CONNECTED
# channel's future connector would create these same rows itself.
# ---------------------------------------------------------------------------

def record_publication(
    session: Session, variant_id: int, *, placement_label: str, status: str = jpm.PUBLICATION_DRAFT,
    publish_date: datetime | None = None, external_link: str | None = None,
    cost_amount_cents: int | None = None, cost_currency: str | None = None, notes: str | None = None,
    created_by: str | None = None,
) -> m.ChannelPublication:
    """Task §9/§10 — records ONE placement of an APPROVED channel-variant
    version and immediately issues its own unique tracking link (task's
    own "every manual/non-connected publication MUST be able to receive a
    unique RF-One tracking link" — issued unconditionally here, whether or
    not the Channel is CONNECTED, since a future connector can reuse the
    same link mechanism)."""

    jpm.validate_publication_status(status)
    variant = session.get(m.JobPostingChannelVariant, variant_id)
    if variant is None:
        raise ValueError(f"No JobPostingChannelVariant with id {variant_id}")
    if variant.approved_version_id is None:
        raise ValueError("A channel variant must be approved before it can be published.")

    channel = session.get(m.ChannelDefinition, variant.channel_id)
    publication = m.ChannelPublication(
        variant_version_id=variant.approved_version_id, channel_id=variant.channel_id,
        placement_label=placement_label, is_connected=channel.is_connected if channel else False,
        status=status, publish_date=publish_date, external_link=external_link,
        cost_amount_cents=cost_amount_cents, cost_currency=cost_currency, notes=notes, created_by=created_by,
    )
    session.add(publication)
    session.flush()

    issue_tracking_link(session, publication.id)
    return publication


def list_publications_for_job_posting(session: Session, job_posting_id: int) -> list[m.ChannelPublication]:
    stmt = (
        select(m.ChannelPublication)
        .join(
            m.JobPostingChannelVariantVersion,
            m.ChannelPublication.variant_version_id == m.JobPostingChannelVariantVersion.id,
        )
        .join(m.JobPostingChannelVariant, m.JobPostingChannelVariantVersion.variant_id == m.JobPostingChannelVariant.id)
        .where(m.JobPostingChannelVariant.job_posting_id == job_posting_id)
        .order_by(m.ChannelPublication.id)
    )
    return list(session.scalars(stmt).all())


def update_publication_status(session: Session, publication_id: int, *, status: str) -> m.ChannelPublication:
    jpm.validate_publication_status(status)
    publication = session.get(m.ChannelPublication, publication_id)
    if publication is None:
        raise ValueError(f"No ChannelPublication with id {publication_id}")
    publication.status = status
    session.flush()
    return publication


# ---------------------------------------------------------------------------
# Tracking links (task §10/§11) — one per publication/placement; multiple
# placements (and therefore multiple links) may exist for the same Channel
# and the same Job Posting/variant version (task §11).
# ---------------------------------------------------------------------------

def issue_tracking_link(session: Session, publication_id: int) -> m.ChannelTrackingLink:
    existing = session.scalars(
        select(m.ChannelTrackingLink).where(
            m.ChannelTrackingLink.channel_publication_id == publication_id, m.ChannelTrackingLink.is_active.is_(True),
        )
    ).first()
    if existing is not None:
        return existing
    link = m.ChannelTrackingLink(channel_publication_id=publication_id, token=secrets.token_urlsafe(24))
    session.add(link)
    session.flush()
    return link


def resolve_tracking_link(session: Session, token: str) -> m.ChannelTrackingLink | None:
    return session.scalars(
        select(m.ChannelTrackingLink).where(
            m.ChannelTrackingLink.token == token, m.ChannelTrackingLink.is_active.is_(True),
        )
    ).first()


def resolve_application_context(session: Session, token: str) -> dict | None:
    """Task §12 — everything the public Web Application Form needs to
    render, derived purely from the tracking link: Selection Session, Role,
    restaurant/branch context, and the exact publication/placement/variant/
    Job Posting the candidate is applying through (task §10's own "each
    tracking link must identify: channel, specific publication/placement,
    Job Posting, variant/version, Selection Session"). Returns `None` for
    an unknown/inactive link — the public route treats that as an invalid
    link, never a 500."""

    link = resolve_tracking_link(session, token)
    if link is None:
        return None
    publication = session.get(m.ChannelPublication, link.channel_publication_id)
    variant_version = session.get(m.JobPostingChannelVariantVersion, publication.variant_version_id)
    variant = session.get(m.JobPostingChannelVariant, variant_version.variant_id)
    job_posting = session.get(m.JobPosting, variant.job_posting_id)
    selection_session = session.get(m.SelectionSession, job_posting.session_id)
    return {
        "link": link, "publication": publication, "variant_version": variant_version, "variant": variant,
        "job_posting": job_posting, "session": selection_session,
    }
