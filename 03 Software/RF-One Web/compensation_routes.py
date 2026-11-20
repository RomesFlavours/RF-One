"""RF-One Web — Compensation V1 (manual Payroll Handoff).

Replaces the provisional "Compensation — Work in progress" page with the
operational V1 flow the Compensation functional specification and this
task describe: prepare compensation data, review/correct/approve it,
produce a manual export view for a human operator to communicate to the
Payroll Provider, record that communication, record the Provider's
returned result, and reconcile.

Every route below calls straight into the existing `rfone_data_store`
service layer (`payroll_calculation.engine`/`incentives`/`approval`/
`export`/`reconciliation`) — no business logic or validation is duplicated
here (the same services remain usable by a future automated Payroll
Provider connector, unchanged).

Registered from `app.py` via `register_compensation_routes(app, ...)`,
which passes in `require_domain_access`/`SessionFactory`/`load_current_account`/
`require_csrf` explicitly — this module never imports `app.py` itself,
mirroring the `training_integration`-style "pass in collaborators
explicitly" convention already used elsewhere in this application."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import Response, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.payroll_calculation import approval as approval_service
from rfone_data_store.payroll_calculation import compensation as compensation_helpers
from rfone_data_store.payroll_calculation import engine as engine_service
from rfone_data_store.payroll_calculation import export as export_service
from rfone_data_store.payroll_calculation import incentives as incentives_service
from rfone_data_store.payroll_calculation import reconciliation as reconciliation_service

UTC = timezone.utc

_EARNING_LINE_SLOTS = 3  # static form rows — no JS-driven dynamic add/remove in this shell


def _as_naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None or not value.strip():
        return None
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        return None


def _terms_for_run(
    db, run: m.CompensationPreparationRun, *, compensation_basis: str,
) -> list[m.EmployeeCompensationTerm]:
    """Every `EmployeeCompensationTerm` of the given basis for this run's
    Legal Entity that is effective at some point during the run's period."""
    terms = db.scalars(
        select(m.EmployeeCompensationTerm).where(
            m.EmployeeCompensationTerm.legal_entity_id == run.legal_entity_id,
            m.EmployeeCompensationTerm.compensation_basis == compensation_basis,
        )
    ).all()
    period_start, period_end = _as_naive(run.period_start), _as_naive(run.period_end)
    active = []
    for term in terms:
        valid_from = _as_naive(term.valid_from)
        valid_to = _as_naive(term.valid_to) if term.valid_to is not None else period_end
        if valid_from < period_end and valid_to > period_start:
            active.append(term)
    return active


def _eligible_terms_for_run(db, run: m.CompensationPreparationRun) -> list[m.EmployeeCompensationTerm]:
    """Every HOURLY `EmployeeCompensationTerm` for this run's Legal Entity
    that is effective at some point during the run's period — engine.py
    only supports HOURLY terms today. SALARIED terms are a known,
    declared V1 limit — see `_terms_for_run(..., compensation_basis=
    compensation_helpers.SALARIED)`, surfaced separately and explicitly in
    `compensation_run_detail` (task: never a silent gap, never a computed
    zero for an unsupported basis)."""
    return _terms_for_run(db, run, compensation_basis=compensation_helpers.HOURLY)


