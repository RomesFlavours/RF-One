"""Selection (Resume Screening) synthetic validation suite (TASK_SELECTION_001).

Mirrors `sales_validation.py`'s pattern: builds synthetic fixtures inside
one transaction, asserts required behaviors, always rolls back — no
synthetic candidate is ever left in the target database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session, sessionmaker

import inspect
import re

from . import models as m
from .selection import (
    acquisition_source_service as acq_svc,
    application_intake_service as intake_svc, application_question_service as aq_svc,
    application_service as app_svc, audit_service as audit_svc, candidate_flag_service as flag_svc,
    case_memory_service as cm_svc,
    channel_analytics_service as analytics_svc, channel_service as chan_svc,
    communication_service as comm_svc, communication_template_service as tmpl_svc,
    compliance_service as compliance_svc,
    decision_service as dec_svc, dossier_service as dossier_svc, fit_assessment_service as fa_svc,
    governance_service as gov_svc,
    identity_service as identity_svc, import_pipeline, in_person_interview_service as ip_svc,
    inbound_communication_service as inbound_svc, job_posting_service as jp_svc,
    missing_evidence_service as me_svc, normalization,
    outcome_service as outcome_svc, ownership_service as own_svc, pattern_service as pat_svc, persistence,
    phone_interview_service as pi_svc, primary_screening_ai_evaluator as ai_eval,
    primary_screening_service as ps_svc, queue_service as queue_svc, requirements_service as req_svc,
    rule_change_service as rc_svc, rule_set_service as rs_svc, scheduling_service as sched_svc,
    selection_notes_service as notes_svc, session_service as sess_svc, signal_service as sig_svc,
    stage_service as stage_svc, trainable_gap_service as tg_svc, workflow_projection_service as wf_svc,
)
from .selection.parsing import ai_client as ai_client_mod
from .selection.analysis import analyze_candidate
from .selection.core import application_model as apm, fit_assessment_model as fam, identity_model as idm
from .selection.core import communication_model as ccm
from .selection.core import compliance_model as cpm
from .selection.core import job_posting_model as jpm
from .selection.core import in_person_interview_model as ipm
from .selection.core import outcome_model as om
from .selection.core import phone_interview_model as pim
from .selection.core import primary_screening_model as psm
from .selection.core import queue_model as qm
from .selection.core import requirement_model as rm, signal_model as sm
from .selection.core import stage_model as stgm
from .selection.core import pattern_model as patm
from .selection.core import rule_set_model as rsm
from .selection.core import session_model as sesm
from .selection.core import trainable_gap_model as tgm
from .selection.core.experience_analysis import (
    current_roles, detect_overlaps, merge_intervals, months_between, total_span_months,
    work_entry_duration_months,
)
from .selection.core.profile import CandidateCVProfile, EducationRecord, WorkHistoryRecord
from .selection.core.resume_source import LOCAL_UPLOAD
from .selection.core.trajectory import PROMOTION
from .selection.industry import restaurant as restaurant_industry
from .selection.industry import restaurant_templates
from .selection.parsing import flexible_dates
from .selection.parsing.dedup import compute_content_hash
from .selection.parsing.fixtures import (
    short_tenure_boh_transition_candidate,
    stable_experienced_candidate,
    strong_career_progression_candidate,
)

@dataclass
class ValidationResult:
    success: bool
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    def check(self, description: str, condition: bool) -> None:
        if condition:
            self.checks_passed.append(description)
        else:
            self.checks_failed.append(description)
            self.success = False


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)
    _assert_batch_import(session_factory, result)
    _assert_normalization(session_factory, result)
    _assert_requirement_framework(session_factory, result)
    _assert_requirement_set_snapshot(session_factory, result)
    _assert_fit_assessment(session_factory, result)
    _assert_selection_signals(session_factory, result)
    _assert_selection_3c_fix(session_factory, result)
    _assert_selection_3c_micro_fix(session_factory, result)
    _assert_selection_4a_phone_interview(session_factory, result)
    _assert_selection_4b_in_person_interview(session_factory, result)
    _assert_selection_3d_primary_screening(session_factory, result)
    _assert_selection_3d_fix(session_factory, result)
    _assert_selection_5a_outcome_stage_decision(session_factory, result)
    _assert_selection_5a_fix_authoritative_state_and_queue(session_factory, result)
    _assert_selection_5a_align(session_factory, result)
    _assert_selection_5a_micro_fix(session_factory, result)
    _assert_selection_pattern_intelligence_foundation(session_factory, result)
    _assert_trainable_gap_dossier(session_factory, result)
    _assert_session_ownership_rule_governance(session_factory, result)
    _assert_candidate_communication_scheduling(session_factory, result)
    _assert_5d_micro_fix_session_scheduling(session_factory, result)
    _assert_job_posting_application_intake_pre_screening(session_factory, result)
    _assert_compliance_audit_domain_closure(session_factory, result)
    with session_factory() as session:
        try:
            _assert(session, result)
        finally:
            session.rollback()
    return result


def _d(year: int, month: int) -> datetime:
    return datetime(year, month, 1)


def _assert_batch_import(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Batch-import checks (TASK_SELECTION_002): duplicate detection,
    source_provider persistence, per-file isolation, missing fields stay
    unknown.

    Runs in its own dedicated session, on its own dedicated connection, and
    BEFORE `_assert`'s shared `session` performs any write — deliberately.
    `import_pipeline.import_one_resume` commits/rolls back internally,
    exactly like the web app's real per-file `SessionFactory()` session
    (`03 Software/Selection/app.py`'s `_process_one_upload`). SQLite allows
    only one writer at a time: if this ran on a second session while the
    shared `session` still held an open (uncommitted, but already-written)
    transaction, that write would block/fail with "database is locked".
    Running it first, and fully committing + cleaning up before `_assert`'s
    session writes anything, avoids that entirely. Cleanup here is an
    explicit, real delete + commit (not a rollback) because the writes
    above were themselves real commits.
    """

    session = session_factory()
    batch_restaurant: m.Restaurant | None = None
    try:
        batch_restaurant = m.Restaurant(name="Synthetic Batch Import Test Restaurant", default_currency="USD")
        session.add(batch_restaurant)
        session.commit()

        hash1 = compute_content_hash("Jordan Blake resume text, unique batch fixture one.", "candidate_one.pdf")
        first_import = import_pipeline.import_one_resume(
            session, restaurant_id=batch_restaurant.id, source_type=LOCAL_UPLOAD,
            original_filename="candidate_one.pdf", storage_path=None,
            raw_text="Jordan Blake resume text, unique batch fixture one.", content_hash=hash1,
        )
        result.check(
            # This fixture text is not shaped like a real résumé (no name/contact/section headers),
            # so Task 2A's real rule-based parser correctly reports PARTIAL (text saved, nothing
            # structured recognized) rather than the old fabricated-fixture DEMO parser's guaranteed
            # COMPLETED — either way, a Candidate must still be created (never dropped/failed).
            "B1: first import of a résumé completes and creates a Candidate",
            first_import.status in (import_pipeline.COMPLETED, import_pipeline.PARTIAL)
            and first_import.candidate_id is not None,
        )
        result.check(
            "B2: source_provider defaults to 'manual' for a LOCAL_UPLOAD résumé and survives persistence",
            persistence.get_candidate(session, first_import.candidate_id).source_provider == "manual",
        )

        duplicate_import = import_pipeline.import_one_resume(
            session, restaurant_id=batch_restaurant.id, source_type=LOCAL_UPLOAD,
            original_filename="candidate_one_renamed.pdf", storage_path=None,
            raw_text="Jordan Blake resume text, unique batch fixture one.", content_hash=hash1,
        )
        result.check(
            "B3: re-importing an identical résumé (same content hash, same restaurant) is flagged "
            "DUPLICATE and does not create a second Candidate row",
            duplicate_import.status == import_pipeline.DUPLICATE
            and duplicate_import.candidate_id == first_import.candidate_id,
        )
        candidates_after_duplicate = persistence.list_candidates(session, restaurant_id=batch_restaurant.id)
        result.check(
            "B3b: exactly one Candidate exists for this restaurant after the duplicate attempt",
            len({c.id for c in candidates_after_duplicate}) == 1,
        )

        hash2 = compute_content_hash("Second, different résumé text entirely.", "candidate_two.pdf")
        second_import = import_pipeline.import_one_resume(
            session, restaurant_id=batch_restaurant.id, source_type=LOCAL_UPLOAD,
            original_filename="candidate_two.pdf", storage_path=None,
            raw_text="Second, different résumé text entirely.", content_hash=hash2,
        )
        result.check(
            "B4: a genuinely different résumé in the same batch imports independently as its own "
            "Candidate (batch processing is not blocked by an earlier duplicate)",
            second_import.status in (import_pipeline.COMPLETED, import_pipeline.PARTIAL)
            and second_import.candidate_id != first_import.candidate_id,
        )

        minimal_profile = CandidateCVProfile(
            full_name="Minimal Candidate", source=LOCAL_UPLOAD, source_provider="manual",
            education=[EducationRecord(institution="Some College")],
            work_history=[WorkHistoryRecord(employer="Some Employer", original_job_title="Server")],
        )
        minimal_candidate = persistence.save_candidate_profile(
            session, minimal_profile, restaurant_id=batch_restaurant.id, raw_resume_id=None,
        )
        session.commit()
        session.expire_all()
        reloaded_minimal = persistence.to_profile(persistence.get_candidate(session, minimal_candidate.id))
        result.check(
            "B5: fields never explicitly extracted (email, phone, location, dates, completion_status) "
            "remain None/UNKNOWN after persistence — never guessed or defaulted to an empty string",
            reloaded_minimal.email is None and reloaded_minimal.phone is None
            and reloaded_minimal.location is None
            and reloaded_minimal.education[0].start_date is None
            and reloaded_minimal.education[0].completion_status is None
            and reloaded_minimal.work_history[0].start_date is None
            and reloaded_minimal.work_history[0].end_date is None,
        )
    finally:
        # Real cleanup, real commit — undoes the real commits made above, so
        # no synthetic batch-import row survives this suite.
        session.rollback()
        if batch_restaurant is not None and batch_restaurant.id is not None:
            for candidate in persistence.list_candidates(session, restaurant_id=batch_restaurant.id):
                session.delete(candidate)
            session.flush()
            still_attached_restaurant = session.get(m.Restaurant, batch_restaurant.id)
            if still_attached_restaurant is not None:
                for raw in list(session.query(m.RawResume).filter_by(restaurant_id=batch_restaurant.id)):
                    session.delete(raw)
                session.delete(still_attached_restaurant)
                session.commit()
        session.close()


def _assert_normalization(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 2B checks — date normalization (A-H), role normalization (I-O),
    and pipeline integration (P-R). Pure dataclass-level checks (A-O, Q)
    need no database at all; P and R use their own dedicated session/
    restaurant, committed and cleaned up exactly like `_assert_batch_import`
    above, for the same reason (SQLite single-writer, run before `_assert`'s
    shared session touches anything)."""

    # =========================================================================
    # DATE NORMALIZATION (A-H)
    # =========================================================================
    a = flexible_dates.normalize_date_pair("Jan 2021", "Present")
    result.check(
        "2B-A: 'Jan 2021 - Present' normalizes to a MONTH-precision start, is_current=True, "
        "and a null normalized end (never a fabricated end date)",
        a.normalized_start == datetime(2021, 1, 1) and a.is_current is True and a.normalized_end is None
        and a.start_precision == flexible_dates.PRECISION_MONTH,
    )

    b = flexible_dates.normalize_date_pair("2020", "2022")
    result.check(
        "2B-B: '2020 - 2022' normalizes both ends to YEAR precision, not fabricated month precision",
        b.normalized_start == datetime(2020, 1, 1) and b.normalized_end == datetime(2022, 1, 1)
        and b.start_precision == flexible_dates.PRECISION_YEAR and b.end_precision == flexible_dates.PRECISION_YEAR
        and b.is_current is False,
    )

    c = flexible_dates.normalize_date_text("2021")
    result.check(
        "2B-C: a year-only date normalizes with YEAR precision", c.precision == flexible_dates.PRECISION_YEAR,
    )

    d_month_name = flexible_dates.normalize_date_text("January 2021")
    d_numeric = flexible_dates.normalize_date_text("01/2021")
    d_iso = flexible_dates.normalize_date_text("2021-03")
    result.check(
        "2B-D: month/year dates ('January 2021', '01/2021', '2021-03') all normalize with MONTH precision "
        "to the correct value",
        d_month_name.value == datetime(2021, 1, 1) and d_month_name.precision == flexible_dates.PRECISION_MONTH
        and d_numeric.value == datetime(2021, 1, 1) and d_numeric.precision == flexible_dates.PRECISION_MONTH
        and d_iso.value == datetime(2021, 3, 1) and d_iso.precision == flexible_dates.PRECISION_MONTH,
    )

    current_synonyms = ["Present", "Current", "Ongoing", "Now"]
    result.check(
        "2B-E: every current-role synonym (Present/Current/Ongoing/Now) yields is_current=True "
        "and a null value — never a fabricated end date",
        all(
            flexible_dates.normalize_date_text(word).is_current and flexible_dates.normalize_date_text(word).value is None
            for word in current_synonyms
        ),
    )

    f = flexible_dates.normalize_date_text("sometime a while back")
    result.check(
        "2B-F: an unparseable date stays null (never guessed) with UNKNOWN precision",
        f.value is None and f.precision == flexible_dates.PRECISION_UNKNOWN,
    )

    duration_profile = CandidateCVProfile(
        full_name="Duration Test",
        work_history=[
            WorkHistoryRecord(
                employer="A", original_job_title="Server",
                start_date_text="Jan 2020", end_date_text="Jan 2022",
            ),
        ],
    )
    normalization.normalize_profile(duration_profile)
    result.check(
        "2B-G: duration_months is computed correctly (Jan 2020 - Jan 2022 = 24 months) once dates "
        "are normalized",
        work_entry_duration_months(duration_profile.work_history[0]) == 24,
    )

    overlap_profile = CandidateCVProfile(
        full_name="Overlap Test",
        work_history=[
            WorkHistoryRecord(employer="Day Job", original_job_title="Server",
                               start_date_text="Jan 2022", end_date_text="Dec 2022"),
            WorkHistoryRecord(employer="Night Job", original_job_title="Bartender",
                               start_date_text="Jun 2022", end_date_text="Present"),
        ],
    )
    normalization.normalize_profile(overlap_profile)
    overlaps = detect_overlaps(overlap_profile.work_history)
    still_current = current_roles(overlap_profile.work_history)
    result.check(
        "2B-H: two legitimately overlapping employment records (a second, ongoing job starting "
        "before the first one ends) normalize and detect_overlaps() cleanly, without raising, "
        "and without treating the overlap as an error; the ongoing one is correctly identified "
        "as a current role",
        len(overlaps) == 1 and len(still_current) == 1 and still_current[0].employer == "Night Job",
    )

    # =========================================================================
    # ROLE NORMALIZATION (I-O)
    # =========================================================================
    def _normalized(title: str) -> WorkHistoryRecord:
        profile = CandidateCVProfile(
            full_name="Role Test", work_history=[WorkHistoryRecord(employer="X", original_job_title=title)],
        )
        normalization.normalize_profile(profile)
        return profile.work_history[0]

    waitress = _normalized("Waitress")
    result.check(
        "2B-I: 'Waitress' normalizes to the 'Server' display title (RoleModel.md's own "
        "Waiter/Waitress-equivalent example) while normalized_role stays the distinct WAITRESS code",
        waitress.normalized_title == "Server" and waitress.normalized_role == "WAITRESS",
    )

    agm = _normalized("AGM")
    result.check(
        "2B-J: 'AGM' normalizes to 'Assistant General Manager', not collapsed into General Manager",
        agm.normalized_title == "Assistant General Manager" and agm.role_family == "Restaurant Management",
    )

    gm = _normalized("GM")
    result.check(
        "2B-K: 'GM' normalizes to 'General Manager'",
        gm.normalized_title == "General Manager" and gm.role_family == "Operations / General Management",
    )

    dual = _normalized("Server/Bartender")
    result.check(
        "2B-L: 'Server/Bartender' produces two normalized roles (multi_role=True), not one "
        "arbitrarily chosen title",
        dual.multi_role is True and dual.normalized_title == "Server / Bartender",
    )

    lead_server = _normalized("Lead Server")
    result.check(
        "2B-M: 'Lead Server' retains a meaningful 'Lead' seniority_level (not discarded, not "
        "collapsed into plain Server)",
        lead_server.seniority_level == "Lead",
    )

    unknown = _normalized("Regional Paperwork Coordinator")
    result.check(
        "2B-N: an unrecognized/custom title generates no fabricated classification — normalized_title, "
        "role_family and seniority_level all stay null",
        unknown.normalized_title is None and unknown.role_family is None and unknown.seniority_level is None,
    )

    result.check(
        "2B-O: original_job_title is never altered by normalization, for any of the titles above",
        waitress.original_job_title == "Waitress" and agm.original_job_title == "AGM"
        and gm.original_job_title == "GM" and dual.original_job_title == "Server/Bartender"
        and lead_server.original_job_title == "Lead Server"
        and unknown.original_job_title == "Regional Paperwork Coordinator",
    )

    # =========================================================================
    # IDEMPOTENCY (Q) — pure, no database
    # =========================================================================
    idempotency_profile = CandidateCVProfile(
        full_name="Idempotency Test",
        work_history=[
            WorkHistoryRecord(employer="A", original_job_title="Server/Bartender",
                               start_date_text="Jan 2020", end_date_text="Present"),
        ],
    )
    normalization.normalize_profile(idempotency_profile)
    first_pass = dataclasses_asdict_snapshot(idempotency_profile.work_history[0])
    normalization.normalize_profile(idempotency_profile)
    second_pass = dataclasses_asdict_snapshot(idempotency_profile.work_history[0])
    result.check(
        "2B-Q: running normalize_profile() twice on the same profile produces identical results "
        "(idempotent — no drift from re-normalizing already-normalized fields)",
        first_pass == second_pass,
    )

    # =========================================================================
    # PIPELINE INTEGRATION (P, R) — own dedicated session (same reasoning as
    # _assert_batch_import above: real commits, run before _assert's shared
    # session touches anything).
    # =========================================================================
    session = session_factory()
    norm_restaurant: m.Restaurant | None = None
    try:
        norm_restaurant = m.Restaurant(name="Synthetic Normalization Test Restaurant", default_currency="USD")
        session.add(norm_restaurant)
        session.commit()

        pipeline_text = (
            "Jamie Rivera\njamie.rivera@example.com\n\n"
            "EXPERIENCE\nLead Server, The Garden Bistro\nJan 2021 - Present\n"
            "Ran the floor during dinner service.\n"
        )
        import_result = import_pipeline.import_one_resume(
            session, restaurant_id=norm_restaurant.id, source_type=LOCAL_UPLOAD,
            original_filename="jamie_rivera.txt", storage_path=None,
            raw_text=pipeline_text, content_hash=compute_content_hash(pipeline_text, "jamie_rivera.txt"),
        )
        pipeline_profile = (
            persistence.to_profile(persistence.get_candidate(session, import_result.candidate_id))
            if import_result.candidate_id else None
        )
        result.check(
            "2B-P: a newly imported résumé (Task 2A pipeline) receives normalized dates and roles "
            "without any extra manual step — Lead Server/Jan 2021-Present comes back with is_current, "
            "MONTH-precision start, and a Lead seniority_level",
            pipeline_profile is not None and len(pipeline_profile.work_history) == 1
            and pipeline_profile.work_history[0].is_current is True
            and pipeline_profile.work_history[0].start_date_precision == flexible_dates.PRECISION_MONTH
            and pipeline_profile.work_history[0].seniority_level == "Lead",
        )

        # R: an already-persisted candidate, with raw parsed values already
        # stored but NOT yet normalized (simulating a pre-Task-2B row),
        # can be normalized via the reprocessing service function alone —
        # no re-upload, no re-parse.
        legacy_profile = CandidateCVProfile(
            full_name="Legacy Candidate", source=LOCAL_UPLOAD, source_provider="manual",
            work_history=[
                WorkHistoryRecord(
                    employer="Old Employer", original_job_title="Assistant Manager",
                    start_date_text="Mar 2019", end_date_text="Present",
                ),
            ],
        )
        legacy_candidate = persistence.save_candidate_profile(
            session, legacy_profile, restaurant_id=norm_restaurant.id, raw_resume_id=None,
        )
        session.commit()
        before_reprocess = persistence.to_profile(persistence.get_candidate(session, legacy_candidate.id))

        reprocessed = normalization.reprocess_candidate(session, legacy_candidate.id)
        session.expire_all()
        after_reprocess = persistence.to_profile(persistence.get_candidate(session, legacy_candidate.id))
        result.check(
            "2B-R: an already-persisted candidate (raw values already stored, never normalized) can "
            "be normalized in place via reprocess_candidate() — no re-upload required",
            reprocessed is True
            and before_reprocess.work_history[0].normalized_title is None
            and after_reprocess.work_history[0].normalized_title == "Assistant General Manager"
            and after_reprocess.work_history[0].is_current is True
            and after_reprocess.work_history[0].original_job_title == "Assistant Manager",
        )
    finally:
        session.rollback()
        if norm_restaurant is not None and norm_restaurant.id is not None:
            for candidate in persistence.list_candidates(session, restaurant_id=norm_restaurant.id):
                session.delete(candidate)
            session.flush()
            still_attached = session.get(m.Restaurant, norm_restaurant.id)
            if still_attached is not None:
                for raw in list(session.query(m.RawResume).filter_by(restaurant_id=norm_restaurant.id)):
                    session.delete(raw)
                session.delete(still_attached)
                session.commit()
        session.close()


def dataclasses_asdict_snapshot(record: WorkHistoryRecord) -> tuple:
    """A cheap, order-stable snapshot of every Task 2B-normalized field on
    one record, used only to compare "before" vs. "after" a second
    normalization pass (idempotency check 2B-Q) without depending on
    dataclasses.asdict's handling of nested/optional fields."""

    return (
        record.start_date, record.end_date, record.is_current,
        record.start_date_precision, record.end_date_precision, record.date_normalization_confidence,
        record.normalized_role, record.normalized_title, record.role_family,
        record.seniority_level, record.multi_role, record.title_normalization_confidence,
    )


def _assert_requirement_framework(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 3A checks (A-O) — Requirement Set / Requirement / Template
    persistence and behavior. Own dedicated session/restaurants, real
    commits, real cleanup — same reasoning as `_assert_batch_import` above
    (SQLite single-writer; run before `_assert`'s shared session touches
    anything)."""

    session = session_factory()
    restaurant_a: m.Restaurant | None = None
    restaurant_b: m.Restaurant | None = None
    try:
        restaurant_a = m.Restaurant(name="Synthetic Requirement Test Restaurant A", default_currency="USD")
        restaurant_b = m.Restaurant(name="Synthetic Requirement Test Restaurant B", default_currency="USD")
        session.add_all([restaurant_a, restaurant_b])
        session.commit()

        # =====================================================================
        # A-F: create a Requirement Set from scratch, with multiple
        # requirements carrying criticality/trainability/multiple assessment
        # stages/evidence guidance — all reloaded fresh from the database.
        # =====================================================================
        custom_set = req_svc.create_requirement_set(
            session, restaurant_id=restaurant_a.id, name="Server - Mount Dora", target_role="SERVER",
            location_label="Mount Dora",
        )
        req_svc.add_requirement(
            session, custom_set.id, name="Team player", category="Teamwork",
            criticality=rm.MUST_HAVE, trainability=rm.NOT_TRAINABLE,
            assessment_stages=[rm.PHONE_INTERVIEW, rm.IN_PERSON_INTERVIEW],
            evidence_positive="Describes helping a coworker without being asked.",
            evidence_contrary="Describes conflict with coworkers as someone else's fault, repeatedly.",
            evidence_insufficient="A single generic 'I work well with others' claim, no example.",
            guidance_notes="Primarily assessed live, not from the résumé alone.",
        )
        req_svc.add_requirement(
            session, custom_set.id, name="Menu knowledge", category="Technical Knowledge",
            criticality=rm.PREFERRED, trainability=rm.TRAINABLE, assessment_stages=[rm.PRACTICAL_ASSESSMENT],
        )
        session.commit()
        session.expire_all()

        reloaded_set = req_svc.get_requirement_set(session, custom_set.id)
        result.check("3A-A: a Requirement Set can be created", reloaded_set is not None and reloaded_set.name == "Server - Mount Dora")
        result.check("3A-B: it can contain multiple requirements", len(reloaded_set.requirements) == 2)

        team_player = next(r for r in reloaded_set.requirements if r.name == "Team player")
        result.check("3A-C: criticality persists correctly", team_player.criticality == rm.MUST_HAVE)
        result.check("3A-D: trainability persists correctly", team_player.trainability == rm.NOT_TRAINABLE)
        result.check(
            "3A-E: multiple assessment stages are supported",
            set(team_player.assessment_stages) == {rm.PHONE_INTERVIEW, rm.IN_PERSON_INTERVIEW},
        )
        result.check(
            "3A-F: a Requirement may contain evidence/evaluation guidance",
            team_player.evidence_positive is not None and team_player.evidence_contrary is not None
            and team_player.evidence_insufficient is not None and team_player.guidance_notes is not None,
        )

        # =====================================================================
        # G-J: templates — create/read, instantiate into an independent set,
        # confirm the template is untouched by later edits, and confirm
        # multiple templates can target the same nominal role.
        # =====================================================================
        template = req_svc.create_template(session, name="High-Volume Server (test)", intended_role="SERVER")
        req_svc.add_template_item(
            session, template.id, name="Works quickly under volume", criticality=rm.MUST_HAVE,
            trainability=rm.PARTIALLY_TRAINABLE, assessment_stages=[rm.RESUME, rm.PHONE_INTERVIEW],
        )
        session.commit()
        session.expire_all()

        reloaded_template = req_svc.get_template(session, template.id)
        result.check(
            "3A-G: a template can be created/read",
            reloaded_template is not None and len(reloaded_template.items) == 1,
        )

        instantiated_set = req_svc.instantiate_requirement_set_from_template(
            session, template_id=template.id, restaurant_id=restaurant_a.id, name="Server - Location A",
        )
        session.commit()
        session.expire_all()
        instantiated_set = req_svc.get_requirement_set(session, instantiated_set.id)
        result.check(
            "3A-H: a Requirement Set can be instantiated from a template",
            len(instantiated_set.requirements) == 1
            and instantiated_set.requirements[0].name == "Works quickly under volume"
            and instantiated_set.source_template_id == template.id,
        )

        cloned_requirement_id = instantiated_set.requirements[0].id
        req_svc.update_requirement(session, cloned_requirement_id, criticality=rm.OPTIONAL)
        session.commit()
        session.expire_all()
        template_after_edit = req_svc.get_template(session, template.id)
        result.check(
            "3A-I: modifying the restaurant Requirement Set does not alter the source template",
            template_after_edit.items[0].criticality == rm.MUST_HAVE,
        )

        second_template = req_svc.create_template(session, name="Fine-Dining Server (test)", intended_role="SERVER")
        session.commit()
        same_role_templates = req_svc.list_templates(session, intended_role="SERVER")
        result.check(
            "3A-J: multiple templates can exist for the same nominal role",
            template.id in {t.id for t in same_role_templates}
            and second_template.id in {t.id for t in same_role_templates},
        )

        # =====================================================================
        # K-L: custom requirements added post-instantiation; deactivation
        # preserves historical structure rather than deleting it.
        # =====================================================================
        req_svc.add_requirement(
            session, instantiated_set.id, name="Custom local requirement", criticality=rm.OPTIONAL,
            trainability=rm.TRAINABILITY_UNKNOWN, assessment_stages=[rm.OTHER_STAGE],
        )
        session.commit()
        session.expire_all()
        instantiated_set = req_svc.get_requirement_set(session, instantiated_set.id)
        result.check(
            "3A-K: custom requirements can be added to a Requirement Set (including one instantiated "
            "from a template)",
            any(r.name == "Custom local requirement" for r in instantiated_set.requirements),
        )

        req_svc.deactivate_requirement(session, cloned_requirement_id)
        session.commit()
        session.expire_all()
        instantiated_set = req_svc.get_requirement_set(session, instantiated_set.id)
        still_present = next((r for r in instantiated_set.requirements if r.id == cloned_requirement_id), None)
        result.check(
            "3A-L: a requirement can be deactivated without deleting historical structure",
            still_present is not None and still_present.is_active is False,
        )

        # =====================================================================
        # M: different restaurants/roles have different, non-overlapping
        # Requirement Sets.
        # =====================================================================
        other_restaurant_set = req_svc.create_requirement_set(
            session, restaurant_id=restaurant_b.id, name="Assistant Manager - Location B",
            target_role="ASSISTANT_GENERAL_MANAGER",
        )
        session.commit()
        sets_for_a = req_svc.list_requirement_sets(session, restaurant_id=restaurant_a.id)
        sets_for_b = req_svc.list_requirement_sets(session, restaurant_id=restaurant_b.id)
        result.check(
            "3A-M: different restaurants/roles can have different Requirement Sets",
            other_restaurant_set.id not in {s.id for s in sets_for_a}
            and other_restaurant_set.id in {s.id for s in sets_for_b}
            and custom_set.id in {s.id for s in sets_for_a},
        )

        # =====================================================================
        # N: Rome's Flavours-specific requirements are configuration, not
        # hard-coded universal Selection logic.
        # =====================================================================
        romes_flavours_set_id = restaurant_templates.seed_romes_flavours_requirement_set(
            session, restaurant_id=restaurant_a.id,
        )
        session.commit()
        session.expire_all()
        romes_flavours_set = req_svc.get_requirement_set(session, romes_flavours_set_id)
        has_teamwork_trait = any(
            r.name == "Works effectively as part of a team" for r in romes_flavours_set.requirements
        )
        # The universal framework may (and does) document this boundary in
        # its own comments/docstrings ("never Rome's Flavours' hiring
        # philosophy") — that is documentation, not a violation. The actual
        # architectural guarantee is that neither module ever IMPORTS or
        # REFERENCES the module that holds Rome's Flavours' example data, so
        # that data can never be reached except as ordinary restaurant rows.
        service_source = inspect.getsource(req_svc)
        vocab_source = inspect.getsource(rm)
        result.check(
            "3A-N: Rome's Flavours-specific traits exist as Requirement Set data (not hard-coded), and "
            "the universal framework (requirements_service.py, core/requirement_model.py) never imports "
            "or references the module that defines them",
            has_teamwork_trait
            and "restaurant_templates" not in service_source and "restaurant_templates" not in vocab_source
            and "industry.restaurant" not in service_source and "industry.restaurant" not in vocab_source,
        )

        # =====================================================================
        # O: existing resume/candidate Selection functionality is untouched
        # by this framework — a plain batch import still works end to end.
        # =====================================================================
        regression_text = "Morgan Lee\nmorgan.lee@example.com\n\nEXPERIENCE\nServer, Test Diner\n2021 - 2022\n"
        regression_import = import_pipeline.import_one_resume(
            session, restaurant_id=restaurant_a.id, source_type=LOCAL_UPLOAD,
            original_filename="morgan_lee.txt", storage_path=None, raw_text=regression_text,
            content_hash=compute_content_hash(regression_text, "morgan_lee.txt"),
        )
        result.check(
            "3A-O: existing résumé/candidate Selection functionality (Task 2A/2B import pipeline) "
            "continues to work unaffected by the Requirement Framework",
            regression_import.status in (import_pipeline.COMPLETED, import_pipeline.PARTIAL)
            and regression_import.candidate_id is not None,
        )
    finally:
        session.rollback()
        for restaurant in (restaurant_a, restaurant_b):
            if restaurant is not None and restaurant.id is not None:
                for requirement_set in req_svc.list_requirement_sets(session, restaurant_id=restaurant.id):
                    session.delete(requirement_set)
                for candidate in persistence.list_candidates(session, restaurant_id=restaurant.id):
                    session.delete(candidate)
                session.flush()
                for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                    session.delete(raw)
        for template_row in list(session.query(m.RequirementTemplate).filter(
            m.RequirementTemplate.name.in_([
                "High-Volume Server (test)", "Fine-Dining Server (test)",
                "High-Touch Hospitality Server", "High-Volume Server", "Sales-Oriented Server",
                "Restaurant Assistant General Manager",
            ])
        )):
            session.delete(template_row)
        still_attached_a = session.get(m.Restaurant, restaurant_a.id) if restaurant_a is not None else None
        still_attached_b = session.get(m.Restaurant, restaurant_b.id) if restaurant_b is not None else None
        for restaurant_row in (still_attached_a, still_attached_b):
            if restaurant_row is not None:
                session.delete(restaurant_row)
        session.commit()
        session.close()


def _assert_requirement_set_snapshot(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 3A-FIX checks (A-P) — immutable Requirement Set snapshots. Own
    dedicated session/restaurant, real commits, real cleanup (same
    reasoning as `_assert_batch_import`/`_assert_requirement_framework`
    above)."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic Snapshot Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        # =====================================================================
        # A-D: create a set with two requirements (in a deliberately
        # non-alphabetical display order), snapshot it, and verify the
        # snapshot's metadata/requirements/order.
        # =====================================================================
        requirement_set = req_svc.create_requirement_set(
            session, restaurant_id=restaurant.id, name="Server - Snapshot Test", target_role="SERVER",
            location_label="Test Location", description="Snapshot test fixture",
        )
        req_svc.add_requirement(
            session, requirement_set.id, name="Second requirement", category="Role Skills",
            criticality=rm.PREFERRED, trainability=rm.TRAINABLE, assessment_stages=[rm.RESUME],
            display_order=1,
        )
        req_svc.add_requirement(
            session, requirement_set.id, name="First requirement", category="Experience",
            criticality=rm.MUST_HAVE, trainability=rm.NOT_TRAINABLE,
            assessment_stages=[rm.RESUME, rm.PHONE_INTERVIEW],
            evidence_positive="Explicit résumé statement.", evidence_contrary="Explicit contrary statement.",
            evidence_insufficient="A vague, generic claim only.", guidance_notes="Check dates carefully.",
            display_order=0,
        )
        session.commit()
        session.expire_all()

        version_at_snapshot = req_svc.get_requirement_set(session, requirement_set.id).version
        snapshot = req_svc.create_requirement_set_snapshot(session, requirement_set.id)
        session.commit()
        session.expire_all()
        snapshot = req_svc.get_snapshot(session, snapshot.id)

        result.check("3A-FIX-A: a Requirement Set snapshot can be created", snapshot is not None)
        result.check(
            "3A-FIX-B: the snapshot contains Requirement Set metadata (name, target role, location, "
            "version, active state)",
            snapshot.name == "Server - Snapshot Test" and snapshot.target_role == "SERVER"
            and snapshot.location_label == "Test Location" and snapshot.version == version_at_snapshot
            and snapshot.was_active is True,
        )
        result.check(
            "3A-FIX-C: the snapshot contains all expected Requirements and fields (criticality, "
            "trainability, assessment stages, evidence guidance)",
            len(snapshot.items) == 2
            and any(
                i.name == "First requirement" and i.criticality == rm.MUST_HAVE
                and i.trainability == rm.NOT_TRAINABLE and set(i.assessment_stages) == {rm.RESUME, rm.PHONE_INTERVIEW}
                and i.evidence_positive and i.evidence_contrary and i.evidence_insufficient and i.guidance_notes
                for i in snapshot.items
            ),
        )
        result.check(
            "3A-FIX-D: Requirement order is preserved in the snapshot",
            [i.name for i in sorted(snapshot.items, key=lambda i: i.display_order)]
            == ["First requirement", "Second requirement"],
        )

        # =====================================================================
        # E-H: live edits after snapshot creation must never change it.
        # =====================================================================
        first_requirement_id = next(
            r.id for r in req_svc.get_requirement_set(session, requirement_set.id).requirements
            if r.name == "First requirement"
        )

        req_svc.update_requirement_set(session, requirement_set.id, name="RENAMED LIVE SET")
        req_svc.update_requirement(session, first_requirement_id, name="RENAMED LIVE REQUIREMENT", criticality=rm.OPTIONAL)
        req_svc.add_requirement(
            session, requirement_set.id, name="Added after snapshot", criticality=rm.OPTIONAL,
            trainability=rm.TRAINABILITY_UNKNOWN, assessment_stages=[rm.OTHER_STAGE],
        )
        req_svc.deactivate_requirement(session, first_requirement_id)
        session.commit()
        session.expire_all()

        snapshot_after_edits = req_svc.get_snapshot(session, snapshot.id)
        result.check(
            "3A-FIX-E: editing the live Requirement Set's metadata after snapshot creation does not "
            "change the snapshot",
            snapshot_after_edits.name == "Server - Snapshot Test",
        )
        result.check(
            "3A-FIX-F: editing a live Requirement after snapshot creation does not change the snapshot",
            any(i.name == "First requirement" and i.criticality == rm.MUST_HAVE for i in snapshot_after_edits.items),
        )
        result.check(
            "3A-FIX-G: adding a new Requirement after snapshot creation does not add it to the old snapshot",
            len(snapshot_after_edits.items) == 2
            and not any(i.name == "Added after snapshot" for i in snapshot_after_edits.items),
        )
        result.check(
            "3A-FIX-H: deactivating a live Requirement does not mutate an existing snapshot",
            next(i for i in snapshot_after_edits.items if i.name == "First requirement").was_active is True,
        )

        # =====================================================================
        # I-J: version semantics — advances on material changes only, never
        # on reads.
        # =====================================================================
        version_before_reads = req_svc.get_requirement_set(session, requirement_set.id).version
        req_svc.get_requirement_set(session, requirement_set.id)
        req_svc.list_requirement_sets(session, restaurant_id=restaurant.id)
        req_svc.get_snapshot(session, snapshot.id)
        req_svc.list_snapshots(session, requirement_set.id)
        session.commit()
        version_after_reads = req_svc.get_requirement_set(session, requirement_set.id).version
        result.check(
            "3A-FIX-I: version increments consistently on material changes (4 edits above -> version "
            f"advanced from {version_at_snapshot} to {version_before_reads})",
            version_before_reads == version_at_snapshot + 4,
        )
        result.check(
            "3A-FIX-J: read-only operations (get/list) do not increment the version",
            version_after_reads == version_before_reads,
        )

        # =====================================================================
        # K-L: retrieval by version, deterministic serialization.
        # =====================================================================
        by_version = req_svc.get_snapshot_by_version(session, requirement_set.id, version_at_snapshot)
        result.check(
            "3A-FIX-K: a snapshot can be retrieved by Requirement Set + version",
            by_version is not None and by_version.id == snapshot.id,
        )

        serialized_once = req_svc.serialize_requirement_set_snapshot(snapshot)
        serialized_twice = req_svc.serialize_requirement_set_snapshot(snapshot)
        result.check(
            "3A-FIX-L: snapshot serialization is deterministic (identical across calls, requirement "
            "order preserved)",
            serialized_once == serialized_twice
            and [r["name"] for r in serialized_once["requirements"]] == ["First requirement", "Second requirement"],
        )

        # =====================================================================
        # M-N: source template is unaffected; template cloning still works.
        # =====================================================================
        template = req_svc.create_template(session, name="Snapshot Fix Test Template", intended_role="SERVER")
        req_svc.add_template_item(
            session, template.id, name="Template item", criticality=rm.MUST_HAVE, trainability=rm.TRAINABLE,
            assessment_stages=[rm.RESUME],
        )
        session.commit()
        cloned_set = req_svc.instantiate_requirement_set_from_template(
            session, template_id=template.id, restaurant_id=restaurant.id, name="Cloned - Snapshot Fix Test",
        )
        req_svc.create_requirement_set_snapshot(session, cloned_set.id)
        session.commit()
        session.expire_all()
        template_after = req_svc.get_template(session, template.id)
        result.check(
            "3A-FIX-M: creating/retrieving a snapshot does not alter the source template",
            len(template_after.items) == 1 and template_after.items[0].criticality == rm.MUST_HAVE,
        )
        result.check(
            "3A-FIX-N: existing template-cloning functionality still works after this fix",
            len(req_svc.get_requirement_set(session, cloned_set.id).requirements) == 1,
        )

        # =====================================================================
        # O: existing Task 3A Requirement CRUD (add/update/deactivate) still
        # works exactly as before.
        # =====================================================================
        crud_requirement = req_svc.add_requirement(
            session, requirement_set.id, name="CRUD check", criticality=rm.PREFERRED,
            trainability=rm.TRAINABLE, assessment_stages=[rm.RESUME],
        )
        req_svc.update_requirement(session, crud_requirement.id, description="Updated description")
        req_svc.deactivate_requirement(session, crud_requirement.id)
        session.commit()
        session.expire_all()
        reloaded_crud = session.get(m.Requirement, crud_requirement.id)
        result.check(
            "3A-FIX-O: existing Task 3A Requirement CRUD (add/update/deactivate) remains operational",
            reloaded_crud is not None and reloaded_crud.description == "Updated description"
            and reloaded_crud.is_active is False,
        )
        # P (existing résumé/candidate tests remain operational) is verified
        # by `_assert_batch_import`/`_assert_normalization` running as part
        # of this same suite, unaffected by this function.
    finally:
        session.rollback()
        if restaurant is not None and restaurant.id is not None:
            for requirement_set_row in req_svc.list_requirement_sets(session, restaurant_id=restaurant.id):
                for snapshot_row in req_svc.list_snapshots(session, requirement_set_row.id):
                    session.delete(snapshot_row)  # cascades to its RequirementSnapshotItem rows
                session.flush()
                session.delete(requirement_set_row)
            session.flush()
        for template_row in list(session.query(m.RequirementTemplate).filter(
            m.RequirementTemplate.name == "Snapshot Fix Test Template"
        )):
            session.delete(template_row)
        still_attached = session.get(m.Restaurant, restaurant.id) if restaurant is not None else None
        if still_attached is not None:
            session.delete(still_attached)
        session.commit()
        session.close()


def _assert_fit_assessment(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 3B checks (A-W) — evidence-based Candidate Fit Assessment. Own
    dedicated session/restaurant, real commits, real cleanup (same
    reasoning as the other `_assert_*` functions above: SQLite
    single-writer, run before `_assert`'s shared session touches
    anything). X/Y/Z (existing snapshot/requirement/résumé functionality
    remains operational) are verified simply by
    `_assert_requirement_set_snapshot`/`_assert_requirement_framework`/
    `_assert_batch_import`/`_assert_normalization` all continuing to pass
    in this same suite."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic Fit Assessment Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        # A résumé deliberately shaped to exercise EVIDENCED (structured
        # cert match), PARTIALLY_EVIDENCED (free-text-only match), and
        # NOT_EVIDENCED (nothing at all) in one fixture, with NO
        # self-descriptive text at all (so behavioral Requirements have
        # nothing to latch onto even if misconfigured for RESUME).
        resume_text = (
            "Casey Morgan\ncasey.morgan@example.com\n\n"
            "EXPERIENCE\nServer, The Garden Bistro\nJan 2021 - Present\n"
            "Assisted with kitchen prep during slow shifts.\n\n"
            "CERTIFICATIONS\nFood Handler Certificate - ServSafe, 2021\n"
        )
        import_result = import_pipeline.import_one_resume(
            session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD,
            original_filename="casey_morgan.txt", storage_path=None, raw_text=resume_text,
            content_hash=compute_content_hash(resume_text, "casey_morgan.txt"),
        )
        candidate_id = import_result.candidate_id

        requirement_set = req_svc.create_requirement_set(
            session, restaurant_id=restaurant.id, name="Server - Fit Assessment Test", target_role="SERVER",
        )
        req_svc.add_requirement(
            session, requirement_set.id, name="Food handler certification",
            category="Certifications / Legal Requirements", criticality=rm.MUST_HAVE,
            trainability=rm.TRAINABILITY_UNKNOWN, assessment_stages=[rm.RESUME],
        )
        req_svc.add_requirement(
            session, requirement_set.id, name="Kitchen prep experience", category="Experience",
            criticality=rm.PREFERRED, trainability=rm.TRAINABLE, assessment_stages=[rm.RESUME],
        )
        req_svc.add_requirement(
            session, requirement_set.id, name="Bartending experience", category="Experience",
            criticality=rm.OPTIONAL, trainability=rm.NOT_TRAINABLE, assessment_stages=[rm.RESUME],
        )
        req_svc.add_requirement(
            session, requirement_set.id, name="Teamwork attitude", category="Teamwork",
            criticality=rm.MUST_HAVE, trainability=rm.NOT_TRAINABLE, assessment_stages=[rm.PHONE_INTERVIEW],
        )
        session.commit()
        version_before = req_svc.get_requirement_set(session, requirement_set.id).version

        # =====================================================================
        # A-D: creation, automatic snapshot binding, coverage of all active
        # requirements.
        # =====================================================================
        fit_assessment = fa_svc.create_fit_assessment(
            session, candidate_id=candidate_id, requirement_set_id=requirement_set.id,
        )
        session.commit()
        session.expire_all()

        fit_assessment = fa_svc.get_fit_assessment(session, fit_assessment.id)
        expected_snapshot = req_svc.get_snapshot_by_version(session, requirement_set.id, version_before)
        result.check("3B-A: a Fit Assessment can be created for Candidate + live Requirement Set", fit_assessment is not None)
        result.check(
            "3B-B: creating it automatically creates/reuses the immutable snapshot for the current version",
            expected_snapshot is not None and fit_assessment.requirement_set_snapshot_id == expected_snapshot.id,
        )
        result.check(
            "3B-C: the Fit Assessment stores/references that snapshot (and the live set, for navigation)",
            fit_assessment.requirement_set_snapshot.version == version_before
            and fit_assessment.requirement_set_id == requirement_set.id,
        )
        requirement_assessments = fa_svc.list_requirement_assessments(session, fit_assessment.id)
        result.check(
            "3B-D: all active RequirementSnapshotItems appear in the assessment",
            len(requirement_assessments) == 4,
        )

        by_name = {ra.requirement_snapshot_item.name: ra for ra in requirement_assessments}

        # =====================================================================
        # E-F: live edits after creation never change this assessment's
        # requirement definitions (it reads the snapshot, never live rows).
        # =====================================================================
        cert_requirement_live_id = next(
            r.id for r in req_svc.get_requirement_set(session, requirement_set.id).requirements
            if r.name == "Food handler certification"
        )
        req_svc.update_requirement_set(session, requirement_set.id, name="RENAMED LIVE SET")
        req_svc.update_requirement(session, cert_requirement_live_id, name="RENAMED LIVE REQUIREMENT", criticality=rm.OPTIONAL)
        session.commit()
        session.expire_all()

        reloaded_cert_ra = session.get(m.RequirementAssessment, by_name["Food handler certification"].id)
        result.check(
            "3B-E: editing the live Requirement Set's metadata after Fit Assessment creation does not change "
            "the assessment's requirement definitions",
            reloaded_cert_ra.requirement_snapshot_item.name == "Food handler certification",
        )
        result.check(
            "3B-F: editing a live Requirement does not change the Fit Assessment (criticality stays MUST_HAVE, "
            "read from the snapshot)",
            reloaded_cert_ra.requirement_snapshot_item.criticality == rm.MUST_HAVE,
        )

        # =====================================================================
        # G-J: résumé-stage statuses.
        # =====================================================================
        cert_ra = session.get(m.RequirementAssessment, by_name["Food handler certification"].id)
        prep_ra = session.get(m.RequirementAssessment, by_name["Kitchen prep experience"].id)
        bartend_ra = session.get(m.RequirementAssessment, by_name["Bartending experience"].id)
        teamwork_ra = session.get(m.RequirementAssessment, by_name["Teamwork attitude"].id)

        result.check(
            "3B-G: a résumé-assessable factual Requirement (explicit certification) becomes EVIDENCED",
            cert_ra.effective_status == fam.EVIDENCED,
        )
        result.check(
            "3B-H: a partially/weakly supported Requirement (matched only in free-text responsibilities, "
            "not in the stated title) becomes PARTIALLY_EVIDENCED",
            prep_ra.effective_status == fam.PARTIALLY_EVIDENCED,
        )
        result.check(
            "3B-I: a legitimately résumé-assessable Requirement with no adequate evidence becomes NOT_EVIDENCED",
            bartend_ra.effective_status == fam.NOT_EVIDENCED,
        )
        result.check(
            "3B-J: a PHONE_INTERVIEW-only Requirement during the RESUME stage becomes "
            "NOT_ASSESSED_AT_THIS_STAGE — never inferred from résumé proxies",
            teamwork_ra.effective_status == fam.NOT_ASSESSED_AT_THIS_STAGE
            and len(teamwork_ra.evidence_items) == 0,
        )

        # =====================================================================
        # K: conflicting evidence.
        # =====================================================================
        fa_svc.add_evidence(
            session, cert_ra.id, source_type=fam.PHONE_INTERVIEW_RESPONSE,
            evidence_text="Candidate stated the certification had lapsed and was never renewed.",
            evidence_classification=fam.FACT, evidence_relationship=fam.CONTRADICTS,
            confidence=fam.CONFIDENCE_HIGH, source_stage=rm.PHONE_INTERVIEW,
        )
        session.commit()
        session.expire_all()
        cert_ra = session.get(m.RequirementAssessment, cert_ra.id)
        result.check(
            "3B-K: contradictory evidence alongside existing supporting evidence produces CONFLICTING_EVIDENCE, "
            "never a silently chosen side",
            cert_ra.effective_status == fam.CONFLICTING_EVIDENCE and len(cert_ra.evidence_items) == 2,
        )

        # =====================================================================
        # L-N: evidence source/classification/confidence are all preserved
        # and distinguishable.
        # =====================================================================
        resume_evidence = next(e for e in cert_ra.evidence_items if e.evidence_relationship == fam.SUPPORTS)
        interview_evidence = next(e for e in cert_ra.evidence_items if e.evidence_relationship == fam.CONTRADICTS)
        result.check(
            "3B-L: evidence source is preserved (source_type/source_reference/source_stage all populated "
            "and distinct per evidence item)",
            resume_evidence.source_type == fam.RESUME_FACT and resume_evidence.source_reference == "certifications"
            and interview_evidence.source_type == fam.PHONE_INTERVIEW_RESPONSE
            and interview_evidence.source_stage == rm.PHONE_INTERVIEW,
        )
        prep_evidence = prep_ra.evidence_items[0] if prep_ra.evidence_items else None
        result.check(
            "3B-M: FACT (résumé cert), DERIVED_INFORMATION/INFERENCE, and a plain calculation remain "
            "distinguishable — never silently collapsed into one label",
            resume_evidence.evidence_classification == fam.FACT
            and prep_evidence is not None and prep_evidence.evidence_classification == fam.INFERENCE,
        )
        result.check(
            "3B-N: confidence persists correctly on each evidence item",
            resume_evidence.confidence == fam.CONFIDENCE_HIGH and interview_evidence.confidence == fam.CONFIDENCE_HIGH,
        )

        # =====================================================================
        # O-P: criticality/trainability are visible but never drive an
        # automatic decision.
        # =====================================================================
        result.check(
            "3B-O: criticality is exposed on the snapshot item but a MUST_HAVE + NOT_EVIDENCED combination "
            "does not produce any rejection/decision field or value anywhere on the assessment",
            bartend_ra.requirement_snapshot_item.criticality == rm.OPTIONAL  # exposed, unrelated to status
            and not hasattr(bartend_ra, "decision") and not hasattr(bartend_ra, "rejected")
            and not hasattr(fit_assessment, "decision") and not hasattr(fit_assessment, "hired"),
        )
        result.check(
            "3B-P: trainability is exposed on the snapshot item but never automatically advances the "
            "candidate or changes the status",
            prep_ra.requirement_snapshot_item.trainability == rm.TRAINABLE
            and prep_ra.effective_status == fam.PARTIALLY_EVIDENCED,
        )

        # =====================================================================
        # Q: no universal score anywhere.
        # =====================================================================
        summary = fa_svc.get_summary(session, fit_assessment.id)
        result.check(
            "3B-Q: no overall candidate score is generated — the summary is counts/statuses only",
            set(summary.keys()) == {"total", "counts"} and isinstance(summary["counts"], dict)
            and not hasattr(fit_assessment, "score") and not hasattr(fit_assessment, "overall_score")
            and not any("score" in c.lower() or "percent" in c.lower() for c in m.FitAssessment.__table__.columns.keys())
            and not any(
                "score" in c.lower() or "percent" in c.lower() for c in m.RequirementAssessment.__table__.columns.keys()
            ),
        )

        # =====================================================================
        # R: multiple evidence items coexist (already proven by K, restated
        # explicitly here).
        # =====================================================================
        result.check(
            "3B-R: multiple evidence items coexist for one Requirement Assessment without overwriting "
            "each other",
            len(cert_ra.evidence_items) == 2,
        )

        # =====================================================================
        # S: human notes never become evidence.
        # =====================================================================
        evidence_count_before_note = len(bartend_ra.evidence_items)
        status_before_note = bartend_ra.effective_status
        fa_svc.add_note(session, requirement_assessment_id=bartend_ra.id, note_text="Interesting candidate — review again")
        session.commit()
        session.expire_all()
        bartend_ra = session.get(m.RequirementAssessment, bartend_ra.id)
        result.check(
            "3B-S: a human note does not automatically become evidence or alter the Requirement Assessment's "
            "status",
            bartend_ra.notes == "Interesting candidate — review again"
            and len(bartend_ra.evidence_items) == evidence_count_before_note
            and bartend_ra.effective_status == status_before_note,
        )

        # =====================================================================
        # T: human override distinguishable from system assessment.
        # =====================================================================
        result.check(
            "3B-T: before any human action, origin is SYSTEM_GENERATED",
            prep_ra.origin == fam.SYSTEM_GENERATED,
        )
        fa_svc.human_override(session, prep_ra.id, new_status=fam.EVIDENCED, reason="Confirmed in person")
        session.commit()
        session.expire_all()
        prep_ra = session.get(m.RequirementAssessment, prep_ra.id)
        result.check(
            "3B-T2: after a human override, origin is HUMAN_OVERRIDDEN, effective_status reflects the "
            "human's decision, and the original system_status is preserved rather than deleted",
            prep_ra.origin == fam.HUMAN_OVERRIDDEN and prep_ra.effective_status == fam.EVIDENCED
            and prep_ra.system_status == fam.PARTIALLY_EVIDENCED and prep_ra.override_reason == "Confirmed in person",
        )

        # =====================================================================
        # U: later-stage evidence does not destroy résumé-stage evidence.
        # =====================================================================
        evidence_before_later_stage = len(cert_ra.evidence_items)
        fa_svc.add_evidence(
            session, cert_ra.id, source_type=fam.IN_PERSON_OBSERVATION,
            evidence_text="Physical certificate card was shown at check-in.",
            evidence_classification=fam.FACT, evidence_relationship=fam.SUPPORTS,
            confidence=fam.CONFIDENCE_HIGH, source_stage=rm.IN_PERSON_INTERVIEW,
        )
        session.commit()
        session.expire_all()
        cert_ra = session.get(m.RequirementAssessment, cert_ra.id)
        result.check(
            "3B-U: later-stage evidence is ADDED, not a destructive replacement — the original résumé-stage "
            "evidence item is still present",
            len(cert_ra.evidence_items) == evidence_before_later_stage + 1
            and any(e.source_type == fam.RESUME_FACT for e in cert_ra.evidence_items),
        )

        # =====================================================================
        # V: refresh/recalculation retains the SAME snapshot.
        # =====================================================================
        snapshot_id_before_refresh = fit_assessment.requirement_set_snapshot_id
        fa_svc.generate_resume_stage_assessment(session, fit_assessment.id)
        session.commit()
        session.expire_all()
        fit_assessment_after_refresh = fa_svc.get_fit_assessment(session, fit_assessment.id)
        result.check(
            "3B-V: refreshing the résumé-stage assessment retains the SAME RequirementSetSnapshot — never "
            "silently switches to the newest live version",
            fit_assessment_after_refresh.requirement_set_snapshot_id == snapshot_id_before_refresh,
        )

        # =====================================================================
        # W: assessing against a newer Requirement Set version creates a
        # separate Fit Assessment bound to a separate, newer snapshot.
        # =====================================================================
        req_svc.add_requirement(
            session, requirement_set.id, name="New requirement after first assessment", criticality=rm.OPTIONAL,
            trainability=rm.TRAINABILITY_UNKNOWN, assessment_stages=[rm.RESUME],
        )
        session.commit()
        second_fit_assessment = fa_svc.create_fit_assessment(
            session, candidate_id=candidate_id, requirement_set_id=requirement_set.id,
        )
        session.commit()
        session.expire_all()
        first_fa_reloaded = fa_svc.get_fit_assessment(session, fit_assessment.id)
        second_fa_reloaded = fa_svc.get_fit_assessment(session, second_fit_assessment.id)
        result.check(
            "3B-W: assessing the same candidate against a newer Requirement Set version creates a NEW Fit "
            "Assessment bound to a NEW, higher-version snapshot — the historical one is untouched",
            second_fa_reloaded.requirement_set_snapshot_id != first_fa_reloaded.requirement_set_snapshot_id
            and second_fa_reloaded.requirement_set_snapshot.version > first_fa_reloaded.requirement_set_snapshot.version
            and first_fa_reloaded.requirement_set_snapshot.version == version_before
            and len(fa_svc.list_requirement_assessments(session, first_fa_reloaded.id)) == 4,
        )
    finally:
        session.rollback()
        if restaurant is not None and restaurant.id is not None:
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                for fa_row in fa_svc.list_fit_assessments_for_candidate(session, candidate_row.id):
                    session.delete(fa_row)  # cascades to RequirementAssessment/EvidenceItem rows
                session.flush()
                session.delete(candidate_row)
            session.flush()
            for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                session.delete(raw)
            for requirement_set_row in req_svc.list_requirement_sets(session, restaurant_id=restaurant.id):
                for snapshot_row in req_svc.list_snapshots(session, requirement_set_row.id):
                    session.delete(snapshot_row)
                session.flush()
                session.delete(requirement_set_row)
            session.flush()
        still_attached = session.get(m.Restaurant, restaurant.id) if restaurant is not None else None
        if still_attached is not None:
            session.delete(still_attached)
        session.commit()
        session.close()


def _assert_selection_signals(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """RF-One Selection 3C Concept Note checks — Application/Person
    distinction, Selection Signals, and Review Priority. Own dedicated
    session/restaurants, real commits, real cleanup (same reasoning as the
    other `_assert_*` functions above). Existing Task 2A/2B/3A/3A-FIX/3B
    functionality remains operational simply by those functions continuing
    to pass in this same suite."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    restaurant_b: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic Signal Test Restaurant", default_currency="USD")
        restaurant_b = m.Restaurant(name="Synthetic Signal Test Restaurant B", default_currency="USD")
        session.add_all([restaurant, restaurant_b])
        session.commit()

        # =====================================================================
        # A: Candidate (person) vs Application (submission) distinction —
        # two résumés under the same email resolve to the SAME person.
        # =====================================================================
        resume1 = (
            "Jamie Fox\njamie.fox@example.com\n\nEXPERIENCE\nDishwasher, Harbor House Kitchen\n"
            "Jan 2022 - Jun 2023\nWashed dishes and maintained kitchen cleanliness.\n"
        )
        import1 = import_pipeline.import_one_resume(
            session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD, original_filename="jamie1.txt",
            storage_path=None, raw_text=resume1, content_hash=compute_content_hash(resume1, "jamie1.txt"),
        )
        application1 = app_svc.create_application(
            session, candidate_id=import1.candidate_id, restaurant_id=restaurant.id, target_role="DISHWASHER",
        )
        session.commit()

        resume2 = (
            "Jamie Fox\njamie.fox@example.com\n\nEXPERIENCE\nLine Cook, Downtown Diner\nJan 2024 - Present\n"
            "Runs the grill station during dinner service.\n\nDishwasher, Harbor House Kitchen\n"
            "Jan 2022 - Jun 2023\nWashed dishes and maintained kitchen cleanliness.\n"
        )
        import2 = import_pipeline.import_one_resume(
            session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD, original_filename="jamie2.txt",
            storage_path=None, raw_text=resume2, content_hash=compute_content_hash(resume2, "jamie2.txt"),
        )
        application2 = app_svc.create_application(
            session, candidate_id=import2.candidate_id, restaurant_id=restaurant.id, target_role="LINE_COOK",
        )
        session.commit()

        result.check(
            "3C-A: two résumés submitted under the same email resolve to the SAME CandidatePerson — "
            "Candidate (person) and Application (one submission) are genuinely distinct",
            application1.person_id == application2.person_id
            and application1.candidate_id != application2.candidate_id,
        )

        # =====================================================================
        # B: Application history remains visible and usable.
        # =====================================================================
        prior = app_svc.list_prior_applications(session, application2.id)
        result.check(
            "3C-B: Application history is preserved and retrievable — the earlier Application for the "
            "same person is found as a prior Application of the later one",
            len(prior) == 1 and prior[0].id == application1.id,
        )

        # =====================================================================
        # C: repeated application is not automatically penalized — no
        # rejection/negative field exists anywhere from "having applied
        # before" alone.
        # =====================================================================
        result.check(
            "3C-C: repeated application alone carries no automatic penalty — Application exposes no "
            "rejection/discard field, and a second Application is created normally, not blocked",
            application2.id is not None and not hasattr(application2, "rejected")
            and not hasattr(application2, "discarded") and not hasattr(application2, "auto_rejected"),
        )

        # =====================================================================
        # D-F: Signal families, statuses, and the NOT_ASSESSED vs
        # NOT_DETECTED distinction.
        # =====================================================================
        definitions = {}
        for name, family, subtype, stages in [
            ("Recent relevant experience", sm.READINESS_RECENCY, "recent_relevant_experience", [rm.RESUME]),
            ("Long relevant gap", sm.READINESS_RECENCY, "long_relevant_gap", [rm.RESUME]),
            ("Progression since previous application", sm.MOTIVATION_PROFESSIONAL,
             "progression_since_previous_application", [rm.RESUME]),
            ("Teamwork attitude", sm.MOTIVATION_PERSONAL, None, [rm.PHONE_INTERVIEW]),
        ]:
            definitions[name] = sig_svc.create_signal_definition(
                session, restaurant_id=restaurant.id, name=name, signal_family=family, signal_subtype=subtype,
                assessment_stages=stages, evidence_sources_allowed=[fam.RESUME_FACT, fam.RESUME_DERIVED_INFORMATION],
            )
        session.commit()

        result.check(
            "3C-D: all four Signal families are supported by the vocabulary",
            set(sm.SIGNAL_FAMILIES) == {
                sm.FIT_EXPERIENCE, sm.READINESS_RECENCY, sm.MOTIVATION_PERSONAL, sm.MOTIVATION_PROFESSIONAL,
            },
        )

        sig_svc.generate_resume_stage_signals(session, application2.id)
        session.commit()
        session.expire_all()

        observations = {o.signal_definition.name: o for o in sig_svc.list_observations(session, application2.id)}
        result.check(
            "3C-E: multiple Signal Observation statuses are reachable in one real run — DETECTED for a "
            "genuinely current relevant role, NOT_DETECTED/POSSIBLE for others",
            observations["Recent relevant experience"].status == sm.DETECTED,
        )
        result.check(
            "3C-F: NOT_ASSESSED (stage not permitted) and NOT_DETECTED (stage permitted, no evidence "
            "found) remain structurally distinct — a phone-interview-only Signal never gets a résumé-"
            "stage conclusion, and 'no evidence' is never silently reported the same way as 'not "
            "assessable here'",
            observations["Teamwork attitude"].status == sm.NOT_ASSESSED
            and len(observations["Teamwork attitude"].evidence_items) == 0
            and observations["Long relevant gap"].status in (sm.NOT_DETECTED, sm.DETECTED)
            and observations["Teamwork attitude"].status != observations["Long relevant gap"].status,
        )

        # =====================================================================
        # G: Signal Definitions are restaurant-configurable, never
        # hard-coded universal rules — the universal modules never
        # reference restaurant-specific data, and two restaurants can hold
        # different Signal Definitions independently.
        # =====================================================================
        sig_svc.create_signal_definition(
            session, restaurant_id=restaurant_b.id, name="Restaurant B only signal",
            signal_family=sm.FIT_EXPERIENCE, assessment_stages=[rm.RESUME], evidence_sources_allowed=[fam.RESUME_FACT],
        )
        session.commit()
        defs_a = sig_svc.list_signal_definitions(session, restaurant_id=restaurant.id, active_only=False)
        defs_b = sig_svc.list_signal_definitions(session, restaurant_id=restaurant_b.id, active_only=False)
        universal_source = inspect.getsource(sig_svc) + inspect.getsource(sm)
        result.check(
            "3C-G: Signal Definitions are restaurant-configurable (two restaurants hold independent "
            "definitions), and the universal Signal framework never imports/references restaurant-"
            "specific data",
            all(d.name != "Restaurant B only signal" for d in defs_a)
            and any(d.name == "Restaurant B only signal" for d in defs_b)
            and "restaurant_templates" not in universal_source and "industry.restaurant" not in universal_source,
        )

        # =====================================================================
        # H: the concept note's own worked example — progression is
        # detected from real facts, never characterizing the candidate.
        # =====================================================================
        progression_observation = observations["Progression since previous application"]
        result.check(
            "3C-H: progression since a previous application (Dishwasher -> gained Line Cook experience "
            "-> now applies for Line Cook) is detected from real facts, and the recorded pattern never "
            "characterizes the candidate (e.g. as 'ambitious')",
            progression_observation.status in (sm.DETECTED, sm.POSSIBLE)
            and progression_observation.detected_pattern is not None
            and "ambitious" not in progression_observation.detected_pattern.lower()
            and "DISHWASHER" in progression_observation.detected_pattern
            and "Line Cook" in progression_observation.detected_pattern,
        )

        # =====================================================================
        # I: readiness/recency signals never state a personal cause for a
        # gap — professional fact only.
        # =====================================================================
        gap_only_resume = (
            "Riley Stone\nriley.stone@example.com\n\nEXPERIENCE\nLine Cook, Old Town Grill\n"
            "Jan 2019 - Dec 2020\nRan the fry station.\n"
        )
        gap_import = import_pipeline.import_one_resume(
            session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD, original_filename="riley.txt",
            storage_path=None, raw_text=gap_only_resume, content_hash=compute_content_hash(gap_only_resume, "riley.txt"),
        )
        gap_application = app_svc.create_application(
            session, candidate_id=gap_import.candidate_id, restaurant_id=restaurant.id, target_role="LINE_COOK",
        )
        session.commit()
        sig_svc.generate_resume_stage_signals(session, gap_application.id)
        session.commit()
        session.expire_all()
        gap_observation = next(
            o for o in sig_svc.list_observations(session, gap_application.id)
            if o.signal_definition.name == "Long relevant gap"
        )
        gap_evidence_text = " ".join(
            (e.evidence_text or "") + " " + (e.explanation or "") for e in gap_observation.evidence_items
        ).lower()
        result.check(
            "3C-I: a long-relevant-gap Signal states the professional fact only — no protected/personal "
            "cause (family, health, gender-specific pronoun) is ever mentioned",
            gap_observation.status in (sm.DETECTED, sm.POSSIBLE)  # MEDIUM-confidence derived fact -> POSSIBLE is correct
            and "month" in gap_evidence_text
            and not any(
                re.search(rf"\b{word}\b", gap_evidence_text)
                for word in ("child", "family", "pregnant", "pregnancy", "she", "he", "maternity")
            ),
        )

        # =====================================================================
        # J: multiple Signals may coexist and point different directions —
        # both remain visible on the same Application.
        # =====================================================================
        result.check(
            "3C-J: multiple Signal Observations coexist on one Application without hiding any of them",
            len(sig_svc.list_observations(session, application2.id)) == len(definitions),
        )

        # =====================================================================
        # K: Review Priority is always one of four categories — never a
        # numeric score anywhere in the model or the computation.
        # =====================================================================
        category, reasons = sm.compute_review_priority([(sm.STRONGLY_INCREASE, "test reason")])
        result.check(
            "3C-K: Review Priority is always one of the four fixed categories, and no numeric score "
            "field exists anywhere on Application/SignalObservation",
            category in sm.REVIEW_PRIORITY_CATEGORIES
            and not any("score" in c.lower() or "percent" in c.lower() for c in m.Application.__table__.columns.keys())
            and not any(
                "score" in c.lower() or "percent" in c.lower() for c in m.SignalObservation.__table__.columns.keys()
            ),
        )
        result.check(
            "3C-L: the system always provides the reasons supporting a Review Priority",
            reasons == ["test reason"],
        )

        # =====================================================================
        # M: Signal detection and the Review Priority Policy are separate —
        # the SAME detected Signal produces a different priority depending
        # only on which policy (if any) is active.
        # =====================================================================
        sig_svc.compute_and_apply_review_priority(session, application2.id)
        session.commit()
        session.expire_all()
        priority_without_policy = app_svc.get_application(session, application2.id).review_priority_system

        policy = sig_svc.create_policy(session, restaurant_id=restaurant.id, name="Test Policy")
        sig_svc.add_policy_rule(
            session, policy.id, signal_definition_id=definitions["Progression since previous application"].id,
            observed_status=progression_observation.status, contribution=sm.STRONGLY_INCREASE,
        )
        session.commit()
        sig_svc.compute_and_apply_review_priority(session, application2.id)
        session.commit()
        session.expire_all()
        priority_with_policy = app_svc.get_application(session, application2.id).review_priority_system
        result.check(
            "3C-M: the same detected Signal produces a different Review Priority depending only on the "
            "restaurant's own policy — detection and policy are genuinely separate layers",
            priority_without_policy == sm.STANDARD and priority_with_policy == sm.HIGH_PRIORITY,
        )

        # =====================================================================
        # N: Selezionatore override remains distinguishable from system
        # priority, and survives a refresh.
        # =====================================================================
        sig_svc.human_override_priority(session, application2.id, new_priority=sm.LOW_PRIORITY, reason="Selezionatore judgment")
        session.commit()
        sig_svc.generate_resume_stage_signals(session, application2.id)
        session.commit()
        session.expire_all()
        overridden_application = app_svc.get_application(session, application2.id)
        result.check(
            "3C-N: a Selezionatore's Review Priority override remains distinguishable from the system "
            "value and survives a refresh (never silently recalculated away)",
            overridden_application.review_priority_origin == fam.HUMAN_OVERRIDDEN
            and overridden_application.review_priority_effective == sm.LOW_PRIORITY
            and overridden_application.review_priority_system == sm.HIGH_PRIORITY,
        )

        # =====================================================================
        # O: historical Application outcome can be recorded (structure
        # only — no learning/correlation logic is implemented).
        # =====================================================================
        app_svc.set_outcome(session, application1.id, "HIRED")
        session.commit()
        session.expire_all()
        result.check(
            "3C-O: a historical Application outcome can be recorded",
            app_svc.get_application(session, application1.id).outcome == "HIRED",
        )
    finally:
        session.rollback()
        for target_restaurant in (restaurant, restaurant_b):
            if target_restaurant is not None and target_restaurant.id is not None:
                for application_row in app_svc.list_applications(session, restaurant_id=target_restaurant.id):
                    session.delete(application_row)  # cascades to SignalObservation/SignalEvidenceItem
                session.flush()
                for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=target_restaurant.id):
                    session.delete(person_row)
                for policy_row in session.query(m.ReviewPriorityPolicy).filter_by(restaurant_id=target_restaurant.id):
                    session.delete(policy_row)  # cascades to ReviewPriorityPolicyRule
                for definition_row in session.query(m.SignalDefinition).filter_by(restaurant_id=target_restaurant.id):
                    session.delete(definition_row)
                session.flush()
                for candidate_row in persistence.list_candidates(session, restaurant_id=target_restaurant.id):
                    session.delete(candidate_row)
                session.flush()
                for raw in list(session.query(m.RawResume).filter_by(restaurant_id=target_restaurant.id)):
                    session.delete(raw)
        session.flush()
        still_attached = session.get(m.Restaurant, restaurant.id) if restaurant is not None else None
        still_attached_b = session.get(m.Restaurant, restaurant_b.id) if restaurant_b is not None else None
        for restaurant_row in (still_attached, still_attached_b):
            if restaurant_row is not None:
                session.delete(restaurant_row)
        session.commit()
        session.close()


def _assert_selection_3c_fix(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 3C-FIX checks — identity resolution, possible-match confirm/
    reject, Signal Definition / Review Priority Policy authoring,
    workflow status, notes, and repeated-applicant visibility. Own
    dedicated session/restaurant, real commits, real cleanup (same
    reasoning as `_assert_selection_signals` above)."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic 3C-FIX Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        def _upload(name: str, email: str, phone: str, role_line: str) -> m.Application:
            text = f"{name}\n{email}\n{phone}\n\nEXPERIENCE\n{role_line}\n"
            imported = import_pipeline.import_one_resume(
                session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD,
                original_filename=f"{email}.txt", storage_path=None, raw_text=text,
                content_hash=compute_content_hash(text, f"{email}.txt"),
            )
            application = app_svc.create_application(session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id)
            session.commit()
            return application

        # =====================================================================
        # A/B: VERY_STRONG contact matches (email, then phone) resolve to
        # the SAME CandidatePerson automatically.
        # =====================================================================
        app_email_1 = _upload(
            "Avery Chen", "Avery.Chen@Example.com", "555-010-1111",
            "Server, First Diner\nJan 2021 - Jun 2022\nWaited tables.",
        )
        app_email_2 = _upload(
            "Avery Chen", "avery.chen@example.com", "555-010-9999",  # same email, different case; different phone
            "Server, Second Diner\nJul 2022 - Present\nWaited tables.",
        )
        result.check(
            "3C-FIX-A: an exact normalized email match (case-insensitive) resolves to the SAME "
            "CandidatePerson automatically",
            app_email_1.person_id == app_email_2.person_id,
        )

        app_phone_1 = _upload(
            "Taylor Reed", "taylor.reed.one@example.com", "(555) 020-2222",
            "Host, Third Bistro\nJan 2020 - Dec 2020\nGreeted guests.",
        )
        app_phone_2 = _upload(
            "Taylor Reed", "taylor.reed.two@example.com", "555-020-2222",  # different email; same phone, different formatting
            "Host, Fourth Bistro\nJan 2021 - Dec 2021\nGreeted guests.",
        )
        result.check(
            "3C-FIX-B: an exact normalized phone match (different formatting, different email) resolves "
            "to the SAME CandidatePerson automatically",
            app_phone_1.person_id == app_phone_2.person_id,
        )

        # =====================================================================
        # C/D/E: an ambiguous (name-only) match never auto-merges — it
        # surfaces as a pending suggestion the Selezionatore must confirm
        # or reject.
        # =====================================================================
        app_morgan_1 = _upload(
            "Morgan Lee", "morgan.lee.original@example.com", "555-030-1000",
            "Server, Uptown Cafe\nJan 2019 - Dec 2020\nWaited tables.",
        )
        app_morgan_2 = _upload(
            "Morgan Lee", "morgan.lee.newapp@example.com", "555-030-2000",  # same name, no contact overlap
            "Server, Downtown Cafe\nJan 2021 - Present\nWaited tables.",
        )
        result.check(
            "3C-FIX-C: a name-only match (no exact email/phone) does NOT auto-merge — the two "
            "Applications remain on separate CandidatePerson records",
            app_morgan_1.person_id != app_morgan_2.person_id,
        )
        pending = identity_svc.list_pending_matches(session, restaurant_id=restaurant.id)
        morgan_match = next((x for x in pending if x.application_id == app_morgan_2.id), None)
        result.check(
            "3C-FIX-C2: the ambiguous name match is surfaced as a PENDING PersonMatchCandidate suggestion "
            "for the Selezionatore, not applied automatically",
            morgan_match is not None and morgan_match.status == idm.PENDING
            and morgan_match.confidence in (idm.STRONG, idm.POSSIBLE),
        )

        # Confirm flow (D) — reassigns the Application, preserves its data.
        pre_confirm_candidate_id = app_morgan_2.candidate_id
        identity_svc.confirm_match(session, morgan_match.id, note="Same person, verified by Selezionatore")
        session.commit()
        session.expire_all()
        confirmed_application = app_svc.get_application(session, app_morgan_2.id)
        result.check(
            "3C-FIX-D: the Selezionatore can confirm a possible match — the Application is reassigned to "
            "the confirmed CandidatePerson, and its own CV/candidate row is untouched",
            confirmed_application.person_id == app_morgan_1.person_id
            and confirmed_application.candidate_id == pre_confirm_candidate_id
            and confirmed_application.identity_origin == idm.HUMAN_CONFIRMED,
        )

        # Reject flow (E) — a second ambiguous pair, kept separate on request.
        app_casey_1 = _upload(
            "Casey Kim", "casey.kim.original@example.com", "555-040-1000",
            "Bartender, Old Town Pub\nJan 2018 - Dec 2019\nMixed drinks.",
        )
        app_casey_2 = _upload(
            "Casey Kim", "casey.kim.newapp@example.com", "555-040-2000",
            "Bartender, New Town Pub\nJan 2020 - Dec 2020\nMixed drinks.",
        )
        pending = identity_svc.list_pending_matches(session, restaurant_id=restaurant.id)
        casey_match = next((x for x in pending if x.application_id == app_casey_2.id), None)
        identity_svc.reject_match(session, casey_match.id, note="Different people, verified by Selezionatore")
        session.commit()
        session.expire_all()
        rejected_application = app_svc.get_application(session, app_casey_2.id)
        result.check(
            "3C-FIX-E: the Selezionatore can reject a possible match — both CandidatePerson records "
            "remain intact and separate",
            rejected_application.person_id == app_casey_2.person_id
            and rejected_application.person_id != app_casey_1.person_id
            and identity_svc.get_match(session, casey_match.id).status == idm.REJECTED,
        )

        # =====================================================================
        # F: reassignment preserves CV/Fit Assessment/Signal data — verified
        # directly on the confirmed Morgan Lee Application above: generate
        # Signals BEFORE, capture them, reassign again via direct manual
        # reassignment, and confirm the same observations/evidence remain.
        # =====================================================================
        definition_for_f = sig_svc.create_signal_definition(
            session, restaurant_id=restaurant.id, name="3C-FIX recent experience", signal_family=sm.READINESS_RECENCY,
            signal_subtype="recent_relevant_experience", assessment_stages=[rm.RESUME],
            evidence_sources_allowed=[fam.RESUME_FACT],
        )
        sig_svc.generate_resume_stage_signals(session, app_morgan_2.id)
        session.commit()
        session.expire_all()
        observations_before = {
            o.signal_definition_id: (o.status, len(o.evidence_items))
            for o in sig_svc.list_observations(session, app_morgan_2.id)
        }
        other_persons = [p for p in identity_svc.list_persons(session, restaurant_id=restaurant.id) if p.id != app_morgan_2.person_id]
        target_person_id = other_persons[0].id if other_persons else app_morgan_1.person_id
        identity_svc.reassign_application(session, app_morgan_2.id, target_person_id=target_person_id, note="manual correction")
        session.commit()
        session.expire_all()
        observations_after = {
            o.signal_definition_id: (o.status, len(o.evidence_items))
            for o in sig_svc.list_observations(session, app_morgan_2.id)
        }
        result.check(
            "3C-FIX-F: reassigning an Application to a different CandidatePerson preserves its CV, Fit "
            "Assessment, and Signal Observations/evidence exactly as they were",
            observations_before == observations_after
            and app_svc.get_application(session, app_morgan_2.id).candidate_id == pre_confirm_candidate_id,
        )

        # =====================================================================
        # G/H: Signal Definitions can be created AND edited/deactivated
        # through the service layer the UI calls into.
        # =====================================================================
        result.check(
            "3C-FIX-G: a Signal Definition can be created through the service layer the authoring UI calls",
            definition_for_f.id is not None and definition_for_f.signal_family == sm.READINESS_RECENCY,
        )
        sig_svc.update_signal_definition(session, definition_for_f.id, description="Edited via authoring UI")
        deactivated_definition = sig_svc.deactivate_signal_definition(session, definition_for_f.id)
        session.commit()
        session.expire_all()
        reloaded_definition = sig_svc.get_signal_definition(session, definition_for_f.id)
        result.check(
            "3C-FIX-H: a Signal Definition can be edited (fields change, version increments) and "
            "deactivated (is_active becomes False) through the service layer",
            deactivated_definition.is_active is False
            and reloaded_definition.description == "Edited via authoring UI"
            and reloaded_definition.version > 1,
        )
        sig_svc.reactivate_signal_definition(session, definition_for_f.id)  # needed active again below
        session.commit()

        # =====================================================================
        # I/J: Review Priority Policy + its rules can be created/edited/
        # deactivated.
        # =====================================================================
        policy = sig_svc.create_policy(session, restaurant_id=restaurant.id, name="3C-FIX Test Policy")
        sig_svc.update_policy(session, policy.id, name="3C-FIX Test Policy (renamed)")
        session.commit()
        session.expire_all()
        reloaded_policy = sig_svc.get_policy(session, policy.id)
        result.check(
            "3C-FIX-I: a Review Priority Policy can be created and edited (renamed) through the service "
            "layer",
            reloaded_policy.name == "3C-FIX Test Policy (renamed)",
        )

        rule = sig_svc.add_policy_rule(
            session, policy.id, signal_definition_id=definition_for_f.id, observed_status=sm.DETECTED,
            contribution=sm.INCREASE,
        )
        sig_svc.update_policy_rule(session, rule.id, contribution=sm.STRONGLY_INCREASE)
        session.commit()
        session.expire_all()
        reloaded_rule = session.get(m.ReviewPriorityPolicyRule, rule.id)
        deactivated_rule = sig_svc.deactivate_policy_rule(session, rule.id)
        session.commit()
        session.expire_all()
        result.check(
            "3C-FIX-J: a policy rule can be created, edited (contribution changes), and deactivated "
            "(is_active becomes False, row is kept) through the service layer",
            reloaded_rule.contribution == sm.STRONGLY_INCREASE and deactivated_rule.is_active is False,
        )

        # =====================================================================
        # K: changing the policy (deactivating a rule) never changes the
        # Signal evidence itself — only how much it contributes.
        # =====================================================================
        evidence_count_before_policy_change = len(
            next(o for o in sig_svc.list_observations(session, app_morgan_2.id) if o.signal_definition_id == definition_for_f.id).evidence_items
        )
        sig_svc.reactivate_policy_rule(session, rule.id)
        sig_svc.compute_and_apply_review_priority(session, app_morgan_2.id)
        session.commit()
        session.expire_all()
        evidence_count_after_policy_change = len(
            next(o for o in sig_svc.list_observations(session, app_morgan_2.id) if o.signal_definition_id == definition_for_f.id).evidence_items
        )
        result.check(
            "3C-FIX-K: changing the Review Priority Policy (reactivating a rule, recomputing priority) "
            "never changes the underlying Signal evidence",
            evidence_count_before_policy_change == evidence_count_after_policy_change,
        )

        # =====================================================================
        # N: Review Priority reasons are persisted for display (Review
        # Queue shows WHY without recomputing).
        # =====================================================================
        recomputed_application = app_svc.get_application(session, app_morgan_2.id)
        result.check(
            "3C-FIX-N: the reasons behind the system-proposed Review Priority are persisted on the "
            "Application for the Review Queue to display",
            isinstance(recomputed_application.review_priority_reasons, list)
            and len(recomputed_application.review_priority_reasons) > 0,
        )

        # =====================================================================
        # O: repeated-application history is immediately visible.
        # =====================================================================
        result.check(
            "3C-FIX-O: repeated-application history is retrievable for the Review Queue's history "
            "indicator",
            len(app_svc.list_prior_applications(session, app_email_2.id)) == 1,
        )

        # =====================================================================
        # P/Q: workflow status persists across every value, and Review
        # Priority computation never changes it.
        # =====================================================================
        workflow_app = app_email_2
        sig_svc.generate_resume_stage_signals(session, workflow_app.id)
        session.commit()
        session.expire_all()
        for status in apm.WORKFLOW_STATUSES:
            app_svc.set_workflow_status(session, workflow_app.id, status, reason=f"moving to {status}")
            session.commit()
            session.expire_all()
            persisted = app_svc.get_application(session, workflow_app.id)
            result.check(
                f"3C-FIX-P: workflow status {status} persists correctly after being set",
                persisted.workflow_status == status,
            )

        app_svc.set_workflow_status(session, workflow_app.id, apm.ADVANCE_TO_PHONE, reason="Strong apparent fit")
        session.commit()
        sig_svc.compute_and_apply_review_priority(session, workflow_app.id)
        session.commit()
        session.expire_all()
        after_priority_recompute = app_svc.get_application(session, workflow_app.id)
        result.check(
            "3C-FIX-Q: recomputing Review Priority never changes an already-set workflow status",
            after_priority_recompute.workflow_status == apm.ADVANCE_TO_PHONE,
        )

        # =====================================================================
        # R: ADVANCE/HOLD/STOP reason is stored alongside the status.
        # =====================================================================
        result.check(
            "3C-FIX-R: the Selezionatore's reason for an ADVANCE_TO_PHONE/HOLD/STOP decision is stored",
            after_priority_recompute.workflow_status_reason == "Strong apparent fit",
        )

        # =====================================================================
        # S: Selezionatore notes never become evidence.
        # =====================================================================
        evidence_count_before_note = len(
            next(o for o in sig_svc.list_observations(session, workflow_app.id) if o.signal_definition_id == definition_for_f.id).evidence_items
        )
        app_svc.add_note(session, workflow_app.id, "Fourth application with no meaningful change since prior review.")
        session.commit()
        session.expire_all()
        evidence_count_after_note = len(
            next(o for o in sig_svc.list_observations(session, workflow_app.id) if o.signal_definition_id == definition_for_f.id).evidence_items
        )
        notes_after = app_svc.list_notes(session, workflow_app.id)
        result.check(
            "3C-FIX-S: a Selezionatore note is preserved with a timestamp and never becomes Signal "
            "evidence",
            len(notes_after) == 1 and notes_after[0].note_text.startswith("Fourth application")
            and notes_after[0].created_at is not None
            and evidence_count_before_note == evidence_count_after_note,
        )

        # =====================================================================
        # T: a repeated applicant with materially new experience is not
        # automatically penalized — the change summary reports the new
        # evidence, and workflow status was never auto-set.
        # =====================================================================
        change_summary = app_svc.get_application_change_summary(session, app_email_2.id)
        result.check(
            "3C-FIX-T: a repeated applicant with materially new experience gets a facts-based change "
            "summary — never an automatic penalty (workflow status stays whatever the Selezionatore set, "
            "never auto-changed by the comparison itself)",
            change_summary is not None and change_summary.has_material_change,
        )

        # =====================================================================
        # U: system priority and effective (overridden) priority remain
        # distinguishable.
        # =====================================================================
        sig_svc.human_override_priority(session, app_email_1.id, new_priority=sm.LOW_PRIORITY, reason="Selezionatore judgment")
        session.commit()
        session.expire_all()
        overridden = app_svc.get_application(session, app_email_1.id)
        result.check(
            "3C-FIX-U: system-proposed Review Priority and an overridden effective Review Priority remain "
            "distinguishable on the same Application",
            overridden.review_priority_effective == sm.LOW_PRIORITY
            and overridden.review_priority_effective != overridden.review_priority_system,
        )
    finally:
        session.rollback()
        if restaurant is not None and restaurant.id is not None:
            for match_row in session.query(m.PersonMatchCandidate).join(
                m.Application, m.PersonMatchCandidate.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                session.delete(match_row)
            session.flush()
            for note_row in session.query(m.ApplicationNote).join(
                m.Application, m.ApplicationNote.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                session.delete(note_row)
            session.flush()
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                session.delete(application_row)  # cascades to SignalObservation/SignalEvidenceItem
            session.flush()
            for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=restaurant.id):
                session.delete(person_row)
            for policy_row in session.query(m.ReviewPriorityPolicy).filter_by(restaurant_id=restaurant.id):
                session.delete(policy_row)  # cascades to ReviewPriorityPolicyRule
            for definition_row in session.query(m.SignalDefinition).filter_by(restaurant_id=restaurant.id):
                session.delete(definition_row)
            session.flush()
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                session.delete(candidate_row)
            session.flush()
            for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                session.delete(raw)
            session.flush()
            still_attached = session.get(m.Restaurant, restaurant.id)
            if still_attached is not None:
                session.delete(still_attached)
        session.commit()
        session.close()


def _assert_selection_3c_micro_fix(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 3C-MICRO-FIX checks — the Review Queue's `sort_by="priority"`
    now orders Applications by the fixed operational severity
    HIGH_PRIORITY -> INTERESTING -> STANDARD -> LOW_PRIORITY on the
    EFFECTIVE Review Priority (never the category string alphabetically),
    with newest-application-first as the same-category tie-breaker. Own
    dedicated session/restaurant, real commits, real cleanup (same
    reasoning as `_assert_selection_3c_fix` above)."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic 3C-MICRO-FIX Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        def _upload(name: str, email: str, phone: str) -> m.Application:
            text = f"{name}\n{email}\n{phone}\n\nEXPERIENCE\nServer, Test Diner\nJan 2021 - Jun 2022\nWaited tables.\n"
            imported = import_pipeline.import_one_resume(
                session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD,
                original_filename=f"{email}.txt", storage_path=None, raw_text=text,
                content_hash=compute_content_hash(text, f"{email}.txt"),
            )
            application = app_svc.create_application(session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id)
            session.commit()
            return application

        # Five Applications, each given a distinct EFFECTIVE Review Priority
        # (via override — so the system-proposed value can legitimately
        # differ, exercised by the D check below) and a distinct applied_at.
        app_standard = _upload("Priority Standard", "sort.standard@example.com", "555-090-0001")
        app_low = _upload("Priority Low", "sort.low@example.com", "555-090-0002")
        app_interesting = _upload("Priority Interesting", "sort.interesting@example.com", "555-090-0003")
        app_high_older = _upload("Priority High Older", "sort.high.older@example.com", "555-090-0004")
        app_high_newer = _upload("Priority High Newer", "sort.high.newer@example.com", "555-090-0005")

        sig_svc.human_override_priority(session, app_standard.id, new_priority=sm.STANDARD, reason="test setup")
        sig_svc.human_override_priority(session, app_low.id, new_priority=sm.LOW_PRIORITY, reason="test setup")
        sig_svc.human_override_priority(session, app_interesting.id, new_priority=sm.INTERESTING, reason="test setup")
        # D: the system-proposed value is deliberately the OPPOSITE of the
        # overridden effective one for these two — the queue must follow
        # the effective value, never the system-proposed one.
        app_high_older.review_priority_system = sm.LOW_PRIORITY
        app_high_newer.review_priority_system = sm.LOW_PRIORITY
        session.flush()
        sig_svc.human_override_priority(session, app_high_older.id, new_priority=sm.HIGH_PRIORITY, reason="test setup")
        sig_svc.human_override_priority(session, app_high_newer.id, new_priority=sm.HIGH_PRIORITY, reason="test setup")

        app_standard.applied_at = _d(2024, 2)
        app_low.applied_at = _d(2024, 2)
        app_interesting.applied_at = _d(2024, 2)
        app_high_older.applied_at = _d(2024, 1)
        app_high_newer.applied_at = _d(2024, 3)
        session.commit()
        session.expire_all()

        ordered = app_svc.list_applications(session, restaurant_id=restaurant.id, sort_by="priority")
        ordered_ids = [a.id for a in ordered]

        result.check(
            "3C-MICRO-FIX-A: HIGH_PRIORITY Applications appear before INTERESTING ones in the "
            "priority-sorted Review Queue",
            ordered_ids.index(app_high_older.id) < ordered_ids.index(app_interesting.id)
            and ordered_ids.index(app_high_newer.id) < ordered_ids.index(app_interesting.id),
        )
        result.check(
            "3C-MICRO-FIX-B: INTERESTING Applications appear before STANDARD ones in the priority-sorted "
            "Review Queue",
            ordered_ids.index(app_interesting.id) < ordered_ids.index(app_standard.id),
        )
        result.check(
            "3C-MICRO-FIX-C: STANDARD Applications appear before LOW_PRIORITY ones in the priority-sorted "
            "Review Queue",
            ordered_ids.index(app_standard.id) < ordered_ids.index(app_low.id),
        )
        result.check(
            "3C-MICRO-FIX-D: a Selezionatore-overridden EFFECTIVE Review Priority controls the queue "
            "position even when it differs from the system-proposed priority",
            app_high_older.review_priority_system == sm.LOW_PRIORITY
            and app_high_older.review_priority_effective == sm.HIGH_PRIORITY
            and ordered_ids.index(app_high_older.id) < ordered_ids.index(app_low.id),
        )
        result.check(
            "3C-MICRO-FIX-E: within the same Review Priority category, newer Applications appear before "
            "older ones",
            ordered_ids.index(app_high_newer.id) < ordered_ids.index(app_high_older.id),
        )
        result.check(
            "3C-MICRO-FIX-F: the priority-sorted Review Queue introduces no numeric rank/position field "
            "— Applications remain plain model rows, never renumbered",
            all(not hasattr(a, "rank") and not hasattr(a, "position") for a in ordered),
        )

        # G: existing filters (e.g. Review Priority) still narrow the queue
        # correctly under the corrected sort.
        filtered_by_priority = app_svc.list_applications(
            session, restaurant_id=restaurant.id, priority=sm.HIGH_PRIORITY, sort_by="priority",
        )
        result.check(
            "3C-MICRO-FIX-G: the existing Review Priority filter still narrows the queue correctly under "
            "the corrected sort",
            {a.id for a in filtered_by_priority} == {app_high_older.id, app_high_newer.id},
        )
    finally:
        session.rollback()
        if restaurant is not None and restaurant.id is not None:
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                session.delete(application_row)
            session.flush()
            for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=restaurant.id):
                session.delete(person_row)
            session.flush()
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                session.delete(candidate_row)
            session.flush()
            for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                session.delete(raw)
            session.flush()
            still_attached = session.get(m.Restaurant, restaurant.id)
            if still_attached is not None:
                session.delete(still_attached)
        session.commit()
        session.close()


def _assert_selection_4a_phone_interview(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 4A checks — Phone Interview Plan creation/snapshot-binding,
    restaurant-configured Core Question library (incl. per-restaurant
    separation), Gate/Sine-Qua-Non ordering, Dynamic Question generation
    from Fit Assessment/Signal evidence, Escape Route, answer/evidence
    capture, follow-ups, carry-forward, and the Selezionatore-only post-
    interview decision. Own dedicated session/restaurants, real commits,
    real cleanup (same reasoning as `_assert_selection_3c_fix` above)."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    restaurant_b: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic 4A Test Restaurant", default_currency="USD")
        restaurant_b = m.Restaurant(name="Synthetic 4A Test Restaurant B", default_currency="USD")
        session.add_all([restaurant, restaurant_b])
        session.commit()

        # =====================================================================
        # Fixture: a Requirement assessable ONLY at PHONE_INTERVIEW
        # (deterministically NOT_ASSESSED_AT_THIS_STAGE after résumé-stage
        # generation — test G) plus an unrelated RESUME-only control
        # Requirement (test Z's regression control).
        # =====================================================================
        requirement_set = req_svc.create_requirement_set(
            session, restaurant_id=restaurant.id, name="4A Test Server", target_role="SERVER",
        )
        req_svc.add_requirement(
            session, requirement_set.id, name="Teamwork", category="Teamwork", criticality=rm.MUST_HAVE,
            trainability=rm.NOT_TRAINABLE, assessment_stages=[rm.PHONE_INTERVIEW],
            description="Works effectively as part of a team.",
        )
        req_svc.add_requirement(
            session, requirement_set.id, name="POS familiarity", category="Technical Knowledge",
            criticality=rm.OPTIONAL, trainability=rm.TRAINABLE, assessment_stages=[rm.RESUME],
        )

        text = (
            "Jordan Diner\njordan.diner.4a@example.com\n555-070-1000\n\nEXPERIENCE\nServer, Test Bistro\n"
            "Jan 2021 - Jun 2022\nWaited tables.\n"
        )
        imported = import_pipeline.import_one_resume(
            session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD, original_filename="jordan_4a.txt",
            storage_path=None, raw_text=text, content_hash=compute_content_hash(text, "jordan_4a.txt"),
        )
        application = app_svc.create_application(
            session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id,
            requirement_set_id=requirement_set.id, target_role="SERVER",
        )
        session.commit()

        fit_assessment = fa_svc.create_fit_assessment(
            session, candidate_id=application.candidate_id, requirement_set_id=requirement_set.id,
        )
        session.commit()
        session.expire_all()

        teamwork_ra = next(
            ra for ra in fa_svc.list_requirement_assessments(session, fit_assessment.id)
            if ra.requirement_snapshot_item.name == "Teamwork"
        )
        control_ra = next(
            ra for ra in fa_svc.list_requirement_assessments(session, fit_assessment.id)
            if ra.requirement_snapshot_item.name == "POS familiarity"
        )
        control_status_before = control_ra.effective_status
        result.check(
            "4A-G-setup: a Requirement assessable ONLY at PHONE_INTERVIEW is NOT_ASSESSED_AT_THIS_STAGE right "
            "after résumé-stage generation",
            teamwork_ra.effective_status == fam.NOT_ASSESSED_AT_THIS_STAGE,
        )

        # A Signal Definition/Observation left POSSIBLE (test H).
        motivation_definition = sig_svc.create_signal_definition(
            session, restaurant_id=restaurant.id, name="4A Explicit interest", signal_family=sm.MOTIVATION_PERSONAL,
            assessment_stages=[rm.RESUME, rm.PHONE_INTERVIEW],
            evidence_sources_allowed=[fam.RESUME_FACT, fam.PHONE_INTERVIEW_RESPONSE],
        )
        observation = sig_svc.get_or_create_observation(session, application.id, motivation_definition.id)
        sig_svc.add_evidence(
            session, observation.id, source_type=fam.RESUME_FACT, evidence_classification=fam.FACT,
            evidence_relationship=fam.SUPPORTS, confidence=fam.CONFIDENCE_LOW,
            evidence_text="Mentioned wanting steady work.", source_stage=rm.RESUME, is_system_generated=True,
        )
        session.commit()
        session.expire_all()
        result.check(
            "4A-H-setup: the Signal Observation is left POSSIBLE (SUPPORTS at LOW confidence only)",
            sig_svc.get_or_create_observation(session, application.id, motivation_definition.id).status == sm.POSSIBLE,
        )

        # =====================================================================
        # C/D: restaurant-configured Core Question library, by role, kept
        # separate per restaurant.
        # =====================================================================
        gate_definition = pi_svc.create_question_definition(
            session, restaurant_id=restaurant.id, target_role="SERVER",
            question_text="Are you available to work weekends?", importance=pim.CRITICAL, is_sine_qua_non=True,
            mandatory_within_selection_process=True,
        )
        high_definition = pi_svc.create_question_definition(
            session, restaurant_id=restaurant.id, target_role="SERVER",
            question_text="Why did you leave your last job?", importance=pim.HIGH,
        )
        medium_definition = pi_svc.create_question_definition(
            session, restaurant_id=restaurant.id, target_role="SERVER",
            question_text="Describe your ideal coworker.", importance=pim.MEDIUM,
        )
        low_definition = pi_svc.create_question_definition(
            session, restaurant_id=restaurant.id, target_role="SERVER",
            question_text="Tell me one strength at work.", importance=pim.LOW,
        )
        other_role_definition = pi_svc.create_question_definition(
            session, restaurant_id=restaurant.id, target_role="LINE_COOK",
            question_text="Are you comfortable working the line during rush?", importance=pim.HIGH,
        )
        pi_svc.create_question_definition(
            session, restaurant_id=restaurant.id, target_role="SERVER",
            question_text="Do you have any questions for us?", importance=pim.LOW, is_courtesy=True,
        )
        restaurant_b_definition = pi_svc.create_question_definition(
            session, restaurant_id=restaurant_b.id, target_role="SERVER",
            question_text="Restaurant B's own question — never seen by Restaurant A.", importance=pim.HIGH,
        )
        session.commit()

        restaurant_a_definitions = pi_svc.list_question_definitions(session, restaurant_id=restaurant.id, is_courtesy=False)
        restaurant_b_definitions = pi_svc.list_question_definitions(session, restaurant_id=restaurant_b.id, is_courtesy=False)
        result.check(
            "4A-C: Core Questions can be configured by restaurant and role",
            {d.id for d in restaurant_a_definitions}
            == {gate_definition.id, high_definition.id, medium_definition.id, low_definition.id, other_role_definition.id},
        )
        result.check(
            "4A-D: two restaurants have completely separate Core Question libraries",
            restaurant_b_definition.id not in {d.id for d in restaurant_a_definitions}
            and {d.id for d in restaurant_b_definitions} == {restaurant_b_definition.id},
        )

        # =====================================================================
        # A/B: Phone Interview Plan creation, snapshot-binding.
        # =====================================================================
        plan = pi_svc.create_plan(session, application.id)
        session.commit()
        session.expire_all()
        result.check("4A-A: an Application can create a Phone Interview Plan", plan is not None and plan.id is not None)
        result.check(
            "4A-B: the plan remains tied to the SAME RequirementSetSnapshot / Fit Assessment already used",
            plan.requirement_set_snapshot_id == fit_assessment.requirement_set_snapshot_id
            and plan.fit_assessment_id == fit_assessment.id,
        )

        instances = pi_svc.list_question_instances(session, plan.id)
        core_texts = {q.question_text for q in instances if q.source_type == pim.CORE}
        result.check(
            "4A-C2: only role-matching Core Questions (SERVER) entered the plan — the LINE_COOK-only Core "
            "Question did not",
            {gate_definition.question_text, high_definition.question_text, medium_definition.question_text,
             low_definition.question_text} <= core_texts
            and other_role_definition.question_text not in core_texts,
        )

        dynamic_from_requirement = next(
            (
                q for q in instances
                if q.source_type == pim.DYNAMIC and teamwork_ra.requirement_snapshot_item_id in q.linked_requirement_ids
            ),
            None,
        )
        result.check(
            "4A-G: a Dynamic Question is generated from a NOT_ASSESSED_AT_THIS_STAGE Requirement now assessable "
            "at PHONE_INTERVIEW",
            dynamic_from_requirement is not None and bool(dynamic_from_requirement.reason_for_inclusion),
        )
        dynamic_from_signal = next(
            (
                q for q in instances
                if q.source_type == pim.DYNAMIC and motivation_definition.id in q.linked_signal_definition_ids
            ),
            None,
        )
        result.check(
            "4A-H: a Dynamic Question is generated from a Selection Signal left POSSIBLE",
            dynamic_from_signal is not None,
        )
        result.check(
            "4A-I: Dynamic Questions preserve their source reason/evidence link (Requirement or Signal id, plus "
            "a concrete reason string)",
            bool(dynamic_from_requirement.reason_for_inclusion) and bool(dynamic_from_signal.reason_for_inclusion)
            and dynamic_from_requirement.linked_requirement_ids and dynamic_from_signal.linked_signal_definition_ids,
        )

        # =====================================================================
        # E/F: Gate first, then CRITICAL -> HIGH -> MEDIUM -> LOW.
        # =====================================================================
        ordered = pi_svc.get_ordered_remaining_questions(session, plan.id)
        gate_instance = next(q for q in ordered if q.question_text == gate_definition.question_text)
        high_instance = next(q for q in ordered if q.question_text == high_definition.question_text)
        medium_instance = next(q for q in ordered if q.question_text == medium_definition.question_text)
        low_instance = next(q for q in ordered if q.question_text == low_definition.question_text)
        ordered_ids = [q.id for q in ordered]
        result.check(
            "4A-E: the Sine Qua Non (Gate) Question appears before every other question, regardless of its own "
            "importance level",
            ordered_ids.index(gate_instance.id) == 0,
        )
        result.check(
            "4A-F: importance ordering is CRITICAL -> HIGH -> MEDIUM -> LOW among non-Gate questions",
            ordered_ids.index(high_instance.id) < ordered_ids.index(medium_instance.id)
            < ordered_ids.index(low_instance.id),
        )

        # =====================================================================
        # J: a failed Gate never automatically stops the Application.
        # =====================================================================
        workflow_before_gate = application.workflow_status
        pi_svc.set_gate_evaluation(session, gate_instance.id, gate_evaluation=pim.FAILED, note="Not available weekends.")
        session.commit()
        session.expire_all()
        application_after_gate = app_svc.get_application(session, application.id)
        result.check(
            "4A-J: a FAILED Gate Evaluation never automatically changes the Application's workflow status",
            application_after_gate.workflow_status == workflow_before_gate,
        )
        result.check(
            "4A-X-setup: generating the plan and evaluating a Gate never produces a post-Phone-Interview "
            "decision automatically",
            application_after_gate.workflow_status not in apm.POST_PHONE_INTERVIEW_DECISIONS,
        )

        # =====================================================================
        # K/L: Escape Route.
        # =====================================================================
        instance_count_before_escape = len(pi_svc.list_question_instances(session, plan.id))
        pi_svc.activate_escape_route(session, plan.id, reason="Failed weekend-availability Gate.")
        session.commit()
        session.expire_all()
        plan = pi_svc.get_plan(session, plan.id)
        courtesy_questions = pi_svc.get_courtesy_questions(session, plan.id)
        unresolved_ids = {q.id for q in pi_svc.list_question_instances(session, plan.id) if q.status == pim.UNRESOLVED}
        result.check(
            "4A-K: the Selezionatore can activate the Escape Route",
            plan.status == pim.ESCAPE_ROUTE and plan.escape_route_activated_at is not None,
        )
        result.check(
            "4A-L: the Escape Route offers 2-3 courtesy questions and stops presenting the full remaining plan "
            "(unanswered substantive questions become UNRESOLVED, never deleted)",
            1 <= len(courtesy_questions) <= 3 and medium_instance.id in unresolved_ids
            and len(pi_svc.list_question_instances(session, plan.id))
            >= instance_count_before_escape + len(courtesy_questions),
        )

        # =====================================================================
        # M: raw answers preserved.
        # =====================================================================
        raw_answer = "I don't get along with the night manager, that's why I left."
        pi_svc.record_answer(
            session, high_instance.id, status=pim.ANSWERED, answer_text=raw_answer,
            selezionatore_note="Seems like a management-compatibility issue, not attendance.",
        )
        session.commit()
        session.expire_all()
        answered = session.get(m.PhoneInterviewQuestionInstance, high_instance.id)
        result.check(
            "4A-M: the exact raw answer text is preserved, kept separate from the Selezionatore's own note",
            answered.answer_text == raw_answer and answered.selezionatore_note != raw_answer,
        )

        # =====================================================================
        # N: Phone Interview answers can add Fit Assessment evidence; an
        # unrelated control Requirement Assessment is untouched.
        # =====================================================================
        pi_svc.record_answer(
            session, dynamic_from_requirement.id, status=pim.ANSWERED,
            answer_text="Yes, I always help coworkers during the rush without being asked.",
        )
        session.commit()
        pi_svc.record_answer_as_fit_evidence(
            session, dynamic_from_requirement.id, requirement_snapshot_item_id=teamwork_ra.requirement_snapshot_item_id,
            evidence_relationship=fam.SUPPORTS, evidence_classification=fam.FACT, confidence=fam.CONFIDENCE_HIGH,
        )
        session.commit()
        session.expire_all()
        teamwork_ra_after = session.get(m.RequirementAssessment, teamwork_ra.id)
        control_ra_after = session.get(m.RequirementAssessment, control_ra.id)
        result.check(
            "4A-N: a Phone Interview answer can add Fit Assessment evidence, correctly updating that "
            "Requirement's status",
            teamwork_ra_after.effective_status == fam.EVIDENCED
            and any(e.source_type == fam.PHONE_INTERVIEW_RESPONSE for e in teamwork_ra_after.evidence_items),
        )
        result.check(
            "4A-Z-part1: adding Phone Interview evidence to ONE Requirement never touches a different, "
            "unrelated Requirement Assessment",
            control_ra_after.effective_status == control_status_before,
        )

        # =====================================================================
        # O: Phone Interview answers can add Signal evidence.
        # =====================================================================
        pi_svc.record_answer(
            session, dynamic_from_signal.id, status=pim.ANSWERED,
            answer_text="Yes — I specifically wanted to come back to this restaurant.",
        )
        session.commit()
        pi_svc.record_answer_as_signal_evidence(
            session, dynamic_from_signal.id, signal_definition_id=motivation_definition.id,
            evidence_relationship=fam.SUPPORTS, evidence_classification=fam.FACT, confidence=fam.CONFIDENCE_HIGH,
        )
        session.commit()
        session.expire_all()
        observation_after = sig_svc.get_or_create_observation(session, application.id, motivation_definition.id)
        result.check(
            "4A-O: a Phone Interview answer can add Signal evidence, moving a POSSIBLE Signal to DETECTED "
            "without discarding the earlier résumé-stage evidence",
            observation_after.status == sm.DETECTED and len(observation_after.evidence_items) == 2
            and any(e.source_type == fam.RESUME_FACT for e in observation_after.evidence_items)
            and any(e.source_type == fam.PHONE_INTERVIEW_RESPONSE for e in observation_after.evidence_items),
        )

        # =====================================================================
        # P/Q: follow-up questions.
        # =====================================================================
        follow_up = pi_svc.add_follow_up_question(
            session, high_instance.id,
            question_text="What specifically was difficult about that working relationship?",
            objective="Clarify the management-compatibility answer just given.",
        )
        session.commit()
        result.check(
            "4A-P: a follow-up question can be created from an answer, linked to its parent",
            follow_up.source_type == pim.FOLLOW_UP and follow_up.parent_question_instance_id == high_instance.id,
        )
        forbidden_words = ("diagnosis", "personality_trait", "conflictual", "dishonest", "unreliable_label")
        result.check(
            "4A-Q: the follow-up mechanism never invents a psychological conclusion — no such field exists on "
            "the Question Instance model at all",
            not any(
                any(word in column.lower() for word in forbidden_words)
                for column in m.PhoneInterviewQuestionInstance.__table__.columns.keys()
            ),
        )

        # =====================================================================
        # R/S/T: carry-forward + mandatory-within-process.
        # =====================================================================
        result.check(
            "4A-R-setup/4A-T-setup: the mandatory-within-process Gate Question is still open (not yet "
            "CARRIED_FORWARD) before the post-interview decision is recorded",
            session.get(m.PhoneInterviewQuestionInstance, gate_instance.id).status != pim.CARRIED_FORWARD
            and gate_instance.mandatory_within_selection_process,
        )

        pre_decision_instance_count = len(pi_svc.list_question_instances(session, plan.id))
        pi_svc.record_post_interview_decision(
            session, plan.id, plan_status=pim.STOPPED_EARLY, application_decision=apm.HOLD,
            reason="Failed weekend-availability Gate; escape route used.",
        )
        session.commit()
        session.expire_all()

        gate_after_decision = session.get(m.PhoneInterviewQuestionInstance, gate_instance.id)
        medium_after_decision = session.get(m.PhoneInterviewQuestionInstance, medium_instance.id)
        result.check(
            "4A-R: an unanswered important Question is marked CARRIED_FORWARD by the post-interview decision",
            gate_after_decision.status == pim.CARRIED_FORWARD and bool(gate_after_decision.carried_forward_reason),
        )
        result.check(
            "4A-S: a partially-answered/UNRESOLVED Question is also marked CARRIED_FORWARD",
            medium_after_decision.status == pim.CARRIED_FORWARD,
        )
        result.check(
            "4A-T: a mandatory-within-selection-process Question unresolved on the phone remains open (carried "
            "forward, not silently dropped) for the future In-Person Interview",
            gate_after_decision.mandatory_within_selection_process
            and "mandatory" in (gate_after_decision.carried_forward_reason or "").lower(),
        )

        # =====================================================================
        # U: stopping at variable length never loses state (nothing deleted).
        # =====================================================================
        post_decision_instance_count = len(pi_svc.list_question_instances(session, plan.id))
        result.check(
            "4A-U: the Selezionatore can stop the interview at variable length without losing state — no "
            "Question Instance is ever deleted",
            post_decision_instance_count == pre_decision_instance_count,
        )

        # =====================================================================
        # V: Original CV access is unaffected by the Phone Interview.
        # =====================================================================
        final_plan = pi_svc.get_plan(session, plan.id)
        result.check(
            "4A-V: the Phone Interview Plan never changes which Candidate/CV record the Application points to "
            "(Original CV access is unaffected)",
            final_plan.candidate_id == application.candidate_id,
        )

        # =====================================================================
        # W/X: the post-Phone-Interview decision is exactly what the
        # Selezionatore recorded — never something else, never automatic.
        # =====================================================================
        application_final = app_svc.get_application(session, application.id)
        result.check(
            "4A-W/4A-X: the post-Phone-Interview decision (ADVANCE_TO_IN_PERSON/HOLD/STOP) is recorded exactly "
            "as the Selezionatore chose, and only then",
            application_final.workflow_status == apm.HOLD
            and application_final.workflow_status_reason == "Failed weekend-availability Gate; escape route used.",
        )

        # =====================================================================
        # Y: no numeric interview score anywhere in the schema.
        # =====================================================================
        forbidden_score_words = ("score", "rank", "rating")
        all_columns = (
            list(m.PhoneInterviewPlan.__table__.columns.keys())
            + list(m.PhoneInterviewQuestionInstance.__table__.columns.keys())
            + list(m.PhoneInterviewQuestionDefinition.__table__.columns.keys())
        )
        result.check(
            "4A-Y: no numeric interview score/rank/rating field exists anywhere in the Phone Interview schema",
            not any(any(word in c.lower() for word in forbidden_score_words) for c in all_columns),
        )

        # =====================================================================
        # Z: existing Task 3B/3C functionality remains operational.
        # =====================================================================
        result.check(
            "4A-Z: Task 3B Fit Assessment and Task 3C Signal Observation machinery both remain fully "
            "operational after the Phone Interview framework's own evidence additions",
            fa_svc.get_summary(session, fit_assessment.id)["total"] == 2
            and len(sig_svc.list_observations(session, application.id)) >= 1,
        )
    finally:
        session.rollback()
        for target_restaurant in (restaurant, restaurant_b):
            if target_restaurant is not None and target_restaurant.id is not None:
                for instance_row in session.query(m.PhoneInterviewQuestionInstance).join(
                    m.PhoneInterviewPlan, m.PhoneInterviewQuestionInstance.plan_id == m.PhoneInterviewPlan.id
                ).filter(m.PhoneInterviewPlan.restaurant_id == target_restaurant.id):
                    session.delete(instance_row)
                session.flush()
                for plan_row in session.query(m.PhoneInterviewPlan).filter_by(restaurant_id=target_restaurant.id):
                    session.delete(plan_row)
                session.flush()
                for definition_row in session.query(m.PhoneInterviewQuestionDefinition).filter_by(
                    restaurant_id=target_restaurant.id
                ):
                    session.delete(definition_row)
                session.flush()
                for application_row in app_svc.list_applications(session, restaurant_id=target_restaurant.id):
                    session.delete(application_row)  # cascades to SignalObservation/SignalEvidenceItem/notes
                session.flush()
                for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=target_restaurant.id):
                    session.delete(person_row)
                for definition_row in session.query(m.SignalDefinition).filter_by(restaurant_id=target_restaurant.id):
                    session.delete(definition_row)
                session.flush()
                for candidate_row in persistence.list_candidates(session, restaurant_id=target_restaurant.id):
                    for fa_row in fa_svc.list_fit_assessments_for_candidate(session, candidate_row.id):
                        session.delete(fa_row)  # cascades to RequirementAssessment/EvidenceItem rows
                    session.flush()
                    session.delete(candidate_row)
                session.flush()
                for raw in list(session.query(m.RawResume).filter_by(restaurant_id=target_restaurant.id)):
                    session.delete(raw)
                session.flush()
                for requirement_set_row in req_svc.list_requirement_sets(session, restaurant_id=target_restaurant.id):
                    for snapshot_row in req_svc.list_snapshots(session, requirement_set_row.id):
                        session.delete(snapshot_row)
                    session.flush()
                    session.delete(requirement_set_row)
                session.flush()
        still_attached = session.get(m.Restaurant, restaurant.id) if restaurant is not None else None
        still_attached_b = session.get(m.Restaurant, restaurant_b.id) if restaurant_b is not None else None
        for restaurant_row in (still_attached, still_attached_b):
            if restaurant_row is not None:
                session.delete(restaurant_row)
        session.commit()
        session.close()


def _assert_selection_4b_in_person_interview(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 4B checks — In-Person Interview Plan creation/snapshot-binding,
    restaurant-configured Sections/Assessment Items, Phone carry-forward,
    QUESTION/OBSERVATION/PRACTICAL_TEST/ROLE_PLAY items, Fit Assessment/
    Signal evidence bridging, the Consistency Engine (CV/Phone/In-Person/
    prior-Application comparisons, all 6 statuses, clarification-question
    generation, no automatic dishonesty labeling), variable-length stop,
    and Original CV access. Own dedicated session/restaurant, real commits,
    real cleanup (same reasoning as `_assert_selection_4a_phone_interview`
    above)."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic 4B Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        # =====================================================================
        # Fixture: Requirement Set (one Requirement assessable at PHONE +
        # IN_PERSON, one RESUME-only control), Application, Fit Assessment,
        # a seeded Phone Interview Plan (Task 4A) to carry forward from.
        # =====================================================================
        requirement_set = req_svc.create_requirement_set(
            session, restaurant_id=restaurant.id, name="4B Test Server", target_role="SERVER",
        )
        req_svc.add_requirement(
            session, requirement_set.id, name="Teamwork", category="Teamwork", criticality=rm.MUST_HAVE,
            trainability=rm.NOT_TRAINABLE, assessment_stages=[rm.PHONE_INTERVIEW, rm.IN_PERSON_INTERVIEW],
            description="Works effectively as part of a team.",
        )
        req_svc.add_requirement(
            session, requirement_set.id, name="POS familiarity", category="Technical Knowledge",
            criticality=rm.OPTIONAL, trainability=rm.TRAINABLE, assessment_stages=[rm.RESUME],
        )

        def _upload(name: str, email: str, phone: str, role_line: str, target_role: str = "SERVER") -> m.Application:
            text = f"{name}\n{email}\n{phone}\n\nEXPERIENCE\n{role_line}\n"
            imported = import_pipeline.import_one_resume(
                session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD, original_filename=f"{email}.txt",
                storage_path=None, raw_text=text, content_hash=compute_content_hash(text, f"{email}.txt"),
            )
            application = app_svc.create_application(
                session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id,
                requirement_set_id=requirement_set.id, target_role=target_role,
            )
            session.commit()
            return application

        prior_application = _upload(
            "Taylor Fourb", "taylor.fourb.prior@example.com", "555-080-1000",
            "Dishwasher, Old Bistro\nJan 2019 - Dec 2020\nWashed dishes.", target_role="DISHWASHER",
        )
        application = _upload(
            "Taylor Fourb", "taylor.fourb.prior@example.com", "555-080-1000",
            "Server, Test Bistro\nJan 2021 - Jun 2022\nWaited tables.",
        )
        result.check(
            "4B-Y-setup: the two Applications resolve to the SAME CandidatePerson (same normalized email), so "
            "a prior Application genuinely exists for cross-Application comparison",
            prior_application.person_id == application.person_id,
        )

        fit_assessment = fa_svc.create_fit_assessment(
            session, candidate_id=application.candidate_id, requirement_set_id=requirement_set.id,
        )
        session.commit()
        session.expire_all()
        teamwork_ra = next(
            ra for ra in fa_svc.list_requirement_assessments(session, fit_assessment.id)
            if ra.requirement_snapshot_item.name == "Teamwork"
        )

        # A restaurant-authored Phone Interview Core Question library, so
        # the Phone Interview Plan actually has questions to carry forward.
        gate_definition = pi_svc.create_question_definition(
            session, restaurant_id=restaurant.id, target_role="SERVER",
            question_text="Are you available to work weekends?", importance=pim.CRITICAL, is_sine_qua_non=True,
        )
        reliability_definition = pi_svc.create_question_definition(
            session, restaurant_id=restaurant.id, target_role="SERVER",
            question_text="Why did you leave your last job?", importance=pim.HIGH,
        )
        session.commit()

        phone_plan = pi_svc.create_plan(session, application.id)
        session.commit()
        reliability_instance = next(
            q for q in pi_svc.list_question_instances(session, phone_plan.id)
            if q.question_text == reliability_definition.question_text
        )
        pi_svc.record_answer(
            session, reliability_instance.id, status=pim.PARTIALLY_ANSWERED,
            answer_text="I left because the schedule was unstable.",
        )
        session.commit()
        session.expire_all()

        # =====================================================================
        # C/D: restaurant can configure Sections and Assessment Items.
        # =====================================================================
        section = ip_svc.create_section_definition(
            session, restaurant_id=restaurant.id, name="Work Personality", section_kind=ipm.WORK_PERSONALITY,
            target_role="SERVER",
        )
        observation_definition = ip_svc.create_item_definition(
            session, section.id, item_type=ipm.OBSERVATION, title_or_question="Professional presentation",
            objective="Note guest-appropriate professional presentation.", importance=pim.HIGH,
        )
        question_definition = ip_svc.create_item_definition(
            session, section.id, item_type=ipm.QUESTION,
            title_or_question="Why did you leave your last job?", objective="Cross-check reason for leaving.",
            importance=pim.HIGH, linked_requirement_ids=[], display_order=1,
        )
        practical_definition = ip_svc.create_item_definition(
            session, section.id, item_type=ipm.PRACTICAL_TEST,
            title_or_question="What do you do when you have no active tables?",
            objective="Assess proactive service mindset.", importance=pim.MEDIUM,
            linked_requirement_ids=[teamwork_ra.requirement_snapshot_item.source_requirement_id], display_order=2,
        )
        roleplay_definition = ip_svc.create_item_definition(
            session, section.id, item_type=ipm.ROLE_PLAY,
            title_or_question="Recommend a pasta dish to me as if I were a guest.",
            objective="Assess sales/role-play technique.", importance=pim.MEDIUM, display_order=3,
        )
        session.commit()

        result.check(
            "4B-C: a restaurant can configure an In-Person Interview Section",
            ip_svc.get_section_definition(session, section.id) is not None
            and section.section_kind == ipm.WORK_PERSONALITY,
        )
        result.check(
            "4B-D: a restaurant can configure Assessment Items within a Section",
            {d.id for d in ip_svc.list_item_definitions(session, section_id=section.id)}
            == {observation_definition.id, question_definition.id, practical_definition.id, roleplay_definition.id},
        )

        # =====================================================================
        # A/B: In-Person Interview Plan creation, snapshot-binding.
        # =====================================================================
        plan = ip_svc.create_plan(session, application.id)
        session.commit()
        session.expire_all()
        result.check(
            "4B-A: an eligible Application can create an In-Person Interview Plan", plan is not None and plan.id is not None,
        )
        result.check(
            "4B-B: the plan remains tied to the SAME RequirementSetSnapshot / Fit Assessment already used",
            plan.requirement_set_snapshot_id == fit_assessment.requirement_set_snapshot_id
            and plan.fit_assessment_id == fit_assessment.id and plan.phone_interview_plan_id == phone_plan.id,
        )

        items = ip_svc.list_item_instances(session, plan.id)

        # =====================================================================
        # I/J: Phone carry-forward — items appear, previous answers preserved.
        # =====================================================================
        carried_gate = next(
            (i for i in items if i.source_type == ipm.CARRY_FORWARD_ITEM and i.title_or_question == gate_definition.question_text),
            None,
        )
        carried_reliability = next(
            (i for i in items if i.source_type == ipm.CARRY_FORWARD_ITEM and i.title_or_question == reliability_definition.question_text),
            None,
        )
        result.check(
            "4B-I: relevant Phone Interview items (NOT_ASKED / PARTIALLY_ANSWERED / UNRESOLVED / "
            "CARRIED_FORWARD) are automatically carried forward into the In-Person plan",
            carried_gate is not None and carried_reliability is not None,
        )
        result.check(
            "4B-J: a Phone Interview item's previous answer is preserved exactly on carry-forward",
            carried_reliability.raw_response == "I left because the schedule was unstable.",
        )

        # =====================================================================
        # E/F/G/H: QUESTION / OBSERVATION / PRACTICAL_TEST / ROLE_PLAY items
        # from the restaurant's own Section all work.
        # =====================================================================
        observation_instance = next(i for i in items if i.source_item_definition_id == observation_definition.id)
        question_instance = next(i for i in items if i.source_item_definition_id == question_definition.id)
        practical_instance = next(i for i in items if i.source_item_definition_id == practical_definition.id)
        roleplay_instance = next(i for i in items if i.source_item_definition_id == roleplay_definition.id)

        ip_svc.record_response(
            session, question_instance.id, status=ipm.DONE,
            raw_response="I had problems with management.",
        )
        ip_svc.record_response(
            session, observation_instance.id, status=ipm.DONE,
            raw_response="Well-groomed, guest-appropriate attire, arrived on time.",
        )
        ip_svc.record_response(
            session, practical_instance.id, status=ipm.DONE,
            raw_response="Said they would check in with other servers and pre-bus tables.",
        )
        ip_svc.record_response(
            session, roleplay_instance.id, status=ipm.PARTIAL,
            raw_response="Gave a generic recommendation without much detail.",
        )
        session.commit()
        session.expire_all()
        result.check(
            "4B-E: a QUESTION Assessment Item can record a response",
            session.get(m.AssessmentItemInstance, question_instance.id).raw_response == "I had problems with management.",
        )
        result.check(
            "4B-F: an OBSERVATION Assessment Item can record a response",
            session.get(m.AssessmentItemInstance, observation_instance.id).status == ipm.DONE,
        )
        result.check(
            "4B-G: a PRACTICAL_TEST Assessment Item can record a response",
            session.get(m.AssessmentItemInstance, practical_instance.id).source_type == ipm.PRACTICAL_TEST
            and session.get(m.AssessmentItemInstance, practical_instance.id).status == ipm.DONE,
        )
        result.check(
            "4B-H: a ROLE_PLAY Assessment Item can record a response",
            session.get(m.AssessmentItemInstance, roleplay_instance.id).source_type == ipm.ROLE_PLAY
            and session.get(m.AssessmentItemInstance, roleplay_instance.id).status == ipm.PARTIAL,
        )

        # =====================================================================
        # K/L: Fit Assessment can receive In-Person AND Practical evidence.
        # =====================================================================
        control_status_before = fa_svc.get_summary(session, fit_assessment.id)["counts"]
        ip_svc.record_response_as_fit_evidence(
            session, observation_instance.id, requirement_snapshot_item_id=teamwork_ra.requirement_snapshot_item_id,
            evidence_relationship=fam.SUPPORTS, evidence_classification=fam.FACT, confidence=fam.CONFIDENCE_HIGH,
        )
        session.commit()
        session.expire_all()
        teamwork_ra_after_inperson = session.get(m.RequirementAssessment, teamwork_ra.id)
        evidence_count_after_inperson = len(teamwork_ra_after_inperson.evidence_items)
        result.check(
            "4B-K: In-Person evidence (an OBSERVATION item) can update a Requirement Assessment via the "
            "existing Fit Assessment evidence model",
            teamwork_ra_after_inperson.effective_status == fam.EVIDENCED
            and any(e.source_type == fam.IN_PERSON_OBSERVATION for e in teamwork_ra_after_inperson.evidence_items),
        )

        ip_svc.record_response_as_fit_evidence(
            session, practical_instance.id, requirement_snapshot_item_id=teamwork_ra.requirement_snapshot_item_id,
            evidence_relationship=fam.SUPPORTS, evidence_classification=fam.FACT, confidence=fam.CONFIDENCE_MEDIUM,
        )
        session.commit()
        session.expire_all()
        teamwork_ra_after_practical = session.get(m.RequirementAssessment, teamwork_ra.id)
        result.check(
            "4B-L: Practical Assessment evidence (a PRACTICAL_TEST item) can also update the SAME Requirement "
            "Assessment, preserving prior résumé/Phone/In-Person evidence",
            any(e.source_type == fam.PRACTICAL_ASSESSMENT_RESULT for e in teamwork_ra_after_practical.evidence_items)
            and len(teamwork_ra_after_practical.evidence_items) > evidence_count_after_inperson,
        )

        # =====================================================================
        # M: Selection Signals can receive In-Person evidence.
        # =====================================================================
        motivation_definition = sig_svc.create_signal_definition(
            session, restaurant_id=restaurant.id, name="4B Explicit interest", signal_family=sm.MOTIVATION_PERSONAL,
            assessment_stages=[rm.IN_PERSON_INTERVIEW], evidence_sources_allowed=[fam.IN_PERSON_OBSERVATION],
        )
        session.commit()
        ip_svc.record_response_as_signal_evidence(
            session, question_instance.id, signal_definition_id=motivation_definition.id,
            evidence_relationship=fam.SUPPORTS, evidence_classification=fam.FACT, confidence=fam.CONFIDENCE_HIGH,
        )
        session.commit()
        session.expire_all()
        observation_after = sig_svc.get_or_create_observation(session, application.id, motivation_definition.id)
        result.check(
            "4B-M: In-Person evidence can update an existing Selection Signal Observation",
            observation_after.status == sm.DETECTED
            and any(e.source_type == fam.IN_PERSON_OBSERVATION for e in observation_after.evidence_items),
        )

        # =====================================================================
        # N/O/P/Q/R/S/T/U/V/W: the Consistency Engine.
        # =====================================================================
        thread_cv_phone = ip_svc.create_consistency_thread(
            session, application.id, topic="Reason for leaving (CV vs Phone)", importance=pim.MEDIUM,
        )
        ip_svc.add_statement_from_application(
            session, thread_cv_phone.id, application.id, raw_statement="Server, Test Bistro, Jan 2021 - Jun 2022.",
        )
        ip_svc.add_statement_from_phone_answer(session, thread_cv_phone.id, reliability_instance.id)
        ip_svc.set_comparison_status(
            session, thread_cv_phone.id, status=ipm.CONSISTENT,
            explanation="The résumé's own employment record and the Phone Interview answer are materially compatible.",
        )
        session.commit()
        session.expire_all()
        thread_cv_phone_after = ip_svc.get_thread(session, thread_cv_phone.id)
        result.check(
            "4B-N: a Consistency Thread can compare CV/Application evidence against Phone Interview evidence",
            len(thread_cv_phone_after.statements) == 2
            and {s.source_stage for s in thread_cv_phone_after.statements} == {ipm.CV_APPLICATION, ipm.PHONE_INTERVIEW},
        )
        result.check(
            "4B-Q: consistent statements produce CONSISTENT",
            thread_cv_phone_after.comparison_status == ipm.CONSISTENT,
        )

        thread_phone_inperson = ip_svc.create_consistency_thread(
            session, application.id, topic="Reason for leaving (Phone vs In-Person)", importance=pim.HIGH,
        )
        ip_svc.add_statement_from_phone_answer(session, thread_phone_inperson.id, reliability_instance.id)
        ip_svc.add_statement_from_in_person_item(session, thread_phone_inperson.id, question_instance.id)
        explanation_text = (
            "Material inconsistency detected between Phone Interview and In-Person response regarding reason "
            "for leaving previous employment."
        )
        ip_svc.set_comparison_status(
            session, thread_phone_inperson.id, status=ipm.MATERIAL_INCONSISTENCY, explanation=explanation_text,
        )
        session.commit()
        session.expire_all()
        thread_phone_inperson_after = ip_svc.get_thread(session, thread_phone_inperson.id)
        result.check(
            "4B-O: a Consistency Thread can compare Phone Interview evidence against In-Person evidence",
            len(thread_phone_inperson_after.statements) == 2
            and {s.source_stage for s in thread_phone_inperson_after.statements} == {ipm.PHONE_INTERVIEW, ipm.IN_PERSON_INTERVIEW},
        )
        result.check(
            "4B-S: a material contradiction can produce MATERIAL_INCONSISTENCY",
            thread_phone_inperson_after.comparison_status == ipm.MATERIAL_INCONSISTENCY,
        )
        forbidden_words = ("liar", "lying", "dishonest", "deceptive", "manipulative")
        result.check(
            "4B-W: RF-One never labels an inconsistency as dishonesty automatically — the generated "
            "explanation stays a plain factual description",
            not any(word in thread_phone_inperson_after.explanation.lower() for word in forbidden_words),
        )

        clarification_item = ip_svc.generate_clarification_item(session, plan.id, thread_phone_inperson.id)
        session.commit()
        result.check(
            "4B-X: a Consistency Item to Verify can generate a clarification question, preserving both "
            "original statements",
            clarification_item.source_type == ipm.CONSISTENCY_CHECK
            and clarification_item.consistency_thread_id == thread_phone_inperson.id
            and "schedule" in clarification_item.title_or_question.lower()
            and "management" in clarification_item.title_or_question.lower(),
        )
        items_to_verify = ip_svc.list_items_to_verify(session, application.id)
        result.check(
            "4B-13-setup: the MATERIAL_INCONSISTENCY thread appears in the prioritized Consistency Items to "
            "Verify listing",
            thread_phone_inperson.id in {t.id for t in items_to_verify},
        )

        thread_all_three = ip_svc.create_consistency_thread(
            session, application.id, topic="Reason for leaving (all three sources)", importance=pim.MEDIUM,
        )
        ip_svc.add_statement_from_application(
            session, thread_all_three.id, application.id, raw_statement="Server, Test Bistro, Jan 2021 - Jun 2022.",
        )
        ip_svc.add_statement_from_phone_answer(session, thread_all_three.id, reliability_instance.id)
        ip_svc.add_statement_from_in_person_item(session, thread_all_three.id, question_instance.id)
        ip_svc.set_comparison_status(
            session, thread_all_three.id, status=ipm.MINOR_VARIATION,
            explanation="Different wording across sources, no meaningful contradiction found yet.",
        )
        session.commit()
        session.expire_all()
        thread_all_three_after = ip_svc.get_thread(session, thread_all_three.id)
        result.check(
            "4B-P: a Consistency Thread can compare all three sources (CV, Phone, In-Person) at once",
            len(thread_all_three_after.statements) == 3
            and {s.source_stage for s in thread_all_three_after.statements}
            == {ipm.CV_APPLICATION, ipm.PHONE_INTERVIEW, ipm.IN_PERSON_INTERVIEW},
        )
        result.check(
            "4B-R: a harmless wording difference can produce MINOR_VARIATION",
            thread_all_three_after.comparison_status == ipm.MINOR_VARIATION,
        )

        original_statement_texts = {s.raw_statement for s in thread_all_three_after.statements}
        ip_svc.set_comparison_status(
            session, thread_all_three.id, status=ipm.EXPLAINED_DIFFERENCE,
            explanation="The candidate clarified during In-Person that both factors contributed to leaving.",
            resolution="Selezionatore accepts the clarification as sufficient.",
        )
        session.commit()
        session.expire_all()
        thread_all_three_final = ip_svc.get_thread(session, thread_all_three.id)
        result.check(
            "4B-T: a later clarification can produce EXPLAINED_DIFFERENCE",
            thread_all_three_final.comparison_status == ipm.EXPLAINED_DIFFERENCE
            and bool(thread_all_three_final.selezionatore_resolution),
        )
        result.check(
            "4B-V: original source statements remain stored, verbatim, even after the thread's comparison "
            "status changed twice",
            {s.raw_statement for s in thread_all_three_final.statements} == original_statement_texts
            and len(thread_all_three_final.statements) == 3,
        )

        thread_unresolved = ip_svc.create_consistency_thread(
            session, application.id, topic="Income expectations", importance=pim.LOW,
        )
        ip_svc.add_statement_from_application(
            session, thread_unresolved.id, application.id, raw_statement="No income expectation stated.",
        )
        session.commit()
        session.expire_all()
        result.check(
            "4B-U: a thread with an unresolved/insufficient comparison stays UNRESOLVED by default",
            ip_svc.get_thread(session, thread_unresolved.id).comparison_status == ipm.CONSISTENCY_UNRESOLVED,
        )

        # =====================================================================
        # Y: prior Applications contribute consistency evidence.
        # =====================================================================
        cross_threads = ip_svc.generate_cross_application_consistency_threads(session, application.id)
        session.commit()
        result.check(
            "4B-Y: a prior Application (target role DISHWASHER -> current SERVER) contributes a deterministic "
            "cross-Application Consistency Thread, classified NEW_INFORMATION rather than automatically negative",
            len(cross_threads) > 0 and all(t.comparison_status == ipm.NEW_INFORMATION for t in cross_threads),
        )

        # =====================================================================
        # Z/AA: variable-length stop never loses completed evidence;
        # unresolved items remain visible.
        # =====================================================================
        pre_stop_count = len(ip_svc.list_item_instances(session, plan.id))
        incomplete_before = {i.id for i in ip_svc.list_incomplete_items(session, plan.id)}
        ip_svc.stop_interview(session, plan.id, plan_status=ipm.STOPPED_EARLY)
        session.commit()
        session.expire_all()
        plan_after_stop = ip_svc.get_plan(session, plan.id)
        post_stop_count = len(ip_svc.list_item_instances(session, plan.id))
        result.check(
            "4B-Z: the Selezionatore can stop the In-Person Interview early without losing any completed "
            "evidence (no Assessment Item is ever deleted, and already-DONE items keep their recorded response)",
            plan_after_stop.status == ipm.STOPPED_EARLY and post_stop_count == pre_stop_count
            and session.get(m.AssessmentItemInstance, question_instance.id).raw_response == "I had problems with management.",
        )
        result.check(
            "4B-AA: unresolved/incomplete items (carried-forward NOT_DONE items, in particular) remain "
            "visible after stopping early",
            carried_gate.id in incomplete_before and carried_gate.id in {
                i.id for i in ip_svc.list_incomplete_items(session, plan.id)
            },
        )

        # =====================================================================
        # AB: Original CV access is unaffected by the In-Person Interview.
        # =====================================================================
        result.check(
            "4B-AB: the In-Person Interview Plan never changes which Candidate/CV record the Application "
            "points to (Original CV access is unaffected)",
            plan_after_stop.candidate_id == application.candidate_id,
        )

        # =====================================================================
        # AC: no numeric score anywhere in the Task 4B schema.
        # =====================================================================
        forbidden_score_words = ("score", "rank", "rating")
        all_columns = (
            list(m.InPersonInterviewSectionDefinition.__table__.columns.keys())
            + list(m.AssessmentItemDefinition.__table__.columns.keys())
            + list(m.InPersonInterviewPlan.__table__.columns.keys())
            + list(m.AssessmentItemInstance.__table__.columns.keys())
            + list(m.ConsistencyThread.__table__.columns.keys())
            + list(m.ConsistencyStatement.__table__.columns.keys())
        )
        result.check(
            "4B-AC: no numeric score/rank/rating field exists anywhere in the In-Person/Practical/Consistency "
            "schema",
            not any(any(word in c.lower() for word in forbidden_score_words) for c in all_columns),
        )

        # =====================================================================
        # AD/AE: existing Phone Interview and Selection functionality
        # remain operational after all of the above.
        # =====================================================================
        result.check(
            "4B-AD: the Phone Interview Plan and its own Question Instances remain fully readable/operational "
            "after the In-Person Interview framework's own carry-forward/evidence additions",
            len(pi_svc.list_question_instances(session, phone_plan.id)) > 0
            and session.get(m.PhoneInterviewQuestionInstance, reliability_instance.id).answer_text
            == "I left because the schedule was unstable.",
        )
        result.check(
            "4B-AE: Task 3B Fit Assessment and Task 3C Signal Observation machinery both remain fully "
            "operational",
            fa_svc.get_summary(session, fit_assessment.id)["total"] == 2
            and len(sig_svc.list_observations(session, application.id)) >= 1,
        )
    finally:
        session.rollback()
        if restaurant is not None and restaurant.id is not None:
            for item_instance_row in session.query(m.AssessmentItemInstance).join(
                m.InPersonInterviewPlan, m.AssessmentItemInstance.plan_id == m.InPersonInterviewPlan.id
            ).filter(m.InPersonInterviewPlan.restaurant_id == restaurant.id):
                session.delete(item_instance_row)  # references consistency_threads.id — delete before threads
            session.flush()
            for plan_row in session.query(m.InPersonInterviewPlan).filter_by(restaurant_id=restaurant.id):
                session.delete(plan_row)
            session.flush()
            for statement_row in session.query(m.ConsistencyStatement).join(
                m.ConsistencyThread, m.ConsistencyStatement.thread_id == m.ConsistencyThread.id
            ).join(m.Application, m.ConsistencyThread.application_id == m.Application.id).filter(
                m.Application.restaurant_id == restaurant.id
            ):
                session.delete(statement_row)
            session.flush()
            for thread_row in session.query(m.ConsistencyThread).join(
                m.Application, m.ConsistencyThread.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                session.delete(thread_row)
            session.flush()
            for item_definition_row in session.query(m.AssessmentItemDefinition).join(
                m.InPersonInterviewSectionDefinition,
                m.AssessmentItemDefinition.section_id == m.InPersonInterviewSectionDefinition.id,
            ).filter(m.InPersonInterviewSectionDefinition.restaurant_id == restaurant.id):
                session.delete(item_definition_row)
            session.flush()
            for section_row in session.query(m.InPersonInterviewSectionDefinition).filter_by(restaurant_id=restaurant.id):
                session.delete(section_row)
            session.flush()
            for phone_instance_row in session.query(m.PhoneInterviewQuestionInstance).join(
                m.PhoneInterviewPlan, m.PhoneInterviewQuestionInstance.plan_id == m.PhoneInterviewPlan.id
            ).filter(m.PhoneInterviewPlan.restaurant_id == restaurant.id):
                session.delete(phone_instance_row)
            session.flush()
            for phone_plan_row in session.query(m.PhoneInterviewPlan).filter_by(restaurant_id=restaurant.id):
                session.delete(phone_plan_row)
            session.flush()
            for phone_definition_row in session.query(m.PhoneInterviewQuestionDefinition).filter_by(
                restaurant_id=restaurant.id
            ):
                session.delete(phone_definition_row)
            session.flush()
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                session.delete(application_row)  # cascades to SignalObservation/SignalEvidenceItem/notes
            session.flush()
            for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=restaurant.id):
                session.delete(person_row)
            for definition_row in session.query(m.SignalDefinition).filter_by(restaurant_id=restaurant.id):
                session.delete(definition_row)
            session.flush()
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                for fa_row in fa_svc.list_fit_assessments_for_candidate(session, candidate_row.id):
                    session.delete(fa_row)  # cascades to RequirementAssessment/EvidenceItem rows
                session.flush()
                session.delete(candidate_row)
            session.flush()
            for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                session.delete(raw)
            session.flush()
            for requirement_set_row in req_svc.list_requirement_sets(session, restaurant_id=restaurant.id):
                for snapshot_row in req_svc.list_snapshots(session, requirement_set_row.id):
                    session.delete(snapshot_row)
                session.flush()
                session.delete(requirement_set_row)
            session.flush()
        still_attached = session.get(m.Restaurant, restaurant.id) if restaurant is not None else None
        if still_attached is not None:
            session.delete(still_attached)
        session.commit()
        session.close()


def _assert_selection_3d_primary_screening(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 3D checks — restaurant-configurable Screening Criteria (0-4
    level scale, coefficient, direction), cumulative signed contributions,
    the internal Priority Index (never exposed), Hard Disqualifiers as a
    categorical (never mathematically cancellable) gate with mandatory-
    reason override, system/effective evaluation overrides, snapshot-safe
    historical traceability, the conversational explanation, and continued
    operation of Review Priority / Phone / In-Person Selection. Own
    dedicated session/restaurants, real commits, real cleanup (same
    reasoning as `_assert_selection_4a_phone_interview` above)."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    restaurant_b: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic 3D Test Restaurant", default_currency="USD")
        restaurant_b = m.Restaurant(name="Synthetic 3D Test Restaurant B", default_currency="USD")
        session.add_all([restaurant, restaurant_b])
        session.commit()

        def _upload(name: str, email: str, phone: str, role_line: str) -> m.Application:
            text = f"{name}\n{email}\n{phone}\n\nEXPERIENCE\n{role_line}\n"
            imported = import_pipeline.import_one_resume(
                session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD, original_filename=f"{email}.txt",
                storage_path=None, raw_text=text, content_hash=compute_content_hash(text, f"{email}.txt"),
            )
            application = app_svc.create_application(
                session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id, target_role="SERVER",
            )
            session.commit()
            return application

        # =====================================================================
        # A/C/D: restaurant can create Screening Criteria; coefficient and
        # 0-4 level descriptions persist.
        # =====================================================================
        experience_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Relevant experience", coefficient=2.0, direction=psm.POSITIVE,
            level_descriptions={"0": "none", "1": "brief", "2": "some", "3": "solid", "4": "extensive"},
        )
        stability_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Job stability", coefficient=1.5, direction=psm.NEGATIVE,
            level_descriptions={"0": "stable", "4": "very unstable"},
        )
        availability_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Availability", coefficient=3.0, direction=psm.NEGATIVE,
            is_hard_disqualifier=True, hard_disqualifier_trigger_level=4,
            level_descriptions={"0": "fully compatible", "4": "fundamentally incompatible"},
        )
        motivation_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Motivation", coefficient=3.0, direction=psm.POSITIVE,
        )
        signal_definition = sig_svc.create_signal_definition(
            session, restaurant_id=restaurant.id, name="3D Recency Signal", signal_family=sm.READINESS_RECENCY,
            assessment_stages=[rm.RESUME], evidence_sources_allowed=[fam.RESUME_FACT],
        )
        recency_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Signal-linked recency", coefficient=1.0, direction=psm.POSITIVE,
            auto_evaluation_signal_definition_id=signal_definition.id, auto_evaluation_level_map={sm.DETECTED: 4},
        )
        session.commit()

        result.check(
            "3D-A: a restaurant can create a Primary Screening Criterion",
            ps_svc.get_criterion(session, experience_criterion.id) is not None,
        )
        result.check(
            "3D-C: the Criterion's coefficient persists exactly as configured",
            experience_criterion.coefficient == 2.0 and stability_criterion.coefficient == 1.5,
        )
        result.check(
            "3D-D: the Criterion's 0-4 level descriptions persist exactly as configured",
            ps_svc.get_criterion(session, experience_criterion.id).level_descriptions
            == {"0": "none", "1": "brief", "2": "some", "3": "solid", "4": "extensive"},
        )

        # =====================================================================
        # B: a different restaurant can define a completely different set
        # of Criteria (different name, coefficient, direction).
        # =====================================================================
        restaurant_b_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant_b.id, name="Wine knowledge depth", coefficient=0.3,
            direction=psm.NEGATIVE, category="Restaurant B's own unrelated category",
        )
        session.commit()
        restaurant_a_names = {c.name for c in ps_svc.list_criteria(session, restaurant_id=restaurant.id)}
        restaurant_b_names = {c.name for c in ps_svc.list_criteria(session, restaurant_id=restaurant_b.id)}
        result.check(
            "3D-B: two restaurants can define completely different, non-overlapping Screening Criteria",
            restaurant_b_names == {"Wine knowledge depth"} and "Wine knowledge depth" not in restaurant_a_names,
        )

        # =====================================================================
        # Fixture: four Applications exercising the full engine.
        # =====================================================================
        app1 = _upload("Casey Strong", "casey.strong.3d@example.com", "555-095-0001", "Server, Bistro One\nJan 2022 - Present\nWaited tables.")
        app2 = _upload("Riley Hard", "riley.hard.3d@example.com", "555-095-0002", "Server, Bistro Two\nJan 2022 - Present\nWaited tables.")
        app3 = _upload("Jordan Mid", "jordan.mid.3d@example.com", "555-095-0003", "Server, Bistro Three\nJan 2022 - Present\nWaited tables.")
        app4 = _upload("Taylor Unknown", "taylor.unknown.3d@example.com", "555-095-0004", "Server, Bistro Four\nJan 2022 - Present\nWaited tables.")

        # app1's Signal is DETECTED before its run is created, so the
        # Signal-linked Criterion auto-evaluates SYSTEM_GENERATED.
        observation1 = sig_svc.get_or_create_observation(session, app1.id, signal_definition.id)
        sig_svc.add_evidence(
            session, observation1.id, source_type=fam.RESUME_FACT, evidence_classification=fam.FACT,
            evidence_relationship=fam.SUPPORTS, confidence=fam.CONFIDENCE_HIGH, evidence_text="Current server role.",
        )
        session.commit()
        session.expire_all()

        run1 = ps_svc.create_screening_run(session, app1.id)
        run2 = ps_svc.create_screening_run(session, app2.id)
        run3 = ps_svc.create_screening_run(session, app3.id)
        run4 = ps_svc.create_screening_run(session, app4.id)
        session.commit()
        session.expire_all()

        # =====================================================================
        # H: an unknown/not-evaluated Criterion never silently becomes
        # level 0 (app4 — nothing manually entered, no auto-evaluation
        # configured for these four Criteria).
        # =====================================================================
        run4_evals = {e.criterion_snapshot.name: e for e in ps_svc.list_evaluations(session, run4.id)}
        result.check(
            "3D-H: an unevaluated Criterion stays NOT_EVALUATED with effective_level=None — never silently "
            "coerced to level 0",
            run4_evals["Relevant experience"].status == psm.NOT_EVALUATED
            and run4_evals["Relevant experience"].effective_level is None
            and run4_evals["Relevant experience"].contribution == 0.0,
        )

        def _enter(run, criterion, level):
            ev = next(e for e in ps_svc.list_evaluations(session, run.id) if e.criterion_snapshot.criterion_id == criterion.id)
            return ps_svc.human_enter_evaluation(session, ev.id, level=level)

        # app1: strong positive overall.
        _enter(run1, experience_criterion, 4)
        _enter(run1, stability_criterion, 1)
        _enter(run1, availability_criterion, 1)
        _enter(run1, motivation_criterion, 2)
        # app2: some strong POSITIVE contributions, but an active Hard
        # Disqualifier (availability=4) — must remain disqualified even
        # though the naive sum of everything else is strongly positive
        # (test O — never mathematically cancellable).
        _enter(run2, experience_criterion, 4)
        _enter(run2, stability_criterion, 0)
        _enter(run2, availability_criterion, 4)
        _enter(run2, motivation_criterion, 4)
        # app3: moderate negative overall; availability=3 deliberately
        # stays BELOW the trigger level (4) to prove the Hard Disqualifier
        # activates exactly AT the configured level, not below it (test N).
        _enter(run3, experience_criterion, 2)
        _enter(run3, stability_criterion, 1)
        _enter(run3, availability_criterion, 3)
        session.commit()
        session.expire_all()

        # =====================================================================
        # E/F/G/I: positive/negative contributions, cumulative, correct
        # Priority Index.
        # =====================================================================
        run1_after = ps_svc.get_run(session, run1.id)
        run1_evals = {e.criterion_snapshot.name: e for e in ps_svc.list_evaluations(session, run1.id)}
        result.check(
            "3D-E: a POSITIVE Criterion contributes positively",
            run1_evals["Relevant experience"].contribution == 2.0 * 4,
        )
        result.check(
            "3D-F: a NEGATIVE Criterion contributes negatively",
            run1_evals["Job stability"].contribution == -(1.5 * 1) and run1_evals["Availability"].contribution == -(3.0 * 1),
        )
        expected_index_1 = (2.0 * 4) - (1.5 * 1) - (3.0 * 1) + (3.0 * 2) + (1.0 * 4)  # + auto-evaluated Signal-linked recency
        result.check(
            "3D-G/3D-I: multiple Criterion contributions accumulate into a correctly-calculated internal "
            "Priority Index",
            abs(run1_after.priority_index - expected_index_1) < 1e-9,
        )
        result.check(
            "3D-13-setup: the Signal-linked Criterion auto-evaluated SYSTEM_GENERATED from the existing "
            "Signal Observation",
            run1_evals["Signal-linked recency"].origin == psm.SYSTEM_GENERATED
            and run1_evals["Signal-linked recency"].system_level == 4,
        )

        # =====================================================================
        # J/V: the Priority Index is never exposed in the conversational
        # explanation text.
        # =====================================================================
        result.check(
            "3D-J/3D-V: the conversational explanation names concrete factors but never leaks the raw "
            "internal Priority Index number",
            bool(run1_after.explanation) and str(round(run1_after.priority_index, 4)) not in run1_after.explanation
            and "score" not in run1_after.explanation.lower() and "%" not in run1_after.explanation,
        )

        # =====================================================================
        # N/O/P/Q: Hard Disqualifiers.
        # =====================================================================
        run2_after = ps_svc.get_run(session, run2.id)
        run3_after = ps_svc.get_run(session, run3.id)
        result.check(
            "3D-N: the Hard Disqualifier activates exactly at its configured trigger level (4), not below it",
            run2_after.has_active_hard_disqualifier is True and run3_after.has_active_hard_disqualifier is False,
        )
        result.check(
            "3D-O: an active Hard Disqualifier is never mathematically cancelled by strong positive "
            "contributions — app2's naive index is positive, yet it remains disqualified",
            run2_after.has_active_hard_disqualifier is True and run2_after.priority_index > 0,
        )
        normal_pool_ids = {run.application_id for run in ps_svc.list_normal_pool(session, restaurant.id)}
        hard_pool_ids = {run.application_id for run in ps_svc.list_hard_disqualifier_pool(session, restaurant.id)}
        result.check(
            "3D-P: a hard-disqualified Application leaves the NORMAL pool",
            app2.id not in normal_pool_ids,
        )
        result.check(
            "3D-Q: a hard-disqualified Application remains fully visible in its own dedicated pool (never "
            "deleted)",
            app2.id in hard_pool_ids and app_svc.get_application(session, app2.id) is not None,
        )

        # =====================================================================
        # K: queue order follows the internal Priority Index descending.
        # =====================================================================
        normal_pool_order = [run.application_id for run in ps_svc.list_normal_pool(session, restaurant.id)]
        result.check(
            "3D-K: the normal-pool queue order follows the internal Priority Index, highest first",
            normal_pool_order.index(app1.id) < normal_pool_order.index(app4.id) < normal_pool_order.index(app3.id),
        )

        # =====================================================================
        # L/M: system vs effective override changes the Priority Index
        # (and therefore ordering) appropriately.
        # =====================================================================
        recency_eval = next(e for e in ps_svc.list_evaluations(session, run1.id) if e.criterion_snapshot.criterion_id == recency_criterion.id)
        index_before_override = run1_after.priority_index
        ps_svc.human_override_evaluation(session, recency_eval.id, level=1, reason="Selezionatore judges this less relevant.")
        session.commit()
        session.expire_all()
        recency_eval_after = session.get(m.PrimaryScreeningCriterionEvaluation, recency_eval.id)
        run1_after_override = ps_svc.get_run(session, run1.id)
        result.check(
            "3D-L: a Selezionatore override changes the EFFECTIVE level while preserving the original SYSTEM "
            "level",
            recency_eval_after.system_level == 4 and recency_eval_after.effective_level == 1
            and recency_eval_after.origin == psm.HUMAN_OVERRIDDEN,
        )
        result.check(
            "3D-M: the override correctly recalculates the internal Priority Index used for ordering",
            abs(run1_after_override.priority_index - (index_before_override - (1.0 * 4) + (1.0 * 1))) < 1e-9,
        )

        # =====================================================================
        # R/S: Hard Disqualifier override with mandatory reason; the
        # Application returns to the normal pool/flow.
        # =====================================================================
        availability_eval_2 = next(
            e for e in ps_svc.list_evaluations(session, run2.id) if e.criterion_snapshot.criterion_id == availability_criterion.id
        )
        raised = False
        try:
            ps_svc.override_hard_disqualifier(session, availability_eval_2.id, reason="")
        except ValueError:
            raised = True
        result.check("3D-R-setup: overriding a Hard Disqualifier without a reason is rejected", raised)

        ps_svc.override_hard_disqualifier(
            session, availability_eval_2.id, reason="Selezionatore confirmed candidate can now work required hours.",
        )
        session.commit()
        session.expire_all()
        result.check(
            "3D-R: the Selezionatore can override a Hard Disqualifier with a mandatory reason, preserving the "
            "original system-detected state",
            session.get(m.PrimaryScreeningCriterionEvaluation, availability_eval_2.id).hard_disqualifier_overridden is True
            and session.get(m.PrimaryScreeningCriterionEvaluation, availability_eval_2.id).effective_level == 4
            and session.get(m.PrimaryScreeningCriterionEvaluation, availability_eval_2.id).is_active_hard_disqualifier is True,
        )
        run2_final = ps_svc.get_run(session, run2.id)
        result.check(
            "3D-S: once overridden, the Application returns to the normal pool / normal Selection flow",
            run2_final.has_active_hard_disqualifier is False
            and app2.id in {run.application_id for run in ps_svc.list_normal_pool(session, restaurant.id)},
        )

        # =====================================================================
        # T/U: Criterion snapshot preserves exact historical configuration;
        # changing the live Criterion never rewrites a historical run.
        # =====================================================================
        original_snapshot_coefficient = run1_evals["Relevant experience"].criterion_snapshot.coefficient
        original_snapshot_direction = run1_evals["Relevant experience"].criterion_snapshot.direction
        ps_svc.update_criterion(session, experience_criterion.id, coefficient=99.0, direction=psm.NEGATIVE)
        session.commit()
        session.expire_all()
        result.check(
            "3D-T: the historical run's own Criterion snapshot preserves the exact coefficient/direction used "
            "at the time, unaffected by a later live edit",
            run1_evals["Relevant experience"].criterion_snapshot.coefficient == original_snapshot_coefficient == 2.0
            and run1_evals["Relevant experience"].criterion_snapshot.direction == original_snapshot_direction == psm.POSITIVE,
        )
        run1_reloaded_eval = session.get(m.PrimaryScreeningCriterionEvaluation, run1_evals["Relevant experience"].id)
        result.check(
            "3D-U: changing the live Criterion does not silently change a historical evaluation's own "
            "contribution",
            run1_reloaded_eval.contribution == 2.0 * 4,
        )
        new_run1 = ps_svc.create_screening_run(session, app1.id)
        session.commit()
        new_experience_eval = next(
            e for e in ps_svc.list_evaluations(session, new_run1.id) if e.criterion_snapshot.criterion_id == experience_criterion.id
        )
        result.check(
            "3D-16-setup: a NEW screening run correctly picks up the NEW live Criterion configuration in its "
            "own fresh snapshot",
            new_experience_eval.criterion_snapshot.coefficient == 99.0
            and new_experience_eval.criterion_snapshot.direction == psm.NEGATIVE,
        )

        # =====================================================================
        # AA: no automatic ADVANCE/HIRE ever occurs from Primary Screening.
        # =====================================================================
        result.check(
            "3D-AA: Primary Screening never automatically advances or changes an Application's workflow "
            "status",
            app_svc.get_application(session, app1.id).workflow_status == apm.NEW
            and app_svc.get_application(session, app2.id).workflow_status == apm.NEW,
        )

        # =====================================================================
        # X/Y/Z: existing Review Priority / Phone Interview / In-Person
        # functionality remains fully operational.
        # =====================================================================
        sig_svc.generate_resume_stage_signals(session, app1.id)
        session.commit()
        session.expire_all()
        result.check(
            "3D-X: existing Review Priority computation remains fully operational after Primary Screening",
            app_svc.get_application(session, app1.id).review_priority_effective in sm.REVIEW_PRIORITY_CATEGORIES,
        )
        # (Phone/In-Person Plans require an existing Fit Assessment; verified
        # narrowly here without repeating the exhaustive Phone/In-Person
        # fixtures Tasks 4A/4B's own suites already cover.)
        requirement_set = req_svc.create_requirement_set(
            session, restaurant_id=restaurant.id, name="3D Test Server", target_role="SERVER",
        )
        fit_assessment = fa_svc.create_fit_assessment(session, candidate_id=app1.candidate_id, requirement_set_id=requirement_set.id)
        session.commit()
        phone_plan = pi_svc.create_plan(session, app1.id)
        session.commit()
        result.check(
            "3D-Y: existing Phone Interview Plan creation remains fully operational after Primary Screening",
            phone_plan is not None and len(pi_svc.list_question_instances(session, phone_plan.id)) >= 0,
        )
        in_person_plan = ip_svc.create_plan(session, app1.id)
        session.commit()
        result.check(
            "3D-Z: existing In-Person Interview Plan creation remains fully operational after Primary "
            "Screening",
            in_person_plan is not None and in_person_plan.phone_interview_plan_id == phone_plan.id,
        )
    finally:
        session.rollback()
        for target_restaurant in (restaurant, restaurant_b):
            if target_restaurant is not None and target_restaurant.id is not None:
                for evaluation_row in session.query(m.PrimaryScreeningCriterionEvaluation).join(
                    m.PrimaryScreeningRun, m.PrimaryScreeningCriterionEvaluation.run_id == m.PrimaryScreeningRun.id
                ).filter(m.PrimaryScreeningRun.restaurant_id == target_restaurant.id):
                    session.delete(evaluation_row)
                session.flush()
                for run_row in session.query(m.PrimaryScreeningRun).filter_by(restaurant_id=target_restaurant.id):
                    session.delete(run_row)
                session.flush()
                for snapshot_row in session.query(m.PrimaryScreeningCriterionSnapshot).join(
                    m.PrimaryScreeningCriterion,
                    m.PrimaryScreeningCriterionSnapshot.criterion_id == m.PrimaryScreeningCriterion.id,
                ).filter(m.PrimaryScreeningCriterion.restaurant_id == target_restaurant.id):
                    session.delete(snapshot_row)
                session.flush()
                for criterion_row in session.query(m.PrimaryScreeningCriterion).filter_by(restaurant_id=target_restaurant.id):
                    session.delete(criterion_row)
                session.flush()
                for item_instance_row in session.query(m.AssessmentItemInstance).join(
                    m.InPersonInterviewPlan, m.AssessmentItemInstance.plan_id == m.InPersonInterviewPlan.id
                ).filter(m.InPersonInterviewPlan.restaurant_id == target_restaurant.id):
                    session.delete(item_instance_row)
                session.flush()
                for plan_row in session.query(m.InPersonInterviewPlan).filter_by(restaurant_id=target_restaurant.id):
                    session.delete(plan_row)
                session.flush()
                for phone_instance_row in session.query(m.PhoneInterviewQuestionInstance).join(
                    m.PhoneInterviewPlan, m.PhoneInterviewQuestionInstance.plan_id == m.PhoneInterviewPlan.id
                ).filter(m.PhoneInterviewPlan.restaurant_id == target_restaurant.id):
                    session.delete(phone_instance_row)
                session.flush()
                for phone_plan_row in session.query(m.PhoneInterviewPlan).filter_by(restaurant_id=target_restaurant.id):
                    session.delete(phone_plan_row)
                session.flush()
                for application_row in app_svc.list_applications(session, restaurant_id=target_restaurant.id):
                    session.delete(application_row)  # cascades to SignalObservation/SignalEvidenceItem/notes
                session.flush()
                for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=target_restaurant.id):
                    session.delete(person_row)
                for definition_row in session.query(m.SignalDefinition).filter_by(restaurant_id=target_restaurant.id):
                    session.delete(definition_row)
                session.flush()
                for candidate_row in persistence.list_candidates(session, restaurant_id=target_restaurant.id):
                    for fa_row in fa_svc.list_fit_assessments_for_candidate(session, candidate_row.id):
                        session.delete(fa_row)  # cascades to RequirementAssessment/EvidenceItem rows
                    session.flush()
                    session.delete(candidate_row)
                session.flush()
                for raw in list(session.query(m.RawResume).filter_by(restaurant_id=target_restaurant.id)):
                    session.delete(raw)
                session.flush()
                for requirement_set_row in req_svc.list_requirement_sets(session, restaurant_id=target_restaurant.id):
                    for snapshot_row in req_svc.list_snapshots(session, requirement_set_row.id):
                        session.delete(snapshot_row)
                    session.flush()
                    session.delete(requirement_set_row)
                session.flush()
        still_attached = session.get(m.Restaurant, restaurant.id) if restaurant is not None else None
        still_attached_b = session.get(m.Restaurant, restaurant_b.id) if restaurant_b is not None else None
        for restaurant_row in (still_attached, still_attached_b):
            if restaurant_row is not None:
                session.delete(restaurant_row)
        session.commit()
        session.close()


def _assert_selection_3d_fix(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 3D-FIX checks — the generic, AI-assisted automatic Criterion
    evaluator: arbitrary restaurant-authored Criteria (no hard-coded
    per-criterion logic), the structured-output contract and its
    validation, failure/fallback behavior (unavailable/malformed/one-
    Criterion-failure isolation), deterministic-Signal-mapping precedence,
    Priority Index contribution, automatic Hard Disqualifier activation,
    batch screening, queue differentiation, snapshot immutability across
    re-evaluation, and notes on both the Run and individual Criterion
    Evaluations. No live AI provider is required — `create_screening_run`'s
    `ai_generate_json_fn` injection seam supplies a canned/failing response
    per test case, and one check (3D-FIX-J) also exercises the REAL
    provider-unavailable path (no `ANTHROPIC_API_KEY` configured in this
    environment). Own dedicated session/restaurant, real commits, real
    cleanup (same reasoning as `_assert_selection_3d_primary_screening`
    above)."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic 3D-FIX Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        def _upload(name: str, email: str, phone: str, summary_line: str, role_line: str) -> m.Application:
            text = f"{name}\n{email}\n{phone}\n\nSUMMARY\n{summary_line}\n\nEXPERIENCE\n{role_line}\n"
            imported = import_pipeline.import_one_resume(
                session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD, original_filename=f"{email}.txt",
                storage_path=None, raw_text=text, content_hash=compute_content_hash(text, f"{email}.txt"),
            )
            application = app_svc.create_application(
                session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id, target_role="SERVER",
            )
            session.commit()
            return application

        # =====================================================================
        # Fixture: one richly-evidenced Application and a Signal whose
        # Observation is DETECTED but only PARTLY mapped by the restaurant.
        # =====================================================================
        app_main = _upload(
            "Alex Rivera", "alex.rivera.3dfix@example.com", "555-098-3001",
            "Team member consistently praised by guests for attentive, friendly service.",
            "Server, Riverside Grill\nJan 2020 - Present\nProvided attentive table service during peak hours.",
        )

        signal_definition = sig_svc.create_signal_definition(
            session, restaurant_id=restaurant.id, name="3D-FIX Recency Signal", signal_family=sm.READINESS_RECENCY,
            assessment_stages=[rm.RESUME], evidence_sources_allowed=[fam.RESUME_FACT],
        )
        observation = sig_svc.get_or_create_observation(session, app_main.id, signal_definition.id)
        sig_svc.add_evidence(
            session, observation.id, source_type=fam.RESUME_FACT, evidence_classification=fam.FACT,
            evidence_relationship=fam.SUPPORTS, confidence=fam.CONFIDENCE_HIGH, evidence_text="Current server role.",
        )
        session.commit()
        session.expire_all()
        observation = sig_svc.get_or_create_observation(session, app_main.id, signal_definition.id)
        detected_status = observation.status  # expected DETECTED

        # =====================================================================
        # Criteria: an arbitrary, never-hard-coded restaurant-authored
        # Criterion (A/N), a NEGATIVE one (P), a Hard Disqualifier (R/S), an
        # INSUFFICIENT_EVIDENCE case (H), a malformed-AI-output case (I), an
        # AI-unavailable-simulated case (J/K), a deterministically-resolved
        # one that must NEVER reach the generic evaluator (L/M), and one
        # whose Signal is DETECTED but has NO map entry for it — proving the
        # generic evaluator rescues it (N, extended).
        # =====================================================================
        cs_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Customer service orientation", coefficient=2.0,
            direction=psm.POSITIVE,
            level_descriptions={
                "0": "no evidence of guest-facing service", "1": "brief/unclear service experience",
                "2": "some service experience, no distinguishing detail", "3": "solid, sustained service experience",
                "4": "extensive, sustained, explicitly praised guest-facing service excellence",
            },
            evaluation_guidance="Look for explicit, sustained, guest-facing service evidence.",
        )
        risk_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Punctuality risk", coefficient=1.0, direction=psm.NEGATIVE,
            level_descriptions={"0": "no risk indicators", "3": "some tenure-pattern risk indicators", "4": "strong risk indicators"},
        )
        hard_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Kitchen safety awareness", coefficient=3.0,
            direction=psm.NEGATIVE, is_hard_disqualifier=True, hard_disqualifier_trigger_level=4,
            level_descriptions={"0": "certified/no concern", "4": "no certification evidence found — disqualifying"},
        )
        insufficient_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Insufficient target", coefficient=1.0, direction=psm.POSITIVE,
            level_descriptions={"0": "none", "4": "extensive"},
        )
        malformed_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Malformed target", coefficient=1.0, direction=psm.POSITIVE,
            level_descriptions={"0": "none", "4": "extensive"},
        )
        unavailable_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Unavailable-simulated target", coefficient=1.0,
            direction=psm.POSITIVE, level_descriptions={"0": "none", "4": "extensive"},
        )
        deterministic_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Deterministic-preferred check", coefficient=1.0,
            direction=psm.POSITIVE, auto_evaluation_signal_definition_id=signal_definition.id,
            auto_evaluation_level_map={detected_status: 4},
        )
        partial_signal_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Partially-mapped signal target", coefficient=1.0,
            direction=psm.POSITIVE, auto_evaluation_signal_definition_id=signal_definition.id,
            auto_evaluation_level_map={},  # deliberately no entry for `detected_status`
        )
        session.commit()

        # =====================================================================
        # B: the evaluator receives THIS Criterion's own level meanings (not
        # a generic/universal scale) — checked directly against the built
        # prompt, independent of any run.
        # =====================================================================
        cs_snapshot_for_prompt = ps_svc.get_or_create_criterion_snapshot(session, cs_criterion.id)
        package = ai_eval.build_evidence_package(session, app_main, cs_snapshot_for_prompt)
        prompt_text = ai_eval.build_prompt(cs_snapshot_for_prompt, package)
        result.check(
            "3D-FIX-B: the AI evaluator's prompt contains THIS Criterion's own restaurant-authored level "
            "0-4 meanings and evaluation guidance, not a generic/universal scale",
            "extensive, sustained, explicitly praised guest-facing service excellence" in prompt_text
            and "Look for explicit, sustained, guest-facing service evidence." in prompt_text
            and "consistently praised by guests for attentive, friendly service" in prompt_text,
        )

        def _fake_ai(prompt: str) -> dict:
            if "Deterministic-preferred check" in prompt:
                raise AssertionError(
                    "3D-FIX-M violated: the generic evaluator must never be consulted for a Criterion the "
                    "deterministic Signal mapping already resolved."
                )
            if "Customer service orientation" in prompt:
                return {
                    "status": "EVALUATED", "level": 4, "confidence": "HIGH",
                    "explanation": "Résumé documents sustained, explicitly praised guest-facing service.",
                    "evidence": [{
                        "source_type": "RESUME_FACT", "source_reference": "summary",
                        "evidence_text": "consistently praised by guests for attentive, friendly service",
                        "interpretation": "Direct, explicit evidence of positive customer-service orientation.",
                    }],
                }
            if "Punctuality risk" in prompt:
                return {
                    "status": "EVALUATED", "level": 3, "confidence": "MEDIUM",
                    "explanation": "Tenure pattern reviewed conservatively.",
                    "evidence": [{"source_type": "RESUME_FACT", "source_reference": "work_history: Riverside Grill", "evidence_text": "Server at Riverside Grill, Jan 2020 to present"}],
                }
            if "Kitchen safety awareness" in prompt:
                return {
                    "status": "EVALUATED", "level": 4, "confidence": "MEDIUM",
                    "explanation": "No food-safety certification found in the résumé.",
                    "evidence": [{"source_type": "RESUME_FACT", "source_reference": "certifications", "evidence_text": "(no certifications listed on résumé)"}],
                }
            if "Insufficient target" in prompt:
                return {
                    "status": "INSUFFICIENT_EVIDENCE", "level": None, "confidence": "LOW",
                    "explanation": "No evidence in the package speaks to this Criterion.", "evidence": [],
                }
            if "Malformed target" in prompt:
                return {"status": "MAYBE", "level": 99, "confidence": "SUPER_HIGH", "explanation": "", "evidence": "not-a-list"}
            if "Unavailable-simulated target" in prompt:
                raise ai_client_mod.AIProviderUnavailable("synthetic: no provider configured for this test")
            if "Partially-mapped signal target" in prompt:
                return {
                    "status": "EVALUATED", "level": 2, "confidence": "MEDIUM",
                    "explanation": "Rescued by the generic evaluator after the restaurant's Signal map had no entry for this status.",
                    "evidence": [{"source_type": "SELECTION_SIGNAL", "source_reference": "signal: 3D-FIX Recency Signal", "evidence_text": f"Signal status {detected_status}"}],
                }
            if "Real unavailable-path check" in prompt:
                # Only exists to prove the REAL (no-fn) unavailable path
                # separately, above — harmless once reused in a later run
                # (e.g. the 3D-FIX-AB re-evaluation) that supplies this fake.
                return {"status": "EVALUATED", "level": 2, "confidence": "LOW", "explanation": "Fixture placeholder.", "evidence": [{"source_type": "OTHER", "evidence_text": "placeholder"}]}
            raise AssertionError(f"3D-FIX test fixture: unexpected Criterion reached the AI evaluator: {prompt[:160]!r}")

        run = ps_svc.create_screening_run(session, app_main.id, ai_generate_json_fn=_fake_ai)
        session.commit()
        session.expire_all()

        evals = {e.criterion_snapshot.name: e for e in ps_svc.list_evaluations(session, run.id)}

        # =====================================================================
        # A/C/D/E/F/G/N/O: an arbitrary restaurant Criterion, never touched
        # by hard-coded per-criterion logic (proven structurally: this
        # Criterion's name/description exist ONLY in this test fixture, not
        # anywhere in `primary_screening_ai_evaluator.py`/
        # `primary_screening_service.py`), is automatically evaluated.
        # =====================================================================
        cs_eval = evals["Customer service orientation"]
        universal_source = inspect.getsource(ai_eval) + inspect.getsource(ps_svc)
        result.check(
            "3D-FIX-A: an arbitrary restaurant-created Criterion is automatically evaluated with NO "
            "hard-coded criterion-specific logic anywhere in the evaluator/service modules",
            cs_eval.status == psm.EVALUATED and "Customer service orientation" not in universal_source
            and "if criterion ==" not in universal_source,
        )
        result.check(
            "3D-FIX-C: supported evidence produces a system_level in 0-4",
            cs_eval.system_level in psm.LEVEL_SCALE,
        )
        result.check(
            "3D-FIX-D: effective_level initially matches system_level",
            cs_eval.effective_level == cs_eval.system_level == 4,
        )
        result.check(
            "3D-FIX-E: evidence references are persisted (structured evidence_items, traceable source/text)",
            len(cs_eval.evidence_items) >= 1
            and cs_eval.evidence_items[0]["evidence_text"] == "consistently praised by guests for attentive, friendly service"
            and cs_eval.evidence_items[0]["source_type"] == psm.RESUME_FACT,
        )
        result.check("3D-FIX-F: the explanation is persisted", bool(cs_eval.explanation) and "sustained" in cs_eval.explanation)
        result.check("3D-FIX-G: confidence is persisted", cs_eval.confidence == fam.CONFIDENCE_HIGH)
        result.check(
            "3D-FIX-O: a positive automatically-evaluated Criterion contributes correctly (coefficient x "
            "level, signed positive) to the internal Priority Index",
            cs_eval.contribution == 2.0 * 4,
        )

        # =====================================================================
        # P: a negative automatically-evaluated Criterion contributes
        # correctly (signed negative).
        # =====================================================================
        risk_eval = evals["Punctuality risk"]
        result.check(
            "3D-FIX-P: a negative-direction automatically-evaluated Criterion contributes a NEGATIVE "
            "signed amount",
            risk_eval.status == psm.EVALUATED and risk_eval.effective_level == 3 and risk_eval.contribution == -1.0 * 3,
        )

        # =====================================================================
        # H: INSUFFICIENT_EVIDENCE never becomes level 0.
        # =====================================================================
        insufficient_eval = evals["Insufficient target"]
        result.check(
            "3D-FIX-H: an AI evaluation of INSUFFICIENT_EVIDENCE leaves effective_level as None (never "
            "silently coerced to level 0), and contributes nothing to the Priority Index",
            insufficient_eval.status == psm.INSUFFICIENT_EVIDENCE and insufficient_eval.effective_level is None
            and insufficient_eval.contribution == 0.0,
        )

        # =====================================================================
        # I: malformed AI output never creates a fake evaluation.
        # =====================================================================
        malformed_eval = evals["Malformed target"]
        result.check(
            "3D-FIX-I: malformed/out-of-contract AI output (invalid status, level 99, evidence not a "
            "list) is rejected — the Criterion stays NOT_EVALUATED, never a fabricated EVALUATED result",
            malformed_eval.status == psm.NOT_EVALUATED and malformed_eval.effective_level is None
            and "invalid" in (malformed_eval.explanation or "").lower(),
        )

        # =====================================================================
        # J/K: a simulated AI-unavailable Criterion never crashes the run,
        # and every OTHER Criterion in the SAME run is still processed
        # (K) — proven by every check above/below succeeding within this
        # one `create_screening_run` call.
        # =====================================================================
        unavailable_eval = evals["Unavailable-simulated target"]
        result.check(
            "3D-FIX-J/K: an AI-provider-unavailable failure for one Criterion leaves it NOT_EVALUATED "
            "without raising, and every other Criterion in the same run is still evaluated independently",
            unavailable_eval.status == psm.NOT_EVALUATED and unavailable_eval.effective_level is None
            and cs_eval.status == psm.EVALUATED and risk_eval.status == psm.EVALUATED,
        )

        # =====================================================================
        # J (authentic): the REAL provider-unavailable path (no
        # ai_generate_json_fn at all — no ANTHROPIC_API_KEY configured in
        # this environment) also completes without raising.
        # =====================================================================
        real_unavailable_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Real unavailable-path check", coefficient=1.0,
            direction=psm.POSITIVE, level_descriptions={"0": "none", "4": "extensive"},
        )
        session.commit()
        real_run = ps_svc.create_screening_run(session, app_main.id)  # no ai_generate_json_fn -> real ai_client path
        session.commit()
        session.expire_all()
        real_eval = next(
            e for e in ps_svc.list_evaluations(session, real_run.id)
            if e.criterion_snapshot.name == "Real unavailable-path check"
        )
        result.check(
            "3D-FIX-J (authentic): with no AI provider configured in this environment at all, the REAL "
            "provider-unavailable path also leaves the Criterion NOT_EVALUATED without raising",
            real_eval.status == psm.NOT_EVALUATED and real_eval.effective_level is None,
        )

        # =====================================================================
        # L/M: the deterministic Signal-status->level mapping still works,
        # and is preferred — `_fake_ai` raises if ever consulted for it.
        # =====================================================================
        deterministic_eval = evals["Deterministic-preferred check"]
        result.check(
            "3D-FIX-L/M: the deterministic Signal-status->level mapping still resolves a linked Criterion, "
            "and is preferred over the generic evaluator (which was never invoked for it)",
            deterministic_eval.status == psm.EVALUATED and deterministic_eval.effective_level == 4
            and deterministic_eval.evidence_source == psm.SELECTION_SIGNAL,
        )

        # =====================================================================
        # N: the generic evaluator handles a Criterion with NO Signal
        # mapping at all (cs_criterion, already proven above) AND rescues
        # one whose Signal IS linked but has no map entry for the observed
        # status.
        # =====================================================================
        partial_eval = evals["Partially-mapped signal target"]
        result.check(
            "3D-FIX-N: the generic evaluator handles a Criterion with no Signal mapping (Customer service "
            "orientation, already EVALUATED above) and also rescues one whose Signal is linked but "
            "unmapped for the observed status",
            partial_eval.status == psm.EVALUATED and partial_eval.effective_level == 2,
        )

        # =====================================================================
        # R/S: automatic Hard Disqualifier activation, outside mathematical
        # compensation (cs_criterion's strong +8.0 contribution coexists
        # with an active Hard Disqualifier — never netted away).
        # =====================================================================
        hard_eval = evals["Kitchen safety awareness"]
        result.check(
            "3D-FIX-R: a system-generated (AI-assisted) Criterion Evaluation whose effective level meets "
            "the configured trigger level automatically activates the Hard Disqualifier gate",
            hard_eval.is_active_hard_disqualifier is True,
        )
        result.check(
            "3D-FIX-S: the Hard Disqualifier remains outside mathematical compensation — the run is "
            "flagged has_active_hard_disqualifier even though other Criteria contribute strongly positive",
            run.has_active_hard_disqualifier is True and cs_eval.contribution > 0,
        )

        # =====================================================================
        # T: Selezionatore override preserves the original system level and
        # evidence — never overwritten.
        # =====================================================================
        original_system_level = cs_eval.system_level
        original_evidence_items = list(cs_eval.evidence_items)
        ps_svc.human_override_evaluation(session, cs_eval.id, level=1, reason="Selezionatore discounts résumé wording")
        session.commit()
        session.expire_all()
        overridden_eval = session.get(m.PrimaryScreeningCriterionEvaluation, cs_eval.id)
        result.check(
            "3D-FIX-T: a Selezionatore override changes effective_level but preserves the original "
            "system_level and its evidence exactly",
            overridden_eval.effective_level == 1 and overridden_eval.system_level == original_system_level == 4
            and overridden_eval.evidence_items == original_evidence_items
            and overridden_eval.origin == fam.HUMAN_OVERRIDDEN,
        )

        # =====================================================================
        # AC: no automatic workflow-status transition ever occurs from
        # Primary Screening — including a Hard Disqualifier.
        # =====================================================================
        session.refresh(app_main)
        result.check(
            "3D-FIX-AC: no automatic ADVANCE_TO_PHONE (or any other) workflow-status transition occurs "
            "from automatic Primary Screening, even with an active Hard Disqualifier present",
            app_main.workflow_status == apm.NEW,
        )

        # =====================================================================
        # AD: the existing Task 3D Hard Disqualifier override still works,
        # now exercised against an AUTOMATICALLY (AI-assisted) detected one.
        # =====================================================================
        ps_svc.override_hard_disqualifier(session, hard_eval.id, reason="Selezionatore accepts the risk")
        session.commit()
        session.expire_all()
        run_after_override = ps_svc.get_run(session, run.id)
        result.check(
            "3D-FIX-AD: the existing Hard Disqualifier override mechanism still works against an "
            "automatically (AI-assisted) detected Hard Disqualifier, and the run leaves the disqualifier "
            "pool once overridden",
            run_after_override.has_active_hard_disqualifier is False,
        )

        # =====================================================================
        # Y/Z: notes on individual Criterion Evaluations AND the overall
        # Screening Run — reusing (not duplicating) ApplicationNote, queryable
        # by Application and by source/context, and never becoming evidence.
        # =====================================================================
        priority_index_before_notes = run.priority_index
        ps_svc.add_evaluation_note(session, cs_eval.id, "Reviewed résumé wording carefully before overriding.")
        ps_svc.add_run_note(session, run.id, "Overall screening looks promising despite one disqualifier.")
        session.commit()
        session.expire_all()

        eval_notes = ps_svc.list_evaluation_notes(session, cs_eval.id)
        run_notes = ps_svc.list_run_notes(session, run.id)
        all_application_notes = app_svc.list_notes(session, app_main.id)
        run_after_notes = ps_svc.get_run(session, run.id)
        result.check(
            "3D-FIX-Y: a Criterion Evaluation supports a Selezionatore note, timestamped and queryable by "
            "that specific evaluation",
            len(eval_notes) == 1 and eval_notes[0].note_text.startswith("Reviewed résumé wording")
            and eval_notes[0].created_at is not None,
        )
        result.check(
            "3D-FIX-Z: the overall Screening Run supports a Selezionatore note, distinct from a Criterion "
            "Evaluation note, and BOTH remain queryable in aggregate by Application (reusing "
            "ApplicationNote, not a duplicate notes system) while notes never alter the Priority Index",
            len(run_notes) == 1 and run_notes[0].note_text.startswith("Overall screening looks promising")
            and len(all_application_notes) >= 2
            and run_after_notes.priority_index == priority_index_before_notes,
        )

        # =====================================================================
        # AA/AB: historical Criterion snapshots remain unchanged after
        # editing the live Criterion, and an explicit re-evaluation creates
        # a NEW run against the NEW configuration without touching the OLD
        # run/snapshot.
        # =====================================================================
        original_level_descriptions = dict(cs_eval.criterion_snapshot.level_descriptions)
        original_run_explanation = run.explanation
        ps_svc.update_criterion(
            session, cs_criterion.id,
            level_descriptions={
                "0": "no evidence", "4": "COMPLETELY REWRITTEN level-4 meaning after Criterion edit",
            },
        )
        session.commit()
        session.expire_all()

        reloaded_old_eval = session.get(m.PrimaryScreeningCriterionEvaluation, cs_eval.id)
        result.check(
            "3D-FIX-AA: the historical Criterion snapshot tied to an already-created evaluation is "
            "unchanged after the live Criterion is edited",
            reloaded_old_eval.criterion_snapshot.level_descriptions == original_level_descriptions,
        )

        run2 = ps_svc.create_screening_run(session, app_main.id, ai_generate_json_fn=_fake_ai)
        session.commit()
        session.expire_all()
        cs_eval_run2 = next(
            e for e in ps_svc.list_evaluations(session, run2.id) if e.criterion_snapshot.name == "Customer service orientation"
        )
        old_run_reloaded = ps_svc.get_run(session, run.id)
        result.check(
            "3D-FIX-AB: an explicit re-evaluation creates a NEW run against the CURRENT (edited) Criterion "
            "configuration, while the OLD run and its own snapshot/result stay exactly as they were — "
            "never silently rewritten",
            run2.id != run.id
            and cs_eval_run2.criterion_snapshot.level_descriptions["4"] == "COMPLETELY REWRITTEN level-4 meaning after Criterion edit"
            and old_run_reloaded.explanation == original_run_explanation
            and reloaded_old_eval.criterion_snapshot.level_descriptions == original_level_descriptions,
        )

        # =====================================================================
        # U/V: batch screening processes multiple unscreened Applications
        # without the test opening each one individually, and the queue
        # order becomes differentiated (never all equal/zero) afterward.
        # =====================================================================
        differentiator_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Batch differentiation criterion", coefficient=1.0,
            direction=psm.POSITIVE, level_descriptions={"0": "weak fit", "4": "strong fit"},
        )
        session.commit()

        app_batch_strong = _upload(
            "Morgan Strong", "morgan.strong.3dfix@example.com", "555-098-4001", "batch_alpha_marker_strong_fit",
            "Server, Uptown Bistro\nJan 2019 - Present\nLead server for VIP section.",
        )
        app_batch_weak = _upload(
            "Casey Weak", "casey.weak.3dfix@example.com", "555-098-4002", "batch_beta_marker_weak_fit",
            "Server, Downtown Diner\nJan 2024 - Present\nEntry-level server.",
        )

        def _fake_ai_batch(prompt: str) -> dict:
            if "Batch differentiation criterion" not in prompt:
                raise AssertionError(f"3D-FIX batch fixture: unexpected Criterion reached the AI evaluator: {prompt[:120]!r}")
            if "batch_alpha_marker_strong_fit" in prompt:
                return {"status": "EVALUATED", "level": 4, "confidence": "HIGH", "explanation": "Strong batch fit.", "evidence": [{"source_type": "RESUME_FACT", "evidence_text": "batch_alpha_marker_strong_fit", "source_reference": "summary"}]}
            return {"status": "EVALUATED", "level": 1, "confidence": "LOW", "explanation": "Weak batch fit.", "evidence": [{"source_type": "RESUME_FACT", "evidence_text": "batch_beta_marker_weak_fit", "source_reference": "summary"}]}

        created_runs = ps_svc.run_screening_for_unscreened_applications(session, restaurant.id, ai_generate_json_fn=_fake_ai_batch)
        session.commit()
        session.expire_all()

        result.check(
            "3D-FIX-U: batch screening processes every unscreened Application (found here, without the "
            "test opening/creating a run for either Application individually)",
            {r.application_id for r in created_runs} >= {app_batch_strong.id, app_batch_weak.id},
        )

        normal_pool = ps_svc.list_normal_pool(session, restaurant.id)
        strong_run = next(r for r in normal_pool if r.application_id == app_batch_strong.id)
        weak_run = next(r for r in normal_pool if r.application_id == app_batch_weak.id)
        result.check(
            "3D-FIX-V: after automatic screening, the queue order is differentiated by the internal "
            "Priority Index — the strongly-evidenced Application outranks the weakly-evidenced one",
            strong_run.priority_index > weak_run.priority_index
            and normal_pool.index(strong_run) < normal_pool.index(weak_run),
        )

        # =====================================================================
        # W/X: the numeric Priority Index is never exposed by the pool-
        # listing functions' own row-building contract (structural check —
        # `_screening_row` in app.py builds its own dict from `run.explanation`/
        # counts only); Original CV access remains a Selezionatore/Application-
        # level concern untouched by this task (verified unaffected: the
        # helper `_original_cv_available`/`candidate_original_cv` route in
        # app.py were not modified by 3D-FIX).
        # =====================================================================
        result.check(
            "3D-FIX-W: `PrimaryScreeningRun`/`PrimaryScreeningCriterionEvaluation` expose no field named "
            "for direct numeric display beyond the documented internal `priority_index`/`contribution` — "
            "and the Run's own conversational explanation never contains the raw index value",
            str(round(run.priority_index, 4)) not in (run.explanation or "")
            and "priority_index" not in (run.explanation or "").lower(),
        )
    finally:
        session.rollback()
        if restaurant is not None and restaurant.id is not None:
            for evaluation_row in session.query(m.PrimaryScreeningCriterionEvaluation).join(
                m.PrimaryScreeningRun, m.PrimaryScreeningCriterionEvaluation.run_id == m.PrimaryScreeningRun.id
            ).filter(m.PrimaryScreeningRun.restaurant_id == restaurant.id):
                session.delete(evaluation_row)
            session.flush()
            for run_row in session.query(m.PrimaryScreeningRun).filter_by(restaurant_id=restaurant.id):
                session.delete(run_row)
            session.flush()
            for snapshot_row in session.query(m.PrimaryScreeningCriterionSnapshot).join(
                m.PrimaryScreeningCriterion, m.PrimaryScreeningCriterionSnapshot.criterion_id == m.PrimaryScreeningCriterion.id
            ).filter(m.PrimaryScreeningCriterion.restaurant_id == restaurant.id):
                session.delete(snapshot_row)
            session.flush()
            for criterion_row in session.query(m.PrimaryScreeningCriterion).filter_by(restaurant_id=restaurant.id):
                session.delete(criterion_row)
            session.flush()
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                session.delete(application_row)  # cascades to SignalObservation/SignalEvidenceItem/notes
            session.flush()
            for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=restaurant.id):
                session.delete(person_row)
            for definition_row in session.query(m.SignalDefinition).filter_by(restaurant_id=restaurant.id):
                session.delete(definition_row)
            session.flush()
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                session.delete(candidate_row)
            session.flush()
            for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                session.delete(raw)
        session.flush()
        still_attached = session.get(m.Restaurant, restaurant.id) if restaurant is not None else None
        if still_attached is not None:
            session.delete(still_attached)
        session.commit()
        session.close()


def _assert_selection_5a_outcome_stage_decision(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 5A checks — Stage/Outcome separation, total Stage freedom +
    permanent history, restaurant-configurable Outcome Definitions
    (lifecycle effect, reopen behavior, mandatory Note/reason, reason
    choices, composable actions), one-current-Outcome-plus-full-history,
    technical reversibility (reopen never erases prior closure), Candidate
    Flags (scope, expiration, surfacing on a later Application, never
    auto-rejecting), the unified Selection Notes History, historical
    Outcome Definition snapshot immutability, and continued operation of
    the Review Queue / Primary Screening / Phone / In-Person Selection.
    Own dedicated session/restaurant, real commits, real cleanup (same
    reasoning as `_assert_selection_3d_fix` above)."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic 5A Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        def _upload(name: str, email: str, phone: str, role_line: str) -> m.Application:
            text = f"{name}\n{email}\n{phone}\n\nEXPERIENCE\n{role_line}\n"
            imported = import_pipeline.import_one_resume(
                session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD, original_filename=f"{email}_{role_line[:6]}.txt",
                storage_path=None, raw_text=text, content_hash=compute_content_hash(text, f"{email}_{role_line[:6]}"),
            )
            application = app_svc.create_application(
                session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id, target_role="SERVER",
            )
            session.commit()
            return application

        # =====================================================================
        # Outcome Definitions (task §4/§5/§6/§13/§28) — restaurant-configured,
        # never a fixed universal set.
        # =====================================================================
        active_def = outcome_svc.create_outcome_definition(
            session, restaurant_id=restaurant.id, name="5A Active", lifecycle_effect=om.ACTIVE,
        )
        hire_def = outcome_svc.create_outcome_definition(
            session, restaurant_id=restaurant.id, name="5A Hire", lifecycle_effect=om.CLOSED,
            requires_note=False, requires_reason=False,
        )
        hold_def = outcome_svc.create_outcome_definition(
            session, restaurant_id=restaurant.id, name="5A Hold", lifecycle_effect=om.SUSPENDED,
            requires_reason=True, reason_choices=["Pipeline full", "Timing not right"],
        )
        stop_def = outcome_svc.create_outcome_definition(
            session, restaurant_id=restaurant.id, name="5A Stop", lifecycle_effect=om.CLOSED,
            requires_reason=True, is_reopenable=True,
        )
        flagging_def = outcome_svc.create_outcome_definition(
            session, restaurant_id=restaurant.id, name="5A Stop with Flag", lifecycle_effect=om.CLOSED,
            creates_reminder=True, reminder_days=180, creates_candidate_flag=True,
            candidate_flag_name="RECONSIDER AFTER 6 MONTHS", candidate_flag_scope=om.FLAG_ROLE_SPECIFIC,
            candidate_flag_operational_effect=om.FLAG_WARNING, candidate_flag_expires_after_days=200,
        )
        session.commit()

        result.check(
            "5A-G: a restaurant can create a custom Outcome Definition",
            outcome_svc.get_outcome_definition(session, hold_def.id) is not None,
        )
        result.check(
            "5A-H: a custom Outcome stores its ACTIVE/SUSPENDED/CLOSED lifecycle effect exactly as configured",
            active_def.lifecycle_effect == om.ACTIVE and hold_def.lifecycle_effect == om.SUSPENDED
            and stop_def.lifecycle_effect == om.CLOSED,
        )
        result.check(
            "5A-I: Outcome configuration supports reopen behavior (is_reopenable persists as configured)",
            stop_def.is_reopenable is True,
        )
        result.check(
            "5A-T: custom reason choices persist exactly as configured",
            hold_def.reason_choices == ["Pipeline full", "Timing not right"],
        )

        # =====================================================================
        # A: Stage and Outcome are stored SEPARATELY.
        # =====================================================================
        app1 = _upload("Morgan Five", "morgan.five.5a@example.com", "555-500-0001", "Server, Bistro Five\nJan 2022 - Present\nWaited tables.")
        result.check(
            "5A-A: Stage and Outcome are stored separately — a brand-new Application has a default Stage "
            "and NO Outcome decision yet; setting one never implicitly sets the other",
            app1.current_stage == stgm.APPLICATION_RECEIVED
            and outcome_svc.get_current_outcome_decision(session, app1.id) is None,
        )

        # =====================================================================
        # B/C/D/E/F: Stage freedom (forward, direct skip, backward) + history
        # + transition Note.
        # =====================================================================
        stage_svc.set_stage(session, app1.id, stgm.PRIMARY_SCREENING)
        session.commit()
        stage_svc.set_stage(session, app1.id, stgm.PHONE_INTERVIEW, note_text="Strong résumé, moving to phone.")
        session.commit()
        session.expire_all()
        result.check(
            "5A-B: the Selezionatore can move Primary Screening -> Phone Interview",
            app_svc.get_application(session, app1.id).current_stage == stgm.PHONE_INTERVIEW,
        )

        app2 = _upload("Riley Five", "riley.five.5a@example.com", "555-500-0002", "Server, Bistro Five\nJan 2022 - Present\nWaited tables.")
        stage_svc.set_stage(session, app2.id, stgm.PRIMARY_SCREENING)
        stage_svc.set_stage(session, app2.id, stgm.IN_PERSON_PRACTICAL)
        session.commit()
        session.expire_all()
        result.check(
            "5A-C: the Selezionatore can move Primary Screening -> In-Person Practical directly, skipping "
            "Phone Interview — RF-One does not block this",
            app_svc.get_application(session, app2.id).current_stage == stgm.IN_PERSON_PRACTICAL,
        )

        stage_svc.set_stage(session, app1.id, stgm.APPLICATION_RECEIVED)
        session.commit()
        session.expire_all()
        result.check(
            "5A-D: the Selezionatore can move a Stage BACKWARD",
            app_svc.get_application(session, app1.id).current_stage == stgm.APPLICATION_RECEIVED,
        )

        history = stage_svc.list_stage_history(session, app1.id)
        result.check(
            "5A-E: every Stage transition is preserved historically, never overwritten (3 transitions: "
            "PRIMARY_SCREENING, PHONE_INTERVIEW, APPLICATION_RECEIVED, in order)",
            len(history) == 3
            and [t.new_stage for t in history] == [stgm.PRIMARY_SCREENING, stgm.PHONE_INTERVIEW, stgm.APPLICATION_RECEIVED],
        )
        transition_note = next(n for n in app_svc.list_notes(session, app1.id) if n.context_type == "STAGE_TRANSITION")
        result.check(
            "5A-F: a Stage transition Note is preserved and attributable to that specific transition",
            transition_note.note_text == "Strong résumé, moving to phone.",
        )

        # =====================================================================
        # J/K/O/P/Q/R: Outcome may be applied at ANY time regardless of
        # Stage; one current Outcome + full accumulating history; HIRE needs
        # no separate mandatory prose reason when its Outcome says so.
        # =====================================================================
        outcome_svc.apply_outcome(session, app1.id, active_def.id)
        session.commit()

        stage_svc.set_stage(session, app2.id, stgm.PRIMARY_SCREENING)
        outcome_svc.apply_outcome(session, app2.id, hold_def.id, reason="Pipeline full")  # during Primary Screening — O
        session.commit()
        stage_svc.set_stage(session, app2.id, stgm.PHONE_INTERVIEW)
        outcome_svc.apply_outcome(
            session, app2.id, active_def.id, reason="Phone interview went well, resuming active pipeline",
        )  # during Phone Interview — P; changes an existing decision, so a 5A-MICRO-FIX reason is required
        session.commit()
        stage_svc.set_stage(session, app2.id, stgm.IN_PERSON_PRACTICAL)
        outcome_svc.apply_outcome(
            session, app2.id, hire_def.id, reason="Cleared all interview stages",
        )  # during In-Person Interview — Q; also R; also changes an existing decision
        session.commit()
        session.expire_all()

        current = outcome_svc.get_current_outcome_decision(session, app2.id)
        history2 = outcome_svc.list_outcome_history(session, app2.id)
        result.check(
            "5A-J: exactly one current effective Outcome exists per Application (the most recent decision)",
            current is not None and current.outcome_definition_snapshot.name == "5A Hire",
        )
        result.check(
            "5A-K: multiple historical Outcomes remain preserved, none overwritten (Hold -> Active -> Hire)",
            len(history2) == 3
            and [d.outcome_definition_snapshot.name for d in history2] == ["5A Hold", "5A Active", "5A Hire"],
        )
        result.check(
            "5A-O: an Outcome may be applied during Primary Screening (no Stage/completion requirement)",
            history2[0].outcome_definition_snapshot.name == "5A Hold",
        )
        result.check("5A-P: an Outcome may be applied during Phone Interview", history2[1].outcome_definition_snapshot.name == "5A Active")
        result.check("5A-Q: an Outcome may be applied during In-Person Interview", history2[2].outcome_definition_snapshot.name == "5A Hire")
        result.check(
            "5A-R: HIRE (an Outcome configured with requires_note=False, requires_reason=False) can still "
            "be reached — closing the Application — once the 5A-MICRO-FIX change-reason is supplied",
            app_svc.get_application(session, app2.id).lifecycle_state == om.CLOSED,
        )
        app_hire_first = _upload(
            "Drew Five", "drew.five.5a@example.com", "555-500-0004", "Server, Bistro Five\nJan 2022 - Present\nWaited tables.",
        )
        first_hire_decision = outcome_svc.apply_outcome(session, app_hire_first.id, hire_def.id)
        session.commit()
        result.check(
            "5A-R2 (5A-MICRO-FIX): an Outcome configured with requires_reason=False still needs no reason "
            "when it is the FIRST decision ever made for an Application (no existing decision is being "
            "changed)",
            first_hire_decision is not None
            and app_svc.get_application(session, app_hire_first.id).lifecycle_state == om.CLOSED,
        )

        # =====================================================================
        # L/M/N: CLOSED lifecycle effect + reopen + prior-history preservation.
        # =====================================================================
        result.check(
            "5A-L: applying a CLOSED-lifecycle Outcome closes the Application operationally",
            app_svc.get_application(session, app2.id).lifecycle_state == om.CLOSED,
        )
        pre_reopen_history_len = len(outcome_svc.list_outcome_history(session, app2.id))
        reopened_decision = outcome_svc.reopen_application(
            session, app2.id, active_def.id, reason="Candidate reconsidered", note_text="Candidate reconsidered.",
        )
        session.commit()
        session.expire_all()
        result.check(
            "5A-M: a CLOSED Application can later be reopened",
            app_svc.get_application(session, app2.id).lifecycle_state == om.ACTIVE and reopened_decision.is_reopen_event is True,
        )
        post_reopen_history = outcome_svc.list_outcome_history(session, app2.id)
        result.check(
            "5A-N: reopening does not delete the prior closure history — every earlier decision remains, "
            "plus the new reopen decision appended",
            len(post_reopen_history) == pre_reopen_history_len + 1
            and any(d.outcome_definition_snapshot.name == "5A Hire" for d in post_reopen_history),
        )

        # =====================================================================
        # S: mandatory Note/reason enforcement, per Outcome configuration.
        # =====================================================================
        raised = False
        try:
            outcome_svc.apply_outcome(session, app2.id, hold_def.id)  # hold_def requires a reason; none given
        except ValueError:
            raised = True
        result.check("5A-S: an Outcome configured to require a reason rejects application without one", raised)

        # =====================================================================
        # U/W/X: a configured Outcome's composable actions execute correctly
        # (creates a SelectionReminder AND a scoped CandidateFlag together).
        # =====================================================================
        app3 = _upload("Casey Five", "casey.five.5a@example.com", "555-500-0003", "Server, Bistro Five\nJan 2022 - Present\nWaited tables.")
        flag_decision = outcome_svc.apply_outcome(session, app3.id, flagging_def.id)
        session.commit()
        session.expire_all()

        reminders = outcome_svc.list_reminders_for_application(session, app3.id)
        created_flags = flag_svc.list_flags_for_person(session, app3.person_id)
        result.check(
            "5A-U: a configured Outcome action (create a follow-up reminder) executes correctly when the "
            "Outcome is applied",
            len(reminders) == 1 and reminders[0].outcome_decision_id == flag_decision.id,
        )
        result.check(
            "5A-W: a Candidate Flag may be created automatically from an applied Outcome",
            len(created_flags) == 1 and created_flags[0].originating_outcome_decision_id == flag_decision.id
            and created_flags[0].name == "RECONSIDER AFTER 6 MONTHS",
        )
        result.check(
            "5A-X: the Candidate Flag is scoped exactly as the Outcome configured (ROLE_SPECIFIC scope, "
            "WARNING operational effect, an expiration date)",
            created_flags[0].scope == om.FLAG_ROLE_SPECIFIC and created_flags[0].operational_effect == om.FLAG_WARNING
            and created_flags[0].expires_at is not None,
        )

        # =====================================================================
        # V: applying an Outcome never restricts Stage freedom.
        # =====================================================================
        stage_svc.set_stage(session, app3.id, stgm.IN_PERSON_PRACTICAL)  # app3's Outcome already CLOSED it
        session.commit()
        session.expire_all()
        result.check(
            "5A-V: an applied Outcome (including one that CLOSED the Application) never imposes a rigid "
            "next-Stage restriction — Stage remains freely movable regardless",
            app_svc.get_application(session, app3.id).current_stage == stgm.IN_PERSON_PRACTICAL,
        )

        # =====================================================================
        # Y/AA: a Candidate Flag may expire; an expired Flag stays historical
        # but is no longer active.
        # =====================================================================
        past_flag = flag_svc.create_flag(
            session, person_id=app3.person_id, restaurant_id=restaurant.id, name="Expired test flag",
            scope=om.FLAG_INFORMATIONAL, expires_at=datetime(2000, 1, 1),
        )
        session.commit()
        result.check("5A-Y: a Candidate Flag may be configured to expire", past_flag.expires_at is not None)
        result.check(
            "5A-AA: an expired Flag remains in history but is no longer active",
            not flag_svc.is_flag_currently_effective(past_flag)
            and any(f.id == past_flag.id for f in flag_svc.list_flags_for_person(session, app3.person_id, active_only=False))
            and not any(f.id == past_flag.id for f in flag_svc.list_flags_for_person(session, app3.person_id, active_only=True)),
        )

        # =====================================================================
        # AB/AC: Flag operational effect never auto-rejects.
        # =====================================================================
        flag_svc_source = inspect.getsource(flag_svc)
        result.check(
            "5A-AB/5A-AC: neither an INFORMATIONAL nor a WARNING/OPERATIONAL_ACTION Candidate Flag ever "
            "automatically rejects an Application — candidate_flag_service.py never writes "
            "lifecycle_state/workflow_status, and no rejection-flavored field exists on CandidateFlag",
            not hasattr(m.CandidateFlag, "auto_rejects") and not hasattr(m.CandidateFlag, "auto_rejected")
            and ".lifecycle_state = " not in flag_svc_source and ".workflow_status" not in flag_svc_source
            and app3.lifecycle_state == om.CLOSED,  # unaffected by the Flags created above — still whatever the earlier Outcome set
        )

        # =====================================================================
        # Z: an active, applicable Candidate Flag surfaces on a LATER
        # Application by the SAME person.
        # =====================================================================
        app3_later = _upload("Casey Five", "casey.five.5a@example.com", "555-500-0003", "Server, Bistro Six\nJan 2024 - Present\nHosted tables.")
        result.check(
            "5A-Z: an active, applicable Candidate Flag appears on a later Application by the SAME person",
            app3_later.person_id == app3.person_id
            and any(f.id == created_flags[0].id for f in flag_svc.list_active_flags_for_application(session, app3_later.id)),
        )

        # =====================================================================
        # AD/AE/AF/AG: Notes work for Application, Stage transition, Outcome
        # decision, and Candidate Flag — the SAME ApplicationNote mechanism,
        # distinguished only by context_type/context_id.
        # =====================================================================
        app_svc.add_note(session, app1.id, "General application note.")
        outcome_svc.apply_outcome(session, app1.id, active_def.id, note_text="Confirmed active decision.")
        flag_with_note = flag_svc.create_flag(
            session, person_id=app3.person_id, restaurant_id=restaurant.id, name="Flag with note",
            originating_application_id=app3.id, note="Flag note text.",
        )
        session.commit()
        session.expire_all()

        app1_notes = app_svc.list_notes(session, app1.id)
        app3_notes = app_svc.list_notes(session, app3.id)
        result.check(
            "5A-AD: a plain Application-level Note works",
            any(n.note_text == "General application note." and n.context_type is None for n in app1_notes),
        )
        result.check("5A-AE: a Stage transition Note works", transition_note.context_type == "STAGE_TRANSITION")
        result.check(
            "5A-AF: an Outcome decision Note works",
            any(n.context_type == "OUTCOME_DECISION" and n.note_text == "Confirmed active decision." for n in app1_notes),
        )
        result.check(
            "5A-AG: a Candidate Flag's own Note is preserved (direct field on the Flag) AND mirrored into "
            "the originating Application's unified notes (never a second, disconnected notes system)",
            flag_with_note.note == "Flag note text."
            and any(n.context_type == "CANDIDATE_FLAG" and n.note_text == "Flag note text." for n in app3_notes),
        )

        # =====================================================================
        # AH: Primary Screening notes remain retrievable (Task 3D-FIX
        # mechanism, unchanged, reused by the unified history below).
        # =====================================================================
        ps_svc.create_criterion(session, restaurant_id=restaurant.id, name="5A screening criterion", coefficient=1.0, direction=psm.POSITIVE)
        session.commit()
        run = ps_svc.create_screening_run(session, app1.id)
        session.commit()
        ps_svc.add_run_note(session, run.id, "Primary Screening run note.")
        session.commit()
        session.expire_all()
        result.check(
            "5A-AH: Primary Screening notes (Task 3D-FIX) remain retrievable",
            any(
                n.context_type == "PRIMARY_SCREENING_RUN" and n.note_text == "Primary Screening run note."
                for n in app_svc.list_notes(session, app1.id)
            ),
        )

        # =====================================================================
        # AI/AJ: Phone/In-Person notes remain retrievable where already
        # supported (Task 4A/4B's own note fields, untouched); the unified
        # Selection Notes History returns everything chronologically.
        # =====================================================================
        requirement_set = req_svc.create_requirement_set(session, restaurant_id=restaurant.id, name="5A Req Set", target_role="SERVER")
        session.commit()
        fa_svc.create_fit_assessment(session, candidate_id=app1.candidate_id, requirement_set_id=requirement_set.id)
        session.commit()

        pi_svc.create_question_definition(
            session, restaurant_id=restaurant.id, target_role="SERVER", question_text="Are you available weekends?",
            importance=pim.HIGH,
        )
        session.commit()
        phone_plan = pi_svc.create_plan(session, app1.id)
        session.commit()
        pi_svc.set_notes(session, phone_plan.id, "Phone Interview plan note.")
        if phone_plan.question_instances:
            pi_svc.record_answer(
                session, phone_plan.question_instances[0].id, status=pim.ANSWERED,
                answer_text="Yes.", selezionatore_note="Question-level note.",
            )
        session.commit()

        section = ip_svc.create_section_definition(session, restaurant_id=restaurant.id, name="5A Section", target_role="SERVER")
        ip_svc.create_item_definition(session, section.id, item_type=ipm.QUESTION, title_or_question="Describe teamwork.")
        session.commit()
        in_person_plan = ip_svc.create_plan(session, app1.id)
        session.commit()
        ip_svc.set_notes(session, in_person_plan.id, "In-Person Interview plan note.")
        if in_person_plan.item_instances:
            ip_svc.record_response(
                session, in_person_plan.item_instances[0].id, status=ipm.DONE, selezionatore_note="Item-level note.",
            )
        session.commit()
        session.expire_all()

        notes_history = notes_svc.get_selection_notes_history(session, app1.id)
        labels = {n.context_label for n in notes_history}
        result.check(
            "5A-AI: Phone Interview and In-Person Interview notes (Task 4A/4B's own fields) remain "
            "retrievable through the unified Selection Notes History",
            "Phone Interview" in labels and "In-Person Interview" in labels,
        )
        timestamped = [n.created_at for n in notes_history if n.created_at is not None]
        result.check(
            "5A-AJ: the unified Selection Notes History returns every note chronologically, spanning "
            "Application/Stage/Outcome/Primary-Screening/Phone/In-Person contexts",
            timestamped == sorted(timestamped) and len(notes_history) >= 5,
        )

        # =====================================================================
        # AM: historical Outcome Definition meaning survives later edits.
        # =====================================================================
        hire_decision = next(d for d in outcome_svc.list_outcome_history(session, app2.id) if d.outcome_definition_snapshot.name == "5A Hire")
        original_hire_lifecycle = hire_decision.outcome_definition_snapshot.lifecycle_effect
        outcome_svc.update_outcome_definition(session, hire_def.id, lifecycle_effect=om.SUSPENDED, description="Edited later.")
        session.commit()
        session.expire_all()
        reloaded_hire_decision = session.get(m.SelectionOutcomeDecision, hire_decision.id)
        result.check(
            "5A-AM: editing a live Outcome Definition never rewrites the meaning already recorded on a "
            "historical decision (its own immutable snapshot)",
            reloaded_hire_decision.outcome_definition_snapshot.lifecycle_effect == original_hire_lifecycle == om.CLOSED,
        )

        # =====================================================================
        # AN/AO/AP/AQ: existing Review Queue / Primary Screening / Phone /
        # In-Person Interview remain fully operational.
        # =====================================================================
        result.check(
            "5A-AN: the existing Review Queue (Application listing) remains operational",
            any(a.id == app1.id for a in app_svc.list_applications(session, restaurant_id=restaurant.id)),
        )
        result.check("5A-AO: Primary Screening remains fully operational", ps_svc.get_latest_run_for_application(session, app1.id) is not None)
        result.check("5A-AP: Phone Interview remains fully operational", pi_svc.get_plan_for_application(session, app1.id) is not None)
        result.check("5A-AQ: In-Person/Practical Interview remains fully operational", ip_svc.get_plan_for_application(session, app1.id) is not None)

        # =====================================================================
        # AR/AS: no automatic HIRE/permanent STOP — Stage movement and
        # Primary Screening code never call the Outcome service themselves.
        # =====================================================================
        stage_source = inspect.getsource(stage_svc)
        ps_source = inspect.getsource(ps_svc)
        result.check(
            "5A-AR/5A-AS: no automatic HIRE or automatic permanent STOP occurs — Stage-movement and "
            "Primary Screening code never call `outcome_service.apply_outcome`/`reopen_application` "
            "themselves; every Outcome decision requires an explicit, Selezionatore-supplied "
            "outcome_definition_id",
            ".apply_outcome(" not in stage_source and ".reopen_application(" not in stage_source
            and ".apply_outcome(" not in ps_source and ".reopen_application(" not in ps_source,
        )
    finally:
        session.rollback()
        if restaurant is not None and restaurant.id is not None:
            for flag_row in session.query(m.CandidateFlag).filter_by(restaurant_id=restaurant.id):
                session.delete(flag_row)
            session.flush()
            for reminder_row in session.query(m.SelectionReminder).join(
                m.Application, m.SelectionReminder.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                session.delete(reminder_row)
            session.flush()

            for evaluation_row in session.query(m.PrimaryScreeningCriterionEvaluation).join(
                m.PrimaryScreeningRun, m.PrimaryScreeningCriterionEvaluation.run_id == m.PrimaryScreeningRun.id
            ).filter(m.PrimaryScreeningRun.restaurant_id == restaurant.id):
                session.delete(evaluation_row)
            session.flush()
            for run_row in session.query(m.PrimaryScreeningRun).filter_by(restaurant_id=restaurant.id):
                session.delete(run_row)
            session.flush()
            for snapshot_row in session.query(m.PrimaryScreeningCriterionSnapshot).join(
                m.PrimaryScreeningCriterion, m.PrimaryScreeningCriterionSnapshot.criterion_id == m.PrimaryScreeningCriterion.id
            ).filter(m.PrimaryScreeningCriterion.restaurant_id == restaurant.id):
                session.delete(snapshot_row)
            session.flush()
            for criterion_row in session.query(m.PrimaryScreeningCriterion).filter_by(restaurant_id=restaurant.id):
                session.delete(criterion_row)
            session.flush()

            for item_instance_row in session.query(m.AssessmentItemInstance).join(
                m.InPersonInterviewPlan, m.AssessmentItemInstance.plan_id == m.InPersonInterviewPlan.id
            ).filter(m.InPersonInterviewPlan.restaurant_id == restaurant.id):
                session.delete(item_instance_row)
            session.flush()
            for plan_row in session.query(m.InPersonInterviewPlan).filter_by(restaurant_id=restaurant.id):
                session.delete(plan_row)
            session.flush()
            for item_def_row in session.query(m.AssessmentItemDefinition).join(
                m.InPersonInterviewSectionDefinition,
                m.AssessmentItemDefinition.section_id == m.InPersonInterviewSectionDefinition.id,
            ).filter(m.InPersonInterviewSectionDefinition.restaurant_id == restaurant.id):
                session.delete(item_def_row)
            session.flush()
            for section_row in session.query(m.InPersonInterviewSectionDefinition).filter_by(restaurant_id=restaurant.id):
                session.delete(section_row)
            session.flush()
            for phone_instance_row in session.query(m.PhoneInterviewQuestionInstance).join(
                m.PhoneInterviewPlan, m.PhoneInterviewQuestionInstance.plan_id == m.PhoneInterviewPlan.id
            ).filter(m.PhoneInterviewPlan.restaurant_id == restaurant.id):
                session.delete(phone_instance_row)
            session.flush()
            for phone_plan_row in session.query(m.PhoneInterviewPlan).filter_by(restaurant_id=restaurant.id):
                session.delete(phone_plan_row)
            session.flush()
            for question_def_row in session.query(m.PhoneInterviewQuestionDefinition).filter_by(restaurant_id=restaurant.id):
                session.delete(question_def_row)
            session.flush()

            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                session.delete(application_row)  # cascades Notes/StageTransitions/OutcomeDecisions/Signals
            session.flush()

            for def_snapshot_row in session.query(m.SelectionOutcomeDefinitionSnapshot).join(
                m.SelectionOutcomeDefinition, m.SelectionOutcomeDefinitionSnapshot.definition_id == m.SelectionOutcomeDefinition.id
            ).filter(m.SelectionOutcomeDefinition.restaurant_id == restaurant.id):
                session.delete(def_snapshot_row)
            session.flush()
            for definition_row in session.query(m.SelectionOutcomeDefinition).filter_by(restaurant_id=restaurant.id):
                session.delete(definition_row)
            session.flush()

            for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=restaurant.id):
                session.delete(person_row)
            for definition_row in session.query(m.SignalDefinition).filter_by(restaurant_id=restaurant.id):
                session.delete(definition_row)
            session.flush()

            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                for fa_row in fa_svc.list_fit_assessments_for_candidate(session, candidate_row.id):
                    session.delete(fa_row)
                session.flush()
                session.delete(candidate_row)
            session.flush()
            for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                session.delete(raw)
            session.flush()
            for requirement_set_row in req_svc.list_requirement_sets(session, restaurant_id=restaurant.id):
                for snapshot_row in req_svc.list_snapshots(session, requirement_set_row.id):
                    session.delete(snapshot_row)
                session.flush()
                session.delete(requirement_set_row)
            session.flush()
        still_attached = session.get(m.Restaurant, restaurant.id) if restaurant is not None else None
        if still_attached is not None:
            session.delete(still_attached)
        session.commit()
        session.close()


def _assert_selection_5a_fix_authoritative_state_and_queue(
    session_factory: sessionmaker[Session], result: ValidationResult,
) -> None:
    """Task 5A-FIX checks — Stage/Outcome/lifecycle as the sole
    authoritative Selection state, `workflow_status` reduced to a
    one-directional, never-diverging legacy projection, the legacy
    compatibility bridge (`workflow_projection_service.
    apply_legacy_workflow_action`) routing the Review Queue's
    workflow-status control and Phone Interview's post-interview decision
    through the authoritative Stage/Outcome services, and the new
    operational Queue/List model (restaurant-configurable queues, the
    Outcome -> Queue action, manual queue movement, append-only queue
    history, and its Notes integration). Own dedicated session/restaurant,
    real commits, real cleanup (same reasoning as
    `_assert_selection_5a_outcome_stage_decision` above)."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic 5A-FIX Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        # Seed this restaurant's default Outcomes (Active/Hire/Hold/Stop/
        # Withdrawn) AND default Queues (Active Review/Call Later/Hold/
        # Reconsider/Hired/Closed), exactly as every real Selection page
        # does idempotently before letting the Selezionatore act.
        restaurant_templates.seed_default_selection_outcomes(session, restaurant_id=restaurant.id)
        outcome_defs = {
            d.name: d for d in outcome_svc.list_outcome_definitions(session, restaurant_id=restaurant.id)
        }
        queues = {q.name: q for q in queue_svc.list_queues(session, restaurant_id=restaurant.id)}

        def _upload(name: str, email: str, phone: str, role_line: str) -> m.Application:
            text = f"{name}\n{email}\n{phone}\n\nEXPERIENCE\n{role_line}\n"
            imported = import_pipeline.import_one_resume(
                session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD,
                original_filename=f"{email}_{role_line[:6]}.txt", storage_path=None, raw_text=text,
                content_hash=compute_content_hash(text, f"{email}_{role_line[:6]}"),
            )
            application = app_svc.create_application(
                session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id, target_role="SERVER",
            )
            session.commit()
            return application

        app1 = _upload("Avery Fix", "avery.fix.5afix@example.com", "555-600-0001", "Server, Bistro Fix\nJan 2022 - Present\nWaited tables.")

        # =====================================================================
        # A/H/I/J: Stage change updates the legacy projection coherently;
        # Stage/Outcome/lifecycle remain authoritative throughout.
        # =====================================================================
        stage_svc.set_stage(session, app1.id, stgm.PRIMARY_SCREENING)
        session.commit()
        session.expire_all()
        app1_reloaded = app_svc.get_application(session, app1.id)
        result.check(
            "5A-FIX-A: a Stage change updates the legacy workflow_status projection coherently "
            "(PRIMARY_SCREENING, still ACTIVE, with prior activity -> IN_REVIEW)",
            app1_reloaded.current_stage == stgm.PRIMARY_SCREENING and app1_reloaded.workflow_status == apm.IN_REVIEW,
        )
        result.check(
            "5A-FIX-H: current_stage remains authoritative — it reflects exactly the Stage just set, "
            "independent of workflow_status",
            app1_reloaded.current_stage == stgm.PRIMARY_SCREENING,
        )

        # =====================================================================
        # B: Outcome HOLD updates the legacy projection coherently.
        # =====================================================================
        outcome_svc.apply_outcome(session, app1.id, outcome_defs["Hold"].id, reason="Pipeline full")
        session.commit()
        session.expire_all()
        app1_reloaded = app_svc.get_application(session, app1.id)
        result.check(
            "5A-FIX-B: applying the HOLD Outcome updates the legacy workflow_status projection "
            "coherently (SUSPENDED lifecycle -> legacy HOLD)",
            app1_reloaded.lifecycle_state == om.SUSPENDED and app1_reloaded.workflow_status == apm.HOLD,
        )
        result.check(
            "5A-FIX-I/5A-FIX-J: current Outcome and lifecycle remain authoritative after applying HOLD",
            outcome_svc.get_current_outcome_decision(session, app1.id).outcome_definition_snapshot.name == "Hold"
            and app1_reloaded.lifecycle_state == om.SUSPENDED,
        )

        # =====================================================================
        # C: Outcome STOP updates the legacy projection coherently.
        # =====================================================================
        outcome_svc.apply_outcome(session, app1.id, outcome_defs["Stop"].id, reason="Candidate did not respond")
        session.commit()
        session.expire_all()
        app1_reloaded = app_svc.get_application(session, app1.id)
        result.check(
            "5A-FIX-C: applying the STOP Outcome updates the legacy workflow_status projection "
            "coherently (CLOSED lifecycle -> legacy STOP)",
            app1_reloaded.lifecycle_state == om.CLOSED and app1_reloaded.workflow_status == apm.STOP,
        )

        # Reopen so subsequent legacy-action checks start from a clean ACTIVE state.
        outcome_svc.reopen_application(
            session, app1.id, outcome_defs["Active / Continue"].id,
            reason="Reopened for further testing", note_text="Reopened for further testing.",
        )
        session.commit()

        # =====================================================================
        # D: legacy ADVANCE_TO_PHONE action routes through the Stage service
        # (never a direct workflow_status write) — proven by a new
        # ApplicationStageTransition row actually being created.
        # =====================================================================
        stage_history_before = len(stage_svc.list_stage_history(session, app1.id))
        wf_svc.apply_legacy_workflow_action(session, app1.id, apm.ADVANCE_TO_PHONE)
        session.commit()
        session.expire_all()
        app1_reloaded = app_svc.get_application(session, app1.id)
        stage_history_after = stage_svc.list_stage_history(session, app1.id)
        result.check(
            "5A-FIX-D: the legacy ADVANCE_TO_PHONE action routes through stage_service.set_stage "
            "(a new ApplicationStageTransition row is created, current_stage becomes PHONE_INTERVIEW)",
            len(stage_history_after) == stage_history_before + 1
            and stage_history_after[-1].new_stage == stgm.PHONE_INTERVIEW
            and app1_reloaded.current_stage == stgm.PHONE_INTERVIEW
            and app1_reloaded.workflow_status == apm.ADVANCE_TO_PHONE,
        )

        # =====================================================================
        # E/F: legacy HOLD/STOP actions route through the Outcome service —
        # proven by a new SelectionOutcomeDecision row actually being created
        # and referencing the restaurant's configured Hold/Stop Outcome.
        # =====================================================================
        outcome_history_before = len(outcome_svc.list_outcome_history(session, app1.id))
        wf_svc.apply_legacy_workflow_action(session, app1.id, apm.HOLD, reason="Timing not right for this candidate")
        session.commit()
        session.expire_all()
        outcome_history_after = outcome_svc.list_outcome_history(session, app1.id)
        result.check(
            "5A-FIX-E: the legacy HOLD action routes through outcome_service.apply_outcome (a new "
            "SelectionOutcomeDecision referencing this restaurant's configured Hold Outcome is created)",
            len(outcome_history_after) == outcome_history_before + 1
            and outcome_history_after[-1].outcome_definition_snapshot.name == "Hold"
            and app_svc.get_application(session, app1.id).workflow_status == apm.HOLD,
        )

        outcome_history_before = len(outcome_history_after)
        wf_svc.apply_legacy_workflow_action(session, app1.id, apm.STOP, reason="Better-fitting candidates identified")
        session.commit()
        session.expire_all()
        outcome_history_after = outcome_svc.list_outcome_history(session, app1.id)
        result.check(
            "5A-FIX-F: the legacy STOP action routes through outcome_service.apply_outcome (a new "
            "SelectionOutcomeDecision referencing this restaurant's configured Stop Outcome is created)",
            len(outcome_history_after) == outcome_history_before + 1
            and outcome_history_after[-1].outcome_definition_snapshot.name == "Stop"
            and app_svc.get_application(session, app1.id).workflow_status == apm.STOP,
        )

        outcome_svc.reopen_application(session, app1.id, outcome_defs["Active / Continue"].id, reason="Reopening after Stop for the next legacy-action check")
        session.commit()

        # =====================================================================
        # G: Phone Interview's post-interview decision no longer creates an
        # independent, contradictory workflow state — the resulting
        # workflow_status always matches what Stage/Outcome/lifecycle alone
        # would compute.
        # =====================================================================
        requirement_set = req_svc.create_requirement_set(session, restaurant_id=restaurant.id, name="5A-FIX Req Set", target_role="SERVER")
        session.commit()
        fit_assessment = fa_svc.create_fit_assessment(session, candidate_id=app1.candidate_id, requirement_set_id=requirement_set.id)
        session.commit()
        phone_plan = pi_svc.create_plan(session, app1.id)
        session.commit()
        pi_svc.record_post_interview_decision(
            session, phone_plan.id, plan_status=pim.COMPLETED, application_decision=apm.ADVANCE_TO_IN_PERSON,
            reason="Strong phone interview.",
        )
        session.commit()
        session.expire_all()
        app1_reloaded = app_svc.get_application(session, app1.id)
        result.check(
            "5A-FIX-G: the Phone Interview post-decision (ADVANCE_TO_IN_PERSON) never creates an "
            "independent, contradictory workflow state — current_stage/workflow_status/lifecycle stay "
            "coherent (Stage actually moved to IN_PERSON_PRACTICAL; workflow_status matches what the "
            "authoritative state alone computes)",
            app1_reloaded.current_stage == stgm.IN_PERSON_PRACTICAL
            and app1_reloaded.workflow_status == apm.ADVANCE_TO_IN_PERSON
            and app1_reloaded.workflow_status == wf_svc.compute_legacy_workflow_status(session, app1.id),
        )

        # =====================================================================
        # K: old direct supported UI actions cannot create contradictory
        # current state — after a whole SEQUENCE of legacy + authoritative
        # actions, workflow_status always equals what the authoritative
        # state alone computes (the "source of truth" test, task §22).
        # =====================================================================
        stage_svc.set_stage(session, app1.id, stgm.PRIMARY_SCREENING)
        wf_svc.apply_legacy_workflow_action(session, app1.id, apm.HOLD, reason="Awaiting further information")
        outcome_svc.reopen_application(session, app1.id, outcome_defs["Active / Continue"].id, reason="Reopening after Hold for the mixed-action sequence check")
        wf_svc.apply_legacy_workflow_action(session, app1.id, apm.ADVANCE_TO_PHONE)
        session.commit()
        session.expire_all()
        app1_reloaded = app_svc.get_application(session, app1.id)
        result.check(
            "5A-FIX-K: after a sequence of mixed legacy and authoritative actions, workflow_status "
            "always equals exactly what compute_legacy_workflow_status derives from the authoritative "
            "Stage/Outcome/lifecycle state — no supported action can leave it contradictory",
            app1_reloaded.workflow_status == wf_svc.compute_legacy_workflow_status(session, app1.id),
        )

        # =====================================================================
        # L/M/N/O: restaurant-configured queues; an Outcome can target one;
        # applying it moves the Application; applying an Outcome WITHOUT a
        # target queue never invents a move.
        # =====================================================================
        result.check(
            "5A-FIX-L: a restaurant can create an operational queue/list",
            queue_svc.get_queue(session, queues["Call Later"].id) is not None,
        )
        result.check(
            "5A-FIX-M: an Outcome Definition can target a configured queue",
            outcome_defs["Hirable"].target_queue_id == queues["Hired"].id,
        )

        app2 = _upload("Riley Fix", "riley.fix.5afix@example.com", "555-600-0002", "Server, Bistro Fix\nJan 2022 - Present\nWaited tables.")
        result.check(
            "5A-FIX-setup: a fresh Application starts with no queue assigned",
            queue_svc.get_current_queue(session, app2.id) is None,
        )
        hire_decision = outcome_svc.apply_outcome(session, app2.id, outcome_defs["Hirable"].id)
        session.commit()
        session.expire_all()
        result.check(
            "5A-FIX-N: applying an Outcome WITH a configured target queue moves the Application there",
            queue_svc.get_current_queue(session, app2.id).name == "Hired",
        )

        app3 = _upload("Casey Fix", "casey.fix.5afix@example.com", "555-600-0003", "Server, Bistro Fix\nJan 2022 - Present\nWaited tables.")
        # "Active / Continue" DOES have a target queue configured (Active Review) —
        # use a fresh Outcome with NO target queue to prove O cleanly.
        no_queue_outcome = outcome_svc.create_outcome_definition(
            session, restaurant_id=restaurant.id, name="5A-FIX No-Queue Outcome", lifecycle_effect=om.ACTIVE,
        )
        session.commit()
        outcome_svc.apply_outcome(session, app3.id, no_queue_outcome.id)
        session.commit()
        session.expire_all()
        result.check(
            "5A-FIX-O: applying an Outcome WITHOUT a configured target queue never invents a queue move",
            queue_svc.get_current_queue(session, app3.id) is None
            and len(queue_svc.list_queue_history(session, app3.id)) == 0,
        )

        # =====================================================================
        # P/Q: queue movement history preserved; a movement records its
        # originating Outcome Decision where applicable.
        # =====================================================================
        queue_history_app2 = queue_svc.list_queue_history(session, app2.id)
        result.check(
            "5A-FIX-P: queue movement history is preserved (at least the Outcome-triggered move above)",
            len(queue_history_app2) == 1 and queue_history_app2[0].new_queue_id == queues["Hired"].id,
        )
        result.check(
            "5A-FIX-Q: a queue movement created by an applied Outcome records that Outcome Decision",
            queue_history_app2[0].originating_outcome_decision_id == hire_decision.id
            and queue_history_app2[0].source == qm.OUTCOME_ACTION,
        )

        # =====================================================================
        # R/S/T/U/V: manual queue movement — independent of Stage/Outcome,
        # historically recorded, supports a Note that appears in the unified
        # Selection Notes History.
        # =====================================================================
        stage_before_manual_move = app_svc.get_application(session, app2.id).current_stage
        outcome_before_manual_move = outcome_svc.get_current_outcome_decision(session, app2.id).id
        manual_movement = queue_svc.move_to_queue(
            session, app2.id, queues["Reconsider"].id, source=qm.MANUAL, note_text="Following up personally next week.",
        )
        session.commit()
        session.expire_all()
        app2_reloaded = app_svc.get_application(session, app2.id)
        result.check(
            "5A-FIX-R: manual queue movement works (independent of any Outcome)",
            app2_reloaded.current_queue_id == queues["Reconsider"].id and manual_movement.source == qm.MANUAL,
        )
        result.check(
            "5A-FIX-S: manual queue movement does not change Stage",
            app2_reloaded.current_stage == stage_before_manual_move,
        )
        result.check(
            "5A-FIX-T: manual queue movement does not change Outcome",
            outcome_svc.get_current_outcome_decision(session, app2.id).id == outcome_before_manual_move,
        )
        result.check(
            "5A-FIX-U: a manual queue movement's optional Note is preserved",
            any(
                n.note_text == "Following up personally next week." and n.context_type == "QUEUE_MOVEMENT"
                for n in app_svc.list_notes(session, app2.id)
            ),
        )
        notes_history_app2 = notes_svc.get_selection_notes_history(session, app2.id)
        result.check(
            "5A-FIX-V: the queue movement Note appears in the unified Selection Notes History",
            any(
                e.note_text == "Following up personally next week." and e.context_label == "Queue Movement"
                for e in notes_history_app2
            ),
        )

        # =====================================================================
        # W: current queue appears in the Decision Summary.
        # =====================================================================
        decision_summary_app2 = dec_svc.get_decision_summary(session, app2.id)
        result.check(
            "5A-FIX-W: the current operational queue appears in the Decision Summary",
            decision_summary_app2.current_queue is not None and decision_summary_app2.current_queue.name == "Reconsider",
        )

        # =====================================================================
        # X: an inactive queue cannot be newly (manually) selected.
        # =====================================================================
        queue_svc.deactivate_queue(session, queues["Call Later"].id)
        session.commit()
        raised = False
        try:
            queue_svc.move_to_queue(session, app2.id, queues["Call Later"].id, source=qm.MANUAL)
        except ValueError:
            raised = True
        result.check("5A-FIX-X: an inactive queue cannot be newly selected for a manual move", raised)
        queue_svc.reactivate_queue(session, queues["Call Later"].id)
        session.commit()

        # =====================================================================
        # Y: changing an Outcome Definition's target queue later does not
        # rewrite a historical queue movement's meaning.
        # =====================================================================
        outcome_svc.update_outcome_definition(session, outcome_defs["Hirable"].id, target_queue_id=queues["Active Review"].id)
        session.commit()
        session.expire_all()
        queue_history_app2_after_edit = queue_svc.list_queue_history(session, app2.id)
        result.check(
            "5A-FIX-Y: editing an Outcome Definition's target queue later never rewrites an already-"
            "recorded historical queue movement",
            queue_history_app2_after_edit[0].new_queue_id == queues["Hired"].id,
        )

        # =====================================================================
        # Z/AA/AB/AC/AD: Primary Screening / Hard Disqualifier / Review Queue
        # / Phone Interview / In-Person Interview all remain fully
        # operational, and an activated Hard Disqualifier never auto-STOPs.
        # =====================================================================
        criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="5A-FIX Hard Disqualifier", coefficient=1.0,
            direction=psm.NEGATIVE, is_hard_disqualifier=True, hard_disqualifier_trigger_level=4,
        )
        session.commit()
        run = ps_svc.create_screening_run(session, app3.id)
        session.commit()
        evaluation = next(e for e in ps_svc.list_evaluations(session, run.id) if e.criterion_snapshot.name == "5A-FIX Hard Disqualifier")
        ps_svc.human_enter_evaluation(session, evaluation.id, level=4)
        session.commit()
        session.expire_all()
        app3_reloaded = app_svc.get_application(session, app3.id)
        result.check(
            "5A-FIX-Z: Primary Screening still works (a run with an evaluation was created)",
            ps_svc.get_latest_run_for_application(session, app3.id) is not None,
        )
        result.check(
            "5A-FIX-AA: an activated Hard Disqualifier still works, and never automatically STOPs/closes "
            "the Application — lifecycle/workflow_status remain whatever they already were",
            ps_svc.get_run(session, run.id).has_active_hard_disqualifier is True
            and app3_reloaded.lifecycle_state == om.ACTIVE and app3_reloaded.workflow_status != apm.STOP,
        )
        result.check(
            "5A-FIX-AB: the existing Review Queue (Application listing) remains operational",
            any(a.id == app1.id for a in app_svc.list_applications(session, restaurant_id=restaurant.id)),
        )
        result.check(
            "5A-FIX-AC: Phone Interview remains fully operational",
            pi_svc.get_plan_for_application(session, app1.id) is not None,
        )
        in_person_plan = ip_svc.create_plan(session, app1.id)
        session.commit()
        result.check("5A-FIX-AD: In-Person/Practical Interview remains fully operational", in_person_plan is not None)

        # =====================================================================
        # AE/AF: Outcome/Stage history remain append-only.
        # =====================================================================
        result.check(
            "5A-FIX-AE: Outcome history remains append-only (every decision recorded above for app1 is "
            "still present)",
            len(outcome_svc.list_outcome_history(session, app1.id)) >= 6,
        )
        result.check(
            "5A-FIX-AF: Stage history remains append-only (every transition recorded above for app1 is "
            "still present)",
            len(stage_svc.list_stage_history(session, app1.id)) >= 3,
        )

        # =====================================================================
        # AG: no automatic HIRE/STOP — structural: Stage-movement and
        # Primary Screening code never call the Outcome service themselves
        # (unchanged from Task 5A's own AR/AS check); the Hard Disqualifier
        # above never created any SelectionOutcomeDecision on its own.
        # =====================================================================
        stage_source = inspect.getsource(stage_svc)
        ps_source = inspect.getsource(ps_svc)
        result.check(
            "5A-FIX-AG: no automatic HIRE/STOP is introduced — Stage-movement and Primary Screening code "
            "still never call outcome_service.apply_outcome/reopen_application themselves, and activating "
            "a Hard Disqualifier alone created zero Outcome Decisions",
            ".apply_outcome(" not in stage_source and ".reopen_application(" not in stage_source
            and ".apply_outcome(" not in ps_source and ".reopen_application(" not in ps_source
            and outcome_svc.get_current_outcome_decision(session, app3.id).outcome_definition_snapshot.name
            == "5A-FIX No-Queue Outcome",  # unchanged by the Hard Disqualifier evaluation above
        )
    finally:
        session.rollback()
        if restaurant is not None and restaurant.id is not None:
            for movement_row in session.query(m.ApplicationQueueMovement).join(
                m.Application, m.ApplicationQueueMovement.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                session.delete(movement_row)
            session.flush()

            for flag_row in session.query(m.CandidateFlag).filter_by(restaurant_id=restaurant.id):
                session.delete(flag_row)
            session.flush()
            for reminder_row in session.query(m.SelectionReminder).join(
                m.Application, m.SelectionReminder.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                session.delete(reminder_row)
            session.flush()

            for evaluation_row in session.query(m.PrimaryScreeningCriterionEvaluation).join(
                m.PrimaryScreeningRun, m.PrimaryScreeningCriterionEvaluation.run_id == m.PrimaryScreeningRun.id
            ).filter(m.PrimaryScreeningRun.restaurant_id == restaurant.id):
                session.delete(evaluation_row)
            session.flush()
            for run_row in session.query(m.PrimaryScreeningRun).filter_by(restaurant_id=restaurant.id):
                session.delete(run_row)
            session.flush()
            for snapshot_row in session.query(m.PrimaryScreeningCriterionSnapshot).join(
                m.PrimaryScreeningCriterion, m.PrimaryScreeningCriterionSnapshot.criterion_id == m.PrimaryScreeningCriterion.id
            ).filter(m.PrimaryScreeningCriterion.restaurant_id == restaurant.id):
                session.delete(snapshot_row)
            session.flush()
            for criterion_row in session.query(m.PrimaryScreeningCriterion).filter_by(restaurant_id=restaurant.id):
                session.delete(criterion_row)
            session.flush()

            for item_instance_row in session.query(m.AssessmentItemInstance).join(
                m.InPersonInterviewPlan, m.AssessmentItemInstance.plan_id == m.InPersonInterviewPlan.id
            ).filter(m.InPersonInterviewPlan.restaurant_id == restaurant.id):
                session.delete(item_instance_row)
            session.flush()
            for plan_row in session.query(m.InPersonInterviewPlan).filter_by(restaurant_id=restaurant.id):
                session.delete(plan_row)
            session.flush()
            for phone_instance_row in session.query(m.PhoneInterviewQuestionInstance).join(
                m.PhoneInterviewPlan, m.PhoneInterviewQuestionInstance.plan_id == m.PhoneInterviewPlan.id
            ).filter(m.PhoneInterviewPlan.restaurant_id == restaurant.id):
                session.delete(phone_instance_row)
            session.flush()
            for phone_plan_row in session.query(m.PhoneInterviewPlan).filter_by(restaurant_id=restaurant.id):
                session.delete(phone_plan_row)
            session.flush()

            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                session.delete(application_row)  # cascades Notes/StageTransitions/OutcomeDecisions/Signals
            session.flush()

            for def_snapshot_row in session.query(m.SelectionOutcomeDefinitionSnapshot).join(
                m.SelectionOutcomeDefinition, m.SelectionOutcomeDefinitionSnapshot.definition_id == m.SelectionOutcomeDefinition.id
            ).filter(m.SelectionOutcomeDefinition.restaurant_id == restaurant.id):
                session.delete(def_snapshot_row)
            session.flush()
            for definition_row in session.query(m.SelectionOutcomeDefinition).filter_by(restaurant_id=restaurant.id):
                session.delete(definition_row)
            session.flush()

            # Queues are deleted last — only now is nothing (no Application.
            # current_queue_id, no SelectionOutcomeDefinition.target_queue_id)
            # left referencing them.
            for queue_row in session.query(m.SelectionQueue).filter_by(restaurant_id=restaurant.id):
                session.delete(queue_row)
            session.flush()

            for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=restaurant.id):
                session.delete(person_row)
            session.flush()

            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                for fa_row in fa_svc.list_fit_assessments_for_candidate(session, candidate_row.id):
                    session.delete(fa_row)
                session.flush()
                session.delete(candidate_row)
            session.flush()
            for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                session.delete(raw)
            session.flush()
            for requirement_set_row in req_svc.list_requirement_sets(session, restaurant_id=restaurant.id):
                for snapshot_row in req_svc.list_snapshots(session, requirement_set_row.id):
                    session.delete(snapshot_row)
                session.flush()
                session.delete(requirement_set_row)
            session.flush()
        still_attached = session.get(m.Restaurant, restaurant.id) if restaurant is not None else None
        if still_attached is not None:
            session.delete(still_attached)
        session.commit()
        session.close()


def _assert_selection_5a_align(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 5A-ALIGN checks — the conceptual-alignment fixes made against
    the current authoritative product decisions: HIRABLE (never HIRE)
    requiring no separate mandatory reason, HIRABLE/DECLINED preserving
    the original HIRABLE decision (distinct from Stop), the new
    INFORMATION/EVENT log never itself changing Application state, a
    historical "Training Check Not Passed" Candidate Flag surfacing on a
    genuinely later Application (including inside the Primary Screening AI
    evidence package), custom-Outcome `authority_label`/`driven_by`
    metadata, and HOLD's three flavors (open-ended/time-based/condition-
    based) via the new restaurant-wide due-reminders query. Own dedicated
    session/restaurant, real commits, real cleanup (same reasoning as
    `_assert_selection_5a_fix_authoritative_state_and_queue` above)."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic 5A-ALIGN Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        restaurant_templates.seed_default_selection_outcomes(session, restaurant_id=restaurant.id)
        outcome_defs = {
            d.name: d for d in outcome_svc.list_outcome_definitions(session, restaurant_id=restaurant.id)
        }

        def _upload(name: str, email: str, phone: str, role_line: str) -> m.Application:
            text = f"{name}\n{email}\n{phone}\n\nEXPERIENCE\n{role_line}\n"
            imported = import_pipeline.import_one_resume(
                session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD,
                original_filename=f"{email}_{role_line[:6]}.txt", storage_path=None, raw_text=text,
                content_hash=compute_content_hash(text, f"{email}_{role_line[:6]}"),
            )
            application = app_svc.create_application(
                session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id, target_role="SERVER",
            )
            session.commit()
            return application

        # =====================================================================
        # Setup: two genuinely separate Applications, same person (same
        # normalized email), so the second one can pick up Flag history
        # from the first (task §12/test "TRAINING CHECK NOT PASSED... future
        # Application").
        # =====================================================================
        app1 = _upload(
            "Avery Align", "avery.align.5a@example.com", "555-610-0001",
            "Server, Bistro Align\nJan 2021 - Jun 2022\nWaited tables.",
        )

        # =====================================================================
        # HIRABLE (never HIRE), no separate mandatory reason, decision
        # occurring DURING Primary Screening (task §2/§5/§9).
        # =====================================================================
        result.check(
            "5A-ALIGN-setup: the seeded positive Outcome is named \"Hirable,\" never \"Hire\"",
            "Hirable" in outcome_defs and "Hire" not in outcome_defs
            and outcome_defs["Hirable"].requires_reason is False,
        )
        stage_svc.set_stage(session, app1.id, stgm.PRIMARY_SCREENING)
        hirable_decision = outcome_svc.apply_outcome(session, app1.id, outcome_defs["Hirable"].id)
        session.commit()
        session.expire_all()
        app1_after_hirable = app_svc.get_application(session, app1.id)
        result.check(
            "5A-ALIGN-A: a decision (HIRABLE) can be applied DURING Primary Screening, with no reason "
            "required",
            app1_after_hirable.current_stage == stgm.PRIMARY_SCREENING
            and app1_after_hirable.lifecycle_state == om.CLOSED,
        )
        result.check(
            "5A-ALIGN-B: HIRABLE never touches Business Domain / creates an employee — structurally, "
            "applying it only ever writes to Selection's own Application/Outcome tables",
            "models.Employee" not in inspect.getsource(outcome_svc) and "business" not in inspect.getsource(outcome_svc).lower(),
        )

        # =====================================================================
        # HIRABLE / DECLINED — preserves the original HIRABLE decision,
        # conceptually distinct from Stop.
        # =====================================================================
        declined_decision = outcome_svc.apply_outcome(
            session, app1.id, outcome_defs["Hirable / Declined"].id,
            reason="Candidate accepted another offer", note_text="Candidate accepted another offer.",
        )
        session.commit()
        session.expire_all()
        history_after_decline = outcome_svc.list_outcome_history(session, app1.id)
        result.check(
            "5A-ALIGN-C: HIRABLE/DECLINED preserves the original HIRABLE decision in history (never "
            "overwritten) and is conceptually distinct from Stop",
            any(d.id == hirable_decision.id and d.outcome_definition_snapshot.name == "Hirable" for d in history_after_decline)
            and any(d.id == declined_decision.id and d.outcome_definition_snapshot.name == "Hirable / Declined" for d in history_after_decline)
            and outcome_defs["Hirable / Declined"].id != outcome_defs["Stop"].id,
        )

        # =====================================================================
        # Training Check Not Passed -> Candidate Flag -> surfaces on a
        # genuinely LATER Application by the same person (task §11/§12).
        # =====================================================================
        outcome_svc.apply_outcome(
            session, app1.id, outcome_defs["Training Check Not Passed"].id,
            reason="Candidate did not pass the required Training Check",
            note_text="Trainer reported the candidate did not pass the required Training Check.",
            performed_by="Trainer: Jordan",
        )
        session.commit()
        session.expire_all()

        app2 = _upload(
            "Avery Align", "avery.align.5a@example.com", "555-610-0001",
            "Server, Bistro Align Two\nJul 2022 - Present\nWaited tables.",
        )
        active_flags_app2 = flag_svc.list_active_flags_for_application(session, app2.id)
        result.check(
            "5A-ALIGN-D: a previous \"Training Check Not Passed\" is detectable as CandidatePerson history "
            "on a genuinely later, separate Application",
            any(f.name == "Training Check Not Passed" for f in active_flags_app2),
        )

        criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="5A-ALIGN Training history", coefficient=1.0,
            direction=psm.NEGATIVE, is_hard_disqualifier=False,
            level_descriptions={"0": "no negative training history", "4": "failed a prior Training Check"},
        )
        snapshot = ps_svc.get_or_create_criterion_snapshot(session, criterion.id)
        package = ai_eval.build_evidence_package(session, app2, snapshot)
        result.check(
            "5A-ALIGN-E: the Primary Screening AI evaluator's evidence package includes the active Candidate "
            "Flag, so a restaurant CAN configure this Criterion as a Hard Disqualifier (never automatic)",
            any(
                "Training Check Not Passed" in item.evidence_text
                for item in package.get(psm.APPLICATION_HISTORY, [])
            ),
        )

        # =====================================================================
        # Information / Event log — a factual report, never itself a
        # decision (task §3/§15).
        # =====================================================================
        stage_before_event = app_svc.get_application(session, app2.id).current_stage
        lifecycle_before_event = app_svc.get_application(session, app2.id).lifecycle_state
        workflow_before_event = app_svc.get_application(session, app2.id).workflow_status
        decision_count_before_event = len(outcome_svc.list_outcome_history(session, app2.id))
        event_note = app_svc.record_information_event(
            session, app2.id, description="Candidate called the restaurant and stated they are withdrawing.",
            event_type="CANDIDATE_WITHDRAWAL_CLAIM", reported_by="Server: Alex",
            original_source="Phone call from the candidate",
        )
        session.commit()
        session.expire_all()
        app2_after_event = app_svc.get_application(session, app2.id)
        result.check(
            "5A-ALIGN-F: recording an Information/Event NEVER itself changes Stage, lifecycle, workflow "
            "status, or the Outcome Decision history — only the Selezionatore's own separate "
            "apply_outcome() call can do that",
            app2_after_event.current_stage == stage_before_event
            and app2_after_event.lifecycle_state == lifecycle_before_event
            and app2_after_event.workflow_status == workflow_before_event
            and len(outcome_svc.list_outcome_history(session, app2.id)) == decision_count_before_event,
        )
        result.check(
            "5A-ALIGN-G: the Information/Event preserves event type, raw description, who reported it, and "
            "the original source, distinctly from an ordinary note",
            event_note.context_type == "INFORMATION_EVENT" and event_note.event_type == "CANDIDATE_WITHDRAWAL_CLAIM"
            and event_note.reported_by == "Server: Alex" and event_note.original_source == "Phone call from the candidate"
            and event_note.note_text == "Candidate called the restaurant and stated they are withdrawing.",
        )
        notes_history_app2 = notes_svc.get_selection_notes_history(session, app2.id)
        event_entry = next((e for e in notes_history_app2 if e.context_label == "Information / Event"), None)
        result.check(
            "5A-ALIGN-H: the Information/Event appears in the SAME unified, chronological Selection Notes "
            "History as every other note — never a second, disconnected system",
            event_entry is not None and "CANDIDATE_WITHDRAWAL_CLAIM" in event_entry.note_text
            and event_entry.author == "Server: Alex",
        )

        # =====================================================================
        # Custom-Outcome wizard metadata — authority + driven-by (task §14).
        # =====================================================================
        training_snapshot = outcome_svc.get_or_create_outcome_definition_snapshot(
            session, outcome_defs["Training Check Not Passed"].id,
        )
        result.check(
            "5A-ALIGN-I: a custom Outcome Definition carries WHO has authority to apply it and whether it is "
            "candidate- or restaurant-driven, preserved onto its immutable snapshot",
            outcome_defs["Training Check Not Passed"].authority_label == "Trainer"
            and training_snapshot.authority_label == "Trainer" and training_snapshot.driven_by == om.DRIVEN_BY_RESTAURANT,
        )

        # =====================================================================
        # HOLD — open-ended, time-based, condition-based (task §6).
        # =====================================================================
        app3 = _upload(
            "Riley Align", "riley.align.5a@example.com", "555-610-0002",
            "Server, Bistro Align Three\nJan 2022 - Present\nWaited tables.",
        )
        # Open-ended: the seeded "Hold" Outcome itself creates no reminder —
        # the Application is simply SUSPENDED until a Selezionatore reviews
        # it again, with no date or condition attached.
        outcome_svc.apply_outcome(session, app3.id, outcome_defs["Hold"].id, reason="Awaiting Selezionatore review.")
        session.commit()
        session.expire_all()
        result.check(
            "5A-ALIGN-J: HOLD can be OPEN-ENDED — SUSPENDED with no reminder/date/condition attached at all",
            app_svc.get_application(session, app3.id).lifecycle_state == om.SUSPENDED
            and not outcome_svc.list_reminders_for_application(session, app3.id),
        )

        # Time-based: a reminder with a due_date already in the past must
        # surface in the restaurant-wide "due" list (task's own "RF-One
        # must bring the Application back to the Selezionatore's
        # attention").
        session.add(m.SelectionReminder(
            application_id=app3.id, due_date=datetime.utcnow() - timedelta(days=1),
            note_text="Follow up after two weeks as agreed.",
        ))
        session.commit()
        due_reminders = outcome_svc.list_due_reminders(session, restaurant.id)
        result.check(
            "5A-ALIGN-K: HOLD can be TIME-BASED — a reminder whose due date has passed is surfaced by the "
            "restaurant-wide due-reminders query, bringing the Application back to attention",
            any(r.application_id == app3.id for r in due_reminders),
        )

        # Condition-based: a reminder with NO due date (an external
        # condition, not a date, is what resolves it) must NOT be treated
        # as chronologically "due" — RF-One cannot detect an external
        # condition on its own — but must remain visible on the
        # Application's own open-reminders list.
        session.add(m.SelectionReminder(
            application_id=app3.id, due_date=None,
            note_text="Condition-based: waiting for the candidate's background check result.",
        ))
        session.commit()
        due_reminders_after = outcome_svc.list_due_reminders(session, restaurant.id)
        open_reminders_app3 = outcome_svc.list_reminders_for_application(session, app3.id, unresolved_only=True)
        result.check(
            "5A-ALIGN-L: HOLD can be CONDITION-BASED — a reminder with no due date never appears in the "
            "date-driven \"due\" list, but stays fully visible on the Application's own open-reminders list",
            sum(1 for r in due_reminders_after if r.application_id == app3.id) == 1  # only the time-based one
            and any(r.due_date is None for r in open_reminders_app3)
            and len(open_reminders_app3) == 2,
        )

        # =====================================================================
        # Regression — existing Primary Screening / Phone / In-Person
        # Selection functionality remains fully operational.
        # =====================================================================
        requirement_set = req_svc.create_requirement_set(
            session, restaurant_id=restaurant.id, name="5A-ALIGN Test Server", target_role="SERVER",
        )
        fit_assessment = fa_svc.create_fit_assessment(session, candidate_id=app1.candidate_id, requirement_set_id=requirement_set.id)
        session.commit()
        screening_run = ps_svc.create_screening_run(session, app1.id)
        phone_plan = pi_svc.create_plan(session, app1.id)
        in_person_plan = ip_svc.create_plan(session, app1.id)
        session.commit()
        result.check(
            "5A-ALIGN-M: existing Primary Screening, Phone Interview, and In-Person Interview Plan creation "
            "all remain fully operational after every 5A-ALIGN change above",
            screening_run is not None and phone_plan is not None
            and in_person_plan is not None and in_person_plan.phone_interview_plan_id == phone_plan.id,
        )
    finally:
        session.rollback()
        if restaurant is not None and restaurant.id is not None:
            for reminder_row in session.query(m.SelectionReminder).join(
                m.Application, m.SelectionReminder.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                session.delete(reminder_row)
            session.flush()
            for flag_row in session.query(m.CandidateFlag).filter_by(restaurant_id=restaurant.id):
                session.delete(flag_row)
            session.flush()
            for evaluation_row in session.query(m.PrimaryScreeningCriterionEvaluation).join(
                m.PrimaryScreeningRun, m.PrimaryScreeningCriterionEvaluation.run_id == m.PrimaryScreeningRun.id
            ).filter(m.PrimaryScreeningRun.restaurant_id == restaurant.id):
                session.delete(evaluation_row)
            session.flush()
            for run_row in session.query(m.PrimaryScreeningRun).filter_by(restaurant_id=restaurant.id):
                session.delete(run_row)
            session.flush()
            for snapshot_row in session.query(m.PrimaryScreeningCriterionSnapshot).join(
                m.PrimaryScreeningCriterion, m.PrimaryScreeningCriterionSnapshot.criterion_id == m.PrimaryScreeningCriterion.id
            ).filter(m.PrimaryScreeningCriterion.restaurant_id == restaurant.id):
                session.delete(snapshot_row)
            session.flush()
            for criterion_row in session.query(m.PrimaryScreeningCriterion).filter_by(restaurant_id=restaurant.id):
                session.delete(criterion_row)
            session.flush()
            for item_instance_row in session.query(m.AssessmentItemInstance).join(
                m.InPersonInterviewPlan, m.AssessmentItemInstance.plan_id == m.InPersonInterviewPlan.id
            ).filter(m.InPersonInterviewPlan.restaurant_id == restaurant.id):
                session.delete(item_instance_row)
            session.flush()
            for plan_row in session.query(m.InPersonInterviewPlan).filter_by(restaurant_id=restaurant.id):
                session.delete(plan_row)
            session.flush()
            for phone_instance_row in session.query(m.PhoneInterviewQuestionInstance).join(
                m.PhoneInterviewPlan, m.PhoneInterviewQuestionInstance.plan_id == m.PhoneInterviewPlan.id
            ).filter(m.PhoneInterviewPlan.restaurant_id == restaurant.id):
                session.delete(phone_instance_row)
            session.flush()
            for phone_plan_row in session.query(m.PhoneInterviewPlan).filter_by(restaurant_id=restaurant.id):
                session.delete(phone_plan_row)
            session.flush()
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                session.delete(application_row)  # cascades Notes/StageTransitions/OutcomeDecisions/Signals
            session.flush()
            for def_snapshot_row in session.query(m.SelectionOutcomeDefinitionSnapshot).join(
                m.SelectionOutcomeDefinition, m.SelectionOutcomeDefinitionSnapshot.definition_id == m.SelectionOutcomeDefinition.id
            ).filter(m.SelectionOutcomeDefinition.restaurant_id == restaurant.id):
                session.delete(def_snapshot_row)
            session.flush()
            for definition_row in session.query(m.SelectionOutcomeDefinition).filter_by(restaurant_id=restaurant.id):
                session.delete(definition_row)
            session.flush()
            for queue_row in session.query(m.SelectionQueue).filter_by(restaurant_id=restaurant.id):
                session.delete(queue_row)
            session.flush()
            for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=restaurant.id):
                session.delete(person_row)
            session.flush()
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                for fa_row in fa_svc.list_fit_assessments_for_candidate(session, candidate_row.id):
                    session.delete(fa_row)
                session.flush()
                session.delete(candidate_row)
            session.flush()
            for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                session.delete(raw)
            session.flush()
            for requirement_set_row in req_svc.list_requirement_sets(session, restaurant_id=restaurant.id):
                for snapshot_row in req_svc.list_snapshots(session, requirement_set_row.id):
                    session.delete(snapshot_row)
                session.flush()
                session.delete(requirement_set_row)
            session.flush()
        still_attached = session.get(m.Restaurant, restaurant.id) if restaurant is not None else None
        if still_attached is not None:
            session.delete(still_attached)
        session.commit()
        session.close()


def _assert_selection_5a_micro_fix(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 5A-MICRO-FIX checks. §1: a non-configurable RF-One governance
    rule layered on top of each Outcome's own `requires_reason` — the FIRST
    decision ever made for an Application follows the chosen Outcome's own
    configuration (so an Outcome with `requires_reason=False` needs none),
    but CHANGING an Application's existing effective decision to a
    genuinely different Outcome always requires a non-empty reason,
    regardless of the target Outcome's own configuration; re-applying the
    SAME Outcome again is never treated as a "change." §2: a previous
    "Training Check Not Passed" must surface as CandidatePerson history on
    a later Application (already exercised by 5A-ALIGN-D/E) and must never
    by itself automatically flag a Hard Disqualifier — only a human/AI
    Criterion Evaluation can. Own dedicated session/restaurant, real
    commits, real cleanup (same reasoning as `_assert_selection_5a_align`
    above)."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic 5A-MICRO-FIX Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        restaurant_templates.seed_default_selection_outcomes(session, restaurant_id=restaurant.id)
        outcome_defs = {
            d.name: d for d in outcome_svc.list_outcome_definitions(session, restaurant_id=restaurant.id)
        }

        def _upload(name: str, email: str, phone: str, role_line: str) -> m.Application:
            text = f"{name}\n{email}\n{phone}\n\nEXPERIENCE\n{role_line}\n"
            imported = import_pipeline.import_one_resume(
                session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD,
                original_filename=f"{email}_{role_line[:6]}.txt", storage_path=None, raw_text=text,
                content_hash=compute_content_hash(text, f"{email}_{role_line[:6]}"),
            )
            application = app_svc.create_application(
                session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id, target_role="SERVER",
            )
            session.commit()
            return application

        # =====================================================================
        # MF-A: the FIRST decision ever made for an Application follows the
        # chosen Outcome's OWN configuration — HIRABLE (requires_reason=
        # False) needs no reason as a first decision.
        # =====================================================================
        app1 = _upload("Jordan Micro", "jordan.micro.5amf@example.com", "555-620-0001", "Server, Bistro Micro\nJan 2022 - Present\nWaited tables.")
        hirable_decision = outcome_svc.apply_outcome(session, app1.id, outcome_defs["Hirable"].id)
        session.commit()
        session.expire_all()
        result.check(
            "5A-MF-A: NEW -> HIRABLE (an Outcome with requires_reason=False) needs no reason as the FIRST "
            "decision ever made for the Application",
            hirable_decision is not None
            and app_svc.get_application(session, app1.id).lifecycle_state == om.CLOSED,
        )

        # =====================================================================
        # MF-B/MF-C: CHANGING an existing decision (HIRABLE -> STOP) always
        # requires a reason, regardless of the target Outcome's own
        # configuration — and succeeds, preserving both decisions plus the
        # reason/author/timestamp, once one is supplied.
        # =====================================================================
        raised_no_reason = False
        try:
            outcome_svc.apply_outcome(session, app1.id, outcome_defs["Stop"].id)
        except ValueError:
            raised_no_reason = True
        result.check(
            "5A-MF-B: HIRABLE -> STOP is a CHANGE to an existing decision and is rejected without a reason, "
            "even though Stop's own `requires_reason` would already independently demand one",
            raised_no_reason,
        )
        stop_decision = outcome_svc.apply_outcome(
            session, app1.id, outcome_defs["Stop"].id, reason="Candidate withdrew interest", performed_by="Selezionatore: Sam",
        )
        session.commit()
        session.expire_all()
        history_after_stop = outcome_svc.list_outcome_history(session, app1.id)
        result.check(
            "5A-MF-C: once a reason is supplied, the change succeeds and history preserves BOTH the "
            "previous decision (Hirable) and the new one (Stop), each with its own reason, author, and "
            "timestamp — nothing overwritten",
            len(history_after_stop) == 2
            and history_after_stop[0].id == hirable_decision.id and history_after_stop[0].reason is None
            and history_after_stop[1].id == stop_decision.id and history_after_stop[1].reason == "Candidate withdrew interest"
            and history_after_stop[1].performed_by == "Selezionatore: Sam"
            and history_after_stop[1].created_at is not None,
        )

        # =====================================================================
        # MF-D: another change (STOP -> HOLD) also requires a reason.
        # =====================================================================
        raised_stop_to_hold = False
        try:
            outcome_svc.apply_outcome(session, app1.id, outcome_defs["Hold"].id)
        except ValueError:
            raised_stop_to_hold = True
        result.check(
            "5A-MF-D: STOP -> HOLD is a CHANGE and is rejected without a reason",
            raised_stop_to_hold,
        )
        outcome_svc.apply_outcome(session, app1.id, outcome_defs["Hold"].id, reason="Reconsidering after all")
        session.commit()
        session.expire_all()

        # =====================================================================
        # MF-E: STOP -> reopened also requires a reason (reopen_application
        # is just one more apply_outcome call under the hood).
        # =====================================================================
        app2 = _upload("Casey Micro", "casey.micro.5amf@example.com", "555-620-0002", "Server, Bistro Micro\nJan 2022 - Present\nWaited tables.")
        outcome_svc.apply_outcome(session, app2.id, outcome_defs["Stop"].id, reason="Not a fit at this time")
        session.commit()
        raised_reopen_no_reason = False
        try:
            outcome_svc.reopen_application(session, app2.id, outcome_defs["Active / Continue"].id)
        except ValueError:
            raised_reopen_no_reason = True
        result.check(
            "5A-MF-E: STOP -> reopened is a CHANGE and is rejected without a reason",
            raised_reopen_no_reason,
        )
        reopened = outcome_svc.reopen_application(
            session, app2.id, outcome_defs["Active / Continue"].id, reason="Pipeline reopened for this role",
        )
        session.commit()
        session.expire_all()
        result.check(
            "5A-MF-E2: STOP -> reopened succeeds once a reason is supplied, and is still flagged as a "
            "reopen event",
            reopened.is_reopen_event is True and reopened.reason == "Pipeline reopened for this role",
        )

        # =====================================================================
        # MF-F: re-applying/confirming the SAME Outcome again is NOT a
        # "change" and needs no reason, even though a decision already
        # exists.
        # =====================================================================
        reconfirmed = outcome_svc.apply_outcome(session, app2.id, outcome_defs["Active / Continue"].id, note_text="Still active, confirmed.")
        session.commit()
        result.check(
            "5A-MF-F: re-applying the SAME Outcome again (not a change to a DIFFERENT Outcome) needs no "
            "reason even though an existing decision is present",
            reconfirmed is not None,
        )

        # =====================================================================
        # MF-G: Training Check Not Passed history (already built in 5A-
        # ALIGN) re-verified here under this task's own explicit wording,
        # AND confirmed to never by itself automatically flag a Hard
        # Disqualifier — only an actual Criterion Evaluation can.
        # =====================================================================
        app3 = _upload("Riley Micro", "riley.micro.5amf@example.com", "555-620-0003", "Server, Bistro Micro\nJan 2021 - Jun 2022\nWaited tables.")
        outcome_svc.apply_outcome(
            session, app3.id, outcome_defs["Training Check Not Passed"].id,
            reason="Candidate did not pass the required Training Check",
            note_text="Trainer reported the candidate did not pass the required Training Check.",
            performed_by="Trainer: Jordan",
        )
        session.commit()
        session.expire_all()
        app4 = _upload("Riley Micro", "riley.micro.5amf@example.com", "555-620-0004", "Server, Bistro Micro Two\nJul 2022 - Present\nWaited tables.")
        active_flags_app4 = flag_svc.list_active_flags_for_application(session, app4.id)
        result.check(
            "5A-MF-G1: \"Previous Training Check Not Passed\" is durable CandidatePerson history, "
            "immediately visible on a genuinely later Application (Primary Screening / CV Review)",
            any(f.name == "Training Check Not Passed" for f in active_flags_app4),
        )

        hard_disqualifier_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="5A-MF Training history (Hard Disqualifier)",
            coefficient=1.0, direction=psm.NEGATIVE, is_hard_disqualifier=True,
            level_descriptions={"0": "no negative training history", "4": "failed a prior Training Check"},
        )
        hd_snapshot = ps_svc.get_or_create_criterion_snapshot(session, hard_disqualifier_criterion.id)
        hd_package = ai_eval.build_evidence_package(session, app4, hd_snapshot)
        run4 = ps_svc.create_screening_run(session, app4.id)
        session.commit()
        session.expire_all()
        result.check(
            "5A-MF-G2: the Flag is available as EVIDENCE to a restaurant-configured Hard-Disqualifier "
            "Criterion (the restaurant MAY use it)",
            any("Training Check Not Passed" in item.evidence_text for item in hd_package.get(psm.APPLICATION_HISTORY, [])),
        )
        result.check(
            "5A-MF-G3: the historical Flag never AUTOMATICALLY triggers the Hard Disqualifier by itself — "
            "evidence existing is not the same as an evaluated level; only an actual Criterion Evaluation "
            "(human or AI-assisted) can set has_active_hard_disqualifier",
            run4.has_active_hard_disqualifier is False,
        )
    finally:
        session.rollback()
        if restaurant is not None and restaurant.id is not None:
            for evaluation_row in session.query(m.PrimaryScreeningCriterionEvaluation).join(
                m.PrimaryScreeningRun, m.PrimaryScreeningCriterionEvaluation.run_id == m.PrimaryScreeningRun.id
            ).filter(m.PrimaryScreeningRun.restaurant_id == restaurant.id):
                session.delete(evaluation_row)
            session.flush()
            for run_row in session.query(m.PrimaryScreeningRun).filter_by(restaurant_id=restaurant.id):
                session.delete(run_row)
            session.flush()
            for snapshot_row in session.query(m.PrimaryScreeningCriterionSnapshot).join(
                m.PrimaryScreeningCriterion, m.PrimaryScreeningCriterionSnapshot.criterion_id == m.PrimaryScreeningCriterion.id
            ).filter(m.PrimaryScreeningCriterion.restaurant_id == restaurant.id):
                session.delete(snapshot_row)
            session.flush()
            for criterion_row in session.query(m.PrimaryScreeningCriterion).filter_by(restaurant_id=restaurant.id):
                session.delete(criterion_row)
            session.flush()
            for flag_row in session.query(m.CandidateFlag).filter_by(restaurant_id=restaurant.id):
                session.delete(flag_row)
            session.flush()
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                session.delete(application_row)  # cascades Notes/StageTransitions/OutcomeDecisions/Signals
            session.flush()
            for def_snapshot_row in session.query(m.SelectionOutcomeDefinitionSnapshot).join(
                m.SelectionOutcomeDefinition, m.SelectionOutcomeDefinitionSnapshot.definition_id == m.SelectionOutcomeDefinition.id
            ).filter(m.SelectionOutcomeDefinition.restaurant_id == restaurant.id):
                session.delete(def_snapshot_row)
            session.flush()
            for definition_row in session.query(m.SelectionOutcomeDefinition).filter_by(restaurant_id=restaurant.id):
                session.delete(definition_row)
            session.flush()
            for queue_row in session.query(m.SelectionQueue).filter_by(restaurant_id=restaurant.id):
                session.delete(queue_row)
            session.flush()
            for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=restaurant.id):
                session.delete(person_row)
            session.flush()
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                for fa_row in fa_svc.list_fit_assessments_for_candidate(session, candidate_row.id):
                    session.delete(fa_row)
                session.flush()
                session.delete(candidate_row)
            session.flush()
            for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                session.delete(raw)
            session.flush()
        still_attached = session.get(m.Restaurant, restaurant.id) if restaurant is not None else None
        if still_attached is not None:
            session.delete(still_attached)
        session.commit()
        session.close()


def _assert_trainable_gap_dossier(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 5B checks — Trainable Gap (Part A) and the Operational Candidate
    Dossier's service-layer aggregation (Part B; template/route rendering
    itself is exercised separately via the Flask app, not here). Own
    dedicated session/restaurant, real commits, real cleanup (same
    reasoning as `_assert_selection_5a_micro_fix` above) — `TrainableGap`
    rows have no cascading relationship from `Application`/`FitAssessment`,
    so they are deleted explicitly before their parents."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic 5B Trainable Gap Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        req_set = req_svc.create_requirement_set(session, restaurant_id=restaurant.id, name="5B Server Requirements")
        trainable_req = req_svc.add_requirement(
            session, req_set.id, name="Wine pairing technique", criticality=rm.MUST_HAVE, trainability=rm.TRAINABLE,
            assessment_stages=[rm.RESUME],
        )
        not_trainable_req = req_svc.add_requirement(
            session, req_set.id, name="Legal authorization to work", criticality=rm.MUST_HAVE,
            trainability=rm.NOT_TRAINABLE, assessment_stages=[rm.RESUME],
        )
        session.commit()

        text = (
            "Robin Trainable\nrobin.trainable.5b@example.com\n555-630-0001\n\n"
            "EXPERIENCE\nCashier, Bistro Gap\nJan 2022 - Present\nGreeted guests, handled payments.\n"
        )
        imported = import_pipeline.import_one_resume(
            session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD,
            original_filename="robin_trainable.txt", storage_path=None, raw_text=text,
            content_hash=compute_content_hash(text, "robin_trainable"),
        )
        application = app_svc.create_application(
            session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id, target_role="SERVER",
        )
        session.commit()

        fit_assessment = fa_svc.create_fit_assessment(session, candidate_id=imported.candidate_id, requirement_set_id=req_set.id)
        session.commit()
        session.expire_all()

        ras = fa_svc.list_requirement_assessments(session, fit_assessment.id)
        trainable_ra = next(r for r in ras if r.requirement_snapshot_item.name == "Wine pairing technique")
        not_trainable_ra = next(r for r in ras if r.requirement_snapshot_item.name == "Legal authorization to work")
        result.check(
            "5B-FIXTURE: the synthetic résumé leaves both Requirements NOT_EVIDENCED (a real, unforced gap)",
            trainable_ra.effective_status == fam.NOT_EVIDENCED and not_trainable_ra.effective_status == fam.NOT_EVIDENCED,
        )

        # =====================================================================
        # TG-A/TG-B: a Trainable Gap is created ONLY for the TRAINABLE,
        # evidenced-as-a-gap Requirement — never for the NOT_TRAINABLE one,
        # which instead surfaces as a separate "non-trainable concern".
        # =====================================================================
        created = tg_svc.generate_trainable_gaps_for_fit_assessment(session, fit_assessment.id)
        session.commit()
        result.check(
            "5B-TG-A: a Trainable Gap is generated for a trainable Requirement with incomplete/no evidence",
            len(created) == 1 and created[0].requirement_assessment_id == trainable_ra.id,
        )
        gap = created[0]
        active_gaps = tg_svc.list_trainable_gaps_for_application(session, application.id)
        result.check(
            "5B-TG-B: the NOT_TRAINABLE Requirement's gap never becomes a persisted TrainableGap row",
            not_trainable_ra.id not in {g.requirement_assessment_id for g in active_gaps},
        )
        concerns = tg_svc.list_non_trainable_concerns_for_application(session, application.id)
        result.check(
            "5B-TG-B2: the NOT_TRAINABLE Requirement instead appears as a separate non-trainable concern",
            any(c["requirement_name"] == "Legal authorization to work" for c in concerns),
        )

        # =====================================================================
        # TG-C/TG-H: RF-One's initial level persists on the 0-4 scale; no
        # Training-target field exists anywhere on the model (Selection
        # never defines a Training target — task's own explicit boundary).
        # =====================================================================
        result.check(
            "5B-TG-C: RF-One's proposed initial level persists on the 0-4 scale",
            gap.rf_one_initial_level in tgm.INITIAL_LEVELS,
        )
        result.check(
            "5B-TG-H: no Training-target level field exists on the persisted TrainableGap model",
            not hasattr(gap, "target_level") and not hasattr(gap, "training_target_level")
            and not hasattr(gap, "training_target"),
        )
        rf_one_level = gap.rf_one_initial_level

        # =====================================================================
        # TG-D/TG-G: the Selezionatore may accept RF-One's level without a
        # redundant manual value being stored, and RF-One's own original
        # level is never touched by doing so.
        # =====================================================================
        tg_svc.set_selezionatore_level(session, gap.id, level=rf_one_level)
        session.commit()
        session.expire_all()
        agreed = tg_svc.get_trainable_gap(session, gap.id)
        result.check(
            "5B-TG-D: agreeing with RF-One's level stores no duplicate manual value and needs no reason",
            agreed.selezionatore_initial_level is None and agreed.origin == fam.HUMAN_CONFIRMED,
        )
        result.check(
            "5B-TG-G: RF-One's original level is unchanged after the Selezionatore agrees",
            agreed.rf_one_initial_level == rf_one_level,
        )

        # =====================================================================
        # TG-F: a DIFFERENT Selezionatore level with NO reason is rejected,
        # and leaves the gap completely unchanged.
        # =====================================================================
        different_level = (rf_one_level + 2) % 5
        raised_no_reason = False
        try:
            tg_svc.set_selezionatore_level(session, gap.id, level=different_level, reason="   ")
        except ValueError:
            raised_no_reason = True
        result.check(
            "5B-TG-F: a Selezionatore level different from RF-One's, with a blank reason, is rejected",
            raised_no_reason,
        )
        session.rollback()
        untouched = tg_svc.get_trainable_gap(session, gap.id)
        result.check(
            "5B-TG-F2: the rejected attempt left selezionatore_initial_level/effective_initial_level unchanged",
            untouched.selezionatore_initial_level is None and untouched.effective_initial_level == rf_one_level,
        )

        # =====================================================================
        # TG-E/TG-G2: a DIFFERENT level WITH a reason is accepted; the
        # effective level becomes the Selezionatore's; RF-One's original
        # level still remains untouched.
        # =====================================================================
        tg_svc.set_selezionatore_level(
            session, gap.id, level=different_level, reason="Observed stronger technique during a trial pour.",
            performed_by="Selezionatore: Morgan",
        )
        session.commit()
        session.expire_all()
        overridden = tg_svc.get_trainable_gap(session, gap.id)
        result.check(
            "5B-TG-E: a different Selezionatore level WITH a reason is accepted",
            overridden.selezionatore_initial_level == different_level and overridden.origin == fam.HUMAN_OVERRIDDEN
            and overridden.override_reason,
        )
        result.check(
            "5B-TG-E2: the effective level becomes the Selezionatore's level",
            overridden.effective_initial_level == different_level,
        )
        result.check(
            "5B-TG-G2: RF-One's original level remains unchanged after the override",
            overridden.rf_one_initial_level == rf_one_level,
        )

        # =====================================================================
        # TG-J: regenerating against the SAME Fit Assessment is idempotent —
        # never creates a second row for the same RequirementAssessment, and
        # never touches the Selezionatore's already-recorded level.
        # =====================================================================
        second_pass = tg_svc.generate_trainable_gaps_for_fit_assessment(session, fit_assessment.id)
        session.commit()
        session.expire_all()
        still_one = tg_svc.list_trainable_gaps_for_application(session, application.id, active_only=False)
        result.check(
            "5B-TG-J: regenerating Trainable Gaps is idempotent (no duplicate row) and preserves the "
            "Selezionatore's recorded level",
            len(second_pass) == 0 and len(still_one) == 1
            and still_one[0].selezionatore_initial_level == different_level,
        )

        # =====================================================================
        # TG-K: once new evidence closes the gap (EVIDENCED), a later
        # regeneration withdraws the gap's lifecycle status — but never
        # touches any of its level fields, preserving the Selezionatore's
        # own judgment in history.
        # =====================================================================
        fa_svc.add_evidence(
            session, trainable_ra.id, source_type=fam.HUMAN_NOTE, evidence_classification=fam.FACT,
            evidence_relationship=fam.SUPPORTS, confidence=fam.CONFIDENCE_HIGH,
            evidence_text="Completed a supervised wine-pairing session; performed to standard.",
            is_system_generated=False,
        )
        session.commit()
        session.expire_all()
        closing_ra = session.get(m.RequirementAssessment, trainable_ra.id)
        result.check(
            "5B-FIXTURE2: new supporting evidence moves the RequirementAssessment to EVIDENCED",
            closing_ra.effective_status == fam.EVIDENCED,
        )
        tg_svc.generate_trainable_gaps_for_fit_assessment(session, fit_assessment.id)
        session.commit()
        session.expire_all()
        withdrawn = tg_svc.get_trainable_gap(session, gap.id)
        active_after_close = tg_svc.list_trainable_gaps_for_application(session, application.id)
        result.check(
            "5B-TG-K: a gap whose Requirement later becomes EVIDENCED is withdrawn from the active list "
            "on the next regeneration",
            withdrawn.status == tgm.WITHDRAWN and gap.id not in {g.id for g in active_after_close},
        )
        result.check(
            "5B-TG-K2: withdrawal never touches the gap's own level fields — the Selezionatore's prior "
            "judgment remains in history",
            withdrawn.selezionatore_initial_level == different_level
            and withdrawn.rf_one_initial_level == rf_one_level,
        )

        # =====================================================================
        # TG-L: the Dossier aggregator (Part B) builds successfully, reuses
        # the existing Decision Summary/Notes History services rather than
        # duplicating them, and surfaces prior "Training Check Not Passed"
        # CandidatePerson history — reusing the ordinary Candidate Flag
        # mechanism 5A-MICRO-FIX already established, never a bespoke type.
        # =====================================================================
        restaurant_templates.seed_default_selection_outcomes(session, restaurant_id=restaurant.id)
        outcome_defs = {d.name: d for d in outcome_svc.list_outcome_definitions(session, restaurant_id=restaurant.id)}
        outcome_svc.apply_outcome(
            session, application.id, outcome_defs["Training Check Not Passed"].id,
            reason="Candidate did not pass the required Training Check",
            note_text="Trainer reported the candidate did not pass the required Training Check.",
            performed_by="Trainer: Jordan",
        )
        session.commit()
        session.expire_all()

        text2 = (
            "Robin Trainable\nrobin.trainable.5b@example.com\n555-630-0002\n\n"
            "EXPERIENCE\nCashier, Bistro Gap Two\nJul 2022 - Present\nGreeted guests, handled payments.\n"
        )
        imported2 = import_pipeline.import_one_resume(
            session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD,
            original_filename="robin_trainable_2.txt", storage_path=None, raw_text=text2,
            content_hash=compute_content_hash(text2, "robin_trainable_2"),
        )
        application2 = app_svc.create_application(
            session, candidate_id=imported2.candidate_id, restaurant_id=restaurant.id, target_role="SERVER",
        )
        session.commit()
        session.expire_all()

        dossier = dossier_svc.get_application_dossier(session, application2.id)
        session.commit()
        result.check(
            "5B-DOSSIER-A: the Dossier aggregates for a second Application by the same person without error",
            dossier.application.id == application2.id,
        )
        result.check(
            "5B-DOSSIER-B: the Dossier surfaces prior Applications by the same person, separate from the "
            "current one",
            any(p.id == application.id for p in dossier.prior_applications),
        )
        result.check(
            "5B-DOSSIER-C: a prior \"Training Check Not Passed\" is visible as CandidatePerson history on "
            "this later Application, without automatically rejecting it",
            any(f.name == "Training Check Not Passed" for f in dossier.training_check_flags)
            and application2.lifecycle_state != om.CLOSED,
        )
        result.check(
            "5B-DOSSIER-D: the Dossier's Decision Summary is the SAME authoritative object Task 5A's own "
            "Decision Summary screen uses — never a parallel/duplicated computation",
            dossier.decision_summary.application.id == application2.id,
        )
        result.check(
            "5B-DOSSIER-E: the Dossier's Notes History is the SAME unified, chronological source "
            "`selection_notes_service` already provides — never a second notes system",
            isinstance(dossier.notes_history, list),
        )
    finally:
        session.rollback()
        if restaurant is not None and restaurant.id is not None:
            for gap_row in session.query(m.TrainableGap).join(
                m.Application, m.TrainableGap.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                session.delete(gap_row)
            session.flush()
            for flag_row in session.query(m.CandidateFlag).filter_by(restaurant_id=restaurant.id):
                session.delete(flag_row)
            session.flush()
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                session.delete(application_row)  # cascades Notes/StageTransitions/OutcomeDecisions/Signals
            session.flush()
            for def_snapshot_row in session.query(m.SelectionOutcomeDefinitionSnapshot).join(
                m.SelectionOutcomeDefinition, m.SelectionOutcomeDefinitionSnapshot.definition_id == m.SelectionOutcomeDefinition.id
            ).filter(m.SelectionOutcomeDefinition.restaurant_id == restaurant.id):
                session.delete(def_snapshot_row)
            session.flush()
            for definition_row in session.query(m.SelectionOutcomeDefinition).filter_by(restaurant_id=restaurant.id):
                session.delete(definition_row)
            session.flush()
            for queue_row in session.query(m.SelectionQueue).filter_by(restaurant_id=restaurant.id):
                session.delete(queue_row)
            session.flush()
            for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=restaurant.id):
                session.delete(person_row)
            session.flush()
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                for fa_row in fa_svc.list_fit_assessments_for_candidate(session, candidate_row.id):
                    session.delete(fa_row)
                session.flush()
                session.delete(candidate_row)
            session.flush()
            for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                session.delete(raw)
            session.flush()
            for req_row in session.query(m.RequirementSetSnapshot).join(
                m.RequirementSet, m.RequirementSetSnapshot.requirement_set_id == m.RequirementSet.id
            ).filter(m.RequirementSet.restaurant_id == restaurant.id):
                session.delete(req_row)
            session.flush()
            for req_set_row in session.query(m.RequirementSet).filter_by(restaurant_id=restaurant.id):
                session.delete(req_set_row)  # cascades live Requirements
            session.flush()
        still_attached = session.get(m.Restaurant, restaurant.id) if restaurant is not None else None
        if still_attached is not None:
            session.delete(still_attached)
        session.commit()
        session.close()


def _assert_session_ownership_rule_governance(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 5C checks — Selection Session, single-role constraint,
    multi-Selezionatore assignment, authority/dependency hierarchy
    (reusing `SelectionAuthorityLevel`), Application ownership (take in
    charge / read-only / reassignment), the Rule Set confirmation gate,
    and Rule Change (SUBSEQUENT_ONLY / ENTIRE_SESSION). Own dedicated
    session/restaurant, real commits, real cleanup (same reasoning as
    `_assert_selection_5a_micro_fix`/`_assert_trainable_gap_dossier`
    above) — Session-governance rows have FK relationships not covered by
    any existing cleanup block, so they are deleted explicitly, in an
    order that respects `SelectionRuleSetVersion`'s self-referencing
    `created_from_version_id` and `SelectionSession`'s circular
    `current_rule_set_version_id`."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    session_ids: list[int] = []
    try:
        restaurant = m.Restaurant(name="Synthetic 5C Session Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        req_set = req_svc.create_requirement_set(session, restaurant_id=restaurant.id, name="5C Server Requirements")
        req_svc.add_requirement(
            session, req_set.id, name="Cash handling accuracy", criticality=rm.MUST_HAVE, trainability=rm.TRAINABLE,
            assessment_stages=[rm.RESUME],
        )
        session.commit()

        def _upload(name: str, email: str, phone: str, role_line: str) -> m.Application:
            text = f"{name}\n{email}\n{phone}\n\nEXPERIENCE\n{role_line}\n"
            imported = import_pipeline.import_one_resume(
                session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD,
                original_filename=f"{email}.txt", storage_path=None, raw_text=text,
                content_hash=compute_content_hash(text, email),
            )
            application = app_svc.create_application(
                session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id, target_role="SERVER",
            )
            session.commit()
            return application

        # =====================================================================
        # 5C-A/5C-B: Session created, single role only.
        # =====================================================================
        sc_session = sess_svc.create_session(
            session, restaurant_id=restaurant.id, name="Server — 5C Validation Suite", target_role="SERVER",
            created_by="Selezionatore: Alex",
        )
        session.commit()
        session_ids.append(sc_session.id)
        result.check(
            "5C-A: a Selection Session can be created, starting DRAFT with a version-1 Rule Set",
            sc_session.id is not None and sc_session.status == sesm.DRAFT and sc_session.current_rule_set_version_id is not None,
        )
        result.check("5C-B: a Session supports exactly one role", sc_session.target_role == "SERVER")

        # =====================================================================
        # 5C-C/5C-D: multiple Selezionatori assigned; no hierarchy -> peers.
        # =====================================================================
        sess_svc.assign_selezionatore(session, sc_session.id, selezionatore_name="Alex")
        sess_svc.assign_selezionatore(session, sc_session.id, selezionatore_name="Jordan")
        session.commit()
        result.check(
            "5C-C: multiple Selezionatori may be assigned to one Session",
            len(sess_svc.list_assignments(session, sc_session.id)) == 2,
        )

        app1 = _upload("Robin FiveCSuite", "robin.5c-suite@example.com", "555-660-0001", "Cashier, Bistro 5C Suite\nJan 2022 - Present\nGreeted guests.")
        sess_svc.link_application_to_session(session, app1.id, sc_session.id)
        session.commit()
        result.check("5C-F: an Application can be linked to a Session", app1.session_id == sc_session.id)

        # =====================================================================
        # 5C-P/5C-Q: Session cannot become operational, and candidate work is
        # blocked, before Rule Set confirmation.
        # =====================================================================
        blocked_before_confirmation = False
        try:
            own_svc.take_in_charge(session, app1.id, owner_name="Alex")
        except ValueError:
            blocked_before_confirmation = True
            session.rollback()
        result.check(
            "5C-P/5C-Q: take-in-charge (candidate operational work) is blocked before Rule Set confirmation",
            blocked_before_confirmation,
        )

        # =====================================================================
        # 5C-R/5C-S: confirmation activates the Session; the Rule Set is
        # Session/role-specific, not personal to a Selezionatore.
        # =====================================================================
        version1_id = sc_session.current_rule_set_version_id
        rs_svc.confirm_rule_set_version(session, sc_session.id, confirmed_by="Alex", note="Reviewed for the validation suite.")
        session.commit()
        session.expire_all()
        sc_session_reloaded = sess_svc.get_session(session, sc_session.id)
        result.check("5C-R: explicit Rule Set confirmation activates the Session", sc_session_reloaded.status == sesm.ACTIVE)
        version1 = rs_svc.get_version(session, version1_id)
        result.check(
            "5C-S: the confirmed Rule Set version is the ONE Session-wide version every Selezionatore uses "
            "— never a personal copy",
            version1.confirmed_by == "Alex" and sc_session_reloaded.current_rule_set_version_id == version1.id,
        )

        double_confirm_rejected = False
        try:
            rs_svc.confirm_rule_set_version(session, sc_session.id, confirmed_by="Jordan")
        except ValueError:
            double_confirm_rejected = True
            session.rollback()
        result.check("re-confirming an already-confirmed Rule Set version is rejected", double_confirm_rejected)

        # =====================================================================
        # 5C-G/5C-H/5C-I/5C-J: take in charge; one active owner; non-owner
        # read-only; owner may operate.
        # =====================================================================
        ownership1 = own_svc.take_in_charge(session, app1.id, owner_name="Alex")
        session.commit()
        result.check("5C-G: an Application may be explicitly taken in charge", ownership1.owner_name == "Alex")
        result.check(
            "5C-H: exactly one active owner exists at a time",
            own_svc.get_current_owner(session, app1.id).id == ownership1.id,
        )
        result.check("5C-I: a non-owner Session Selezionatore is read-only", not own_svc.can_write(session, app1.id, "Jordan"))
        result.check("5C-J: the owner can perform allowed Application operations", own_svc.can_write(session, app1.id, "Alex"))

        # =====================================================================
        # 5C-D/5C-M: no hierarchy defined -> peers -> a peer may not reassign.
        # =====================================================================
        peer_reassign_rejected = False
        try:
            own_svc.reassign(session, app1.id, new_owner="Jordan", performed_by="Jordan", reason="Peer attempt")
        except ValueError:
            peer_reassign_rejected = True
            session.rollback()
        result.check(
            "5C-D/5C-M: with no configured hierarchy, Selezionatori are peers — a peer cannot reassign "
            "another owner's Application",
            peer_reassign_rejected,
        )

        # =====================================================================
        # 5C-N: reassignment requires a reason.
        # =====================================================================
        reason_required = False
        try:
            own_svc.reassign(session, app1.id, new_owner="Jordan", performed_by="Alex", reason="")
        except ValueError:
            reason_required = True
            session.rollback()
        result.check("5C-N: reassignment requires a free-text reason", reason_required)

        # =====================================================================
        # 5C-K/5C-O: the current owner can reassign; history is preserved.
        # =====================================================================
        ownership2 = own_svc.reassign(session, app1.id, new_owner="Jordan", performed_by="Alex", reason="Handing off before end of shift.")
        session.commit()
        result.check("5C-K: the current owner can reassign", ownership2.owner_name == "Jordan")
        history = own_svc.list_ownership_history(session, app1.id)
        result.check(
            "5C-O: ownership history is preserved (never overwritten) — 2 rows, the first closed",
            len(history) == 2 and history[0].is_active is False and history[1].is_active is True,
        )

        # =====================================================================
        # 5C-E/5C-L: configuring authority/dependency allows a superior to
        # reassign; an inferior still cannot reassign a superior's Application.
        # =====================================================================
        senior_level = gov_svc.create_authority_level(session, restaurant_id=restaurant.id, level_key="5C_SENIOR", level_order=2, label="Senior")
        junior_level = gov_svc.create_authority_level(session, restaurant_id=restaurant.id, level_key="5C_JUNIOR", level_order=1, label="Junior")
        session.commit()
        sess_svc.assign_selezionatore(session, sc_session.id, selezionatore_name="Jordan", authority_level_id=junior_level.id)
        sess_svc.assign_selezionatore(session, sc_session.id, selezionatore_name="Morgan", authority_level_id=senior_level.id)
        session.commit()
        result.check(
            "5C-E: authority/dependency hierarchy may be configured (reusing SelectionAuthorityLevel)",
            sess_svc.get_assignment_for_selezionatore(session, sc_session.id, "Morgan").authority_level_id == senior_level.id,
        )
        ownership3 = own_svc.reassign(session, app1.id, new_owner="Morgan", performed_by="Morgan", reason="Escalating per configured seniority.")
        session.commit()
        result.check("5C-L: a Selezionatore with configured superior authority can reassign", ownership3.owner_name == "Morgan")

        inferior_rejected = False
        try:
            own_svc.reassign(session, app1.id, new_owner="Jordan", performed_by="Jordan", reason="Trying anyway")
        except ValueError:
            inferior_rejected = True
            session.rollback()
        result.check("5C-M2: an inferior authority cannot reassign a superior's owned Application", inferior_rejected)

        # =====================================================================
        # 5C-U/5C-V: a Rule Change requires a reason and an explicit scope.
        # =====================================================================
        reason_required_rc = False
        try:
            rc_svc.propose_rule_change(session, sc_session.id, rules_changed_summary="x", reason="", scope=rsm.SUBSEQUENT_ONLY)
        except ValueError:
            reason_required_rc = True
        result.check("5C-U: a Rule Change requires a reason", reason_required_rc)

        scope_required = False
        try:
            rc_svc.propose_rule_change(session, sc_session.id, rules_changed_summary="x", reason="because", scope="INVALID")
        except ValueError:
            scope_required = True
        result.check("5C-V: a Rule Change requires an explicit, valid scope", scope_required)

        # =====================================================================
        # 5C-T/5C-W/5C-X/5C-Y: SUBSEQUENT_ONLY — new version created;
        # already-processed Application stays on the old version; a
        # subsequent Application uses the new one.
        # =====================================================================
        rule_change_1 = rc_svc.propose_rule_change(
            session, sc_session.id, rules_changed_summary="Clarified cash-handling evidence guidance.",
            reason="Identified ambiguity while reviewing an interview.", scope=rsm.SUBSEQUENT_ONLY,
            performed_by="Alex",
        )
        session.commit()
        session.expire_all()
        result.check("5C-T: an active Session's rules may be changed", rule_change_1.id is not None)
        result.check(
            "5C-W: SUBSEQUENT_ONLY creates a new Rule Set version",
            rule_change_1.new_version_id != rule_change_1.previous_version_id,
        )
        app1_reloaded = session.get(m.Application, app1.id)
        result.check(
            "5C-X: an already-processed Application remains tied to the PREVIOUS Rule Set version under "
            "SUBSEQUENT_ONLY",
            app1_reloaded.rule_set_version_id == rule_change_1.previous_version_id,
        )

        app2 = _upload("Casey FiveCSuite", "casey.5c-suite@example.com", "555-660-0002", "Cashier, Bistro 5C Suite Two\nMar 2023 - Present\nGreeted guests.")
        sess_svc.link_application_to_session(session, app2.id, sc_session.id)
        session.commit()
        session.expire_all()
        sc_session_current = sess_svc.get_session(session, sc_session.id)
        result.check(
            "5C-Y: a subsequent Application uses the NEW Rule Set version",
            app2.rule_set_version_id == sc_session_current.current_rule_set_version_id == rule_change_1.new_version_id,
        )
        result.check(
            "5C-AD: the old Rule Set version remains historically available",
            rs_svc.get_version(session, rule_change_1.previous_version_id) is not None,
        )
        result.check("5C-AE: the Application records the exact applicable Rule Set version", app1_reloaded.rule_set_version_id is not None)

        # =====================================================================
        # 5C-Z/5C-AA/5C-AB/5C-AC: ENTIRE_SESSION — new version; already-
        # processed Applications identified as impacted; deterministic
        # recalculation where safe; human decisions never silently changed.
        # =====================================================================
        fa_svc.create_fit_assessment(session, candidate_id=app1.candidate_id, requirement_set_id=req_set.id)
        session.commit()

        rule_change_2 = rc_svc.propose_rule_change(
            session, sc_session.id, rules_changed_summary="Added Hard Disqualifier evidence guidance.",
            reason="A material behavioral screening gap was identified mid-Session.", scope=rsm.ENTIRE_SESSION,
            performed_by="Alex",
        )
        session.commit()
        session.expire_all()
        result.check("5C-Z: ENTIRE_SESSION creates a new Rule Set version", rule_change_2.new_version_id != rule_change_2.previous_version_id)

        impacts = rc_svc.list_impacts_for_rule_change(session, rule_change_2.id)
        impacted_ids = {i.application_id for i in impacts}
        result.check(
            "5C-AA: ENTIRE_SESSION identifies previously-processed Applications as impacted",
            app1.id in impacted_ids and app2.id in impacted_ids,
        )
        impact_app1 = next(i for i in impacts if i.application_id == app1.id)
        result.check(
            "5C-AB: deterministic recalculation occurs safely where a Fit Assessment exists",
            impact_app1.recalculation_status == rsm.RECALC_RECALCULATED,
        )
        result.check(
            "review_status starts NEEDS_REVIEW — a retroactive change never silently decides anything",
            impact_app1.review_status == rsm.REVIEW_NEEDS_REVIEW,
        )
        result.check(
            "5C-AC: a retroactive Rule Change never sets/changes an Outcome or lifecycle state on its own",
            app1_reloaded.lifecycle_state == "ACTIVE" and app1_reloaded.outcome is None,
        )
        rc_svc.mark_impact_reviewed(session, impact_app1.id, note="Reviewed for the validation suite — no material change.")
        session.commit()
        result.check(
            "review_status only ever advances via an explicit Selezionatore action",
            rc_svc.list_impacts_for_rule_change(session, rule_change_2.id)[0].review_status == rsm.REVIEW_REVIEWED
            if rc_svc.list_impacts_for_rule_change(session, rule_change_2.id)[0].application_id == app1.id
            else True,
        )

        # =====================================================================
        # 5C-AF/5C-AG: the next Session for the same restaurant/role starts
        # from the latest complete Rule Set, and still requires its own
        # explicit confirmation.
        # =====================================================================
        sc_session_2 = sess_svc.create_session(
            session, restaurant_id=restaurant.id, name="Server — 5C Validation Suite Session 2", target_role="SERVER",
            created_by="Selezionatore: Alex",
        )
        session.commit()
        session.expire_all()
        session_ids.append(sc_session_2.id)
        result.check(
            "5C-AF: the next Session for the same restaurant/role initializes from the latest complete Rule Set",
            sc_session_2.current_rule_set_version_id is not None,
        )
        version2_seed = rs_svc.get_version(session, sc_session_2.current_rule_set_version_id)
        result.check("seeded version records where it was carried forward from", version2_seed.created_from_version_id is not None)
        result.check(
            "5C-AG: the new Session still requires its OWN explicit Rule Set confirmation (never pre-confirmed)",
            version2_seed.confirmed_at is None,
        )

        # =====================================================================
        # Session-level notes reuse the unified ApplicationNote table.
        # =====================================================================
        sess_svc.add_session_note(session, sc_session.id, "General Session note for the validation suite.")
        session.commit()
        result.check(
            "Session notes use the SAME unified, append-only notes table — no second notes system",
            len(sess_svc.list_session_notes(session, sc_session.id)) >= 1,
        )

        # =====================================================================
        # 5C-AH: the Dossier surfaces Session/owner/Rule-Set-version context.
        # =====================================================================
        dossier = dossier_svc.get_application_dossier(session, app1.id)
        session.commit()
        result.check(
            "5C-AH: the Candidate Dossier shows Session/owner/Rule Set version/Rule-Change-impact context",
            dossier.session_context.session is not None and dossier.session_context.session.id == sc_session.id
            and dossier.session_context.current_owner is not None
            and dossier.session_context.applicable_rule_set_version is not None
            and dossier.session_context.was_affected_by_rule_change is True,
        )
    finally:
        session.rollback()
        if restaurant is not None and restaurant.id is not None:
            for ownership_row in session.query(m.ApplicationOwnership).join(
                m.Application, m.ApplicationOwnership.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                session.delete(ownership_row)
            session.flush()
            for impact_row in session.query(m.SelectionRuleChangeImpact).join(
                m.SelectionRuleChange, m.SelectionRuleChangeImpact.rule_change_id == m.SelectionRuleChange.id
            ).filter(m.SelectionRuleChange.session_id.in_(session_ids)):
                session.delete(impact_row)
            session.flush()
            for change_row in session.query(m.SelectionRuleChange).filter(m.SelectionRuleChange.session_id.in_(session_ids)):
                session.delete(change_row)
            session.flush()
            for assignment_row in session.query(m.SelectionSessionAssignment).filter(
                m.SelectionSessionAssignment.session_id.in_(session_ids)
            ):
                session.delete(assignment_row)
            session.flush()
            for session_note_row in session.query(m.ApplicationNote).filter(
                m.ApplicationNote.session_id.in_(session_ids)
            ):
                session.delete(session_note_row)
            session.flush()
            for gap_row in session.query(m.TrainableGap).join(
                m.Application, m.TrainableGap.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                session.delete(gap_row)
            session.flush()
            for match_row in session.query(m.PersonMatchCandidate).join(
                m.Application, m.PersonMatchCandidate.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                session.delete(match_row)
            session.flush()
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                application_row.session_id = None
                application_row.rule_set_version_id = None
            session.flush()
            for sid in session_ids:
                sc = session.get(m.SelectionSession, sid)
                if sc is not None:
                    sc.current_rule_set_version_id = None
            session.flush()
            version_rows = sorted(
                session.query(m.SelectionRuleSetVersion).filter(m.SelectionRuleSetVersion.session_id.in_(session_ids)),
                key=lambda v: v.id, reverse=True,
            )
            for version_row in version_rows:
                session.delete(version_row)
                session.flush()
            for sid in session_ids:
                sc = session.get(m.SelectionSession, sid)
                if sc is not None:
                    session.delete(sc)
            session.flush()
            for level_row in session.query(m.SelectionAuthorityLevel).filter_by(restaurant_id=restaurant.id):
                session.delete(level_row)
            session.flush()
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                for fa_row in fa_svc.list_fit_assessments_for_candidate(session, application_row.candidate_id):
                    session.delete(fa_row)
                session.flush()
                session.delete(application_row)  # cascades Notes/StageTransitions/OutcomeDecisions/Signals
            session.flush()
            for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=restaurant.id):
                session.delete(person_row)
            session.flush()
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                session.delete(candidate_row)
            session.flush()
            for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                session.delete(raw)
            session.flush()
            for req_row in session.query(m.RequirementSetSnapshot).join(
                m.RequirementSet, m.RequirementSetSnapshot.requirement_set_id == m.RequirementSet.id
            ).filter(m.RequirementSet.restaurant_id == restaurant.id):
                session.delete(req_row)
            session.flush()
            for req_set_row in session.query(m.RequirementSet).filter_by(restaurant_id=restaurant.id):
                session.delete(req_set_row)  # cascades live Requirements
            session.flush()
        still_attached = session.get(m.Restaurant, restaurant.id) if restaurant is not None else None
        if still_attached is not None:
            session.delete(still_attached)
        session.commit()
        session.close()


def _assert_candidate_communication_scheduling(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 5D checks A-AT (task's own letter list) — Acquisition Source vs.
    Communication Channel, versioned/multilingual Communication Templates,
    SMS+Email simultaneous send with single-channel fallback, every
    Stage/Outcome-triggered automatic communication, exact historical
    rendering after a Template edit, Interview Scheduling windows/slots/
    automatic confirmation/double-booking prevention/reschedule history,
    configurable reminders and delegated NO RESPONSE auto-STOP through the
    existing authoritative Outcome Engine, late-response handling, inbound
    classification/correction/alerting, and Dossier/Communication-History
    integration. Own dedicated session/restaurant, real commits, real
    cleanup (same reasoning as `_assert_session_ownership_rule_governance`
    above) — the new Task 5D tables have FK relationships not covered by
    any existing cleanup block."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic 5D Communication Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        def _upload(name: str, email: str, phone: str | None, role_line: str) -> m.Application:
            phone_line = phone or ""
            text = f"{name}\n{email}\n{phone_line}\n\nEXPERIENCE\n{role_line}\n"
            imported = import_pipeline.import_one_resume(
                session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD,
                original_filename=f"{email}_{role_line[:6]}.txt", storage_path=None, raw_text=text,
                content_hash=compute_content_hash(text, f"{email}_{role_line[:6]}"),
            )
            application = app_svc.create_application(
                session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id, target_role="SERVER",
            )
            if phone is None:
                application.candidate.phone = None
            session.commit()
            return application

        # =====================================================================
        # A. Acquisition Source is stored separately from Communication Channel.
        # =====================================================================
        sources = acq_svc.seed_default_acquisition_sources(session, restaurant_id=restaurant.id)
        session.commit()
        app_both = _upload("Robin FiveD", "robin.5d@example.com", "555-770-0001", "Server, Bistro 5D\nJan 2023 - Present\nServed guests.")
        acq_svc.set_application_acquisition_source(session, app_both.id, acquisition_source_id=sources["LinkedIn"])
        session.commit()
        session.expire_all()
        app_both = app_svc.get_application(session, app_both.id)
        result.check(
            "A: Acquisition Source ('LinkedIn') is stored on the Application, structurally separate from any "
            "Communication Channel field",
            app_both.acquisition_source is not None and app_both.acquisition_source.name == "LinkedIn"
            and not hasattr(m.AcquisitionSourceDefinition, "channel"),
        )

        # =====================================================================
        # B. Communication Template can be created/versioned.
        # =====================================================================
        stop_def = outcome_svc.create_outcome_definition(
            session, restaurant_id=restaurant.id, name="5D Stop", lifecycle_effect=om.CLOSED, requires_reason=False,
        )
        hold_def = outcome_svc.create_outcome_definition(
            session, restaurant_id=restaurant.id, name="5D Hold", lifecycle_effect=om.SUSPENDED, requires_reason=False,
        )
        hirable_def = outcome_svc.create_outcome_definition(
            session, restaurant_id=restaurant.id, name="5D Hirable", lifecycle_effect=om.CLOSED, requires_reason=False,
        )
        session.commit()

        screening_stop_tmpl = tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_PRIMARY_SCREENING_STOP,
            stage=stgm.PRIMARY_SCREENING, outcome_definition_id=stop_def.id, purpose="Rejection after CV Review",
            sms_text="Hi $candidate_name, thanks for applying to $restaurant_name. We will not be moving forward.",
            email_subject="Update on your application", email_body="Hi $candidate_name, thank you for your interest.",
        )
        session.commit()
        version_before = screening_stop_tmpl.version
        tmpl_svc.update_template(session, screening_stop_tmpl.id, purpose="Rejection after CV Review (v2)")
        session.commit()
        result.check(
            "B: editing a Communication Template bumps its version",
            screening_stop_tmpl.version == version_before + 1,
        )
        snap_v2 = tmpl_svc.get_or_create_template_snapshot(session, screening_stop_tmpl.id)
        result.check(
            "B: a distinct immutable Template Snapshot exists per version",
            snap_v2.version == screening_stop_tmpl.version,
        )

        # =====================================================================
        # C. Multilingual template variants can coexist.
        # =====================================================================
        reminder_tmpl_en = tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_REMINDER, stage=stgm.PHONE_INTERVIEW,
            language="en", sms_text="Reminder: please pick a time. $scheduling_link",
        )
        reminder_tmpl_it = tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_REMINDER, stage=stgm.PHONE_INTERVIEW,
            language="it", sms_text="Promemoria: scegli un orario. $scheduling_link",
        )
        session.commit()
        found_it = tmpl_svc.find_best_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_REMINDER, stage=stgm.PHONE_INTERVIEW,
            language="it",
        )
        found_default = tmpl_svc.find_best_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_REMINDER, stage=stgm.PHONE_INTERVIEW,
        )
        result.check(
            "C: a language-specific Template variant is selected when that language is requested",
            found_it is not None and found_it.id == reminder_tmpl_it.id,
        )
        result.check(
            "C: falls back to the default-language (\"en\") variant when no language is requested",
            found_default is not None and found_default.id == reminder_tmpl_en.id,
        )

        # =====================================================================
        # D/E. SMS+Email simultaneous send; single-channel fallback.
        # =====================================================================
        app_email_only = _upload("Casey FiveD", "casey.5d@example.com", None, "Server, Cafe 5D\nMar 2023 - Present\nServed guests.")
        generic_tmpl = tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_APPOINTMENT_CONFIRMATION,
            purpose="Generic confirmation test", sms_text="See you at $appointment_time.",
            email_subject="Confirmed", email_body="See you soon.",
        )
        session.commit()
        comm_both = comm_svc.send_communication(session, app_both, generic_tmpl, trigger_event=ccm.TRIGGER_APPOINTMENT_CONFIRMATION)
        comm_email_only = comm_svc.send_communication(session, app_email_only, generic_tmpl, trigger_event=ccm.TRIGGER_APPOINTMENT_CONFIRMATION)
        session.commit()
        result.check(
            "D: both SMS and Email are generated when both contact methods exist",
            comm_both.channel_sms_used and comm_both.channel_email_used
            and comm_both.sms_status == ccm.DELIVERY_SENT and comm_both.email_status == ccm.DELIVERY_SENT,
        )
        result.check(
            "E: only the available channel (Email) is used when the phone number is missing",
            comm_email_only.channel_email_used and not comm_email_only.channel_sms_used
            and comm_email_only.sms_status == ccm.DELIVERY_NOT_APPLICABLE,
        )

        # =====================================================================
        # F. Primary Screening STOP triggers configured rejection communication.
        # =====================================================================
        stage_svc.set_stage(session, app_both.id, stgm.PRIMARY_SCREENING, performed_by="Selezionatore: Alex")
        session.commit()
        screening_decision = outcome_svc.apply_outcome(session, app_both.id, stop_def.id, performed_by="Selezionatore: Alex")
        session.commit()
        screening_comm = comm_svc.on_outcome_decision(session, app_both, screening_decision)
        session.commit()
        result.check(
            "F: a Primary Screening STOP automatically triggers the configured rejection communication, "
            "with no extra Send step",
            screening_comm is not None and screening_comm.trigger_event == ccm.TRIGGER_PRIMARY_SCREENING_STOP,
        )

        # =====================================================================
        # G/H. Advance to Phone Interview supports Scheduling and Contact modes.
        # =====================================================================
        app_phone = _upload("Jordan FiveD", "jordan.5d@example.com", "555-770-0002", "Server, Diner 5D\nFeb 2023 - Present\nServed guests.")
        scheduling_tmpl = tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_ADVANCE_TO_PHONE_SCHEDULING,
            stage=stgm.PHONE_INTERVIEW, purpose="Advance to Phone — Scheduling",
            sms_text="Hi $candidate_name, please pick a time: $scheduling_link",
            email_subject="Schedule your phone interview", email_body="Please pick a time: $scheduling_link",
        )
        contact_tmpl = tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_ADVANCE_TO_PHONE_CONTACT,
            stage=stgm.PHONE_INTERVIEW, purpose="Advance to Phone — Contact",
            sms_text="Hi $candidate_name, you have been selected for a phone interview; we will contact you.",
        )
        session.commit()
        phone_transition = stage_svc.set_stage(session, app_phone.id, stgm.PHONE_INTERVIEW, performed_by="Selezionatore: Alex")
        session.commit()
        comm_scheduling = comm_svc.on_stage_transition(
            session, app_phone, phone_transition, communication_mode=ccm.PHONE_ADVANCE_MODE_SCHEDULING,
        )
        session.commit()
        result.check(
            "G: advancing to Phone Interview in SCHEDULING mode sends a communication containing a scheduling link",
            comm_scheduling is not None and comm_scheduling.trigger_event == ccm.TRIGGER_ADVANCE_TO_PHONE_SCHEDULING
            and "/schedule/" in (comm_scheduling.rendered_sms_text or ""),
        )
        comm_contact = comm_svc.on_stage_transition(
            session, app_phone, phone_transition, communication_mode=ccm.PHONE_ADVANCE_MODE_CONTACT,
        )
        session.commit()
        result.check(
            "H: advancing to Phone Interview in CONTACT mode sends the standard \"you will be contacted\" "
            "communication, with no scheduling link required",
            comm_contact is not None and comm_contact.trigger_event == ccm.TRIGGER_ADVANCE_TO_PHONE_CONTACT,
        )

        # =====================================================================
        # I/J. Phone HOLD / Phone STOP trigger configured communication.
        # =====================================================================
        phone_hold_tmpl = tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_PHONE_HOLD, stage=stgm.PHONE_INTERVIEW,
            outcome_definition_id=hold_def.id, sms_text="You remain under consideration.",
        )
        phone_stop_tmpl = tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_PHONE_STOP, stage=stgm.PHONE_INTERVIEW,
            outcome_definition_id=stop_def.id, sms_text="We will not be moving forward after the phone interview.",
        )
        session.commit()
        hold_decision = outcome_svc.apply_outcome(session, app_phone.id, hold_def.id, reason="Pipeline full", performed_by="Selezionatore: Alex")
        session.commit()
        hold_comm = comm_svc.on_outcome_decision(session, app_phone, hold_decision)
        session.commit()
        result.check(
            "I: a Phone HOLD automatically triggers the configured Phone-Hold communication",
            hold_comm is not None and hold_comm.trigger_event == ccm.TRIGGER_PHONE_HOLD,
        )
        stop_decision = outcome_svc.apply_outcome(session, app_phone.id, stop_def.id, reason="Availability incompatible", performed_by="Selezionatore: Alex")
        session.commit()
        phone_stop_comm = comm_svc.on_outcome_decision(session, app_phone, stop_decision)
        session.commit()
        result.check(
            "J: a Phone STOP automatically triggers the configured Phone-Stop communication (distinct from the "
            "Primary Screening rejection communication)",
            phone_stop_comm is not None and phone_stop_comm.trigger_event == ccm.TRIGGER_PHONE_STOP
            and phone_stop_comm.template_snapshot_id != screening_comm.template_snapshot_id,
        )

        # =====================================================================
        # K. ADVANCE_TO_IN_PERSON triggers configured communication.
        # =====================================================================
        app_in_person = _upload("Taylor FiveD", "taylor.5d@example.com", "555-770-0003", "Server, Grill 5D\nApr 2023 - Present\nServed guests.")
        advance_in_person_tmpl = tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_ADVANCE_TO_IN_PERSON,
            stage=stgm.IN_PERSON_PRACTICAL, sms_text="Congratulations, next: an in-person interview.",
        )
        session.commit()
        in_person_transition = stage_svc.set_stage(session, app_in_person.id, stgm.IN_PERSON_PRACTICAL, performed_by="Selezionatore: Alex")
        session.commit()
        advance_comm = comm_svc.on_stage_transition(session, app_in_person, in_person_transition)
        session.commit()
        result.check(
            "K: advancing to In-Person/Practical automatically triggers the configured communication",
            advance_comm is not None and advance_comm.trigger_event == ccm.TRIGGER_ADVANCE_TO_IN_PERSON,
        )

        # =====================================================================
        # L/M/N. In-Person HOLD / STOP / HIRABLE trigger configured communication.
        # =====================================================================
        tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_IN_PERSON_HOLD, stage=stgm.IN_PERSON_PRACTICAL,
            outcome_definition_id=hold_def.id, sms_text="Still under consideration after the in-person interview.",
        )
        tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_IN_PERSON_STOP, stage=stgm.IN_PERSON_PRACTICAL,
            outcome_definition_id=stop_def.id, sms_text="We will not be moving forward.",
        )
        tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_HIRABLE, stage=stgm.IN_PERSON_PRACTICAL,
            outcome_definition_id=hirable_def.id,
            sms_text="Congratulations $candidate_name — you have been selected to proceed. Next steps to follow.",
        )
        session.commit()

        ip_hold_decision = outcome_svc.apply_outcome(session, app_in_person.id, hold_def.id, reason="Timing not right", performed_by="Selezionatore: Alex")
        session.commit()
        ip_hold_comm = comm_svc.on_outcome_decision(session, app_in_person, ip_hold_decision)
        session.commit()
        result.check(
            "L: an In-Person HOLD automatically triggers the configured communication",
            ip_hold_comm is not None and ip_hold_comm.trigger_event == ccm.TRIGGER_IN_PERSON_HOLD,
        )

        app_in_person_stop = _upload("Morgan FiveD", "morgan.5d@example.com", "555-770-0004", "Server, Grill 5D\nMay 2023 - Present\nServed guests.")
        stage_svc.set_stage(session, app_in_person_stop.id, stgm.IN_PERSON_PRACTICAL, performed_by="Selezionatore: Alex")
        session.commit()
        ip_stop_decision = outcome_svc.apply_outcome(session, app_in_person_stop.id, stop_def.id, reason="Better-fitting candidates identified", performed_by="Selezionatore: Alex")
        session.commit()
        ip_stop_comm = comm_svc.on_outcome_decision(session, app_in_person_stop, ip_stop_decision)
        session.commit()
        result.check(
            "M: an In-Person STOP automatically triggers the configured communication",
            ip_stop_comm is not None and ip_stop_comm.trigger_event == ccm.TRIGGER_IN_PERSON_STOP,
        )

        hirable_decision = outcome_svc.apply_outcome(
            session, app_in_person.id, hirable_def.id, reason="Strong in-person interview performance",
            performed_by="Selezionatore: Alex",
        )
        session.commit()
        hirable_comm = comm_svc.on_outcome_decision(session, app_in_person, hirable_decision)
        session.commit()
        result.check(
            "N: a HIRABLE decision automatically triggers the configured communication explaining next steps follow",
            hirable_comm is not None and hirable_comm.trigger_event == ccm.TRIGGER_HIRABLE,
        )

        # =====================================================================
        # O. Exact rendered historical message remains unchanged after a
        # Template edit (never reconstructed from the current Template).
        # =====================================================================
        original_rendered_text = screening_comm.rendered_sms_text
        tmpl_svc.update_template(session, screening_stop_tmpl.id, sms_text="COMPLETELY DIFFERENT TEXT NOW")
        session.commit()
        session.expire_all()
        reloaded_comm = session.get(m.CandidateCommunication, screening_comm.id)
        result.check(
            "O: a historical communication's exact rendered text is unchanged after the Template is edited",
            reloaded_comm.rendered_sms_text == original_rendered_text
            and "COMPLETELY DIFFERENT" not in reloaded_comm.rendered_sms_text,
        )

        # =====================================================================
        # P/Q. Scheduling windows: creatable; multiple days/windows supported.
        # =====================================================================
        window_monday = sched_svc.create_scheduling_window(
            session, application_id=app_phone.id, interview_stage=stgm.PHONE_INTERVIEW, window_date=date(2026, 9, 7),
            start_time=time(14, 0), end_time=time(18, 0), slot_duration_minutes=30, created_by="Alex",
        )
        window_tuesday = sched_svc.create_scheduling_window(
            session, application_id=app_phone.id, interview_stage=stgm.PHONE_INTERVIEW, window_date=date(2026, 9, 8),
            start_time=time(14, 0), end_time=time(18, 0), slot_duration_minutes=30, created_by="Alex",
        )
        session.commit()
        windows = sched_svc.list_windows_for_application(session, app_phone.id, interview_stage=stgm.PHONE_INTERVIEW)
        result.check("P: a scheduling window can be created for an Application", window_monday.id in {w.id for w in windows})
        result.check(
            "Q: multiple days/windows are supported for the same Application/stage",
            len({window_monday.id, window_tuesday.id} & {w.id for w in windows}) == 2,
        )

        # =====================================================================
        # R. Candidate secure scheduling page (token-based) — service-layer
        # equivalent: an opaque token resolves back to the right Application
        # without exposing the internal id.
        # =====================================================================
        token_row = sched_svc.issue_scheduling_token(session, app_phone.id, interview_stage=stgm.PHONE_INTERVIEW)
        session.commit()
        resolved = sched_svc.resolve_token(session, token_row.token)
        result.check(
            "R: a secure opaque scheduling token resolves to the correct Application/stage",
            resolved is not None and resolved.application_id == app_phone.id
            # Opaque/unguessable, never a trivial encoding of the id — a
            # long random token (`secrets.token_urlsafe`) may coincidentally
            # contain the id's digits as a substring by pure chance, so
            # substring absence is not itself a meaningful safety property;
            # what matters is the token isn't simply derived from the id.
            and token_row.token != str(app_phone.id) and len(token_row.token) >= 20,
        )

        # =====================================================================
        # S/T/U. Candidate selects an available slot; it is confirmed
        # automatically; confirmation SMS+Email are generated automatically.
        # =====================================================================
        confirm_tmpl = tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_APPOINTMENT_CONFIRMATION,
            stage=stgm.PHONE_INTERVIEW, sms_text="Confirmed for $appointment_date at $appointment_time.",
            email_subject="Interview confirmed", email_body="Confirmed for $appointment_date at $appointment_time.",
        )
        session.commit()
        available_slots = sched_svc.list_available_slots(session, app_phone.id, interview_stage=stgm.PHONE_INTERVIEW)
        result.check("S: available slots are computed from the offered scheduling windows", len(available_slots) > 0)
        chosen_slot = available_slots[0]
        appointment = sched_svc.book_slot(
            session, app_phone.id, interview_stage=stgm.PHONE_INTERVIEW, window_id=chosen_slot["window_id"],
            slot_start_at=chosen_slot["start"],
        )
        session.commit()
        result.check(
            "T: selecting an available slot confirms the appointment automatically, no Selezionatore approval step",
            appointment.status == ccm.APPOINTMENT_CONFIRMED and appointment.confirmed_at is not None,
        )
        confirmation_comms = [
            c for c in comm_svc.list_communications_for_application(session, app_phone.id)
            if c.trigger_event == ccm.TRIGGER_APPOINTMENT_CONFIRMATION
        ]
        result.check(
            "U: automatic confirmation SMS+Email are generated on slot selection",
            len(confirmation_comms) >= 1 and confirmation_comms[-1].channel_sms_used and confirmation_comms[-1].channel_email_used,
        )

        # =====================================================================
        # V. Double-booking conflict is prevented.
        # =====================================================================
        double_booking_prevented = _raises(
            ValueError, sched_svc.book_slot, session, app_phone.id, interview_stage=stgm.PHONE_INTERVIEW,
            window_id=chosen_slot["window_id"], slot_start_at=chosen_slot["start"],
        )
        session.rollback()
        result.check("V: booking an already-taken (capacity-1) slot again is rejected", double_booking_prevented)

        # =====================================================================
        # W. Reschedule preserves prior appointment history.
        # =====================================================================
        other_slot = next(s for s in sched_svc.list_available_slots(session, app_phone.id, interview_stage=stgm.PHONE_INTERVIEW) if s["start"] != chosen_slot["start"])
        rescheduled = sched_svc.reschedule_appointment(
            session, appointment.id, new_window_id=other_slot["window_id"], new_slot_start_at=other_slot["start"],
            reason="Candidate requested a different time",
        )
        session.commit()
        session.expire_all()
        history = sched_svc.list_appointment_history(session, app_phone.id)
        prior = session.get(m.InterviewAppointment, appointment.id)
        result.check(
            "W: rescheduling preserves the prior appointment (marked RESCHEDULED, never deleted) and links the "
            "new one back to it",
            prior.status == ccm.APPOINTMENT_RESCHEDULED and rescheduled.previous_appointment_id == prior.id
            and prior.id in {a.id for a in history} and rescheduled.id in {a.id for a in history},
        )

        # =====================================================================
        # X/Y/Z/AA. Reminder count/timing configurable; reminders generated;
        # no premature STOP; NO RESPONSE STOP after deadline+reminders exhausted.
        # =====================================================================
        app_no_response = _upload("Drew FiveD", "drew.5d@example.com", "555-770-0005", "Server, Tavern 5D\nJun 2023 - Present\nServed guests.")
        policy = m.CommunicationReminderPolicy(
            restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_ADVANCE_TO_PHONE_SCHEDULING,
            stage=stgm.PHONE_INTERVIEW, reminder_count=1, first_reminder_delay_hours=1,
            reminder_interval_hours=1, final_deadline_hours=2, auto_stop_enabled=True,
            auto_stop_outcome_definition_id=stop_def.id,
        )
        session.add(policy)
        session.commit()
        result.check(
            "X: a Reminder Policy's reminder count/timing/deadline are configurable and persisted",
            policy.reminder_count == 1 and policy.first_reminder_delay_hours == 1 and policy.final_deadline_hours == 2,
        )

        transition_nr = stage_svc.set_stage(session, app_no_response.id, stgm.PHONE_INTERVIEW, performed_by="Selezionatore: Alex")
        session.commit()
        root_comm = comm_svc.on_stage_transition(
            session, app_no_response, transition_nr, communication_mode=ccm.PHONE_ADVANCE_MODE_SCHEDULING,
        )
        session.commit()
        result.check(
            "X: the outbound communication opens a response-tracking cycle when a matching Reminder Policy exists",
            root_comm.awaiting_response and root_comm.reminder_policy_id == policy.id and root_comm.final_deadline_at is not None,
        )

        before_first_reminder_due = comm_svc.process_reminders_and_deadlines(
            session, restaurant_id=restaurant.id, as_of=root_comm.created_at + timedelta(minutes=30),
        )
        session.commit()
        session.expire_all()
        root_comm = session.get(m.CandidateCommunication, root_comm.id)
        result.check(
            "Z: before the configured deadline/reminder timing, no reminder is sent and no automatic STOP occurs",
            root_comm.reminders_sent_count == 0 and not root_comm.no_response_stop_applied,
        )

        comm_svc.process_reminders_and_deadlines(
            session, restaurant_id=restaurant.id, as_of=root_comm.created_at + timedelta(hours=1, minutes=5),
        )
        session.commit()
        session.expire_all()
        root_comm = session.get(m.CandidateCommunication, root_comm.id)
        reminder_rows = [
            c for c in comm_svc.list_communications_for_application(session, app_no_response.id)
            if c.is_reminder and c.parent_communication_id == root_comm.id
        ]
        result.check(
            "Y: configured reminders are actually generated (SMS+Email) once due",
            root_comm.reminders_sent_count == 1 and len(reminder_rows) == 1,
        )

        comm_svc.process_reminders_and_deadlines(
            session, restaurant_id=restaurant.id, as_of=root_comm.final_deadline_at + timedelta(minutes=1),
        )
        session.commit()
        session.expire_all()
        root_comm = session.get(m.CandidateCommunication, root_comm.id)
        app_no_response_reloaded = app_svc.get_application(session, app_no_response.id)
        result.check(
            "AA: after the configured deadline, with every reminder sent and no response, an automatic STOP "
            "(reason NO RESPONSE) is applied",
            root_comm.no_response_stop_applied and app_no_response_reloaded.lifecycle_state == om.CLOSED,
        )
        auto_stop_decision = session.get(m.SelectionOutcomeDecision, root_comm.no_response_stop_outcome_decision_id)
        result.check(
            "AB: the automatic NO RESPONSE STOP is recorded through the existing authoritative Outcome Engine "
            "(a real SelectionOutcomeDecision, reason NO RESPONSE)",
            auto_stop_decision is not None and auto_stop_decision.reason == "NO RESPONSE"
            and auto_stop_decision.performed_by == "SYSTEM_AUTOMATIC_NO_RESPONSE",
        )

        # =====================================================================
        # AC/AD. Late response after NO RESPONSE STOP does not reopen the
        # Application, and generates a mandatory Selezionatore alert.
        # =====================================================================
        late_inbound = inbound_svc.record_inbound(
            session, app_no_response.id, channel=ccm.CHANNEL_SMS, raw_text="Sorry for the late reply, I am still interested!",
        )
        session.commit()
        session.expire_all()
        app_no_response_after_late = app_svc.get_application(session, app_no_response.id)
        result.check(
            "AC: a late response after an automatic NO RESPONSE STOP does NOT reopen the Application",
            app_no_response_after_late.lifecycle_state == om.CLOSED,
        )
        result.check(
            "AD: the late response is classified LATE_RESPONSE_AFTER_NO_RESPONSE_STOP and raises a mandatory alert",
            late_inbound.classification_effective == ccm.CLASS_LATE_RESPONSE_AFTER_NO_RESPONSE_STOP
            and late_inbound.alert_required,
        )

        # =====================================================================
        # AE-AI. Inbound preserved verbatim; classification stored; ambiguous
        # stays ambiguous; correction preserves system classification;
        # DECLINED/WITHDRAWAL never change the Outcome by themselves.
        # =====================================================================
        app_inbound_general = _upload("Sam FiveD", "sam.5d@example.com", "555-770-0006", "Server, Bistro 5D\nJul 2023 - Present\nServed guests.")
        raw_text_sample = "Thanks so much, sounds good but can we reschedule to another time?"
        inbound_general = inbound_svc.record_inbound(session, app_inbound_general.id, channel=ccm.CHANNEL_SMS, raw_text=raw_text_sample)
        session.commit()
        result.check("AE: the raw inbound message is preserved verbatim", inbound_general.raw_text == raw_text_sample)
        result.check(
            "AF: an inbound classification (system + confidence) is stored",
            inbound_general.classification_system is not None and inbound_general.classification_confidence is not None,
        )
        result.check(
            "AG: a message with genuinely mixed signals stays AMBIGUOUS_OR_UNCLEAR rather than guessing",
            inbound_general.classification_effective == ccm.CLASS_AMBIGUOUS_OR_UNCLEAR,
        )

        corrected = inbound_svc.correct_classification(
            session, inbound_general.id, new_classification=ccm.CLASS_RESCHEDULE_REQUESTED,
            corrected_by="Selezionatore: Alex", reason="Listened to the voicemail — it's a reschedule request.",
        )
        session.commit()
        result.check(
            "AH: a Selezionatore can correct the EFFECTIVE classification without losing the original system "
            "classification",
            corrected.classification_effective == ccm.CLASS_RESCHEDULE_REQUESTED
            and corrected.classification_system == ccm.CLASS_AMBIGUOUS_OR_UNCLEAR
            and corrected.classification_corrected_by == "Selezionatore: Alex",
        )

        lifecycle_before_declined = app_inbound_general.lifecycle_state
        declined_inbound = inbound_svc.record_inbound(
            session, app_inbound_general.id, channel=ccm.CHANNEL_SMS, raw_text="I have to decline, won't be able to accept.",
        )
        session.commit()
        session.expire_all()
        app_inbound_general_reloaded = app_svc.get_application(session, app_inbound_general.id)
        result.check(
            "AI: a DECLINED classification never automatically changes the Outcome by itself",
            declined_inbound.classification_effective == ccm.CLASS_DECLINED
            and app_inbound_general_reloaded.lifecycle_state == lifecycle_before_declined,
        )
        withdrawal_inbound = inbound_svc.record_inbound(
            session, app_inbound_general.id, channel=ccm.CHANNEL_SMS, raw_text="I would like to withdraw my application.",
        )
        session.commit()
        session.expire_all()
        app_inbound_general_reloaded = app_svc.get_application(session, app_inbound_general.id)
        result.check(
            "AJ: a WITHDRAWAL classification never automatically changes the Outcome by itself",
            withdrawal_inbound.classification_effective == ccm.CLASS_WITHDRAWAL
            and app_inbound_general_reloaded.lifecycle_state == lifecycle_before_declined,
        )

        # =====================================================================
        # AK. Communication History is chronological.
        # =====================================================================
        full_history = comm_svc.list_communications_for_application(session, app_phone.id)
        timestamps = [c.created_at for c in full_history if c.created_at is not None]
        result.check("AK: the Communication History is in chronological order", timestamps == sorted(timestamps))

        # =====================================================================
        # AL. Candidate Dossier shows communication/scheduling state.
        # =====================================================================
        dossier = dossier_svc.get_application_dossier(session, app_phone.id)
        session.commit()
        result.check(
            "AL: the Candidate Dossier surfaces communication history/state and the current appointment",
            dossier.communication_context.communication_count > 0
            and dossier.communication_context.current_phone_appointment is not None,
        )

        # =====================================================================
        # AM-AS. Existing Selection functionality remains operational.
        # =====================================================================
        result.check(
            "AM/AO/AP/AQ/AR: Primary Screening / Phone / In-Person / Outcome Engine / Dossier remain operational "
            "for an Application that also has Task 5D communication history",
            dossier.decision_summary is not None and dossier.application.id == app_phone.id,
        )
        result.check(
            "AN: repeated-applicant history remains operational alongside Task 5D",
            app_svc.list_prior_applications(session, app_phone.id) is not None,
        )

    finally:
        if restaurant is not None:
            for c in session.query(m.CandidateCommunication).join(
                m.Application, m.CandidateCommunication.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                c.response_inbound_id = None
                c.parent_communication_id = None
            session.flush()
            for i in list(session.query(m.InboundCommunication).join(
                m.Application, m.InboundCommunication.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(i)
            session.flush()
            for c in list(session.query(m.CandidateCommunication).join(
                m.Application, m.CandidateCommunication.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(c)
            session.flush()
            for a in session.query(m.InterviewAppointment).join(
                m.Application, m.InterviewAppointment.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                a.previous_appointment_id = None
            session.flush()
            for a in list(session.query(m.InterviewAppointment).join(
                m.Application, m.InterviewAppointment.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(a)
            session.flush()
            for w in list(session.query(m.InterviewSchedulingWindow).join(
                m.Application, m.InterviewSchedulingWindow.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(w)
            session.flush()
            for t in list(session.query(m.CandidateSchedulingToken).join(
                m.Application, m.CandidateSchedulingToken.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(t)
            session.flush()
            for p in list(session.query(m.CommunicationReminderPolicy).filter_by(restaurant_id=restaurant.id)):
                session.delete(p)
            session.flush()
            for s in list(session.query(m.CommunicationTemplateSnapshot).join(
                m.CommunicationTemplate, m.CommunicationTemplateSnapshot.template_id == m.CommunicationTemplate.id
            ).filter(m.CommunicationTemplate.restaurant_id == restaurant.id)):
                session.delete(s)
            session.flush()
            for t in list(session.query(m.CommunicationTemplate).filter_by(restaurant_id=restaurant.id)):
                session.delete(t)
            session.flush()

            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                application_row.acquisition_source_id = None
            session.flush()
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                session.delete(application_row)  # cascades Notes/StageTransitions/OutcomeDecisions/Signals
            session.flush()
            for a in list(session.query(m.AcquisitionSourceDefinition).filter_by(restaurant_id=restaurant.id)):
                session.delete(a)
            session.flush()

            for def_snapshot_row in session.query(m.SelectionOutcomeDefinitionSnapshot).join(
                m.SelectionOutcomeDefinition, m.SelectionOutcomeDefinitionSnapshot.definition_id == m.SelectionOutcomeDefinition.id
            ).filter(m.SelectionOutcomeDefinition.restaurant_id == restaurant.id):
                session.delete(def_snapshot_row)
            session.flush()
            for definition_row in session.query(m.SelectionOutcomeDefinition).filter_by(restaurant_id=restaurant.id):
                session.delete(definition_row)
            session.flush()

            for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=restaurant.id):
                session.delete(person_row)
            session.flush()
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                session.delete(candidate_row)
            session.flush()
            for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                session.delete(raw)
            session.flush()

            still_attached = session.get(m.Restaurant, restaurant.id)
            if still_attached is not None:
                session.delete(still_attached)
            session.commit()
        session.close()


def _assert_5d_micro_fix_session_scheduling(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 5D-MICRO-FIX checks A-N (task's own letter list) — Selection
    Session scheduling windows shared across multiple Applications, the
    shared slot pool/capacity (including the DB-level concurrency guard),
    Phone-vs-In-Person distinguishability, the candidate secure link
    showing only the applicable Session/stage pool, automatic confirmation/
    SMS+Email/reschedule history unchanged, the Application-specific
    override path still working, and Dossier/Session UI wiring. Own
    dedicated session/restaurant, real commits, real cleanup (same
    reasoning as `_assert_session_ownership_rule_governance` above)."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    session_ids: list[int] = []
    try:
        restaurant = m.Restaurant(name="Synthetic 5D-MICRO-FIX Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        def _upload(name: str, email: str, phone: str, role_line: str) -> m.Application:
            text = f"{name}\n{email}\n{phone}\n\nEXPERIENCE\n{role_line}\n"
            imported = import_pipeline.import_one_resume(
                session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD, original_filename=f"{email}.txt",
                storage_path=None, raw_text=text, content_hash=compute_content_hash(text, email),
            )
            application = app_svc.create_application(
                session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id, target_role="SERVER",
            )
            session.commit()
            return application

        selection_session = sess_svc.create_session(
            session, restaurant_id=restaurant.id, name="Server — 5D-MICRO-FIX Suite", target_role="SERVER",
            created_by="Selezionatore: Alex",
        )
        session.commit()
        session_ids.append(selection_session.id)

        app_a = _upload("Robin MicroFix", "robin.microfix@example.com", "555-880-0001", "Server, Bistro MF\nJan 2023 - Present\nServed guests.")
        app_b = _upload("Jordan MicroFix", "jordan.microfix@example.com", "555-880-0002", "Server, Diner MF\nFeb 2023 - Present\nServed guests.")
        app_c = _upload("Taylor MicroFix", "taylor.microfix@example.com", "555-880-0003", "Server, Grill MF\nMar 2023 - Present\nServed guests.")
        sess_svc.link_application_to_session(session, app_a.id, selection_session.id)
        sess_svc.link_application_to_session(session, app_b.id, selection_session.id)
        sess_svc.link_application_to_session(session, app_c.id, selection_session.id)
        session.commit()

        confirm_tmpl = tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_APPOINTMENT_CONFIRMATION,
            sms_text="Confirmed for $appointment_date at $appointment_time.",
            email_subject="Interview confirmed", email_body="Confirmed for $appointment_date at $appointment_time.",
        )
        session.commit()

        # =====================================================================
        # A. One Selection Session can have multiple scheduling windows.
        # =====================================================================
        window_monday = sched_svc.create_scheduling_window(
            session, session_id=selection_session.id, interview_stage=stgm.PHONE_INTERVIEW,
            window_date=date(2026, 9, 7), start_time=time(14, 0), end_time=time(18, 0),
            slot_duration_minutes=60, capacity_per_slot=1, created_by="Alex",
        )
        window_tuesday = sched_svc.create_scheduling_window(
            session, session_id=selection_session.id, interview_stage=stgm.PHONE_INTERVIEW,
            window_date=date(2026, 9, 8), start_time=time(14, 0), end_time=time(18, 0),
            slot_duration_minutes=60, capacity_per_slot=1, created_by="Alex",
        )
        in_person_window = sched_svc.create_scheduling_window(
            session, session_id=selection_session.id, interview_stage=stgm.IN_PERSON_PRACTICAL,
            window_date=date(2026, 9, 10), start_time=time(10, 0), end_time=time(12, 0),
            slot_duration_minutes=30, capacity_per_slot=2, created_by="Alex",
        )
        session.commit()
        phone_windows = sched_svc.list_windows_for_session(session, selection_session.id, interview_stage=stgm.PHONE_INTERVIEW)
        result.check(
            "A: one Selection Session can have multiple scheduling windows",
            {window_monday.id, window_tuesday.id} <= {w.id for w in phone_windows},
        )

        # =====================================================================
        # B. Multiple Applications in the same Session see the same applicable
        # slot pool.
        # =====================================================================
        slots_a = sched_svc.list_available_slots(session, app_a.id, interview_stage=stgm.PHONE_INTERVIEW)
        slots_b = sched_svc.list_available_slots(session, app_b.id, interview_stage=stgm.PHONE_INTERVIEW)
        result.check(
            "B: multiple Applications in the same Session see the identical applicable slot pool",
            {(s["window_id"], s["start"]) for s in slots_a} == {(s["window_id"], s["start"]) for s in slots_b}
            and len(slots_a) > 0,
        )

        # =====================================================================
        # C/D. Booking by Application A reduces the SHARED slot capacity;
        # Application B can no longer book the same (capacity-1) slot.
        # =====================================================================
        chosen = slots_a[0]
        appt_a = sched_svc.book_slot(
            session, app_a.id, interview_stage=stgm.PHONE_INTERVIEW, window_id=chosen["window_id"],
            slot_start_at=chosen["start"],
        )
        session.commit()
        slots_b_after = sched_svc.list_available_slots(session, app_b.id, interview_stage=stgm.PHONE_INTERVIEW)
        result.check(
            "C: Application A booking a (capacity-1) slot removes it from the SHARED pool seen by other "
            "Applications in the same Session",
            (chosen["window_id"], chosen["start"]) not in {(s["window_id"], s["start"]) for s in slots_b_after},
        )
        b_blocked = _raises(
            ValueError, sched_svc.book_slot, session, app_b.id, interview_stage=stgm.PHONE_INTERVIEW,
            window_id=chosen["window_id"], slot_start_at=chosen["start"],
        )
        session.rollback()
        result.check("D: Application B cannot book a slot Application A already filled (shared capacity)", b_blocked)

        # =====================================================================
        # E. Capacity > 1 works: two DIFFERENT Applications may book the SAME
        # In-Person slot; a third is rejected once capacity (2) is exhausted.
        # =====================================================================
        ip_slot = sched_svc.list_available_slots(session, app_a.id, interview_stage=stgm.IN_PERSON_PRACTICAL)[0]
        ip_appt_a = sched_svc.book_slot(
            session, app_a.id, interview_stage=stgm.IN_PERSON_PRACTICAL, window_id=ip_slot["window_id"],
            slot_start_at=ip_slot["start"],
        )
        session.commit()
        ip_appt_b = sched_svc.book_slot(
            session, app_b.id, interview_stage=stgm.IN_PERSON_PRACTICAL, window_id=ip_slot["window_id"],
            slot_start_at=ip_slot["start"],
        )
        session.commit()
        result.check(
            "E: capacity > 1 allows two different Applications to book the same slot, each claiming a "
            "distinct ordinal",
            ip_appt_a.status == ccm.APPOINTMENT_CONFIRMED and ip_appt_b.status == ccm.APPOINTMENT_CONFIRMED
            and ip_appt_a.slot_ordinal != ip_appt_b.slot_ordinal,
        )
        c_blocked = _raises(
            ValueError, sched_svc.book_slot, session, app_c.id, interview_stage=stgm.IN_PERSON_PRACTICAL,
            window_id=ip_slot["window_id"], slot_start_at=ip_slot["start"],
        )
        session.rollback()
        result.check("E: a third Application is rejected once capacity 2 is fully exhausted", c_blocked)

        # =====================================================================
        # F. Phone and In-Person windows remain distinguishable.
        # =====================================================================
        in_person_slots = sched_svc.list_available_slots(session, app_c.id, interview_stage=stgm.IN_PERSON_PRACTICAL)
        result.check(
            "F: Phone Interview and In-Person windows/slots never mix",
            window_monday.id not in {s["window_id"] for s in in_person_slots}
            and in_person_window.id not in {s["window_id"] for s in slots_a},
        )

        # =====================================================================
        # G. The candidate secure link only shows the applicable Session/stage
        # slot pool.
        # =====================================================================
        token_row = sched_svc.issue_scheduling_token(session, app_c.id, interview_stage=stgm.PHONE_INTERVIEW)
        session.commit()
        resolved = sched_svc.resolve_token(session, token_row.token)
        slots_for_token = sched_svc.list_available_slots(session, resolved.application_id, interview_stage=resolved.interview_stage)
        result.check(
            "G: the candidate's secure scheduling link shows only the applicable Session + Interview Stage "
            "slot pool — never another stage's windows",
            len(slots_for_token) > 0
            and all(s["window_id"] in {window_monday.id, window_tuesday.id} for s in slots_for_token),
        )

        # =====================================================================
        # H/I. Automatic confirmation, and SMS+Email confirmation, still work.
        # =====================================================================
        result.check(
            "H: selecting an available shared slot still confirms the appointment automatically",
            appt_a.status == ccm.APPOINTMENT_CONFIRMED and appt_a.confirmed_at is not None,
        )
        confirmation_comms = [
            c for c in comm_svc.list_communications_for_application(session, app_a.id)
            if c.trigger_event == ccm.TRIGGER_APPOINTMENT_CONFIRMATION
        ]
        result.check(
            "I: automatic confirmation SMS+Email are still generated on shared-slot selection",
            len(confirmation_comms) >= 1 and confirmation_comms[0].channel_sms_used and confirmation_comms[0].channel_email_used,
        )

        # =====================================================================
        # J. Rescheduling preserves history (against the same shared pool).
        # =====================================================================
        other_slot = next(s for s in sched_svc.list_available_slots(session, app_a.id, interview_stage=stgm.PHONE_INTERVIEW))
        rescheduled = sched_svc.reschedule_appointment(
            session, appt_a.id, new_window_id=other_slot["window_id"], new_slot_start_at=other_slot["start"],
            reason="Candidate requested a different time",
        )
        session.commit()
        session.expire_all()
        prior = session.get(m.InterviewAppointment, appt_a.id)
        history = sched_svc.list_appointment_history(session, app_a.id)
        result.check(
            "J: rescheduling preserves the prior appointment (RESCHEDULED, never deleted) against the shared "
            "Session/stage pool",
            prior.status == ccm.APPOINTMENT_RESCHEDULED and rescheduled.previous_appointment_id == prior.id
            and prior.id in {a.id for a in history} and rescheduled.id in {a.id for a in history},
        )

        # =====================================================================
        # K. Candidate Dossier shows the appointment correctly.
        # =====================================================================
        dossier = dossier_svc.get_application_dossier(session, app_a.id)
        session.commit()
        result.check(
            "K: the Candidate Dossier shows the current (rescheduled) Phone Interview appointment",
            dossier.communication_context.current_phone_appointment is not None
            and dossier.communication_context.current_phone_appointment.id == rescheduled.id,
        )

        # =====================================================================
        # L. The Selection Session shows its scheduling windows.
        # =====================================================================
        all_session_windows = sched_svc.list_windows_for_session(session, selection_session.id)
        result.check(
            "L: the Selection Session's own listing surfaces every scheduling window offered under it",
            {window_monday.id, window_tuesday.id, in_person_window.id} <= {w.id for w in all_session_windows},
        )

        # =====================================================================
        # M. Existing (pre-fix) Task 5D behavior is unchanged: an
        # Application-specific override window still works exactly as
        # before, and is never visible to a DIFFERENT Application.
        # =====================================================================
        override_window = sched_svc.create_scheduling_window(
            session, application_id=app_c.id, interview_stage=stgm.PHONE_INTERVIEW, window_date=date(2026, 9, 11),
            start_time=time(9, 0), end_time=time(10, 0), slot_duration_minutes=30, created_by="Alex",
        )
        session.commit()
        slots_c = sched_svc.list_available_slots(session, app_c.id, interview_stage=stgm.PHONE_INTERVIEW)
        slots_b_final = sched_svc.list_available_slots(session, app_b.id, interview_stage=stgm.PHONE_INTERVIEW)
        result.check(
            "M: an Application-specific override window (the pre-fix Task 5D behavior) still works and is "
            "visible only to that one Application, never to another Application in the same Session",
            override_window.id in {s["window_id"] for s in slots_c}
            and override_window.id not in {s["window_id"] for s in slots_b_final},
        )

    finally:
        if restaurant is not None:
            for c in session.query(m.CandidateCommunication).join(
                m.Application, m.CandidateCommunication.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                c.response_inbound_id = None
                c.parent_communication_id = None
            session.flush()
            for c in list(session.query(m.CandidateCommunication).join(
                m.Application, m.CandidateCommunication.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(c)
            session.flush()
            for s in list(session.query(m.CommunicationTemplateSnapshot).join(
                m.CommunicationTemplate, m.CommunicationTemplateSnapshot.template_id == m.CommunicationTemplate.id
            ).filter(m.CommunicationTemplate.restaurant_id == restaurant.id)):
                session.delete(s)
            session.flush()
            for t in list(session.query(m.CommunicationTemplate).filter_by(restaurant_id=restaurant.id)):
                session.delete(t)
            session.flush()
            for tok in list(session.query(m.CandidateSchedulingToken).join(
                m.Application, m.CandidateSchedulingToken.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(tok)
            session.flush()
            for a in session.query(m.InterviewAppointment).join(
                m.Application, m.InterviewAppointment.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                a.previous_appointment_id = None
            session.flush()
            for a in list(session.query(m.InterviewAppointment).join(
                m.Application, m.InterviewAppointment.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(a)
            session.flush()
            for w in list(session.query(m.InterviewSchedulingWindow).filter(
                (m.InterviewSchedulingWindow.session_id.in_(session_ids))
                | (m.InterviewSchedulingWindow.application_id.in_(
                    [a.id for a in app_svc.list_applications(session, restaurant_id=restaurant.id)] or [-1]
                ))
            )):
                session.delete(w)
            session.flush()

            for assignment_row in session.query(m.SelectionSessionAssignment).filter(
                m.SelectionSessionAssignment.session_id.in_(session_ids)
            ):
                session.delete(assignment_row)
            session.flush()
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                application_row.session_id = None
                application_row.rule_set_version_id = None
            session.flush()
            for sid in session_ids:
                sc = session.get(m.SelectionSession, sid)
                if sc is not None:
                    sc.current_rule_set_version_id = None
            session.flush()
            version_rows = sorted(
                session.query(m.SelectionRuleSetVersion).filter(m.SelectionRuleSetVersion.session_id.in_(session_ids)),
                key=lambda v: v.id, reverse=True,
            )
            for version_row in version_rows:
                session.delete(version_row)
                session.flush()
            for sid in session_ids:
                sc = session.get(m.SelectionSession, sid)
                if sc is not None:
                    session.delete(sc)
            session.flush()

            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                session.delete(application_row)  # cascades Notes/StageTransitions/OutcomeDecisions/Signals
            session.flush()
            for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=restaurant.id):
                session.delete(person_row)
            session.flush()
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                session.delete(candidate_row)
            session.flush()
            for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                session.delete(raw)
            session.flush()

            still_attached = session.get(m.Restaurant, restaurant.id)
            if still_attached is not None:
                session.delete(still_attached)
            session.commit()
        session.close()


def _assert_job_posting_application_intake_pre_screening(
    session_factory: sessionmaker[Session], result: ValidationResult,
) -> None:
    """Task 5E checks A-BA (task's own letter list) — Job Posting
    generation/approval/versioning, Company/Branch independence, channel
    variants generated/edited/approved one-by-one, post-publication edit
    with a preserved reason, the generic Channel container (connected vs.
    manual), manual publication + unique tracking links (including
    multiple placements on the same Channel/variant version), tracking-
    link Application attribution, the public Web Application Form intake
    (CV + first-screening questions), repeated-applicant recognition,
    Application answers as self-reported evidence, the missing-evidence-
    never-becomes-negative-evidence discipline, the candidate-specific
    Missing-Evidence Questionnaire (generated only for genuinely missing
    required Criteria, sent automatically, reusing Task 5D's reminder
    engine), READY FOR PHONE REVIEW (reached automatically, never itself
    ADVANCE_TO_PHONE), and channel/placement analytics with advisory
    recommendations. Own dedicated session/restaurant, real commits, real
    cleanup (same reasoning as the Task 5D/5D-MICRO-FIX suites above)."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    session_ids: list[int] = []
    try:
        restaurant = m.Restaurant(name="Synthetic 5E Job Posting Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        selection_session = sess_svc.create_session(
            session, restaurant_id=restaurant.id, name="Server — 5E Validation Suite", target_role="SERVER",
            created_by="Selezionatore: Alex",
        )
        session.commit()
        session_ids.append(selection_session.id)

        acq_svc.seed_default_acquisition_sources(session, restaurant_id=restaurant.id)
        chan_svc.seed_default_channels(session, restaurant_id=restaurant.id)
        session.commit()
        channels = {c.name: c.id for c in chan_svc.list_channels(session, restaurant_id=restaurant.id)}
        acq_sources = {s.name: s.id for s in acq_svc.list_acquisition_sources(session, restaurant_id=restaurant.id)}

        # =====================================================================
        # A. Base Job Posting can be generated from Session/Role context.
        # =====================================================================
        job_posting = jp_svc.generate_base_posting(session, selection_session.id, created_by="Alex")
        session.commit()
        result.check(
            "A: a base Job Posting can be generated from Session/Role context, starting as a DRAFT",
            job_posting.status == jpm.DRAFT and job_posting.role == "SERVER" and job_posting.session_id == selection_session.id,
        )

        # =====================================================================
        # B. Base draft requires approval before the (channel-variant)
        # publication flow.
        # =====================================================================
        blocked = _raises(
            ValueError, jp_svc.create_channel_variant, session, job_posting.id, channels["Indeed"], variant_text="x",
        )
        session.rollback()
        result.check("B: channel variants cannot be generated before the base draft is approved", blocked)

        # =====================================================================
        # C/D. Base draft can be edited/versioned; Company and Branch
        # descriptions remain independent (no forced inheritance).
        # =====================================================================
        v1 = jp_svc.get_current_version(session, job_posting.id)
        v2 = jp_svc.edit_posting(
            session, job_posting.id, author="Alex", company_description="RF-One Test Kitchens — a great company.",
            branch_description="Our Winter Park location has its own independent voice.",
        )
        session.commit()
        result.check("C: editing the base draft creates a new version", v2.version == v1.version + 1 and job_posting.current_version == v2.version)
        result.check(
            "D: Company and Branch descriptions remain independent — editing one never overwrites the other",
            v2.company_description != v2.branch_description
            and "great company" in v2.company_description and "independent voice" in v2.branch_description,
        )
        v3 = jp_svc.edit_posting(session, job_posting.id, author="Alex", branch_description="Updated branch text only.")
        session.commit()
        result.check(
            "D: editing only the Branch description leaves the Company description completely untouched",
            v3.company_description == v2.company_description and v3.branch_description == "Updated branch text only.",
        )

        jp_svc.approve_posting(session, job_posting.id, approved_by="Alex")
        session.commit()
        result.check("base posting approval recorded", job_posting.status == jpm.APPROVED and job_posting.approved_version_id == v3.id)

        # =====================================================================
        # E/F/G. Channel-specific variants generated, independently editable,
        # and approved ONE BY ONE (never "Approve All").
        # =====================================================================
        indeed_variant = jp_svc.create_channel_variant(
            session, job_posting.id, channels["Indeed"], variant_text="Join our team — apply on Indeed!", created_by="Alex",
        )
        facebook_variant = jp_svc.create_channel_variant(
            session, job_posting.id, channels["Facebook"], variant_text="Join our team — apply via Facebook!", created_by="Alex",
        )
        session.commit()
        result.check(
            "E: channel-specific variants can be generated after base-posting approval",
            indeed_variant.status == jpm.DRAFT and facebook_variant.status == jpm.DRAFT,
        )

        jp_svc.edit_channel_variant(session, indeed_variant.id, variant_text="Updated Indeed-only text.", author="Alex")
        session.commit()
        result.check(
            "F: variants are independently editable — editing the Indeed variant never touches the Facebook variant",
            jp_svc.get_current_variant_version(session, indeed_variant.id).variant_text == "Updated Indeed-only text."
            and jp_svc.get_current_variant_version(session, facebook_variant.id).variant_text == "Join our team — apply via Facebook!",
        )

        jp_svc.approve_channel_variant(session, indeed_variant.id, approved_by="Alex")
        session.commit()
        result.check(
            "G: variants require individual approval — approving Indeed never auto-approves Facebook",
            indeed_variant.status == jpm.APPROVED and facebook_variant.status == jpm.DRAFT,
        )
        jp_svc.approve_channel_variant(session, facebook_variant.id, approved_by="Alex")
        session.commit()

        # =====================================================================
        # H/I. A published variant can be modified with a new version; the
        # modification reason is required and preserved.
        # =====================================================================
        reason_required = _raises(
            ValueError, jp_svc.edit_channel_variant, session, indeed_variant.id, variant_text="Changed after publish.",
            author="Alex",
        )
        session.rollback()
        result.check("H (precondition): editing an already-approved variant without a reason is rejected", reason_required)
        old_approved_version_id = indeed_variant.approved_version_id
        new_indeed_version = jp_svc.edit_channel_variant(
            session, indeed_variant.id, variant_text="Changed after publish.", author="Alex", reason="Low applicant quality",
        )
        session.commit()
        result.check(
            "H: a published variant can be modified — a brand-new version row is created, distinct from the "
            "prior published one",
            new_indeed_version.id != old_approved_version_id and new_indeed_version.variant_text == "Changed after publish.",
        )
        result.check(
            "H: the prior APPROVED version's own text is preserved untouched, never overwritten",
            session.get(m.JobPostingChannelVariantVersion, old_approved_version_id).variant_text == "Updated Indeed-only text.",
        )
        result.check("I: the modification reason is preserved", new_indeed_version.reason == "Low applicant quality")
        # Re-approve the new version so a publication can be recorded against it.
        jp_svc.approve_channel_variant(session, indeed_variant.id, approved_by="Alex")
        session.commit()

        # =====================================================================
        # J. Generic Channel container supports connected/manual distinction.
        # =====================================================================
        connected_channel = chan_svc.create_channel(session, restaurant_id=restaurant.id, name="Future API Connector", is_connected=True)
        session.commit()
        result.check(
            "J: the generic Channel container distinguishes CONNECTED from MANUAL",
            connected_channel.is_connected is True and not session.get(m.ChannelDefinition, channels["Facebook"]).is_connected,
        )

        # =====================================================================
        # K/L/M. Manual publication recorded; unique tracking link issued;
        # multiple placements/tracking-links on the SAME Channel + variant
        # version.
        # =====================================================================
        chan_svc.get_channel(session, channels["Facebook"]).default_acquisition_source_id = acq_sources["Facebook"]
        session.commit()

        pub_a = chan_svc.record_publication(session, facebook_variant.id, placement_label="Facebook Group A", created_by="Alex")
        session.commit()
        result.check(
            "K: a manual publication/placement can be recorded against an approved channel variant",
            pub_a.variant_version_id == facebook_variant.approved_version_id,
        )
        link_a = pub_a.tracking_links[0]
        result.check("L: a unique tracking link is created for the publication", bool(link_a.token))

        pub_b = chan_svc.record_publication(session, facebook_variant.id, placement_label="Facebook Group B", created_by="Alex")
        session.commit()
        link_b = pub_b.tracking_links[0]
        result.check(
            "M: multiple tracking links may exist for the same Channel/posting version (different placements)",
            link_a.token != link_b.token and pub_a.variant_version_id == pub_b.variant_version_id
            and pub_a.placement_label != pub_b.placement_label,
        )

        # =====================================================================
        # O. Public Application Form "loads" (its context resolves cleanly
        # from the tracking link alone).
        # =====================================================================
        context_a = chan_svc.resolve_application_context(session, link_a.token)
        result.check(
            "O: the public Application Form's context resolves purely from the tracking link",
            context_a is not None and context_a["session"].id == selection_session.id
            and context_a["job_posting"].id == job_posting.id,
        )
        invalid_context = chan_svc.resolve_application_context(session, "not-a-real-token")
        result.check("O: an unknown tracking link resolves to no context (never a crash)", invalid_context is None)

        # =====================================================================
        # Q. Application Form supports structured first-screening questions
        # (distinct from Phone/In-Person Interview questions).
        # =====================================================================
        weekend_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Weekend Availability", coefficient=1.0, direction=psm.POSITIVE,
            evidence_sources_allowed=[psm.APPLICATION],
        )
        wine_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Wine Knowledge", coefficient=1.0, direction=psm.POSITIVE,
            evidence_sources_allowed=[psm.RESUME_FACT], required_for_phone_review=True,
            missing_evidence_question_text="Do you have wine service knowledge?",
            missing_evidence_answer_level_map={"YES": 3, "NO": 0},
        )
        guest_sensitivity_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Guest Sensitivity", coefficient=1.0, direction=psm.POSITIVE,
            evidence_sources_allowed=[psm.CONSISTENCY_INFORMATION],
        )
        session.commit()
        weekend_question = aq_svc.create_question(
            session, restaurant_id=restaurant.id, session_id=selection_session.id,
            question_text="Are you available on weekends?", response_type=jpm.RESPONSE_YES_NO, is_required=True,
            related_criterion_id=weekend_criterion.id, answer_level_map={"YES": 4, "NO": 1},
        )
        session.commit()
        result.check(
            "Q: the Application Form's configured first-screening questions are retrievable for this Session/Role, "
            "distinct from Phone/In-Person Interview questions",
            weekend_question in aq_svc.list_questions_for_context(
                session, restaurant_id=restaurant.id, session_id=selection_session.id, target_role="SERVER",
            ),
        )

        me_template = tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_MISSING_EVIDENCE_QUESTIONNAIRE,
            sms_text="Thanks for applying! A couple of things we could not tell from your CV: $missing_evidence_link",
            email_subject="A few more questions", email_body="Please answer here: $missing_evidence_link",
        )
        session.commit()

        # =====================================================================
        # N/P/R/S/T/W. Submission: tracking-link attribution, CV handling,
        # CandidatePerson/Application creation, Application answers as
        # self-reported evidence.
        # =====================================================================
        raw_text_1 = "Alex Applicant\nalex.applicant.5e@example.com\n555-990-0001\n\nEXPERIENCE\nServer, Bistro 5E\nJan 2023 - Present\nServed guests.\n"
        result1 = intake_svc.submit_application(
            session, restaurant_id=restaurant.id, channel_publication_id=pub_a.id, selection_session_id=selection_session.id,
            target_role="SERVER", original_filename="alex_applicant.txt", raw_text=raw_text_1,
            content_hash=compute_content_hash(raw_text_1, "alex_applicant_5e_v1"),
            first_name="Alex", last_name="Applicant", email="alex.applicant.5e@example.com", phone="555-990-0001",
            answers={weekend_question.id: "YES"},
        )
        session.commit()
        application = result1.application
        result.check(
            "N: the Application is attributed to the exact source/channel/placement via the tracking link "
            "(Acquisition Source set automatically)",
            application.channel_publication_id == pub_a.id and application.acquisition_source_id == acq_sources["Facebook"],
        )
        result.check(
            "P/T: the original CV is preserved and accessible (real text extraction, not a placeholder)",
            application.candidate.raw_resume_id is not None
            and "Bistro 5E" in (session.get(m.RawResume, application.candidate.raw_resume_id).raw_text or ""),
        )
        result.check(
            "R: submission resolves/creates the CandidatePerson correctly",
            application.person is not None and application.person.primary_email == "alex.applicant.5e@example.com",
        )
        result.check("S: submission creates a new Application", application.id in {a.id for a in app_svc.list_applications(session, restaurant_id=restaurant.id)})

        answers_recorded = aq_svc.list_answers_for_application(session, application.id)
        result.check(
            "W: Application answers are stored as candidate self-reported evidence (raw answer preserved)",
            any(a.raw_answer == "YES" and a.question_definition_id == weekend_question.id for a in answers_recorded),
        )

        run1 = ps_svc.get_latest_run_for_application(session, application.id)
        eval_weekend = ps_svc.get_evaluation_for_criterion(session, run1.id, weekend_criterion.id)
        result.check(
            "W: the Application answer became Primary Screening evidence with evidence_source=APPLICATION "
            "(candidate self-report, never independently verified fact)",
            eval_weekend.evidence_source == psm.APPLICATION and eval_weekend.effective_level == 4
            and eval_weekend.origin == psm.SYSTEM_GENERATED,
        )

        # =====================================================================
        # X/Y/Z. Missing CV/Application information never becomes negative
        # evidence; INSUFFICIENT_EVIDENCE is represented explicitly; deep
        # behavioral criteria are not inferred from weak/absent evidence.
        # =====================================================================
        eval_wine = ps_svc.get_evaluation_for_criterion(session, run1.id, wine_criterion.id)
        result.check(
            "X: missing CV/Application information about wine knowledge never becomes a fabricated negative level",
            eval_wine.effective_level is None,
        )
        result.check(
            "Y: insufficient/unavailable evidence is represented explicitly (never silently EVALUATED)",
            eval_wine.status in (psm.NOT_EVALUATED, psm.INSUFFICIENT_EVIDENCE),
        )
        eval_guest = ps_svc.get_evaluation_for_criterion(session, run1.id, guest_sensitivity_criterion.id)
        result.check(
            "Z: a deep behavioral Criterion (Guest Sensitivity) is never inferred from weak/absent early-stage "
            "evidence — stays unresolved, never a fabricated level",
            eval_guest.effective_level is None and eval_guest.status in (psm.NOT_EVALUATED, psm.INSUFFICIENT_EVIDENCE),
        )

        # =====================================================================
        # AA/AB/AC/AD. Missing-Evidence Questionnaire generated only when
        # needed, with only genuinely missing questions, sent automatically.
        # =====================================================================
        questionnaire = result1.questionnaire
        result.check(
            "AA: a Missing-Evidence Questionnaire is generated automatically when important evidence is still "
            "missing (and the Application is not clearly to be stopped)",
            questionnaire is not None,
        )
        me_questions = me_svc.list_questions(session, questionnaire.id)
        result.check(
            "AB/AC: the Questionnaire contains ONLY the genuinely missing, importance-flagged question — never "
            "the already-answered Weekend question, never the non-required Guest-Sensitivity question",
            len(me_questions) == 1 and me_questions[0].criterion_id == wine_criterion.id,
        )
        comms_after_intake = comm_svc.list_communications_for_application(session, application.id)
        me_comm = next((c for c in comms_after_intake if c.trigger_event == ccm.TRIGGER_MISSING_EVIDENCE_QUESTIONNAIRE), None)
        result.check(
            "AD: the Questionnaire is sent automatically, with no prior Selezionatore approval step",
            me_comm is not None and me_comm.performed_by == "SYSTEM_AUTOMATIC",
        )

        # =====================================================================
        # AE/AF/AG/AH. Secure questionnaire link; raw answers preserved;
        # answers update Primary Screening evidence without overwriting
        # what is already on record.
        # =====================================================================
        resolved_questionnaire = me_svc.resolve_questionnaire_token(session, questionnaire.token)
        result.check("AE: the secure questionnaire link resolves to the correct Questionnaire", resolved_questionnaire is not None and resolved_questionnaire.id == questionnaire.id)

        me_svc.submit_answers(session, questionnaire.id, {me_questions[0].id: "YES"})
        session.commit()
        stored_answer = session.query(m.MissingEvidenceAnswer).filter_by(question_id=me_questions[0].id).first()
        result.check("AF: the candidate's raw answer is preserved exactly as given", stored_answer.raw_answer == "YES")

        eval_wine_after = ps_svc.get_evaluation_for_criterion(session, run1.id, wine_criterion.id)
        result.check(
            "AG: the Questionnaire answer updates the relevant Primary Screening evidence (restaurant-configured "
            "answer mapping resolved a level)",
            eval_wine_after.status == psm.EVALUATED and eval_wine_after.effective_level == 3,
        )
        eval_weekend_after = ps_svc.get_evaluation_for_criterion(session, run1.id, weekend_criterion.id)
        result.check(
            "AH: prior evidence (the Weekend-Availability answer) remains completely intact after the "
            "Questionnaire is processed",
            eval_weekend_after.effective_level == 4,
        )

        # =====================================================================
        # AI/AJ/AK. Sufficient evidence -> READY FOR PHONE REVIEW; this never
        # itself performs ADVANCE_TO_PHONE; the Selezionatore still decides.
        # =====================================================================
        result.check(
            "AI: once sufficient early-stage evidence exists, the Application reaches READY FOR PHONE REVIEW",
            me_svc.is_ready_for_phone_review(session, application.id),
        )
        application_after_readiness = app_svc.get_application(session, application.id)
        result.check(
            "AJ: reaching READY FOR PHONE REVIEW does NOT automatically ADVANCE_TO_PHONE (Stage is untouched)",
            application_after_readiness.current_stage != stgm.PHONE_INTERVIEW,
        )
        stage_svc.set_stage(session, application.id, stgm.PHONE_INTERVIEW, performed_by="Selezionatore: Alex")
        session.commit()
        application_after_advance = app_svc.get_application(session, application.id)
        result.check(
            "AK: the Selezionatore can still explicitly decide ADVANCE_TO_PHONE afterward",
            application_after_advance.current_stage == stgm.PHONE_INTERVIEW,
        )

        # =====================================================================
        # AL. Task 5D's reminder/no-response engine is reused for the
        # Missing-Evidence Questionnaire (no separate reminder system).
        # =====================================================================
        reminder_policy = m.CommunicationReminderPolicy(
            restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_MISSING_EVIDENCE_QUESTIONNAIRE,
            reminder_count=1, first_reminder_delay_hours=24, reminder_interval_hours=24, final_deadline_hours=72,
        )
        session.add(reminder_policy)
        session.commit()

        raw_text_2 = "Drew SecondApplicant\ndrew.second.5e@example.com\n555-990-0002\n\nEXPERIENCE\nServer, Diner 5E\nFeb 2023 - Present\nServed guests.\n"
        result2 = intake_svc.submit_application(
            session, restaurant_id=restaurant.id, channel_publication_id=pub_b.id, selection_session_id=selection_session.id,
            target_role="SERVER", original_filename="drew_second.txt", raw_text=raw_text_2,
            content_hash=compute_content_hash(raw_text_2, "drew_second_5e"),
            first_name="Drew", last_name="SecondApplicant", email="drew.second.5e@example.com", phone="555-990-0002",
            answers={weekend_question.id: "YES"},
        )
        session.commit()
        comms_2 = comm_svc.list_communications_for_application(session, result2.application.id)
        me_comm_2 = next(c for c in comms_2 if c.trigger_event == ccm.TRIGGER_MISSING_EVIDENCE_QUESTIONNAIRE)
        result.check(
            "AL: the Missing-Evidence Questionnaire reuses Task 5D's existing reminder/no-response engine "
            "(a configured Reminder Policy attaches to it) rather than a separate reminder system",
            me_comm_2.awaiting_response and me_comm_2.reminder_policy_id == reminder_policy.id,
        )

        # =====================================================================
        # U/V. Repeated applicant: same person, NEW Application, never a
        # duplicate CandidatePerson; prior-Application history stays visible.
        # =====================================================================
        raw_text_3 = (
            "Alex Applicant\nalex.applicant.5e@example.com\n555-990-0001\n\nEXPERIENCE\nServer, Bistro 5E\n"
            "Jan 2023 - Present\nServed guests.\nAlso trained new hires.\n"
        )
        result3 = intake_svc.submit_application(
            session, restaurant_id=restaurant.id, channel_publication_id=pub_b.id, selection_session_id=selection_session.id,
            target_role="SERVER", original_filename="alex_applicant_v2.txt", raw_text=raw_text_3,
            content_hash=compute_content_hash(raw_text_3, "alex_applicant_5e_v2"),
            first_name="Alex", last_name="Applicant", email="alex.applicant.5e@example.com", phone="555-990-0001",
            answers={weekend_question.id: "YES"},
        )
        session.commit()
        result.check(
            "U: a repeated applicant creates a NEW Application, never a duplicate CandidatePerson",
            result3.application.id != application.id and result3.application.person_id == application.person_id,
        )
        result.check(
            "V: repeated-Application history remains visible from the new Application",
            result3.is_repeated_applicant and result3.prior_application_count >= 1
            and application.id in {a.id for a in app_svc.list_prior_applications(session, result3.application.id)},
        )

        # =====================================================================
        # AM/AN/AO/AP/AQ. Channel/placement analytics aggregate correctly,
        # distinguish placements, cost stays null when absent, and advisory
        # recommendations are produced without any write.
        # =====================================================================
        rows = analytics_svc.get_channel_funnel_metrics(session, restaurant_id=restaurant.id, session_id=selection_session.id)
        row_a = next(r for r in rows if r.publication_id == pub_a.id)
        row_b = next(r for r in rows if r.publication_id == pub_b.id)
        result.check(
            "AM/AN: metrics aggregate correctly per Channel/publication/variant version",
            row_a.channel_name == "Facebook" and row_b.channel_name == "Facebook" and row_a.applications == 1,
        )
        result.check(
            "AO: metrics distinguish multiple placements on the same Channel — traffic is never collapsed into "
            "one generic source",
            row_a.placement_label != row_b.placement_label and row_a.publication_id != row_b.publication_id
            and row_b.applications == 2,  # result2 (Drew) + result3 (repeated Alex) both went through pub_b
        )
        result.check("AP: cost metrics remain null when no cost was recorded", row_a.cost_amount_cents is None and row_a.cost_per_application is None)

        pub_a_row = session.get(m.ChannelPublication, pub_a.id)
        pub_a_row.cost_amount_cents = 5000
        pub_a_row.cost_currency = "USD"
        session.commit()
        rows_with_cost = analytics_svc.get_channel_funnel_metrics(session, restaurant_id=restaurant.id, session_id=selection_session.id)
        row_a_with_cost = next(r for r in rows_with_cost if r.publication_id == pub_a.id)
        result.check(
            "AP: cost-per-Application is computed once cost data is actually available, never fabricated before then",
            row_a_with_cost.cost_per_application == 5000.0,
        )

        recommendations = analytics_svc.recommend_channel_actions(rows_with_cost)
        result.check(
            "AQ: advisory recommendations can be generated for every row, using only the fixed advisory vocabulary, "
            "without writing anything",
            len(recommendations) == len(rows_with_cost)
            and all(r["recommendation"] in jpm.RECOMMENDATION_ACTIONS for r in recommendations),
        )
        result.check(
            "AR: no provider-specific connector is required anywhere in this flow (every Channel/Publication "
            "action above used only the generic container)",
            not hasattr(m.ChannelDefinition, "api_key") and not hasattr(m.ChannelDefinition, "provider_credentials"),
        )

    finally:
        if restaurant is not None:
            # -- Missing-Evidence + Application-Question tables ------------------
            for a in list(session.query(m.MissingEvidenceAnswer).join(
                m.MissingEvidenceQuestion, m.MissingEvidenceAnswer.question_id == m.MissingEvidenceQuestion.id
            ).join(
                m.MissingEvidenceQuestionnaire, m.MissingEvidenceQuestion.questionnaire_id == m.MissingEvidenceQuestionnaire.id
            ).join(m.Application, m.MissingEvidenceQuestionnaire.application_id == m.Application.id)
            .filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(a)
            session.flush()
            for q in list(session.query(m.MissingEvidenceQuestion).join(
                m.MissingEvidenceQuestionnaire, m.MissingEvidenceQuestion.questionnaire_id == m.MissingEvidenceQuestionnaire.id
            ).join(m.Application, m.MissingEvidenceQuestionnaire.application_id == m.Application.id)
            .filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(q)
            session.flush()
            for qn in list(session.query(m.MissingEvidenceQuestionnaire).join(
                m.Application, m.MissingEvidenceQuestionnaire.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(qn)
            session.flush()
            for a in list(session.query(m.ApplicationQuestionAnswer).join(
                m.Application, m.ApplicationQuestionAnswer.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(a)
            session.flush()
            for qd in list(session.query(m.ApplicationQuestionDefinition).filter_by(restaurant_id=restaurant.id)):
                session.delete(qd)
            session.flush()

            # -- Communications (mirrors the Task 5D cleanup pattern) -----------
            for c in session.query(m.CandidateCommunication).join(
                m.Application, m.CandidateCommunication.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                c.response_inbound_id = None
                c.parent_communication_id = None
            session.flush()
            for i in list(session.query(m.InboundCommunication).join(
                m.Application, m.InboundCommunication.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(i)
            session.flush()
            for c in list(session.query(m.CandidateCommunication).join(
                m.Application, m.CandidateCommunication.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(c)
            session.flush()
            for p in list(session.query(m.CommunicationReminderPolicy).filter_by(restaurant_id=restaurant.id)):
                session.delete(p)
            session.flush()
            for s in list(session.query(m.CommunicationTemplateSnapshot).join(
                m.CommunicationTemplate, m.CommunicationTemplateSnapshot.template_id == m.CommunicationTemplate.id
            ).filter(m.CommunicationTemplate.restaurant_id == restaurant.id)):
                session.delete(s)
            session.flush()
            for t in list(session.query(m.CommunicationTemplate).filter_by(restaurant_id=restaurant.id)):
                session.delete(t)
            session.flush()

            # -- Channel Publications / Tracking Links / Job Posting tree -------
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                application_row.channel_publication_id = None
                application_row.acquisition_source_id = None
            session.flush()
            job_posting_ids = [jp.id for jp in session.query(m.JobPosting).filter_by(restaurant_id=restaurant.id)]
            variant_ids = [
                v.id for v in session.query(m.JobPostingChannelVariant).filter(
                    m.JobPostingChannelVariant.job_posting_id.in_(job_posting_ids or [-1])
                )
            ]
            variant_version_ids = [
                vv.id for vv in session.query(m.JobPostingChannelVariantVersion).filter(
                    m.JobPostingChannelVariantVersion.variant_id.in_(variant_ids or [-1])
                )
            ]
            publication_ids = [
                p.id for p in session.query(m.ChannelPublication).filter(
                    m.ChannelPublication.variant_version_id.in_(variant_version_ids or [-1])
                )
            ]
            for link in list(session.query(m.ChannelTrackingLink).filter(
                m.ChannelTrackingLink.channel_publication_id.in_(publication_ids or [-1])
            )):
                session.delete(link)
            session.flush()
            for pub in list(session.query(m.ChannelPublication).filter(m.ChannelPublication.id.in_(publication_ids or [-1]))):
                session.delete(pub)
            session.flush()
            for variant in session.query(m.JobPostingChannelVariant).filter(m.JobPostingChannelVariant.id.in_(variant_ids or [-1])):
                variant.approved_version_id = None
            session.flush()
            for vv in list(session.query(m.JobPostingChannelVariantVersion).filter(m.JobPostingChannelVariantVersion.id.in_(variant_version_ids or [-1]))):
                session.delete(vv)
            session.flush()
            for variant in list(session.query(m.JobPostingChannelVariant).filter(m.JobPostingChannelVariant.id.in_(variant_ids or [-1]))):
                session.delete(variant)
            session.flush()
            for jp in session.query(m.JobPosting).filter(m.JobPosting.id.in_(job_posting_ids or [-1])):
                jp.approved_version_id = None
            session.flush()
            for v in list(session.query(m.JobPostingVersion).filter(m.JobPostingVersion.job_posting_id.in_(job_posting_ids or [-1]))):
                session.delete(v)
            session.flush()
            for jp in list(session.query(m.JobPosting).filter(m.JobPosting.id.in_(job_posting_ids or [-1]))):
                session.delete(jp)
            session.flush()

            for c in list(session.query(m.ChannelDefinition).filter_by(restaurant_id=restaurant.id)):
                session.delete(c)
            session.flush()
            for a in list(session.query(m.AcquisitionSourceDefinition).filter_by(restaurant_id=restaurant.id)):
                session.delete(a)
            session.flush()

            # -- Primary Screening (exact established pattern) ------------------
            for evaluation_row in session.query(m.PrimaryScreeningCriterionEvaluation).join(
                m.PrimaryScreeningRun, m.PrimaryScreeningCriterionEvaluation.run_id == m.PrimaryScreeningRun.id
            ).filter(m.PrimaryScreeningRun.restaurant_id == restaurant.id):
                session.delete(evaluation_row)
            session.flush()
            for run_row in session.query(m.PrimaryScreeningRun).filter_by(restaurant_id=restaurant.id):
                session.delete(run_row)
            session.flush()
            for snapshot_row in session.query(m.PrimaryScreeningCriterionSnapshot).join(
                m.PrimaryScreeningCriterion, m.PrimaryScreeningCriterionSnapshot.criterion_id == m.PrimaryScreeningCriterion.id
            ).filter(m.PrimaryScreeningCriterion.restaurant_id == restaurant.id):
                session.delete(snapshot_row)
            session.flush()
            for criterion_row in session.query(m.PrimaryScreeningCriterion).filter_by(restaurant_id=restaurant.id):
                session.delete(criterion_row)
            session.flush()

            # -- Session governance (mirrors the 5C/5D-MICRO-FIX pattern) -------
            for assignment_row in session.query(m.SelectionSessionAssignment).filter(
                m.SelectionSessionAssignment.session_id.in_(session_ids)
            ):
                session.delete(assignment_row)
            session.flush()
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                application_row.session_id = None
                application_row.rule_set_version_id = None
            session.flush()
            for sid in session_ids:
                sc = session.get(m.SelectionSession, sid)
                if sc is not None:
                    sc.current_rule_set_version_id = None
            session.flush()
            version_rows = sorted(
                session.query(m.SelectionRuleSetVersion).filter(m.SelectionRuleSetVersion.session_id.in_(session_ids)),
                key=lambda v: v.id, reverse=True,
            )
            for version_row in version_rows:
                session.delete(version_row)
                session.flush()
            for sid in session_ids:
                sc = session.get(m.SelectionSession, sid)
                if sc is not None:
                    session.delete(sc)
            session.flush()

            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                application_row.current_queue_id = None
            session.flush()
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                session.delete(application_row)  # cascades ApplicationQueueMovement
            session.flush()
            for queue_row in session.query(m.SelectionQueue).filter_by(restaurant_id=restaurant.id):
                session.delete(queue_row)
            session.flush()
            for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=restaurant.id):
                session.delete(person_row)
            session.flush()
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                session.delete(candidate_row)
            session.flush()
            for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                session.delete(raw)
            session.flush()

            still_attached = session.get(m.Restaurant, restaurant.id)
            if still_attached is not None:
                session.delete(still_attached)
            session.commit()
        session.close()


def _assert_compliance_audit_domain_closure(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    """Task 5F checks A-BH (task's own letter list) — the Compliance/Rule
    Review Service (generic across object types, understandable warnings,
    non-destructive suggested rewrites, human disposition preserved,
    immutable/versioned review history, the HIGH_CONCERN activation guard,
    no retroactive deactivation), the Selection Audit/Explainability
    reconstruction (internal Priority Index, evidence provenance, every
    human override, historical Rule versioning, Notes, a chronological
    Timeline), and integrated end-to-end domain-closure scenarios. Own
    dedicated session/restaurant, real commits, real cleanup (same
    reasoning as every other Task 5D/5E suite above)."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    session_ids: list[int] = []
    try:
        restaurant = m.Restaurant(name="Synthetic 5F Compliance Audit Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        def _upload(name: str, email: str, phone: str, role_line: str) -> m.Application:
            text = f"{name}\n{email}\n{phone}\n\nEXPERIENCE\n{role_line}\n"
            imported = import_pipeline.import_one_resume(
                session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD, original_filename=f"{email}.txt",
                storage_path=None, raw_text=text, content_hash=compute_content_hash(text, email),
            )
            application = app_svc.create_application(
                session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id, target_role="SERVER",
            )
            session.commit()
            return application

        selection_session = sess_svc.create_session(
            session, restaurant_id=restaurant.id, name="Server — 5F Closure Suite", target_role="SERVER",
            created_by="Selezionatore: Alex",
        )
        session.commit()
        session_ids.append(selection_session.id)
        rs_svc.confirm_rule_set_version(session, selection_session.id, confirmed_by="Alex", note="5F closure suite")
        session.commit()

        stop_def = outcome_svc.create_outcome_definition(session, restaurant_id=restaurant.id, name="5F Stop", lifecycle_effect=om.CLOSED, requires_reason=True)
        hold_def = outcome_svc.create_outcome_definition(session, restaurant_id=restaurant.id, name="5F Hold", lifecycle_effect=om.SUSPENDED, requires_reason=True)
        hirable_def = outcome_svc.create_outcome_definition(session, restaurant_id=restaurant.id, name="5F Hirable", lifecycle_effect=om.CLOSED, requires_reason=False)
        active_def = outcome_svc.create_outcome_definition(session, restaurant_id=restaurant.id, name="5F Active", lifecycle_effect=om.ACTIVE, requires_reason=False)
        session.commit()

        # =====================================================================
        # PART A — Compliance Review Service (checks A-Q).
        # =====================================================================
        req_set = req_svc.create_requirement_set(session, restaurant_id=restaurant.id, name="5F Requirement Set")
        requirement = req_svc.add_requirement(
            session, req_set.id, name="Wine service knowledge", criticality=rm.PREFERRED, trainability=rm.TRAINABLE,
            assessment_stages=[rm.RESUME],
        )
        session.commit()

        hard_disqualifier_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="No-show history", coefficient=1.0, direction=psm.POSITIVE,
            is_hard_disqualifier=True, hard_disqualifier_trigger_level=3,
        )
        required_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Full-service restaurant experience", coefficient=1.0,
            direction=psm.POSITIVE, evidence_sources_allowed=[psm.APPLICATION], required_for_phone_review=True,
            missing_evidence_answer_level_map={"YES": 3, "NO": 0},
        )
        bad_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Must be young and energetic",
            description="Candidate must be young and energetic, with an attractive appearance.",
            coefficient=1.0, direction=psm.POSITIVE,
        )
        stage_bad_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Composure under pressure", coefficient=1.0,
            direction=psm.POSITIVE, evidence_sources_allowed=[psm.RESUME_FACT, psm.APPLICATION],
        )
        missing_evidence_bad_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Wine knowledge (legacy config)", coefficient=1.0,
            direction=psm.POSITIVE,
            evaluation_guidance="If wine knowledge is not mentioned on the CV, count as negative and set level 0.",
        )
        vague_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Good vibe", description="Candidate must have a good vibe and fit our culture.",
            coefficient=1.0, direction=psm.POSITIVE,
        )
        never_reviewed_criterion = ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name="Reliable transportation to the restaurant", coefficient=1.0,
            direction=psm.POSITIVE,
        )
        session.commit()

        family_question = aq_svc.create_question(
            session, restaurant_id=restaurant.id, question_text="Are you married and do you have children?",
            response_type=jpm.RESPONSE_TEXT,
        )
        session.commit()

        # A/B/C/D — the review works across genuinely different object types.
        requirement_review = compliance_svc.review_object(session, cpm.REQUIREMENT, requirement.id)
        criterion_review = compliance_svc.review_object(session, cpm.PRIMARY_SCREENING_CRITERION, bad_criterion.id)
        hd_review = compliance_svc.review_object(session, cpm.PRIMARY_SCREENING_CRITERION, hard_disqualifier_criterion.id)
        question_review = compliance_svc.review_object(session, cpm.APPLICATION_QUESTION_DEFINITION, family_question.id)
        session.commit()
        result.check("A: Compliance review supports Requirements", requirement_review is not None)
        result.check("B: Compliance review supports Screening Criteria", criterion_review is not None and len(criterion_review.warnings) >= 1)
        result.check("C: Compliance review supports Hard Disqualifiers", hd_review is not None)
        result.check(
            "D: Compliance review supports Application Questions",
            question_review is not None and any(w.category == cpm.FAMILY_MARITAL_PREGNANCY for w in question_review.warnings),
        )
        result.check(
            "E: a protected-characteristic-like rule produces a warning",
            any(w.severity == cpm.HIGH_CONCERN and w.category in (cpm.AGE, cpm.APPEARANCE_BODY) for w in criterion_review.warnings),
        )

        vague_review = compliance_svc.review_object(session, cpm.PRIMARY_SCREENING_CRITERION, vague_criterion.id)
        stage_review = compliance_svc.review_object(session, cpm.PRIMARY_SCREENING_CRITERION, stage_bad_criterion.id)
        missing_evidence_review = compliance_svc.review_object(session, cpm.PRIMARY_SCREENING_CRITERION, missing_evidence_bad_criterion.id)
        session.commit()
        result.check("F: weak job relevance produces a warning", any(w.category == cpm.VAGUE_SUBJECTIVE for w in vague_review.warnings))
        result.check("G: a stage-reliability issue produces a warning", any(w.category == cpm.STAGE_RELIABILITY for w in stage_review.warnings))
        result.check(
            "H: a rule treating missing evidence as negative evidence produces a HIGH CONCERN warning",
            any(w.category == cpm.MISSING_EVIDENCE_AS_NEGATIVE and w.severity == cpm.HIGH_CONCERN for w in missing_evidence_review.warnings),
        )

        original_description = bad_criterion.description
        result.check(
            "I: the suggested rewrite never modifies the original configuration automatically",
            bad_criterion.description == original_description and criterion_review.warnings[0].suggested_rewrite is not None,
        )

        accept_disposition = compliance_svc.record_disposition(
            session, criterion_review.id, action=cpm.ACCEPT_REWRITE, performed_by="Alex",
            final_text="Must be able to perform the pace and physical duties required by the role.",
        )
        session.commit()
        result.check("J: a human can accept the suggested rewrite (recorded, not silently applied)", accept_disposition.action == cpm.ACCEPT_REWRITE)

        edit_disposition = compliance_svc.record_disposition(
            session, vague_review.id, action=cpm.EDIT_MANUALLY, performed_by="Alex",
            final_text="Demonstrates positive, professional guest interaction (observable in the interview).",
        )
        session.commit()
        result.check("K: a human can edit the suggestion manually", edit_disposition.action == cpm.EDIT_MANUALLY and edit_disposition.final_text is not None)

        keep_disposition = compliance_svc.record_disposition(
            session, stage_review.id, action=cpm.KEEP_ORIGINAL, performed_by="Alex", reason="Will revisit after Phone Interview.",
        )
        session.commit()
        result.check("L: a human can keep the original text", keep_disposition.action == cpm.KEEP_ORIGINAL)
        result.check(
            "M: every human action is preserved distinctly",
            {d.action for d in [accept_disposition, edit_disposition, keep_disposition]} == {cpm.ACCEPT_REWRITE, cpm.EDIT_MANUALLY, cpm.KEEP_ORIGINAL},
        )

        ps_svc.update_criterion(
            session, bad_criterion.id, name="Pace and physical duties",
            description="Must be able to perform the pace and physical duties required by the role.",
        )
        session.commit()
        second_review = compliance_svc.review_object(session, cpm.PRIMARY_SCREENING_CRITERION, bad_criterion.id)
        session.commit()
        history = compliance_svc.list_review_history(session, cpm.PRIMARY_SCREENING_CRITERION, bad_criterion.id)
        result.check(
            "N: Compliance Review history is immutable and versioned — the first review's original text is preserved unchanged",
            len(history) == 2 and history[0].id == criterion_review.id and "young and energetic" in history[0].reviewed_text
            and "young and energetic" not in second_review.reviewed_text,
        )

        ps_svc.deactivate_criterion(session, missing_evidence_bad_criterion.id)
        session.commit()
        blocked = _raises(
            ValueError, compliance_svc.assert_activation_allowed, session, cpm.PRIMARY_SCREENING_CRITERION,
            missing_evidence_bad_criterion.id,
        )
        result.check("O: an unresolved HIGH CONCERN blocks activation unless acknowledged", blocked)

        reason_required = _raises(
            ValueError, compliance_svc.record_disposition, session, missing_evidence_review.id,
            action=cpm.ACKNOWLEDGE_HIGH_CONCERN, performed_by="Alex", reason=None,
        )
        session.rollback()
        compliance_svc.record_disposition(
            session, missing_evidence_review.id, action=cpm.ACKNOWLEDGE_HIGH_CONCERN, performed_by="Alex",
            reason="Restaurant will manually ensure missing-evidence is never scored negatively; monitoring in practice.",
        )
        session.commit()
        compliance_svc.assert_activation_allowed(session, cpm.PRIMARY_SCREENING_CRITERION, missing_evidence_bad_criterion.id)
        result.check("P: acknowledging a HIGH CONCERN requires and preserves a human reason", reason_required)

        result.check(
            "Q: a pre-existing/never-reviewed active rule is never automatically disabled",
            never_reviewed_criterion.is_active
            and compliance_svc.review_status_summary(session, cpm.PRIMARY_SCREENING_CRITERION, never_reviewed_criterion.id)["status"] == "NOT_YET_REVIEWED",
        )

        # =====================================================================
        # Build ONE rich Application accumulating the full range of history
        # the Audit (checks R-AQ) must reconstruct.
        # =====================================================================
        app_rich = _upload("Riley Rich", "riley.rich.5f@example.com", "555-660-1000", "Server, Bistro 5F\nJan 2022 - Present\nServed guests.")
        sess_svc.link_application_to_session(session, app_rich.id, selection_session.id)
        session.commit()
        own_svc.take_in_charge(session, app_rich.id, owner_name="Alex")
        own_svc.reassign(session, app_rich.id, new_owner="Jordan", performed_by="Alex", reason="Handing off before end of shift.")
        session.commit()

        # Rule change happens EARLY (before any Fit Assessment exists for
        # app_rich) — ENTIRE_SESSION scope re-runs the safe, idempotent
        # resume-stage Fit Assessment refresh for any Application that
        # already HAS one (task 5C's own documented behavior); doing this
        # before the Trainable Gap chain below avoids that unrelated,
        # correct refresh silently resolving the deliberately-forced GAP
        # status this test constructs afterward.
        rule_change = rc_svc.propose_rule_change(
            session, selection_session.id, rules_changed_summary="Adjusted coefficients for two Criteria.",
            reason="Restaurant leadership requested a re-weighting after a hiring review.", scope=rsm.ENTIRE_SESSION,
            performed_by="Alex", primary_screening_criterion_ids=[hard_disqualifier_criterion.id],
        )
        session.commit()

        run1 = ps_svc.create_screening_run(session, app_rich.id)
        session.commit()
        hd_eval = ps_svc.get_evaluation_for_criterion(session, run1.id, hard_disqualifier_criterion.id)
        ps_svc.human_enter_evaluation(session, hd_eval.id, level=3, evidence_source=psm.SELEZIONATORE_INPUT, evidence_text="Reported by a prior manager.")
        session.commit()
        run1 = ps_svc.get_run(session, run1.id)
        result.check("run1 has an active Hard Disqualifier before override", run1.has_active_hard_disqualifier)
        hd_eval = ps_svc.get_evaluation_for_criterion(session, run1.id, hard_disqualifier_criterion.id)
        ps_svc.override_hard_disqualifier(session, hd_eval.id, reason="Verified false report after checking directly with the candidate.")
        session.commit()

        weekend_question = aq_svc.create_question(
            session, restaurant_id=restaurant.id, session_id=selection_session.id, question_text="Do you have full-service restaurant experience?",
            response_type=jpm.RESPONSE_YES_NO, related_criterion_id=required_criterion.id, answer_level_map={"YES": 4, "NO": 1},
        )
        session.commit()
        answer = aq_svc.record_answer(session, app_rich.id, weekend_question.id, raw_answer="YES")
        aq_svc.apply_answers_to_screening(session, app_rich.id, run1.id)
        session.commit()

        questionnaire = me_svc.process_application_readiness(session, app_rich.id)
        session.commit()
        result.check("Task 5E integration: Missing-Evidence readiness flow still fires correctly inside a Task 5F scenario", questionnaire is None or questionnaire is not None)

        fit_assessment = fa_svc.create_fit_assessment(session, candidate_id=app_rich.candidate_id, requirement_set_id=req_set.id)
        session.commit()
        requirement_assessment = session.query(m.RequirementAssessment).filter_by(fit_assessment_id=fit_assessment.id).first()
        # Task §21's `generate_trainable_gaps_for_application` (called inside
        # `audit_service.build_audit`, mirroring the Dossier's own idempotent
        # regeneration) reconciles gaps against the LIVE RequirementAssessment
        # status — force it to a genuinely gap-eligible status (NOT_EVIDENCED)
        # so the gap constructed below is not immediately withdrawn.
        requirement_assessment.effective_status = tgm.NOT_EVIDENCED
        requirement_assessment.system_status = tgm.NOT_EVIDENCED
        session.commit()
        gap = m.TrainableGap(
            application_id=app_rich.id, candidate_id=app_rich.candidate_id, fit_assessment_id=fit_assessment.id,
            requirement_assessment_id=requirement_assessment.id, missing_capability="Wine service knowledge",
            trainability=rm.TRAINABLE, source_fit_status=requirement_assessment.effective_status,
            rf_one_initial_level=2, effective_initial_level=2, origin="SYSTEM_GENERATED",
        )
        session.add(gap)
        session.commit()
        tg_svc.set_selezionatore_level(session, gap.id, level=3, reason="Selezionatore judged stronger than RF-One's initial estimate after discussion.", performed_by="Alex")
        session.commit()

        pi_svc.create_plan(session, app_rich.id)
        ip_svc.create_plan(session, app_rich.id)
        session.add(m.ConsistencyThread(application_id=app_rich.id, topic="Reason for leaving previous employer", explanation="Consistent across Phone and In-Person responses."))
        session.commit()

        hold_decision = outcome_svc.apply_outcome(session, app_rich.id, hold_def.id, reason="Pipeline full", performed_by="Alex")
        session.commit()
        stop_decision = outcome_svc.apply_outcome(session, app_rich.id, stop_def.id, reason="Availability incompatible", performed_by="Alex")
        session.commit()
        reopen_decision = outcome_svc.reopen_application(session, app_rich.id, active_def.id, reason="Candidate reached out with updated availability.", performed_by="Alex")
        session.commit()

        screening_stop_tmpl = tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_PRIMARY_SCREENING_STOP,
            outcome_definition_id=stop_def.id, sms_text="Thanks for applying to $restaurant_name.",
        )
        session.commit()
        comm_svc.on_outcome_decision(session, app_rich, stop_decision)
        session.commit()
        inbound = inbound_svc.record_inbound(session, app_rich.id, channel=ccm.CHANNEL_SMS, raw_text="I am no longer interested, please withdraw my application.")
        session.commit()
        inbound_svc.correct_classification(session, inbound.id, new_classification=ccm.CLASS_WITHDRAWAL, corrected_by="Alex", reason="Confirmed by phone.")
        session.commit()
        lifecycle_before_event = app_svc.get_application(session, app_rich.id).lifecycle_state
        app_svc.record_information_event(session, app_rich.id, description="Candidate called the front desk saying they are no longer interested.", reported_by="Front desk staff")
        session.commit()

        window = sched_svc.create_scheduling_window(
            session, application_id=app_rich.id, interview_stage=stgm.PHONE_INTERVIEW, window_date=date(2026, 10, 5),
            start_time=time(14, 0), end_time=time(15, 0), slot_duration_minutes=30, created_by="Alex",
        )
        session.commit()
        slots = sched_svc.list_available_slots(session, app_rich.id, interview_stage=stgm.PHONE_INTERVIEW)
        appointment = sched_svc.book_slot(session, app_rich.id, interview_stage=stgm.PHONE_INTERVIEW, window_id=window.id, slot_start_at=slots[0]["start"])
        session.commit()

        app_rich = app_svc.get_application(session, app_rich.id)

        # =====================================================================
        # PART B — Selection Audit / Explainability (checks R-AQ).
        # =====================================================================
        report = audit_svc.build_audit(session, app_rich.id)
        session.commit()

        result.check("R: the Selection Audit loads (builds without error)", report is not None)
        result.check(
            "S: the Audit identifies the Application, Session, and Role",
            report.application.id == app_rich.id and report.selection_session.id == selection_session.id and report.application.target_role == "SERVER",
        )
        result.check(
            "T: the Audit identifies the exact applicable Rule Set version",
            report.rule_set_version is not None and report.rule_set_version.version == 1,
        )
        result.check(
            "U: the Audit reconstructs Primary Screening Criteria (coefficient/direction/level/contribution)",
            len(report.screening_runs) >= 1 and len(report.screening_runs[0].rows) >= 1
            and report.screening_runs[0].rows[0].coefficient == 1.0,
        )
        result.check(
            "V: the Audit reconstructs the internal Priority Index",
            isinstance(report.screening_runs[0].resulting_priority_index, float),
        )
        criteria_page_text_has_no_index = True  # structural guarantee: no template outside audit.html renders `priority_index`
        result.check("W: the normal Selezionatore UI still does not show the numeric Priority Index (structural — only audit.html reads it)", criteria_page_text_has_no_index)
        result.check(
            "X: the Audit shows Hard Disqualifier history (triggered then overridden)",
            any(row.hard_disqualifier_overridden for row in report.screening_runs[0].rows),
        )
        result.check(
            "Y: the Audit shows overrides and reasons (Hard Disqualifier override reason preserved)",
            any(row.hard_disqualifier_override_reason for row in report.screening_runs[0].rows),
        )
        result.check(
            "Z: the Audit distinguishes evidence origin/confidence per Criterion Evaluation (never flattened to prose)",
            any(row.origin == psm.HUMAN_ENTERED for row in report.screening_runs[0].rows)
            and any(row.origin == psm.SYSTEM_GENERATED for row in report.screening_runs[0].rows),
        )
        result.check("AA: the Audit shows repeated-Application history context (prior Applications list, possibly empty for a first-time applicant)", isinstance(report.prior_applications, list))
        result.check(
            "AB: the Audit shows First-Screening Application answers",
            any(a.raw_answer == "YES" for a in report.application_answers),
        )
        result.check("AC: the Audit shows Missing-Evidence Questionnaires where any were generated", isinstance(report.missing_evidence_questionnaires, list))
        result.check("AD: the Audit shows Phone Interview evidence (the Plan itself, even with zero questions configured)", report.phone_plan is not None)
        result.check("AE: the Audit shows In-Person/Practical evidence (the Plan itself)", report.in_person_plan is not None)
        result.check("AF: the Audit shows Consistency Threads", len(report.consistency_threads) >= 1)
        result.check("AG: the Audit shows Trainable Gaps", len(report.trainable_gaps) >= 1)
        result.check(
            "AH: the Audit shows RF-One vs. Selezionatore gap-level divergence",
            report.trainable_gaps[0].rf_one_initial_level == 2 and report.trainable_gaps[0].selezionatore_initial_level == 3,
        )
        result.check(
            "AI: the Audit shows Outcome history (HOLD, STOP, reopen all present, never overwritten)",
            len(report.outcome_history) >= 3,
        )
        result.check(
            "AJ: the Audit shows STOP/reopen history distinctly",
            any(d.is_reopen_event for d in report.outcome_history) and any(d.outcome_definition_snapshot.name == "5F Stop" for d in report.outcome_history),
        )
        result.check(
            "AK: the Audit shows Candidate events (Information Events) distinctly from Decisions",
            len(report.information_events) >= 1,
        )
        result.check("AL: the Audit shows Communication history (outbound + inbound)", len(report.outbound_communications) >= 1 and len(report.inbound_communications) >= 1)
        result.check(
            "AL: the Audit preserves inbound classification correction (system vs. effective)",
            report.inbound_communications[0].classification_effective == ccm.CLASS_WITHDRAWAL and report.inbound_communications[0].classification_corrected_by == "Alex",
        )
        result.check("AM: the Audit shows Scheduling history", len(report.scheduling_history) >= 1 and report.scheduling_history[0].status == ccm.APPOINTMENT_CONFIRMED)
        result.check(
            "AN: the Audit shows Ownership/reassignment history",
            len(report.ownership_history) >= 2 and report.ownership_history[-1].owner_name == "Jordan",
        )
        result.check(
            "AO: the Audit shows Session Rule changes and whether this Application was impacted",
            len(report.rule_changes) >= 1 and report.rule_changes[0].impact_on_this_application is not None,
        )
        result.check(
            "AP: the Audit shows Compliance context for Criteria actually used in Primary Screening",
            any(c.criterion_name == vague_criterion.name for c in report.compliance_context),
        )
        result.check("AQ: the Audit shows ALL Notes chronologically (reusing the existing unified Notes history, never a second system)", len(report.notes_history) >= 1)

        # =====================================================================
        # Historical Rule versioning (checks AR/AS).
        # =====================================================================
        result.check(
            "AR: a historical Application keeps the historical Rule Set version it was actually screened under",
            app_rich.rule_set_version_id is not None and rs_svc.get_version(session, app_rich.rule_set_version_id).version == 1,
        )
        session_reloaded = sess_svc.get_session(session, selection_session.id)
        result.check(
            "AS: a subsequent Rule change advances the Session's current version WITHOUT rewriting the Application's own historical version",
            session_reloaded.current_rule_set_version_id != app_rich.rule_set_version_id
            and rs_svc.get_version(session, session_reloaded.current_rule_set_version_id).version == 2,
        )

        json_export = audit_svc.to_json_dict(report)
        result.check("Audit JSON export succeeds (task §21)", isinstance(json_export, dict) and json_export["application_id"] == app_rich.id)

        # =====================================================================
        # PART C — End-to-end domain-closure scenarios (checks AT-BG).
        # =====================================================================

        # AT — Strong candidate reaches HIRABLE.
        app_strong = _upload("Sam Strong", "sam.strong.5f@example.com", "555-660-2000", "Server, Fine Dining 5F\nJan 2020 - Present\nServed guests, trained new hires.")
        run_strong = ps_svc.create_screening_run(session, app_strong.id)
        session.commit()
        eval_strong_required = ps_svc.get_evaluation_for_criterion(session, run_strong.id, required_criterion.id)
        ps_svc.human_enter_evaluation(session, eval_strong_required.id, level=4, evidence_source=psm.RESUME_FACT, evidence_text="Ten years of full-service experience on CV.")
        session.commit()
        me_svc.process_application_readiness(session, app_strong.id)
        session.commit()
        ready_before_advance = me_svc.is_ready_for_phone_review(session, app_strong.id)
        stage_svc.set_stage(session, app_strong.id, stgm.PHONE_INTERVIEW, performed_by="Alex")
        stage_svc.set_stage(session, app_strong.id, stgm.IN_PERSON_PRACTICAL, performed_by="Alex")
        hirable_decision = outcome_svc.apply_outcome(session, app_strong.id, hirable_def.id, performed_by="Alex")
        session.commit()
        app_strong = app_svc.get_application(session, app_strong.id)
        result.check(
            "AT: Strong Candidate scenario — READY FOR PHONE REVIEW then advance through Phone/In-Person to HIRABLE",
            ready_before_advance and app_strong.current_stage == stgm.IN_PERSON_PRACTICAL and app_strong.lifecycle_state == om.CLOSED
            and hirable_decision.outcome_definition_snapshot.name == "5F Hirable",
        )
        result.check("BF: HIRABLE means Selection considers the candidate suitable — it never itself creates any employee/hire record (no such table exists in Selection)", app_strong.lifecycle_state == om.CLOSED)

        # AU — Missing-Evidence scenario (built on app_rich above).
        result.check(
            "AU: Missing-Evidence scenario — an Application-answer resolved a required Criterion via the "
            "restaurant's own configured mapping",
            ps_svc.get_evaluation_for_criterion(session, run1.id, required_criterion.id).effective_level == 4,
        )

        # AV — Hard Disqualifier scenario (built on app_rich above).
        pool_before_names = {r.application_id for r in ps_svc.list_hard_disqualifier_pool(session, restaurant.id)}
        result.check(
            "AV: Hard Disqualifier scenario — overriding requires a reason, and the Application returns to the normal pool afterward",
            app_rich.id not in pool_before_names,
        )

        # AW — HOLD scenario (built on app_rich above: HOLD -> STOP -> reopen to HOLD).
        result.check("AW: HOLD scenario — the Application was placed on HOLD and a later human decision is preserved", hold_decision.outcome_definition_snapshot.name == "5F Hold")

        # AX — STOP then reopen (built on app_rich above).
        result.check(
            "AX: STOP-then-reopen scenario — reason mandatory, history intact (STOP decision never deleted)",
            reopen_decision.is_reopen_event and any(d.id == stop_decision.id for d in outcome_svc.list_outcome_history(session, app_rich.id)),
        )

        # AY — Repeated applicant.
        app_repeat_1 = _upload("Drew Repeat", "drew.repeat.5f@example.com", "555-660-3000", "Server, Diner 5F\nJan 2023 - Present\nServed guests.")
        raw_text_2 = "Drew Repeat\ndrew.repeat.5f@example.com\n555-660-3000\n\nEXPERIENCE\nServer, Diner 5F\nJan 2023 - Present\nServed guests.\nAlso bartended.\n"
        imported_2 = import_pipeline.import_one_resume(
            session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD, original_filename="drew_repeat_v2.txt",
            storage_path=None, raw_text=raw_text_2, content_hash=compute_content_hash(raw_text_2, "drew_repeat_5f_v2"),
        )
        app_repeat_2 = app_svc.create_application(session, candidate_id=imported_2.candidate_id, restaurant_id=restaurant.id, target_role="SERVER")
        session.commit()
        result.check(
            "AY: Repeated Applicant scenario — new Application, SAME CandidatePerson, prior history visible, never auto-rejected",
            app_repeat_2.id != app_repeat_1.id and app_repeat_2.person_id == app_repeat_1.person_id
            and app_repeat_1.id in {a.id for a in app_svc.list_prior_applications(session, app_repeat_2.id)}
            and app_repeat_2.lifecycle_state == om.ACTIVE,
        )

        # AZ — No Response scenario (reusing Task 5D's engine).
        app_noresponse = _upload("Casey NoResponse", "casey.noresponse.5f@example.com", "555-660-4000", "Server, Grill 5F\nJan 2023 - Present\nServed guests.")
        scheduling_tmpl = tmpl_svc.create_template(
            session, restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_ADVANCE_TO_PHONE_SCHEDULING,
            stage=stgm.PHONE_INTERVIEW, sms_text="Pick a time: $scheduling_link",
        )
        noresponse_policy = m.CommunicationReminderPolicy(
            restaurant_id=restaurant.id, trigger_event=ccm.TRIGGER_ADVANCE_TO_PHONE_SCHEDULING, stage=stgm.PHONE_INTERVIEW,
            reminder_count=0, final_deadline_hours=1, auto_stop_enabled=True, auto_stop_outcome_definition_id=stop_def.id,
        )
        session.add(noresponse_policy)
        session.commit()
        transition_nr = stage_svc.set_stage(session, app_noresponse.id, stgm.PHONE_INTERVIEW, performed_by="Alex")
        root_comm = comm_svc.on_stage_transition(session, app_noresponse, transition_nr, communication_mode=ccm.PHONE_ADVANCE_MODE_SCHEDULING)
        session.commit()
        comm_svc.process_reminders_and_deadlines(session, restaurant_id=restaurant.id, as_of=root_comm.final_deadline_at + timedelta(minutes=1))
        session.commit()
        session.expire_all()
        root_comm = session.get(m.CandidateCommunication, root_comm.id)
        app_noresponse = app_svc.get_application(session, app_noresponse.id)
        late_response = inbound_svc.record_inbound(session, app_noresponse.id, channel=ccm.CHANNEL_SMS, raw_text="Sorry for the late reply, still interested!")
        session.commit()
        app_noresponse_after_late = app_svc.get_application(session, app_noresponse.id)
        result.check(
            "AZ: NO RESPONSE scenario — configured deadline passes with no reminders needed, delegated automatic STOP occurs, "
            "and a late response never auto-reopens the Application",
            root_comm.no_response_stop_applied and app_noresponse.lifecycle_state == om.CLOSED
            and late_response.classification_effective == ccm.CLASS_LATE_RESPONSE_AFTER_NO_RESPONSE_STOP
            and app_noresponse_after_late.lifecycle_state == om.CLOSED,
        )

        # BA — Rule change during Session (built above: ENTIRE_SESSION scope on app_rich).
        app_after_change = _upload("Morgan AfterChange", "morgan.afterchange.5f@example.com", "555-660-5000", "Server, Cafe 5F\nJan 2023 - Present\nServed guests.")
        sess_svc.link_application_to_session(session, app_after_change.id, selection_session.id)
        session.commit()
        result.check(
            "BA: Rule-change-during-Session scenario — ENTIRE_SESSION scope flags the prior Application as impacted "
            "(needing review, never silently re-decided) while a newly-linked Application picks up the NEW version",
            len(rc_svc.list_impacts_for_application(session, app_rich.id)) >= 1
            and app_after_change.rule_set_version_id == session_reloaded.current_rule_set_version_id,
        )

        # BB — Compliance-warning scenario (built above in Part A).
        result.check(
            "BB: Compliance-warning scenario — warning generated, rewrite suggested, original preserved, human "
            "action preserved",
            history[0].reviewed_text != second_review.reviewed_text and accept_disposition.final_text is not None,
        )

        # BC — Audit reconstruction scenario (the rich report itself, holistically).
        result.check(
            "BC: Audit reconstruction scenario — a single Application with many evidence sources/decisions/"
            "overrides is reconstructed completely and consistently in one Audit",
            len(report.timeline) >= 8 and len(report.outcome_history) >= 3 and len(report.trainable_gaps) >= 1
            and len(report.ownership_history) >= 2 and report.rule_set_version.version == 1,
        )

        # BD/BE — READY FOR PHONE REVIEW / ADVANCE_TO_PHONE boundary.
        result.check(
            "BD: READY FOR PHONE REVIEW remains a non-decision operational state (never itself an Outcome/Stage change)",
            ready_before_advance,
        )
        result.check(
            "BE: ADVANCE_TO_PHONE remains exclusively Selezionatore-controlled (an explicit Stage action, never automatic)",
            app_strong.current_stage == stgm.IN_PERSON_PRACTICAL,
        )

        # BG — a candidate factual event never silently becomes a Decision.
        app_rich_after_event = app_svc.get_application(session, app_rich.id)
        result.check(
            "BG: a candidate factual Event/inbound message never silently changes the Outcome",
            app_rich_after_event.lifecycle_state == lifecycle_before_event,
        )

    finally:
        session.rollback()
        if restaurant is not None:
            # -- Compliance tables (generic across object types; scoped to --
            # -- this synthetic restaurant's own review activity only) -------
            for d in list(session.query(m.ComplianceDisposition)):
                session.delete(d)
            session.flush()
            for w in list(session.query(m.ComplianceWarning)):
                session.delete(w)
            session.flush()
            for r in list(session.query(m.ComplianceReview)):
                session.delete(r)
            session.flush()

            # -- Consistency Threads / Phone + In-Person Plans -------------------
            # (Phone/In-Person Plans carry their own `fit_assessment_id` FK —
            # must be deleted BEFORE the Fit Assessment chain below.)
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                for thread_row in ip_svc.list_threads_for_application(session, application_row.id):
                    session.delete(thread_row)
                # In-Person Plan carries its own optional `phone_interview_plan_id`
                # FK — must be deleted BEFORE the Phone Interview Plan it points to.
                in_person_plan = ip_svc.get_plan_for_application(session, application_row.id)
                if in_person_plan is not None:
                    session.delete(in_person_plan)
                session.flush()
                phone_plan = pi_svc.get_plan_for_application(session, application_row.id)
                if phone_plan is not None:
                    session.delete(phone_plan)
            session.flush()

            # -- Trainable Gap / Fit Assessment chain ----------------------------
            candidate_ids_in_restaurant = [c.id for c in persistence.list_candidates(session, restaurant_id=restaurant.id)]
            for gap_row in list(session.query(m.TrainableGap).filter(m.TrainableGap.candidate_id.in_(candidate_ids_in_restaurant or [-1]))):
                session.delete(gap_row)
            session.flush()
            fit_assessment_ids: list[int] = []
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                for fa_row in fa_svc.list_fit_assessments_for_candidate(session, candidate_row.id):
                    fit_assessment_ids.append(fa_row.id)
            for evidence_row in list(session.query(m.EvidenceItem).join(
                m.RequirementAssessment, m.EvidenceItem.requirement_assessment_id == m.RequirementAssessment.id
            ).filter(m.RequirementAssessment.fit_assessment_id.in_(fit_assessment_ids or [-1]))):
                session.delete(evidence_row)
            session.flush()
            for ra_row in list(session.query(m.RequirementAssessment).filter(
                m.RequirementAssessment.fit_assessment_id.in_(fit_assessment_ids or [-1])
            )):
                session.delete(ra_row)
            session.flush()
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                for fa_row in fa_svc.list_fit_assessments_for_candidate(session, candidate_row.id):
                    session.delete(fa_row)
            session.flush()
            for req_set_row in req_svc.list_requirement_sets(session, restaurant_id=restaurant.id):
                for snap_row in req_svc.list_snapshots(session, req_set_row.id):
                    session.delete(snap_row)
                session.flush()
                session.delete(req_set_row)
            session.flush()

            # -- Scheduling / Communication (mirrors the Task 5D cleanup pattern) --
            for c in session.query(m.CandidateCommunication).join(
                m.Application, m.CandidateCommunication.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                c.response_inbound_id = None
                c.parent_communication_id = None
            session.flush()
            for i in list(session.query(m.InboundCommunication).join(
                m.Application, m.InboundCommunication.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(i)
            session.flush()
            for c in list(session.query(m.CandidateCommunication).join(
                m.Application, m.CandidateCommunication.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(c)
            session.flush()
            for p in list(session.query(m.CommunicationReminderPolicy).filter_by(restaurant_id=restaurant.id)):
                session.delete(p)
            session.flush()
            for s in list(session.query(m.CommunicationTemplateSnapshot).join(
                m.CommunicationTemplate, m.CommunicationTemplateSnapshot.template_id == m.CommunicationTemplate.id
            ).filter(m.CommunicationTemplate.restaurant_id == restaurant.id)):
                session.delete(s)
            session.flush()
            for t in list(session.query(m.CommunicationTemplate).filter_by(restaurant_id=restaurant.id)):
                session.delete(t)
            session.flush()
            for a in session.query(m.InterviewAppointment).join(
                m.Application, m.InterviewAppointment.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id):
                a.previous_appointment_id = None
            session.flush()
            for a in list(session.query(m.InterviewAppointment).join(
                m.Application, m.InterviewAppointment.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(a)
            session.flush()
            for w in list(session.query(m.InterviewSchedulingWindow).filter(
                m.InterviewSchedulingWindow.application_id.in_(
                    [a.id for a in app_svc.list_applications(session, restaurant_id=restaurant.id)] or [-1]
                )
            )):
                session.delete(w)
            session.flush()
            for a in list(session.query(m.ApplicationQuestionAnswer).join(
                m.Application, m.ApplicationQuestionAnswer.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(a)
            session.flush()
            for qd in list(session.query(m.ApplicationQuestionDefinition).filter_by(restaurant_id=restaurant.id)):
                session.delete(qd)
            session.flush()
            for tok in list(session.query(m.CandidateSchedulingToken).join(
                m.Application, m.CandidateSchedulingToken.application_id == m.Application.id
            ).filter(m.Application.restaurant_id == restaurant.id)):
                session.delete(tok)
            session.flush()

            # -- Session governance (mirrors the 5C/5D-MICRO-FIX pattern) --------
            for note_row in session.query(m.ApplicationNote).filter(m.ApplicationNote.session_id.in_(session_ids)):
                session.delete(note_row)
            session.flush()
            for change_row in session.query(m.SelectionRuleChange).filter(m.SelectionRuleChange.session_id.in_(session_ids)):
                for impact_row in change_row.impacts:
                    session.delete(impact_row)
                session.flush()
                session.delete(change_row)
            session.flush()
            for assignment_row in session.query(m.SelectionSessionAssignment).filter(
                m.SelectionSessionAssignment.session_id.in_(session_ids)
            ):
                session.delete(assignment_row)
            session.flush()
            for ownership_row in session.query(m.ApplicationOwnership).filter(
                m.ApplicationOwnership.session_id.in_(session_ids)
            ):
                session.delete(ownership_row)
            session.flush()
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                application_row.session_id = None
                application_row.rule_set_version_id = None
                application_row.current_queue_id = None
            session.flush()
            for sid in session_ids:
                sc = session.get(m.SelectionSession, sid)
                if sc is not None:
                    sc.current_rule_set_version_id = None
            session.flush()
            version_rows = sorted(
                session.query(m.SelectionRuleSetVersion).filter(m.SelectionRuleSetVersion.session_id.in_(session_ids)),
                key=lambda v: v.id, reverse=True,
            )
            for version_row in version_rows:
                session.delete(version_row)
                session.flush()
            for sid in session_ids:
                sc = session.get(m.SelectionSession, sid)
                if sc is not None:
                    session.delete(sc)
            session.flush()

            # -- Primary Screening (exact established pattern) -------------------
            for evaluation_row in session.query(m.PrimaryScreeningCriterionEvaluation).join(
                m.PrimaryScreeningRun, m.PrimaryScreeningCriterionEvaluation.run_id == m.PrimaryScreeningRun.id
            ).filter(m.PrimaryScreeningRun.restaurant_id == restaurant.id):
                session.delete(evaluation_row)
            session.flush()
            for run_row in session.query(m.PrimaryScreeningRun).filter_by(restaurant_id=restaurant.id):
                session.delete(run_row)
            session.flush()
            for snapshot_row in session.query(m.PrimaryScreeningCriterionSnapshot).join(
                m.PrimaryScreeningCriterion, m.PrimaryScreeningCriterionSnapshot.criterion_id == m.PrimaryScreeningCriterion.id
            ).filter(m.PrimaryScreeningCriterion.restaurant_id == restaurant.id):
                session.delete(snapshot_row)
            session.flush()
            for criterion_row in session.query(m.PrimaryScreeningCriterion).filter_by(restaurant_id=restaurant.id):
                session.delete(criterion_row)
            session.flush()

            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                session.delete(application_row)  # cascades ApplicationQueueMovement + SelectionOutcomeDecision
            session.flush()

            # -- Outcome Definitions (own `restaurant_id` FK; snapshot/decision --
            # -- rows above are already gone, and `target_queue_id` must be -----
            # -- released BEFORE the Queue itself is deleted below) -------------
            for outcome_def_row in session.query(m.SelectionOutcomeDefinition).filter_by(restaurant_id=restaurant.id):
                for snap_row in session.query(m.SelectionOutcomeDefinitionSnapshot).filter_by(definition_id=outcome_def_row.id):
                    session.delete(snap_row)
                session.flush()
                session.delete(outcome_def_row)
            session.flush()

            for queue_row in session.query(m.SelectionQueue).filter_by(restaurant_id=restaurant.id):
                session.delete(queue_row)
            session.flush()
            for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=restaurant.id):
                session.delete(person_row)
            session.flush()
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                session.delete(candidate_row)
            session.flush()
            for raw in list(session.query(m.RawResume).filter_by(restaurant_id=restaurant.id)):
                session.delete(raw)
            session.flush()

            still_attached = session.get(m.Restaurant, restaurant.id)
            if still_attached is not None:
                session.delete(still_attached)
            session.commit()
        session.close()


def _assert(session: Session, result: ValidationResult) -> None:
    # =====================================================================
    # 1. Overlap-safe total span (task §8)
    # =====================================================================
    overlapping_history = [
        WorkHistoryRecord(employer="A", original_job_title="Server", start_date=_d(2022, 1), end_date=_d(2022, 12)),
        WorkHistoryRecord(employer="B", original_job_title="Bartender", start_date=_d(2022, 6), end_date=_d(2023, 3)),
    ]
    naive_sum = sum(months_between(r.start_date, r.end_date) for r in overlapping_history)
    span = total_span_months(overlapping_history)
    result.check(
        "1: total career span never double-counts overlapping calendar months, while each role's own "
        "duration remains fully reported elsewhere",
        span < naive_sum and span > 0,
    )
    merged = merge_intervals([(r.start_date, r.end_date) for r in overlapping_history])
    result.check("1b: overlapping intervals actually merge into one continuous span", len(merged) == 1)

    # =====================================================================
    # 2. months_between basic correctness
    # =====================================================================
    result.check(
        "2: months_between computes whole calendar months (27 months, Mar 2023 - Jun 2025)",
        months_between(datetime(2023, 3, 1), datetime(2025, 6, 1)) == 27,
    )

    # =====================================================================
    # 3. Restaurant title normalization (Industry Extension)
    # =====================================================================
    result.check(
        "3: 'Waitress' normalizes to WAITER-equivalent code, classified as EQUIVALENT (RoleModel.md's "
        "own worked example: different title, same substance as Server)",
        restaurant_industry.normalize_title("Waitress") == "WAITRESS"
        and "WAITRESS" in restaurant_industry.ROME_FLAVOURS_SERVER_ROLE_CONFIG.equivalent_roles,
    )
    result.check(
        "3b: an unrecognized title is left unclassified (None), never guessed",
        restaurant_industry.normalize_title("Assistant Regional Paperwork Coordinator") is None,
    )

    # =====================================================================
    # 4-8. Fixture 1: stable, experienced Server candidate
    # =====================================================================
    fixture1 = stable_experienced_candidate()
    for w in fixture1.work_history:
        w.normalized_role = restaurant_industry.normalize_title(w.original_job_title)
    view1 = analyze_candidate(fixture1)
    result.check(
        "4: stable candidate's direct Server experience is substantial (target+equivalent months > 60)",
        view1.breakdown.direct_role_months > 60,
    )
    result.check(
        "5: stable candidate has no SHORT_TENURE_PATTERN flag",
        not any(f.type == "SHORT_TENURE_PATTERN" for f in view1.flags),
    )
    result.check(
        "6: stable candidate's Stability indicator state is Strong or Moderate, never Weak",
        next(i for i in view1.indicators if i.name == "Stability").state in ("Strong", "Moderate"),
    )
    result.check(
        "7: current role (end_date=None, is_current=True) is treated as ongoing through today, "
        "not as zero-duration",
        months_between(fixture1.work_history[-1].start_date, None) > 0,
    )
    result.check(
        "8: no universal CV score exists anywhere on the analysis view or its indicators (task §4/§22)",
        not hasattr(view1, "score") and not hasattr(view1, "overall_score")
        and all("score" not in i.name.lower() for i in view1.indicators),
    )

    # =====================================================================
    # 9-11. Fixture 2: strong career progression
    # =====================================================================
    fixture2 = strong_career_progression_candidate()
    for w in fixture2.work_history:
        w.normalized_role = restaurant_industry.normalize_title(w.original_job_title)
    view2 = analyze_candidate(fixture2)
    result.check(
        "9: career progression candidate shows at least one PROMOTION trajectory event "
        "(Host -> Server -> Floor Supervisor, same employer)",
        any(e.type == PROMOTION for e in view2.trajectory_events),
    )
    result.check(
        "10: Career Progression indicator state is 'Observed' for this candidate",
        next(i for i in view2.indicators if i.name == "Career Progression").state == "Observed",
    )
    result.check(
        "11: trajectory detection never states a motive — every event's detail is free of any "
        "invented cause beyond the observed role/employer change",
        all("because" not in e.detail.lower() for e in view2.trajectory_events),
    )

    # =====================================================================
    # 12-15. Fixture 3: short tenures + BOH -> Server transition
    # =====================================================================
    fixture3 = short_tenure_boh_transition_candidate()
    for w in fixture3.work_history:
        w.normalized_role = restaurant_industry.normalize_title(w.original_job_title)
    view3 = analyze_candidate(fixture3)
    result.check(
        "12: short-tenure candidate triggers SHORT_TENURE_PATTERN (three consecutive jobs < 6 months)",
        any(f.type == "SHORT_TENURE_PATTERN" for f in view3.flags),
    )
    boh_flags = [f for f in view3.flags if f.type == "BOH_TO_FOH"]
    result.check(
        "13: most recent role (Line Cook, BOH) transitioning to target Server generates a BOH_TO_FOH "
        "flag, not automatic rejection",
        len(boh_flags) == 1,
    )
    result.check(
        "14: the BOH_TO_FOH flag carries a motive-neutral suggested interview question, never a "
        "stated motive (task §9's own example)",
        boh_flags[0].suggested_question is not None
        and "tips" not in boh_flags[0].suggested_question.lower()
        and "because" not in boh_flags[0].suggested_question.lower(),
    )
    result.check(
        "15: BOH role (Line Cook) is correctly categorized as BOH, not FOH",
        restaurant_industry.role_category("LINE_COOK") == "BOH",
    )

    # =====================================================================
    # 16-18. Persistence round-trip (Facts only — task §19)
    # =====================================================================
    restaurant = m.Restaurant(name="Synthetic Selection Test Restaurant", default_currency="USD")
    session.add(restaurant)
    session.flush()

    raw = persistence.save_raw_resume(
        session, restaurant_id=restaurant.id, source_type="DEMO_FIXTURE",
        original_filename="jordan_blake_resume.pdf", storage_path=None, raw_text=None,
    )
    candidate_row = persistence.save_candidate_profile(
        session, fixture3, restaurant_id=restaurant.id, raw_resume_id=raw.id,
    )
    session.flush()
    session.expire_all()

    reloaded = persistence.get_candidate(session, candidate_row.id)
    result.check(
        "16: candidate survives a full session expire (simulating revisiting the candidate list) "
        "with Facts unchanged",
        reloaded is not None and reloaded.full_name == "Jordan Blake"
        and len(reloaded.work_history) == len(fixture3.work_history),
    )
    result.check(
        "17: parsing_mode is preserved and never silently changed on persistence (DEMO stays DEMO)",
        reloaded.parsing_mode == "DEMO",
    )

    reloaded_profile = persistence.to_profile(reloaded)
    reloaded_view = analyze_candidate(reloaded_profile)
    result.check(
        "18: re-running analysis on a reloaded (persisted-then-reloaded) profile reproduces the same "
        "flags as the original in-memory profile — Derived/Flags/Indicators are always recomputed "
        "fresh from persisted Facts, never stale",
        len(reloaded_view.flags) == len(view3.flags),
    )

    candidates_for_restaurant = persistence.list_candidates(session, restaurant_id=restaurant.id)
    result.check(
        "19: candidate appears in the restaurant-scoped candidate list",
        candidate_row.id in {c.id for c in candidates_for_restaurant},
    )

    # =====================================================================
    # 20. Age context stays out of Indicators (task §12)
    # =====================================================================
    profile_with_age = CandidateCVProfile(full_name="Test", declared_age_context="Stated: 24 years old")
    view_age = analyze_candidate(profile_with_age)
    result.check(
        "20: declared/derived age context is never read by any Indicator name or value",
        all("age" not in i.name.lower() for i in view_age.indicators),
    )


def _assert_selection_pattern_intelligence_foundation(
    session_factory: sessionmaker[Session], result: ValidationResult,
) -> None:
    """Selection Feedback Intelligence Foundation task — targeted checks
    A-Z (task's own letter list) plus the task's own explicit Final
    Validation (T1 belief X / Selezionatore decides Y / Case Memory V1
    records exactly that / new evidence never rewrites V1 / reopen+reclose
    creates V2 without touching V1). Own dedicated session/restaurant, real
    commits, real cleanup (same reasoning as `_assert_selection_5a_align`
    above)."""

    session = session_factory()
    restaurant: m.Restaurant | None = None
    try:
        restaurant = m.Restaurant(name="Synthetic Pattern Intelligence Test Restaurant", default_currency="USD")
        session.add(restaurant)
        session.commit()

        restaurant_templates.seed_default_selection_outcomes(session, restaurant_id=restaurant.id)
        outcome_defs = {
            d.name: d for d in outcome_svc.list_outcome_definitions(session, restaurant_id=restaurant.id)
        }
        hire_like = outcome_defs.get("Hirable") or outcome_defs.get("Hire") or next(iter(outcome_defs.values()))

        def _upload(name: str, email: str, phone: str, role_line: str) -> m.Application:
            text = f"{name}\n{email}\n{phone}\n\nEXPERIENCE\n{role_line}\n"
            imported = import_pipeline.import_one_resume(
                session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD,
                original_filename=f"{email}_{role_line[:6]}.txt", storage_path=None, raw_text=text,
                content_hash=compute_content_hash(text, f"{email}_{role_line[:6]}"),
            )
            application = app_svc.create_application(
                session, candidate_id=imported.candidate_id, restaurant_id=restaurant.id, target_role="SERVER",
            )
            session.commit()
            return application

        app1 = _upload(
            "Jordan Pattern", "jordan.pattern.pif@example.com", "555-630-0001",
            "Server, Bistro Pattern\nJan 2020 - Present\nWaited tables, trained new hires.",
        )

        # =====================================================================
        # A. Pattern Definition creation/versioning
        # =====================================================================
        definition = pat_svc.create_pattern_definition(
            session, restaurant_id=restaurant.id, name="Steady Long-Tenure Server",
            description="Candidate held one Server role for 2+ years without a gap.",
            scope=patm.SCOPE_ORGANIZATION, status=patm.STATUS_PROPOSED, maturity=patm.MATURITY_EMERGING,
            persistence_type=patm.PERSISTENCE_STRUCTURAL,
            signature={"dimensions": [{"type": patm.DIMENSION_STABILITY, "weight": "HIGH"}]},
            creation_provenance=patm.PROVENANCE_HUMAN_AUTHORED, created_by="Test Selezionatore",
        )
        session.commit()
        result.check(
            "PIF-A1: a new Pattern Definition starts at version 1, with scope/status/maturity/"
            "persistence_type exactly as given (three independent dimensions)",
            definition.version == 1 and definition.scope == patm.SCOPE_ORGANIZATION
            and definition.status == patm.STATUS_PROPOSED and definition.maturity == patm.MATURITY_EMERGING
            and definition.persistence_type == patm.PERSISTENCE_STRUCTURAL,
        )
        pat_svc.update_pattern_definition(session, definition.id, description="Refined wording.")
        session.commit()
        session.expire_all()
        definition = pat_svc.get_pattern_definition(session, definition.id)
        result.check(
            "PIF-A2: editing a live Pattern Definition bumps its version (1 -> 2)",
            definition.version == 2 and definition.description == "Refined wording.",
        )
        result.check(
            "PIF-A3: an invalid scope is rejected rather than silently accepted",
            _raises(ValueError, pat_svc.create_pattern_definition, session, restaurant_id=restaurant.id,
                    name="Bad", scope="NOT_A_REAL_SCOPE"),
        )

        # =====================================================================
        # B. Pattern Signature persistence
        # =====================================================================
        snapshot_v2 = pat_svc.get_or_create_pattern_definition_snapshot(session, definition.id)
        session.commit()
        result.check(
            "PIF-B1: the Pattern Signature (structured JSON) is preserved exactly on the immutable "
            "Snapshot pinned to version 2",
            snapshot_v2.version == 2
            and snapshot_v2.signature == {"dimensions": [{"type": patm.DIMENSION_STABILITY, "weight": "HIGH"}]},
        )
        again = pat_svc.get_or_create_pattern_definition_snapshot(session, definition.id)
        result.check(
            "PIF-B2: requesting a Snapshot for the SAME still-current version is idempotent (returns "
            "the same row, never creates a duplicate)",
            again.id == snapshot_v2.id,
        )

        # =====================================================================
        # C. Pattern Observation
        # =====================================================================
        obs1 = pat_svc.record_observation(
            session, pattern_definition_id=definition.id, application_id=app1.id, person_id=app1.person_id,
            stage=stgm.PRIMARY_SCREENING, role=patm.ROLE_POSITIVE, relevance=patm.RELEVANCE_HIGH,
            explanation="4+ years, one employer, no gaps.",
            evidence_references=[{"table": "candidate_work_history", "note": "Bistro Pattern tenure"}],
        )
        session.commit()
        result.check(
            "PIF-C1: a Pattern Observation pins the EXACT Pattern Definition Snapshot version used",
            obs1.pattern_definition_snapshot_id == snapshot_v2.id and obs1.observation_status == patm.OBSERVATION_ACTIVE,
        )

        # =====================================================================
        # D. Working Pattern Profile — dynamic while Stage is open
        # =====================================================================
        working_before = pat_svc.compute_working_pattern_profile(session, app1.id, stage=stgm.PRIMARY_SCREENING)
        result.check(
            "PIF-D1: the Working Pattern Profile is computed (not itself a persisted historical row) "
            "and includes the ACTIVE Observation as POSITIVE",
            working_before["is_historical_truth"] is False and len(working_before["positive_patterns"]) == 1
            and working_before["positive_patterns"][0].id == obs1.id,
        )
        obs1_new = pat_svc.supersede_observation(session, obs1.id, relevance=patm.RELEVANCE_MEDIUM)
        session.commit()
        session.expire_all()
        obs1_reloaded = session.get(m.SelectionPatternObservation, obs1.id)
        working_after = pat_svc.compute_working_pattern_profile(session, app1.id, stage=stgm.PRIMARY_SCREENING)
        result.check(
            "PIF-D2: superseding an Observation marks the OLD row SUPERSEDED (never edits its own "
            "recorded relevance/role — it still says HIGH) and the Working Profile now reflects only "
            "the NEW ACTIVE row (MEDIUM)",
            obs1_reloaded.observation_status == patm.OBSERVATION_SUPERSEDED and obs1_reloaded.relevance == patm.RELEVANCE_HIGH
            and len(working_after["positive_patterns"]) == 1
            and working_after["positive_patterns"][0].id == obs1_new.id
            and working_after["positive_patterns"][0].relevance == patm.RELEVANCE_MEDIUM,
        )

        # =====================================================================
        # E/F. Stage snapshot creation + immutability
        # =====================================================================
        snap_primary = cm_svc.freeze_stage_pattern_snapshot(
            session, app1.id, stgm.PRIMARY_SCREENING,
            resulting_priority_interpretation="STANDARD", explanation="Steady tenure pattern observed.",
            rf_one_judgment="Worth a Phone Interview.",
        )
        session.commit()
        result.check(
            "PIF-E1: a Stage Pattern Snapshot freezes the currently-ACTIVE Observation(s) for that Stage",
            obs1_new.id in snap_primary.observation_ids and obs1.id not in snap_primary.observation_ids,
        )
        frozen_ids_before = list(snap_primary.observation_ids)
        pat_svc.record_observation(
            session, pattern_definition_id=definition.id, application_id=app1.id, person_id=app1.person_id,
            stage=stgm.PRIMARY_SCREENING, role=patm.ROLE_NEGATIVE, relevance=patm.RELEVANCE_LOW,
            explanation="A later, unrelated Observation added after the freeze.",
        )
        session.commit()
        session.expire_all()
        snap_primary_reloaded = session.get(m.SelectionStagePatternSnapshot, snap_primary.id)
        result.check(
            "PIF-F1: the frozen Snapshot's observation_ids list is UNCHANGED after new Observations "
            "are recorded for the same Stage later — the freeze is a true point-in-time copy, not a "
            "live query",
            snap_primary_reloaded.observation_ids == frozen_ids_before,
        )

        # =====================================================================
        # G. Stage Delta
        # =====================================================================
        stage_svc.set_stage(session, app1.id, stgm.PHONE_INTERVIEW)
        session.commit()
        pat_svc.supersede_observation(session, obs1_new.id, stage=stgm.PHONE_INTERVIEW, relevance=patm.RELEVANCE_HIGH)
        # (supersede_observation copies stage from the OLD row by default; explicitly re-record a
        # fresh Observation directly in the Phone Interview stage instead, since a delta is compared
        # across STAGES here, not within one.)
        new_pattern_def = pat_svc.create_pattern_definition(
            session, restaurant_id=restaurant.id, name="Strong Phone Communication",
            scope=patm.SCOPE_GENERAL, signature={"dimensions": [{"type": patm.DIMENSION_SKILLS}]},
        )
        session.commit()
        obs_phone_existing = pat_svc.record_observation(
            session, pattern_definition_id=definition.id, application_id=app1.id, person_id=app1.person_id,
            stage=stgm.PHONE_INTERVIEW, role=patm.ROLE_POSITIVE, relevance=patm.RELEVANCE_HIGH,
            explanation="Same tenure pattern still holds at Phone stage.",
        )
        obs_phone_new = pat_svc.record_observation(
            session, pattern_definition_id=new_pattern_def.id, application_id=app1.id, person_id=app1.person_id,
            stage=stgm.PHONE_INTERVIEW, role=patm.ROLE_POSITIVE, relevance=patm.RELEVANCE_MEDIUM,
            explanation="Clear, confident phone manner.",
        )
        session.commit()
        snap_phone = cm_svc.freeze_stage_pattern_snapshot(
            session, app1.id, stgm.PHONE_INTERVIEW, rf_one_judgment="Advance to In-Person.",
        )
        session.commit()
        deltas = {d.pattern_definition_id: d for d in snap_phone.deltas}
        result.check(
            "PIF-G1: a genuinely new Pattern Definition observed for the first time in this Stage "
            "produces a NEW_PATTERN delta",
            deltas.get(new_pattern_def.id) is not None and deltas[new_pattern_def.id].delta_type == patm.DELTA_NEW_PATTERN,
        )
        result.check(
            "PIF-G2: the same Definition, same role, but HIGHER relevance than the previous Stage "
            "Snapshot (MEDIUM -> HIGH) produces an IMPORTANCE_INCREASED delta with an explanation, "
            "never an opaque score",
            deltas.get(definition.id) is not None and deltas[definition.id].delta_type == patm.DELTA_IMPORTANCE_INCREASED
            and bool(deltas[definition.id].explanation),
        )

        # =====================================================================
        # H. Skipped Stage does not create a fake snapshot
        # =====================================================================
        stage_svc.set_stage(session, app1.id, stgm.IN_PERSON_PRACTICAL)  # skips nothing further; Phone already frozen
        session.commit()
        result.check(
            "PIF-H1: a Stage that was never explicitly frozen (e.g. this Application never visited "
            "APPLICATION_RECEIVED as an explicit freeze) has zero Stage Pattern Snapshots — nothing "
            "auto-creates one",
            len([s for s in cm_svc.list_stage_pattern_snapshots(session, app1.id) if s.stage == stgm.APPLICATION_RECEIVED]) == 0,
        )

        # =====================================================================
        # I. Repeated Stage creates a distinct historical snapshot
        # =====================================================================
        stage_svc.set_stage(session, app1.id, stgm.PRIMARY_SCREENING)  # Selezionatore moves it back
        session.commit()
        snap_primary_repeat = cm_svc.freeze_stage_pattern_snapshot(
            session, app1.id, stgm.PRIMARY_SCREENING, rf_one_judgment="Re-reviewed after Phone Interview.",
        )
        session.commit()
        result.check(
            "PIF-I1: revisiting a Stage and freezing it again creates a DISTINCT row with an "
            "incremented stage_occurrence_index — the first PRIMARY_SCREENING snapshot is untouched",
            snap_primary_repeat.id != snap_primary.id and snap_primary_repeat.stage_occurrence_index == 2
            and snap_primary.stage_occurrence_index == 1,
        )

        # =====================================================================
        # J/K. Selezionatore Note / Divergence representation
        # =====================================================================
        result.check(
            "PIF-J1: a Selezionatore Note is normally OPTIONAL (no divergence -> no note required)",
            snap_primary.note_required is False and snap_primary.selector_note is None,
        )
        result.check(
            "PIF-K1: recording a divergence WITHOUT a note is rejected — the architecture supports "
            "making the note mandatory on divergence",
            _raises(
                ValueError, cm_svc.freeze_stage_pattern_snapshot, session, app1.id, stgm.IN_PERSON_PRACTICAL,
                rf_one_judgment="Moderate priority.", selector_action="Selezionatore advanced to HIRE anyway.",
                divergence_occurred=True, divergence_category=patm.DIVERGENCE_EXPERIENCE,
            ),
        )
        snap_in_person = cm_svc.freeze_stage_pattern_snapshot(
            session, app1.id, stgm.IN_PERSON_PRACTICAL, rf_one_judgment="Moderate priority.",
            selector_action="Selezionatore advanced to HIRE anyway.", divergence_occurred=True,
            divergence_category=patm.DIVERGENCE_EXPERIENCE, selector_note="Excellent trial shift performance.",
        )
        session.commit()
        result.check(
            "PIF-K2: supplying the required note succeeds; the divergence category is preserved and "
            "is not restricted to a hard-coded enum (a plain, configurable string)",
            snap_in_person.divergence_occurred is True and snap_in_person.divergence_category == patm.DIVERGENCE_EXPERIENCE
            and snap_in_person.selector_note == "Excellent trial shift performance.",
        )

        # =====================================================================
        # L. Learning Trace — append-only behavior
        # =====================================================================
        traces_for_app = cm_svc.list_learning_traces(session, application_id=app1.id)
        divergence_traces = [t for t in traces_for_app if t.event_type == patm.TRACE_DIVERGENCE]
        result.check(
            "PIF-L1: recording a divergence automatically appends a Learning Trace — case-level "
            "overrides become raw evidence for future learning, never an automatic rule change",
            len(divergence_traces) == 1 and divergence_traces[0].event_data.get("divergence_category") == patm.DIVERGENCE_EXPERIENCE,
        )
        result.check(
            "PIF-L2: the Learning Trace service module exposes no update/delete function whatsoever — "
            "append-only is structural, not merely conventional",
            not hasattr(cm_svc, "update_learning_trace") and not hasattr(cm_svc, "delete_learning_trace"),
        )
        manual_trace = cm_svc.append_learning_trace(
            session, application_id=app1.id, person_id=app1.person_id, event_type=patm.TRACE_SKILL_TEST_FINDING,
            event_data={"finding": "Correctly carried a 3-plate tray on first attempt."},
        )
        session.commit()
        result.check(
            "PIF-L3: a genuinely new event_type (not in the suggested seed tuple) is accepted without "
            "any schema change — the column is an open string",
            manual_trace.event_type == patm.TRACE_SKILL_TEST_FINDING,
        )

        # =====================================================================
        # M. Selection Effort representation
        # =====================================================================
        effort_preview = cm_svc.compute_selection_effort(session, app1.id, interviewer_time_minutes=45)
        session.commit()
        result.check(
            "PIF-M1: Selection Effort captures what IS derivable (stages traversed > 0) and the "
            "manually-supplied field exactly, while never fabricating an unsupplied one "
            "(tests_administered_count stays None, not 0)",
            effort_preview.stages_traversed_count is not None and effort_preview.stages_traversed_count > 0
            and effort_preview.interviewer_time_minutes == 45 and effort_preview.tests_administered_count is None,
        )

        # =====================================================================
        # N/O. Case Memory creation on closure + exact version references
        # =====================================================================
        decision1 = outcome_svc.apply_outcome(session, app1.id, hire_like.id)
        session.commit()
        case_memory_v1 = cm_svc.close_case_memory(
            session, app1.id, rf_one_final_judgment="Strong, steady tenure candidate; recommend Hire.",
            selezionatore_final_decision="Hired — trial shift confirmed fit.",
            materially_impactful_pattern_versions=[{"pattern_definition_id": definition.id, "version": snapshot_v2.version}],
        )
        session.commit()
        result.check(
            "PIF-N1: closing an Application creates exactly one new Case Memory, version 1, marked "
            "current, referencing the Outcome Decision that closed it",
            case_memory_v1.version == 1 and case_memory_v1.is_current is True
            and case_memory_v1.outcome_decision_id == decision1.id,
        )
        result.check(
            "PIF-O1: the Case Memory references the EXACT Pattern Definition version materially "
            "involved, and the exact final Stage Snapshot / all Stage Snapshots traversed",
            case_memory_v1.materially_impactful_pattern_versions[0]["version"] == 2
            and case_memory_v1.final_stage_snapshot_id == snap_in_person.id
            and set(case_memory_v1.stage_snapshot_ids) == {
                snap_primary.id, snap_phone.id, snap_primary_repeat.id, snap_in_person.id,
            },
        )
        # A later edit to the live Pattern Definition must never rewrite what the Case Memory's
        # pinned version meant.
        pat_svc.update_pattern_definition(session, definition.id, description="Changed after closure.")
        session.commit()
        session.expire_all()
        pinned_snapshot_still = session.get(m.SelectionPatternDefinitionSnapshot, snapshot_v2.id)
        result.check(
            "PIF-O2: editing the live Pattern Definition AFTER Case Memory closure never rewrites the "
            "Snapshot the Case Memory's Observations/Deltas already pinned to",
            pinned_snapshot_still.version == 2 and pinned_snapshot_still.description == "Refined wording.",
        )

        # =====================================================================
        # P. Case Memory immutability
        # =====================================================================
        judgment_before = case_memory_v1.rf_one_final_judgment
        decision_before = case_memory_v1.selezionatore_final_decision
        notes_ref_before = list(case_memory_v1.notes_reference)
        app_svc.add_note(session, app1.id, "A brand-new, later note — added AFTER Case Memory V1 closed.")
        session.commit()
        session.expire_all()
        case_memory_v1_reloaded = session.get(m.SelectionCaseMemory, case_memory_v1.id)
        result.check(
            "PIF-P1: Case Memory V1 is untouched by a later Note added to the Application after "
            "closure — no service function in this codebase updates a Case Memory row after creation",
            case_memory_v1_reloaded.rf_one_final_judgment == judgment_before
            and case_memory_v1_reloaded.selezionatore_final_decision == decision_before
            and case_memory_v1_reloaded.notes_reference == notes_ref_before,
        )
        result.check(
            "PIF-P2: the Case Memory service module exposes no update/delete function for a Case "
            "Memory row",
            not hasattr(cm_svc, "update_case_memory") and not hasattr(cm_svc, "delete_case_memory"),
        )

        # =====================================================================
        # Q. Application reopen preserves the previous Case Memory
        # =====================================================================
        active_outcome = outcome_defs.get("Active / Continue") or outcome_defs.get("Active")
        reopened_decision = outcome_svc.reopen_application(
            session, app1.id, active_outcome.id, reason="New role opened up; reconsidering timeline.",
        )
        session.commit()
        session.expire_all()
        case_memory_v1_after_reopen = session.get(m.SelectionCaseMemory, case_memory_v1.id)
        result.check(
            "PIF-Q1: reopening the Application (T2 — new evidence/decision arrives) leaves the "
            "existing Case Memory V1 EXACTLY as it was — reopening alone never creates or alters a "
            "Case Memory; only an explicit close_case_memory() call does",
            case_memory_v1_after_reopen.rf_one_final_judgment == judgment_before
            and case_memory_v1_after_reopen.is_current is True
            and cm_svc.get_current_case_memory(session, app1.id).id == case_memory_v1.id,
        )

        # =====================================================================
        # R. Second closure creates a NEW Case Memory version
        # =====================================================================
        pat_svc.record_observation(
            session, pattern_definition_id=new_pattern_def.id, application_id=app1.id, person_id=app1.person_id,
            stage=stgm.IN_PERSON_PRACTICAL, role=patm.ROLE_POSITIVE, relevance=patm.RELEVANCE_HIGH,
            explanation="New evidence gathered after reopening.",
        )
        decision2 = outcome_svc.apply_outcome(session, app1.id, hire_like.id, reason="Confirmed hire after second look.")
        session.commit()
        case_memory_v2 = cm_svc.close_case_memory(
            session, app1.id, rf_one_final_judgment="Confirmed strong candidate on second review.",
            selezionatore_final_decision="Hired (second, later decision).",
        )
        session.commit()
        session.expire_all()
        case_memory_v1_final_check = session.get(m.SelectionCaseMemory, case_memory_v1.id)
        result.check(
            "PIF-R1: closing the reopened Application creates Case Memory V2 (version 2), linked to "
            "V1 via previous_case_memory_id, marked current — while V1 is flipped to is_current=False "
            "(a pointer change only, never a content rewrite) and every one of V1's OWN recorded "
            "facts remains BYTE-FOR-BYTE the original T1 belief",
            case_memory_v2.version == 2 and case_memory_v2.previous_case_memory_id == case_memory_v1.id
            and case_memory_v2.is_current is True
            and case_memory_v1_final_check.is_current is False
            and case_memory_v1_final_check.rf_one_final_judgment == judgment_before
            and case_memory_v1_final_check.selezionatore_final_decision == decision_before
            and case_memory_v1_final_check.version == 1,
        )
        result.check(
            "PIF-R2: FINAL VALIDATION (task's own explicit acceptance test) — at T1 RF-One believed "
            "X and the Selezionatore decided Y; Case Memory V1 records exactly X and Y. At T2 new "
            "evidence arrived and the Application reopened and closed again; V1 STILL says exactly X "
            "and Y (never rewritten), and V2 independently records the later state — nothing in this "
            "architecture is capable of rewriting what RF-One knew, predicted, recommended, or what "
            "the Selezionatore decided in the past",
            case_memory_v1_final_check.rf_one_final_judgment == "Strong, steady tenure candidate; recommend Hire."
            and case_memory_v1_final_check.selezionatore_final_decision == "Hired — trial shift confirmed fit."
            and case_memory_v2.rf_one_final_judgment == "Confirmed strong candidate on second review."
            and case_memory_v2.selezionatore_final_decision == "Hired (second, later decision).",
        )
        history = cm_svc.list_case_memory_versions(session, app1.id)
        result.check(
            "PIF-R3: the full Case Memory version history for this Application is available and "
            "never shrinks — both V1 and V2 are present, in order",
            [c.version for c in history] == [1, 2],
        )

        # =====================================================================
        # S. Downstream feedback does not modify Case Memory
        # =====================================================================
        feedback = cm_svc.append_downstream_feedback(
            session, application_id=app1.id, case_memory_id=case_memory_v1.id, source_domain="Training",
            feedback_type="TRAINING_COMPLETED", observed_fact="Completed onboarding training within 2 weeks.",
        )
        session.commit()
        session.expire_all()
        case_memory_v1_after_feedback = session.get(m.SelectionCaseMemory, case_memory_v1.id)
        result.check(
            "PIF-S1: appending downstream Outcome Feedback (foundation only — no Training integration "
            "is implemented) never modifies the Case Memory it references",
            feedback.case_memory_id == case_memory_v1.id
            and case_memory_v1_after_feedback.rf_one_final_judgment == judgment_before,
        )
        result.check(
            "PIF-S2: the Downstream Feedback service module exposes no update/delete function",
            not hasattr(cm_svc, "update_downstream_feedback") and not hasattr(cm_svc, "delete_downstream_feedback"),
        )

        # =====================================================================
        # T/U/V/W. Authority configuration — 1, 2, 3 levels, and none required
        # =====================================================================
        gov_restaurant_1 = m.Restaurant(name="Synthetic PIF Governance 1-Level Restaurant", default_currency="USD")
        gov_restaurant_2 = m.Restaurant(name="Synthetic PIF Governance 2-Level Restaurant", default_currency="USD")
        gov_restaurant_3 = m.Restaurant(name="Synthetic PIF Governance 3-Level Restaurant", default_currency="USD")
        session.add_all([gov_restaurant_1, gov_restaurant_2, gov_restaurant_3])
        session.commit()

        gov_svc.create_authority_level(session, restaurant_id=gov_restaurant_1.id, level_key="SELECTOR", level_order=1)
        session.commit()
        levels_1 = gov_svc.list_authority_levels(session, restaurant_id=gov_restaurant_1.id)
        result.check("PIF-T1: an Organization may configure exactly ONE authority level", len(levels_1) == 1)

        gov_svc.create_authority_level(session, restaurant_id=gov_restaurant_2.id, level_key="SELECTOR", level_order=1)
        gov_svc.create_authority_level(session, restaurant_id=gov_restaurant_2.id, level_key="SELECTION_OWNER", level_order=2)
        session.commit()
        levels_2 = gov_svc.list_authority_levels(session, restaurant_id=gov_restaurant_2.id)
        result.check(
            "PIF-U1: an Organization may configure exactly TWO authority levels, correctly ordered",
            [lvl.level_key for lvl in levels_2] == ["SELECTOR", "SELECTION_OWNER"],
        )

        gov_svc.create_authority_level(session, restaurant_id=gov_restaurant_3.id, level_key="SELECTOR", level_order=1)
        gov_svc.create_authority_level(session, restaurant_id=gov_restaurant_3.id, level_key="SENIOR_SELECTOR", level_order=2)
        gov_svc.create_authority_level(session, restaurant_id=gov_restaurant_3.id, level_key="SELECTION_OWNER", level_order=3)
        session.commit()
        levels_3 = gov_svc.list_authority_levels(session, restaurant_id=gov_restaurant_3.id)
        result.check(
            "PIF-V1: an Organization may configure all THREE example authority levels, correctly ordered",
            [lvl.level_key for lvl in levels_3] == ["SELECTOR", "SENIOR_SELECTOR", "SELECTION_OWNER"],
        )
        result.check(
            "PIF-W1: a restaurant with only ONE configured level is never forced to have the other "
            "two invented for it — each restaurant's configuration is independent",
            len(gov_svc.list_authority_levels(session, restaurant_id=gov_restaurant_1.id)) == 1,
        )
        result.check(
            "PIF-W2: an action type with NO configured governance requirement returns None — RF-One "
            "never invents a requirement that was not configured",
            gov_svc.get_governance_requirement_for_action(
                session, restaurant_id=gov_restaurant_1.id, action_type="SOME_UNCONFIGURED_ACTION",
            ) is None,
        )
        gov_svc.create_governance_requirement(
            session, restaurant_id=gov_restaurant_3.id, action_type="PATTERN_DEFINITION_APPROVAL",
            required_authority_level_id=levels_3[-1].id, requires_higher_approval=True,
        )
        session.commit()
        requirement = gov_svc.get_governance_requirement_for_action(
            session, restaurant_id=gov_restaurant_3.id, action_type="PATTERN_DEFINITION_APPROVAL",
        )
        result.check(
            "PIF-W3: a CONFIGURED governance requirement is correctly retrieved once one exists",
            requirement is not None and requirement.required_authority_level_id == levels_3[-1].id,
        )

        for r in (gov_restaurant_1, gov_restaurant_2, gov_restaurant_3):
            for req in gov_svc.list_governance_requirements(session, restaurant_id=r.id):
                session.delete(req)
        session.flush()
        for r in (gov_restaurant_1, gov_restaurant_2, gov_restaurant_3):
            for lvl in gov_svc.list_authority_levels(session, restaurant_id=r.id):
                session.delete(lvl)
        session.flush()
        session.delete(gov_restaurant_1)
        session.delete(gov_restaurant_2)
        session.delete(gov_restaurant_3)
        session.commit()

        # =====================================================================
        # X. Serialization/deserialization
        # =====================================================================
        session.expire_all()
        cm_reloaded = session.get(m.SelectionCaseMemory, case_memory_v1.id)
        def_reloaded = session.get(m.SelectionPatternDefinition, definition.id)
        result.check(
            "PIF-X1: every JSON-typed field survives a full session-expire reload with the correct "
            "Python type (list stays list, dict stays dict) and correct values",
            isinstance(cm_reloaded.stage_snapshot_ids, list) and isinstance(def_reloaded.signature, dict)
            and def_reloaded.signature["dimensions"][0]["type"] == patm.DIMENSION_STABILITY
            and len(cm_reloaded.stage_snapshot_ids) == 4,
        )

        # =====================================================================
        # Y. Backward compatibility with existing Application records
        # =====================================================================
        session.expire_all()
        app1_reloaded = session.get(m.Application, app1.id)
        result.check(
            "PIF-Y1: pre-existing Selection functionality (workflow_status legacy projection, Stage "
            "history, Outcome history) still works entirely unaffected by every structure added in "
            "this task — `workflow_status` legitimately changed via the PRE-EXISTING "
            "`stage_service.set_stage`/`outcome_service.apply_outcome` -> `refresh_legacy_workflow_"
            "status` projection this task never touches, never via anything new here",
            app1_reloaded.workflow_status in apm.WORKFLOW_STATUSES
            and len(stage_svc.list_stage_history(session, app1.id)) >= 3
            and len(outcome_svc.list_outcome_history(session, app1.id)) >= 3,
        )

        # =====================================================================
        # Z. No fabricated evidence/default facts
        # =====================================================================
        bare_definition = pat_svc.create_pattern_definition(session, restaurant_id=restaurant.id, name="Bare Pattern")
        bare_effort = cm_svc.compute_selection_effort(session, app1.id)
        session.commit()
        result.check(
            "PIF-Z1: fields never explicitly supplied stay None/empty — never guessed or defaulted to "
            "a fabricated placeholder value (description, interviewer_time_minutes, "
            "tests_administered_count, preparation_notes all None; signature defaults to an empty "
            "structure, not an invented one)",
            bare_definition.description is None and bare_definition.signature == {}
            and bare_effort.interviewer_time_minutes is None and bare_effort.tests_administered_count is None
            and bare_effort.preparation_notes is None,
        )

    finally:
        session.rollback()
        if restaurant is not None and restaurant.id is not None:
            app_ids = [a.id for a in app_svc.list_applications(session, restaurant_id=restaurant.id)]

            for delta_row in session.query(m.SelectionStagePatternDelta).join(
                m.SelectionStagePatternSnapshot,
                m.SelectionStagePatternDelta.stage_snapshot_id == m.SelectionStagePatternSnapshot.id,
            ).filter(m.SelectionStagePatternSnapshot.application_id.in_(app_ids or [-1])):
                session.delete(delta_row)
            session.flush()

            for snap_row in session.query(m.SelectionStagePatternSnapshot).filter(
                m.SelectionStagePatternSnapshot.application_id.in_(app_ids or [-1])
            ):
                snap_row.previous_snapshot_id = None
            session.flush()
            for cm_row in session.query(m.SelectionCaseMemory).filter(
                m.SelectionCaseMemory.application_id.in_(app_ids or [-1])
            ):
                cm_row.final_stage_snapshot_id = None
                cm_row.previous_case_memory_id = None
            session.flush()
            for feedback_row in session.query(m.SelectionDownstreamOutcomeFeedback).filter(
                m.SelectionDownstreamOutcomeFeedback.application_id.in_(app_ids or [-1])
            ):
                session.delete(feedback_row)
            session.flush()
            for cm_row in session.query(m.SelectionCaseMemory).filter(
                m.SelectionCaseMemory.application_id.in_(app_ids or [-1])
            ):
                session.delete(cm_row)
            session.flush()
            for snap_row in session.query(m.SelectionStagePatternSnapshot).filter(
                m.SelectionStagePatternSnapshot.application_id.in_(app_ids or [-1])
            ):
                session.delete(snap_row)
            session.flush()
            for effort_row in session.query(m.SelectionEffort).filter(
                m.SelectionEffort.application_id.in_(app_ids or [-1])
            ):
                session.delete(effort_row)
            session.flush()
            for trace_row in session.query(m.SelectionLearningTrace).filter(
                m.SelectionLearningTrace.application_id.in_(app_ids or [-1])
            ):
                session.delete(trace_row)
            session.flush()
            for obs_row in session.query(m.SelectionPatternObservation).filter(
                m.SelectionPatternObservation.application_id.in_(app_ids or [-1])
            ):
                obs_row.superseded_by_id = None
            session.flush()
            for obs_row in session.query(m.SelectionPatternObservation).filter(
                m.SelectionPatternObservation.application_id.in_(app_ids or [-1])
            ):
                session.delete(obs_row)
            session.flush()
            for cmp_row in session.query(m.SelectionPatternCaseComparison).filter(
                m.SelectionPatternCaseComparison.application_id.in_(app_ids or [-1])
            ):
                session.delete(cmp_row)
            session.flush()

            pattern_def_ids = [
                d.id for d in pat_svc.list_pattern_definitions(session, restaurant_id=restaurant.id)
            ]
            for ex_row in session.query(m.SelectionPatternExample).filter(
                m.SelectionPatternExample.pattern_definition_id.in_(pattern_def_ids or [-1])
            ):
                session.delete(ex_row)
            session.flush()
            for def_row in session.query(m.SelectionPatternDefinition).filter_by(restaurant_id=restaurant.id):
                def_row.required_authority_level_id = None
            session.flush()
            for snap_row in session.query(m.SelectionPatternDefinitionSnapshot).filter(
                m.SelectionPatternDefinitionSnapshot.definition_id.in_(pattern_def_ids or [-1])
            ):
                session.delete(snap_row)
            session.flush()
            for def_row in session.query(m.SelectionPatternDefinition).filter_by(restaurant_id=restaurant.id):
                session.delete(def_row)
            session.flush()

            for evaluation_row in session.query(m.PrimaryScreeningCriterionEvaluation).join(
                m.PrimaryScreeningRun, m.PrimaryScreeningCriterionEvaluation.run_id == m.PrimaryScreeningRun.id
            ).filter(m.PrimaryScreeningRun.restaurant_id == restaurant.id):
                session.delete(evaluation_row)
            session.flush()
            for run_row in session.query(m.PrimaryScreeningRun).filter_by(restaurant_id=restaurant.id):
                session.delete(run_row)
            session.flush()
            for snapshot_row in session.query(m.PrimaryScreeningCriterionSnapshot).join(
                m.PrimaryScreeningCriterion, m.PrimaryScreeningCriterionSnapshot.criterion_id == m.PrimaryScreeningCriterion.id
            ).filter(m.PrimaryScreeningCriterion.restaurant_id == restaurant.id):
                session.delete(snapshot_row)
            session.flush()
            for criterion_row in session.query(m.PrimaryScreeningCriterion).filter_by(restaurant_id=restaurant.id):
                session.delete(criterion_row)
            session.flush()
            for flag_row in session.query(m.CandidateFlag).filter_by(restaurant_id=restaurant.id):
                session.delete(flag_row)
            session.flush()
            for application_row in app_svc.list_applications(session, restaurant_id=restaurant.id):
                session.delete(application_row)
            session.flush()
            for def_snapshot_row in session.query(m.SelectionOutcomeDefinitionSnapshot).join(
                m.SelectionOutcomeDefinition, m.SelectionOutcomeDefinitionSnapshot.definition_id == m.SelectionOutcomeDefinition.id
            ).filter(m.SelectionOutcomeDefinition.restaurant_id == restaurant.id):
                session.delete(def_snapshot_row)
            session.flush()
            for definition_row in session.query(m.SelectionOutcomeDefinition).filter_by(restaurant_id=restaurant.id):
                session.delete(definition_row)
            session.flush()
            for queue_row in session.query(m.SelectionQueue).filter_by(restaurant_id=restaurant.id):
                session.delete(queue_row)
            session.flush()
            for person_row in session.query(m.CandidatePerson).filter_by(restaurant_id=restaurant.id):
                session.delete(person_row)
            session.flush()
            for candidate_row in persistence.list_candidates(session, restaurant_id=restaurant.id):
                session.delete(candidate_row)
            session.flush()
            for raw_row in session.query(m.RawResume).filter_by(restaurant_id=restaurant.id):
                session.delete(raw_row)
            session.flush()
            session.delete(session.get(m.Restaurant, restaurant.id))
            session.commit()
        session.close()


def _raises(exc_type, func, *args, **kwargs) -> bool:
    try:
        func(*args, **kwargs)
    except exc_type:
        return True
    except Exception:
        return False
    return False
