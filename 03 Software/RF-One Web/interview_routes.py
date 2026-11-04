"""RF-One interview administration, personal tasks and candidate results."""
import json

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import select

from auth import load_current_account
from rfone_data_store import models as m
from rfone_data_store import people_registry as people
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


def register_interview_routes(app, *, SessionFactory, require_login, require_admin, require_csrf):
    app.jinja_env.globals["interview_status_labels"] = STATUS_LABELS

    def ready(db):
        if not svc.available(db) or not people.available(db):
            abort(503, description="Interviews are not available yet. Please contact your administrator.")

    @app.route("/admin/interviews", methods=["GET", "POST"])
    @require_admin
    def interview_admin():
        with SessionFactory() as db:
            ready(db)
            actor = load_current_account(db)
            try:
                selected_id = int(request.values.get("person_id", "0"))
            except ValueError:
                abort(400)
            selected = db.get(m.CandidatePerson, selected_id) if selected_id else None
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
            persons = list(db.scalars(select(m.CandidatePerson).order_by(m.CandidatePerson.full_name)))
            delivery = {p.id: people.delivery_account(db, p.id) for p in persons}
            rows = svc.requested(db, actor)
            if selected:
                rows = [row for row in rows if (svc.interview_person(db, row) is not None and
                    svc.interview_person(db, row).id == selected.id)]
            names = {a.id: a.display_name for a in db.scalars(select(m.RFOneAccount))}
            row_people = {row.id: svc.interview_person(db, row) for row in rows}
            return render_template("interview_admin.html", people=persons, delivery=delivery,
                rows=rows, names=names, row_people=row_people, selected_person=selected)

    @app.get("/admin/interviews/<session_id>")
    @require_admin
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
                    svc.advance(db, actor, row, revision, request.form.get("action", ""),
                        request.form.get("message", ""), app.config.get("INTERVIEW_PROVIDER") or generate,
                        channel=request.form.get("channel", "text"))
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
        return response
