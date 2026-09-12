"""Organizational Responsibility + Attention Management — ADMIN /
CONFIGURATION / TEST HARNESS routes (TASK_ATTENTION_ORG_RUNTIME §12).

These screens are NOT an operational interface. They exist solely to let an
administrator configure Positions/Scope/Occupants/Temporary Coverage/Process
Ownership, and to inspect Attention Items and routing results for
configuration/testing/debugging purposes — never as the eventual end-user
"Attention Inbox" (task explicitly forbids building that here; a future
Cognito Human Interaction capability, or any other operational channel, is
the intended consumer of `attention_service.list_attention_for_identity`,
not this admin UI).

Same registration pattern `compensation_routes.py` already establishes:
`require_admin`/`SessionFactory`/`require_csrf` are passed in explicitly by
`app.py`; this module never imports `app.py` itself, so it stays testable
and reusable independent of the shell's own auth wiring.

Business logic lives entirely in `organizational_responsibility_service.py`/
`attention_service.py` (`03 Software/RF-One Data Store`) — every route below
is a thin HTTP adapter over those services, never a second implementation of
scope matching, routing, or lifecycle rules (Core 2.0 Channel Independence).
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store import attention_service as att_svc
from rfone_data_store import organizational_responsibility_service as org_svc
from rfone_data_store.organizational_responsibility_service import ScopeContext

UTC = timezone.utc


def _parse_datetime_local(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def register_organizational_responsibility_routes(app, *, require_admin, SessionFactory, require_csrf):

    # -- Positions ------------------------------------------------------------

    @app.route("/admin/org/positions")
    @require_admin
    def admin_org_positions():
        with SessionFactory() as db:
            positions = list(db.scalars(select(m.Position).order_by(m.Position.name)))
            rows = []
            for p in positions:
                occupant = org_svc.resolve_current_occupant(db, position=p)
                rows.append({"position": p, "occupant": occupant})
            return render_template("admin_org_positions.html", rows=rows)

    @app.route("/admin/org/positions/new", methods=["GET", "POST"])
    @require_admin
    def admin_org_position_new():
        with SessionFactory() as db:
            positions = list(db.scalars(select(m.Position).order_by(m.Position.name)))
            if request.method == "POST":
                require_csrf()
                name = request.form.get("name", "").strip()
                description = request.form.get("description", "").strip() or None
                parent_id = request.form.get("parent_position_id", type=int)
                parent = db.get(m.Position, parent_id) if parent_id else None
                try:
                    org_svc.create_position(db, name=name, description=description, parent=parent)
                    db.commit()
                except (ValueError, org_svc.OrganizationalResponsibilityError) as exc:
                    db.rollback()
                    flash(str(exc), "error")
                    return render_template("admin_org_position_form.html", positions=positions), 400
                flash(f"Position {name!r} created.", "info")
                return redirect(url_for("admin_org_positions"))
            return render_template("admin_org_position_form.html", positions=positions)

    @app.route("/admin/org/positions/<int:position_id>")
    @require_admin
    def admin_org_position_detail(position_id: int):
        with SessionFactory() as db:
            position = db.get(m.Position, position_id)
            if position is None:
                abort(404)
            scopes = list(db.scalars(select(m.PositionScope).where(m.PositionScope.position_id == position_id)))
            assignments = list(
                db.scalars(
                    select(m.PositionAssignment).where(m.PositionAssignment.position_id == position_id)
                    .order_by(m.PositionAssignment.valid_from.desc())
                )
            )
            coverages = list(
                db.scalars(
                    select(m.PositionTemporaryCoverage)
                    .where(m.PositionTemporaryCoverage.covered_position_id == position_id)
                    .order_by(m.PositionTemporaryCoverage.valid_from.desc())
                )
            )
            ownerships = list(
                db.scalars(select(m.ProcessOwnership).where(m.ProcessOwnership.position_id == position_id))
            )
            identities = list(db.scalars(select(m.ActingIdentity).order_by(m.ActingIdentity.display_name)))
            positions = list(db.scalars(select(m.Position).order_by(m.Position.name)))
            current_occupant = org_svc.resolve_current_occupant(db, position=position)
            active_coverage = org_svc.resolve_active_coverage(db, position=position)
            return render_template(
                "admin_org_position_detail.html", position=position, scopes=scopes, assignments=assignments,
                coverages=coverages, ownerships=ownerships, identities=identities, positions=positions,
                current_occupant=current_occupant, active_coverage=active_coverage,
                scope_kinds=m.POSITION_SCOPE_KINDS, scope_id_kinds=m.POSITION_SCOPE_ID_KINDS,
                scope_key_kinds=m.POSITION_SCOPE_KEY_KINDS,
            )

    @app.route("/admin/org/positions/<int:position_id>/scopes/new", methods=["POST"])
    @require_admin
    def admin_org_position_scope_new(position_id: int):
        require_csrf()
        with SessionFactory() as db:
            position = db.get(m.Position, position_id)
            if position is None:
                abort(404)
            scope_type = request.form.get("scope_type", "")
            scope_id = request.form.get("scope_id", type=int)
            scope_key = request.form.get("scope_key", "").strip() or None
            try:
                org_svc.add_position_scope(db, position=position, scope_type=scope_type, scope_id=scope_id, scope_key=scope_key)
                db.commit()
                flash("Scope added.", "info")
            except org_svc.OrganizationalResponsibilityError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(url_for("admin_org_position_detail", position_id=position_id))

    @app.route("/admin/org/positions/<int:position_id>/assignments/new", methods=["POST"])
    @require_admin
    def admin_org_position_assignment_new(position_id: int):
        require_csrf()
        with SessionFactory() as db:
            position = db.get(m.Position, position_id)
            occupant = db.get(m.ActingIdentity, request.form.get("acting_identity_id", type=int))
            if position is None or occupant is None:
                abort(404)
            valid_from = _parse_datetime_local(request.form.get("valid_from")) or datetime.now(UTC)
            valid_to = _parse_datetime_local(request.form.get("valid_to"))
            org_svc.assign_occupant(db, position=position, occupant=occupant, valid_from=valid_from, valid_to=valid_to)
            db.commit()
            flash(f"{occupant.display_name} assigned to {position.name}.", "info")
        return redirect(url_for("admin_org_position_detail", position_id=position_id))

    @app.route("/admin/org/positions/<int:position_id>/coverages/new", methods=["POST"])
    @require_admin
    def admin_org_position_coverage_new(position_id: int):
        require_csrf()
        with SessionFactory() as db:
            covered_position = db.get(m.Position, position_id)
            if covered_position is None:
                abort(404)
            delegate_position_id = request.form.get("delegate_position_id", type=int)
            delegate_identity_id = request.form.get("delegate_acting_identity_id", type=int)
            delegate_position = db.get(m.Position, delegate_position_id) if delegate_position_id else None
            delegate_identity = db.get(m.ActingIdentity, delegate_identity_id) if delegate_identity_id else None
            valid_from = _parse_datetime_local(request.form.get("valid_from")) or datetime.now(UTC)
            valid_to = _parse_datetime_local(request.form.get("valid_to"))
            try:
                org_svc.create_temporary_coverage(
                    db, covered_position=covered_position, delegate_position=delegate_position,
                    delegate_acting_identity=delegate_identity, valid_from=valid_from, valid_to=valid_to,
                )
                db.commit()
                flash("Temporary coverage created.", "info")
            except org_svc.OrganizationalResponsibilityError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(url_for("admin_org_position_detail", position_id=position_id))

    # -- Process Ownership ------------------------------------------------------

    @app.route("/admin/org/process-ownerships")
    @require_admin
    def admin_org_process_ownerships():
        with SessionFactory() as db:
            ownerships = list(db.scalars(select(m.ProcessOwnership)))
            positions = list(db.scalars(select(m.Position).order_by(m.Position.name)))
            return render_template(
                "admin_org_process_ownerships.html", ownerships=ownerships, positions=positions,
                phases=m.PROCESS_PHASES, scope_kinds=m.POSITION_SCOPE_KINDS,
            )

    @app.route("/admin/org/process-ownerships/new", methods=["POST"])
    @require_admin
    def admin_org_process_ownership_new():
        require_csrf()
        with SessionFactory() as db:
            position = db.get(m.Position, request.form.get("position_id", type=int))
            if position is None:
                abort(404)
            domain = request.form.get("domain", "").strip()
            module = request.form.get("module", "").strip() or None
            process_name = request.form.get("process_name", "").strip()
            phase = request.form.get("phase") or None
            scope_type = request.form.get("scope_type") or None
            scope_id = request.form.get("scope_id", type=int)
            scope_key = request.form.get("scope_key", "").strip() or None
            try:
                org_svc.set_process_ownership(
                    db, domain=domain, process_name=process_name, position=position, module=module, phase=phase,
                    scope_type=scope_type, scope_id=scope_id, scope_key=scope_key,
                )
                db.commit()
                flash("Process Ownership created.", "info")
            except org_svc.OrganizationalResponsibilityError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(url_for("admin_org_process_ownerships"))

    # -- Org chart (minimal, administrative) -------------------------------------

    @app.route("/admin/org/chart")
    @require_admin
    def admin_org_chart():
        with SessionFactory() as db:
            positions = list(db.scalars(select(m.Position).order_by(m.Position.name)))
            nodes = []
            for p in positions:
                occupant = org_svc.resolve_current_occupant(db, position=p)
                scopes = list(db.scalars(select(m.PositionScope).where(m.PositionScope.position_id == p.id)))
                ownerships = list(db.scalars(select(m.ProcessOwnership).where(m.ProcessOwnership.position_id == p.id)))
                coverage = org_svc.resolve_active_coverage(db, position=p)
                nodes.append({
                    "position": p, "occupant": occupant, "scopes": scopes, "ownerships": ownerships,
                    "coverage": coverage,
                })
            return render_template("admin_org_chart.html", nodes=nodes)

    # -- Attention Items (inspection only) ---------------------------------------

    @app.route("/admin/org/attention")
    @require_admin
    def admin_org_attention():
        with SessionFactory() as db:
            status_filter = request.args.get("status")
            query = select(m.AttentionItem).order_by(m.AttentionItem.created_at.desc())
            if status_filter:
                query = query.where(m.AttentionItem.status == status_filter)
            items = list(db.scalars(query))
            unresolved = att_svc.list_unresolved_routing(db)
            return render_template(
                "admin_org_attention.html", items=items, unresolved_ids={i.id for i in unresolved},
                statuses=m.ATTENTION_STATUSES, priorities=m.ATTENTION_PRIORITIES, status_filter=status_filter,
            )

    @app.route("/admin/org/attention/<int:item_id>")
    @require_admin
    def admin_org_attention_detail(item_id: int):
        with SessionFactory() as db:
            item = db.get(m.AttentionItem, item_id)
            if item is None:
                abort(404)
            identities = list(db.scalars(select(m.ActingIdentity).order_by(m.ActingIdentity.display_name)))
            return render_template("admin_org_attention_detail.html", item=item, identities=identities)

    @app.route("/admin/org/attention/<int:item_id>/route", methods=["POST"])
    @require_admin
    def admin_org_attention_route(item_id: int):
        require_csrf()
        with SessionFactory() as db:
            item = db.get(m.AttentionItem, item_id)
            if item is None:
                abort(404)
            att_svc.route_attention(db, item=item)
            db.commit()
            flash("Routing re-evaluated.", "info")
        return redirect(url_for("admin_org_attention_detail", item_id=item_id))

    @app.route("/admin/org/attention/<int:item_id>/acknowledge", methods=["POST"])
    @require_admin
    def admin_org_attention_acknowledge(item_id: int):
        require_csrf()
        with SessionFactory() as db:
            item = db.get(m.AttentionItem, item_id)
            actor = db.get(m.ActingIdentity, request.form.get("by_acting_identity_id", type=int))
            if item is None or actor is None:
                abort(404)
            try:
                att_svc.acknowledge_attention(db, item=item, by=actor)
                db.commit()
                flash("Acknowledged.", "info")
            except att_svc.AttentionError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(url_for("admin_org_attention_detail", item_id=item_id))

    @app.route("/admin/org/attention/<int:item_id>/resolve", methods=["POST"])
    @require_admin
    def admin_org_attention_resolve(item_id: int):
        require_csrf()
        with SessionFactory() as db:
            item = db.get(m.AttentionItem, item_id)
            actor = db.get(m.ActingIdentity, request.form.get("by_acting_identity_id", type=int))
            if item is None or actor is None:
                abort(404)
            try:
                att_svc.resolve_attention(db, item=item, by=actor)
                db.commit()
                flash("Resolved.", "info")
            except att_svc.AttentionError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(url_for("admin_org_attention_detail", item_id=item_id))
