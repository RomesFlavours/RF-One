"""RF-One interview administration, personal tasks and candidate results."""
import json

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import select

from auth import load_current_account
from rfone_data_store import models as m
from rfone_data_store.interviews import directory_bridge as people
from rfone_data_store.interviews import service as svc
from rfone_data_store.interviews.provider import ProviderError, generate


STATUS_LABELS = {"REQUESTED": "Requested", "IN_PROGRESS": "In progress", "COMPLETED": "Completed"}


def home_state(db, account):
    ready = svc.available(db)
    tasks = []
    if ready:
        for row in svc.pending(db, account):
            requester = db.get(m.RFOneAccount, row.requester_id)
            tasks.append(dict(id=row.id, purpose=row.purpose,
                requester=requester.display_name if requester else "Administrator",
                status=STATUS_LABELS[row.status]))
    return dict(interview_tasks=tasks, interviews_ready=ready)


def register_interview_routes(app, *, SessionFactory, require_login, require_admin, require_csrf, require_domain_access):
    def admin_gate(view):
        return require_domain_access("ORGANIZATION")(view)
    app.jinja_env.globals["interview_status_labels"] = STATUS_LABELS

    def ready(db):
        if not svc.available(db) or not people.available(db):
            abort(503, description="Interviews are not available yet. Please contact your administrator.")

    @app.route("/admin/interviews", methods=["GET", "POST"])
    @admin_gate
    def interview_admin():
        with SessionFactory() as db:
            ready(db)
            actor = load_current_account(db)
            try:
                selected_id = int(request.values.get("person_id", "0"))
            except ValueError:
                abort(400)
            selected = people.get_person(db, selected_id) if selected_id else None
            if selected_id and selected is None:
                abort(404)
            if request.method == "POST":
                require_csrf()
                try:
                    row = svc.request_for_person(db, actor, selected_id,
                        request.form.get("purpose", ""))
                    db.commit()
                    flash("Interview requested. The recipient will find it on their MyRFOne home page.", "info")
                    return redirect(url_for("interview_admin_results", session_id=row.id))
                except PermissionError:
                    abort(403)
                except ValueError as exc:
                    db.rollback()
                    flash(str(exc), "error")
            persons = people.list_people(db)
            delivery = people.delivery_accounts(db)
            rows = svc.managed(db, actor)
            if selected:
                rows = [row for row in rows if (svc.interview_person(db, row) is not None and
                    svc.interview_person(db, row).id == selected.id)]
            names = {a.id: a.display_name for a in db.scalars(select(m.RFOneAccount))}
            row_people = {row.id: svc.interview_person(db, row) for row in rows}
            return render_template("interview_admin.html", people=persons, delivery=delivery,
                rows=rows, names=names, row_people=row_people, selected_person=selected)

    @app.get("/admin/interviews/<session_id>")
    @admin_gate
    def interview_admin_results(session_id):
        with SessionFactory() as db:
            ready(db)
            try:
                row = svc.load(db, load_current_account(db), session_id, admin=True)
            except PermissionError:
                abort(404)
            return render_template("interview_results.html", row=row,
                recipient=db.get(m.RFOneAccount, row.recipient_id),
                person=svc.interview_person(db, row),
                requester=db.get(m.RFOneAccount, row.requester_id),
                answer_count=sum(msg['role'] == 'user' for msg in json.loads(row.transcript)),
                result=json.loads(row.results) if row.results else None,
                messages=json.loads(row.transcript) if row.status == "COMPLETED" else [])

    @app.route("/interviews/<session_id>", methods=["GET", "POST"])
    @require_login
    def interview_session(session_id):
        wants_json = request.accept_mimetypes.best == "application/json"
        error, status = None, 200
        with SessionFactory() as db:
            ready(db)
            actor = load_current_account(db)
            try:
                row = svc.load(db, actor, session_id)
            except PermissionError:
                abort(404)
            if request.method == "POST":
                require_csrf()
                try:
                    try:
                        revision = int(request.form.get("revision", "-1"))
                    except ValueError:
                        abort(400)
                    # Release the read transaction before a potentially slow AI
                    # call. The shared factory keeps loaded values on commit;
                    # advance still uses a conditional revision update to win.
                    db.commit()
                    provider = app.config.get("INTERVIEW_PROVIDER") or generate
                    def call_provider(payload):
                        # Identity-link validation also performs reads. Release
                        # those before waiting on AI, then rely on revision CAS.
                        db.commit()
                        return provider(payload)
                    svc.advance(db, actor, row, revision, request.form.get("action", ""),
                        request.form.get("message", ""), call_provider,
                        channel=request.form.get("channel", "text"),
                        consent=request.form.get("consent") == "yes")
                    db.commit()
                    if wants_json:
                        messages = json.loads(row.transcript)
                        return jsonify(status=row.status, revision=row.revision, messages=messages,
                            redirect=url_for("interview_session", session_id=row.id))
                    return redirect(url_for("interview_session", session_id=row.id))
                except svc.ConflictError as exc:
                    error, status = str(exc), 409
                except ProviderError as exc:
                    error, status = str(exc), 503
                except ValueError as exc:
                    error, status = str(exc), 400
                if error:
                    db.rollback()
                    if wants_json:
                        return jsonify(error=error), status
            requester = db.get(m.RFOneAccount, row.requester_id)
            response = app.make_response((render_template("interview_session.html", row=row,
                messages=json.loads(row.transcript), requester=requester, person=svc.interview_person(db, row), error=error,
                unsent=request.form.get("message", "") if error else ""), status))
            response.headers["Cache-Control"] = "no-store"
            return response

    @app.after_request
    def interview_private_pages(response):
        if request.endpoint in {"home", "interview_admin", "interview_admin_results", "interview_session"}:
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    @app.get("/people")
    @require_domain_access("EMPLOYEES")
    def people_home():
        return redirect(url_for("employee_directory_home"))

    @app.get("/people/<int:person_id>")
    @require_domain_access("EMPLOYEES")
    def person_detail(person_id):
        return redirect(url_for("employee_directory_detail", employee_id=person_id))

    @app.context_processor
    def interview_navigation_context():
        if request.endpoint not in {"interview_admin", "interview_admin_results"}:
            return {}
        from rfone_data_store import rfone_web_session as permissions
        with SessionFactory() as db:
            return dict(interview_directory_access=permissions.account_may_enter_domain(
                db, load_current_account(db), "EMPLOYEES"))

    @app.context_processor
    def interview_directory_context():
        if request.endpoint != "employee_directory_detail":
            return {}
        with SessionFactory() as db:
            actor = load_current_account(db)
            if not actor or not svc.available(db):
                return {}
            from rfone_data_store import rfone_web_session as permissions
            if not permissions.account_may_use_domain_item(db, actor, "ORGANIZATION", "interviews"):
                return {}
            person = people.get_person(db, request.view_args["employee_id"])
            if person is None:
                return {}
            rows = [row for row in svc.managed(db, actor) if row.person_id == person.id]
            return dict(interview_person=person, person_interviews=rows,
                interview_can_request=people.delivery_account(db, person.id) is not None)
