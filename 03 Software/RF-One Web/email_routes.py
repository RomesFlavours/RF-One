"""RF-One Email API and Administration / Email Control."""
from datetime import datetime, timezone, timedelta
import secrets

from flask import abort, jsonify, request, render_template, session, redirect, url_for
from sqlalchemy import select, func
from rfone_data_store import email_service as e
from rfone_data_store import rfone_web_session as identity


def register_email_routes(app, *, SessionFactory, load_current_account, require_csrf):
    def authorize(db, domain=None, admin=False):
        account = load_current_account(db)
        if account is None or account.status != 'ACTIVE':
            abort(401)
        if admin:
            if not account.is_admin:
                abort(403)
        elif not identity.account_may_enter_domain(db, account, domain):
            abort(403)
        return account

    def csrf():
        if request.is_json:
            expected = session.get(identity.SESSION_CSRF_KEY, '')
            supplied = request.headers.get('X-CSRF-Token', '')
            if not expected or not supplied or not secrets.compare_digest(expected, supplied):
                abort(400)
        else:
            require_csrf()

    def filters():
        values = {k: request.args.get(k) for k in ('recipient', 'status')}
        try:
            for key in ('start', 'end'):
                raw = request.args.get(key)
                values[key] = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc) if raw else None
            values['offset'] = max(0, int(request.args.get('offset', 0)))
        except ValueError:
            abort(400)
        return values

    @app.route('/api/email/<domain>/requests', methods=['GET', 'POST'])
    def email_requests(domain):
        with SessionFactory() as db:
            authorize(db, domain)
            if request.method == 'POST':
                csrf()
                data = request.get_json(silent=True)
                if not isinstance(data, dict):
                    abort(400)
                try:
                    row = e.enqueue(db, domain=domain, **{k: data.get(k) for k in
                        ('recipient', 'subject', 'body', 'event', 'dedup_key')})
                    db.commit()
                except ValueError as exc:
                    return jsonify(error=str(exc)), 400
                return jsonify(e.snapshot(row)), 202
            return jsonify([e.snapshot(row) for row in e.history(db, domain=domain, **filters())])

    @app.get('/api/email/<domain>/requests/<request_id>')
    def email_status(domain, request_id):
        with SessionFactory() as db:
            authorize(db, domain)
            row = e.get(db, domain, request_id)
            if row is None:
                abort(404)
            data = e.snapshot(row)
            data['attempt_history'] = [dict(number=a.number, outcome=a.outcome, error=a.error,
                started_at=a.started_at, finished_at=a.finished_at) for a in db.scalars(
                    select(e.EmailAttempt).where(e.EmailAttempt.request_id == row.id).order_by(e.EmailAttempt.number))]
            return jsonify(data)

    @app.post('/api/email/<domain>/requests/<request_id>/<action>')
    def email_action(domain, request_id, action):
        with SessionFactory() as db:
            account = authorize(db, domain)
            if action == 'resend' and not account.is_admin:
                abort(403)
            csrf()
            if e.get(db, domain, request_id) is None:
                abort(404)
            try:
                e.transition(db, domain=domain, request_id=request_id, action=action, actor_account_id=account.id)
                db.commit()
            except ValueError as exc:
                return jsonify(error=str(exc)), 409
            return jsonify(status='ok')

    @app.get('/administration/email')
    def email_control():
        with SessionFactory() as db:
            authorize(db, admin=True)
            rows = e.history(db, domain=request.args.get('domain'), **filters())
            counts = dict(db.execute(select(e.EmailRequest.status, func.count()).group_by(e.EmailRequest.status)).all())
            worker = db.get(e.EmailWorkerState, 1)
            live = bool(worker and worker.heartbeat and
                worker.heartbeat.replace(tzinfo=timezone.utc) > e.now() - timedelta(seconds=15))
            busy = bool(worker and worker.owner and worker.lease_until.replace(tzinfo=timezone.utc) > e.now())
            return render_template('email_control.html', rows=rows, counts=counts, worker=worker,
                                   live=live or busy, offset=filters()['offset'])

    @app.route('/administration/email/<domain>/<request_id>', methods=['GET', 'POST'])
    def email_detail(domain, request_id):
        with SessionFactory() as db:
            account = authorize(db, admin=True)
            row = e.get(db, domain, request_id)
            if row is None:
                abort(404)
            if request.method == 'POST':
                csrf()
                try:
                    e.transition(db, domain=domain, request_id=request_id,
                                 action=request.form.get('action'), actor_account_id=account.id)
                    db.commit()
                except ValueError:
                    abort(409)
                return redirect(url_for('email_detail', domain=domain, request_id=request_id))
            attempts = list(db.scalars(select(e.EmailAttempt).where(e.EmailAttempt.request_id == row.id).order_by(e.EmailAttempt.number)))
            audit = list(db.scalars(select(e.EmailAudit).where(e.EmailAudit.request_id == row.id).order_by(e.EmailAudit.id)))
            return render_template('email_detail.html', row=row, attempts=attempts, audit=audit)
