"""RF-One Selection — Resume Screening web MVP (TASK_SELECTION_001, extended
by TASK_SELECTION_002 with multi-résumé batch import, by Task 2A with
DOCX/TXT support and a real, non-fabricating parsing fallback — see
`rfone_data_store/selection/parsing/text_extraction.py` and
`.../parsing/deterministic_parser.py` — and by Task 3A with the Selection
Requirement Framework (`/requirements` routes below) — see
`rfone_data_store/selection/requirements_service.py`. The Requirement
Framework defines WHAT a restaurant is looking for; it never touches a
Candidate row and performs no matching/scoring (Task 3A's own conceptual
boundary). Task 3B adds Fit Assessment (`/fit-assessments` routes below) —
see `rfone_data_store/selection/fit_assessment_service.py` — which organizes
EVIDENCE against those Requirements for one candidate; it never decides
whether to hire, never scores, never ranks.

Follows the same small-local-Flask-app convention `03 Software/InvoiceIntake/
app.py` already established: server-rendered Jinja2 templates, no JS
framework/build step, local dev server — `home.html`'s batch-upload progress
UI adds a small amount of vanilla JavaScript (drag/drop + per-file
fetch()/JSON polling of `/api/upload`) but no framework or build step.
Reuses the existing RF-One Data Store persistence mechanism (SQLAlchemy +
Alembic, `rfone_data_store`) — see that package's `selection/` subpackage
for all business logic; this file is routing/glue only. The per-file
duplicate-checked parse+persist orchestration itself lives in
`rfone_data_store/selection/import_pipeline.py`, not here, so it is testable
without a running Flask app and reusable by a future non-HTTP ResumeSource.

Database: by default this app uses its OWN local SQLite file
(`data/selection.db`), NOT the shared production `data/rfone.db` used by
Tips/Payroll/Sales — a deliberate choice so demo/mock candidate data is
never mixed into the real Rome's Flavours operational database. Point
`RFONE_DATABASE_URL` at the shared store instead if/when the Product Owner
wants Selection unified into it; the schema is fully compatible (same
Alembic migration chain, see `migrations/versions/
b8f1c4a2e6d9_add_selection_resume_screening_schema.py`).
"""

from __future__ import annotations

import os
import sys
import uuid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DATA_DIR = os.path.join(BASE_DIR, "data")
DEFAULT_DB_PATH = os.path.join(DATA_DIR, "selection.db")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

os.environ.setdefault("RFONE_DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH.replace(os.sep, '/')}")

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for  # noqa: E402

from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.database import (  # noqa: E402
    create_configured_engine, create_session_factory, get_database_url,
    redact_database_url, run_migrations_to_head,
)
from rfone_data_store.selection import acquisition_source_service as acq_svc  # noqa: E402
from rfone_data_store.selection import application_intake_service as intake_svc  # noqa: E402
from rfone_data_store.selection import application_question_service as aq_svc  # noqa: E402
from rfone_data_store.selection import application_service as app_svc  # noqa: E402
from rfone_data_store.selection import candidate_flag_service as flag_svc  # noqa: E402
from rfone_data_store.selection import audit_service as audit_svc  # noqa: E402
from rfone_data_store.selection import channel_analytics_service as analytics_svc  # noqa: E402
from rfone_data_store.selection import channel_service as chan_svc  # noqa: E402
from rfone_data_store.selection import compliance_service as compliance_svc  # noqa: E402
from rfone_data_store.selection import communication_service as comm_svc  # noqa: E402
from rfone_data_store.selection import communication_template_service as tmpl_svc  # noqa: E402
from rfone_data_store.selection import decision_service as dec_svc  # noqa: E402
from rfone_data_store.selection import dossier_service as dossier_svc  # noqa: E402
from rfone_data_store.selection import fit_assessment_service as fa_svc  # noqa: E402
from rfone_data_store.selection import governance_service as gov_svc  # noqa: E402
from rfone_data_store.selection import identity_service as id_svc  # noqa: E402
from rfone_data_store.selection import in_person_interview_service as ip_svc  # noqa: E402
from rfone_data_store.selection import inbound_communication_service as inbound_svc  # noqa: E402
from rfone_data_store.selection import job_posting_service as jp_svc  # noqa: E402
from rfone_data_store.selection import missing_evidence_service as me_svc  # noqa: E402
from rfone_data_store.selection import outcome_service as outcome_svc  # noqa: E402
from rfone_data_store.selection import scheduling_service as sched_svc  # noqa: E402
from rfone_data_store.selection import ownership_service as own_svc  # noqa: E402
from rfone_data_store.selection import persistence  # noqa: E402
from rfone_data_store.selection import phone_interview_service as pi_svc  # noqa: E402
from rfone_data_store.selection import primary_screening_service as ps_svc  # noqa: E402
from rfone_data_store.selection import queue_service as queue_svc  # noqa: E402
from rfone_data_store.selection import requirements_service as req_svc  # noqa: E402
from rfone_data_store.selection import rule_change_service as rc_svc  # noqa: E402
from rfone_data_store.selection import rule_set_service as rs_svc  # noqa: E402
from rfone_data_store.selection import selection_notes_service as notes_svc  # noqa: E402
from rfone_data_store.selection import session_service as sess_svc  # noqa: E402
from rfone_data_store.selection import signal_service as sig_svc  # noqa: E402
from rfone_data_store.selection import stage_service as stage_svc  # noqa: E402
from rfone_data_store.selection import trainable_gap_service as tg_svc  # noqa: E402
from rfone_data_store.selection import workflow_projection_service as wf_svc  # noqa: E402
from rfone_data_store.selection.analysis import analyze_candidate  # noqa: E402
from rfone_data_store.selection.core import application_model as apm  # noqa: E402
from rfone_data_store.selection.core import fit_assessment_model as fam  # noqa: E402
from rfone_data_store.selection.core import in_person_interview_model as ipm  # noqa: E402
from rfone_data_store.selection.core import communication_model as cm  # noqa: E402
from rfone_data_store.selection.core import compliance_model as cpm  # noqa: E402
from rfone_data_store.selection.core import job_posting_model as jpm  # noqa: E402
from rfone_data_store.selection.core import outcome_model as om  # noqa: E402
from rfone_data_store.selection.core import phone_interview_model as pim  # noqa: E402
from rfone_data_store.selection.core import primary_screening_model as psm  # noqa: E402
from rfone_data_store.selection.core import queue_model as qm  # noqa: E402
from rfone_data_store.selection.core import requirement_model as rm  # noqa: E402
from rfone_data_store.selection.core import rule_set_model as rsm  # noqa: E402
from rfone_data_store.selection.core import session_model as sesm  # noqa: E402
from rfone_data_store.selection.core import signal_model as sigm  # noqa: E402
from rfone_data_store.selection.core import stage_model as stgm  # noqa: E402
from rfone_data_store.selection.core import trainable_gap_model as tgm  # noqa: E402
from rfone_data_store.selection.core.resume_source import LOCAL_UPLOAD  # noqa: E402
from rfone_data_store.selection.import_pipeline import COMPLETED, PARTIAL, import_one_resume  # noqa: E402
from rfone_data_store.selection.industry.restaurant import ROME_FLAVOURS_SERVER_ROLE_CONFIG  # noqa: E402
from rfone_data_store.selection.industry.restaurant_templates import (  # noqa: E402
    seed_default_review_priority_policy, seed_default_selection_outcomes, seed_default_selection_queues,
    seed_romes_flavours_in_person_interview_structure, seed_romes_flavours_phone_interview_questions,
    seed_romes_flavours_primary_screening_criteria, seed_sample_templates,
)
from rfone_data_store.selection.parsing.dedup import compute_content_hash  # noqa: E402
from rfone_data_store.selection.parsing.text_extraction import SUPPORTED_EXTENSIONS, extract_text  # noqa: E402

ALLOWED_EXT = set(SUPPORTED_EXTENSIONS)

_DB_URL = get_database_url()
run_migrations_to_head(_DB_URL)
_engine = create_configured_engine(_DB_URL)
SessionFactory = create_session_factory(_engine)

app = Flask(__name__)


