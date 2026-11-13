"""Thin local-only web adapter for AI Organization."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import abort, flash, redirect, render_template, request, url_for, jsonify, Response
from sqlalchemy import select
from rfone_data_store import ai_organization as svc
from auth import load_current_account


def register_ai_organization_routes(app, *, SessionFactory, require_domain_access, require_csrf):
    guard = require_domain_access('AI_ORGANIZATION')
    app.jinja_env.filters['from_json'] = json.loads
    app.jinja_env.filters['org_local_time'] = lambda value: datetime.fromisoformat(value).astimezone(ZoneInfo('America/New_York')).strftime('%d/%m/%Y %H:%M %Z')

    @app.route('/ai-organization', methods=['GET', 'POST'])
    @guard
    def ai_organization():
        with SessionFactory() as db:
            account = load_current_account(db)
            if request.method == 'POST':
                require_csrf()
                try:
                    row = svc.create(db, account, int(request.form.get('entity_id', '0')))
                    text = request.form.get('message', '')
                    svc.turn(db, row, account, text, app.config.get('AI_ORGANIZATION_PROVIDER'))
                    db.commit()
                    return redirect(url_for('ai_organization_session', interview_id=row.id))
                except PermissionError:
                    abort(403)
                except ValueError as exc:
                    db.rollback()
                    flash(str(exc), 'error')
            entities = svc.companies(db, account)
            sessions = list(db.scalars(select(svc.Interview).where(svc.Interview.account_id == account.id,
                svc.Interview.entity_id.in_([e.id for e in entities]))))
            return render_template('ai_organization.html', entities=entities, sessions=sessions, row=None)

    @app.route('/ai-organization/<interview_id>', methods=['GET', 'POST'])
    @guard
    def ai_organization_session(interview_id):
        with SessionFactory() as db:
            account = load_current_account(db)
            try:
                row = svc.load(db, account, interview_id)
                if request.method == 'POST':
                    require_csrf()
                    db.connection().exec_driver_sql('UPDATE ai_organization_interviews SET revision=revision WHERE id=?', (row.id,))
                    db.refresh(row)
                    # Prevent old browser tabs from overwriting newer interview turns.
                    if int(request.form.get('revision', '-1')) != row.revision:
                        raise ValueError('La sessione è cambiata: ricarica prima di continuare.')
                    action = request.form.get('action')
                    if action == 'message':
                        svc.turn(db, row, account, request.form.get('message', ''), app.config.get('AI_ORGANIZATION_PROVIDER'))
                    elif action == 'revise':
                        names = request.form.getlist('name')
                        descriptions = request.form.getlist('description')
                        processes = request.form.getlist('process')
                        if not len(names) == len(descriptions) == len(processes):
                            raise ValueError('Correzione incompleta.')
                        svc.revise(row, [dict(name=n, description=d, process=p) for n, d, p in zip(names, descriptions, processes) if n.strip()], account)
                    elif action == 'approve':
                        if request.form.get('baseline') != svc.fingerprint(svc.context(db, row.entity_id)):
                            raise ValueError('Organization è cambiata dal confronto visualizzato: rivedi la pagina.')
                        svc.approve(db, row, account)
                    elif action == 'apply':
                        svc.apply(db, row, account)
                    else:
                        abort(400)
                    db.commit()
                    flash('Operazione salvata.', 'info')
                    return redirect(url_for('ai_organization_session', interview_id=row.id))
                doc = json.loads(row.document)
                current, changes = svc.preview(db, row)
                return render_template('ai_organization.html', row=row, doc=doc, current=current,
                    changes=changes, baseline=svc.fingerprint(current), entity=db.get(svc.m.LegalEntity, row.entity_id),
                    can_apply=account.is_admin or bool((g := db.get(svc.CompanyGrant, (account.id, row.entity_id))) and g.can_apply))
            except PermissionError:
                abort(403)
            except ValueError as exc:
                db.rollback()
                flash(str(exc), 'error')
                if request.method == 'GET':
                    return Response(str(exc), status=409, mimetype='text/plain')
                return redirect(url_for('ai_organization_session', interview_id=interview_id))

    @app.get('/ai-organization/<interview_id>/myrf')
    @guard
    def ai_organization_myrf(interview_id):
        with SessionFactory() as db:
            try:
                row = svc.load(db, load_current_account(db), interview_id)
            except PermissionError:
                abort(403)
            doc = json.loads(row.document)
            return jsonify(dict(contract='organization-approved-context-v1', entity_id=row.entity_id,
                applications=doc['applied'], approved=doc['approved'] if row.applied_revision == row.approved_revision else None,
                notifications_sent=False))
