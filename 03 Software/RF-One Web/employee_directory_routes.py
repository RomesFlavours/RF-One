"""Administration > Employee Directory (Anagrafica): person cards, explicit sites and manual POS IDs.

REGISTRY_MULTISITE_001 (Product Owner, 2026-11-22): no Clover staff-list import, no "links to reconcile"
queue, no Sync Now for that flow. The list of a site shows only the people explicitly assigned to it."""
from __future__ import annotations

import os
from types import SimpleNamespace

from flask import abort, flash, redirect, render_template, request, session as browser_session, url_for
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from rfone_data_store import employee_directory as directory
from rfone_data_store import models as m
from rfone_data_store import access_profiles as profiles
from rfone_data_store import rfone_web_session as shared_session


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
                restaurant_id, role_id, area_id = directory.parse_site_role(request.form.get("site_role"))
                if restaurant_id not in _site_ids(db, account):
                    raise ValueError("This site is not available to you.")
                person = directory.create_person(db, display_name=request.form.get("display_name", ""),
                    email=request.form.get("email"), phone=request.form.get("phone"), account_id=account.id,
                    restaurant_id=restaurant_id, role_id=role_id, area_id=area_id)
                if profiles.employee_scope_ids(db,account) is not None:
                    profiles.membership(db,f'employee:{person.id}',profiles.company_context.get(),account.id)
                db.commit()
                return redirect(url_for("employee_directory_detail", employee_id=person.id))
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return redirect(url_for("employee_directory_home"))

    def _site_ids(db, account):
        """Sites the account may see in this Domain (central per-site authorization)."""
        from rfone_data_store import site_selection
        return set(site_selection.account_restaurant_ids(db, account, "EMPLOYEES"))

    @app.route("/administration/employees")
    @gate
    def employee_directory_home():
        with SessionFactory() as db:
            account = load_current_account(db)
            query = request.args.get("q", "").strip()
            scope_ids = profiles.employee_scope_ids(db, account)
            all_sites = directory.sites(db)
            allowed = _site_ids(db, account)
            sites = [site for site in all_sites if site.id in allowed]
            requested = request.args.get("site", "").strip()
            if requested:
                selected = int(requested) if requested.isdecimal() else -1
                browser_session["rfone_directory_site"] = selected
            else:
                selected = browser_session.get("rfone_directory_site")
                if selected is None and sites:
                    selected = sites[0].id
            # No fallback to another site (REGISTRY_MULTISITE_001 §1): unknown or not accessible -> notice.
            site = next((row for row in sites if row.id == selected), None)
            members = directory.site_employee_ids(db, selected) if site is not None else set()
            assigned = set()
            for row in all_sites:
                assigned |= directory.site_employee_ids(db, row.id)
            people_query = directory.canonical_employees().order_by(m.Employee.display_name, m.Employee.id)
            if scope_ids is not None:
                people_query = people_query.where(m.Employee.id.in_(scope_ids))
            rows, unsited, dismissed = [], [], []
            for employee in db.scalars(people_query):
                searchable = " ".join([employee.display_name or "", employee.custom_id or "", employee.email or "",
                                       employee.phone or ""])
                if query and query.casefold() not in searchable.casefold():
                    continue
                if not directory.employee_is_active(employee, []):
                    dismissed.append(employee)
                elif employee.id in members:
                    rows.append(employee)
                elif employee.id not in assigned:
                    unsited.append(employee)
            pos = {}
            if site is not None:
                for employee in rows:
                    link = directory.pos_links(db, employee.id).get(site.id)
                    pos[employee.id] = link.external_employee_id if link else None
            return render_template(
                "employee_directory.html", rows=rows, unsited=unsited, dismissed=dismissed, pos=pos,
                sites=sites, selected=selected, site=site, query=query,
                site_roles=directory.site_role_groups(db, sites),
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
            scope_ids=profiles.employee_scope_ids(db,account)
            if scope_ids is not None and employee_id not in scope_ids:abort(403)
            if request.method == "POST":
                if not shared_session.account_is_domain_admin(db, account, "EMPLOYEES"):
                    abort(403)
                require_csrf()
                anchor = ""
                try:
                    if request.form.get("action") == "assign_site":
                        restaurant_id, role_id, area_id = directory.parse_site_role(request.form.get("site_role"))
                        if restaurant_id not in _site_ids(db, account):
                            raise ValueError("This site is not available to you.")
                        directory.assign_site(db, employee_id=employee_id, restaurant_id=restaurant_id,
                                              role_id=role_id, area_id=area_id, account_id=account.id)
                        anchor = "sites"
                    elif request.form.get("action") == "pos_id":
                        restaurant_id = int(request.form.get("restaurant_id", ""))
                        if restaurant_id not in _site_ids(db, account):
                            raise ValueError("This site is not available to you.")
                        _link, counts = directory.set_pos_id(db, employee_id=employee_id, restaurant_id=restaurant_id,
                                                             pos_id=request.form.get("pos_id"), account_id=account.id)
                        anchor = f"site-{restaurant_id}"
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
                return redirect(url_for("employee_directory_detail", employee_id=employee_id) + (f"#{anchor}" if anchor else ""))
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
            allowed = _site_ids(db, account)
            visible_sites = [site for site in directory.sites(db) if site.id in allowed]
            person_sites = directory.employee_site_ids(db, employee_id)
            pos = directory.pos_links(db, employee_id)
            site_cards = [{"site": site, "pos": pos.get(site.id),
                           "has_pos": directory.site_clover_location(db, site.id) is not None}
                          for site in visible_sites if site.id in person_sites]
            return render_template(
                "employee_directory_detail.html", contexts=contexts, context_options=context_options, employee=employee, links=links, locations=locations,
                site_cards=site_cards,
                site_roles=directory.site_role_groups(db, [site for site in visible_sites if site.id not in person_sites]),
                assignments=assignments, terms=terms, events=events, actors=actors,
                other_employees=[option for option in directory.employee_options(db, include_inactive=True)
                                 if option.id != employee_id],
                can_manage=shared_session.account_is_domain_admin(db, account, "EMPLOYEES"),
                can_org=can_org, can_compensation=can_compensation,
            )

    @app.route("/administration/employees/departments", methods=["GET", "POST"])
    @gate
    def employee_departments():
        """Anagrafica > Reparti e ruoli (REGISTRY_CLOVER_DEPARTMENTS_001): the central Role/Department table of
        Registry. Clover itself is never modified."""
        from rfone_data_store import registry_departments as departments
        with SessionFactory() as db:
            account = load_current_account(db)
            can_manage = shared_session.account_is_domain_admin(db, account, "EMPLOYEES")
            if request.method == "POST":
                require_csrf()
                if not can_manage:
                    abort(403)
                anchor = request.form.get("return_to", "")
                number = lambda name: int(request.form[name]) if request.form.get(name, "").strip() else None
                try:
                    action = request.form.get("action", "")
                    if action == "map":
                        departments.set_role_mapping(
                            db, restaurant_id=number("restaurant_id"), source=request.form.get("source", ""),
                            original_key=request.form.get("original_key", ""),
                            original_label=request.form.get("original_label"),
                            restaurant_role_id=number("restaurant_role_id"), department_id=number("department_id"),
                            account_id=account.id)
                        flash("Corrispondenza salvata. Le assegnazioni restano decise in Registry: non sono state modificate.", "info")
                    elif action == "role":
                        role = departments.save_role(db, role_id=number("role_id"), name=request.form.get("name"),
                                                     department_id=number("department_id"), account_id=account.id)
                        anchor = anchor or f"rf-role-{role.id}"
                        flash("Ruolo salvato.", "info")
                    elif action == "department":
                        row = departments.save_department(
                            db, department_id=number("department_id"), name=request.form.get("name"),
                            code=request.form.get("code"), active=request.form.get("active", "1") == "1",
                            account_id=account.id)
                        anchor = anchor or f"department-{row.id}"
                        flash("Reparto salvato.", "info")
                    else:
                        abort(400)
                    db.commit()
                except (ValueError, IntegrityError) as exc:
                    db.rollback()
                    flash(str(exc) if isinstance(exc, ValueError) else "Il dato è cambiato nel frattempo. Ricarica e riprova.", "error")
                return redirect(url_for("employee_departments") + (f"#{anchor}" if anchor else ""))
            data = departments.overview(db)
            installed = departments.available(db)
            people_by_department = {}
            for item in departments.classification(db):
                if item["department_code"]:
                    people_by_department[item["department_code"]] = people_by_department.get(item["department_code"], 0) + 1
            return render_template(
                "employee_departments.html", data=data, installed=installed, can_manage=can_manage,
                departments=list(db.scalars(select(m.RegistryDepartment).order_by(m.RegistryDepartment.name))) if installed else [],
                rf_roles=[r for r in db.scalars(select(m.RestaurantRole).order_by(m.RestaurantRole.name)) if r.active is not False],
                areas={a.id: a for a in db.scalars(select(m.OperationalArea))},
                accounts={a.id: a.display_name for a in db.scalars(select(m.RFOneAccount))},
                people_by_department=people_by_department)
