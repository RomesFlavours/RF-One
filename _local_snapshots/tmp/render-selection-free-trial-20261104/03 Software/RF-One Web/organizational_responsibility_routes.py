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
from rfone_data_store import organizational_ai_review_service as ai_svc
from rfone_data_store import organizational_coverage_check_service as coverage_svc
from rfone_data_store import organizational_responsibility_service as org_svc
from rfone_data_store.organizational_responsibility_service import ScopeContext

UTC = timezone.utc


def _scope_display(db, scope) -> str:
    """A human-readable label for one PositionScope/ProcessOwnership/
    OrganizationalFallbackPolicy scope statement — resolves a real name for
    the dimensions that have a canonical table (Restaurant, Legal Entity),
    falls back to the raw id/key otherwise. Never free text the user typed
    (task §5) — always derived from the structured scope_type/scope_id/
    scope_key fields."""
    if scope.scope_type == m.POSITION_SCOPE_GLOBAL:
        return "GLOBAL"
    if scope.scope_type == m.POSITION_SCOPE_RESTAURANT and scope.scope_id:
        restaurant = db.get(m.Restaurant, scope.scope_id)
        return f"Restaurant (Brand): {restaurant.name}" if restaurant else f"RESTAURANT={scope.scope_id} (not found)"
    if scope.scope_type == m.POSITION_SCOPE_OPERATIONAL_UNIT and scope.scope_id:
        location = db.get(m.Location, scope.scope_id)
        return f"Operational Unit (Location): {location.name}" if location else f"OPERATIONAL_UNIT={scope.scope_id} (not found)"
    if scope.scope_type == m.POSITION_SCOPE_LEGAL_ENTITY and scope.scope_id:
        entity = db.get(m.LegalEntity, scope.scope_id)
        return f"Legal Entity: {entity.legal_name}" if entity else f"LEGAL_ENTITY={scope.scope_id} (not found)"
    value = scope.scope_id if scope.scope_id is not None else scope.scope_key
    return f"{scope.scope_type}={value}"


