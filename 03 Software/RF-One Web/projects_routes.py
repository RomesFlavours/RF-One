"""MyRF Project Management — Projects list, a Project's Plan (tree + dialogs)
and its read-only Gantt.

`01 Domains/Business Domain/Restaurant/MyRF/Project Management/README.md`.

Every route is gated by `require_domain_access("PROJECTS")` and every POST
checks CSRF. Every Chapter and Task route carries its Project in the path and
answers 404 for an id of another Project, so a page never reads or changes
another Project's data. The rules live in `rfone_data_store.projects.service`;
this module only reads forms and renders pages. A refusal re-renders the page
with the dialog still open, holding the values entered and the reason; a
success redirects back to the page it came from.

Registered from `app.py` via `register_projects_routes(app, ...)`, which
passes in `require_domain_access`/`SessionFactory`/`require_csrf`
explicitly — this module never imports `app.py` itself.
"""

from __future__ import annotations

from functools import wraps

from flask import abort, flash, redirect, render_template, request, url_for

from rfone_data_store.projects import service
from rfone_data_store.projects.gantt import timeline_for


def register_projects_routes(app, *, require_domain_access, SessionFactory, require_csrf):
    gate = require_domain_access("PROJECTS")

    def scoped(view):
        """An id that is not in the opened Project is a 404, never another Project's data."""
        @wraps(view)
        def wrapped(*args, **kwargs):
            try:
                return view(*args, **kwargs)
            except service.ProjectScopeError:
                abort(404)
        return wrapped

    def _dialog_from_form(error, *, kind: str, action: str, item_id: int | None) -> dict:
        values = request.form.to_dict()
        values["predecessor_ids"] = request.form.getlist("predecessor_ids")
        return {"kind": kind, "action": action, "id": item_id, "values": values, "error": str(error)}

    # ------------------------------------------------------------ projects

    def _render_list(db, *, dialog: dict | None = None, status: int = 200):
        return render_template("projects_list.html", projects=service.list_projects(db), dialog=dialog), status

    @app.route("/projects")
    @gate
    def projects_list():
        with SessionFactory() as db:
            return _render_list(db)

    @app.route("/projects", methods=["POST"])
    @gate
    def projects_project_create():
        require_csrf()
        with SessionFactory() as db:
            try:
                project = service.create_project(db, name=request.form.get("name", ""))
            except service.ProjectValidationError as error:
                db.rollback()
                return _render_list(db, status=422, dialog=_dialog_from_form(
                    error, kind="project", action=url_for("projects_project_create"), item_id=None))
            db.commit()
            project_id = project.id
        flash("Project created.", "info")
        return redirect(url_for("projects_plan", project_id=project_id))

    @app.route("/projects/<int:project_id>/rename", methods=["POST"])
    @gate
    @scoped
    def projects_project_rename(project_id: int):
        require_csrf()
        back_to_plan = request.form.get("from") == "plan"
        with SessionFactory() as db:
            try:
                service.rename_project(db, project_id, name=request.form.get("name", ""))
            except service.ProjectValidationError as error:
                db.rollback()
                dialog = _dialog_from_form(error, kind="project", item_id=project_id,
                                           action=url_for("projects_project_rename", project_id=project_id))
                if back_to_plan:
                    return _render_plan(db, project_id, dialog=dialog, status=422)
                return _render_list(db, dialog=dialog, status=422)
            db.commit()
        flash("Project name saved.", "info")
        return redirect(url_for("projects_plan", project_id=project_id) if back_to_plan else url_for("projects_list"))

    @app.route("/projects/<int:project_id>/delete", methods=["POST"])
    @gate
    @scoped
    def projects_project_delete(project_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                service.delete_project(db, project_id)
            except service.ProjectValidationError as error:
                db.rollback()
                flash(str(error), "error")
                return redirect(url_for("projects_list"))
            db.commit()
        flash("Project deleted.", "info")
        return redirect(url_for("projects_list"))

    # ------------------------------------------------------------ a project's plan

    def _render_plan(db, project_id: int, *, dialog: dict | None = None, status: int = 200):
        plan = service.build_plan(db, project_id)
        return render_template("projects_plan.html", plan=plan, dialog=dialog), status

    def _refused(db, project_id: int, error, *, kind: str, action: str, item_id: int | None):
        db.rollback()
        return _render_plan(db, project_id, status=422,
                            dialog=_dialog_from_form(error, kind=kind, action=action, item_id=item_id))

    def _back_to_plan(project_id: int):
        return redirect(url_for("projects_plan", project_id=project_id))

    @app.route("/projects/<int:project_id>")
    @gate
    @scoped
    def projects_plan(project_id: int):
        with SessionFactory() as db:
            return _render_plan(db, project_id)

    @app.route("/projects/<int:project_id>/chapters", methods=["POST"])
    @gate
    @scoped
    def projects_chapter_create(project_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                service.create_chapter(db, project_id, title=request.form.get("title", ""),
                                       description=request.form.get("description"))
            except service.ProjectValidationError as error:
                return _refused(db, project_id, error, kind="chapter", item_id=None,
                                action=url_for("projects_chapter_create", project_id=project_id))
            db.commit()
        flash("Chapter created.", "info")
        return _back_to_plan(project_id)

    @app.route("/projects/<int:project_id>/chapters/<int:chapter_id>", methods=["POST"])
    @gate
    @scoped
    def projects_chapter_update(project_id: int, chapter_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                service.update_chapter(db, project_id, chapter_id, title=request.form.get("title", ""),
                                       description=request.form.get("description"))
            except service.ProjectValidationError as error:
                return _refused(db, project_id, error, kind="chapter", item_id=chapter_id,
                                action=url_for("projects_chapter_update", project_id=project_id, chapter_id=chapter_id))
            db.commit()
        flash("Chapter saved.", "info")
        return _back_to_plan(project_id)

    @app.route("/projects/<int:project_id>/chapters/<int:chapter_id>/delete", methods=["POST"])
    @gate
    @scoped
    def projects_chapter_delete(project_id: int, chapter_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                service.delete_chapter(db, project_id, chapter_id)
            except service.ProjectValidationError as error:
                db.rollback()
                flash(str(error), "error")
                return _back_to_plan(project_id)
            db.commit()
        flash("Chapter deleted.", "info")
        return _back_to_plan(project_id)

    @app.route("/projects/<int:project_id>/tasks", methods=["POST"])
    @gate
    @scoped
    def projects_task_create(project_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                service.create_task(db, project_id, service.task_input_from_form(request.form))
            except service.ProjectValidationError as error:
                return _refused(db, project_id, error, kind="task", item_id=None,
                                action=url_for("projects_task_create", project_id=project_id))
            db.commit()
        flash("Task created.", "info")
        return _back_to_plan(project_id)

    @app.route("/projects/<int:project_id>/tasks/<int:task_id>", methods=["POST"])
    @gate
    @scoped
    def projects_task_update(project_id: int, task_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                service.update_task(db, project_id, task_id, service.task_input_from_form(request.form))
            except service.ProjectValidationError as error:
                return _refused(db, project_id, error, kind="task", item_id=task_id,
                                action=url_for("projects_task_update", project_id=project_id, task_id=task_id))
            db.commit()
        flash("Task saved.", "info")
        return _back_to_plan(project_id)

    @app.route("/projects/<int:project_id>/tasks/<int:task_id>/delete", methods=["POST"])
    @gate
    @scoped
    def projects_task_delete(project_id: int, task_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                service.delete_task(db, project_id, task_id)
            except service.ProjectValidationError as error:
                db.rollback()
                flash(str(error), "error")
                return _back_to_plan(project_id)
            db.commit()
        flash("Task deleted.", "info")
        return _back_to_plan(project_id)

    # ------------------------------------------------------------ Gantt

    @app.route("/projects/<int:project_id>/gantt")
    @gate
    @scoped
    def projects_gantt(project_id: int):
        with SessionFactory() as db:
            plan = service.build_plan(db, project_id)
        return render_template("projects_gantt.html", plan=plan, timeline=timeline_for(plan))
