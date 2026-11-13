"""Realistic demo CandidateCVProfile fixtures (task §21). Exercise the same
schema and downstream analysis a real parsed résumé would. `normalized_role`
is deliberately left unset here — normalization is applied uniformly by
`resolve.py` regardless of whether a profile came from a fixture or a real
parser, so the fixtures also exercise the Restaurant Industry Extension's
`normalize_title()`, not a shortcut around it.
"""

from __future__ import annotations

from datetime import datetime

from ..core.profile import CandidateCVProfile, EducationRecord, WorkHistoryRecord


def _d(year: int, month: int) -> datetime:
    # Naive by convention — see core/experience_analysis.py's module note.
    return datetime(year, month, 1)


def stable_experienced_candidate() -> CandidateCVProfile:
    """Fixture 1: a stable, experienced Server candidate — long tenures, no
    gaps, direct target-role experience."""

    return CandidateCVProfile(
        full_name="Maria Gonzalez",
        email="maria.gonzalez@example.com",
        phone="(407) 555-0142",
        location="Orlando, FL",
        languages="English, Spanish",
        target_role="SERVER",
        declared_availability="Full-time, weekends included",
        source="DEMO_FIXTURE",
        source_file="maria_gonzalez_resume.pdf",
        declared_age_context=None,
        education=[
            EducationRecord(
                institution="Orlando High School", program=None, qualification="High School Diploma",
                field=None, start_date=_d(2012, 8), end_date=_d(2016, 5), completion_status="COMPLETED",
            ),
        ],
        work_history=[
            WorkHistoryRecord(
                employer="The Garden Bistro", location="Orlando, FL", original_job_title="Server",
                start_date=_d(2016, 6), end_date=_d(2020, 3), is_current=False,
                responsibilities="Took orders for a 12-table section, processed payments, coordinated "
                "with kitchen on timing.",
                achievements="Consistently ranked top 3 in guest satisfaction surveys for two consecutive years.",
                reason_for_leaving="Relocated closer to family.",
                evidence_snippet="Server, The Garden Bistro (Jun 2016 - Mar 2020): Managed a 12-table "
                "section during peak dinner service; trained 4 new servers.",
            ),
            WorkHistoryRecord(
                employer="Rome's Flavours - WP", location="Winter Park, FL", original_job_title="Server",
                start_date=_d(2020, 5), end_date=None, is_current=True,
                responsibilities="Full-service dining, wine service, private event coordination.",
                achievements="Selected to train new hires on wine service standard.",
                reason_for_leaving=None,
                evidence_snippet="Server, Rome's Flavours (May 2020 - Present): Handle full-service "
                "dining including wine presentation and private event coordination.",
            ),
        ],
    )


def strong_career_progression_candidate() -> CandidateCVProfile:
    """Fixture 2: started as Host, promoted internally to Server, then to
    FOH Supervisor — clear upward trajectory at the same employer."""

    return CandidateCVProfile(
        full_name="Devon Ashworth",
        email="devon.ashworth@example.com",
        phone="(321) 555-0198",
        location="Mount Dora, FL",
        languages="English",
        target_role="SERVER",
        declared_availability="Full-time",
        source="DEMO_FIXTURE",
        source_file="devon_ashworth_resume.pdf",
        declared_age_context=None,
        education=[
            EducationRecord(
                institution="Lake County Community College", program="Associate of Arts",
                qualification="Associate Degree", field="Business Administration",
                start_date=_d(2015, 8), end_date=_d(2017, 5), completion_status="COMPLETED",
            ),
        ],
        work_history=[
            WorkHistoryRecord(
                employer="Lakeside Grill", location="Mount Dora, FL", original_job_title="Host",
                start_date=_d(2017, 6), end_date=_d(2018, 9), is_current=False,
                responsibilities="Greeted guests, managed reservation book and wait list.",
                achievements=None, reason_for_leaving="Promoted internally to Server.",
                evidence_snippet="Host, Lakeside Grill (Jun 2017 - Sep 2018): Managed wait list of up "
                "to 40 parties on weekend nights.",
            ),
            WorkHistoryRecord(
                employer="Lakeside Grill", location="Mount Dora, FL", original_job_title="Server",
                start_date=_d(2018, 9), end_date=_d(2021, 4), is_current=False,
                responsibilities="Full-service dining for up to 8 tables, upsold specials and wine pairings.",
                achievements="Top upsell performer, Q2-Q4 2020.",
                reason_for_leaving="Promoted internally to FOH Supervisor.",
                evidence_snippet="Server, Lakeside Grill (Sep 2018 - Apr 2021): Recognized as top upsell "
                "performer for three consecutive quarters in 2020.",
            ),
            WorkHistoryRecord(
                employer="Lakeside Grill", location="Mount Dora, FL", original_job_title="Floor Supervisor",
                start_date=_d(2021, 4), end_date=None, is_current=True,
                responsibilities="Supervise a team of 6 servers, manage nightly floor assignments, "
                "resolve guest escalations.",
                achievements="Reduced average table turn time by 8 minutes through revised seating flow.",
                reason_for_leaving=None,
                evidence_snippet="Floor Supervisor, Lakeside Grill (Apr 2021 - Present): Supervise a "
                "team of 6 servers; redesigned seating flow to reduce average table turn time by 8 minutes.",
            ),
        ],
    )


