"""User-owned mailbox configuration and header-only arrivals in Email Control."""
from datetime import timedelta, timezone

from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from rfone_data_store import incoming_email as incoming, display_format
from rfone_data_store.email_service import EmailWorkerState, now
from rfone_data_store.technical.mailbox_credentials import LocalMailboxVault, CredentialError


def register_incoming_email_routes(app, *, SessionFactory, load_current_account, require_csrf,
                                   get_timezone=lambda: None, vault=None):
    vault = vault or LocalMailboxVault()

    def format_bytes(value):
        if value is None:
            return 'Unknown'
        value = int(value)
        if value < 1024:
            return f'{value} B'
        for unit in ('KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB'):
            value /= 1024
            if value < 1024 or unit == 'EiB':
                return f'{value:.1f} {unit}'

    app.jinja_env.filters['email_bytes'] = format_bytes


    def account(db):
        current = load_current_account(db)
        if current is None or current.status != 'ACTIVE':
            abort(401)
        return current

    def view(current):
        return dict(email_is_admin=bool(current.is_admin), page_zone=display_format.zone_label(get_timezone()))

    def checking(box):
        return bool(box.lease_owner and box.lease_until and box.lease_until.replace(tzinfo=timezone.utc) > now())

    @app.get('/administration/email/mailboxes')
    def email_mailboxes():
        with SessionFactory() as db:
            current = account(db)
            boxes = list(db.scalars(select(incoming.Mailbox).where(
                incoming.Mailbox.owner_account_id == current.id).order_by(incoming.Mailbox.label)))
            counts = dict(db.execute(select(incoming.Arrival.mailbox_id, func.count()).join(incoming.Mailbox,
                incoming.Mailbox.id == incoming.Arrival.mailbox_id).where(
                    incoming.Mailbox.owner_account_id == current.id).group_by(incoming.Arrival.mailbox_id)).all())
            state = db.get(EmailWorkerState, incoming.RECEIVER_STATE_ID)
            live = bool(state and state.heartbeat and (state.heartbeat.replace(tzinfo=timezone.utc) > now() - timedelta(seconds=15)
                or (state.mode == 'CHECKING' and state.lease_until.replace(tzinfo=timezone.utc) > now())))
            return render_template('email_mailboxes.html', boxes=boxes, counts=counts,
                checking=checking, errors=incoming.ERRORS, monitor_live=live, **view(current))

    @app.route('/administration/email/mailboxes/new', methods=['GET', 'POST'])
    @app.route('/administration/email/mailboxes/<mailbox_id>/edit', methods=['GET', 'POST'])
    def email_mailbox_form(mailbox_id=None):
        with SessionFactory() as db:
            current = account(db)
            row = incoming.owned(db, current.id, mailbox_id) if mailbox_id else None
            if mailbox_id and row is None:
                abort(404)
            values = {k: getattr(row, k) for k in ('label', 'address', 'host', 'username', 'folder', 'interval_seconds')} if row else dict(
                label='', address='', host='imaps.aruba.it', username='', folder='INBOX', interval_seconds=60)
            if request.method == 'POST':
                require_csrf()
                values = {key: request.form.get(key, '') for key in values}
                new_ref, old_ref = None, row.credential_ref if row else None
                try:
                    # Validate before writing any secret. Passwords never enter template values or the database.
                    incoming.configuration(**values)
                    password = request.form.get('password', '')
                    if password:
                        new_ref = vault.save(password)
                    incoming.configure(db, owner=current.id, mailbox_id=mailbox_id,
                                       credential_ref=new_ref, **values)
                    db.commit()
                except (ValueError, CredentialError, IntegrityError) as exc:
                    db.rollback()
                    if new_ref:
                        vault.delete(new_ref)
                    if isinstance(exc, IntegrityError):
                        message = 'This mailbox server, username and folder are already configured.'
                    elif isinstance(exc, CredentialError):
                        message = 'The credentials could not be protected. Run the local service as your Windows user.'
                    else:
                        message = str(exc)
                    flash(message, 'error')
                    return render_template('email_mailbox_form.html', row=row, values=values, **view(current)), 400
                if new_ref and old_ref and new_ref != old_ref:
                    vault.delete(old_ref)
                flash('Mailbox settings saved.' if mailbox_id else
                      'Mailbox saved. The monitor will establish its starting point on the first successful check.', 'info')
                return redirect(url_for('email_mailboxes'))
            return render_template('email_mailbox_form.html', row=row, values=values, **view(current))

    @app.post('/administration/email/mailboxes/<mailbox_id>/<action>')
    def email_mailbox_action(mailbox_id, action):
        with SessionFactory() as db:
            current = account(db)
            require_csrf()
            try:
                incoming.control(db, owner=current.id, mailbox_id=mailbox_id, action=action)
                db.commit()
            except LookupError:
                abort(404)
            except ValueError as exc:
                db.rollback()
                flash(str(exc), 'error')
                return redirect(url_for('email_mailboxes'))
            flash({'pause': 'Monitoring paused.', 'resume': 'Monitoring resumed.',
                   'check': 'Check requested. The background monitor will process it.'}[action], 'info')
            return redirect(url_for('email_mailboxes') + '#mailbox-' + mailbox_id)

    @app.get('/administration/email/mailboxes/<mailbox_id>/checks')
    def email_mailbox_checks(mailbox_id):
        with SessionFactory() as db:
            current = account(db)
            row = incoming.owned(db, current.id, mailbox_id)
            if row is None:
                abort(404)
            checks = list(db.scalars(select(incoming.MailboxCheck).where(incoming.MailboxCheck.mailbox_id == row.id)
                .order_by(incoming.MailboxCheck.started_at.desc(), incoming.MailboxCheck.id.desc()).limit(50)))
            audit = list(db.scalars(select(incoming.MailboxAudit).where(incoming.MailboxAudit.mailbox_id == row.id)
                .order_by(incoming.MailboxAudit.id.desc()).limit(50)))
            return render_template('email_mailbox_checks.html', row=row, checks=checks, audit=audit,
                                   errors=incoming.ERRORS, **view(current))

    @app.get('/administration/email/incoming')
    def email_incoming():
        with SessionFactory() as db:
            current = account(db)
            boxes = list(db.scalars(select(incoming.Mailbox).where(
                incoming.Mailbox.owner_account_id == current.id).order_by(incoming.Mailbox.label)))
            mailbox_id = request.args.get('mailbox', '')
            if mailbox_id and mailbox_id not in {b.id for b in boxes}:
                abort(404)
            try:
                offset = max(0, int(request.args.get('offset', 0)))
            except ValueError:
                abort(400)
            search = request.args.get('q', '').strip()
            query = incoming.arrivals(db, current.id, mailbox_id=mailbox_id, search=search, offset=offset)
            rows = list(db.execute(query))
            return render_template('email_incoming.html', boxes=boxes, rows=rows, offset=offset,
                                   search=search, mailbox_id=mailbox_id, **view(current))
