"""Two trainer entry routes, one recipient activation page and existing RF-One identity."""
import secrets
from flask import abort, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash
from rfone_data_store import models as m, people_registry as people, student_registry as registry
from rfone_data_store import rfone_account_service as accounts
from rfone_data_store.training import enrollment as enroll, workspace as ws
from rfone_data_store.technical import account_email
import training_integration as integration
from training_account_routes import public_base

INVALID = 'Invito non valido, scaduto o già utilizzato. Chiedi un nuovo invito all’istruttore.'


def protected(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


def complete(db, invitation, form):
    issuer = integration.check_training_authorization(db, db.get(m.RFOneAccount, invitation.created_by_id))
    if not issuer.training_account or issuer.training_account.role != 'trainer':
        raise ValueError('L’invito non è più autorizzato. Chiedi all’istruttore di verificarlo.')
    first, last, phone = (form.get(k, '').strip() for k in ('first_name', 'last_name', 'phone'))
    name = f'{first} {last}'
    if not first or not last or len(name) > 255 or len(phone) > 64 or (phone and len(enroll.phone_key(phone)) < 5):
        raise ValueError('Inserisci nome, cognome e un telefono valido (se presente).')
    people.lock_identity_evidence(db, invitation.email, name, enroll.phone_key(phone))
    if invitation.selection_id:
        actor = db.get(m.RFOneAccount, invitation.created_by_id)
        confirmed = {r['id']: r for r in enroll.confirmed_candidates(db, actor)}
        if invitation.selection_id not in confirmed or confirmed[invitation.selection_id]['person_id'] != invitation.person_id:
            raise ValueError('La conferma in Selezione non è più disponibile. Chiedi all’istruttore di verificare l’invito.')
    account = enroll.account_for(db, invitation)
    # Resolve again under the same identity locks: invitations never freeze permission
    # or allow a later-created identity to be duplicated.
    matches = enroll.identity_matches(db, name, invitation.email, phone)
    allowed = set()
    if invitation.person_id: allowed.add(f'person:{invitation.person_id}')
    if account: allowed.add(f'account:{account.id}')
    if any(r['key'] not in allowed for r in matches):
        raise ValueError('I dati corrispondono a un’anagrafica da verificare. Chiedi all’istruttore di confermare l’identità e creare un nuovo invito.')
    if account:
        if account.status != 'ACTIVE' or account.email != invitation.email:
            raise ValueError('Account non disponibile per questo invito. Chiedi la verifica all’istruttore.')
        if not check_password_hash(account.password_hash, form.get('current_password', '')):
            invitation.failed_attempts += 1
            return None, 'Password RF-One non valida. Dopo cinque tentativi occorre un nuovo invito.'
        password = secrets.token_urlsafe(32)  # existing credentials are never replaced
        username = account.username
    else:
        password = form.get('password', '')
        if len(password) < 8 or len(password) > 1024 or password != form.get('password_confirm', ''):
            raise ValueError('Scegli e conferma una password da 8 a 1024 caratteri.')
        username = integration.generate_username(db, first, last)
    confirmation = f'person:{invitation.person_id}' if invitation.person_id else f'account:{account.id}' if account else None
    if invitation.person_id:
        person = db.scalar(select(m.CandidatePerson).where(m.CandidatePerson.id == invitation.person_id).with_for_update())
        if not person: raise ValueError('Anagrafica non disponibile. Chiedi all’istruttore.')
        # A selected person remains that exact identity when correcting their name.
        person.full_name = name; person.normalized_name = ' '.join(name.casefold().split())
        db.flush()
    rf, training = integration.create_student_via_rf_one(db, username=username, display_name=name,
        password=password, email=invitation.email, confirmation=confirmation)
    profile = ws.profile(db, training.id)
    if profile.archived_at:
        raise ValueError('Studente in archivio. Il ripristino deve essere effettuato dall’istruttore.')
    person_link = db.get(registry.TrainingPersonLink, training.id)
    person = db.get(m.CandidatePerson, person_link.person_id)
    if not person.primary_email: person.primary_email = invitation.email
    if phone:
        person.primary_phone = phone; person.primary_phone_normalized = enroll.phone_key(phone)
    profile.phone = phone
    # Link possession proves only the invitation's immutable target email.
    if not rf.email_verified_at: accounts.confirm_account_email(db, rf, invitation.email)
    if account is None: profile.must_change_password = False
    invitation.person_id = person.id; invitation.account_id = rf.id; invitation.consumed_at = enroll.now()
    db.flush()
    return rf, None


def install(app, *, SessionFactory, auth, trainer):
    @app.route('/training/manage/enrollment', methods=['GET', 'POST'])
    @trainer
    def tw_enrollment():
        error = link = None; matches = []; draft = request.form
        with SessionFactory() as db:
            actor = auth.load_current_account(db)
            confirmed = enroll.confirmed_candidates(db, actor)
            if request.method == 'POST':
                auth.require_csrf()
                try:
                    mode = request.form.get('mode')
                    if mode not in ('selection', 'direct'): abort(400)
                    selection_id = int(request.form.get('selection_id', '')) if mode == 'selection' else None
                    invitation, token = enroll.issue(db, actor=actor, email=request.form.get('email', ''),
                        name=request.form.get('name', ''), phone=request.form.get('phone', ''), selection_id=selection_id,
                        confirmation=request.form.get('confirmation'))
                    link = public_base() + url_for('tw_enrollment_link', token=token)
                    email = invitation.email
                    db.commit()
                except (ValueError, IntegrityError) as exc:
                    db.rollback(); error = str(exc) if isinstance(exc, ValueError) else 'Invito aggiornato da un’altra sessione. Ricarica e riprova.'
                    if isinstance(exc, registry.ConfirmationRequired): matches = exc.candidates
                else:
                    if current_app.config.get('TRAINING_ENROLLMENT_LOCAL'):
                        flash('Invito pronto. Copia il collegamento personale: funziona su questo computer.', 'info')
                    else:
                        try:
                            account_email.send_email(to_address=email, subject='RF-One Training: completa la tua attivazione',
                                text_body=f'Completa i tuoi dati e attiva Training: {link}\nIl collegamento è personale, vale 48 ore e funziona una volta sola.\n')
                            flash('Invito inviato.', 'info')
                        except account_email.EmailSendError:
                            flash('Invito creato ma email non consegnata. Puoi copiare il collegamento oppure creare un nuovo invito tra un minuto.', 'error')
            return protected(app.make_response((render_template('training_workspace/enrollment.html',
                active_tab='students', help_section='training_enrollment', error=error, draft=draft,
                confirmed=confirmed, matches=matches, invitation_url=link), 400 if error else 200)))

    @app.get('/training/activate/<token>')
    def tw_enrollment_link(token):
        auth.log_out()
        # Never keep the personal bearer link in subsequent requests or referrers.
        session['tw_enrollment_token'] = token if len(token) == 43 else ''
        return protected(redirect(url_for('tw_enrollment_activation')))

    @app.route('/training/activate', methods=['GET', 'POST'])
    def tw_enrollment_activation():
        error = None; invitation = None; existing = False
        with SessionFactory() as db:
            invitation = enroll.lookup(db, session.get('tw_enrollment_token'), lock=request.method == 'POST')
            if invitation:
                account = enroll.account_for(db, invitation); existing = account is not None
                if request.method == 'POST':
                    auth.require_csrf()
                    try:
                        account, error = complete(db, invitation, request.form)
                        db.commit()
                    except (ValueError, IntegrityError) as exc:
                        db.rollback(); error = str(exc) if isinstance(exc, ValueError) else 'I dati sono cambiati. Chiedi all’istruttore di verificare l’anagrafica.'
                    else:
                        if not error:
                            auth.log_in(account.id, account.session_version)
                            session.pop('tw_enrollment_token', None)
                            session['tw_student_session'] = True
                            flash('Attivazione completata. Benvenuto in Training.', 'info')
                            return protected(redirect(url_for('training.home')))
                data = dict(email=invitation.email, name=invitation.name, phone=invitation.phone)
            else:
                error = INVALID; data = None
        return protected(app.make_response((render_template('training_workspace/enrollment_activation.html',
            active_tab='activation', help_section='training_enrollment_activation', error=error,
            invitation=data, existing_account=existing, draft=request.form), 400 if error else 200)))
