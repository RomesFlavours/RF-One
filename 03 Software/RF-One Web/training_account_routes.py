"""Training entry points over the shared RF-One verification/password services."""
import os
from flask import current_app, request, render_template, redirect, url_for, flash
from rfone_data_store import models as m, rfone_account_service as accounts, rfone_recovery_service as recovery
from rfone_data_store.technical import account_email
from rfone_data_store.training import workspace as ws


def public_base():
    """Official HTTPS origin when configured (shared deployments); otherwise the
    origin of this request, so a local email link opens the local server."""
    from rfone_data_store.public_entry import public_base_url
    return (public_base_url() or request.url_root).rstrip('/')


def activation_url(base, token):
    return f'{base}/training/activation/{token}'


def pending_link_activation(db, account):
    """A login created by the Training onboarding that was never activated:
    unverified email, mandatory password replacement, Training-student only."""
    import training_integration as integration
    link = integration.get_link_for_rfone_account(db, account.id)
    profile = db.get(ws.TrainingStudentProfile, link.training_account_id) if link else None
    return bool(profile and profile.must_change_password and not account.email_verified_at
                and account.status == 'ACTIVE' and integration.is_pure_training_student(db, account))


def invite(db, account, initial_password=None, display_username=None):
    """Commit first, then send. New/never-activated student logins receive
    username, initial password and a personal single-use activation link;
    existing logins keep their credentials (verified: access link only;
    unverified: the existing activation-code path)."""
    base = public_base()
    username = display_username or account.username
    if not account.email_verified_at and pending_link_activation(db, account):
        try:
            token = recovery.issue_code(db, account=account, purpose=recovery.PURPOSE_EMAIL_VERIFICATION,
                target_email=account.email, flask_secret_key=current_app.secret_key, request_ip=request.remote_addr,
                code=recovery.generate_link_token(), ttl=recovery.ACTIVATION_LINK_TTL)
        except recovery.RateLimitedError:
            return False
        if initial_password is None:
            # The original is never stored in clear: a resend for an account that
            # was never activated issues a new initial password with the new link.
            initial_password = integration_password()
            accounts.set_password(db, account, initial_password)
        db.commit()
        hours = int(recovery.ACTIVATION_LINK_TTL.total_seconds() // 3600)
        body = (f'RF-One Training\n\n'
                f'Nome utente / Username: {username}\n'
                f'Password iniziale / Initial password: {initial_password}\n\n'
                f'Attiva il tuo account / Activate your account:\n{activation_url(base, token)}\n\n'
                f'Il collegamento vale una sola volta e scade dopo {hours} ore. Richiede anche nome utente e '
                f'password iniziale; poi sceglierai una nuova password personale.\n'
                f'The link works once and expires after {hours} hours. It also requires the username and '
                f'initial password; you will then choose a new personal password.\n')
        try:
            account_email.send_email(to_address=account.email, subject='RF-One Training: attiva il tuo account', text_body=body)
        except account_email.EmailSendError:
            return False
        return True
    code = None
    if not account.email_verified_at:
        try:
            code = recovery.issue_code(db, account=account, purpose=recovery.PURPOSE_EMAIL_VERIFICATION,
                target_email=account.email, flask_secret_key=current_app.secret_key, request_ip=request.remote_addr)
        except recovery.RateLimitedError:
            return False
    db.commit()
    body = f'RF-One Training\nNome utente / Username: {username}\n{base}/training/access\n'
    if code:
        body += f'Attiva e verifica / Activate and verify: {base}/training/account/activate\nCode: {code}\nExpires in 10 minutes.\n'
    body += 'Usa il tuo account RF-One / Use your RF-One account.\n'
    try:
        account_email.send_email(to_address=account.email, subject='RF-One Training invitation', text_body=body)
    except account_email.EmailSendError:
        return False
    return True


def integration_password():
    import training_integration as integration
    return integration.generate_initial_password()


def install(app, *, SessionFactory, auth):
    @app.route('/training/account/<mode>', methods=['GET', 'POST'])
    def tw_account(mode):
        from flask import abort
        if mode not in ('activate', 'recover', 'reset'): abort(404)
        error = None
        if request.method == 'POST':
            auth.require_csrf()
            with SessionFactory() as db:
                account = accounts.get_account_by_username(db, request.form.get('username', ''))
                if mode == 'recover':
                    if account and account.status == 'ACTIVE' and account.email_verified_at and account.email == accounts.normalize_email(request.form.get('email','')):
                        try:
                            code = recovery.issue_code(db, account=account, purpose=recovery.PURPOSE_PASSWORD_RESET,
                                target_email=account.email, flask_secret_key=app.secret_key, request_ip=request.remote_addr)
                            db.commit()
                            account_email.send_email(to_address=account.email, subject='RF-One password recovery',
                                text_body=f'Code: {code}\nExpires in 10 minutes. Use /training/account/reset.\n')
                        except (recovery.RateLimitedError, account_email.EmailSendError):
                            pass
                    flash('Se i dati corrispondono a un account idoneo, riceverai un codice valido per 10 minuti.', 'info')
                    return redirect(url_for('tw_account', mode='reset'))
                purpose = recovery.PURPOSE_PASSWORD_RESET if mode == 'reset' else recovery.PURPOSE_EMAIL_VERIFICATION
                password = request.form.get('password','')
                if len(password) < 8 or password != request.form.get('password_confirm',''):
                    error = 'Inserisci e conferma una password di almeno 8 caratteri.'
                elif not account or account.status != 'ACTIVE' or not recovery.is_numeric_code(request.form.get('code', '')):
                    error = 'Codice non valido o scaduto.'
                else:
                    result = recovery.verify_and_consume_code(db, account_id=account.id, purpose=purpose,
                        submitted_code=request.form.get('code',''), flask_secret_key=app.secret_key)
                    if not result.ok or result.code_row.target_email != account.email:
                        db.commit(); error = 'Codice non valido o scaduto.'
                    else:
                        if mode == 'activate':
                            accounts.confirm_account_email(db, account, result.code_row.target_email)
                        accounts.set_password(db, account, password)
                        recovery.invalidate_pending_codes(db, account.id)
                        from rfone_data_store import models as m
                        from sqlalchemy import select
                        link = db.scalar(select(m.RFOneTrainingIdentityLink).where(m.RFOneTrainingIdentityLink.rfone_account_id==account.id))
                        if link:
                            p=db.get(ws.TrainingStudentProfile,link.training_account_id)
                            if p:p.must_change_password=False
                        db.commit()
                        auth.log_out()
                        flash('Account RF-One pronto. Accedi con la tua password.', 'info')
                        return redirect(url_for('tw_login'))
        return render_template('training_workspace/account.html', mode=mode, error=error,
            help_section='training_account', active_tab='account'), 400 if error else 200

    # Personal activation link. The link alone never signs in: username and
    # initial password are required, then a different personal password.
    # Until completion the learner holds no RF-One session (no MyRF/modules).
    TOKEN_KEY, PENDING_KEY = 'tw_activation_token', 'tw_activation_account'
    INVALID = ('Collegamento non valido, scaduto o già utilizzato, oppure nome utente e password '
               'iniziale non corrispondono. Chiedi all’istruttore di reinviare l’invito.')

    def no_referrer(response):
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/training/activation/<token>')
    def tw_activation_link(token):
        from flask import session
        valid = len(token) >= recovery.LINK_TOKEN_MIN_LENGTH and all(c.isalnum() or c in '-_' for c in token)
        auth.log_out()  # any other session in this browser ends; nothing is signed in
        if valid:
            session[TOKEN_KEY] = token
        return no_referrer(redirect(url_for('tw_activation')))

    def pending_account(db):
        from flask import session
        pending = session.get(PENDING_KEY) or {}
        account = db.get(m.RFOneAccount, pending.get('id')) if pending.get('id') else None
        if account is None or account.session_version != pending.get('version'):
            session.pop(PENDING_KEY, None)
            return None
        return account

    @app.route('/training/activation', methods=['GET', 'POST'])
    def tw_activation():
        from flask import session
        from training_account_routes import pending_link_activation
        from werkzeug.security import check_password_hash
        error, status = None, 200
        token = session.get(TOKEN_KEY)
        with SessionFactory() as db:
            account = pending_account(db) if token else None
            if request.method == 'POST':
                auth.require_csrf()
                step = request.form.get('step')
                if not token:
                    error = INVALID
                elif step == 'credentials':
                    login = accounts.verify_login(db, request.form.get('username', ''), request.form.get('password', ''))
                    candidate = login.account
                    result = None
                    if candidate is not None and pending_link_activation(db, candidate):
                        result = recovery.verify_and_consume_code(db, account_id=candidate.id,
                            purpose=recovery.PURPOSE_EMAIL_VERIFICATION, submitted_code=token,
                            flask_secret_key=app.secret_key, consume=False)
                    db.commit()
                    if result is None or not result.ok or result.code_row.target_email != candidate.email:
                        error, account = INVALID, None
                    else:
                        session[PENDING_KEY] = {'id': candidate.id, 'version': candidate.session_version}
                        return redirect(url_for('tw_activation'))
                elif step == 'password' and account is not None:
                    password = request.form.get('password', '')
                    if len(password) < 8:
                        error = 'La nuova password deve contenere almeno 8 caratteri.'
                    elif password != request.form.get('password_confirm', ''):
                        error = 'Le password non coincidono.'
                    elif check_password_hash(account.password_hash, password):
                        error = 'Scegli una password diversa da quella iniziale.'
                    elif not pending_link_activation(db, account):
                        error, account = INVALID, None
                    else:
                        result = recovery.verify_and_consume_code(db, account_id=account.id,
                            purpose=recovery.PURPOSE_EMAIL_VERIFICATION, submitted_code=token,
                            flask_secret_key=app.secret_key)
                        if not result.ok or result.code_row.target_email != account.email:
                            db.commit(); error, account = INVALID, None
                        else:
                            accounts.confirm_account_email(db, account, result.code_row.target_email)
                            accounts.set_password(db, account, password)  # initial password stops working
                            recovery.invalidate_pending_codes(db, account.id)
                            import training_integration as integration
                            link = integration.get_link_for_rfone_account(db, account.id)
                            ws.profile(db, link.training_account_id).must_change_password = False
                            db.commit()
                            auth.log_in(account.id, account.session_version)
                            session['tw_student_session'] = True
                            flash('Account attivato. Benvenuto in MyRF.', 'info')
                            return no_referrer(redirect(url_for('home')))
                else:
                    error, account = INVALID, None
                if error == INVALID:
                    session.pop(PENDING_KEY, None)
                status = 400 if error else 200
            username = account.username if account is not None else None
        return no_referrer(app.make_response((render_template('training_workspace/activation.html',
            error=error, has_token=bool(token), pending_username=username,
            help_section='training_activation', active_tab='activation'), status)))
