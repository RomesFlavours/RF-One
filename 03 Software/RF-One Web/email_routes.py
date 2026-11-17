"""RF-One Email API and Administration / Email Control."""
from datetime import date, datetime, time, timezone, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import secrets

from flask import abort, flash, jsonify, request, render_template, session, redirect, url_for
from sqlalchemy import select, func, or_
from rfone_data_store import display_format
from rfone_data_store import models as m
from rfone_data_store import email_service as e
from rfone_data_store import rfone_web_session as identity


STATUS = {
    'QUEUED': ('Waiting', 'neutral', 'Waiting for its first attempt.'),
    'RETRY': ('Retry scheduled', 'warn', 'A temporary issue occurred. Another attempt is scheduled.'),
    'SENDING': ('Sending', 'neutral', 'The sending service is processing this message.'),
    'ACCEPTED': ('Accepted by Aruba', 'ok', 'Aruba accepted the message. Recipient delivery is not confirmed.'),
    'FAILED': ('Failed', 'bad', 'Sending stopped. Review the issue before authorizing another attempt.'),
    'UNCERTAIN': ('Outcome uncertain', 'warn', 'Check the outcome with Aruba before requesting another message.'),
    'CANCELLED': ('Cancelled', 'neutral', 'This request was cancelled before sending.'),
}
STATUS_GROUPS = {'pending': ('QUEUED', 'RETRY', 'SENDING'), 'attention': ('FAILED', 'UNCERTAIN')}


def register_email_routes(app, *, SessionFactory, load_current_account, require_csrf, get_timezone=lambda: None):
    def list_context():
        candidate = request.values.get('back', '')
        try:
            parsed = urlsplit(candidate)
        except ValueError:
            return url_for('email_control')
        if not parsed.scheme and not parsed.netloc and parsed.path == url_for('email_control'):
            return candidate
        return url_for('email_control')

    def detail_context():
        return dict(status_info=STATUS, page_zone=display_format.zone_label(get_timezone()))

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
            page_zone = display_format.zone_label(get_timezone())
            query = select(e.EmailRequest)
            search = request.args.get('q', request.args.get('recipient', '')).strip()
            domain = request.args.get('domain', '')
            status = request.args.get('status', '')
            if search:
                query = query.where(or_(e.EmailRequest.recipient.contains(search, autoescape=True),
                                        e.EmailRequest.subject.contains(search, autoescape=True)))
            if domain:
                query = query.where(e.EmailRequest.domain == domain)
            if status:
                query = query.where(e.EmailRequest.status.in_(STATUS_GROUPS.get(status, (status,))))
            try:
                offset = max(0, int(request.args.get('offset', 0)))
                for key in ('start', 'end'):
                    raw = request.args.get(key)
                    if raw:
                        day = date.fromisoformat(raw)
                        if key == 'end':
                            day += timedelta(days=1)
                        boundary = datetime.combine(day, time.min, tzinfo=ZoneInfo(page_zone)).astimezone(timezone.utc)
                        query = query.where(e.EmailRequest.created_at >= boundary if key == 'start' else
                                            e.EmailRequest.created_at < boundary)
            except (ValueError, OverflowError):
                abort(400)
            total = db.scalar(select(func.count()).select_from(query.subquery()))
            offset = min(offset, max(0, ((total - 1) // 25) * 25))
            rows = list(db.scalars(query.order_by(e.EmailRequest.created_at.desc(), e.EmailRequest.id).limit(25).offset(offset)))
            counts = dict(db.execute(select(e.EmailRequest.status, func.count()).group_by(e.EmailRequest.status)).all())
            domains = list(db.scalars(select(e.EmailRequest.domain).distinct().order_by(e.EmailRequest.domain)))
            worker = db.get(e.EmailWorkerState, 1)
            live = bool(worker and worker.heartbeat and
                worker.heartbeat.replace(tzinfo=timezone.utc) > e.now() - timedelta(seconds=15))
            busy = bool(worker and worker.owner and worker.lease_until.replace(tzinfo=timezone.utc) > e.now())
            args = {key: request.args.get(key, '') for key in ('q', 'recipient', 'domain', 'status', 'start', 'end')}
            def page_link(position):
                return url_for('email_control', **{k: v for k, v in args.items() if v}, offset=position)
            return render_template('email_control.html', rows=rows, counts=counts, worker=worker,
                live=live or busy, offset=offset, total=total, domains=domains, search=search,
                status_info=STATUS, status_groups=STATUS_GROUPS, page_zone=page_zone,
                all_count=sum(counts.values()), pending_count=sum(counts.get(k, 0) for k in STATUS_GROUPS['pending']),
                attention_count=sum(counts.get(k, 0) for k in STATUS_GROUPS['attention']),
                previous_url=page_link(max(0, offset - 25)), next_url=page_link(offset + 25))

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
                flash('Another sending attempt has been authorized.' if request.form.get('action') == 'resend' else
                      'The pending email has been cancelled.', 'info')
                return redirect(url_for('email_detail', domain=domain, request_id=request_id, back=list_context()))
            attempts = list(db.scalars(select(e.EmailAttempt).where(e.EmailAttempt.request_id == row.id).order_by(e.EmailAttempt.number)))
            audit = list(db.scalars(select(e.EmailAudit).where(e.EmailAudit.request_id == row.id).order_by(e.EmailAudit.id)))
            ids = {item.actor_account_id for item in audit}
            accounts = list(db.scalars(select(m.RFOneAccount).where(m.RFOneAccount.id.in_(ids)))) if ids else []
            actors = {a.id: display_format.employee_short_name(a.display_name or a.username) for a in accounts}
            activity = [dict(title=STATUS.get(a.outcome, (a.outcome,))[0],
                             meta=f'Attempt {a.number}', when=a.finished_at or a.started_at) for a in attempts]
            activity += [dict(title='Another attempt authorized' if item.action == 'resend' else 'Email cancelled',
                              meta=actors.get(item.actor_account_id, 'RF-One administrator'),
                              when=item.created_at) for item in audit]
            activity.append(dict(title='Email requested', meta='', when=row.created_at))
            activity.sort(key=lambda item: item['when'].replace(tzinfo=timezone.utc), reverse=True)
            error_help = {
                'SMTP_550': 'Aruba refused the message. Check the recipient and sending settings before trying again.',
                'SMTP_535': 'Aruba authentication failed. Check the sending service credentials.',
                'SMTP_CONFIGURATION': 'The sending service configuration needs attention before another attempt.',
                'SMTP_CONNECTION': 'The connection to Aruba was interrupted.',
                'WORKER_INTERRUPTED': 'Processing was interrupted before the outcome could be recorded.',
            }.get(row.error)
            return render_template('email_detail.html', row=row, attempts=attempts, audit=audit,
                                   activity=activity, error_help=error_help,
                                   back_url=list_context(), **detail_context())
