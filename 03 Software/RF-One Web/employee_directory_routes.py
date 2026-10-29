"""Administration > Employee Directory; existing RF-One access and Clover jobs."""
from __future__ import annotations

import os
from types import SimpleNamespace

from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from rfone_data_store import employee_directory as directory
from rfone_data_store import models as m
from rfone_data_store import rfone_web_session as shared_session
from rfone_data_store.technical.connectors.clover import acquisition_jobs as jobs
from rfone_data_store.technical.connectors.clover.acquisition import ImportAlreadyRunningError


def _employee_groups(rows, locations):
    """Presentation only: an absent source roster never changes RF-One status."""
    by_location = {}
    dismissed = []
    for row in rows:
        employee, links = row["employee"], row["links"]
        if not directory.employee_is_active(employee, links):
            dismissed.append(row)
            continue
        site_ids = row.get("site_ids") or directory.employee_location_ids(employee, links)
        for location_id in site_ids or {None}:
            site_links = [l for l in links if l.location_id == location_id]
            site_link = next((l for l in site_links if l.state == "PRESENT"), site_links[0] if site_links else None)
            by_location.setdefault(location_id, []).append({**row, "site_link": site_link})
    groups = [{"location": locations.get(location_id, SimpleNamespace(id=None, name="Senza sede", timezone=None)), "rows": members} for location_id, members in by_location.items()]
    groups.sort(key=lambda group: (group["location"].name.casefold(), group["location"].id or 0))
    return groups, dismissed