def _parse_datetime_local(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def _post_redirect(default_endpoint: str, **kwargs):
    """Every Position-editor POST handler redirects to `next` when the
    submitting form came from the modal-in-graph editor (task §4/§17: the
    org chart view must not be lost unnecessarily) — the graph page reopens
    the same Position's modal automatically via its own URL hash. Falls
    back to the handler's normal default (the full detail page) otherwise."""
    next_url = request.form.get("next")
    if next_url:
        return redirect(next_url)
    return redirect(url_for(default_endpoint, **kwargs))


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
            backups = org_svc.list_position_backups(db, position=position, include_inactive=True)
            subordinates = list(db.scalars(select(m.Position).where(m.Position.parent_position_id == position_id)))
            identities = list(db.scalars(select(m.ActingIdentity).order_by(m.ActingIdentity.display_name)))
            positions = list(db.scalars(select(m.Position).where(m.Position.id != position_id).order_by(m.Position.name)))
            restaurants = list(db.scalars(select(m.Restaurant).order_by(m.Restaurant.name)))
            legal_entities = list(db.scalars(select(m.LegalEntity).order_by(m.LegalEntity.legal_name)))
            locations = list(db.scalars(select(m.Location).order_by(m.Location.name)))
            current_occupant = org_svc.resolve_current_occupant(db, position=position)
            active_coverage = org_svc.resolve_active_coverage(db, position=position)
            return render_template(
                "admin_org_position_detail.html", position=position, scopes=scopes, assignments=assignments,
                coverages=coverages, backups=backups, subordinates=subordinates, ownerships=ownerships,
                identities=identities, positions=positions, restaurants=restaurants, legal_entities=legal_entities,
                locations=locations, current_occupant=current_occupant, active_coverage=active_coverage,
                scope_kinds=m.POSITION_SCOPE_KINDS, scope_id_kinds=m.POSITION_SCOPE_ID_KINDS,
                scope_key_kinds=m.POSITION_SCOPE_KEY_KINDS, phases=m.PROCESS_PHASES,
                scope_display=lambda s: _scope_display(db, s),
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
        return _post_redirect("admin_org_position_detail", position_id=position_id)

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
        return _post_redirect("admin_org_position_detail", position_id=position_id)

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
        return _post_redirect("admin_org_position_detail", position_id=position_id)

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

    # -- Organizational Chart — SYSTEM / ORGANIZATION CONFIGURATION -------------
    # Interactive, DB-derived graph (task §2/§17). `/admin/org/chart` (the
    # earlier, simpler listing) now redirects here rather than existing as a
    # second, overlapping page for the same concern.

    @app.route("/admin/org/chart")
    @require_admin
    def admin_org_chart():
        return redirect(url_for("admin_organization"))

    @app.route("/admin/organization")
    @require_admin
    def admin_organization():
        with SessionFactory() as db:
            check_result = coverage_svc.run_organizational_coverage_check(db)
            return render_template("admin_organization.html", counts=check_result.counts)

    @app.route("/admin/organization/graph-data.json")
    @require_admin
    def admin_organization_graph_data():
        from flask import jsonify

        with SessionFactory() as db:
            check_result = coverage_svc.run_organizational_coverage_check(db)
            # Per-Position DELIVERY badge (TASK_ORG_RUNTIME_CONSISTENCY_FIXES
            # §4): a Position that owns several Processes can have entries at
            # different delivery statuses — pick the single WORST one to
            # badge the node with, worst-first so a real gap is never masked
            # by another, better-covered Process the same Position also owns.
            # Backup/Fallback coverage is deliberately NOT labelled "gap" —
            # the Attention is actually routable; only genuine GAP is.
            _DELIVERY_BADGE_PRIORITY = (
                coverage_svc.STATUS_GAP, coverage_svc.STATUS_COVERED_VIA_FALLBACK, coverage_svc.STATUS_COVERED_VIA_BACKUP,
            )
            position_delivery_status: dict[int, str] = {}
            for e in check_result.entries:
                if e.owner_position is None or e.status == coverage_svc.STATUS_FULLY_COVERED:
                    continue
                current = position_delivery_status.get(e.owner_position.id)
                if current is None or _DELIVERY_BADGE_PRIORITY.index(e.status) < _DELIVERY_BADGE_PRIORITY.index(current):
                    position_delivery_status[e.owner_position.id] = e.status
            gap_position_ids = {pid for pid, status in position_delivery_status.items() if status == coverage_svc.STATUS_GAP}
            backup_covered_position_ids = {pid for pid, status in position_delivery_status.items() if status == coverage_svc.STATUS_COVERED_VIA_BACKUP}
            fallback_covered_position_ids = {pid for pid, status in position_delivery_status.items() if status == coverage_svc.STATUS_COVERED_VIA_FALLBACK}
            backup_required_gap_ids = {p.id for p in check_result.positions_missing_required_backup}

            positions = list(db.scalars(select(m.Position).order_by(m.Position.name)))
            nodes = []
            for p in positions:
                occupant = org_svc.resolve_current_occupant(db, position=p)
                coverage = org_svc.resolve_active_coverage(db, position=p)
                scopes = list(db.scalars(select(m.PositionScope).where(m.PositionScope.position_id == p.id)))
                backups = org_svc.list_position_backups(db, position=p)
                nodes.append({
                    "id": p.id, "name": p.name, "parent_id": p.parent_position_id, "is_active": p.is_active,
                    "vacant": occupant is None,
                    "occupant_name": occupant.display_name if occupant else None,
                    "scope_summary": ", ".join(_scope_display(db, s) for s in scopes) if scopes else "Global (no scope set)",
                    "backup_summary": ", ".join(b.backup_position.name for b in backups) if backups else None,
                    "coverage_summary": (
                        (coverage.delegate_acting_identity.display_name if coverage.delegate_acting_identity
                         else coverage.delegate_position.name) + (f" until {coverage.valid_to}" if coverage.valid_to else "")
                    ) if coverage else None,
                    "gap_warning": p.id in gap_position_ids,
                    "covered_via_backup": p.id in backup_covered_position_ids,
                    "covered_via_fallback": p.id in fallback_covered_position_ids,
                    "missing_required_backup": p.id in backup_required_gap_ids,
                })
            return jsonify({"positions": nodes, "coverage_counts": check_result.counts})

    @app.route("/admin/organization/positions/<int:position_id>/fragment")
    @require_admin
    def admin_organization_position_fragment(position_id: int):
        """Same data as `admin_org_position_detail`, rendered WITHOUT the
        page chrome — fetched and injected into the graph page's modal so a
        click-to-edit never navigates away from the chart (task §4)."""
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
            backups = org_svc.list_position_backups(db, position=position, include_inactive=True)
            ownerships = list(db.scalars(select(m.ProcessOwnership).where(m.ProcessOwnership.position_id == position_id)))
            subordinates = list(db.scalars(select(m.Position).where(m.Position.parent_position_id == position_id)))
            identities = list(db.scalars(select(m.ActingIdentity).order_by(m.ActingIdentity.display_name)))
            positions = list(db.scalars(select(m.Position).where(m.Position.id != position_id).order_by(m.Position.name)))
            restaurants = list(db.scalars(select(m.Restaurant).order_by(m.Restaurant.name)))
            legal_entities = list(db.scalars(select(m.LegalEntity).order_by(m.LegalEntity.legal_name)))
            locations = list(db.scalars(select(m.Location).order_by(m.Location.name)))
            current_occupant = org_svc.resolve_current_occupant(db, position=position)
            active_coverage = org_svc.resolve_active_coverage(db, position=position)
            return render_template(
                "admin_org_position_editor_fragment.html", position=position, scopes=scopes, assignments=assignments,
                coverages=coverages, backups=backups, ownerships=ownerships, subordinates=subordinates,
                identities=identities, positions=positions, restaurants=restaurants, legal_entities=legal_entities,
                locations=locations, current_occupant=current_occupant, active_coverage=active_coverage,
                scope_kinds=m.POSITION_SCOPE_KINDS, scope_id_kinds=m.POSITION_SCOPE_ID_KINDS,
                scope_key_kinds=m.POSITION_SCOPE_KEY_KINDS, phases=m.PROCESS_PHASES,
                scope_display=lambda s: _scope_display(db, s), in_modal=True,
            )

    # -- Backup Position ----------------------------------------------------------

    @app.route("/admin/org/positions/<int:position_id>/backups/new", methods=["POST"])
    @require_admin
    def admin_org_position_backup_new(position_id: int):
        require_csrf()
        with SessionFactory() as db:
            covered = db.get(m.Position, position_id)
            backup = db.get(m.Position, request.form.get("backup_position_id", type=int))
            if covered is None or backup is None:
                abort(404)
            try:
                org_svc.add_position_backup(db, covered_position=covered, backup_position=backup)
                db.commit()
                flash(f"{backup.name!r} added as Backup Position.", "info")
            except org_svc.OrganizationalResponsibilityError as exc:
                db.rollback()
                flash(str(exc), "error")
        return _post_redirect("admin_org_position_detail", position_id=position_id)

    @app.route("/admin/org/positions/<int:position_id>/backups/<int:backup_id>/deactivate", methods=["POST"])
    @require_admin
    def admin_org_position_backup_deactivate(position_id: int, backup_id: int):
        require_csrf()
        with SessionFactory() as db:
            backup = db.get(m.PositionBackup, backup_id)
            if backup is None or backup.covered_position_id != position_id:
                abort(404)
            org_svc.deactivate_position_backup(db, backup=backup)
            db.commit()
            flash("Backup Position deactivated.", "info")
        return _post_redirect("admin_org_position_detail", position_id=position_id)

    @app.route("/admin/org/positions/<int:position_id>/backup-required", methods=["POST"])
    @require_admin
    def admin_org_position_backup_required_toggle(position_id: int):
        require_csrf()
        with SessionFactory() as db:
            position = db.get(m.Position, position_id)
            if position is None:
                abort(404)
            position.backup_required = request.form.get("backup_required") == "on"
            db.commit()
        return _post_redirect("admin_org_position_detail", position_id=position_id)

    # -- Organizational Fallback Policy -------------------------------------------

    @app.route("/admin/org/fallback-policies")
    @require_admin
    def admin_org_fallback_policies():
        with SessionFactory() as db:
            policies = list(db.scalars(select(m.OrganizationalFallbackPolicy)))
            positions = list(db.scalars(select(m.Position).order_by(m.Position.name)))
            return render_template(
                "admin_org_fallback_policies.html", policies=policies, positions=positions,
                scope_kinds=m.POSITION_SCOPE_KINDS, scope_display=lambda s: _scope_display(db, s),
            )

    @app.route("/admin/org/fallback-policies/new", methods=["POST"])
    @require_admin
    def admin_org_fallback_policy_new():
        require_csrf()
        with SessionFactory() as db:
            position = db.get(m.Position, request.form.get("fallback_position_id", type=int))
            if position is None:
                abort(404)
            scope_type = request.form.get("scope_type") or m.POSITION_SCOPE_GLOBAL
            scope_id = request.form.get("scope_id", type=int)
            scope_key = request.form.get("scope_key", "").strip() or None
            try:
                org_svc.set_organizational_fallback_policy(
                    db, fallback_position=position, scope_type=scope_type, scope_id=scope_id, scope_key=scope_key,
                )
                db.commit()
                flash(f"Organizational Fallback Policy set to {position.name!r}.", "info")
            except org_svc.OrganizationalResponsibilityError as exc:
                db.rollback()
                flash(str(exc), "error")
        return redirect(url_for("admin_org_fallback_policies"))

    @app.route("/admin/org/fallback-policies/<int:policy_id>/deactivate", methods=["POST"])
    @require_admin
    def admin_org_fallback_policy_deactivate(policy_id: int):
        require_csrf()
        with SessionFactory() as db:
            policy = db.get(m.OrganizationalFallbackPolicy, policy_id)
            if policy is None:
                abort(404)
            org_svc.deactivate_organizational_fallback_policy(db, policy=policy)
            db.commit()
            flash("Fallback Policy deactivated.", "info")
        return redirect(url_for("admin_org_fallback_policies"))

    # -- Organizational Coverage Check --------------------------------------------

    @app.route("/admin/org/coverage-check")
    @require_admin
    def admin_org_coverage_check():
        with SessionFactory() as db:
            result = coverage_svc.run_organizational_coverage_check(db)
            return render_template(
                "admin_org_coverage_check.html", result=result, counts=result.counts, coverage_svc=coverage_svc,
            )

    # -- Scope & Ownership Interview — ADMIN / TEST ONLY (task §6-7) -------------
    # Stands in for a future Cognito-led interview: the SAME structured
    # service functions are called on submit (never free-text prose saved
    # as canonical Scope).

    @app.route("/admin/org/positions/<int:position_id>/interview", methods=["GET", "POST"])
    @require_admin
    def admin_org_position_interview(position_id: int):
        with SessionFactory() as db:
            position = db.get(m.Position, position_id)
            if position is None:
                abort(404)
            if request.method == "POST":
                require_csrf()
                restaurant_ids = request.form.getlist("restaurant_ids", type=int)
                for rid in restaurant_ids:
                    org_svc.add_position_scope(db, position=position, scope_type=m.POSITION_SCOPE_RESTAURANT, scope_id=rid)
                domain_answer = request.form.get("domain", "").strip()
                if domain_answer:
                    org_svc.add_position_scope(db, position=position, scope_type=m.POSITION_SCOPE_DOMAIN, scope_key=domain_answer)
                process_answer = request.form.get("process_name", "").strip()
                if process_answer:
                    phase_answer = request.form.get("phase") or None
                    org_svc.set_process_ownership(
                        db, domain=domain_answer or "UNSPECIFIED", process_name=process_answer, position=position,
                        phase=phase_answer,
                    )
                backup_answer = request.form.get("backup_position_id", type=int)
                if backup_answer:
                    backup_position = db.get(m.Position, backup_answer)
                    if backup_position is not None:
                        org_svc.add_position_backup(db, covered_position=position, backup_position=backup_position)
                db.commit()
                flash(
                    "Interview answers saved as structured Scope/Process Ownership/Backup Position — "
                    "no free-text prose was stored as canonical Scope.", "info",
                )
                return _post_redirect("admin_org_position_detail", position_id=position_id)

            restaurants = list(db.scalars(select(m.Restaurant).order_by(m.Restaurant.name)))
            positions = list(db.scalars(select(m.Position).where(m.Position.id != position_id).order_by(m.Position.name)))
            return render_template(
                "admin_org_position_interview.html", position=position, restaurants=restaurants, positions=positions,
                phases=m.PROCESS_PHASES,
            )

    # -- AI Consistency Review — test harness, NOT a real AI call (task §16) ----

    @app.route("/admin/org/ai-review")
    @require_admin
    def admin_org_ai_review():
        with SessionFactory() as db:
            request_payload = ai_svc.build_ai_consistency_review_request(db)
            not_available_message = None
            try:
                ai_svc.run_ai_consistency_review(db)
            except ai_svc.AIConsistencyReviewNotAvailable as exc:
                not_available_message = str(exc)
            return render_template(
                "admin_org_ai_review.html", request_payload=request_payload, not_available_message=not_available_message,
            )

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
            routing_history = att_svc.list_routing_history(db, item=item)
            return render_template(
                "admin_org_attention_detail.html", item=item, identities=identities, routing_history=routing_history,
            )

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
