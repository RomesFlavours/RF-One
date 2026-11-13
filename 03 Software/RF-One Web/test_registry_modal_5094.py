"""Actual loopback Registry E2E; synthetic person is removed in finally.

Targets only the verified 5094 launcher and its local database. Original profile
and account data are digested before/after. No external requests are allowed.
"""
import json, sys, uuid, socket, time
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from playwright.sync_api import sync_playwright, expect

BASE='http://127.0.0.1:5094'
LOCAL=Path('C:/Users/servi/AppData/Local/RF-One/Employee Directory/AWS-20261110T120743Z')
OUT=Path('C:/Users/servi/AppData/Local/RF-One/Backups/registry-person-modal-20261112')


def run():
    state=json.loads((LOCAL/'verification.json').read_text(encoding='utf-8'))
    cfg=state['local_database']
    assert cfg['host']=='127.0.0.1' and cfg['database']=='rfone_employee_directory' and state['web_port']==5094
    engine=create_engine(URL.create('postgresql+psycopg2',username=cfg['username'],host=cfg['host'],port=cfg['port'],database=cfg['database']))
    for attempt in range(30):
        try:
            with socket.create_connection(('127.0.0.1',5094),timeout=1):break
        except OSError:time.sleep(1)
    else:raise RuntimeError('Verified local service did not start.')
    name='ZZ QA Registry '+uuid.uuid4().hex[:12]
    person_id=account_id=None
    checks=[]
    tables=['employees','rfone_accounts','rfone_person_company_memberships','rfone_role_profile_assignments','rfone_account_domain_access']
    def digests(c):
        return {table:c.scalar(text("SELECT md5(string_agg(row_to_json(t)::text,'|' ORDER BY id)) FROM "+table+' t')) for table in tables}
    with engine.connect() as c:
        before=digests(c)
        event_start=c.scalar(text('SELECT coalesce(max(id),0) FROM rfone_access_profile_events'))
    def verify(codes,status):
        with engine.connect() as c:
            actual=set(c.execute(text('SELECT code FROM rfone_person_company_statuses WHERE employee_id=:id'),{'id':person_id}).scalars())
            assert actual==set(codes),(actual,codes)
            assert c.scalar(text('SELECT status FROM rfone_accounts WHERE id=:id'),{'id':account_id})==status
            assert c.scalar(text('SELECT count(*) FROM employees WHERE display_name=:name'),{'name':name})==1
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            context=browser.new_context(viewport={'width':1440,'height':1000},locale='it-IT')
            context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(BASE+'/') else route.abort())
            page=context.new_page();errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
            response=page.goto(BASE+'/admin/roles',wait_until='networkidle');assert response.status==200
            page.locator('[data-new-person]').click()
            modal=page.locator('#person-dialog');panel=modal.locator('.profile-modal')
            expect(modal).to_be_visible()
            box=panel.bounding_box();assert box['width']<=760 and box['height']<650,box
            expect(modal.get_by_text('Status Aziendale',exact=True)).to_be_visible()
            expect(modal.locator('[name=account_status]')).to_be_visible()
            page.screenshot(path=str(OUT/'person-modal-desktop.png'))
            modal.locator('[name=name]').fill(name)
            modal.locator('[name=email]').fill('registry-qa@example.test')
            modal.get_by_role('checkbox',name='Candidato',exact=True).check()
            modal.get_by_role('checkbox',name='Dipendente',exact=True).check()
            modal.locator('[name=account_status]').select_option('ACTIVE')
            modal.get_by_role('button',name='Aiuto gestione persona').click()
            expect(page.locator('#registry-person-editor')).to_be_visible()
            page.keyboard.press('Escape');expect(modal).to_be_visible()
            assert modal.locator('[name=name]').input_value()==name
            with page.expect_navigation():modal.get_by_role('button',name='Salva',exact=True).click()
            expect(modal).to_be_hidden()
            payload=page.locator('#profile-data').evaluate('(el)=>JSON.parse(el.textContent)')
            person=next(row for row in payload['people'] if row['name']==name)
            key=person['key'];person_id=int(key.split(':')[1])
            with engine.connect() as c:
                account_id=c.scalar(text('SELECT rfone_account_id FROM employee_context_links WHERE employee_id=:id AND rfone_account_id IS NOT NULL'),{'id':person_id})
            assert account_id is not None
            verify(['CANDIDATE','EMPLOYEE'],'ACTIVE')
            checks.append('Desktop: compact Italian modal, contextual help retains draft, create saves both statuses and one identity.')
            button=page.locator('[data-edit-person="'+key+'"]');button.click()
            expect(modal.get_by_role('checkbox',name='Candidato',exact=True)).to_be_checked()
            assert modal.locator('[name=account_status]').input_value()=='ACTIVE'
            modal.locator('[name=account_status]').select_option('INACTIVE')
            modal.locator('[name=email]').evaluate("el=>{el.type='text';el.value='invalid';}")
            with page.expect_navigation():modal.get_by_role('button',name='Salva',exact=True).click()
            expect(modal).to_be_visible()
            expect(modal.get_by_role('alert')).to_contain_text('email valido')
            assert modal.locator('[name=email]').input_value()=='invalid'
            assert modal.locator('[name=account_status]').input_value()=='INACTIVE'
            verify(['CANDIDATE','EMPLOYEE'],'ACTIVE')
            modal.locator('[name=email]').fill('registry-qa@example.test')
            modal.get_by_role('checkbox',name='Candidato',exact=True).uncheck()
            modal.get_by_role('checkbox',name='Esterno',exact=True).check()
            with page.expect_navigation():modal.get_by_role('button',name='Salva',exact=True).click()
            expect(modal).to_be_hidden();verify(['EXTERNAL','EMPLOYEE'],'INACTIVE')
            assert page.evaluate('document.activeElement.dataset.editPerson')==key
            page.reload(wait_until='networkidle');page.locator('[data-edit-person="'+key+'"]').click()
            expect(modal.get_by_role('checkbox',name='Esterno',exact=True)).to_be_checked()
            assert modal.locator('[name=account_status]').input_value()=='INACTIVE'
            page.keyboard.press('Escape');expect(modal).to_be_hidden()
            checks.append('Desktop edit: validation rolls back partial changes; corrected save, reload and row focus retain persisted statuses.')
            page.set_viewport_size({'width':390,'height':844})
            page.locator('[data-edit-person="'+key+'"]').click()
            box=panel.bounding_box();assert box['x']>=0 and box['x']+box['width']<=391,box
            modal.locator('[name=account_status]').select_option('ACTIVE')
            modal.get_by_role('button',name='Aiuto gestione persona').click()
            page.locator('#rf-help').get_by_role('button',name='Chiudi',exact=True).click()
            expect(modal).to_be_visible()
            assert modal.locator('[name=account_status]').input_value()=='ACTIVE'
            page.screenshot(path=str(OUT/'person-modal-mobile.png'))
            with page.expect_navigation():modal.get_by_role('button',name='Salva',exact=True).click()
            expect(modal).to_be_hidden();verify(['EXTERNAL','EMPLOYEE'],'ACTIVE')
            page.locator('[data-edit-person="'+key+'"]').click()
            modal.get_by_role('checkbox',name='Candidato',exact=True).check()
            modal.get_by_role('button',name='Chiudi',exact=True).click();expect(modal).to_be_hidden()
            verify(['EXTERNAL','EMPLOYEE'],'ACTIVE')
            assert not errors,errors
            checks.append('Mobile 390px: responsive panel, Help preserves draft, save persists account reactivation; X cancels without writes; zero JS errors.')
            context.close();browser.close()
    finally:
        with engine.begin() as c:
            # Restrict cleanup to this unique synthetic identity even after failed UI assertions.
            found=c.execute(text('SELECT id FROM employees WHERE display_name=:name'),{'name':name}).scalars().all()
            assert len(found)<=1
            if found:
                person_id=found[0]
                account_id=c.scalar(text('SELECT rfone_account_id FROM employee_context_links WHERE employee_id=:id AND rfone_account_id IS NOT NULL'),{'id':person_id})
                member_ids=set(c.execute(text('SELECT id FROM rfone_person_company_memberships WHERE employee_id=:id'),{'id':person_id}).scalars())
                for row in c.execute(text('SELECT id,details FROM rfone_access_profile_events WHERE id>:start'),{'start':event_start}):
                    details=row.details
                    if details.get('target')==f'employee:{person_id}' or details.get('employee_id')==person_id or details.get('account_id')==account_id or details.get('membership_id') in member_ids:
                        c.execute(text('DELETE FROM rfone_access_profile_events WHERE id=:id'),{'id':row.id})
                c.execute(text('DELETE FROM rfone_person_company_statuses WHERE employee_id=:id'),{'id':person_id})
                c.execute(text('DELETE FROM employee_directory_events WHERE employee_id=:id'),{'id':person_id})
                c.execute(text('DELETE FROM rfone_person_company_memberships WHERE employee_id=:id'),{'id':person_id})
                c.execute(text('DELETE FROM employee_context_links WHERE employee_id=:id'),{'id':person_id})
                if account_id is not None:c.execute(text('DELETE FROM rfone_accounts WHERE id=:id'),{'id':account_id})
                c.execute(text('DELETE FROM employees WHERE id=:id AND display_name=:name'),{'id':person_id,'name':name})
            assert digests(c)==before,'Original records changed; inspect before continuing.'
        engine.dispose()
    checks.append('Synthetic person/account/status/audit rows removed; original people, accounts, memberships, roles and direct grants match pre-test digests.')
    OUT.joinpath('verification.json').write_text(json.dumps({'base_url':BASE,'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
    for check in checks:print('PASS:',check)

if __name__=='__main__':run()