def register_employee_directory_routes(app, *, require_domain_access, SessionFactory,
                                       load_current_account, require_csrf, get_launcher=lambda: None):
    gate = require_domain_access("EMPLOYEES")

    def _context_permissions(db, account):
        administrator = bool(account and (account.is_admin or account.is_owner))
        return {"RFONE_ACCOUNT": administrator, "ACTING_IDENTITY": administrator,
                "TRAINING": shared_session.account_is_domain_admin(db, account, "TRAINING"),
                "CANDIDATE": shared_session.account_is_domain_admin(db, account, "SELECTION"),
                "PROJECT_RESPONSIBLE": shared_session.account_is_domain_admin(db, account, "PROJECTS")}

    def _context_view(db, person_id, permissions):
        records, choices = [], []
        for kind, (model, field, label_field) in directory.CONTEXTS.items():
            if not permissions.get(kind):
                continue
            links = list(db.scalars(select(m.EmployeeContextLink).where(
                getattr(m.EmployeeContextLink, field).is_not(None))))
            by_target = {getattr(link, field): link for link in links}
            for target in db.scalars(select(model).order_by(model.id)):
                if kind == "ACTING_IDENTITY" and target.kind != "HUMAN_USER":
                    continue
                label = f"{getattr(target, label_field) or 'Nome da completare'} · #{target.id}"
                if kind == "PROJECT_RESPONSIBLE":
                    project = db.get(m.Project, target.project_id)
                    label = f"{project.name} · {label}"
                existing = by_target.get(target.id)
                if existing and existing.employee_id == person_id:
                    records.append({"id": existing.id, "kind": kind, "kind_label": directory.CONTEXT_LABELS[kind], "label": label})
                elif existing is None:
                    choices.append({"kind": kind, "kind_label": directory.CONTEXT_LABELS[kind], "id": target.id, "label": label})
        return records, choices

    @app.route("/administration/employees/new", methods=["POST"])
    @gate
    def employee_directory_create():
        require_csrf()
        with SessionFactory() as db:
            account = load_current_account(db)
            if not shared_session.account_is_domain_admin(db, account, "EMPLOYEES"):
                abort(403)
            try:
                person = directory.create_person(db, display_name=request.form.get("display_name", ""),
                    email=request.form.get("email"), phone=request.form.get("phone"), account_id=account.id)
                db.commit()
                return redirect(url_for("employee_directory_detail", employee_id=person.id))
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return redirect(url_for("employee_directory_home"))

    def _sites(db):
        locations = list(db.scalars(select(m.Location).join(
            m.SourceSystem, m.SourceSystem.id == m.Location.source_system_id
        ).where(m.SourceSystem.code == "CLOVER").order_by(m.Location.id)))
        sites = []
        md_id = os.environ.get("CLOVER_MD_MERCHANT_ID", "").strip()
        for location in locations:
            # Connection configuration belongs to the worker. The web app only
            # needs the non-secret configured marker for MD, not the token.
            md = location.source_location_id == md_id if md_id else "dora" in location.name.casefold()
            configured = bool(location.source_location_id) and (not md or bool(md_id and (
                os.environ.get("CLOVER_MD_API_TOKEN") or os.environ.get("RFONE_CLOVER_MD_CONFIGURED") == "1")))
            last_sync = db.scalar(select(func.max(m.IngestionRun.finished_at)).where(
                m.IngestionRun.location_id == location.id,
                m.IngestionRun.source_system_id == location.source_system_id,
                m.IngestionRun.resource_type.is_(None),
                m.IngestionRun.status == "COMPLETE",
            ))
            sites.append({"location": location, "configured": configured, "last_sync": last_sync})
        return sites

    @app.route("/administration/employees")
    @gate
    def employee_directory_home():
        with SessionFactory() as db:
            account = load_current_account(db)
            query = request.args.get("q", "").strip()
            employees = list(db.scalars(directory.canonical_employees().order_by(m.Employee.display_name, m.Employee.id)))
            all_links = list(db.scalars(select(m.EmployeeCloverLink).order_by(m.EmployeeCloverLink.id)))
            locations = {loc.id: loc for loc in db.scalars(select(m.Location))}
            active_options = {option.id: option for option in directory.employee_options(db)}
            rows = []
            for employee in employees:
                links = [l for l in all_links if l.employee_id == employee.id]
                searchable = [employee.display_name or "", employee.custom_id or "", employee.email or "", employee.phone or ""]
                searchable.extend(str((l.snapshot or {}).get("email") or "") for l in links)
                if query and query.casefold() not in " ".join(searchable).casefold():
                    continue
                conflicts = directory.source_conflicts(links)
                rows.append({"employee": employee, "links": links, "conflicts": conflicts,
                             "site_ids": active_options[employee.id].location_ids if employee.id in active_options else (),
                             "reviewed": directory.is_reviewed(db, employee.id, links),
                             "absence_link_ids": directory.source_absence_link_ids(links)})
            pending = [{"link": l, "candidates": directory.candidates(db, l.snapshot or {})}
                       for l in all_links if directory.pending_requires_review(db, l)]
            sites = _sites(db)
            active_groups, dismissed = _employee_groups(rows, locations)
            return render_template(
                "employee_directory.html", active_groups=active_groups, dismissed=dismissed,
                pending=pending, locations=locations,
                employees=directory.employee_options(db, include_inactive=True), sites=sites, query=query,
                md_configured=any(s["location"].source_location_id == os.environ.get("CLOVER_MD_MERCHANT_ID", "").strip()
                                  and s["configured"] for s in sites),
                can_sync=shared_session.account_may_enter_domain(db, account, "CLOVER_ACQUISITION"),
                can_manage=shared_session.account_is_domain_admin(db, account, "EMPLOYEES"),
            )

    @app.route("/administration/employees/<int:employee_id>", methods=["GET", "POST"])
    @gate
    def employee_directory_detail(employee_id):
        with SessionFactory() as db:
            canonical_id = directory.resolve_employee_id(db, employee_id)
            if canonical_id != employee_id:
                return redirect(url_for("employee_directory_detail", employee_id=canonical_id))
            employee = db.scalar(select(m.Employee).where(m.Employee.id == employee_id).with_for_update())
            if employee is None:
                abort(404)
            links = list(db.scalars(select(m.EmployeeCloverLink).where(
                m.EmployeeCloverLink.employee_id == employee_id).order_by(m.EmployeeCloverLink.id)))
            account = load_current_account(db)
            if request.method == "POST":
                if not shared_session.account_is_domain_admin(db, account, "EMPLOYEES"):
                    abort(403)
                require_csrf()
                try:
                    if request.form.get("action") == "review":
                        # Recheck the exact snapshots rendered to prevent a stale
                        # page acknowledging source changes the user never saw.
                        if request.form.get("fingerprint") != directory.review_fingerprint(links):
                            raise ValueError("Source data changed. Review the current page before confirming.")
                        directory.review(db, employee_id, links, account.id)
                    elif request.form.get("action") == "management":
                        active_text = request.form.get("active", "")
                        if active_text not in ("", "true", "false"):
                            raise ValueError("Invalid internal active state.")
                        directory.update_management(
                            db, employee, display_name=request.form.get("display_name", "").strip(),
                            custom_id=request.form.get("custom_id", "").strip(),
                            email=request.form.get("email"), phone=request.form.get("phone"),
                            active={"": None, "true": True, "false": False}[active_text], account_id=account.id,
                        )
                    elif request.form.get("action") in ("context_link", "context_unlink"):
                        permissions = _context_permissions(db, account)
                        if request.form.get("confirm_identity") != "yes":
                            raise ValueError("Confirm explicitly that this context belongs to the person.")
                        if request.form["action"] == "context_link":
                            kind, raw_target = request.form.get("context_target", "").split(":", 1)
                            if not permissions.get(kind):
                                abort(403)
                            directory.link_context(db, employee_id=employee_id, kind=kind,
                                target_id=int(raw_target), account_id=account.id)
                        else:
                            context_link = db.get(m.EmployeeContextLink, int(request.form.get("context_link_id", "")))
                            if context_link is None or context_link.employee_id != employee_id:
                                abort(404)
                            kind = next(kind for kind, (_, field, _) in directory.CONTEXTS.items()
                                        if getattr(context_link, field) is not None)
                            if not permissions.get(kind):
                                abort(403)
                            directory.unlink_context(db, employee_id=employee_id, link_id=context_link.id, account_id=account.id)
                    elif request.form.get("action") == "consolidate":
                        if request.form.get("confirm_identity") != "yes":
                            raise ValueError("Confirm explicitly that both records are the same person.")
                        target_id = int(request.form.get("target_employee_id", ""))
                        directory.consolidate(db, from_employee_id=employee_id,
                                              into_employee_id=target_id, account_id=account.id)
                        db.commit()
                        flash("Identity consolidated; work history and Clover links preserved. Target management values retained.", "info")
                        return redirect(url_for("employee_directory_detail", employee_id=target_id))
                    else:
                        raise ValueError("Unknown employee action.")
                    db.commit()
                    flash("Employee record saved.", "info")
                except (ValueError, IntegrityError) as exc:
                    db.rollback()
                    flash(str(exc) if isinstance(exc, ValueError) else "The record changed concurrently. Reload and retry.", "error")
                return redirect(url_for("employee_directory_detail", employee_id=employee_id))
            can_org = shared_session.account_may_use_domain_item(db, account, "ORGANIZATION", "chart")
            can_compensation = shared_session.account_may_enter_domain(db, account, "COMPENSATION")
            assignments = list(db.execute(select(m.EmployeeAssignment, m.RestaurantRole.name, m.OperationalArea.name)
                .join(m.RestaurantRole, m.RestaurantRole.id == m.EmployeeAssignment.restaurant_role_id)
                .join(m.OperationalArea, m.OperationalArea.id == m.EmployeeAssignment.operational_area_id)
                .where(m.EmployeeAssignment.employee_id == employee_id)
                .order_by(m.EmployeeAssignment.valid_from.desc()))) if can_org else []
            terms = list(db.scalars(select(m.EmployeeCompensationTerm).where(
                m.EmployeeCompensationTerm.employee_id == employee_id).order_by(m.EmployeeCompensationTerm.valid_from.desc()))) if can_compensation else []
            events = list(db.scalars(select(m.EmployeeDirectoryEvent).where(
                or_(m.EmployeeDirectoryEvent.employee_id == employee_id,
                    m.EmployeeDirectoryEvent.link_id.in_([l.id for l in links]))
                ).order_by(m.EmployeeDirectoryEvent.id.desc()).limit(50)))
            locations = {loc.id: loc for loc in db.scalars(select(m.Location))}
            actors = {a.id: shared_session.account_display_name(a) for a in db.scalars(select(m.RFOneAccount).where(
                m.RFOneAccount.id.in_({e.account_id for e in events if e.account_id is not None})))}
            contexts, context_options = _context_view(db, employee_id, _context_permissions(db, account))
            return render_template(
                "employee_directory_detail.html", contexts=contexts, context_options=context_options, employee=employee, links=links, locations=locations,
                conflicts=directory.source_conflicts(links), reviewed=directory.is_reviewed(db, employee_id, links),
                fingerprint=directory.review_fingerprint(links), assignments=assignments, terms=terms, events=events,
                actors=actors, absence_link_ids=directory.source_absence_link_ids(links),
                has_missing=bool(directory.source_absence_link_ids(links)),
                other_employees=[option for option in directory.employee_options(db, include_inactive=True)
                                 if option.id != employee_id],
                can_manage=shared_session.account_is_domain_admin(db, account, "EMPLOYEES"),
                can_org=can_org, can_compensation=can_compensation,
            )

    @app.route("/administration/employees/links/<int:link_id>/confirm", methods=["POST"])
    @gate
    def employee_directory_link(link_id):
        require_csrf()
        with SessionFactory() as db:
            account = load_current_account(db)
            if not shared_session.account_is_domain_admin(db, account, "EMPLOYEES"):
                abort(403)
            try:
                raw_id = request.form.get("employee_id", "")
                employee = directory.attach_link(
                    db, link_id=link_id, employee_id=int(raw_id) if raw_id else None,
                    create_new=request.form.get("create_new") == "yes", account_id=account.id,
                )
                db.commit()
                flash("Clover identity linked. Run Sync Now to recover any pending work records.", "info")
                return redirect(url_for("employee_directory_home", q=request.form.get("q", "")))
            except (ValueError, IntegrityError) as exc:
                db.rollback()
                flash(str(exc) if isinstance(exc, ValueError) else "The record changed concurrently. Reload and retry.", "error")
                return redirect(url_for("employee_directory_home"))

    @app.route("/administration/employees/sync-now", methods=["POST"])
    @gate
    @require_domain_access("CLOVER_ACQUISITION")
    def employee_directory_sync():
        require_csrf()
        with SessionFactory() as db:
            account = load_current_account(db)
            try:
                location_id = int(request.form.get("location_id", ""))
                site = next((s for s in _sites(db) if s["location"].id == location_id), None)
                if site is None or not site["configured"]:
                    raise ValueError("This site's Clover connection is not configured.")
                run = jobs.request_sync_now(db, location_id=location_id, launcher=get_launcher(),
                                            requested_by_account_id=account.id)
                db.commit()
                flash(f"Synchronization requested (run {run.id}). Refresh this page to see the outcome.", "info")
            except (ValueError, ImportAlreadyRunningError, jobs.JobLaunchError, jobs.NoSyncStartingPointError,
                    jobs.NotACloverLocationError) as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(url_for("employee_directory_home"))
