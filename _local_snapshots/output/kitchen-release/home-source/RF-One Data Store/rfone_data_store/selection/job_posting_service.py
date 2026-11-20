"""Job Posting Generator service (Task 5E Part A). Generates an editable,
versioned base Job Posting draft from existing structured Selection data
(Selection Session + Rule Set), never auto-publishes it, and — once
explicitly approved — supports independently-editable, independently-
approved channel-specific variants. Internal Screening Rules are never
copied into posting content (task §2's own "internal screening logic and
public job-posting content are separate concepts") — only public-facing
descriptive fields ever appear here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .core import job_posting_model as jpm

_POSTING_CONTENT_FIELDS = (
    "title", "company_description", "branch_description", "role_summary", "responsibilities",
    "minimum_requirements", "preferred_experience", "availability_expectations", "schedule_description",
    "compensation_description", "benefits_description", "location_context", "application_instructions",
    "other_info",
)


# ---------------------------------------------------------------------------
# Base Job Posting generation (task §1) — Selection Session + Rule Set +
# Company/Branch context -> an initial DRAFT, never auto-published.
# ---------------------------------------------------------------------------

def generate_base_posting(session: Session, session_id: int, *, created_by: str | None = None) -> m.JobPosting:
    """Task §1 — RF-One drafts an INITIAL version from what Selection
    already knows structurally about this Session (role, restaurant/branch
    context, current Rule Set version) — never from any internal Screening
    Criterion content (task §2). The draft is intentionally plain/generic
    text a human is expected to review and rewrite; RF-One never invents
    compensation/benefits specifics it has no data for."""

    selection_session = session.get(m.SelectionSession, session_id)
    if selection_session is None:
        raise ValueError(f"No Selection Session with id {session_id}")

    job_posting = m.JobPosting(
        session_id=session_id, restaurant_id=selection_session.restaurant_id,
        location_label=selection_session.location_label, role=selection_session.target_role,
        rule_set_version_id=selection_session.current_rule_set_version_id, status=jpm.DRAFT,
        created_by=created_by,
    )
    session.add(job_posting)
    session.flush()

    draft = m.JobPostingVersion(
        job_posting_id=job_posting.id, version=1, title=f"{selection_session.target_role.title()} — Now Hiring",
        role_summary=(
            f"We are looking for a {selection_session.target_role.title()} to join our team"
            + (f" at {selection_session.location_label}" if selection_session.location_label else "") + "."
        ),
        application_instructions="Apply online — a short application form and a résumé/CV are all that's needed.",
        source=jpm.SYSTEM_GENERATED, author="RF-One",
    )
    session.add(draft)
    session.flush()
    return job_posting


def get_job_posting(session: Session, job_posting_id: int) -> m.JobPosting | None:
    return session.get(m.JobPosting, job_posting_id)


def list_job_postings_for_session(session: Session, session_id: int) -> list[m.JobPosting]:
    stmt = select(m.JobPosting).where(m.JobPosting.session_id == session_id).order_by(m.JobPosting.id)
    return list(session.scalars(stmt).all())


def get_current_version(session: Session, job_posting_id: int) -> m.JobPostingVersion:
    job_posting = session.get(m.JobPosting, job_posting_id)
    if job_posting is None:
        raise ValueError(f"No JobPosting with id {job_posting_id}")
    stmt = select(m.JobPostingVersion).where(
        m.JobPostingVersion.job_posting_id == job_posting_id, m.JobPostingVersion.version == job_posting.current_version,
    )
    version = session.scalars(stmt).first()
    if version is None:
        raise ValueError(f"JobPosting {job_posting_id} has no version {job_posting.current_version}")
    return version


def list_versions(session: Session, job_posting_id: int) -> list[m.JobPostingVersion]:
    stmt = (
        select(m.JobPostingVersion)
        .where(m.JobPostingVersion.job_posting_id == job_posting_id)
        .order_by(m.JobPostingVersion.version)
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Human edit / approval (task §4) — every edit creates a NEW version; never
# overwrites a prior one. Approval is one explicit event on one specific
# version.
# ---------------------------------------------------------------------------

def edit_posting(
    session: Session, job_posting_id: int, *, author: str | None, reason: str | None = None, **content_fields,
) -> m.JobPostingVersion:
    """Task §4/§7 — always creates a new `JobPostingVersion` (the base
    posting's own append-only history, mirroring
    `SelectionRuleSetVersion`'s discipline). A `reason` is REQUIRED once the
    Job Posting has already been `APPROVED` at least once (an edit after
    approval is a real, accountable change — task §7's own "require/
    preserve a reason for the change"); before first approval, editing the
    still-draft content needs none."""

    job_posting = session.get(m.JobPosting, job_posting_id)
    if job_posting is None:
        raise ValueError(f"No JobPosting with id {job_posting_id}")
    unknown = [k for k in content_fields if k not in _POSTING_CONTENT_FIELDS]
    if unknown:
        raise ValueError(f"Unknown Job Posting content field(s) {unknown!r}")

    if job_posting.approved_version_id is not None and not (reason and reason.strip()):
        raise ValueError("Editing a Job Posting that has already been approved requires a reason for the change.")

    current = get_current_version(session, job_posting_id)
    new_version = m.JobPostingVersion(
        job_posting_id=job_posting_id, version=job_posting.current_version + 1, author=author, reason=reason,
        source=jpm.HUMAN_EDITED,
    )
    for field in _POSTING_CONTENT_FIELDS:
        setattr(new_version, field, content_fields.get(field, getattr(current, field)))
    session.add(new_version)
    job_posting.current_version += 1
    session.flush()
    return new_version


def approve_posting(session: Session, job_posting_id: int, *, approved_by: str) -> m.JobPosting:
    """Task §4 — approves the CURRENT version specifically; channel variants
    may only be generated from an approved base version (task's own
    "after the base posting is approved")."""

    if not approved_by or not approved_by.strip():
        raise ValueError("Approving a Job Posting requires the approving Selezionatore's name.")
    job_posting = session.get(m.JobPosting, job_posting_id)
    if job_posting is None:
        raise ValueError(f"No JobPosting with id {job_posting_id}")

    current = get_current_version(session, job_posting_id)
    current.approved_by = approved_by
    current.approved_at = datetime.utcnow()
    job_posting.approved_version_id = current.id
    job_posting.status = jpm.APPROVED
    session.flush()
    return job_posting


# ---------------------------------------------------------------------------
# Channel-specific variants (task §5/§6/§7) — created only from an approved
# base posting; approved ONE BY ONE, never "Approve All" (task's own
# explicit prohibition — no bulk-approve function exists here at all).
# ---------------------------------------------------------------------------

def create_channel_variant(
    session: Session, job_posting_id: int, channel_id: int, *, variant_text: str, title_override: str | None = None,
    created_by: str | None = None,
) -> m.JobPostingChannelVariant:
    job_posting = session.get(m.JobPosting, job_posting_id)
    if job_posting is None:
        raise ValueError(f"No JobPosting with id {job_posting_id}")
    if job_posting.approved_version_id is None:
        raise ValueError("Channel variants may only be generated after the base Job Posting is approved.")
    channel = session.get(m.ChannelDefinition, channel_id)
    if channel is None:
        raise ValueError(f"No ChannelDefinition with id {channel_id}")

    variant = m.JobPostingChannelVariant(
        job_posting_id=job_posting_id, channel_id=channel_id, status=jpm.DRAFT, created_by=created_by,
    )
    session.add(variant)
    session.flush()

    version = m.JobPostingChannelVariantVersion(
        variant_id=variant.id, version=1, title_override=title_override, variant_text=variant_text,
        source=jpm.SYSTEM_GENERATED, author=created_by or "RF-One",
    )
    session.add(version)
    session.flush()
    return variant


def get_channel_variant(session: Session, variant_id: int) -> m.JobPostingChannelVariant | None:
    return session.get(m.JobPostingChannelVariant, variant_id)


def list_channel_variants(session: Session, job_posting_id: int) -> list[m.JobPostingChannelVariant]:
    stmt = (
        select(m.JobPostingChannelVariant)
        .where(m.JobPostingChannelVariant.job_posting_id == job_posting_id)
        .order_by(m.JobPostingChannelVariant.id)
    )
    return list(session.scalars(stmt).all())


def get_current_variant_version(session: Session, variant_id: int) -> m.JobPostingChannelVariantVersion:
    variant = session.get(m.JobPostingChannelVariant, variant_id)
    if variant is None:
        raise ValueError(f"No JobPostingChannelVariant with id {variant_id}")
    stmt = select(m.JobPostingChannelVariantVersion).where(
        m.JobPostingChannelVariantVersion.variant_id == variant_id,
        m.JobPostingChannelVariantVersion.version == variant.current_version,
    )
    version = session.scalars(stmt).first()
    if version is None:
        raise ValueError(f"Variant {variant_id} has no version {variant.current_version}")
    return version


def list_variant_versions(session: Session, variant_id: int) -> list[m.JobPostingChannelVariantVersion]:
    stmt = (
        select(m.JobPostingChannelVariantVersion)
        .where(m.JobPostingChannelVariantVersion.variant_id == variant_id)
        .order_by(m.JobPostingChannelVariantVersion.version)
    )
    return list(session.scalars(stmt).all())


def edit_channel_variant(
    session: Session, variant_id: int, *, variant_text: str, author: str | None = None,
    title_override: str | None = None, reason: str | None = None,
) -> m.JobPostingChannelVariantVersion:
    """Task §6/§7 — always a NEW version. Once the variant has been
    `APPROVED` (task §7's own "a published channel variant may later be
    edited"), a `reason` is REQUIRED and preserved; the prior, already-
    published text is never overwritten (still readable via
    `list_variant_versions`)."""

    variant = session.get(m.JobPostingChannelVariant, variant_id)
    if variant is None:
        raise ValueError(f"No JobPostingChannelVariant with id {variant_id}")
    if variant.approved_version_id is not None and not (reason and reason.strip()):
        raise ValueError("Editing an already-approved/published channel variant requires a reason for the change.")

    new_version = m.JobPostingChannelVariantVersion(
        variant_id=variant_id, version=variant.current_version + 1, title_override=title_override,
        variant_text=variant_text, source=jpm.HUMAN_EDITED, author=author, reason=reason,
    )
    session.add(new_version)
    variant.current_version += 1
    session.flush()
    return new_version


def approve_channel_variant(session: Session, variant_id: int, *, approved_by: str) -> m.JobPostingChannelVariant:
    """Task §6 — approves ONE variant's CURRENT version. Never a bulk
    operation: approving variant A never touches variant B (task's own
    "do NOT implement Approve All as the default behavior" — there is
    simply no function here that approves more than one)."""

    if not approved_by or not approved_by.strip():
        raise ValueError("Approving a channel variant requires the approving Selezionatore's name.")
    variant = session.get(m.JobPostingChannelVariant, variant_id)
    if variant is None:
        raise ValueError(f"No JobPostingChannelVariant with id {variant_id}")

    current = get_current_variant_version(session, variant_id)
    current.approved_by = approved_by
    current.approved_at = datetime.utcnow()
    variant.approved_version_id = current.id
    variant.status = jpm.APPROVED
    session.flush()
    return variant
