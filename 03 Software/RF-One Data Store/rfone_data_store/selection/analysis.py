"""Runtime orchestration: combines Selection Core + the Restaurant Industry
Extension + one candidate's persisted Facts into a single view for the web
MVP (Facts / Derived / Flags / Indicators — task §17.C). This is where the
Client/Role Configuration choice actually happens for the current
single-client deployment: Rome's Flavours' Server Role Configuration is
selected by `target_role`, via `industry.restaurant.ROLE_CONFIGURATIONS`
(01 Domains/Shared Domains/Selection/ResumeScreening/README.md,
"Domain architecture", layers C/D). A future multi-client deployment would
look this up per-client instead of importing one industry module directly —
not needed yet (single Restaurant client today, TASK_RESTAURANT_STRUCTURE_001).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .core import contextual_age, flags as flags_mod, indicators as indicators_mod
from .core.experience_analysis import (
    EmploymentGap, EmploymentOverlap, ExperienceBreakdown, TenureStats,
    compute_experience_breakdown, compute_tenure_stats, detect_gaps, detect_overlaps,
)
from .core.flags import Flag
from .core.indicators import Indicator
from .core.information_quality import InformationQuality, compute_information_quality
from .core.profile import CandidateCVProfile
from .core.trajectory import TrajectoryEvent, TransitionToInvestigate, detect_trajectory, detect_transitions_to_investigate
from .industry import restaurant as restaurant_industry


@dataclass
class CandidateAnalysisView:
    profile: CandidateCVProfile
    role_config_found: bool
    breakdown: ExperienceBreakdown
    tenure: TenureStats
    gaps: list[EmploymentGap]
    overlaps: list[EmploymentOverlap]
    trajectory_events: list[TrajectoryEvent]
    transitions_to_investigate: list[TransitionToInvestigate]
    flags: list[Flag] = field(default_factory=list)
    indicators: list[Indicator] = field(default_factory=list)
    information_quality: InformationQuality | None = None
    derived_age_context: contextual_age.DerivedAgeContext | None = None


def analyze_candidate(profile: CandidateCVProfile) -> CandidateAnalysisView:
    role_config = restaurant_industry.ROLE_CONFIGURATIONS.get(
        profile.target_role or "SERVER", restaurant_industry.ROME_FLAVOURS_SERVER_ROLE_CONFIG
    )
    role_config_found = (profile.target_role or "SERVER") in restaurant_industry.ROLE_CONFIGURATIONS

    breakdown = compute_experience_breakdown(
        profile.work_history, role_config,
        industry_roles=restaurant_industry.INDUSTRY_ROLES,
        customer_facing_roles=restaurant_industry.CUSTOMER_FACING_ROLES,
        commercial_roles=restaurant_industry.COMMERCIAL_ROLES,
        supervisory_roles=restaurant_industry.SUPERVISORY_ROLES,
    )
    tenure = compute_tenure_stats(profile.work_history)
    gaps = detect_gaps(profile.work_history)
    overlaps = detect_overlaps(profile.work_history)
    trajectory_events = detect_trajectory(profile.work_history, seniority_rank_fn=restaurant_industry.seniority_rank)
    transitions = detect_transitions_to_investigate(
        profile.work_history, role_config, role_category_fn=restaurant_industry.role_category
    )
    information_quality = compute_information_quality(profile)
    derived_age = contextual_age.derive_age_context_from_education(profile)

    view = CandidateAnalysisView(
        profile=profile, role_config_found=role_config_found, breakdown=breakdown, tenure=tenure,
        gaps=gaps, overlaps=overlaps, trajectory_events=trajectory_events,
        transitions_to_investigate=transitions, information_quality=information_quality,
        derived_age_context=derived_age,
    )

    flag_list: list[Flag] = []
    short_tenure = flags_mod.flag_short_tenure_pattern(profile.work_history)
    if short_tenure:
        flag_list.append(short_tenure)
    flag_list.extend(flags_mod.flag_employment_gaps(gaps))
    flag_list.extend(flags_mod.flag_date_overlaps(overlaps))
    flag_list.extend(
        flags_mod.flag_role_transitions(transitions, detail_type_fn=restaurant_industry.transition_detail_type)
    )
    flag_list.extend(flags_mod.flag_title_inconsistencies(profile.work_history))
    flag_list.extend(
        flags_mod.flag_missing_information(
            has_email=bool(profile.email), has_phone=bool(profile.phone), work_history=profile.work_history,
        )
    )
    flag_list.extend(flags_mod.flag_chronology_questions(profile.work_history))
    view.flags = flag_list

    view.indicators = indicators_mod.compute_indicators(breakdown, tenure, trajectory_events, information_quality)

    return view
