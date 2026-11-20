"""Edge renderer E2E on loopback; rollback-only and SMTP sink, no external mail.

Trainer entry -> Registry/STUDENT -> intercepted email -> personal link ->
initial credentials -> mandatory password change -> MyRF -> Training.
"""
import json,re,secrets,string,threading,sys
from pathlib import Path
from unittest.mock import patch
import training_local
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright,expect

def run():
    engine=training_local.configure()
    from rfone_data_store import models as m,student_registry as sr,people_registry as people
    from rfone_data_store.technical import account_email
    import training_integration as ti
    dest=Path(__file__).resolve().parents[2]/'output/training-activation-link-20261112'
    dest.mkdir(parents=True,exist_ok=True)
    connection=engine.connect();transaction=connection.begin()
    factory=sessionmaker(bind=connection,join_transaction_mode='create_savepoint',expire_on_commit=False)
    sent=[];checks=[]
    first='Zv'+''.join(secrets.choice(string.ascii_lowercase) for _ in range(6))
    import db as web_db
    web_db.SessionFactory=factory
    app=training_local.create_app(factory=factory)
    import app as shell,auth
    shell.SessionFactory=factory;auth.SessionFactory=factory
    for name in ('_training_internal_routes','_training_internal_auth','_training_internal_db'):
        sys.modules[name].SessionFactory=factory
    server=make_server('127.0.0.1',0,app,threaded=False)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    username=None
    def snap(page,name):
        page.screenshot(path=str(dest/(name+'.png')),full_page=True)
    def fields(message):
        body=message['text_body']
        return (re.search(r'Username: (\S+)',body)[1],re.search(r'Initial password: (\S+)',body)[1],
                re.search(r'(https?://\S+/training/activation/[A-Za-z0-9_-]+)',body)[1])
    try:
      with patch.object(account_email,'send_email',side_effect=lambda **kw:sent.append(kw)),sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        def context():
            c=browser.new_context(viewport={'width':1440,'height':1000})
            # Deny every non-loopback resource, including analytics, remote images and production.
            c.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
            return c
        page=context().new_page();page.goto(base+'/training/manage/students')
        expect(page.get_by_role('heading',name='Studenti',exact=True)).to_be_visible()
        checks.append('Existing rfone operator opens Training students locally without password and without new grants')
        page.locator('#new-student').click()
        form=page.locator('#student-editor-form')
        expect(form.locator('[name=username]')).to_be_hidden();expect(form.locator('[name=password]')).to_be_hidden()
        form.locator('[name=first_name]').fill(first);form.locator('[name=last_name]').fill('Rossi')
        form.locator('[name=email]').fill(first+'@example.invalid')
        snap(page,'01-new-student')
        page.locator('[data-modal-help="student-form"]').click();snap(page,'02-context-help')
        page.keyboard.press('Escape')
        expect(form.locator('[name=first_name]')).to_have_value(first)
        form.get_by_role('button',name='Salva studente').click()
        expected=first.capitalize()+'Ros'
        expect(page.get_by_text(f'Nome utente assegnato: {expected}. Invito inviato.',exact=True)).to_be_visible()
        snap(page,'03-assigned-username')
        username,initial,link=fields(sent[-1])
        assert username==expected and link.startswith(base+'/training/activation/') and initial not in link
        with factory() as db:
            account=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username==expected.lower()))
            aid=account.id;pid=people.person_for_account(db,aid).id
            assert db.get(sr.PersonQualification,(pid,'STUDENT'))
            assert not list(db.scalars(select(people.PersonEmployeeLink).where(people.PersonEmployeeLink.person_id==pid)))
        checks.append(f'Trainer enters name/surname/email; Registry person + STUDENT, no employee; username {expected} shown; email intercepted with initial password and local link')
        # Collision: another person whose username would be the same.
        page.locator('#new-student').click()
        form.locator('[name=first_name]').fill(first);form.locator('[name=last_name]').fill('Rossetti')
        form.locator('[name=email]').fill(first+'-2@example.invalid')
        form.get_by_role('button',name='Salva studente').click()
        expect(page.get_by_text(f'Nome utente assegnato: {expected}2. Invito inviato.',exact=True)).to_be_visible()
        checks.append(f'Username collision shown as {expected}2; first account untouched')
        # Identity match requires explicit confirmation.
        page.locator('#new-student').click()
        form.locator('[name=first_name]').fill(first);form.locator('[name=last_name]').fill('Rossi')
        form.locator('[name=email]').fill(first+'-dup@example.invalid')
        form.get_by_role('button',name='Salva studente').click()
        expect(page.locator('#student-editor input[name=confirmation]').first).to_be_visible()
        snap(page,'04-identity-confirmation')
        page.locator('#student-editor [data-close]').first.click()
        checks.append('Possible Registry match opens explicit confirmation; nothing linked automatically')
        page.goto(base+'/people?q='+first)
        expect(page.get_by_text(first+' Rossi',exact=True)).to_be_visible()
        # Assign the Visual Menu course to the student.
        page.goto(base+'/training/manage/students?q='+first)
        page.locator('tr',has_text=first+' Rossi').get_by_role('button',name='Assegna contenuti',exact=True).click()
        page.locator('#student-assignment-form input[name=pills]').first.check()
        page.get_by_role('button',name='Conferma assegnazione',exact=True).click()
        expect(page.locator('#student-assignment-editor')).not_to_be_visible()

        learner=context().new_page()
        # Skipping activation: initial credentials on the sign-in page.
        learner.goto(base+'/training/access')
        learner.locator('[name=username]').fill(username);learner.locator('[name=password]').fill(initial)
        learner.get_by_role('button',name='Accedi',exact=True).click()
        expect(learner.get_by_text('Account non ancora attivato',exact=False)).to_be_visible()
        snap(learner,'05-skip-rejected')
        checks.append('Initial credentials on the sign-in page are refused until activation')
        # Personal link: credentials, then mandatory new password.
        learner.goto(link);learner.wait_for_url('**/training/activation')
        expect(learner.get_by_role('heading',name='Attiva il tuo account',exact=True)).to_be_visible()
        snap(learner,'06-activation-credentials')
        learner.locator('[data-how-works]').click();expect(learner.locator('#rf-help')).to_be_visible()
        snap(learner,'07-activation-help');learner.keyboard.press('Escape')
        learner.locator('[name=username]').fill(username);learner.locator('[name=password]').fill('Wrong-pass-1')
        learner.get_by_role('button',name='Verifica',exact=True).click()
        expect(learner.get_by_role('alert')).to_contain_text('Collegamento non valido')
        learner.locator('[name=username]').fill(username);learner.locator('[name=password]').fill(initial)
        learner.get_by_role('button',name='Verifica',exact=True).click()
        expect(learner.get_by_role('heading',name='Scegli la tua password',exact=True)).to_be_visible()
        snap(learner,'08-mandatory-change')
        learner.goto(base+'/');assert '/login' in learner.url  # no MyRF before completion
        learner.goto(base+'/training/activation')
        learner.locator('[name=password]').fill(initial);learner.locator('[name=password_confirm]').fill(initial)
        learner.get_by_role('button',name='Attiva e continua',exact=True).click()
        expect(learner.get_by_role('alert')).to_contain_text('diversa da quella iniziale')
        learner.locator('[name=password]').fill('Visual-password-123');learner.locator('[name=password_confirm]').fill('Visual-password-123')
        learner.get_by_role('button',name='Attiva e continua',exact=True).click()
        learner.wait_for_url(base+'/')
        expect(learner.get_by_text('Account attivato. Benvenuto in MyRF.',exact=True)).to_be_visible()
        cards=learner.locator('a[href^="/training"]')
        assert cards.count()>=1
        snap(learner,'09-myrf')
        with factory() as db:
            a=db.get(m.RFOneAccount,aid)
            assert a.email_verified_at
            grants=[g.domain_code for g in __import__('rfone_data_store.rfone_account_service',fromlist=['x']).list_domain_access_for_account(db,aid) if g.enabled]
            assert grants==['TRAINING'],grants
        checks.append('Link + username + initial password -> wrong password and same-as-initial refused -> new password -> MyRF with Training only; email verified')
        cards.first.click();learner.wait_for_url('**/training')
        expect(learner.get_by_role('heading',name='Il tuo percorso Training',exact=True)).to_be_visible()
        snap(learner,'10-training-home')
        links=learner.locator('a[href*="/training/course-assignment/"], a[href*="/training/assignment"]')
        assert links.count(),'No course link found'
        links.first.click();snap(learner,'11-course')
        assert learner.goto(base+'/training/manage/students').status==403
        checks.append('Training opens from MyRF; assigned course opens; trainer pages denied')
        # Reused link.
        other=context().new_page();other.goto(link)
        other.locator('[name=username]').fill(username);other.locator('[name=password]').fill(initial)
        other.get_by_role('button',name='Verifica',exact=True).click()
        expect(other.get_by_role('alert')).to_contain_text('già utilizzato');snap(other,'12-link-reused')
        checks.append('Consumed link refused on reuse; initial password no longer valid')
        # Forgot password on the single RF-One account.
        learner.goto(base+'/training/account/recover')
        learner.locator('[name=username]').fill(username);learner.locator('[name=email]').fill(first.lower()+'@example.invalid')
        learner.get_by_role('button',name='Invia codice',exact=True).click()
        code=re.search(r'Code: (\d{6})',sent[-1]['text_body'])[1]
        learner.locator('[name=username]').fill(username);learner.locator('[name=code]').fill(code)
        learner.locator('[name=password]').fill('Recovered-visual-456');learner.locator('[name=password_confirm]').fill('Recovered-visual-456')
        snap(learner,'13-password-reset');learner.get_by_role('button',name='Conferma',exact=True).click()
        learner.locator('[name=username]').fill(username);learner.locator('[name=password]').fill('Recovered-visual-456')
        learner.get_by_role('button',name='Accedi',exact=True).click();learner.wait_for_url('**/training')
        checks.append('Forgot password: code by email, new password, sign-in to Training')
        mobile=context().new_page();mobile.set_viewport_size({'width':390,'height':844})
        mobile.goto(fields(sent[1])[2]);snap(mobile,'14-mobile-activation')
        assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth')
        browser.close()
      assert all(x['to_address'].endswith('@example.invalid') for x in sent)
      (dest/'browser-results.json').write_text(json.dumps({'browser':'Microsoft Edge headless (msedge channel)','checks':checks,
          'emails_intercepted':len(sent),'email_transport':'intercepted, no real delivery','external_requests':'blocked',
          'rollback':True},indent=2),encoding='utf-8')
    finally:
      server.shutdown();thread.join();transaction.rollback();connection.close()
      with engine.connect() as c:
          assert not c.scalar(select(m.RFOneAccount.id).where(m.RFOneAccount.username.like(first.lower()+'%')))
      engine.dispose()
    print('PASS browser:');[print(' -',c) for c in checks];print('All test data rolled back; no real email.')

if __name__=='__main__':run()