def _bootstrap_restaurant(session) -> "m.Restaurant":
    """This deployment's one Client — Rome's Flavours. Created once,
    locally, if this Selection app's own database does not have it yet
    (never touches the shared production RF-One Data Store)."""

    from sqlalchemy import select

    existing = session.scalars(select(m.Restaurant)).first()
    if existing:
        return existing
    restaurant = m.Restaurant(name="Rome's Flavours", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.commit()
    return restaurant


def _candidate_rows(candidates: list["m.Candidate"]) -> list[dict]:
    """Builds the candidate-list table's rows (TASK_SELECTION_002 §9): name,
    location, source, latest/current role, employment-record count, import
    status and information-quality confidence — no universal CV score."""

    rows = []
    for candidate in candidates:
        profile = persistence.to_profile(candidate)
        view = analyze_candidate(profile)

        current_role = next((w.original_job_title for w in profile.work_history if w.is_current), None)
        if not current_role:
            dated = [w for w in profile.work_history if w.start_date is not None]
            if dated:
                current_role = max(dated, key=lambda w: w.start_date).original_job_title

        rows.append(
            {
                "id": candidate.id,
                "full_name": candidate.full_name or "(name not extracted)",
                "location": candidate.location or "-",
                "source": candidate.source or "-",
                "source_provider": candidate.source_provider or "-",
                "current_role": current_role or "-",
                "employment_count": len(profile.work_history),
                "target_role": candidate.target_role or "-",
                "direct_months": view.breakdown.direct_role_months,
                "relevant_months": view.breakdown.relevant_propedeutic_months,
                "stability": next(i for i in view.indicators if i.name == "Stability").state,
                "flag_count": len(view.flags),
                "confidence_pct": view.information_quality.overall_confidence_pct,
                "status": candidate.status,
                "parsing_mode": candidate.parsing_mode,
                "imported_at": candidate.created_at,
            }
        )
    return rows


@app.route("/")
def home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        candidates = persistence.list_candidates(session, restaurant_id=restaurant.id)
        rows = _candidate_rows(candidates)

        return render_template(
            "home.html",
            client_name=restaurant.name,
            active_role=ROME_FLAVOURS_SERVER_ROLE_CONFIG.target_role,
            candidate_count=len(rows),
            candidates=rows,
            db_url=redact_database_url(_DB_URL),
            active_nav="candidates",
        )


def _process_one_upload(file_storage) -> dict:
    """Handles exactly one uploaded résumé — file-extension validation,
    saving, real text extraction, then hands off to
    `import_pipeline.import_one_resume` for duplicate-checked
    parsing/persistence. Always returns a result dict (never raises), so a
    caller looping over many files gets per-file isolation for free
    (task §2)."""

    filename = file_storage.filename or "(unnamed file)"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        supported = ", ".join(sorted(e.lstrip(".").upper() for e in ALLOWED_EXT))
        return {
            "filename": filename, "status": "FAILED",
            "error": f"Unsupported format: {ext or '(none)'}. Supported formats: {supported}.",
        }

    unique_name = f"{uuid.uuid4().hex[:8]}_{filename}"
    saved_path = os.path.join(UPLOAD_DIR, unique_name)
    try:
        file_storage.save(saved_path)
    except Exception:
        return {"filename": filename, "status": "FAILED", "error": "Could not save the uploaded file."}

    raw_text = extract_text(saved_path, ext)
    content_hash = compute_content_hash(raw_text, filename)

    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        result = import_one_resume(
            session, restaurant_id=restaurant.id, source_type=LOCAL_UPLOAD,
            original_filename=filename, storage_path=saved_path, raw_text=raw_text,
            content_hash=content_hash,
        )

        application_id = None
        if result.status in (COMPLETED, PARTIAL) and result.candidate_id is not None:
            # Task 3C: every successfully imported résumé becomes one
            # Application, resolved/linked to its CandidatePerson (best-
            # effort, by email) — never blocks or fails the upload itself.
            application = app_svc.create_application(session, candidate_id=result.candidate_id, restaurant_id=restaurant.id)
            seed_default_review_priority_policy(session, restaurant_id=restaurant.id)  # idempotent
            sig_svc.generate_resume_stage_signals(session, application.id)
            session.commit()
            application_id = application.id

    if result.status == "FAILED":
        app.logger.warning("Resume import failed for %r: %s", filename, result.error)

    return {
        "filename": filename, "status": result.status,
        "candidate_id": result.candidate_id, "full_name": result.full_name,
        "parsing_mode": result.parsing_mode, "error": result.error, "application_id": application_id,
    }


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """JSON endpoint used by the batch-upload UI's JavaScript — one file per
    call, so the page can show a live WAITING/PROCESSING/COMPLETED/FAILED
    state per file and an aggregate "x / y processed" count while a batch is
    still in flight."""

    file = request.files.get("resume_file")
    if not file or file.filename == "":
        return jsonify({"filename": None, "status": "FAILED", "error": "No file received."}), 400
    return jsonify(_process_one_upload(file))


@app.route("/upload", methods=["POST"])
def upload():
    """Classic multipart-form fallback for when JavaScript is unavailable —
    accepts one or many files (the form's file input has `multiple`) in a
    single POST and processes each independently, then re-renders the
    candidate list with a batch-results summary."""

    files = [f for f in request.files.getlist("resume_file") if f and f.filename]
    if not files:
        return redirect(url_for("home"))

    results = [_process_one_upload(f) for f in files]

    if len(results) == 1 and results[0]["status"] in (COMPLETED, PARTIAL):
        return redirect(url_for("candidate_detail", candidate_id=results[0]["candidate_id"]))

    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        candidates = persistence.list_candidates(session, restaurant_id=restaurant.id)
        rows = _candidate_rows(candidates)

    return render_template(
        "home.html",
        client_name=restaurant.name,
        active_role=ROME_FLAVOURS_SERVER_ROLE_CONFIG.target_role,
        candidate_count=len(rows),
        candidates=rows,
        db_url=redact_database_url(_DB_URL),
        batch_results=results,
    )


@app.route("/candidate/<int:candidate_id>")
def candidate_detail(candidate_id: int):
    from rfone_data_store.selection.core.experience_analysis import months_between
    from rfone_data_store.selection.core.role_model import classify_role

    with SessionFactory() as session:
        candidate = persistence.get_candidate(session, candidate_id)
        if candidate is None:
            return redirect(url_for("home"))

        profile = persistence.to_profile(candidate)
        view = analyze_candidate(profile)

        role_config = ROME_FLAVOURS_SERVER_ROLE_CONFIG
        work_entries = [
            {
                "record": w,
                "months": months_between(w.start_date, w.end_date if not w.is_current else None),
                "category": classify_role(w.normalized_role, role_config),
            }
            for w in profile.work_history
        ]

        raw_resume_text = None
        if candidate.raw_resume_id:
            raw = session.get(m.RawResume, candidate.raw_resume_id)
            raw_resume_text = raw.raw_text if raw else None

        fit_assessments = fa_svc.list_fit_assessments_for_candidate(session, candidate_id)
        available_requirement_sets = req_svc.list_requirement_sets(
            session, restaurant_id=candidate.restaurant_id, active_only=True,
        )
        application = app_svc.get_application_for_candidate(session, candidate_id)
        # Task 5A-ALIGN §12 — a Candidate Flag (e.g. a prior "Training Check
        # Not Passed") must be immediately visible at CV Review too.
        active_flags = flag_svc.list_active_flags_for_application(session, application.id) if application else []

        return render_template(
            "detail.html",
            candidate=candidate, profile=profile, view=view,
            work_entries=work_entries, raw_resume_text=raw_resume_text,
            fit_assessments=fit_assessments, available_requirement_sets=available_requirement_sets,
            application=application, original_cv_available=_original_cv_available(session, candidate),
            active_flags=active_flags, active_nav="candidates",
        )


def _original_cv_available(session, candidate: "m.Candidate") -> bool:
    """Task 3C-FIX §5 — whether "Open Original CV" has a real file to open.
    Never assumed true just because `raw_resume_id` is set: the row may
    reference a since-removed local upload."""

    if not candidate.raw_resume_id:
        return False
    raw = session.get(m.RawResume, candidate.raw_resume_id)
    return bool(raw and raw.storage_path and os.path.isfile(raw.storage_path))


@app.route("/candidate/<int:candidate_id>/original-cv")
def candidate_original_cv(candidate_id: int):
    """Opens the ORIGINAL uploaded résumé file directly (Task 3C-FIX §5) —
    never a re-rendering of extracted/interpreted data, so the Selezionatore
    can always compare RF-One's interpretation against the source document.
    Linked with `target="_blank"` everywhere it appears, so this always
    opens in a new tab/window."""

    with SessionFactory() as session:
        candidate = persistence.get_candidate(session, candidate_id)
        if candidate is None or not _original_cv_available(session, candidate):
            return render_template("original_cv_unavailable.html", candidate=candidate, active_nav="candidates"), 404

        raw = session.get(m.RawResume, candidate.raw_resume_id)
        storage_path = os.path.normpath(raw.storage_path)
        # The only files ever referenced here are ones this app itself saved
        # into UPLOAD_DIR (see `_process_one_upload`) — refuse anything else.
        if os.path.commonpath([storage_path, UPLOAD_DIR]) != os.path.normpath(UPLOAD_DIR):
            abort(403)

        return send_file(storage_path, as_attachment=False, download_name=raw.original_filename or None)


# ---------------------------------------------------------------------------
# Selection Requirement Framework (Task 3A) — "what is the restaurant
# looking for," completely separate from Candidate data. Routes are thin:
# every actual operation is delegated to `requirements_service.py`
# (task §14: "Avoid putting all business logic directly inside Flask
# routes.").
# ---------------------------------------------------------------------------


@app.route("/requirements")
def requirements_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        seed_sample_templates(session)  # idempotent — cheap on an already-seeded database

        requirement_sets = req_svc.list_requirement_sets(session, restaurant_id=restaurant.id)
        templates = req_svc.list_templates(session)

        return render_template(
            "requirements_home.html",
            client_name=restaurant.name,
            requirement_sets=requirement_sets,
            templates=templates,
            active_nav="requirements",
        )


@app.route("/requirements/new-custom", methods=["POST"])
def requirements_new_custom():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        name = (request.form.get("name") or "").strip()
        if not name:
            return redirect(url_for("requirements_home"))
        requirement_set = req_svc.create_requirement_set(
            session, restaurant_id=restaurant.id, name=name,
            description=(request.form.get("description") or "").strip() or None,
            location_label=(request.form.get("location_label") or "").strip() or None,
            target_role=(request.form.get("target_role") or "").strip() or None,
        )
        session.commit()
        return redirect(url_for("requirement_set_detail", requirement_set_id=requirement_set.id))


@app.route("/requirements/new-from-template", methods=["POST"])
def requirements_new_from_template():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        template_id = request.form.get("template_id", type=int)
        name = (request.form.get("name") or "").strip()
        if not template_id or not name:
            return redirect(url_for("requirements_home"))
        requirement_set = req_svc.instantiate_requirement_set_from_template(
            session, template_id=template_id, restaurant_id=restaurant.id, name=name,
            location_label=(request.form.get("location_label") or "").strip() or None,
            target_role=(request.form.get("target_role") or "").strip() or None,
        )
        session.commit()
        return redirect(url_for("requirement_set_detail", requirement_set_id=requirement_set.id))


@app.route("/requirements/<int:requirement_set_id>")
def requirement_set_detail(requirement_set_id: int):
    with SessionFactory() as session:
        requirement_set = req_svc.get_requirement_set(session, requirement_set_id)
        if requirement_set is None:
            return redirect(url_for("requirements_home"))
        snapshots = req_svc.list_snapshots(session, requirement_set_id)
        return render_template(
            "requirement_set_detail.html",
            requirement_set=requirement_set,
            snapshots=snapshots,
            criticality_levels=rm.CRITICALITY_LEVELS,
            trainability_levels=rm.TRAINABILITY_LEVELS,
            assessment_stages=rm.ASSESSMENT_STAGES,
            categories=rm.STARTER_CATEGORIES,
            active_nav="requirements",
        )


@app.route("/requirements/<int:requirement_set_id>/snapshot", methods=["POST"])
def requirement_set_create_snapshot(requirement_set_id: int):
    """Captures the Requirement Set's current state as an immutable
    snapshot (Task 3A-FIX) — idempotent per version, so clicking this twice
    without an intervening edit returns/reuses the same snapshot rather than
    creating a duplicate."""

    with SessionFactory() as session:
        req_svc.create_requirement_set_snapshot(session, requirement_set_id)
        session.commit()
        return redirect(url_for("requirement_set_detail", requirement_set_id=requirement_set_id))


@app.route("/requirements/<int:requirement_set_id>/snapshots/<int:snapshot_id>")
def requirement_set_snapshot_detail(requirement_set_id: int, snapshot_id: int):
    """Read-only view of one immutable historical snapshot — no edit
    routes exist for snapshot content by design (Task 3A-FIX §5)."""

    with SessionFactory() as session:
        snapshot = req_svc.get_snapshot(session, snapshot_id)
        if snapshot is None or snapshot.requirement_set_id != requirement_set_id:
            return redirect(url_for("requirement_set_detail", requirement_set_id=requirement_set_id))
        return render_template(
            "requirement_set_snapshot_detail.html",
            snapshot=snapshot, requirement_set_id=requirement_set_id, active_nav="requirements",
        )


@app.route("/requirements/<int:requirement_set_id>/update", methods=["POST"])
def requirement_set_update(requirement_set_id: int):
    with SessionFactory() as session:
        fields = {
            "name": (request.form.get("name") or "").strip(),
            "description": (request.form.get("description") or "").strip() or None,
            "location_label": (request.form.get("location_label") or "").strip() or None,
            "target_role": (request.form.get("target_role") or "").strip() or None,
        }
        if not fields["name"]:
            return redirect(url_for("requirement_set_detail", requirement_set_id=requirement_set_id))
        req_svc.update_requirement_set(session, requirement_set_id, **fields)
        session.commit()
        return redirect(url_for("requirement_set_detail", requirement_set_id=requirement_set_id))


@app.route("/requirements/<int:requirement_set_id>/toggle-active", methods=["POST"])
def requirement_set_toggle_active(requirement_set_id: int):
    with SessionFactory() as session:
        requirement_set = req_svc.get_requirement_set(session, requirement_set_id)
        if requirement_set is not None:
            req_svc.update_requirement_set(
                session, requirement_set_id, is_active=not requirement_set.is_active, bump_version=False,
            )
            session.commit()
        return redirect(url_for("requirement_set_detail", requirement_set_id=requirement_set_id))


@app.route("/requirements/<int:requirement_set_id>/requirements/add", methods=["POST"])
def requirement_add(requirement_set_id: int):
    with SessionFactory() as session:
        name = (request.form.get("name") or "").strip()
        criticality = request.form.get("criticality")
        trainability = request.form.get("trainability")
        stages = request.form.getlist("assessment_stages")
        if not (name and criticality and trainability and stages):
            return redirect(url_for("requirement_set_detail", requirement_set_id=requirement_set_id))

        req_svc.add_requirement(
            session, requirement_set_id, name=name, criticality=criticality, trainability=trainability,
            assessment_stages=stages,
            description=(request.form.get("description") or "").strip() or None,
            category=(request.form.get("category") or "").strip() or None,
            evidence_positive=(request.form.get("evidence_positive") or "").strip() or None,
            evidence_contrary=(request.form.get("evidence_contrary") or "").strip() or None,
            evidence_insufficient=(request.form.get("evidence_insufficient") or "").strip() or None,
            guidance_notes=(request.form.get("guidance_notes") or "").strip() or None,
        )
        session.commit()
        return redirect(url_for("requirement_set_detail", requirement_set_id=requirement_set_id))


@app.route("/requirements/<int:requirement_set_id>/requirements/<int:requirement_id>/update", methods=["POST"])
def requirement_update(requirement_set_id: int, requirement_id: int):
    with SessionFactory() as session:
        stages = request.form.getlist("assessment_stages")
        req_svc.update_requirement(
            session, requirement_id,
            name=(request.form.get("name") or "").strip(),
            description=(request.form.get("description") or "").strip() or None,
            category=(request.form.get("category") or "").strip() or None,
            criticality=request.form.get("criticality"),
            trainability=request.form.get("trainability"),
            assessment_stages=stages,
            evidence_positive=(request.form.get("evidence_positive") or "").strip() or None,
            evidence_contrary=(request.form.get("evidence_contrary") or "").strip() or None,
            evidence_insufficient=(request.form.get("evidence_insufficient") or "").strip() or None,
            guidance_notes=(request.form.get("guidance_notes") or "").strip() or None,
        )
        session.commit()
        return redirect(url_for("requirement_set_detail", requirement_set_id=requirement_set_id))


@app.route(
    "/requirements/<int:requirement_set_id>/requirements/<int:requirement_id>/toggle-active", methods=["POST"]
)
def requirement_toggle_active(requirement_set_id: int, requirement_id: int):
    with SessionFactory() as session:
        requirement = session.get(m.Requirement, requirement_id)
        if requirement is not None:
            if requirement.is_active:
                req_svc.deactivate_requirement(session, requirement_id)
            else:
                req_svc.reactivate_requirement(session, requirement_id)
            session.commit()
        return redirect(url_for("requirement_set_detail", requirement_set_id=requirement_set_id))


# ---------------------------------------------------------------------------
# Candidate Fit Assessment (Task 3B) — "for this candidate, against this
# exact immutable Requirement Set snapshot, what evidence do we have
# regarding each Requirement?" Routes are thin: every actual operation is
# delegated to `fit_assessment_service.py`. Never a hiring decision, never a
# score, never a ranking — see that module's own docstring.
# ---------------------------------------------------------------------------


@app.route("/candidate/<int:candidate_id>/fit-assessments", methods=["POST"])
def fit_assessment_create(candidate_id: int):
    with SessionFactory() as session:
        requirement_set_id = request.form.get("requirement_set_id", type=int)
        if not requirement_set_id:
            return redirect(url_for("candidate_detail", candidate_id=candidate_id))
        fit_assessment = fa_svc.create_fit_assessment(
            session, candidate_id=candidate_id, requirement_set_id=requirement_set_id,
        )
        session.commit()
        return redirect(url_for("fit_assessment_detail", fit_assessment_id=fit_assessment.id))


@app.route("/fit-assessments/<int:fit_assessment_id>")
def fit_assessment_detail(fit_assessment_id: int):
    with SessionFactory() as session:
        fit_assessment = fa_svc.get_fit_assessment(session, fit_assessment_id)
        if fit_assessment is None:
            return redirect(url_for("home"))
        summary = fa_svc.get_summary(session, fit_assessment_id)
        return render_template(
            "fit_assessment_detail.html",
            fit_assessment=fit_assessment, summary=summary,
            requirement_assessments=fa_svc.list_requirement_assessments(session, fit_assessment_id),
            assessment_statuses=fam.ASSESSMENT_STATUSES,
            evidence_source_types=fam.EVIDENCE_SOURCE_TYPES,
            evidence_classifications=fam.EVIDENCE_CLASSIFICATIONS,
            evidence_relationships=fam.EVIDENCE_RELATIONSHIPS,
            confidence_levels=fam.CONFIDENCE_LEVELS,
            assessment_stages=rm.ASSESSMENT_STAGES,
            active_nav="candidates",
        )


@app.route("/fit-assessments/<int:fit_assessment_id>/refresh", methods=["POST"])
def fit_assessment_refresh(fit_assessment_id: int):
    """Re-runs the résumé-stage matcher against the SAME immutable snapshot
    (task §21) — never switches to a newer live Requirement Set version;
    human-touched Requirement Assessments keep their recorded
    effective_status regardless."""

    with SessionFactory() as session:
        fa_svc.generate_resume_stage_assessment(session, fit_assessment_id)
        session.commit()
        return redirect(url_for("fit_assessment_detail", fit_assessment_id=fit_assessment_id))


@app.route("/fit-assessments/<int:fit_assessment_id>/note", methods=["POST"])
def fit_assessment_add_note(fit_assessment_id: int):
    with SessionFactory() as session:
        note_text = (request.form.get("note_text") or "").strip()
        if note_text:
            fa_svc.add_note(session, fit_assessment_id=fit_assessment_id, note_text=note_text)
            session.commit()
        return redirect(url_for("fit_assessment_detail", fit_assessment_id=fit_assessment_id))


@app.route(
    "/fit-assessments/<int:fit_assessment_id>/requirement-assessments/<int:requirement_assessment_id>/evidence",
    methods=["POST"],
)
def requirement_assessment_add_evidence(fit_assessment_id: int, requirement_assessment_id: int):
    with SessionFactory() as session:
        source_type = request.form.get("source_type")
        evidence_classification = request.form.get("evidence_classification")
        evidence_relationship = request.form.get("evidence_relationship")
        confidence = request.form.get("confidence") or fam.CONFIDENCE_UNKNOWN
        if source_type and evidence_classification and evidence_relationship:
            fa_svc.add_evidence(
                session, requirement_assessment_id, source_type=source_type,
                evidence_classification=evidence_classification, evidence_relationship=evidence_relationship,
                confidence=confidence, evidence_text=(request.form.get("evidence_text") or "").strip() or None,
                source_stage=(request.form.get("source_stage") or "").strip() or None,
                source_reference=(request.form.get("source_reference") or "").strip() or None,
                explanation=(request.form.get("explanation") or "").strip() or None,
                is_system_generated=False,
            )
            session.commit()
        return redirect(url_for("fit_assessment_detail", fit_assessment_id=fit_assessment_id))


@app.route(
    "/fit-assessments/<int:fit_assessment_id>/requirement-assessments/<int:requirement_assessment_id>/note",
    methods=["POST"],
)
def requirement_assessment_add_note(fit_assessment_id: int, requirement_assessment_id: int):
    with SessionFactory() as session:
        note_text = (request.form.get("note_text") or "").strip()
        if note_text:
            fa_svc.add_note(session, requirement_assessment_id=requirement_assessment_id, note_text=note_text)
            session.commit()
        return redirect(url_for("fit_assessment_detail", fit_assessment_id=fit_assessment_id))


@app.route(
    "/fit-assessments/<int:fit_assessment_id>/requirement-assessments/<int:requirement_assessment_id>/confirm",
    methods=["POST"],
)
def requirement_assessment_confirm(fit_assessment_id: int, requirement_assessment_id: int):
    with SessionFactory() as session:
        fa_svc.human_confirm(session, requirement_assessment_id)
        session.commit()
        return redirect(url_for("fit_assessment_detail", fit_assessment_id=fit_assessment_id))


@app.route(
    "/fit-assessments/<int:fit_assessment_id>/requirement-assessments/<int:requirement_assessment_id>/override",
    methods=["POST"],
)
def requirement_assessment_override(fit_assessment_id: int, requirement_assessment_id: int):
    with SessionFactory() as session:
        new_status = request.form.get("new_status")
        if new_status:
            fa_svc.human_override(
                session, requirement_assessment_id, new_status=new_status,
                reason=(request.form.get("reason") or "").strip() or None,
            )
            session.commit()
        return redirect(url_for("fit_assessment_detail", fit_assessment_id=fit_assessment_id))


# ---------------------------------------------------------------------------
# Selection Signals + Review Priority (Task 3C) — "which Applications
# should the Selezionatore review first, and why?" Never a ranking, never
# an automatic discard. Routes are thin: every actual operation is
# delegated to `application_service.py`/`signal_service.py`.
# ---------------------------------------------------------------------------


@app.route("/applications")
def applications_home():
    """The Review Queue (Task 3C-FIX §6) — Applications, never rank
    positions. Filterable/sortable by Review Priority, workflow status,
    target role, application date, and repeated-applicant, via query
    params; priority SORTING is fine, priority RANKING (position numbers)
    is deliberately never shown."""

    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        seed_default_review_priority_policy(session, restaurant_id=restaurant.id)  # idempotent

        priority = request.args.get("priority") or None
        workflow_status = request.args.get("status") or None
        target_role = request.args.get("role") or None
        repeated_only = request.args.get("repeated") == "1"
        sort_by = request.args.get("sort") or "applied_at"

        applications = app_svc.list_applications(
            session, restaurant_id=restaurant.id, priority=priority, workflow_status=workflow_status,
            target_role=target_role, repeated_only=repeated_only, sort_by=sort_by,
        )
        rows = [
            {
                "id": a.id,
                "candidate_id": a.candidate_id,
                "full_name": a.candidate.full_name or "(name not extracted)",
                "target_role": a.target_role or "-",
                "location": a.candidate.location or "-",
                "applied_at": a.applied_at,
                "source": a.candidate.source or "-",
                "priority": a.review_priority_effective or "STANDARD",
                "priority_system": a.review_priority_system or "STANDARD",
                "priority_origin": a.review_priority_origin,
                "priority_reasons": a.review_priority_reasons or [],
                "workflow_status": a.workflow_status,
                "outcome": a.outcome or "-",
                "prior_count": len(app_svc.list_prior_applications(session, a.id)),
                "original_cv_available": _original_cv_available(session, a.candidate),
            }
            for a in applications
        ]
        target_roles = sorted({a.target_role for a in applications if a.target_role})

        return render_template(
            "applications_home.html", client_name=restaurant.name, applications=rows, active_nav="applications",
            priority_categories=sigm.REVIEW_PRIORITY_CATEGORIES, workflow_statuses=apm.WORKFLOW_STATUSES,
            target_roles=target_roles, filters={
                "priority": priority, "status": workflow_status, "role": target_role,
                "repeated": repeated_only, "sort": sort_by,
            },
            pending_identity_matches=len(id_svc.list_pending_matches(session, restaurant_id=restaurant.id)),
        )


@app.route("/applications/<int:application_id>")
def application_detail(application_id: int):
    with SessionFactory() as session:
        application = app_svc.get_application(session, application_id)
        if application is None:
            return redirect(url_for("applications_home"))

        observations = sig_svc.list_observations(session, application_id)
        prior_applications = app_svc.list_prior_applications(session, application_id)
        change_summary = app_svc.get_application_change_summary(session, application_id)
        notes = app_svc.list_notes(session, application_id)
        pending_matches = [
            match for match in id_svc.list_pending_matches(session, restaurant_id=application.restaurant_id)
            if match.application_id == application_id
        ]
        other_persons = [
            p for p in id_svc.list_persons(session, restaurant_id=application.restaurant_id)
            if p.id != application.person_id
        ]
        phone_interview_plan = pi_svc.get_plan_for_application(session, application_id)
        in_person_interview_plan = ip_svc.get_plan_for_application(session, application_id)
        has_fit_assessment = bool(fa_svc.list_fit_assessments_for_candidate(session, application.candidate_id))
        primary_screening_run = ps_svc.get_latest_run_for_application(session, application_id)

        # Task 5A — Stage/Outcome are available from the Application view
        # itself (task §31), not only from the Decision Summary page.
        seed_default_selection_outcomes(session, restaurant_id=application.restaurant_id)  # idempotent
        current_outcome_decision = outcome_svc.get_current_outcome_decision(session, application_id)
        active_flags = flag_svc.list_active_flags_for_application(session, application_id)
        current_queue = queue_svc.get_current_queue(session, application_id)

        return render_template(
            "application_detail.html",
            application=application, observations=observations, prior_applications=prior_applications,
            phone_interview_plan=phone_interview_plan, in_person_interview_plan=in_person_interview_plan,
            primary_screening_run=primary_screening_run, has_fit_assessment=has_fit_assessment,
            profile=persistence.to_profile(application.candidate),
            signal_statuses=sigm.SIGNAL_STATUSES, priority_categories=sigm.REVIEW_PRIORITY_CATEGORIES,
            outcome_options=sigm.APPLICATION_OUTCOMES, workflow_statuses=apm.WORKFLOW_STATUSES,
            decision_statuses=apm.DECISION_STATUSES,
            evidence_source_types=fam.EVIDENCE_SOURCE_TYPES, evidence_classifications=fam.EVIDENCE_CLASSIFICATIONS,
            evidence_relationships=fam.EVIDENCE_RELATIONSHIPS, confidence_levels=fam.CONFIDENCE_LEVELS,
            assessment_stages=rm.ASSESSMENT_STAGES,
            change_summary=change_summary, notes=notes, pending_matches=pending_matches,
            other_persons=other_persons, original_cv_available=_original_cv_available(session, application.candidate),
            stages=stgm.STAGES, current_outcome_decision=current_outcome_decision,
            outcome_definitions=outcome_svc.list_outcome_definitions(session, restaurant_id=application.restaurant_id),
            active_flags=active_flags, current_queue=current_queue,
            active_nav="applications",
        )


@app.route("/applications/<int:application_id>/dossier")
def application_dossier(application_id: int):
    """Task 5B — the Operational Candidate Dossier: one Application-centric
    page a Selezionatore can read in ~2-3 minutes, aggregating Primary
    Screening, Evidence, Trainable Gaps, Interview journey, Decision/Outcome
    history, Information/Events, candidate history, and Notes. Never a
    parallel data source — `dossier_service.get_application_dossier` is a
    pure aggregator over the same authoritative services every other
    Selection screen already uses."""

    with SessionFactory() as session:
        application = app_svc.get_application(session, application_id)
        if application is None:
            return redirect(url_for("applications_home"))

        dossier = dossier_svc.get_application_dossier(session, application_id)
        # Persists any Trainable Gaps newly generated while building the
        # Dossier (idempotent — never overwrites an existing gap's level).
        session.commit()

        seed_default_selection_outcomes(session, restaurant_id=application.restaurant_id)  # idempotent
        outcome_definitions = outcome_svc.list_outcome_definitions(session, restaurant_id=application.restaurant_id)

        return render_template(
            "dossier.html", dossier=dossier, application=application,
            original_cv_available=_original_cv_available(session, application.candidate),
            initial_levels=tgm.INITIAL_LEVELS, level_descriptions=tgm.LEVEL_DESCRIPTIONS,
            outcome_definitions=outcome_definitions, stages=stgm.STAGES,
            active_nav="applications",
        )


@app.route("/trainable-gaps/<int:gap_id>/review", methods=["POST"])
def trainable_gap_review(gap_id: int):
    """The Dossier's Trainable Gap edit-modal target (task §19/§20/§21) —
    a thin route delegating entirely to `trainable_gap_service.
    set_selezionatore_level`/`.add_note`, which enforce the mandatory-
    reason-on-difference rule and never touch `rf_one_initial_level`."""

    with SessionFactory() as session:
        gap = tg_svc.get_trainable_gap(session, gap_id)
        if gap is None:
            return redirect(url_for("applications_home"))
        application_id = gap.application_id

        actor = (request.form.get("actor") or "").strip() or None
        level = request.form.get("level", type=int)
        if level is not None:
            try:
                own_svc.assert_can_operate(session, application_id, actor)
                tg_svc.set_selezionatore_level(
                    session, gap_id, level=level,
                    reason=(request.form.get("reason") or "").strip() or None,
                    performed_by=actor,
                )
                session.commit()
            except ValueError:
                session.rollback()

        note_text = (request.form.get("note_text") or "").strip()
        if note_text:
            tg_svc.add_note(session, gap_id, note_text)
            session.commit()

        return redirect(request.form.get("next") or url_for("application_dossier", application_id=application_id))


@app.route("/applications/<int:application_id>/take-in-charge", methods=["POST"])
def application_take_in_charge(application_id: int):
    """Task 5C §7 — the explicit "TAKE IN CHARGE" action; ownership is
    never implied merely by viewing an Application read-only."""

    with SessionFactory() as session:
        owner_name = (request.form.get("owner_name") or "").strip()
        if owner_name:
            try:
                own_svc.take_in_charge(session, application_id, owner_name=owner_name)
                session.commit()
            except ValueError:
                session.rollback()
        return redirect(request.form.get("next") or url_for("application_dossier", application_id=application_id))


@app.route("/applications/<int:application_id>/reassign", methods=["POST"])
def application_reassign(application_id: int):
    """Task 5C §9 — reassignment by the current owner or a Selezionatore
    with configured superior authority; always requires a reason."""

    with SessionFactory() as session:
        new_owner = (request.form.get("new_owner") or "").strip()
        performed_by = (request.form.get("performed_by") or "").strip()
        reason = (request.form.get("reason") or "").strip()
        if new_owner and performed_by:
            try:
                own_svc.reassign(session, application_id, new_owner=new_owner, performed_by=performed_by, reason=reason)
                session.commit()
            except ValueError:
                session.rollback()
        return redirect(request.form.get("next") or url_for("application_dossier", application_id=application_id))


@app.route("/applications/<int:application_id>/workflow-status", methods=["POST"])
def application_set_workflow_status(application_id: int):
    """A legacy, backward-compatible control (Task 5A-FIX §5) — the
    Selezionatore's choice is translated into the authoritative Stage
    transition and/or Outcome application via `workflow_projection_
    service.apply_legacy_workflow_action`; `workflow_status` itself is
    only ever refreshed as the resulting projection, never written
    directly here anymore (Task 3C-FIX §7's original behavior)."""

    with SessionFactory() as session:
        new_status = request.form.get("new_status")
        if new_status:
            try:
                wf_svc.apply_legacy_workflow_action(
                    session, application_id, new_status,
                    reason=(request.form.get("reason") or "").strip() or None,
                )
                session.commit()
            except ValueError:
                session.rollback()
        return redirect(url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/notes", methods=["POST"])
def application_add_note_entry(application_id: int):
    with SessionFactory() as session:
        note_text = (request.form.get("note_text") or "").strip()
        if note_text:
            app_svc.add_note(session, application_id, note_text)
            session.commit()
        return redirect(request.form.get("next") or url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/stage", methods=["POST"])
def application_set_stage(application_id: int):
    """Task 5A §2/§3 — the Selezionatore may move an Application to ANY
    Stage, forward, backward, repeated, or skipped; no validation here
    restricts which Stage may follow which."""

    with SessionFactory() as session:
        new_stage = request.form.get("new_stage")
        if new_stage:
            actor = (request.form.get("actor") or "").strip() or None
            communication_mode = (request.form.get("communication_mode") or "").strip() or None
            try:
                own_svc.assert_can_operate(session, application_id, actor)
                transition = stage_svc.set_stage(
                    session, application_id, new_stage, performed_by=actor,
                    note_text=(request.form.get("note_text") or "").strip() or None,
                )
                # Task 5D §7/§9 — communication is a CONSEQUENCE of the Stage
                # transition just recorded above, never itself the decision.
                application = app_svc.get_application(session, application_id)
                comm_svc.on_stage_transition(
                    session, application, transition, communication_mode=communication_mode, performed_by=actor,
                )
                session.commit()
            except ValueError:
                session.rollback()
        return redirect(request.form.get("next") or url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/outcome/apply", methods=["POST"])
def application_apply_outcome(application_id: int):
    """Task 5A §9 — an Outcome may be applied at ANY moment, regardless of
    Stage or completion of Primary Screening/Phone/In-Person."""

    with SessionFactory() as session:
        outcome_definition_id = request.form.get("outcome_definition_id", type=int)
        if outcome_definition_id:
            actor = (request.form.get("actor") or "").strip() or None
            try:
                own_svc.assert_can_operate(session, application_id, actor)
                decision = outcome_svc.apply_outcome(
                    session, application_id, outcome_definition_id,
                    reason=(request.form.get("reason") or "").strip() or None,
                    note_text=(request.form.get("note_text") or "").strip() or None,
                    performed_by=actor,
                )
                # Task 5D §6/§8/§9 — communication is a CONSEQUENCE of the
                # Outcome decision just recorded above, never itself the
                # decision (task §10).
                application = app_svc.get_application(session, application_id)
                comm_svc.on_outcome_decision(session, application, decision)
                session.commit()
            except ValueError:
                session.rollback()
        return redirect(request.form.get("next") or url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/outcome/reopen", methods=["POST"])
def application_reopen(application_id: int):
    """Task 5A §7 — even a CLOSED Application may always be reopened by a
    deliberate Selezionatore action; never technically blocked."""

    with SessionFactory() as session:
        outcome_definition_id = request.form.get("outcome_definition_id", type=int)
        if outcome_definition_id:
            actor = (request.form.get("actor") or "").strip() or None
            try:
                own_svc.assert_can_operate(session, application_id, actor)
                outcome_svc.reopen_application(
                    session, application_id, outcome_definition_id,
                    reason=(request.form.get("reason") or "").strip() or None,
                    note_text=(request.form.get("note_text") or "").strip() or None,
                    performed_by=actor,
                )
                session.commit()
            except ValueError:
                session.rollback()
        return redirect(request.form.get("next") or url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/information-event", methods=["POST"])
def application_record_information_event(application_id: int):
    """Task 5A-ALIGN §3/§15 — a factual INFORMATION/EVENT report (e.g. "a
    server received a phone call from the candidate saying they are
    withdrawing"), kept clearly separate from a Selezionatore DECISION.
    Recording this NEVER itself changes Stage/Outcome/lifecycle — see
    `application_service.record_information_event`'s own docstring."""

    with SessionFactory() as session:
        description = (request.form.get("description") or "").strip()
        if description:
            app_svc.record_information_event(
                session, application_id, description=description,
                event_type=(request.form.get("event_type") or "").strip() or None,
                reported_by=(request.form.get("reported_by") or "").strip() or None,
                original_source=(request.form.get("original_source") or "").strip() or None,
            )
            session.commit()
        return redirect(request.form.get("next") or url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/flags/new", methods=["POST"])
def application_create_flag(application_id: int):
    with SessionFactory() as session:
        application = app_svc.get_application(session, application_id)
        name = (request.form.get("name") or "").strip()
        if application is not None and name:
            flag_svc.create_flag(
                session, person_id=application.person_id, restaurant_id=application.restaurant_id, name=name,
                description=(request.form.get("description") or "").strip() or None,
                originating_application_id=application_id,
                reason=(request.form.get("reason") or "").strip() or None,
                scope=request.form.get("scope") or om.DEFAULT_FLAG_SCOPE,
                role_scope=(request.form.get("role_scope") or "").strip() or None,
                location_scope=(request.form.get("location_scope") or "").strip() or None,
                operational_effect=request.form.get("operational_effect") or om.DEFAULT_FLAG_OPERATIONAL_EFFECT,
                note=(request.form.get("note") or "").strip() or None,
                expires_after_days=request.form.get("expires_after_days", type=int),
            )
            session.commit()
        return redirect(request.form.get("next") or url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/flags/<int:flag_id>/deactivate", methods=["POST"])
def application_deactivate_flag(application_id: int, flag_id: int):
    with SessionFactory() as session:
        flag_svc.deactivate_flag(session, flag_id)
        session.commit()
        return redirect(request.form.get("next") or url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/reminders/<int:reminder_id>/resolve", methods=["POST"])
def application_resolve_reminder(application_id: int, reminder_id: int):
    with SessionFactory() as session:
        outcome_svc.resolve_reminder(session, reminder_id)
        session.commit()
        return redirect(url_for("application_decision", application_id=application_id))


@app.route("/applications/<int:application_id>/decision")
def application_decision(application_id: int):
    """Task 5A §23 — the consolidated Decision Summary: current-state,
    usable at any moment, never a mandatory final phase."""

    with SessionFactory() as session:
        application = app_svc.get_application(session, application_id)
        if application is None:
            return redirect(url_for("applications_home"))

        seed_default_selection_outcomes(session, restaurant_id=application.restaurant_id)  # idempotent (also seeds default queues)
        summary = dec_svc.get_decision_summary(session, application_id)
        summary_text = dec_svc.generate_current_summary_text(session, application_id)
        notes_history = notes_svc.get_selection_notes_history(session, application_id)

        return render_template(
            "decision_summary.html", application=application, summary=summary, summary_text=summary_text,
            notes_history=notes_history, stages=stgm.STAGES,
            outcome_definitions=outcome_svc.list_outcome_definitions(session, restaurant_id=application.restaurant_id),
            lifecycle_states=om.LIFECYCLE_STATES,
            queues=queue_svc.list_queues(session, restaurant_id=application.restaurant_id),
            original_cv_available=_original_cv_available(session, application.candidate),
            active_nav="applications",
        )


@app.route("/applications/<int:application_id>/reassign-person", methods=["POST"])
def application_reassign_person(application_id: int):
    """Direct manual identity correction (Task 3C-FIX §2), independent of
    any system-generated suggestion — e.g. the Selezionatore recognizes the
    same person by other means."""

    with SessionFactory() as session:
        target_person_id = request.form.get("target_person_id", type=int)
        if target_person_id:
            id_svc.reassign_application(
                session, application_id, target_person_id=target_person_id,
                note=(request.form.get("note") or "").strip() or None,
            )
            session.commit()
        return redirect(url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/refresh", methods=["POST"])
def application_refresh_signals(application_id: int):
    """Re-runs résumé-stage Signal detection and recomputes Review Priority
    — human-touched Signal Observations and a Selezionatore's Review
    Priority override are both left untouched (task's own system/effective
    distinction)."""

    with SessionFactory() as session:
        sig_svc.generate_resume_stage_signals(session, application_id)
        session.commit()
        return redirect(url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/target-role", methods=["POST"])
def application_set_target_role(application_id: int):
    with SessionFactory() as session:
        target_role = (request.form.get("target_role") or "").strip() or None
        app_svc.set_target_role(session, application_id, target_role)
        session.commit()
        return redirect(url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/outcome", methods=["POST"])
def application_set_outcome(application_id: int):
    with SessionFactory() as session:
        outcome = request.form.get("outcome")
        if outcome:
            app_svc.set_outcome(session, application_id, outcome)
            session.commit()
        return redirect(url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/priority/confirm", methods=["POST"])
def application_priority_confirm(application_id: int):
    with SessionFactory() as session:
        sig_svc.human_confirm_priority(session, application_id)
        session.commit()
        return redirect(url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/priority/override", methods=["POST"])
def application_priority_override(application_id: int):
    with SessionFactory() as session:
        new_priority = request.form.get("new_priority")
        if new_priority:
            sig_svc.human_override_priority(
                session, application_id, new_priority=new_priority,
                reason=(request.form.get("reason") or "").strip() or None,
            )
            session.commit()
        return redirect(url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/signal-observations/<int:observation_id>/confirm", methods=["POST"])
def signal_observation_confirm(application_id: int, observation_id: int):
    with SessionFactory() as session:
        sig_svc.human_confirm(session, observation_id)
        session.commit()
        return redirect(url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/signal-observations/<int:observation_id>/override", methods=["POST"])
def signal_observation_override(application_id: int, observation_id: int):
    with SessionFactory() as session:
        new_status = request.form.get("new_status")
        if new_status:
            sig_svc.human_override(
                session, observation_id, new_status=new_status,
                reason=(request.form.get("reason") or "").strip() or None,
            )
            session.commit()
        return redirect(url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/signal-observations/<int:observation_id>/evidence", methods=["POST"])
def signal_observation_add_evidence(application_id: int, observation_id: int):
    with SessionFactory() as session:
        source_type = request.form.get("source_type")
        evidence_classification = request.form.get("evidence_classification")
        evidence_relationship = request.form.get("evidence_relationship")
        confidence = request.form.get("confidence") or fam.CONFIDENCE_UNKNOWN
        if source_type and evidence_classification and evidence_relationship:
            sig_svc.add_evidence(
                session, observation_id, source_type=source_type,
                evidence_classification=evidence_classification, evidence_relationship=evidence_relationship,
                confidence=confidence, evidence_text=(request.form.get("evidence_text") or "").strip() or None,
                source_stage=(request.form.get("source_stage") or "").strip() or None,
                source_reference=(request.form.get("source_reference") or "").strip() or None,
                explanation=(request.form.get("explanation") or "").strip() or None,
                is_system_generated=False,
            )
            session.commit()
        return redirect(url_for("application_detail", application_id=application_id))


@app.route("/signals")
def signals_home():
    """Selection Signal Definition authoring (Task 3C-FIX §3) — a
    restaurant creates/edits/activates/deactivates its OWN Signal
    Definitions here; the universal Signal framework
    (`core/signal_model.py`/`signal_service.py`) has no knowledge any
    specific restaurant's definitions exist. Seeded examples may remain
    alongside restaurant-authored ones."""

    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        seed_default_review_priority_policy(session, restaurant_id=restaurant.id)  # idempotent
        definitions = sig_svc.list_signal_definitions(session, restaurant_id=restaurant.id, active_only=False)
        by_family = {}
        for d in definitions:
            by_family.setdefault(d.signal_family, []).append(d)
        return render_template(
            "signals_home.html", client_name=restaurant.name, by_family=by_family,
            signal_families=sigm.SIGNAL_FAMILIES, assessment_stages=rm.ASSESSMENT_STAGES,
            evidence_source_types=fam.EVIDENCE_SOURCE_TYPES, active_nav="signals",
        )


@app.route("/signals/new", methods=["POST"])
def signal_definition_create():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        name = (request.form.get("name") or "").strip()
        signal_family = request.form.get("signal_family")
        if not (name and signal_family):
            return redirect(url_for("signals_home"))
        sig_svc.create_signal_definition(
            session, restaurant_id=restaurant.id, name=name, signal_family=signal_family,
            signal_subtype=(request.form.get("signal_subtype") or "").strip() or None,
            description=(request.form.get("description") or "").strip() or None,
            assessment_stages=request.form.getlist("assessment_stages"),
            evidence_sources_allowed=request.form.getlist("evidence_sources_allowed"),
            detection_guidance=(request.form.get("detection_guidance") or "").strip() or None,
            evidence_positive=(request.form.get("evidence_positive") or "").strip() or None,
            evidence_contrary=(request.form.get("evidence_contrary") or "").strip() or None,
            evidence_insufficient=(request.form.get("evidence_insufficient") or "").strip() or None,
        )
        session.commit()
        return redirect(url_for("signals_home"))


@app.route("/signals/<int:signal_definition_id>/update", methods=["POST"])
def signal_definition_update(signal_definition_id: int):
    with SessionFactory() as session:
        sig_svc.update_signal_definition(
            session, signal_definition_id,
            name=(request.form.get("name") or "").strip(),
            signal_family=request.form.get("signal_family"),
            signal_subtype=(request.form.get("signal_subtype") or "").strip() or None,
            description=(request.form.get("description") or "").strip() or None,
            assessment_stages=request.form.getlist("assessment_stages"),
            evidence_sources_allowed=request.form.getlist("evidence_sources_allowed"),
            detection_guidance=(request.form.get("detection_guidance") or "").strip() or None,
            evidence_positive=(request.form.get("evidence_positive") or "").strip() or None,
            evidence_contrary=(request.form.get("evidence_contrary") or "").strip() or None,
            evidence_insufficient=(request.form.get("evidence_insufficient") or "").strip() or None,
        )
        session.commit()
        return redirect(url_for("signals_home"))


@app.route("/signals/<int:signal_definition_id>/toggle-active", methods=["POST"])
def signal_definition_toggle_active(signal_definition_id: int):
    with SessionFactory() as session:
        definition = sig_svc.get_signal_definition(session, signal_definition_id)
        if definition is not None:
            if definition.is_active:
                sig_svc.deactivate_signal_definition(session, signal_definition_id)
            else:
                sig_svc.reactivate_signal_definition(session, signal_definition_id)
            session.commit()
        return redirect(url_for("signals_home"))


# ---------------------------------------------------------------------------
# Review Priority Policy authoring (Task 3C-FIX §4) — HOW MUCH a detected
# Signal affects Review Priority, kept structurally separate from Signal
# Definitions (WHAT is detected) above.
# ---------------------------------------------------------------------------


@app.route("/priority-policies")
def priority_policies_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        seed_default_review_priority_policy(session, restaurant_id=restaurant.id)  # idempotent
        policies = sig_svc.list_policies(session, restaurant_id=restaurant.id)
        return render_template(
            "priority_policies_home.html", client_name=restaurant.name, policies=policies,
            active_nav="priority-policies",
        )


@app.route("/priority-policies/new", methods=["POST"])
def priority_policy_create():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        name = (request.form.get("name") or "").strip()
        if not name:
            return redirect(url_for("priority_policies_home"))
        policy = sig_svc.create_policy(session, restaurant_id=restaurant.id, name=name)
        session.commit()
        return redirect(url_for("priority_policy_detail", policy_id=policy.id))


@app.route("/priority-policies/<int:policy_id>")
def priority_policy_detail(policy_id: int):
    with SessionFactory() as session:
        policy = sig_svc.get_policy(session, policy_id)
        if policy is None:
            return redirect(url_for("priority_policies_home"))
        definitions = sig_svc.list_signal_definitions(session, restaurant_id=policy.restaurant_id, active_only=False)
        return render_template(
            "priority_policy_detail.html", policy=policy, definitions=definitions,
            signal_statuses=sigm.SIGNAL_STATUSES, priority_contributions=sigm.PRIORITY_CONTRIBUTIONS,
            active_nav="priority-policies",
        )


@app.route("/priority-policies/<int:policy_id>/update", methods=["POST"])
def priority_policy_update(policy_id: int):
    with SessionFactory() as session:
        name = (request.form.get("name") or "").strip()
        if name:
            sig_svc.update_policy(session, policy_id, name=name)
            session.commit()
        return redirect(url_for("priority_policy_detail", policy_id=policy_id))


@app.route("/priority-policies/<int:policy_id>/toggle-active", methods=["POST"])
def priority_policy_toggle_active(policy_id: int):
    with SessionFactory() as session:
        policy = sig_svc.get_policy(session, policy_id)
        if policy is not None:
            if policy.is_active:
                sig_svc.deactivate_policy(session, policy_id)
            else:
                sig_svc.reactivate_policy(session, policy_id)
            session.commit()
        return redirect(url_for("priority_policy_detail", policy_id=policy_id))


@app.route("/priority-policies/<int:policy_id>/rules/add", methods=["POST"])
def priority_policy_rule_add(policy_id: int):
    with SessionFactory() as session:
        signal_definition_id = request.form.get("signal_definition_id", type=int)
        observed_status = request.form.get("observed_status")
        contribution = request.form.get("contribution")
        if signal_definition_id and observed_status and contribution:
            sig_svc.add_policy_rule(
                session, policy_id, signal_definition_id=signal_definition_id, observed_status=observed_status,
                contribution=contribution,
            )
            session.commit()
        return redirect(url_for("priority_policy_detail", policy_id=policy_id))


@app.route("/priority-policies/<int:policy_id>/rules/<int:rule_id>/update", methods=["POST"])
def priority_policy_rule_update(policy_id: int, rule_id: int):
    with SessionFactory() as session:
        contribution = request.form.get("contribution")
        if contribution:
            sig_svc.update_policy_rule(session, rule_id, contribution=contribution)
            session.commit()
        return redirect(url_for("priority_policy_detail", policy_id=policy_id))


@app.route("/priority-policies/<int:policy_id>/rules/<int:rule_id>/toggle-active", methods=["POST"])
def priority_policy_rule_toggle_active(policy_id: int, rule_id: int):
    with SessionFactory() as session:
        rule = session.get(m.ReviewPriorityPolicyRule, rule_id)
        if rule is not None:
            if rule.is_active:
                sig_svc.deactivate_policy_rule(session, rule_id)
            else:
                sig_svc.reactivate_policy_rule(session, rule_id)
            session.commit()
        return redirect(url_for("priority_policy_detail", policy_id=policy_id))


@app.route("/priority-policies/<int:policy_id>/rules/<int:rule_id>/remove", methods=["POST"])
def priority_policy_rule_remove(policy_id: int, rule_id: int):
    with SessionFactory() as session:
        sig_svc.remove_policy_rule(session, rule_id)
        session.commit()
        return redirect(url_for("priority_policy_detail", policy_id=policy_id))


# ---------------------------------------------------------------------------
# CandidatePerson identity resolution (Task 3C-FIX §1/§2) — possible-match
# suggestions the Selezionatore must explicitly confirm or reject; never an
# automatic merge.
# ---------------------------------------------------------------------------


@app.route("/identity-matches")
def identity_matches_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        matches = id_svc.list_pending_matches(session, restaurant_id=restaurant.id)
        return render_template(
            "identity_matches.html", client_name=restaurant.name, matches=matches, active_nav="identity-matches",
        )


@app.route("/identity-matches/<int:match_id>/confirm", methods=["POST"])
def identity_match_confirm(match_id: int):
    with SessionFactory() as session:
        match = id_svc.confirm_match(session, match_id, note=(request.form.get("note") or "").strip() or None)
        session.commit()
        return redirect(request.form.get("next") or url_for("application_detail", application_id=match.application_id))


@app.route("/identity-matches/<int:match_id>/reject", methods=["POST"])
def identity_match_reject(match_id: int):
    with SessionFactory() as session:
        match = id_svc.reject_match(session, match_id, note=(request.form.get("note") or "").strip() or None)
        session.commit()
        return redirect(request.form.get("next") or url_for("application_detail", application_id=match.application_id))


# ---------------------------------------------------------------------------
# Phone Interview Question Library (Task 4A §3/§18/§24) — restaurant-
# configured Core (and Courtesy) Questions. RF-One supplies the framework;
# the restaurant supplies the actual questions (never hard-coded here).
# ---------------------------------------------------------------------------


@app.route("/phone-interview-questions")
def phone_interview_questions_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        seed_romes_flavours_phone_interview_questions(session, restaurant_id=restaurant.id)  # idempotent
        definitions = pi_svc.list_question_definitions(session, restaurant_id=restaurant.id, active_only=False)
        core_definitions = [d for d in definitions if not d.is_courtesy]
        courtesy_definitions = [d for d in definitions if d.is_courtesy]
        return render_template(
            "phone_interview_questions_home.html", client_name=restaurant.name,
            core_definitions=core_definitions, courtesy_definitions=courtesy_definitions,
            importance_levels=pim.IMPORTANCE_LEVELS, assessment_stages=rm.ASSESSMENT_STAGES,
            active_nav="phone-interview-questions",
        )


@app.route("/phone-interview-questions/new", methods=["POST"])
def phone_interview_question_create():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        question_text = (request.form.get("question_text") or "").strip()
        if not question_text:
            return redirect(url_for("phone_interview_questions_home"))
        pi_svc.create_question_definition(
            session, restaurant_id=restaurant.id, question_text=question_text,
            target_role=(request.form.get("target_role") or "").strip() or None,
            objective=(request.form.get("objective") or "").strip() or None,
            importance=request.form.get("importance") or pim.MEDIUM,
            is_sine_qua_non=request.form.get("is_sine_qua_non") == "on",
            mandatory_within_selection_process=request.form.get("mandatory_within_selection_process") == "on",
            is_courtesy=request.form.get("is_courtesy") == "on",
            assessment_stages=request.form.getlist("assessment_stages") or [rm.PHONE_INTERVIEW],
            follow_up_guidance=(request.form.get("follow_up_guidance") or "").strip() or None,
        )
        session.commit()
        return redirect(url_for("phone_interview_questions_home"))


@app.route("/phone-interview-questions/<int:definition_id>/update", methods=["POST"])
def phone_interview_question_update(definition_id: int):
    with SessionFactory() as session:
        pi_svc.update_question_definition(
            session, definition_id,
            question_text=(request.form.get("question_text") or "").strip(),
            target_role=(request.form.get("target_role") or "").strip() or None,
            objective=(request.form.get("objective") or "").strip() or None,
            importance=request.form.get("importance") or pim.MEDIUM,
            is_sine_qua_non=request.form.get("is_sine_qua_non") == "on",
            mandatory_within_selection_process=request.form.get("mandatory_within_selection_process") == "on",
            is_courtesy=request.form.get("is_courtesy") == "on",
            assessment_stages=request.form.getlist("assessment_stages") or [rm.PHONE_INTERVIEW],
            follow_up_guidance=(request.form.get("follow_up_guidance") or "").strip() or None,
        )
        session.commit()
        return redirect(url_for("phone_interview_questions_home"))


@app.route("/phone-interview-questions/<int:definition_id>/toggle-active", methods=["POST"])
def phone_interview_question_toggle_active(definition_id: int):
    with SessionFactory() as session:
        definition = pi_svc.get_question_definition(session, definition_id)
        if definition is not None:
            if definition.is_active:
                pi_svc.deactivate_question_definition(session, definition_id)
            else:
                pi_svc.reactivate_question_definition(session, definition_id)
            session.commit()
        return redirect(url_for("phone_interview_questions_home"))


# ---------------------------------------------------------------------------
# Phone Interview (Task 4A) — begins when an Application reaches
# ADVANCE_TO_PHONE. Routes are thin: every actual operation is delegated to
# `phone_interview_service.py`. Never a hiring decision, never a score,
# never a rigid questionnaire that must always be completed in full.
# ---------------------------------------------------------------------------


@app.route("/applications/<int:application_id>/phone-interview", methods=["POST"])
def phone_interview_create(application_id: int):
    with SessionFactory() as session:
        application = app_svc.get_application(session, application_id)
        if application is not None:
            seed_romes_flavours_phone_interview_questions(session, restaurant_id=application.restaurant_id)  # idempotent
        try:
            plan = pi_svc.create_plan(session, application_id)
        except ValueError:
            session.rollback()
            return redirect(url_for("application_detail", application_id=application_id))
        session.commit()
        return redirect(url_for("phone_interview_detail", plan_id=plan.id))


def _phone_interview_context(session, plan) -> dict:
    application = session.get(m.Application, plan.application_id)
    observations = sig_svc.list_observations(session, application.id)
    snapshot = session.get(m.RequirementSetSnapshot, plan.requirement_set_snapshot_id)
    return {
        "plan": plan, "application": application, "profile": persistence.to_profile(application.candidate),
        "observations": observations,
        "snapshot_items_by_id": {item.id: item for item in snapshot.items},
        "signal_definitions_by_id": {o.signal_definition_id: o.signal_definition for o in observations},
        "fit_summary": fa_svc.get_summary(session, plan.fit_assessment_id),
        "remaining_questions": pi_svc.get_ordered_remaining_questions(session, plan.id),
        "history_questions": [
            q for q in pi_svc.list_question_instances(session, plan.id)
            if q.status not in (pim.NOT_ASKED,) and q.source_type != pim.COURTESY
        ],
        "courtesy_questions": pi_svc.get_courtesy_questions(session, plan.id),
        "carried_forward_questions": pi_svc.get_carried_forward_questions(session, plan.id),
        "original_cv_available": _original_cv_available(session, application.candidate),
        "plan_statuses": pim.PLAN_STATUSES, "question_statuses": pim.QUESTION_INSTANCE_STATUSES,
        "gate_evaluations": pim.GATE_EVALUATIONS, "importance_levels": pim.IMPORTANCE_LEVELS,
        "post_interview_decisions": apm.POST_PHONE_INTERVIEW_DECISIONS,
        "priority_categories": sigm.REVIEW_PRIORITY_CATEGORIES,
        "evidence_relationships": fam.EVIDENCE_RELATIONSHIPS, "evidence_classifications": fam.EVIDENCE_CLASSIFICATIONS,
        "confidence_levels": fam.CONFIDENCE_LEVELS,
        "active_nav": "applications",
    }


@app.route("/phone-interviews/<int:plan_id>")
def phone_interview_detail(plan_id: int):
    with SessionFactory() as session:
        plan = pi_svc.get_plan(session, plan_id)
        if plan is None:
            return redirect(url_for("applications_home"))
        return render_template("phone_interview_detail.html", **_phone_interview_context(session, plan))


@app.route("/phone-interviews/<int:plan_id>/refresh", methods=["POST"])
def phone_interview_refresh(plan_id: int):
    with SessionFactory() as session:
        pi_svc.refresh_plan(session, plan_id)
        session.commit()
        return redirect(url_for("phone_interview_detail", plan_id=plan_id))


@app.route("/phone-interviews/<int:plan_id>/start", methods=["POST"])
def phone_interview_start(plan_id: int):
    with SessionFactory() as session:
        pi_svc.start_interview(session, plan_id)
        session.commit()
        return redirect(url_for("phone_interview_detail", plan_id=plan_id))


@app.route("/phone-interviews/<int:plan_id>/notes", methods=["POST"])
def phone_interview_set_notes(plan_id: int):
    with SessionFactory() as session:
        pi_svc.set_notes(session, plan_id, (request.form.get("notes") or "").strip() or None)
        session.commit()
        return redirect(url_for("phone_interview_detail", plan_id=plan_id))


@app.route("/phone-interviews/<int:plan_id>/questions/<int:question_instance_id>/answer", methods=["POST"])
def phone_interview_record_answer(plan_id: int, question_instance_id: int):
    with SessionFactory() as session:
        status = request.form.get("status")
        if status:
            pi_svc.record_answer(
                session, question_instance_id, status=status,
                answer_text=request.form.get("answer_text"),
                selezionatore_note=request.form.get("selezionatore_note"),
            )
            session.commit()
        return redirect(url_for("phone_interview_detail", plan_id=plan_id))


@app.route("/phone-interviews/<int:plan_id>/questions/<int:question_instance_id>/gate", methods=["POST"])
def phone_interview_set_gate(plan_id: int, question_instance_id: int):
    with SessionFactory() as session:
        gate_evaluation = request.form.get("gate_evaluation")
        if gate_evaluation:
            pi_svc.set_gate_evaluation(
                session, question_instance_id, gate_evaluation=gate_evaluation,
                note=(request.form.get("note") or "").strip() or None,
            )
            session.commit()
        return redirect(url_for("phone_interview_detail", plan_id=plan_id))


@app.route("/phone-interviews/<int:plan_id>/questions/<int:question_instance_id>/follow-up", methods=["POST"])
def phone_interview_add_follow_up(plan_id: int, question_instance_id: int):
    with SessionFactory() as session:
        question_text = (request.form.get("question_text") or "").strip()
        if question_text:
            pi_svc.add_follow_up_question(
                session, question_instance_id, question_text=question_text,
                objective=(request.form.get("objective") or "").strip() or None,
                importance=request.form.get("importance") or None,
            )
            session.commit()
        return redirect(url_for("phone_interview_detail", plan_id=plan_id))


@app.route("/phone-interviews/<int:plan_id>/questions/<int:question_instance_id>/fit-evidence", methods=["POST"])
def phone_interview_add_fit_evidence(plan_id: int, question_instance_id: int):
    with SessionFactory() as session:
        requirement_snapshot_item_id = request.form.get("requirement_snapshot_item_id", type=int)
        evidence_relationship = request.form.get("evidence_relationship")
        if requirement_snapshot_item_id and evidence_relationship:
            pi_svc.record_answer_as_fit_evidence(
                session, question_instance_id, requirement_snapshot_item_id=requirement_snapshot_item_id,
                evidence_relationship=evidence_relationship,
                evidence_classification=request.form.get("evidence_classification") or fam.FACT,
                confidence=request.form.get("confidence") or fam.CONFIDENCE_MEDIUM,
                explanation=(request.form.get("explanation") or "").strip() or None,
            )
            session.commit()
        return redirect(url_for("phone_interview_detail", plan_id=plan_id))


@app.route("/phone-interviews/<int:plan_id>/questions/<int:question_instance_id>/signal-evidence", methods=["POST"])
def phone_interview_add_signal_evidence(plan_id: int, question_instance_id: int):
    with SessionFactory() as session:
        signal_definition_id = request.form.get("signal_definition_id", type=int)
        evidence_relationship = request.form.get("evidence_relationship")
        if signal_definition_id and evidence_relationship:
            pi_svc.record_answer_as_signal_evidence(
                session, question_instance_id, signal_definition_id=signal_definition_id,
                evidence_relationship=evidence_relationship,
                evidence_classification=request.form.get("evidence_classification") or fam.FACT,
                confidence=request.form.get("confidence") or fam.CONFIDENCE_MEDIUM,
                explanation=(request.form.get("explanation") or "").strip() or None,
            )
            session.commit()
        return redirect(url_for("phone_interview_detail", plan_id=plan_id))


@app.route("/phone-interviews/<int:plan_id>/escape-route", methods=["POST"])
def phone_interview_escape_route(plan_id: int):
    with SessionFactory() as session:
        pi_svc.activate_escape_route(session, plan_id, reason=(request.form.get("reason") or "").strip() or None)
        session.commit()
        return redirect(url_for("phone_interview_detail", plan_id=plan_id))


@app.route("/phone-interviews/<int:plan_id>/decision", methods=["POST"])
def phone_interview_decision(plan_id: int):
    with SessionFactory() as session:
        plan_status = request.form.get("plan_status")
        application_decision = request.form.get("application_decision")
        if plan_status and application_decision:
            pi_svc.record_post_interview_decision(
                session, plan_id, plan_status=plan_status, application_decision=application_decision,
                reason=(request.form.get("reason") or "").strip() or None,
            )
            session.commit()
        return redirect(url_for("phone_interview_detail", plan_id=plan_id))


@app.route("/in-person-interview-sections")
def in_person_interview_sections_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        seed_romes_flavours_in_person_interview_structure(session, restaurant_id=restaurant.id)  # idempotent
        sections = ip_svc.list_section_definitions(session, restaurant_id=restaurant.id, active_only=False)
        sections_with_items = [
            (section, ip_svc.list_item_definitions(session, section_id=section.id, active_only=False))
            for section in sections
        ]
        return render_template(
            "in_person_interview_sections_home.html", client_name=restaurant.name, sections_with_items=sections_with_items,
            section_kinds=ipm.SECTION_KINDS, item_types=ipm.ASSESSMENT_ITEM_TYPES, importance_levels=ipm.IMPORTANCE_LEVELS,
            active_nav="in-person-interview-sections",
        )


@app.route("/in-person-interview-sections/new", methods=["POST"])
def in_person_interview_section_create():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        name = (request.form.get("name") or "").strip()
        if not name:
            return redirect(url_for("in_person_interview_sections_home"))
        ip_svc.create_section_definition(
            session, restaurant_id=restaurant.id, name=name,
            section_kind=request.form.get("section_kind") or ipm.OTHER_SECTION_KIND,
            target_role=(request.form.get("target_role") or "").strip() or None,
            description=(request.form.get("description") or "").strip() or None,
        )
        session.commit()
        return redirect(url_for("in_person_interview_sections_home"))


@app.route("/in-person-interview-sections/<int:section_id>/update", methods=["POST"])
def in_person_interview_section_update(section_id: int):
    with SessionFactory() as session:
        ip_svc.update_section_definition(
            session, section_id,
            name=(request.form.get("name") or "").strip(),
            section_kind=request.form.get("section_kind") or ipm.OTHER_SECTION_KIND,
            target_role=(request.form.get("target_role") or "").strip() or None,
            description=(request.form.get("description") or "").strip() or None,
        )
        session.commit()
        return redirect(url_for("in_person_interview_sections_home"))


@app.route("/in-person-interview-sections/<int:section_id>/toggle-active", methods=["POST"])
def in_person_interview_section_toggle_active(section_id: int):
    with SessionFactory() as session:
        section = ip_svc.get_section_definition(session, section_id)
        if section is not None:
            if section.is_active:
                ip_svc.deactivate_section_definition(session, section_id)
            else:
                ip_svc.reactivate_section_definition(session, section_id)
            session.commit()
        return redirect(url_for("in_person_interview_sections_home"))


@app.route("/in-person-interview-sections/<int:section_id>/items/new", methods=["POST"])
def in_person_interview_item_create(section_id: int):
    with SessionFactory() as session:
        title_or_question = (request.form.get("title_or_question") or "").strip()
        item_type = request.form.get("item_type")
        if not (title_or_question and item_type):
            return redirect(url_for("in_person_interview_sections_home"))
        ip_svc.create_item_definition(
            session, section_id, item_type=item_type, title_or_question=title_or_question,
            instruction=(request.form.get("instruction") or "").strip() or None,
            scenario=(request.form.get("scenario") or "").strip() or None,
            objective=(request.form.get("objective") or "").strip() or None,
            importance=request.form.get("importance") or ipm.IMPORTANCE_LEVELS[2],
            mandatory_within_selection_process=request.form.get("mandatory_within_selection_process") == "on",
            evidence_expected=(request.form.get("evidence_expected") or "").strip() or None,
            evidence_positive=(request.form.get("evidence_positive") or "").strip() or None,
            evidence_contrary=(request.form.get("evidence_contrary") or "").strip() or None,
            evidence_insufficient=(request.form.get("evidence_insufficient") or "").strip() or None,
            selezionatore_instructions=(request.form.get("selezionatore_instructions") or "").strip() or None,
        )
        session.commit()
        return redirect(url_for("in_person_interview_sections_home"))


@app.route("/in-person-interview-sections/<int:section_id>/items/<int:item_id>/update", methods=["POST"])
def in_person_interview_item_update(section_id: int, item_id: int):
    with SessionFactory() as session:
        ip_svc.update_item_definition(
            session, item_id,
            title_or_question=(request.form.get("title_or_question") or "").strip(),
            item_type=request.form.get("item_type"),
            instruction=(request.form.get("instruction") or "").strip() or None,
            scenario=(request.form.get("scenario") or "").strip() or None,
            objective=(request.form.get("objective") or "").strip() or None,
            importance=request.form.get("importance") or ipm.IMPORTANCE_LEVELS[2],
            mandatory_within_selection_process=request.form.get("mandatory_within_selection_process") == "on",
            evidence_expected=(request.form.get("evidence_expected") or "").strip() or None,
            evidence_positive=(request.form.get("evidence_positive") or "").strip() or None,
            evidence_contrary=(request.form.get("evidence_contrary") or "").strip() or None,
            evidence_insufficient=(request.form.get("evidence_insufficient") or "").strip() or None,
            selezionatore_instructions=(request.form.get("selezionatore_instructions") or "").strip() or None,
        )
        session.commit()
        return redirect(url_for("in_person_interview_sections_home"))


@app.route("/in-person-interview-sections/<int:section_id>/items/<int:item_id>/toggle-active", methods=["POST"])
def in_person_interview_item_toggle_active(section_id: int, item_id: int):
    with SessionFactory() as session:
        item = ip_svc.get_item_definition(session, item_id)
        if item is not None:
            if item.is_active:
                ip_svc.deactivate_item_definition(session, item_id)
            else:
                ip_svc.reactivate_item_definition(session, item_id)
            session.commit()
        return redirect(url_for("in_person_interview_sections_home"))


# ---------------------------------------------------------------------------
# In-Person Interview + Practical Assessment + Consistency Engine (Task 4B)
# — routes are thin: every actual operation is delegated to
# `in_person_interview_service.py`. Never a hiring decision, never a score.
# ---------------------------------------------------------------------------


@app.route("/applications/<int:application_id>/in-person-interview", methods=["POST"])
def in_person_interview_create(application_id: int):
    with SessionFactory() as session:
        application = app_svc.get_application(session, application_id)
        if application is not None:
            seed_romes_flavours_in_person_interview_structure(session, restaurant_id=application.restaurant_id)  # idempotent
        try:
            plan = ip_svc.create_plan(session, application_id)
        except ValueError:
            session.rollback()
            return redirect(url_for("application_detail", application_id=application_id))
        session.commit()
        return redirect(url_for("in_person_interview_detail", plan_id=plan.id))


def _in_person_interview_context(session, plan) -> dict:
    application = session.get(m.Application, plan.application_id)
    observations = sig_svc.list_observations(session, application.id)
    snapshot = session.get(m.RequirementSetSnapshot, plan.requirement_set_snapshot_id)
    return {
        "plan": plan, "application": application, "profile": persistence.to_profile(application.candidate),
        "observations": observations,
        "snapshot_items_by_id": {item.id: item for item in snapshot.items},
        "signal_definitions_by_id": {o.signal_definition_id: o.signal_definition for o in observations},
        "fit_summary": fa_svc.get_summary(session, plan.fit_assessment_id),
        "remaining_items": ip_svc.get_ordered_remaining_items(session, plan.id),
        "history_items": [
            i for i in ip_svc.list_item_instances(session, plan.id) if i.status != ipm.NOT_DONE
        ],
        "incomplete_items": ip_svc.list_incomplete_items(session, plan.id),
        "threads": ip_svc.list_threads_for_application(session, application.id),
        "items_to_verify": ip_svc.list_items_to_verify(session, application.id),
        "original_cv_available": _original_cv_available(session, application.candidate),
        "plan_statuses": ipm.PLAN_STATUSES, "item_statuses": ipm.ASSESSMENT_ITEM_STATUSES,
        "importance_levels": ipm.IMPORTANCE_LEVELS, "consistency_statuses": ipm.CONSISTENCY_STATUSES,
        "consistency_source_stages": ipm.CONSISTENCY_SOURCE_STAGES,
        "starter_consistency_topics": ipm.STARTER_CONSISTENCY_TOPICS,
        "priority_categories": sigm.REVIEW_PRIORITY_CATEGORIES,
        "evidence_relationships": fam.EVIDENCE_RELATIONSHIPS, "evidence_classifications": fam.EVIDENCE_CLASSIFICATIONS,
        "confidence_levels": fam.CONFIDENCE_LEVELS,
        "active_nav": "applications",
    }


@app.route("/in-person-interviews/<int:plan_id>")
def in_person_interview_detail(plan_id: int):
    with SessionFactory() as session:
        plan = ip_svc.get_plan(session, plan_id)
        if plan is None:
            return redirect(url_for("applications_home"))
        return render_template("in_person_interview_detail.html", **_in_person_interview_context(session, plan))


@app.route("/in-person-interviews/<int:plan_id>/refresh", methods=["POST"])
def in_person_interview_refresh(plan_id: int):
    with SessionFactory() as session:
        ip_svc.refresh_plan(session, plan_id)
        session.commit()
        return redirect(url_for("in_person_interview_detail", plan_id=plan_id))


@app.route("/in-person-interviews/<int:plan_id>/start", methods=["POST"])
def in_person_interview_start(plan_id: int):
    with SessionFactory() as session:
        ip_svc.start_interview(session, plan_id)
        session.commit()
        return redirect(url_for("in_person_interview_detail", plan_id=plan_id))


@app.route("/in-person-interviews/<int:plan_id>/notes", methods=["POST"])
def in_person_interview_set_notes(plan_id: int):
    with SessionFactory() as session:
        ip_svc.set_notes(session, plan_id, (request.form.get("notes") or "").strip() or None)
        session.commit()
        return redirect(url_for("in_person_interview_detail", plan_id=plan_id))


@app.route("/in-person-interviews/<int:plan_id>/items/<int:item_instance_id>/response", methods=["POST"])
def in_person_interview_record_response(plan_id: int, item_instance_id: int):
    with SessionFactory() as session:
        status = request.form.get("status")
        if status:
            ip_svc.record_response(
                session, item_instance_id, status=status, raw_response=request.form.get("raw_response"),
                selezionatore_note=request.form.get("selezionatore_note"),
                confidence=(request.form.get("confidence") or "").strip() or None,
            )
            session.commit()
        return redirect(url_for("in_person_interview_detail", plan_id=plan_id))


@app.route("/in-person-interviews/<int:plan_id>/items/<int:item_instance_id>/follow-up", methods=["POST"])
def in_person_interview_add_follow_up(plan_id: int, item_instance_id: int):
    with SessionFactory() as session:
        title_or_question = (request.form.get("title_or_question") or "").strip()
        if title_or_question:
            ip_svc.add_follow_up_item(
                session, item_instance_id, title_or_question=title_or_question,
                objective=(request.form.get("objective") or "").strip() or None,
                importance=request.form.get("importance") or None,
            )
            session.commit()
        return redirect(url_for("in_person_interview_detail", plan_id=plan_id))


@app.route("/in-person-interviews/<int:plan_id>/items/<int:item_instance_id>/fit-evidence", methods=["POST"])
def in_person_interview_add_fit_evidence(plan_id: int, item_instance_id: int):
    with SessionFactory() as session:
        requirement_snapshot_item_id = request.form.get("requirement_snapshot_item_id", type=int)
        evidence_relationship = request.form.get("evidence_relationship")
        if requirement_snapshot_item_id and evidence_relationship:
            ip_svc.record_response_as_fit_evidence(
                session, item_instance_id, requirement_snapshot_item_id=requirement_snapshot_item_id,
                evidence_relationship=evidence_relationship,
                evidence_classification=request.form.get("evidence_classification") or fam.FACT,
                confidence=request.form.get("confidence") or fam.CONFIDENCE_MEDIUM,
                explanation=(request.form.get("explanation") or "").strip() or None,
            )
            session.commit()
        return redirect(url_for("in_person_interview_detail", plan_id=plan_id))


@app.route("/in-person-interviews/<int:plan_id>/items/<int:item_instance_id>/signal-evidence", methods=["POST"])
def in_person_interview_add_signal_evidence(plan_id: int, item_instance_id: int):
    with SessionFactory() as session:
        signal_definition_id = request.form.get("signal_definition_id", type=int)
        evidence_relationship = request.form.get("evidence_relationship")
        if signal_definition_id and evidence_relationship:
            ip_svc.record_response_as_signal_evidence(
                session, item_instance_id, signal_definition_id=signal_definition_id,
                evidence_relationship=evidence_relationship,
                evidence_classification=request.form.get("evidence_classification") or fam.FACT,
                confidence=request.form.get("confidence") or fam.CONFIDENCE_MEDIUM,
                explanation=(request.form.get("explanation") or "").strip() or None,
            )
            session.commit()
        return redirect(url_for("in_person_interview_detail", plan_id=plan_id))


@app.route("/in-person-interviews/<int:plan_id>/stop", methods=["POST"])
def in_person_interview_stop(plan_id: int):
    with SessionFactory() as session:
        plan_status = request.form.get("plan_status")
        if plan_status:
            ip_svc.stop_interview(session, plan_id, plan_status=plan_status)
            session.commit()
        return redirect(url_for("in_person_interview_detail", plan_id=plan_id))


# ---------------------------------------------------------------------------
# Consistency Engine (Task 4B §8-§15) — a Consistency Thread compares one
# topic across CV/Application, prior Applications, Phone Interview, In-
# Person Interview, and Practical Assessment sources. A contradiction is
# evidence, never automatic proof of dishonesty.
# ---------------------------------------------------------------------------


@app.route("/applications/<int:application_id>/consistency-threads/new", methods=["POST"])
def consistency_thread_create(application_id: int):
    with SessionFactory() as session:
        topic = (request.form.get("topic") or "").strip()
        if topic:
            ip_svc.create_consistency_thread(
                session, application_id, topic=topic, importance=request.form.get("importance") or pim.MEDIUM,
            )
            session.commit()
        return redirect(request.form.get("next") or url_for("application_detail", application_id=application_id))


@app.route("/applications/<int:application_id>/consistency-threads/generate-cross-application", methods=["POST"])
def consistency_thread_generate_cross_application(application_id: int):
    with SessionFactory() as session:
        ip_svc.generate_cross_application_consistency_threads(session, application_id)
        session.commit()
        return redirect(request.form.get("next") or url_for("application_detail", application_id=application_id))


@app.route("/consistency-threads/<int:thread_id>/statements", methods=["POST"])
def consistency_thread_add_statement(thread_id: int):
    with SessionFactory() as session:
        phone_question_instance_id = request.form.get("phone_question_instance_id", type=int)
        item_instance_id = request.form.get("item_instance_id", type=int)
        raw_statement = (request.form.get("raw_statement") or "").strip()
        if phone_question_instance_id:
            ip_svc.add_statement_from_phone_answer(session, thread_id, phone_question_instance_id)
        elif item_instance_id:
            ip_svc.add_statement_from_in_person_item(session, thread_id, item_instance_id)
        elif raw_statement:
            ip_svc.add_statement(
                session, thread_id, source_stage=request.form.get("source_stage") or ipm.SELEZIONATORE_ENTERED,
                raw_statement=raw_statement,
            )
        session.commit()
        return redirect(request.form.get("next") or url_for("home"))


@app.route("/consistency-threads/<int:thread_id>/status", methods=["POST"])
def consistency_thread_set_status(thread_id: int):
    with SessionFactory() as session:
        status = request.form.get("status")
        if status:
            ip_svc.set_comparison_status(
                session, thread_id, status=status,
                explanation=(request.form.get("explanation") or "").strip() or None,
                confidence=(request.form.get("confidence") or "").strip() or None,
                resolution=(request.form.get("resolution") or "").strip() or None,
            )
            session.commit()
        return redirect(request.form.get("next") or url_for("home"))


@app.route("/in-person-interviews/<int:plan_id>/consistency-threads/<int:thread_id>/generate-clarification", methods=["POST"])
def consistency_thread_generate_clarification(plan_id: int, thread_id: int):
    with SessionFactory() as session:
        ip_svc.generate_clarification_item(session, plan_id, thread_id)
        session.commit()
        return redirect(url_for("in_person_interview_detail", plan_id=plan_id))


@app.route("/primary-screening-criteria")
def primary_screening_criteria_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        seed_romes_flavours_primary_screening_criteria(session, restaurant_id=restaurant.id)  # idempotent
        criteria = ps_svc.list_criteria(session, restaurant_id=restaurant.id, active_only=False)
        signal_definitions = sig_svc.list_signal_definitions(session, restaurant_id=restaurant.id, active_only=False)
        compliance_status = {
            c.id: compliance_svc.review_status_summary(session, cpm.PRIMARY_SCREENING_CRITERION, c.id) for c in criteria
        }
        return render_template(
            "primary_screening_criteria_home.html", client_name=restaurant.name, criteria=criteria,
            directions=psm.DIRECTIONS, evidence_sources=psm.EVIDENCE_SOURCES, signal_statuses=sigm.SIGNAL_STATUSES,
            signal_definitions=signal_definitions, level_scale=psm.LEVEL_SCALE, active_nav="primary-screening-criteria",
            compliance_status=compliance_status, compliance_object_type=cpm.PRIMARY_SCREENING_CRITERION,
            disposition_actions=cpm.DISPOSITION_ACTIONS, compliance_disclaimer=cpm.DISCLAIMER,
        )


def _parse_level_descriptions(form) -> dict:
    return {str(level): (form.get(f"level_description_{level}") or "").strip() for level in psm.LEVEL_SCALE if (form.get(f"level_description_{level}") or "").strip()}


def _parse_auto_evaluation_level_map(form) -> dict:
    result = {}
    for status in sigm.SIGNAL_STATUSES:
        value = (form.get(f"auto_level_{status}") or "").strip()
        if value != "":
            result[status] = int(value)
    return result


@app.route("/primary-screening-criteria/new", methods=["POST"])
def primary_screening_criterion_create():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        name = (request.form.get("name") or "").strip()
        if not name:
            return redirect(url_for("primary_screening_criteria_home"))
        ps_svc.create_criterion(
            session, restaurant_id=restaurant.id, name=name,
            description=(request.form.get("description") or "").strip() or None,
            category=(request.form.get("category") or "").strip() or None,
            target_role=(request.form.get("target_role") or "").strip() or None,
            location_label=(request.form.get("location_label") or "").strip() or None,
            coefficient=request.form.get("coefficient", type=float) or 1.0,
            direction=request.form.get("direction") or psm.POSITIVE,
            is_hard_disqualifier=request.form.get("is_hard_disqualifier") == "on",
            hard_disqualifier_trigger_level=request.form.get("hard_disqualifier_trigger_level", type=int),
            level_descriptions=_parse_level_descriptions(request.form),
            evidence_sources_allowed=request.form.getlist("evidence_sources_allowed"),
            evaluation_guidance=(request.form.get("evaluation_guidance") or "").strip() or None,
            evidence_positive=(request.form.get("evidence_positive") or "").strip() or None,
            evidence_contrary=(request.form.get("evidence_contrary") or "").strip() or None,
            evidence_insufficient=(request.form.get("evidence_insufficient") or "").strip() or None,
            auto_evaluation_signal_definition_id=request.form.get("auto_evaluation_signal_definition_id", type=int),
            auto_evaluation_level_map=_parse_auto_evaluation_level_map(request.form),
        )
        session.commit()
        return redirect(url_for("primary_screening_criteria_home"))


@app.route("/primary-screening-criteria/<int:criterion_id>/update", methods=["POST"])
def primary_screening_criterion_update(criterion_id: int):
    with SessionFactory() as session:
        ps_svc.update_criterion(
            session, criterion_id,
            name=(request.form.get("name") or "").strip(),
            description=(request.form.get("description") or "").strip() or None,
            category=(request.form.get("category") or "").strip() or None,
            target_role=(request.form.get("target_role") or "").strip() or None,
            location_label=(request.form.get("location_label") or "").strip() or None,
            coefficient=request.form.get("coefficient", type=float) or 1.0,
            direction=request.form.get("direction") or psm.POSITIVE,
            is_hard_disqualifier=request.form.get("is_hard_disqualifier") == "on",
            hard_disqualifier_trigger_level=request.form.get("hard_disqualifier_trigger_level", type=int),
            level_descriptions=_parse_level_descriptions(request.form),
            evidence_sources_allowed=request.form.getlist("evidence_sources_allowed"),
            evaluation_guidance=(request.form.get("evaluation_guidance") or "").strip() or None,
            evidence_positive=(request.form.get("evidence_positive") or "").strip() or None,
            evidence_contrary=(request.form.get("evidence_contrary") or "").strip() or None,
            evidence_insufficient=(request.form.get("evidence_insufficient") or "").strip() or None,
            auto_evaluation_signal_definition_id=request.form.get("auto_evaluation_signal_definition_id", type=int),
            auto_evaluation_level_map=_parse_auto_evaluation_level_map(request.form),
        )
        session.commit()
        return redirect(url_for("primary_screening_criteria_home"))


@app.route("/primary-screening-criteria/<int:criterion_id>/toggle-active", methods=["POST"])
def primary_screening_criterion_toggle_active(criterion_id: int):
    with SessionFactory() as session:
        criterion = ps_svc.get_criterion(session, criterion_id)
        if criterion is not None:
            try:
                if criterion.is_active:
                    ps_svc.deactivate_criterion(session, criterion_id)
                else:
                    compliance_svc.assert_activation_allowed(session, cpm.PRIMARY_SCREENING_CRITERION, criterion_id)
                    ps_svc.reactivate_criterion(session, criterion_id)
                session.commit()
            except ValueError:
                session.rollback()
        return redirect(url_for("primary_screening_criteria_home"))


# ---------------------------------------------------------------------------
# Primary Screening Queue (Task 3D) — the operational, aggressive early-
# stage filter sitting BEFORE Phone Interview. The internal Priority Index
# orders the queue but is NEVER rendered to the Selezionatore.
# ---------------------------------------------------------------------------


def _screening_row(session, run) -> dict:
    application = session.get(m.Application, run.application_id)
    evaluations = ps_svc.list_evaluations(session, run.id)
    return {
        "run_id": run.id, "application_id": application.id, "candidate_id": application.candidate_id,
        "full_name": application.candidate.full_name or "(name not extracted)",
        "target_role": application.target_role or "-", "applied_at": application.applied_at,
        "explanation": run.explanation or "Not yet evaluated.",
        "unresolved_count": sum(1 for e in evaluations if e.status == psm.INSUFFICIENT_EVIDENCE),
        "prior_count": len(app_svc.list_prior_applications(session, application.id)),
        "original_cv_available": _original_cv_available(session, application.candidate),
        "hard_disqualifier_names": [
            e.criterion_snapshot.name for e in evaluations
            if e.is_active_hard_disqualifier and not e.hard_disqualifier_overridden
        ],
        # Task 5A-ALIGN §12 — a Candidate Flag (e.g. a prior "Training Check
        # Not Passed") must be immediately visible at Primary Screening.
        "active_flag_names": [flag.name for flag in flag_svc.list_active_flags_for_application(session, application.id)],
    }


@app.route("/primary-screening-queue")
def primary_screening_queue():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        show = request.args.get("show") or "20"
        limit = None if show == "all" else int(show) if show.isdigit() else 20

        normal_runs = ps_svc.list_normal_pool(session, restaurant.id, limit=limit)
        hard_runs = ps_svc.list_hard_disqualifier_pool(session, restaurant.id)
        due_reminders = outcome_svc.list_due_reminders(session, restaurant.id)

        return render_template(
            "primary_screening_queue.html", client_name=restaurant.name,
            normal_rows=[_screening_row(session, run) for run in normal_runs],
            hard_rows=[_screening_row(session, run) for run in hard_runs],
            due_reminders=[
                {
                    "reminder": reminder,
                    "application": session.get(m.Application, reminder.application_id),
                }
                for reminder in due_reminders
            ],
            show=show, active_nav="primary-screening-queue",
        )


@app.route("/primary-screening-queue/run-all", methods=["POST"])
def primary_screening_run_all():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        seed_romes_flavours_primary_screening_criteria(session, restaurant_id=restaurant.id)  # idempotent
        ps_svc.run_screening_for_unscreened_applications(session, restaurant.id)
        session.commit()
        return redirect(url_for("primary_screening_queue"))


@app.route("/applications/<int:application_id>/primary-screening/run", methods=["POST"])
def primary_screening_run_create(application_id: int):
    with SessionFactory() as session:
        application = app_svc.get_application(session, application_id)
        if application is not None:
            seed_romes_flavours_primary_screening_criteria(session, restaurant_id=application.restaurant_id)  # idempotent
        run = ps_svc.create_screening_run(session, application_id)
        session.commit()
        return redirect(url_for("primary_screening_detail", run_id=run.id))


@app.route("/primary-screening/<int:run_id>")
def primary_screening_detail(run_id: int):
    with SessionFactory() as session:
        run = ps_svc.get_run(session, run_id)
        if run is None:
            return redirect(url_for("primary_screening_queue"))
        application = session.get(m.Application, run.application_id)
        evaluations = ps_svc.list_evaluations(session, run.id)
        evaluation_notes = {e.id: ps_svc.list_evaluation_notes(session, e.id) for e in evaluations}
        return render_template(
            "primary_screening_detail.html", run=run, application=application, evaluations=evaluations,
            level_scale=psm.LEVEL_SCALE, evaluation_statuses=psm.EVALUATION_STATUSES,
            evidence_sources=psm.EVIDENCE_SOURCES, confidence_levels=fam.CONFIDENCE_LEVELS,
            original_cv_available=_original_cv_available(session, application.candidate),
            prior_runs=ps_svc.list_runs_for_application(session, application.id),
            run_notes=ps_svc.list_run_notes(session, run.id), evaluation_notes=evaluation_notes,
            active_flags=flag_svc.list_active_flags_for_application(session, application.id),
            active_nav="primary-screening-queue",
        )


@app.route("/primary-screening/<int:run_id>/notes", methods=["POST"])
def primary_screening_run_add_note(run_id: int):
    with SessionFactory() as session:
        note_text = (request.form.get("note_text") or "").strip()
        if note_text:
            ps_svc.add_run_note(session, run_id, note_text)
            session.commit()
        return redirect(url_for("primary_screening_detail", run_id=run_id))


@app.route("/primary-screening/<int:run_id>/evaluations/<int:evaluation_id>/notes", methods=["POST"])
def primary_screening_evaluation_add_note(run_id: int, evaluation_id: int):
    with SessionFactory() as session:
        note_text = (request.form.get("note_text") or "").strip()
        if note_text:
            ps_svc.add_evaluation_note(session, evaluation_id, note_text)
            session.commit()
        return redirect(url_for("primary_screening_detail", run_id=run_id))


@app.route("/primary-screening/<int:run_id>/evaluations/<int:evaluation_id>/enter", methods=["POST"])
def primary_screening_evaluation_enter(run_id: int, evaluation_id: int):
    with SessionFactory() as session:
        level = request.form.get("level", type=int)
        if level is not None:
            ps_svc.human_enter_evaluation(
                session, evaluation_id, level=level,
                confidence=(request.form.get("confidence") or "").strip() or None,
                evidence_source=(request.form.get("evidence_source") or "").strip() or None,
                evidence_text=(request.form.get("evidence_text") or "").strip() or None,
                explanation=(request.form.get("explanation") or "").strip() or None,
            )
            session.commit()
        return redirect(url_for("primary_screening_detail", run_id=run_id))


@app.route("/primary-screening/<int:run_id>/evaluations/<int:evaluation_id>/override", methods=["POST"])
def primary_screening_evaluation_override(run_id: int, evaluation_id: int):
    with SessionFactory() as session:
        level = request.form.get("level", type=int)
        if level is not None:
            ps_svc.human_override_evaluation(
                session, evaluation_id, level=level, reason=(request.form.get("reason") or "").strip() or None,
            )
            session.commit()
        return redirect(url_for("primary_screening_detail", run_id=run_id))


@app.route("/primary-screening/<int:run_id>/evaluations/<int:evaluation_id>/confirm", methods=["POST"])
def primary_screening_evaluation_confirm(run_id: int, evaluation_id: int):
    with SessionFactory() as session:
        ps_svc.human_confirm_evaluation(session, evaluation_id)
        session.commit()
        return redirect(url_for("primary_screening_detail", run_id=run_id))


@app.route("/primary-screening/<int:run_id>/evaluations/<int:evaluation_id>/not-applicable", methods=["POST"])
def primary_screening_evaluation_not_applicable(run_id: int, evaluation_id: int):
    with SessionFactory() as session:
        ps_svc.mark_not_applicable(session, evaluation_id)
        session.commit()
        return redirect(url_for("primary_screening_detail", run_id=run_id))


@app.route("/primary-screening/<int:run_id>/evaluations/<int:evaluation_id>/insufficient-evidence", methods=["POST"])
def primary_screening_evaluation_insufficient(run_id: int, evaluation_id: int):
    with SessionFactory() as session:
        ps_svc.mark_insufficient_evidence(session, evaluation_id)
        session.commit()
        return redirect(url_for("primary_screening_detail", run_id=run_id))


@app.route("/primary-screening/<int:run_id>/evaluations/<int:evaluation_id>/override-hard-disqualifier", methods=["POST"])
def primary_screening_override_hard_disqualifier(run_id: int, evaluation_id: int):
    with SessionFactory() as session:
        reason = (request.form.get("reason") or "").strip()
        actor = (request.form.get("actor") or "").strip() or None
        try:
            run = ps_svc.get_run(session, run_id)
            if run is not None:
                own_svc.assert_can_operate(session, run.application_id, actor)
            ps_svc.override_hard_disqualifier(session, evaluation_id, reason=reason)
            session.commit()
        except ValueError:
            session.rollback()
        return redirect(request.form.get("next") or url_for("primary_screening_detail", run_id=run_id))


# ---------------------------------------------------------------------------
# Selection Outcome Definitions (Task 5A §4/§5/§30) — restaurant-
# configurable, guided-form "wizard" (conversational labels/groupings,
# never raw database terminology) rather than a free-text label.
# ---------------------------------------------------------------------------


def _parse_reason_choices(form) -> list[str]:
    raw = form.get("reason_choices") or ""
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _outcome_definition_form_fields(form) -> dict:
    return dict(
        description=(form.get("description") or "").strip() or None,
        lifecycle_effect=form.get("lifecycle_effect") or om.ACTIVE,
        is_reopenable=form.get("is_reopenable") == "on",
        requires_note=form.get("requires_note") == "on",
        requires_reason=form.get("requires_reason") == "on",
        reason_choices=_parse_reason_choices(form),
        target_queue_id=form.get("target_queue_id", type=int),
        creates_reminder=form.get("creates_reminder") == "on",
        reminder_days=form.get("reminder_days", type=int),
        future_contact_policy=form.get("future_contact_policy") or om.CONTACT_ALLOWED,
        creates_candidate_flag=form.get("creates_candidate_flag") == "on",
        candidate_flag_name=(form.get("candidate_flag_name") or "").strip() or None,
        candidate_flag_scope=form.get("candidate_flag_scope") or None,
        candidate_flag_operational_effect=form.get("candidate_flag_operational_effect") or None,
        candidate_flag_default_reason=(form.get("candidate_flag_default_reason") or "").strip() or None,
        candidate_flag_expires_after_days=form.get("candidate_flag_expires_after_days", type=int),
        authority_label=(form.get("authority_label") or "").strip() or None,
        driven_by=(form.get("driven_by") or "").strip() or None,
    )


@app.route("/selection-outcomes")
def selection_outcomes_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        seed_default_selection_outcomes(session, restaurant_id=restaurant.id)  # idempotent (also seeds default queues)
        definitions = outcome_svc.list_outcome_definitions(session, restaurant_id=restaurant.id, active_only=False)
        return render_template(
            "selection_outcomes_home.html", client_name=restaurant.name, definitions=definitions,
            lifecycle_states=om.LIFECYCLE_STATES, future_contact_policies=om.FUTURE_CONTACT_POLICIES,
            flag_scopes=om.FLAG_SCOPES, flag_operational_effects=om.FLAG_OPERATIONAL_EFFECTS,
            driven_by_options=om.DRIVEN_BY_OPTIONS,
            queues=queue_svc.list_queues(session, restaurant_id=restaurant.id, active_only=False),
            active_nav="selection-outcomes",
        )


@app.route("/selection-outcomes/new", methods=["POST"])
def selection_outcome_definition_create():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        name = (request.form.get("name") or "").strip()
        if name:
            outcome_svc.create_outcome_definition(
                session, restaurant_id=restaurant.id, name=name, **_outcome_definition_form_fields(request.form)
            )
            session.commit()
        return redirect(url_for("selection_outcomes_home"))


@app.route("/selection-outcomes/<int:definition_id>/update", methods=["POST"])
def selection_outcome_definition_update(definition_id: int):
    with SessionFactory() as session:
        name = (request.form.get("name") or "").strip()
        fields = _outcome_definition_form_fields(request.form)
        if name:
            fields["name"] = name
        outcome_svc.update_outcome_definition(session, definition_id, **fields)
        session.commit()
        return redirect(url_for("selection_outcomes_home"))


@app.route("/selection-outcomes/<int:definition_id>/toggle-active", methods=["POST"])
def selection_outcome_definition_toggle_active(definition_id: int):
    with SessionFactory() as session:
        definition = outcome_svc.get_outcome_definition(session, definition_id)
        if definition is not None:
            if definition.is_active:
                outcome_svc.deactivate_outcome_definition(session, definition_id)
            else:
                outcome_svc.reactivate_outcome_definition(session, definition_id)
            session.commit()
        return redirect(url_for("selection_outcomes_home"))


# ---------------------------------------------------------------------------
# Operational Queues/Lists (Task 5A-FIX §8/§15) — restaurant-configurable,
# purely organizational; never a hiring decision.
# ---------------------------------------------------------------------------


@app.route("/selection-queues")
def selection_queues_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        seed_default_selection_queues(session, restaurant_id=restaurant.id)  # idempotent
        queues = queue_svc.list_queues(session, restaurant_id=restaurant.id, active_only=False)
        return render_template(
            "selection_queues_home.html", client_name=restaurant.name, queues=queues, active_nav="selection-queues",
        )


@app.route("/selection-queues/new", methods=["POST"])
def selection_queue_create():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        name = (request.form.get("name") or "").strip()
        if name:
            queue_svc.create_queue(
                session, restaurant_id=restaurant.id, name=name,
                description=(request.form.get("description") or "").strip() or None,
            )
            session.commit()
        return redirect(url_for("selection_queues_home"))


@app.route("/selection-queues/<int:queue_id>/update", methods=["POST"])
def selection_queue_update(queue_id: int):
    with SessionFactory() as session:
        name = (request.form.get("name") or "").strip()
        fields = {"description": (request.form.get("description") or "").strip() or None}
        display_order = request.form.get("display_order", type=int)
        if display_order is not None:
            fields["display_order"] = display_order
        if name:
            fields["name"] = name
        queue_svc.update_queue(session, queue_id, **fields)
        session.commit()
        return redirect(url_for("selection_queues_home"))


@app.route("/selection-queues/<int:queue_id>/toggle-active", methods=["POST"])
def selection_queue_toggle_active(queue_id: int):
    with SessionFactory() as session:
        queue = queue_svc.get_queue(session, queue_id)
        if queue is not None:
            if queue.is_active:
                queue_svc.deactivate_queue(session, queue_id)
            else:
                queue_svc.reactivate_queue(session, queue_id)
            session.commit()
        return redirect(url_for("selection_queues_home"))


@app.route("/applications/<int:application_id>/queue/move", methods=["POST"])
def application_move_queue(application_id: int):
    """Task 5A-FIX §12 — manual queue movement, independent of Stage and
    Outcome: never changes either, always historically recorded."""

    with SessionFactory() as session:
        queue_id = request.form.get("queue_id", type=int)
        if queue_id:
            try:
                queue_svc.move_to_queue(
                    session, application_id, queue_id, source=qm.MANUAL,
                    note_text=(request.form.get("note_text") or "").strip() or None,
                    reason=(request.form.get("reason") or "").strip() or None,
                )
                session.commit()
            except ValueError:
                session.rollback()
        return redirect(request.form.get("next") or url_for("application_decision", application_id=application_id))


# ---------------------------------------------------------------------------
# Selection Session + Application Ownership + Rule Governance (Task 5C) —
# routes are thin: every operation delegates to session_service/
# rule_set_service/rule_change_service/ownership_service.
# ---------------------------------------------------------------------------

@app.route("/sessions")
def sessions_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        sessions = sess_svc.list_sessions(session, restaurant_id=restaurant.id)
        summaries = []
        for s in sessions:
            applications = sess_svc.list_applications_for_session(session, s.id)
            owned = sum(1 for a in applications if own_svc.get_current_owner(session, a.id) is not None)
            summaries.append({
                "session": s,
                "application_count": len(applications),
                "owned_count": owned,
                "assignments": sess_svc.list_assignments(session, s.id, active_only=True),
                "current_version": (
                    rs_svc.get_version(session, s.current_rule_set_version_id) if s.current_rule_set_version_id else None
                ),
            })
        return render_template(
            "sessions_home.html", client_name=restaurant.name, summaries=summaries,
            session_statuses=sesm.SESSION_STATUSES, active_nav="sessions",
        )


@app.route("/sessions/new", methods=["POST"])
def session_create():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        name = (request.form.get("name") or "").strip()
        target_role = (request.form.get("target_role") or "").strip()
        if name and target_role:
            new_session = sess_svc.create_session(
                session, restaurant_id=restaurant.id, name=name, target_role=target_role,
                location_label=(request.form.get("location_label") or "").strip() or None,
                created_by=(request.form.get("created_by") or "").strip() or None,
                carry_forward_from_session_id=request.form.get("carry_forward_from_session_id", type=int),
            )
            session.commit()
            return redirect(url_for("session_detail", session_id=new_session.id))
        return redirect(url_for("sessions_home"))


@app.route("/sessions/<int:session_id>")
def session_detail(session_id: int):
    with SessionFactory() as session:
        selection_session = sess_svc.get_session(session, session_id)
        if selection_session is None:
            return redirect(url_for("sessions_home"))

        assignments = sess_svc.list_assignments(session, session_id)
        versions = rs_svc.list_versions_for_session(session, session_id)
        current_version = (
            rs_svc.get_version(session, selection_session.current_rule_set_version_id)
            if selection_session.current_rule_set_version_id else None
        )
        rule_set_summary = rs_svc.get_rule_set_summary(session, current_version.id) if current_version else None

        applications = sess_svc.list_applications_for_session(session, session_id)
        application_rows = [
            {"application": a, "owner": own_svc.get_current_owner(session, a.id)} for a in applications
        ]

        rule_changes = rc_svc.list_rule_changes_for_session(session, session_id)
        impacts_needing_review = rc_svc.list_impacts_needing_review_for_session(session, session_id)

        # Convenience "link an existing Application" list — same
        # restaurant/role Applications not already linked to any Session.
        linkable_applications = [
            a for a in app_svc.list_applications(
                session, restaurant_id=selection_session.restaurant_id, target_role=selection_session.target_role,
            )
            if a.session_id is None
        ]

        return render_template(
            "session_detail.html", selection_session=selection_session, assignments=assignments,
            versions=versions, current_version=current_version, rule_set_summary=rule_set_summary,
            application_rows=application_rows, rule_changes=rule_changes,
            impacts_needing_review=impacts_needing_review, linkable_applications=linkable_applications,
            session_statuses=sesm.SESSION_STATUSES, rule_change_scopes=rsm.RULE_CHANGE_SCOPES,
            is_confirmed=sess_svc.is_confirmed(session, session_id),
            authority_levels=gov_svc.list_authority_levels(session, restaurant_id=selection_session.restaurant_id),
            requirement_sets=req_svc.list_requirement_sets(session, restaurant_id=selection_session.restaurant_id),
            criteria=ps_svc.list_criteria(session, restaurant_id=selection_session.restaurant_id, active_only=False),
            signal_definitions=sig_svc.list_signal_definitions(
                session, restaurant_id=selection_session.restaurant_id, active_only=False,
            ),
            outcome_definitions=outcome_svc.list_outcome_definitions(
                session, restaurant_id=selection_session.restaurant_id, active_only=False,
            ),
            session_notes=sess_svc.list_session_notes(session, session_id),
            scheduling_windows=sched_svc.list_windows_for_session(session, session_id, active_only=False),
            schedulable_stages=cm.SCHEDULABLE_STAGES,
            job_postings=jp_svc.list_job_postings_for_session(session, session_id),
            active_nav="sessions",
        )


@app.route("/sessions/<int:session_id>/assign", methods=["POST"])
def session_assign_selezionatore(session_id: int):
    with SessionFactory() as session:
        name = (request.form.get("selezionatore_name") or "").strip()
        if name:
            sess_svc.assign_selezionatore(
                session, session_id, selezionatore_name=name,
                authority_level_id=request.form.get("authority_level_id", type=int),
            )
            session.commit()
        return redirect(url_for("session_detail", session_id=session_id))


@app.route("/sessions/<int:session_id>/assignments/<int:assignment_id>/deactivate", methods=["POST"])
def session_deactivate_assignment(session_id: int, assignment_id: int):
    with SessionFactory() as session:
        sess_svc.deactivate_assignment(session, assignment_id)
        session.commit()
        return redirect(url_for("session_detail", session_id=session_id))


@app.route("/sessions/<int:session_id>/status", methods=["POST"])
def session_set_status(session_id: int):
    with SessionFactory() as session:
        new_status = request.form.get("new_status")
        if new_status:
            try:
                sess_svc.set_session_status(session, session_id, new_status)
                session.commit()
            except ValueError:
                session.rollback()
        return redirect(url_for("session_detail", session_id=session_id))


@app.route("/sessions/<int:session_id>/notes", methods=["POST"])
def session_add_note(session_id: int):
    with SessionFactory() as session:
        note_text = (request.form.get("note_text") or "").strip()
        if note_text:
            sess_svc.add_session_note(session, session_id, note_text)
            session.commit()
        return redirect(url_for("session_detail", session_id=session_id))


@app.route("/sessions/<int:session_id>/link-application", methods=["POST"])
def session_link_application(session_id: int):
    with SessionFactory() as session:
        application_id = request.form.get("application_id", type=int)
        if application_id:
            try:
                sess_svc.link_application_to_session(session, application_id, session_id)
                session.commit()
            except ValueError:
                session.rollback()
        return redirect(url_for("session_detail", session_id=session_id))


@app.route("/sessions/<int:session_id>/rule-set/update", methods=["POST"])
def session_rule_set_update(session_id: int):
    """Task 5C §13/§29 — pre-confirmation Rule Set preparation: freely
    edits the DRAFT/RULES_REVIEW envelope by building a fresh version
    (never a governed Rule Change — nothing has been confirmed/used under
    it yet, so no impact/history bookkeeping applies)."""

    with SessionFactory() as session:
        criterion_ids = [int(v) for v in request.form.getlist("criterion_ids") if v]
        signal_ids = [int(v) for v in request.form.getlist("signal_ids") if v]
        outcome_ids = [int(v) for v in request.form.getlist("outcome_ids") if v]
        try:
            rs_svc.build_rule_set_version(
                session, session_id,
                requirement_set_id=request.form.get("requirement_set_id", type=int),
                primary_screening_criterion_ids=criterion_ids, signal_definition_ids=signal_ids,
                outcome_definition_ids=outcome_ids,
                change_summary=(request.form.get("change_summary") or "").strip() or "Rule Set updated during preparation.",
                created_by=(request.form.get("created_by") or "").strip() or None,
            )
            session.commit()
        except ValueError:
            session.rollback()
        return redirect(url_for("session_detail", session_id=session_id))


@app.route("/sessions/<int:session_id>/rule-set/confirm", methods=["POST"])
def session_confirm_rule_set(session_id: int):
    with SessionFactory() as session:
        confirmed_by = (request.form.get("confirmed_by") or "").strip()
        if confirmed_by:
            try:
                rs_svc.confirm_rule_set_version(
                    session, session_id, confirmed_by=confirmed_by,
                    note=(request.form.get("note") or "").strip() or None,
                )
                session.commit()
            except ValueError:
                session.rollback()
        return redirect(url_for("session_detail", session_id=session_id))


@app.route("/sessions/<int:session_id>/rule-changes/new", methods=["POST"])
def session_propose_rule_change(session_id: int):
    with SessionFactory() as session:
        criterion_ids = [int(v) for v in request.form.getlist("criterion_ids") if v]
        try:
            rc_svc.propose_rule_change(
                session, session_id,
                rules_changed_summary=(request.form.get("rules_changed_summary") or "").strip(),
                reason=(request.form.get("reason") or "").strip(),
                scope=request.form.get("scope") or "",
                performed_by=(request.form.get("performed_by") or "").strip() or None,
                requirement_set_id=request.form.get("requirement_set_id", type=int),
                primary_screening_criterion_ids=criterion_ids or None,
            )
            session.commit()
        except ValueError:
            session.rollback()
        return redirect(url_for("session_detail", session_id=session_id))


@app.route("/rule-change-impacts/<int:impact_id>/mark-reviewed", methods=["POST"])
def rule_change_impact_mark_reviewed(impact_id: int):
    with SessionFactory() as session:
        impact = rc_svc.mark_impact_reviewed(
            session, impact_id, note=(request.form.get("note") or "").strip() or None,
        )
        session_id = impact.rule_change.session_id
        session.commit()
        return redirect(request.form.get("next") or url_for("session_detail", session_id=session_id))


# ===========================================================================
# Task 5D — Candidate Communication + Interview Scheduling
# ===========================================================================

@app.route("/acquisition-sources")
def acquisition_sources_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        acq_svc.seed_default_acquisition_sources(session, restaurant_id=restaurant.id)  # idempotent
        session.commit()
        return render_template(
            "acquisition_sources_home.html",
            sources=acq_svc.list_acquisition_sources(session, restaurant_id=restaurant.id, active_only=False),
            active_nav="acquisition-sources",
        )


@app.route("/acquisition-sources/new", methods=["POST"])
def acquisition_source_create():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        name = (request.form.get("name") or "").strip()
        if name:
            try:
                acq_svc.create_acquisition_source(
                    session, restaurant_id=restaurant.id, name=name,
                    description=(request.form.get("description") or "").strip() or None,
                )
                session.commit()
            except ValueError:
                session.rollback()
        return redirect(url_for("acquisition_sources_home"))


@app.route("/applications/<int:application_id>/acquisition-source", methods=["POST"])
def application_set_acquisition_source(application_id: int):
    with SessionFactory() as session:
        try:
            acq_svc.set_application_acquisition_source(
                session, application_id,
                acquisition_source_id=request.form.get("acquisition_source_id", type=int),
                other_text=(request.form.get("other_text") or "").strip() or None,
            )
            session.commit()
        except ValueError:
            session.rollback()
        return redirect(request.form.get("next") or url_for("application_dossier", application_id=application_id))


@app.route("/communication-templates")
def communication_templates_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        return render_template(
            "communication_templates_home.html",
            templates=tmpl_svc.list_templates(session, restaurant_id=restaurant.id, active_only=False),
            trigger_events=cm.TRIGGER_EVENTS, stages=stgm.STAGES,
            outcome_definitions=outcome_svc.list_outcome_definitions(session, restaurant_id=restaurant.id),
            active_nav="communication-templates",
        )


@app.route("/communication-templates/new", methods=["POST"])
def communication_template_create():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        trigger_event = request.form.get("trigger_event")
        if trigger_event:
            try:
                tmpl_svc.create_template(
                    session, restaurant_id=restaurant.id, trigger_event=trigger_event,
                    location_label=(request.form.get("location_label") or "").strip() or None,
                    role=(request.form.get("role") or "").strip() or None,
                    stage=(request.form.get("stage") or "").strip() or None,
                    outcome_definition_id=request.form.get("outcome_definition_id", type=int),
                    purpose=(request.form.get("purpose") or "").strip() or None,
                    language=(request.form.get("language") or "en").strip() or "en",
                    sms_text=(request.form.get("sms_text") or "").strip() or None,
                    email_subject=(request.form.get("email_subject") or "").strip() or None,
                    email_body=(request.form.get("email_body") or "").strip() or None,
                )
                session.commit()
            except ValueError:
                session.rollback()
        return redirect(url_for("communication_templates_home"))


@app.route("/communication-templates/<int:template_id>/update", methods=["POST"])
def communication_template_update(template_id: int):
    with SessionFactory() as session:
        try:
            tmpl_svc.update_template(
                session, template_id,
                purpose=(request.form.get("purpose") or "").strip() or None,
                sms_text=(request.form.get("sms_text") or "").strip() or None,
                email_subject=(request.form.get("email_subject") or "").strip() or None,
                email_body=(request.form.get("email_body") or "").strip() or None,
            )
            session.commit()
        except ValueError:
            session.rollback()
        return redirect(url_for("communication_templates_home"))


@app.route("/communication-templates/<int:template_id>/toggle-active", methods=["POST"])
def communication_template_toggle_active(template_id: int):
    with SessionFactory() as session:
        template = session.get(m.CommunicationTemplate, template_id)
        if template is not None:
            tmpl_svc.update_template(session, template_id, is_active=not template.is_active)
            session.commit()
        return redirect(url_for("communication_templates_home"))


@app.route("/reminder-policies")
def reminder_policies_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        from sqlalchemy import select as _select
        policies = list(session.scalars(
            _select(m.CommunicationReminderPolicy).where(m.CommunicationReminderPolicy.restaurant_id == restaurant.id)
        ).all())
        return render_template(
            "reminder_policies_home.html", policies=policies, trigger_events=cm.TRIGGER_EVENTS,
            outcome_definitions=outcome_svc.list_outcome_definitions(session, restaurant_id=restaurant.id),
            active_nav="reminder-policies",
        )


@app.route("/reminder-policies/new", methods=["POST"])
def reminder_policy_create():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        trigger_event = request.form.get("trigger_event")
        if trigger_event:
            policy = m.CommunicationReminderPolicy(
                restaurant_id=restaurant.id, trigger_event=trigger_event,
                stage=(request.form.get("stage") or "").strip() or None,
                role=(request.form.get("role") or "").strip() or None,
                reminder_count=request.form.get("reminder_count", type=int) or 0,
                first_reminder_delay_hours=request.form.get("first_reminder_delay_hours", type=int),
                reminder_interval_hours=request.form.get("reminder_interval_hours", type=int),
                final_deadline_hours=request.form.get("final_deadline_hours", type=int),
                auto_stop_enabled=bool(request.form.get("auto_stop_enabled")),
                auto_stop_outcome_definition_id=request.form.get("auto_stop_outcome_definition_id", type=int),
            )
            session.add(policy)
            session.commit()
        return redirect(url_for("reminder_policies_home"))


@app.route("/reminder-policies/<int:policy_id>/toggle-active", methods=["POST"])
def reminder_policy_toggle_active(policy_id: int):
    with SessionFactory() as session:
        policy = session.get(m.CommunicationReminderPolicy, policy_id)
        if policy is not None:
            policy.is_active = not policy.is_active
            session.commit()
        return redirect(url_for("reminder_policies_home"))


@app.route("/admin/process-reminders", methods=["POST"])
def admin_process_reminders():
    """Task §16-§20 — computed-on-demand processing (no scheduler exists
    anywhere in this codebase, by design; mirrors `outcome_service.
    list_due_reminders`'s own convention). An operator/cron would POST here
    periodically in a real deployment."""

    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        summary = comm_svc.process_reminders_and_deadlines(session, restaurant_id=restaurant.id)
        session.commit()
        return jsonify(summary)


@app.route("/applications/<int:application_id>/communications")
def application_communication_history(application_id: int):
    with SessionFactory() as session:
        application = app_svc.get_application(session, application_id)
        if application is None:
            return redirect(url_for("applications_home"))
        return render_template(
            "application_communication_history.html", application=application,
            communications=comm_svc.list_communications_for_application(session, application_id),
            inbound_messages=inbound_svc.list_inbound_for_application(session, application_id),
            active_nav="applications",
        )


@app.route("/applications/<int:application_id>/scheduling-windows/new", methods=["POST"])
def application_scheduling_window_create(application_id: int):
    """Task 5D-MICRO-FIX §3/§8 — the Dossier's window form is now the
    Application-specific OVERRIDE path only (`application_id` set,
    `session_id` left unset). The normal/default path is
    `session_scheduling_window_create` below, reached from the Selection
    Session page."""

    with SessionFactory() as session:
        try:
            from datetime import datetime as _dt
            window_date = _dt.strptime(request.form.get("window_date", ""), "%Y-%m-%d").date()
            start_time = _dt.strptime(request.form.get("start_time", ""), "%H:%M").time()
            end_time = _dt.strptime(request.form.get("end_time", ""), "%H:%M").time()
            sched_svc.create_scheduling_window(
                session, application_id=application_id, interview_stage=request.form.get("interview_stage"),
                window_date=window_date, start_time=start_time, end_time=end_time,
                slot_duration_minutes=request.form.get("slot_duration_minutes", type=int) or 30,
                capacity_per_slot=request.form.get("capacity_per_slot", type=int) or 1,
                created_by=(request.form.get("created_by") or "").strip() or None,
                notes=(request.form.get("notes") or "").strip() or None,
            )
            session.commit()
        except (ValueError, TypeError):
            session.rollback()
        return redirect(request.form.get("next") or url_for("application_dossier", application_id=application_id))


@app.route("/sessions/<int:session_id>/scheduling-windows/new", methods=["POST"])
def session_scheduling_window_create(session_id: int):
    """Task 5D-MICRO-FIX §1/§3/§8 — the NORMAL path: one scheduling window
    offered once for the whole Selection Session/stage, shared by every
    eligible Application in it, never recreated per candidate."""

    with SessionFactory() as session:
        try:
            from datetime import datetime as _dt
            window_date = _dt.strptime(request.form.get("window_date", ""), "%Y-%m-%d").date()
            start_time = _dt.strptime(request.form.get("start_time", ""), "%H:%M").time()
            end_time = _dt.strptime(request.form.get("end_time", ""), "%H:%M").time()
            sched_svc.create_scheduling_window(
                session, session_id=session_id, interview_stage=request.form.get("interview_stage"),
                window_date=window_date, start_time=start_time, end_time=end_time,
                slot_duration_minutes=request.form.get("slot_duration_minutes", type=int) or 30,
                capacity_per_slot=request.form.get("capacity_per_slot", type=int) or 1,
                created_by=(request.form.get("created_by") or "").strip() or None,
                notes=(request.form.get("notes") or "").strip() or None,
            )
            session.commit()
        except (ValueError, TypeError):
            session.rollback()
        return redirect(url_for("session_detail", session_id=session_id))


@app.route("/applications/<int:application_id>/inbound", methods=["POST"])
def application_record_inbound(application_id: int):
    """No real SMS/Email webhook exists in this environment (task §30);
    this route is Selection's own honest stand-in for "an inbound message
    arrived" — used by the validation suite and by a Selezionatore manually
    recording a phone call/text reported to them."""

    with SessionFactory() as session:
        raw_text = (request.form.get("raw_text") or "").strip()
        if raw_text:
            inbound_svc.record_inbound(
                session, application_id, channel=request.form.get("channel") or cm.CHANNEL_SMS, raw_text=raw_text,
                source=(request.form.get("source") or "MANUAL_ENTRY"),
            )
            session.commit()
        return redirect(request.form.get("next") or url_for("application_communication_history", application_id=application_id))


@app.route("/inbound/<int:inbound_id>/correct-classification", methods=["POST"])
def inbound_correct_classification(inbound_id: int):
    with SessionFactory() as session:
        new_classification = request.form.get("new_classification")
        corrected_by = (request.form.get("corrected_by") or "").strip()
        if new_classification and corrected_by:
            try:
                inbound = inbound_svc.correct_classification(
                    session, inbound_id, new_classification=new_classification, corrected_by=corrected_by,
                    reason=(request.form.get("reason") or "").strip() or None,
                )
                application_id = inbound.application_id
                session.commit()
            except ValueError:
                session.rollback()
                application_id = None
        else:
            application_id = session.get(m.InboundCommunication, inbound_id).application_id
        return redirect(url_for("application_communication_history", application_id=application_id))


@app.route("/inbound/<int:inbound_id>/acknowledge", methods=["POST"])
def inbound_acknowledge_alert(inbound_id: int):
    with SessionFactory() as session:
        acknowledged_by = (request.form.get("acknowledged_by") or "").strip() or "Selezionatore"
        inbound = inbound_svc.acknowledge_alert(session, inbound_id, acknowledged_by=acknowledged_by)
        application_id = inbound.application_id
        session.commit()
        return redirect(request.form.get("next") or url_for("application_communication_history", application_id=application_id))


@app.route("/alerts")
def alerts_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        return render_template(
            "alerts_home.html", alerts=inbound_svc.list_open_alerts(session, restaurant_id=restaurant.id),
            active_nav="alerts",
        )


# ---------------------------------------------------------------------------
# Candidate-facing scheduling page (task §12/§31) — reached only via an
# opaque token, never an internal Application id; exposes the minimum
# information needed to schedule/reschedule and nothing from the rest of
# RF-One.
# ---------------------------------------------------------------------------

@app.route("/schedule/<token>")
def candidate_schedule_page(token: str):
    with SessionFactory() as session:
        token_row = sched_svc.resolve_token(session, token)
        if token_row is None:
            return render_template("candidate_schedule_invalid.html"), 404

        application = app_svc.get_application(session, token_row.application_id)
        restaurant = session.get(m.Restaurant, application.restaurant_id) if application.restaurant_id else None
        current_appointment = sched_svc.get_current_appointment(
            session, application.id, interview_stage=token_row.interview_stage,
        )
        slots = sched_svc.list_available_slots(session, application.id, interview_stage=token_row.interview_stage)
        return render_template(
            "candidate_schedule.html", token=token, application=application, restaurant_name=(restaurant.name if restaurant else ""),
            interview_stage=token_row.interview_stage, slots=slots, current_appointment=current_appointment,
        )


@app.route("/schedule/<token>/book", methods=["POST"])
def candidate_schedule_book(token: str):
    with SessionFactory() as session:
        token_row = sched_svc.resolve_token(session, token)
        if token_row is None:
            return render_template("candidate_schedule_invalid.html"), 404

        window_id = request.form.get("window_id", type=int)
        slot_start_raw = request.form.get("slot_start")
        error = None
        if window_id and slot_start_raw:
            try:
                from datetime import datetime as _dt
                slot_start_at = _dt.fromisoformat(slot_start_raw)
                sched_svc.book_slot(
                    session, token_row.application_id, interview_stage=token_row.interview_stage,
                    window_id=window_id, slot_start_at=slot_start_at,
                )
                session.commit()
            except ValueError as exc:
                session.rollback()
                error = str(exc)
        else:
            error = "Please choose an available time."

        application = app_svc.get_application(session, token_row.application_id)
        restaurant = session.get(m.Restaurant, application.restaurant_id) if application.restaurant_id else None
        current_appointment = sched_svc.get_current_appointment(
            session, application.id, interview_stage=token_row.interview_stage,
        )
        slots = sched_svc.list_available_slots(session, application.id, interview_stage=token_row.interview_stage)
        return render_template(
            "candidate_schedule.html", token=token, application=application, restaurant_name=(restaurant.name if restaurant else ""),
            interview_stage=token_row.interview_stage, slots=slots, current_appointment=current_appointment, error=error,
        )


# ===========================================================================
# Task 5E — Job Posting Generator + Application Intake + Missing-Evidence
# Pre-Screening
# ===========================================================================

@app.route("/sessions/<int:session_id>/job-postings/generate", methods=["POST"])
def job_posting_generate(session_id: int):
    with SessionFactory() as session:
        try:
            job_posting = jp_svc.generate_base_posting(
                session, session_id, created_by=(request.form.get("created_by") or "").strip() or None,
            )
            session.commit()
            return redirect(url_for("job_posting_detail", job_posting_id=job_posting.id))
        except ValueError:
            session.rollback()
            return redirect(url_for("session_detail", session_id=session_id))


@app.route("/job-postings/<int:job_posting_id>")
def job_posting_detail(job_posting_id: int):
    with SessionFactory() as session:
        job_posting = jp_svc.get_job_posting(session, job_posting_id)
        if job_posting is None:
            return redirect(url_for("sessions_home"))
        restaurant_id = job_posting.restaurant_id
        chan_svc.seed_default_channels(session, restaurant_id=restaurant_id)  # idempotent
        session.commit()
        variants = jp_svc.list_channel_variants(session, job_posting_id)
        variant_rows = [
            {
                "variant": v, "current_version": jp_svc.get_current_variant_version(session, v.id),
                "publications": chan_svc.list_publications_for_job_posting(session, job_posting_id),
            }
            for v in variants
        ]
        return render_template(
            "job_posting_detail.html", job_posting=job_posting, current_version=jp_svc.get_current_version(session, job_posting_id),
            versions=jp_svc.list_versions(session, job_posting_id), variant_rows=variant_rows,
            channels=chan_svc.list_channels(session, restaurant_id=restaurant_id),
            publications=chan_svc.list_publications_for_job_posting(session, job_posting_id),
            active_nav="sessions",
        )


@app.route("/job-postings/<int:job_posting_id>/edit", methods=["POST"])
def job_posting_edit(job_posting_id: int):
    with SessionFactory() as session:
        try:
            jp_svc.edit_posting(
                session, job_posting_id, author=(request.form.get("author") or "").strip() or None,
                reason=(request.form.get("reason") or "").strip() or None,
                title=(request.form.get("title") or "").strip() or None,
                company_description=(request.form.get("company_description") or "").strip() or None,
                branch_description=(request.form.get("branch_description") or "").strip() or None,
                role_summary=(request.form.get("role_summary") or "").strip() or None,
                responsibilities=(request.form.get("responsibilities") or "").strip() or None,
                minimum_requirements=(request.form.get("minimum_requirements") or "").strip() or None,
                preferred_experience=(request.form.get("preferred_experience") or "").strip() or None,
                availability_expectations=(request.form.get("availability_expectations") or "").strip() or None,
                schedule_description=(request.form.get("schedule_description") or "").strip() or None,
                compensation_description=(request.form.get("compensation_description") or "").strip() or None,
                benefits_description=(request.form.get("benefits_description") or "").strip() or None,
                location_context=(request.form.get("location_context") or "").strip() or None,
                application_instructions=(request.form.get("application_instructions") or "").strip() or None,
                other_info=(request.form.get("other_info") or "").strip() or None,
            )
            session.commit()
        except ValueError:
            session.rollback()
        return redirect(url_for("job_posting_detail", job_posting_id=job_posting_id))


@app.route("/job-postings/<int:job_posting_id>/approve", methods=["POST"])
def job_posting_approve(job_posting_id: int):
    with SessionFactory() as session:
        try:
            jp_svc.approve_posting(session, job_posting_id, approved_by=(request.form.get("approved_by") or "").strip())
            session.commit()
        except ValueError:
            session.rollback()
        return redirect(url_for("job_posting_detail", job_posting_id=job_posting_id))


@app.route("/job-postings/<int:job_posting_id>/channel-variants/new", methods=["POST"])
def job_posting_channel_variant_create(job_posting_id: int):
    with SessionFactory() as session:
        try:
            jp_svc.create_channel_variant(
                session, job_posting_id, request.form.get("channel_id", type=int),
                variant_text=(request.form.get("variant_text") or "").strip(),
                title_override=(request.form.get("title_override") or "").strip() or None,
                created_by=(request.form.get("created_by") or "").strip() or None,
            )
            session.commit()
        except ValueError:
            session.rollback()
        return redirect(url_for("job_posting_detail", job_posting_id=job_posting_id))


@app.route("/job-posting-channel-variants/<int:variant_id>/edit", methods=["POST"])
def job_posting_channel_variant_edit(variant_id: int):
    with SessionFactory() as session:
        variant = jp_svc.get_channel_variant(session, variant_id)
        job_posting_id = variant.job_posting_id if variant else None
        try:
            jp_svc.edit_channel_variant(
                session, variant_id, variant_text=(request.form.get("variant_text") or "").strip(),
                author=(request.form.get("author") or "").strip() or None,
                title_override=(request.form.get("title_override") or "").strip() or None,
                reason=(request.form.get("reason") or "").strip() or None,
            )
            session.commit()
        except ValueError:
            session.rollback()
        return redirect(url_for("job_posting_detail", job_posting_id=job_posting_id) if job_posting_id else url_for("sessions_home"))


@app.route("/job-posting-channel-variants/<int:variant_id>/approve", methods=["POST"])
def job_posting_channel_variant_approve(variant_id: int):
    with SessionFactory() as session:
        variant = jp_svc.get_channel_variant(session, variant_id)
        job_posting_id = variant.job_posting_id if variant else None
        try:
            jp_svc.approve_channel_variant(session, variant_id, approved_by=(request.form.get("approved_by") or "").strip())
            session.commit()
        except ValueError:
            session.rollback()
        return redirect(url_for("job_posting_detail", job_posting_id=job_posting_id) if job_posting_id else url_for("sessions_home"))


@app.route("/job-posting-channel-variants/<int:variant_id>/publications/new", methods=["POST"])
def channel_publication_create(variant_id: int):
    with SessionFactory() as session:
        variant = jp_svc.get_channel_variant(session, variant_id)
        job_posting_id = variant.job_posting_id if variant else None
        try:
            cost_amount = request.form.get("cost_amount", type=float)
            chan_svc.record_publication(
                session, variant_id, placement_label=(request.form.get("placement_label") or "").strip(),
                external_link=(request.form.get("external_link") or "").strip() or None,
                cost_amount_cents=int(round(cost_amount * 100)) if cost_amount is not None else None,
                cost_currency=(request.form.get("cost_currency") or "").strip() or None,
                notes=(request.form.get("notes") or "").strip() or None,
                created_by=(request.form.get("created_by") or "").strip() or None,
            )
            session.commit()
        except ValueError:
            session.rollback()
        return redirect(url_for("job_posting_detail", job_posting_id=job_posting_id) if job_posting_id else url_for("sessions_home"))


@app.route("/channels")
def channels_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        chan_svc.seed_default_channels(session, restaurant_id=restaurant.id)  # idempotent
        session.commit()
        return render_template(
            "channels_home.html", channels=chan_svc.list_channels(session, restaurant_id=restaurant.id, active_only=False),
            acquisition_sources=acq_svc.list_acquisition_sources(session, restaurant_id=restaurant.id, active_only=False),
            active_nav="channels",
        )


@app.route("/channels/new", methods=["POST"])
def channel_create():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        name = (request.form.get("name") or "").strip()
        if name:
            chan_svc.create_channel(
                session, restaurant_id=restaurant.id, name=name, is_connected=bool(request.form.get("is_connected")),
                is_paid=bool(request.form.get("is_paid")), supports_metrics=bool(request.form.get("supports_metrics")),
                supports_cost_tracking=bool(request.form.get("supports_cost_tracking")),
                default_acquisition_source_id=request.form.get("default_acquisition_source_id", type=int),
            )
            session.commit()
        return redirect(url_for("channels_home"))


@app.route("/application-questions")
def application_questions_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        questions = aq_svc.list_questions_for_context(session, restaurant_id=restaurant.id, active_only=False)
        compliance_status = {
            q.id: compliance_svc.review_status_summary(session, cpm.APPLICATION_QUESTION_DEFINITION, q.id) for q in questions
        }
        return render_template(
            "application_questions_home.html",
            questions=questions,
            criteria=ps_svc.list_criteria(session, restaurant_id=restaurant.id, active_only=False),
            response_types=jpm.RESPONSE_TYPES,
            sessions=sess_svc.list_sessions(session, restaurant_id=restaurant.id),
            active_nav="application-questions",
            compliance_status=compliance_status, compliance_object_type=cpm.APPLICATION_QUESTION_DEFINITION,
            disposition_actions=cpm.DISPOSITION_ACTIONS, compliance_disclaimer=cpm.DISCLAIMER,
        )


@app.route("/application-questions/new", methods=["POST"])
def application_question_create():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        question_text = (request.form.get("question_text") or "").strip()
        if question_text:
            try:
                aq_svc.create_question(
                    session, restaurant_id=restaurant.id, question_text=question_text,
                    session_id=request.form.get("session_id", type=int),
                    target_role=(request.form.get("target_role") or "").strip() or None,
                    response_type=request.form.get("response_type") or jpm.RESPONSE_TEXT,
                    is_required=bool(request.form.get("is_required")),
                    related_criterion_id=request.form.get("related_criterion_id", type=int),
                )
                session.commit()
            except ValueError:
                session.rollback()
        return redirect(url_for("application_questions_home"))


@app.route("/application-questions/<int:question_id>/toggle-active", methods=["POST"])
def application_question_toggle_active(question_id: int):
    with SessionFactory() as session:
        question = session.get(m.ApplicationQuestionDefinition, question_id)
        if question is not None:
            try:
                if not question.is_active:
                    compliance_svc.assert_activation_allowed(session, cpm.APPLICATION_QUESTION_DEFINITION, question_id)
                aq_svc.update_question(session, question_id, is_active=not question.is_active)
                session.commit()
            except ValueError:
                session.rollback()
        return redirect(url_for("application_questions_home"))


@app.route("/channel-analytics")
def channel_analytics_home():
    with SessionFactory() as session:
        restaurant = _bootstrap_restaurant(session)
        rows = analytics_svc.get_channel_funnel_metrics(session, restaurant_id=restaurant.id)
        recommendations = {r["publication_id"]: r for r in analytics_svc.recommend_channel_actions(rows)}
        return render_template(
            "channel_analytics.html", rows=rows, recommendations=recommendations, active_nav="channel-analytics",
        )


# ---------------------------------------------------------------------------
# Public Web Application Form (task Part B) — reached only via an opaque
# Channel Tracking Link token, never an internal Session/JobPosting id.
# ---------------------------------------------------------------------------

@app.route("/apply/<token>")
def public_application_form(token: str):
    with SessionFactory() as session:
        context = chan_svc.resolve_application_context(session, token)
        if context is None:
            return render_template("candidate_schedule_invalid.html"), 404
        restaurant = session.get(m.Restaurant, context["job_posting"].restaurant_id) if context["job_posting"].restaurant_id else None
        questions = aq_svc.list_questions_for_context(
            session, restaurant_id=context["job_posting"].restaurant_id, session_id=context["session"].id,
            target_role=context["session"].target_role,
        )
        return render_template(
            "apply_form.html", token=token, job_posting=context["job_posting"], variant_version=context["variant_version"],
            selection_session=context["session"], restaurant_name=(restaurant.name if restaurant else ""),
            questions=questions,
        )


@app.route("/apply/<token>", methods=["POST"])
def public_application_submit(token: str):
    with SessionFactory() as session:
        context = chan_svc.resolve_application_context(session, token)
        if context is None:
            return render_template("candidate_schedule_invalid.html"), 404

        error = None
        first_name = (request.form.get("first_name") or "").strip()
        last_name = (request.form.get("last_name") or "").strip()
        email = (request.form.get("email") or "").strip()
        phone = (request.form.get("phone") or "").strip() or None
        resume_file = request.files.get("resume_file")
        consent = bool(request.form.get("consent"))

        if not (first_name and last_name and email and resume_file and resume_file.filename):
            error = "First name, last name, email, and a CV/résumé file are all required."
        elif not consent:
            error = "Please acknowledge the consent/privacy statement to submit your application."
        else:
            ext = os.path.splitext(resume_file.filename)[1].lower()
            if ext not in ALLOWED_EXT:
                error = f"Unsupported CV file format: {ext or '(none)'}."

        if error:
            questions = aq_svc.list_questions_for_context(
                session, restaurant_id=context["job_posting"].restaurant_id, session_id=context["session"].id,
                target_role=context["session"].target_role,
            )
            return render_template(
                "apply_form.html", token=token, job_posting=context["job_posting"], variant_version=context["variant_version"],
                selection_session=context["session"], restaurant_name="", questions=questions, error=error,
            ), 400

        unique_name = f"{uuid.uuid4().hex[:8]}_{resume_file.filename}"
        saved_path = os.path.join(UPLOAD_DIR, unique_name)
        resume_file.save(saved_path)
        raw_text = extract_text(saved_path, ext)
        content_hash = compute_content_hash(raw_text, resume_file.filename)

        answers = {}
        for key, value in request.form.items():
            if key.startswith("question_") and value.strip():
                try:
                    answers[int(key[len("question_"):])] = value
                except ValueError:
                    continue

        try:
            result = intake_svc.submit_application(
                session, restaurant_id=context["job_posting"].restaurant_id,
                channel_publication_id=context["publication"].id, selection_session_id=context["session"].id,
                target_role=context["session"].target_role, original_filename=resume_file.filename, raw_text=raw_text,
                content_hash=content_hash, first_name=first_name, last_name=last_name, email=email, phone=phone,
                candidate_message=(request.form.get("candidate_message") or "").strip() or None, answers=answers,
            )
            session.commit()
        except ValueError as exc:
            session.rollback()
            questions = aq_svc.list_questions_for_context(
                session, restaurant_id=context["job_posting"].restaurant_id, session_id=context["session"].id,
                target_role=context["session"].target_role,
            )
            return render_template(
                "apply_form.html", token=token, job_posting=context["job_posting"], variant_version=context["variant_version"],
                selection_session=context["session"], restaurant_name="", questions=questions, error=str(exc),
            ), 400

        return render_template("apply_confirmation.html", is_repeated_applicant=result.is_repeated_applicant)


# ---------------------------------------------------------------------------
# Public Missing-Evidence Questionnaire page (task §26/§31).
# ---------------------------------------------------------------------------

@app.route("/missing-evidence/<token>")
def missing_evidence_page(token: str):
    with SessionFactory() as session:
        questionnaire = me_svc.resolve_questionnaire_token(session, token)
        if questionnaire is None:
            return render_template("candidate_schedule_invalid.html"), 404
        return render_template(
            "missing_evidence_questionnaire.html", token=token, questionnaire=questionnaire,
            questions=me_svc.list_questions(session, questionnaire.id),
        )


@app.route("/missing-evidence/<token>", methods=["POST"])
def missing_evidence_submit(token: str):
    with SessionFactory() as session:
        questionnaire = me_svc.resolve_questionnaire_token(session, token)
        if questionnaire is None:
            return render_template("candidate_schedule_invalid.html"), 404

        answers = {}
        for key, value in request.form.items():
            if key.startswith("answer_") and value.strip():
                try:
                    answers[int(key[len("answer_"):])] = value.strip()
                except ValueError:
                    continue

        me_svc.submit_answers(session, questionnaire.id, answers)
        session.commit()
        return render_template("missing_evidence_confirmation.html")


# ===========================================================================
# Task 5F — Compliance / Rule Review + Selection Audit / Explainability
# ===========================================================================

@app.route("/compliance-reviews")
def compliance_reviews_home():
    with SessionFactory() as session:
        reviews = compliance_svc.list_all_reviews(session)
        rows = [
            {
                "review": r, "obj": compliance_svc.get_object(session, r.object_type, r.object_id),
                "dispositions": compliance_svc.list_dispositions(session, r.id),
            }
            for r in reviews
        ]
        return render_template(
            "compliance_reviews_home.html", rows=rows, disclaimer=cpm.DISCLAIMER,
            disposition_actions=cpm.DISPOSITION_ACTIONS, active_nav="compliance",
        )


@app.route("/compliance/review", methods=["POST"])
def compliance_review_create():
    with SessionFactory() as session:
        object_type = request.form.get("object_type")
        object_id = request.form.get("object_id", type=int)
        try:
            compliance_svc.review_object(session, object_type, object_id)
            session.commit()
        except ValueError:
            session.rollback()
        return redirect(request.form.get("next") or url_for("compliance_reviews_home"))


@app.route("/compliance/reviews/<int:review_id>/disposition", methods=["POST"])
def compliance_disposition_create(review_id: int):
    with SessionFactory() as session:
        try:
            compliance_svc.record_disposition(
                session, review_id, action=request.form.get("action"),
                performed_by=(request.form.get("performed_by") or "").strip() or None,
                final_text=(request.form.get("final_text") or "").strip() or None,
                reason=(request.form.get("reason") or "").strip() or None,
            )
            session.commit()
        except ValueError:
            session.rollback()
        return redirect(request.form.get("next") or url_for("compliance_reviews_home"))


@app.route("/applications/<int:application_id>/audit")
def application_audit(application_id: int):
    """Task §20 — the Selection Audit/Explainability view, reachable from
    the Candidate Dossier; never a redesign of the Dossier itself."""

    with SessionFactory() as session:
        application = app_svc.get_application(session, application_id)
        if application is None:
            return redirect(url_for("applications_home"))
        report = audit_svc.build_audit(session, application_id)
        session.commit()
        return render_template("audit.html", report=report, active_nav="applications")


@app.route("/applications/<int:application_id>/audit.json")
def application_audit_json(application_id: int):
    with SessionFactory() as session:
        application = app_svc.get_application(session, application_id)
        if application is None:
            return jsonify({"error": "Application not found"}), 404
        report = audit_svc.build_audit(session, application_id)
        session.commit()
        return jsonify(audit_svc.to_json_dict(report))


if __name__ == "__main__":
    print(f"Selection database: {redact_database_url(_DB_URL)}")
    app.run(debug=True, host="127.0.0.1", port=5050)