def short_tenure_boh_transition_candidate() -> CandidateCVProfile:
    """Fixture 3: several short-tenure kitchen jobs, most recently Line
    Cook, now applying for Server — exercises SHORT_TENURE_PATTERN and the
    BOH -> SERVER transition-to-investigate."""

    return CandidateCVProfile(
        full_name="Jordan Blake",
        email="jordan.blake@example.com",
        phone="(689) 555-0177",
        location="Orlando, FL",
        languages="English",
        target_role="SERVER",
        declared_availability="Evenings and weekends",
        source="DEMO_FIXTURE",
        source_file="jordan_blake_resume.pdf",
        declared_age_context=None,
        education=[
            EducationRecord(
                institution="Central Florida High School", program=None, qualification="High School Diploma",
                field=None, start_date=_d(2019, 8), end_date=_d(2023, 5), completion_status="COMPLETED",
            ),
        ],
        work_history=[
            WorkHistoryRecord(
                employer="Sunset Diner", location="Orlando, FL", original_job_title="Prep Cook",
                start_date=_d(2023, 6), end_date=_d(2023, 10), is_current=False,
                responsibilities="Prepped ingredients for line service, maintained walk-in organization.",
                achievements=None, reason_for_leaving="Seasonal position ended.",
                evidence_snippet="Prep Cook, Sunset Diner (Jun 2023 - Oct 2023): Prepped ingredients for "
                "a high-volume breakfast/lunch line.",
            ),
            WorkHistoryRecord(
                employer="Downtown Pizza Co.", location="Orlando, FL", original_job_title="Pizza Cook",
                start_date=_d(2023, 11), end_date=_d(2024, 3), is_current=False,
                responsibilities="Built and fired pizzas during dinner rush, restocked line.",
                achievements=None, reason_for_leaving="Hours were cut below full-time.",
                evidence_snippet="Pizza Cook, Downtown Pizza Co. (Nov 2023 - Mar 2024): Fired 60+ pizzas "
                "per shift during weekend dinner rush.",
            ),
            WorkHistoryRecord(
                employer="The Garden Bistro", location="Orlando, FL", original_job_title="Line Cook",
                start_date=_d(2024, 4), end_date=_d(2024, 8), is_current=False,
                responsibilities="Ran the saute station during dinner service.",
                achievements=None, reason_for_leaving="Wanted a change of pace from the kitchen.",
                evidence_snippet="Line Cook, The Garden Bistro (Apr 2024 - Aug 2024): Ran the saute "
                "station for a 150-cover dinner service.",
            ),
            WorkHistoryRecord(
                employer="Harbor House Kitchen", location="Orlando, FL", original_job_title="Line Cook",
                start_date=_d(2024, 9), end_date=None, is_current=True,
                responsibilities="Current line cook, expo and saute rotation.",
                achievements=None, reason_for_leaving=None,
                evidence_snippet="Line Cook, Harbor House Kitchen (Sep 2024 - Present): Rotate between "
                "expo and saute stations.",
            ),
        ],
    )


FIXTURES = [
    stable_experienced_candidate,
    strong_career_progression_candidate,
    short_tenure_boh_transition_candidate,
]


def select_fixture(seed_text: str) -> CandidateCVProfile:
    """Deterministic fixture selection so repeated uploads of the same file
    name/content consistently produce the same demo candidate."""

    index = sum(seed_text.encode("utf-8")) % len(FIXTURES) if seed_text else 0
    return FIXTURES[index]()
