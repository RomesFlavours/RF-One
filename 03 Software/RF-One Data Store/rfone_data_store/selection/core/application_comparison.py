"""Application-to-application comparison (Task 3C-FIX §10) — a concise,
evidence-based summary of what changed between a person's most recent PRIOR
Application and their current one. Reuses only already-normalized profile
fields (`role_family`/`normalized_role` from `selection/normalization.py`,
certifications as stated) — never infers motivation or personality from the
mere fact of a repeat application (task's own boundary: "Do NOT infer
motivation/personality from the mere fact of reapplying.")."""

from __future__ import annotations

from dataclasses import dataclass, field

from .experience_analysis import months_between
from .profile import CandidateCVProfile


@dataclass
class ApplicationChangeSummary:
    changes: list[str] = field(default_factory=list)
    has_material_change: bool = False


def _relevant_months(profile: CandidateCVProfile, role_family: str | None, normalized_role: str | None) -> int:
    if not (role_family or normalized_role):
        return 0
    total = 0
    for w in profile.work_history:
        if (role_family and w.role_family == role_family) or (normalized_role and w.normalized_role == normalized_role):
            total += months_between(w.start_date, w.end_date if not w.is_current else None) or 0
    return total


def compare_applications(
    *, prior_profile: CandidateCVProfile, prior_target_role: str | None,
    current_profile: CandidateCVProfile, current_target_role: str | None,
) -> ApplicationChangeSummary:
    """Facts-only diff — every line is traceable back to a concrete field
    on one of the two profiles. Returns one "no material change" line
    (`has_material_change=False`) rather than an empty list when nothing
    changed, so the caller always has something to display."""

    changes: list[str] = []

    if prior_target_role != current_target_role:
        changes.append(
            f"Target role changed from {prior_target_role or '(unspecified)'} to "
            f"{current_target_role or '(unspecified)'}."
        )

    prior_roles = {w.normalized_role for w in prior_profile.work_history if w.normalized_role}
    current_roles = {w.normalized_role for w in current_profile.work_history if w.normalized_role}
    new_roles = current_roles - prior_roles
    if new_roles:
        changes.append(f"New role(s) on record since the previous application: {', '.join(sorted(new_roles))}.")

    prior_certs = {c.name.strip().lower() for c in prior_profile.certifications if c.name}
    current_certs = {c.name.strip().lower() for c in current_profile.certifications if c.name}
    new_certs = current_certs - prior_certs
    if new_certs:
        changes.append(f"New certification(s) on record: {', '.join(sorted(new_certs))}.")

    if current_target_role:
        target_role_family = next(
            (w.role_family for w in current_profile.work_history if w.normalized_role == current_target_role), None,
        )
        prior_months = _relevant_months(prior_profile, target_role_family, current_target_role)
        current_months = _relevant_months(current_profile, target_role_family, current_target_role)
        if current_months > prior_months:
            changes.append(
                f"Longer relevant tenure toward the current target role: {prior_months} -> "
                f"{current_months} month(s)."
            )

    if changes:
        return ApplicationChangeSummary(changes=changes, has_material_change=True)
    return ApplicationChangeSummary(
        changes=["No material professional change detected since the previous application."],
        has_material_change=False,
    )