def register_compensation_routes(
    app, *, require_domain_access, SessionFactory, load_current_account, require_csrf,
):
    gate = require_domain_access("COMPENSATION")

    def _current_account(db):
        account = load_current_account(db)
        if account is None:
            abort(403)
        return account

    def _actor_label(account) -> str:
        return account.display_name or account.username

    # -----------------------------------------------------------------
    # Home — every CompensationPreparationRun, across Legal Entities.
    # -----------------------------------------------------------------

    @app.route("/compensation")
    @gate
    def compensation_home():
        with SessionFactory() as db:
            runs = db.scalars(
                select(m.CompensationPreparationRun).order_by(
                    m.CompensationPreparationRun.period_start.desc(),
                    m.CompensationPreparationRun.id.desc(),
                )
            ).all()
            legal_entities = {le.id: le for le in db.scalars(select(m.LegalEntity)).all()}
            snapshot_by_run = {
                s.compensation_preparation_run_id: s
                for s in db.scalars(select(m.ApprovedCompensationSnapshot)).all()
            }
            return render_template(
                "compensation_home.html", runs=runs, legal_entities=legal_entities,
                snapshot_by_run=snapshot_by_run,
            )

    # -----------------------------------------------------------------
    # Create a CompensationPreparationRun (Legal Entity + period).
    # -----------------------------------------------------------------

    @app.route("/compensation/runs/new", methods=["GET", "POST"])
    @gate
    def compensation_run_new():
        with SessionFactory() as db:
            legal_entities = db.scalars(
                select(m.LegalEntity).where(m.LegalEntity.status == "ACTIVE")
                .order_by(m.LegalEntity.legal_name)
            ).all()

            if request.method == "POST":
                require_csrf()
                legal_entity_id = request.form.get("legal_entity_id", type=int)
                period_start = _parse_date(request.form.get("period_start"))
                period_end = _parse_date(request.form.get("period_end"))

                if not legal_entity_id or period_start is None or period_end is None:
                    flash("Legal Entity, period start and period end are required.", "error")
                    return render_template("compensation_run_new.html", legal_entities=legal_entities), 400
                if period_end < period_start:
                    flash("Period end cannot be before period start.", "error")
                    return render_template("compensation_run_new.html", legal_entities=legal_entities), 400

                run = engine_service.create_calculation_run(
                    db, legal_entity_id=legal_entity_id, period_start=period_start, period_end=period_end,
                )
                db.commit()
                flash("Compensation preparation run created.", "info")
                return redirect(url_for("compensation_run_detail", run_id=run.id))

            return render_template("compensation_run_new.html", legal_entities=legal_entities)

    # -----------------------------------------------------------------
    # Run detail — prepare, review, correct, mark calculated, approve.
    # -----------------------------------------------------------------

    @app.route("/compensation/runs/<int:run_id>")
    @gate
    def compensation_run_detail(run_id: int):
        with SessionFactory() as db:
            run = db.get(m.CompensationPreparationRun, run_id)
            if run is None:
                abort(404)
            legal_entity = db.get(m.LegalEntity, run.legal_entity_id)

            eligible_terms = _eligible_terms_for_run(db, run)
            terms_by_employee: dict[int, list[m.EmployeeCompensationTerm]] = {}
            for term in eligible_terms:
                terms_by_employee.setdefault(term.employee_id, []).append(term)

            calculations = db.scalars(
                select(m.EmployeePayrollCalculation).where(
                    m.EmployeePayrollCalculation.calculation_run_id == run.id
                )
            ).all()
            calc_by_employee = {c.employee_id: c for c in calculations}

            employee_ids = sorted(set(terms_by_employee) | set(calc_by_employee))
            employees = {e.id: e for e in db.scalars(
                select(m.Employee).where(m.Employee.id.in_(employee_ids))
            ).all()} if employee_ids else {}

            incentives_by_employee = {
                employee_id: incentives_service.list_incentive_contributions(
                    db, calculation_run_id=run.id, employee_id=employee_id,
                )
                for employee_id in employee_ids
            }

            employee_rows = [
                {
                    "employee": employees.get(employee_id),
                    "employee_id": employee_id,
                    "terms": terms_by_employee.get(employee_id, []),
                    "calculation": calc_by_employee.get(employee_id),
                    "incentive_contributions": incentives_by_employee.get(employee_id, []),
                    "recognized_incentive_preview": incentives_service.calculate_recognized_incentive(
                        incentives_by_employee.get(employee_id, [])
                    ),
                }
                for employee_id in employee_ids
            ]

            # SALARIED is a declared V1 limit (engine.py only computes
            # HOURLY) — surfaced explicitly and separately here, never
            # silently omitted and never given a computed/zero value (task:
            # "impedisci che un calcolo non supportato produca uno zero o
            # un totale apparentemente valido").
            salaried_terms = _terms_for_run(db, run, compensation_basis=compensation_helpers.SALARIED)
            salaried_employee_ids = sorted({t.employee_id for t in salaried_terms})
            salaried_employees = {
                e.id: e for e in db.scalars(
                    select(m.Employee).where(m.Employee.id.in_(salaried_employee_ids))
                ).all()
            } if salaried_employee_ids else {}
            salaried_terms_by_employee: dict[int, list[m.EmployeeCompensationTerm]] = {}
            for term in salaried_terms:
                salaried_terms_by_employee.setdefault(term.employee_id, []).append(term)
            salaried_rows = [
                {
                    "employee": salaried_employees.get(employee_id),
                    "employee_id": employee_id,
                    "terms": salaried_terms_by_employee[employee_id],
                }
                for employee_id in salaried_employee_ids
            ]

            snapshot = approval_service.get_approved_snapshot_by_run(db, run.id)
            editable = run.status in ("OPEN", "CALCULATED")
            not_yet_calculated_count = sum(1 for row in employee_rows if row["calculation"] is None)

            return render_template(
                "compensation_run_detail.html", run=run, legal_entity=legal_entity,
                employee_rows=employee_rows, snapshot=snapshot, editable=editable,
                earning_line_slots=range(_EARNING_LINE_SLOTS), salaried_rows=salaried_rows,
                not_yet_calculated_count=not_yet_calculated_count,
            )

    @app.route("/compensation/runs/<int:run_id>/employees/<int:employee_id>/calculate", methods=["POST"])
    @gate
    def compensation_calculate_employee(run_id: int, employee_id: int):
        require_csrf()
        with SessionFactory() as db:
            run = db.get(m.CompensationPreparationRun, run_id)
            if run is None:
                abort(404)

            earning_lines: list[engine_service.EarningLineInput] = []
            for slot in range(_EARNING_LINE_SLOTS):
                term_id = request.form.get(f"term_{slot}", type=int)
                hours = _parse_decimal(request.form.get(f"hours_{slot}"))
                work_date_raw = request.form.get(f"work_date_{slot}")
                work_date = _parse_date(work_date_raw).date() if work_date_raw else None
                if term_id and hours is not None:
                    earning_lines.append(
                        engine_service.EarningLineInput(
                            compensation_term_id=term_id, hours=hours, work_date=work_date,
                        )
                    )

            tips_amount = _parse_decimal(request.form.get("tips_amount")) or Decimal("0")
            bonus_amount = _parse_decimal(request.form.get("bonus_amount")) or Decimal("0")
            tip_credit_makeup_amount = _parse_decimal(request.form.get("tip_credit_makeup_amount"))

            if not earning_lines:
                flash("At least one earning line (compensation term + hours) is required.", "error")
                return redirect(url_for("compensation_run_detail", run_id=run_id))

            try:
                engine_service.calculate_employee_payroll(
                    db, run, employee_id=employee_id, earning_lines=earning_lines,
                    tips_amount=tips_amount, bonus_amount=bonus_amount,
                    tip_credit_makeup_amount=tip_credit_makeup_amount,
                )
                db.commit()
            except (engine_service.InvalidCompensationTermError, engine_service.CalculationRunNotEditableError, ValueError) as exc:
                db.rollback()
                flash(str(exc), "error")
                return redirect(url_for("compensation_run_detail", run_id=run_id))

            flash("Compensation calculated for this Employee.", "info")
            return redirect(url_for("compensation_run_detail", run_id=run_id))

    @app.route("/compensation/runs/<int:run_id>/employees/<int:employee_id>/incentives", methods=["POST"])
    @gate
    def compensation_add_incentive(run_id: int, employee_id: int):
        require_csrf()
        with SessionFactory() as db:
            account = _current_account(db)
            label = request.form.get("label", "").strip()
            amount = _parse_decimal(request.form.get("amount"))
            source_note = request.form.get("source_note", "").strip() or None

            if amount is None:
                flash("An Incentive Contribution amount is required (positive or negative).", "error")
                return redirect(url_for("compensation_run_detail", run_id=run_id))

            try:
                incentives_service.add_incentive_contribution(
                    db, calculation_run_id=run_id, employee_id=employee_id, label=label,
                    amount=amount, created_by=_actor_label(account), source_note=source_note,
                )
                db.commit()
            except (incentives_service.IncentiveContributionRunNotEditableError, ValueError) as exc:
                db.rollback()
                flash(str(exc), "error")
                return redirect(url_for("compensation_run_detail", run_id=run_id))

            flash("Incentive Contribution added. Recalculate this Employee to apply it.", "info")
            return redirect(url_for("compensation_run_detail", run_id=run_id))

    @app.route("/compensation/runs/<int:run_id>/incentives/<int:contribution_id>/delete", methods=["POST"])
    @gate
    def compensation_delete_incentive(run_id: int, contribution_id: int):
        require_csrf()
        with SessionFactory() as db:
            try:
                incentives_service.delete_incentive_contribution(db, contribution_id=contribution_id)
                db.commit()
            except incentives_service.IncentiveContributionRunNotEditableError as exc:
                db.rollback()
                flash(str(exc), "error")
                return redirect(url_for("compensation_run_detail", run_id=run_id))

            flash("Incentive Contribution removed. Recalculate this Employee to apply it.", "info")
            return redirect(url_for("compensation_run_detail", run_id=run_id))

    @app.route("/compensation/runs/<int:run_id>/mark-calculated", methods=["POST"])
    @gate
    def compensation_mark_calculated(run_id: int):
        require_csrf()
        with SessionFactory() as db:
            run = db.get(m.CompensationPreparationRun, run_id)
            if run is None:
                abort(404)
            if run.status != "OPEN":
                flash(f"Run is not OPEN (status={run.status}).", "error")
                return redirect(url_for("compensation_run_detail", run_id=run_id))

            has_results = db.scalars(
                select(m.EmployeePayrollCalculation.id).where(
                    m.EmployeePayrollCalculation.calculation_run_id == run.id
                )
            ).first()
            if not has_results:
                flash("Calculate at least one Employee before marking this run CALCULATED.", "error")
                return redirect(url_for("compensation_run_detail", run_id=run_id))

            run.status = "CALCULATED"
            db.commit()
            flash("Run marked CALCULATED — ready for review and approval.", "info")
            return redirect(url_for("compensation_run_detail", run_id=run_id))

    @app.route("/compensation/runs/<int:run_id>/approve", methods=["POST"])
    @gate
    def compensation_approve_run(run_id: int):
        require_csrf()
        with SessionFactory() as db:
            account = _current_account(db)
            try:
                snapshot = approval_service.approve_compensation_preparation(
                    db, calculation_run_id=run_id, approved_by=_actor_label(account),
                )
                db.commit()
            except (approval_service.CompensationPreparationNotFoundError, approval_service.CompensationPreparationNotReadyError) as exc:
                db.rollback()
                flash(str(exc), "error")
                return redirect(url_for("compensation_run_detail", run_id=run_id))

            flash("Compensation approved — an immutable Approved Compensation Snapshot was created.", "info")
            return redirect(url_for("compensation_snapshot_detail", snapshot_id=snapshot.id))

    # -----------------------------------------------------------------
    # Approved Snapshot — manual export view, communication confirmation,
    # provider-result recording, reconciliation.
    # -----------------------------------------------------------------

    @app.route("/compensation/snapshots/<int:snapshot_id>")
    @gate
    def compensation_snapshot_detail(snapshot_id: int):
        with SessionFactory() as db:
            snapshot = approval_service.get_approved_snapshot(db, snapshot_id)
            if snapshot is None:
                abort(404)
            run = db.get(m.CompensationPreparationRun, snapshot.compensation_preparation_run_id)
            legal_entity = db.get(m.LegalEntity, snapshot.legal_entity_id)

            rows = export_service.build_export_rows(db, snapshot_id=snapshot_id)
            confirmations = export_service.get_export_confirmations(db, snapshot_id=snapshot_id)
            reconciliations = reconciliation_service.list_reconciliations_for_snapshot(
                db, snapshot_id=snapshot_id,
            )
            restaurants = db.scalars(
                select(m.Restaurant).where(m.Restaurant.legal_entity_id == snapshot.legal_entity_id)
                .order_by(m.Restaurant.name)
            ).all()
            source_systems = db.scalars(select(m.SourceSystem).order_by(m.SourceSystem.name)).all()

            return render_template(
                "compensation_snapshot_detail.html", snapshot=snapshot, run=run,
                legal_entity=legal_entity, rows=rows, confirmations=confirmations,
                reconciliations=reconciliations, restaurants=restaurants, source_systems=source_systems,
            )

    @app.route("/compensation/snapshots/<int:snapshot_id>/export.csv")
    @gate
    def compensation_snapshot_export_csv(snapshot_id: int):
        with SessionFactory() as db:
            try:
                rows = export_service.build_export_rows(db, snapshot_id=snapshot_id)
            except export_service.SnapshotNotFoundError:
                abort(404)

            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow([
                "Employee", "Provider Employee Key", "Provider Mapping Status", "Legal Entity",
                "Period Start", "Period End", "Regular Hours", "Regular Pay", "Tips",
                "Recognized Incentive", "Tip Credit Make-Up", "Bonus", "Gross Pay",
            ])
            for row in rows:
                writer.writerow([
                    row.employee_display_name,
                    row.provider_external_employee_key or "",
                    row.provider_mapping_status,
                    row.legal_entity_name,
                    row.period_start.date().isoformat(),
                    row.period_end.date().isoformat(),
                    row.regular_hours,
                    row.regular_pay,
                    row.tips_amount,
                    row.incentive_recognized_amount,
                    row.tip_credit_makeup_amount if row.tip_credit_makeup_amount is not None else "TO COMPLETE",
                    row.bonus_amount,
                    row.gross_pay,
                ])

            return Response(
                buffer.getvalue(), mimetype="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=compensation_snapshot_{snapshot_id}.csv"
                },
            )

    @app.route("/compensation/snapshots/<int:snapshot_id>/confirm-communication", methods=["POST"])
    @gate
    def compensation_confirm_communication(snapshot_id: int):
        require_csrf()
        with SessionFactory() as db:
            account = _current_account(db)
            communicated_at = _parse_date(request.form.get("communicated_at")) or datetime.now(UTC)
            reference = request.form.get("reference", "").strip() or None
            note = request.form.get("note", "").strip() or None

            try:
                export_service.confirm_manual_communication(
                    db, snapshot_id=snapshot_id, communicated_by=_actor_label(account),
                    communicated_at=communicated_at, reference=reference, note=note,
                )
                db.commit()
            except (export_service.SnapshotNotFoundError, export_service.SnapshotNotApprovedError, ValueError) as exc:
                db.rollback()
                flash(str(exc), "error")
                return redirect(url_for("compensation_snapshot_detail", snapshot_id=snapshot_id))

            flash(
                "Communication to the Payroll Provider recorded. This does not mean payroll was "
                "processed or paid.", "info",
            )
            return redirect(url_for("compensation_snapshot_detail", snapshot_id=snapshot_id))

    @app.route("/compensation/snapshots/<int:snapshot_id>/reconciliation/new", methods=["POST"])
    @gate
    def compensation_record_provider_result(snapshot_id: int):
        require_csrf()
        with SessionFactory() as db:
            account = _current_account(db)
            snapshot = approval_service.get_approved_snapshot(db, snapshot_id)
            if snapshot is None:
                abort(404)

            restaurant_id = request.form.get("restaurant_id", type=int)
            source_system_id = request.form.get("source_system_id", type=int)
            period_start = _parse_date(request.form.get("period_start")) or snapshot.period_start
            period_end = _parse_date(request.form.get("period_end")) or snapshot.period_end
            pay_date = _parse_date(request.form.get("pay_date"))
            run_type = request.form.get("run_type", "REGULAR")
            provider_reference = request.form.get("provider_reference", "").strip() or None

            if not restaurant_id or not source_system_id or pay_date is None:
                flash("Restaurant, source system and pay date are required.", "error")
                return redirect(url_for("compensation_snapshot_detail", snapshot_id=snapshot_id))

            employee_results: list[reconciliation_service.ManualEmployeeResult] = []
            for result in snapshot.employee_results:
                entries: list[reconciliation_service.ManualEarningEntry] = []
                regular_pay = _parse_decimal(request.form.get(f"regular_pay_{result.employee_id}"))
                tips = _parse_decimal(request.form.get(f"tips_{result.employee_id}"))
                incentive = _parse_decimal(request.form.get(f"incentive_{result.employee_id}"))
                other_label = request.form.get(f"other_label_{result.employee_id}", "").strip()
                other_amount = _parse_decimal(request.form.get(f"other_amount_{result.employee_id}"))

                if regular_pay is not None:
                    entries.append(
                        reconciliation_service.ManualEarningEntry("REGULAR", "Regular", regular_pay)
                    )
                if tips is not None:
                    entries.append(
                        reconciliation_service.ManualEarningEntry("TIPS", "Tips", tips)
                    )
                if incentive is not None:
                    entries.append(
                        reconciliation_service.ManualEarningEntry("BONUS", "Bonus/Incentive", incentive)
                    )
                if other_label and other_amount is not None:
                    entries.append(
                        reconciliation_service.ManualEarningEntry(
                            other_label.upper().replace(" ", "_"), other_label, other_amount,
                        )
                    )
                if entries:
                    employee_results.append(
                        reconciliation_service.ManualEmployeeResult(
                            employee_id=result.employee_id, entries=entries,
                        )
                    )

            if not employee_results:
                flash("Enter at least one reported value for at least one Employee.", "error")
                return redirect(url_for("compensation_snapshot_detail", snapshot_id=snapshot_id))

            try:
                payroll_run = reconciliation_service.record_manual_provider_result(
                    db, source_system_id=source_system_id, restaurant_id=restaurant_id,
                    period_start=period_start, period_end=period_end, pay_date=pay_date,
                    run_type=run_type, employee_results=employee_results,
                    created_by=_actor_label(account), provider_reference=provider_reference,
                )
                recon = reconciliation_service.reconcile(
                    db, snapshot_id=snapshot_id, payroll_run_id=payroll_run.id,
                    created_by=_actor_label(account),
                )
                db.commit()
            except (reconciliation_service.LegalEntityMismatchError, ValueError) as exc:
                db.rollback()
                flash(str(exc), "error")
                return redirect(url_for("compensation_snapshot_detail", snapshot_id=snapshot_id))

            flash("Payroll Provider result recorded and reconciled against the approved data.", "info")
            return redirect(url_for("compensation_reconciliation_detail", reconciliation_id=recon.id))

    @app.route("/compensation/reconciliations/<int:reconciliation_id>")
    @gate
    def compensation_reconciliation_detail(reconciliation_id: int):
        with SessionFactory() as db:
            recon = reconciliation_service.get_reconciliation(db, reconciliation_id)
            if recon is None:
                abort(404)
            snapshot = db.get(m.ApprovedCompensationSnapshot, recon.snapshot_id)
            payroll_run = db.get(m.PayrollRun, recon.payroll_run_id)
            employees = {
                e.id: e for e in db.scalars(
                    select(m.Employee).where(
                        m.Employee.id.in_({line.employee_id for line in recon.lines})
                    )
                ).all()
            } if recon.lines else {}

            return render_template(
                "compensation_reconciliation_detail.html", recon=recon, snapshot=snapshot,
                payroll_run=payroll_run, employees=employees,
            )

    @app.route(
        "/compensation/reconciliations/<int:reconciliation_id>/lines/<int:line_id>/annotate",
        methods=["POST"],
    )
    @gate
    def compensation_annotate_reconciliation_line(reconciliation_id: int, line_id: int):
        require_csrf()
        with SessionFactory() as db:
            account = _current_account(db)
            note = request.form.get("note", "").strip() or None
            resolution_status = request.form.get("resolution_status", "").strip() or None

            try:
                reconciliation_service.annotate_reconciliation_line(
                    db, line_id=line_id, note=note, resolution_status=resolution_status,
                    resolved_by=_actor_label(account) if resolution_status else None,
                )
                db.commit()
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return redirect(url_for("compensation_reconciliation_detail", reconciliation_id=reconciliation_id))

            flash("Reconciliation line updated.", "info")
            return redirect(url_for("compensation_reconciliation_detail", reconciliation_id=reconciliation_id))
