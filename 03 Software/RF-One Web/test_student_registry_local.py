"""Rollback-only canonical PostgreSQL integration tests; SMTP is always intercepted.

Covers the trainer onboarding flow: Registry/STUDENT, generated username and
initial password, personal activation link (credentials + mandatory new
password), MyRF/Training access, collisions, identity reuse, link misuse and
password recovery.
"""
import os
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from sqlalchemy import select, func
from sqlalchemy.orm import sessionmaker

LINK = re.compile(r'(https?://[^\s/]+)/training/activation/([A-Za-z0-9_-]+)')


def letters(n=6):
    return ''.join(secrets.choice(string.ascii_lowercase) for _ in range(n))


def mail_fields(message):
    body = message['text_body']
    username = re.search(r'Username: (\S+)', body)[1]
    password = re.search(r'Initial password: (\S+)', body)
    link = LINK.search(body)
    return username, (password[1] if password else None), link


def csrf(client, path='/training/activation'):
    import auth
    client.get(path)
    with client.session_transaction() as session:
        return session[auth.SESSION_CSRF_KEY]


def run(engine):
    import training_local
    from rfone_data_store import models as m, student_registry as registry, people_registry as people
    from rfone_data_store import rfone_account_service as accounts, rfone_recovery_service as recovery
    from rfone_data_store.training import workspace as ws
    from rfone_data_store.bank_reconciliation.configuration import cardholder_candidates
    from rfone_data_store.technical import account_email
    import training_integration as ti
    marker = 'Zq' + letters()          # unique first name, letters only (emails are stored lowercase)
    connection = engine.connect(); transaction = connection.begin()
    factory = sessionmaker(bind=connection, join_transaction_mode='create_savepoint', expire_on_commit=False)
    sent = []
    def capture(**kwargs): sent.append(kwargs)
    passed = []
    try:
        app = training_local.create_app(factory=factory, automatic_operator=False)
        import app as shell, auth
        shell.SessionFactory = factory; auth.SessionFactory = factory
        import sys, db as web_db
        web_db.SessionFactory = factory
        for name in ('_training_internal_routes', '_training_internal_auth', '_training_internal_db'):
            if name in sys.modules: sys.modules[name].SessionFactory = factory
        app.config.update(TESTING=True)
        client = app.test_client()
        with factory() as db:
            operator = db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username == 'rfone'))
        with client.session_transaction() as session:
            session[auth.SESSION_ACCOUNT_KEY] = operator.id; session[auth.SESSION_VERSION_KEY] = operator.session_version
            session[auth.SESSION_CSRF_KEY] = 'test'

        # Pure username rule, including short surnames, accents and spaces.
        assert ti.proposed_username('Mario', 'Rossi') == 'MarioRos'
        assert ti.proposed_username('mario', 'LI') == 'MarioLi'
        assert ti.proposed_username('José', "D'Angelo") == 'JoseDan'
        assert ti.proposed_username('Anna Maria', 'De Luca') == 'AnnamariaDel'
        pw = ti.generate_initial_password()
        assert len(pw) >= 12 and any(c.isupper() for c in pw) and any(c.islower() for c in pw) and any(c.isdigit() for c in pw)
        passed.append('username rule (MarioRos, short/accented/compound) and random initial password')

        # 1. Trainer creates the student: name, surname, email only.
        form = dict(action='save', first_name=marker, last_name='Rossi', email=marker + '@example.invalid',
                    phone='123', csrf_token='test')
        with patch.object(account_email, 'send_email', side_effect=capture):
            response = client.post('/training/manage/students', data=form)
        assert response.status_code == 302, response.get_data(as_text=True)
        expected = marker.capitalize() + 'Ros'
        page = client.get(response.location).get_data(as_text=True)
        assert f'Nome utente assegnato: {expected}' in page
        assert len(sent) == 1 and sent[0]["to_address"] == form["email"].lower()
        username, initial, link = mail_fields(sent[0])
        assert username == expected and initial and link and 'Code:' not in sent[0]['text_body']
        assert link[1] == 'http://localhost'  # local request origin, never production
        assert initial not in link[0] and username not in link[0]
        token = link[2]
        with factory() as db:
            account = accounts.get_account_by_username(db, username); aid = account.id
            assert account.username == expected.lower() and not account.email_verified_at
            assert accounts.verify_login(db, expected.upper(), initial).account  # case-insensitive login
            tid = ti.get_link_for_rfone_account(db, aid).training_account_id
            person = people.person_for_account(db, aid); pid = person.id
            assert db.get(registry.PersonQualification, (pid, 'STUDENT'))
            assert db.get(registry.TrainingPersonLink, tid).person_id == pid
            assert not db.scalar(select(people.PersonEmployeeLink.employee_id).where(people.PersonEmployeeLink.person_id == pid))
            grants = accounts.list_domain_access_for_account(db, aid)
            assert len(grants) == 1 and grants[0].domain_code == 'TRAINING' and grants[0].role_code == 'student'
            assert db.get(ws.TrainingStudentProfile, tid).must_change_password
            identity = db.get(m.TrainingAccount, tid).acting_identity_id
            assert identity not in registry.operational_identity_ids(db)
            assert not any(r['kind'] == 'ACTING_IDENTITY' and r['id'] == identity for r in cardholder_candidates(db))
            persons_before = db.scalar(select(func.count()).select_from(m.CandidatePerson))
        passed.append('trainer entry -> Registry person + STUDENT, no employee, TRAINING only; generated username and initial password emailed with local link')

        # 2. Username collision: different person, same proposed username.
        form2 = dict(form, last_name='Rossetti', email=marker + '-2@example.invalid')
        with patch.object(account_email, 'send_email', side_effect=capture):
            assert client.post('/training/manage/students', data=form2).status_code == 302
        username2, initial2, link2 = mail_fields(sent[-1])
        assert username2 == expected + '2'
        with factory() as db:
            aid2 = accounts.get_account_by_username(db, username2).id
            assert accounts.verify_login(db, username, initial).account  # first account untouched
        # A legacy Training username also counts as taken.
        with factory() as db:
            from rfone_data_store.training import service
            service.create_account(db, display_name='Legacy fixture', username=(expected + '3').lower(), password='unused', role='student'); db.commit()
            assert ti.generate_username(db, marker, 'Rossini') == expected + '4'
        passed.append('username collisions numbered (…2, …4 past a legacy Training name) without touching existing accounts')

        # 3. Identity match requires confirmation; no duplicate person/account.
        response = client.post('/training/manage/students', data=dict(form, email=marker + '-other@example.invalid'))
        assert response.status_code == 400 and b'name="confirmation"' in response.data
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(m.CandidatePerson)) == persons_before + 1  # only form2
        passed.append('possible Registry match blocks creation until explicit confirmation')

        # Existing verified login with other grants: credentials, username and grants preserved.
        with factory() as db:
            existing = accounts.create_account(db, username=marker.lower() + '-existing', display_name=marker + ' Existing',
                password='Keep-password-123', email=marker + '-existing@example.invalid')
            existing.email_verified_at = datetime.now(timezone.utc)
            old_hash = existing.password_hash
            accounts.set_domain_access(db, account_id=existing.id, domain_code='ORGANIZATION', enabled=True, role_code=None)
            db.commit(); eid = existing.id
        existing_form = dict(form, first_name=marker, last_name='Existing', email=marker + '-existing@example.invalid',
                             confirmation=f'account:{eid}')
        with patch.object(account_email, 'send_email', side_effect=capture):
            response = client.post('/training/manage/students', data=existing_form)
        assert response.status_code == 302
        assert 'credenziali invariate' in client.get(response.location).get_data(as_text=True)
        assert 'Initial password' not in sent[-1]['text_body'] and 'activation/' not in sent[-1]['text_body']
        with factory() as db:
            current = db.get(m.RFOneAccount, eid)
            assert current.password_hash == old_hash and current.username == marker.lower() + '-existing'
            assert {g.domain_code for g in accounts.list_domain_access_for_account(db, eid) if g.enabled} == {'ORGANIZATION', 'TRAINING'}
            assert not db.get(ws.TrainingStudentProfile, ti.get_link_for_rfone_account(db, eid).training_account_id).must_change_password
        passed.append('existing verified identity reused after confirmation: username, password and other grants preserved; no initial password sent')

        # 4. Skipping activation: initial credentials do not open Training or MyRF.
        skip = app.test_client()
        response = skip.post('/training/access', data=dict(username=username2, password=initial2, csrf_token=csrf(skip, '/training/access')))
        assert response.status_code == 400 and 'collegamento personale' in response.get_data(as_text=True)
        response = skip.post('/login', data=dict(username=username2, password=initial2, csrf_token=csrf(skip, '/login')))
        assert response.status_code == 302
        response = skip.get('/')
        assert response.status_code == 302 and response.location.endswith('/training/access')
        assert skip.get('/').status_code == 302 and '/login' in skip.get('/').location  # session ended
        passed.append('initial credentials alone rejected on Training sign-in; shared /login session ended before MyRF')

        # 5. Link misuse: link alone, wrong password, another account's credentials, code page.
        learner = app.test_client()
        response = learner.get(f'/training/activation/{token}')
        assert response.status_code == 302 and response.headers['Referrer-Policy'] == 'no-referrer'
        with learner.session_transaction() as session:
            assert auth.SESSION_ACCOUNT_KEY not in session
        assert learner.get('/').status_code == 302 and '/login' in learner.get('/').location
        token_csrf = csrf(learner)
        def post(c, **data):
            c.get('/training/activation')  # renders the form and its CSRF token, changes nothing
            with c.session_transaction() as session: data['csrf_token'] = session[auth.SESSION_CSRF_KEY]
            return c.post('/training/activation', data=data)
        assert post(learner, step='credentials', username=username, password='Wrong-password-1').status_code == 400
        assert post(learner, step='credentials', username=username2, password=initial2).status_code == 400
        assert post(learner, step='password', password='New-password-123', password_confirm='New-password-123').status_code == 400
        codepage = app.test_client()
        response = codepage.post('/training/account/activate', data=dict(username=username, code=token,
            password='Hijack-password-1', password_confirm='Hijack-password-1', csrf_token=csrf(codepage, '/training/account/activate')))
        assert response.status_code == 400
        with factory() as db:
            assert not db.get(m.RFOneAccount, aid).email_verified_at
        passed.append('link alone, wrong initial password, another account credentials and token-as-code all rejected')

        # 6. Correct credentials -> forced change; still no MyRF access before completion.
        response = post(learner, step='credentials', username=expected.lower(), password=initial)
        assert response.status_code == 302 and response.location.endswith('/training/activation')
        assert 'Scegli la tua password' in learner.get('/training/activation').get_data(as_text=True)
        assert learner.get('/').status_code == 302 and '/login' in learner.get('/').location
        assert learner.get('/training').status_code == 302
        assert 'diversa da quella iniziale' in post(learner, step='password', password=initial, password_confirm=initial).get_data(as_text=True)
        assert post(learner, step='password', password='Personal-pass-123', password_confirm='Different-123').status_code == 400
        response = post(learner, step='password', password='Personal-pass-123', password_confirm='Personal-pass-123')
        assert response.status_code == 302 and response.location in ('/', 'http://localhost/')
        home = learner.get('/')
        assert home.status_code == 200 and 'href="/training' in home.get_data(as_text=True)
        r = learner.get('/training'); assert r.status_code == 200 or (r.status_code in (301, 302, 308) and learner.get(r.location).status_code == 200), (r.status_code, r.location)
        assert learner.get('/training/manage/students').status_code == 403
        with factory() as db:
            account = db.get(m.RFOneAccount, aid)
            assert account.email_verified_at
            assert not db.get(ws.TrainingStudentProfile, tid).must_change_password
            assert not accounts.verify_login(db, username, initial).account
            assert accounts.verify_login(db, username, 'Personal-pass-123').account
            row = db.scalar(select(m.RFOneAccountVerificationCode).where(m.RFOneAccountVerificationCode.account_id == aid)
                .order_by(m.RFOneAccountVerificationCode.id.desc()))
            assert row.consumed_at is not None
            assert [g.domain_code for g in accounts.list_domain_access_for_account(db, aid) if g.enabled] == ['TRAINING']
        passed.append('credentials -> mandatory different password -> email verified, link consumed, initial password invalid, MyRF with only Training')

        # 7. Reuse of the consumed link.
        again = app.test_client(); again.get(f'/training/activation/{token}')
        assert post(again, step='credentials', username=username, password='Personal-pass-123').status_code == 400
        assert post(again, step='credentials', username=username, password=initial).status_code == 400
        passed.append('consumed link cannot be reused')

        # 8. Expired link; resend issues new credentials and invalidates the old ones.
        with factory() as db:
            row = recovery.get_pending_code(db, aid2, recovery.PURPOSE_EMAIL_VERIFICATION)
            row.created_at = row.created_at - timedelta(minutes=5)  # past the 60 s resend cooldown
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1); db.commit()
        expired = app.test_client(); expired.get(f'/training/activation/{link2[2]}')
        assert post(expired, step='credentials', username=username2, password=initial2).status_code == 400
        with factory() as db:
            tid2 = ti.get_link_for_rfone_account(db, aid2).training_account_id
        with patch.object(account_email, 'send_email', side_effect=capture):
            assert client.post('/training/manage/students', data=dict(action='invite', id=tid2, csrf_token='test')).status_code == 302
        username2b, initial2b, link2b = mail_fields(sent[-1])
        assert username2b.lower() == username2.lower() and initial2b != initial2 and link2b[2] != link2[2]
        with factory() as db:
            assert not accounts.verify_login(db, username2, initial2).account
        fresh = app.test_client(); fresh.get(f'/training/activation/{link2[2]}')
        assert post(fresh, step='credentials', username=username2, password=initial2b).status_code == 400  # old link
        fresh.get(f'/training/activation/{link2b[2]}')
        assert post(fresh, step='credentials', username=username2, password=initial2b).status_code == 302
        passed.append('expired link rejected; resend gives new initial password and link, old ones invalid')

        # 9. Forgot password on the one RF-One account.
        rec = app.test_client()
        with patch.object(account_email, 'send_email', side_effect=capture):
            assert rec.post('/training/account/recover', data=dict(username=username, email=form['email'].lower(),
                csrf_token=csrf(rec, '/training/account/recover'))).status_code == 302
        reset_code = re.search(r'Code: (\d{6})', sent[-1]['text_body'])[1]
        assert rec.post('/training/account/reset', data=dict(username=username, code=reset_code, password='Recovered-pass-456',
            password_confirm='Recovered-pass-456', csrf_token=csrf(rec, '/training/account/reset'))).status_code == 302
        with factory() as db:
            assert accounts.verify_login(db, username, 'Recovered-pass-456').account
            assert not accounts.verify_login(db, username, 'Personal-pass-123').account
        passed.append('forgot password works on the single RF-One account')

        # Delivery failure keeps one recoverable Registry identity; resend completes it.
        failed = dict(form, first_name=marker, last_name='Failed', email=marker + '-failed@example.invalid')
        with patch.object(account_email, 'send_email', side_effect=account_email.EmailSendError('test')):
            response = client.post('/training/manage/students', data=failed)
        assert response.status_code == 302 and 'Reinvia invito' in client.get(response.location).get_data(as_text=True)
        with factory() as db:
            failed_account = accounts.get_account_by_username(db, marker.lower() + 'fai')
            assert people.person_for_account(db, failed_account.id)
            ftid = ti.get_link_for_rfone_account(db, failed_account.id).training_account_id
            row = recovery.get_pending_code(db, failed_account.id, recovery.PURPOSE_EMAIL_VERIFICATION)
            row.created_at = row.created_at - timedelta(minutes=5); db.commit()
        with patch.object(account_email, 'send_email', side_effect=capture):
            client.post('/training/manage/students', data=dict(action='invite', id=ftid, csrf_token='test'))
        assert mail_fields(sent[-1])[2] and mail_fields(sent[-1])[1]
        passed.append('delivery failure keeps the identity; Reinvia invito sends fresh credentials and link')

        # Mixed-role archive keeps qualification and other grants.
        with factory() as db:
            account = db.get(m.RFOneAccount, aid)
            accounts.set_domain_access(db, account_id=aid, domain_code='ORGANIZATION', enabled=True, role_code=None)
            version = account.session_version
            ws.archive_student(db, tid, True)
            assert account.status == 'ACTIVE' and account.session_version == version + 1
            assert not ti.check_training_authorization(db, account).training_account
            assert db.get(registry.PersonQualification, (pid, 'STUDENT'))
            ws.archive_student(db, tid, False)
            assert ti.check_training_authorization(db, account).training_account.id == tid
            db.rollback()
        passed.append('archive with other grants blocks only Training and keeps STUDENT qualification')

        # 10. Shared configuration builds the official HTTPS origin.
        import training_account_routes as tar
        previous = os.environ.get('RFONE_PUBLIC_BASE_URL')
        os.environ['RFONE_PUBLIC_BASE_URL'] = 'https://rfone.romesflavours.com'
        try:
            with app.test_request_context('/training/manage/students', base_url='http://127.0.0.1:5098'):
                assert tar.activation_url(tar.public_base(), 'T' * 43) == 'https://rfone.romesflavours.com/training/activation/' + 'T' * 43
        finally:
            if previous is None: os.environ.pop('RFONE_PUBLIC_BASE_URL', None)
            else: os.environ['RFONE_PUBLIC_BASE_URL'] = previous
        with app.test_request_context('/training/manage/students', base_url='http://127.0.0.1:5098'):
            if previous is None: assert tar.public_base() == 'http://127.0.0.1:5098'
        passed.append('shared configuration yields https://rfone.romesflavours.com; local yields the local origin')
        assert all(m_['to_address'].endswith('@example.invalid') for m_ in sent)
        for line in passed: print('PASS:', line)
    finally:
        transaction.rollback(); connection.close()
    with engine.connect() as connection:
        from rfone_data_store import models as m
        assert not connection.scalar(select(m.RFOneAccount.id).where(m.RFOneAccount.username.like(marker.lower() + '%')))
    print(f'PASS: all test data rolled back; {len(sent)} emails intercepted, none sent.')


if __name__ == '__main__':
    import training_local
    engine = training_local.configure()
    try: run(engine)
    finally: engine.dispose()
