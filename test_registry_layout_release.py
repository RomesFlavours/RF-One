"""Registry layout and existing writes against an isolated disposable database."""
import os, sys, tempfile, json, re
from pathlib import Path

base = Path(sys.argv[1]).resolve()
if (base / '03 Software').exists():
    base = base / '03 Software'
tmp = tempfile.TemporaryDirectory(prefix='registry-layout-test-')
os.environ.update(RFONE_DATABASE_URL='sqlite:///' + str(Path(tmp.name) / 'test.db').replace('\\', '/'),
                  RFONE_FLASK_SECRET_KEY='isolated-registry-layout-test', AWS_EC2_METADATA_DISABLED='true')
os.environ.pop('RFONE_UI_LANGUAGE', None)
sys.path[:0] = [str(base / 'RF-One Web'), str(base / 'RF-One Data Store')]
import app as web
import db, auth
from rfone_data_store import models as m, access_profiles as profiles
from sqlalchemy import select
web.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
m.Base.metadata.create_all(db._engine)
with db.SessionFactory() as s:
    owner = m.RFOneAccount(username='layoutowner', display_name='Layout Owner', password_hash='!',
                          status='ACTIVE', is_admin=True, is_owner=True, session_version=1)
    ordinary = m.RFOneAccount(username='layoutuser', display_name='Layout User', password_hash='!',
                             status='ACTIVE', is_admin=False, is_owner=False, session_version=1)
    company = profiles.CompanyContext(name='Layout Company', kind='COMPANY')
    s.add_all([owner, ordinary, company]); s.commit()
    owner_id, user_id = owner.id, ordinary.id

def client(identity=None):
    c = web.app.test_client()
    if identity:
        with c.session_transaction() as session:
            session['rfone_account_id'] = identity
            session['rfone_session_version'] = 1
    return c

checks = []
c = client(owner_id)
assert client().get('/admin/roles').status_code == 302
assert client(user_id).get('/admin/roles').status_code == 403
checks.append('Anonymous and ordinary-user Registry access remains denied')
for tab in ['people', 'roles', 'areas', 'companies']:
    response = c.get('/admin/roles?tab=' + tab)
    assert response.status_code == 200, (tab, response.status_code)
    html = response.get_data(as_text=True)
    assert 'registry-shell' in html and 'registry-layout.css' in html
    assert 'registry-navigation' in html and 'data-how-works' in html
    assert 'Come funziona' not in html and 'lang="en"' in html
    for anchor in ['registry-person-editor', 'registry-role-dialog', 'registry-area-dialog',
                   'registry-permission-dialog', 'registry-membership-dialog', 'registry-assignment-dialog']:
        assert 'id="' + anchor + '"' in html
    assert html.count('aria-label="Dialog help"') == 6
    checks.append('English layout and contextual page/modal help: ' + tab)
with c.session_transaction() as session:
    token = session[auth.SESSION_CSRF_KEY]
assert c.post('/admin/roles', data={'action':'area_save','name':'Layout Area'}).status_code == 400
r = c.post('/admin/roles', data={'action':'area_save', 'name':'Layout Area', 'tab':'areas', 'csrf_token':token})
assert r.status_code == 302
with db.SessionFactory() as s:
    area = s.scalar(select(m.OperationalArea).where(m.OperationalArea.name=='Layout Area'))
    assert area is not None
    area_id = area.id
r = c.post('/admin/roles', data={'action':'role_save','name':'Layout Role','area_ids':[str(area_id)],'tab':'roles','csrf_token':token})
assert r.status_code == 302
r = c.post('/admin/roles', data={'action':'area_save','name':'Layout Area','tab':'areas','csrf_token':token})
assert r.status_code == 422 and b'profile-data' in r.data
checks.append('Existing area/role saves, duplicate validation and CSRF protection remain functional')

if os.environ.get('REGISTRY_LAYOUT_BROWSER') == '1':
    from werkzeug.serving import make_server
    from threading import Thread
    from playwright.sync_api import sync_playwright
    server = make_server('127.0.0.1', 0, web.app, threaded=True)
    Thread(target=server.serve_forever, daemon=True).start()
    origin = 'http://127.0.0.1:' + str(server.server_port)
    cookie = c.get_cookie(web.app.config['SESSION_COOKIE_NAME'])
    screenshots = Path(os.environ['REGISTRY_LAYOUT_SCREENSHOTS']); screenshots.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width':1440,'height':1000})
        context.add_cookies([{'name':cookie.key, 'value':cookie.value, 'url':origin}])
        context.route('**/*', lambda r: r.continue_() if r.request.url.startswith(origin) else r.abort())
        page = context.new_page(); errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        for width in [1440, 390]:
            page.set_viewport_size({'width':width,'height':1000})
            for tab in ['people','roles','areas','companies']:
                page.goto(origin + '/admin/roles?tab=' + tab)
                assert page.locator('.registry-navigation a[aria-current]').count() == 1
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                page.locator('[data-how-works]').click()
                assert page.locator('#rf-help').evaluate('(e)=>e.open')
                page.locator('#rf-help [aria-label=Close]').click()
                if tab in ['people','roles','areas']:
                    attr = {'people':'data-new-person','roles':'data-new-role','areas':'data-new-area'}[tab]
                    modal = {'people':'person-dialog','roles':'role-dialog','areas':'area-dialog'}[tab]
                    page.locator('[' + attr + ']').click()
                    panel = page.locator('#' + modal)
                    field = panel.locator('input:not([type=hidden])').first
                    field.fill('Unsaved layout draft')
                    panel.get_by_role('button', name='Dialog help', exact=True).click()
                    page.locator('#rf-help [aria-label=Close]').click()
                    assert field.input_value() == 'Unsaved layout draft'
                    page.screenshot(path=str(screenshots / (tab+'-modal-'+str(width)+'.png')))
                    panel.locator('[data-modal-close]').first.click()
                    assert not panel.is_visible()
                if tab == 'roles':
                    page.locator('[data-permissions]').first.click()
                    panel = page.locator('#permission-dialog')
                    panel.get_by_role('button', name='Dialog help', exact=True).click()
                    page.locator('#rf-help [aria-label=Close]').click()
                    panel.locator('[data-modal-close]').first.click()
                page.screenshot(path=str(screenshots / (tab+'-'+str(width)+'.png')))
        assert not errors, errors
        browser.close()
    server.shutdown()
    checks.append('Edge English desktop/mobile: four tabs, no overflow, all principal modals/help and draft retention')
print(json.dumps({'passed':checks, 'database':'disposable SQLite', 'production_writes':False}))
db._engine.dispose()
tmp.cleanup()
