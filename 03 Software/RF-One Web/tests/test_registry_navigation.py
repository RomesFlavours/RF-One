"""Real Registry navigation with disposable SQLite and a headless browser."""
from pathlib import Path
import os,sys,tempfile,unittest,json,re,threading
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'RF-One Web'),str(ROOT/'RF-One Data Store')]
TMP=tempfile.TemporaryDirectory(prefix='registry-navigation-')
os.environ.update(RFONE_DATABASE_URL='sqlite:///'+str(Path(TMP.name)/'fixture.db').replace('\\','/'),RFONE_FLASK_SECRET_KEY='navigation-disposable-only',AWS_EC2_METADATA_DISABLED='true')
import app as web
from db import SessionFactory,_engine
from rfone_data_store import models as m
from sqlalchemy import select
from urllib.parse import urlsplit,parse_qs

class NavigationTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  m.Base.metadata.create_all(_engine);web.app.config.update(TESTING=True,SESSION_COOKIE_SECURE=False)
  with SessionFactory() as db:
   a=m.RFOneAccount(username='owner',display_name='Owner',password_hash='!',status='ACTIVE',is_admin=True,is_owner=True,session_version=1)
   b=m.RFOneAccount(username='external',display_name='External',password_hash='!',status='ACTIVE',is_admin=False,is_owner=False,session_version=1)
   p=m.Employee(display_name='Owner person',active=True);db.add_all([a,b,p]);db.flush();db.add(m.EmployeeContextLink(employee_id=p.id,rfone_account_id=a.id));db.commit();cls.owner,cls.external,cls.person=a.id,b.id,p.id
 @classmethod
 def tearDownClass(cls):_engine.dispose();TMP.cleanup()
 def setUp(self):
  self.client=web.app.test_client()
  with self.client.session_transaction() as s:s['rfone_account_id']=self.owner;s['rfone_session_version']=1;s['rfone_csrf_token']='token'
 def post(self,path,**data):return self.client.post(path,data={'csrf_token':'token',**data})
 def assertPerson(self,response,target):
  self.assertEqual(response.status_code,302);u=urlsplit(response.location);self.assertEqual(u.path,'/admin/roles');self.assertEqual(parse_qs(u.query)['person'],[target]);self.assertEqual(u.fragment,'people-table')
 def test_access_save_returns_same_person_and_own_account(self):
  for account,target in [(self.owner,f'employee:{self.person}'),(self.external,f'account:{self.external}')]:
   self.assertPerson(self.post(f'/admin/accounts/{account}/access',from_person=f'account:{account}',access_KITCHEN='all',role_KITCHEN=''),target)
   page=self.client.get('/admin/roles?tab=people&person='+target).get_data(as_text=True)
   payload=json.loads(re.search(r'<script id="profile-data" type="application/json">(.*?)</script>',page,re.S)[1]);self.assertEqual(payload['returnPerson'],target)
 def test_breadcrumbs_context_and_legacy_entry(self):
  for suffix in ('access','edit','training-link'):
   r=self.client.get(f'/admin/accounts/{self.owner}/{suffix}');self.assertEqual(r.status_code,200);text=r.get_data(as_text=True)
   self.assertNotIn('href="/admin/accounts"',text);self.assertNotIn('/administration/employees',text);self.assertIn('Back to person',text);self.assertIn('name="from_person"',text)
  r=self.client.get('/admin/accounts');self.assertEqual(r.location,'/admin/roles?tab=people')
 def test_error_preserves_permissions_form_and_rolls_back(self):
  with patch.object(web.account_service,'set_domain_access',side_effect=ValueError('fixture validation failure')):
   r=self.post(f'/admin/accounts/{self.external}/access',from_person=f'account:{self.external}',access_KITCHEN='all',role_KITCHEN='admin')
  self.assertEqual(r.status_code,400);text=r.get_data(as_text=True);self.assertIn('Nothing saved.',text)
  kitchen=text.split('data-domain="KITCHEN"',1)[1].split('</fieldset>',1)[0];self.assertRegex(kitchen,r'value="all"\s+checked');self.assertRegex(kitchen,r'value="admin"\s+selected')
 def test_context_cannot_switch_person_or_redirect_outside_registry(self):
  for target in (f'employee:{self.person+999}',f'account:{self.owner}', 'https://example.com','//example.com'):
   self.assertEqual(self.post(f'/admin/accounts/{self.external}/access',from_person=target).status_code,400)
  self.assertEqual(self.client.post(f'/admin/accounts/{self.external}/access',data={}).status_code,400)
 def test_account_save_password_and_training_return(self):
  self.assertPerson(self.post(f'/admin/accounts/{self.external}/edit',display_name='External',status='ACTIVE'),f'account:{self.external}')
  r=self.post(f'/admin/accounts/{self.external}/reset-password',password='one',password_confirm='two');self.assertEqual(r.status_code,302);self.assertIn('from_person=account:',r.location);self.assertTrue(r.location.endswith('#reset-password'))
  self.assertPerson(self.post(f'/admin/accounts/{self.external}/reset-password',password='Valid-fixture-pass-123',password_confirm='Valid-fixture-pass-123'),f'account:{self.external}')
  self.assertPerson(self.post(f'/admin/accounts/{self.external}/training-link',action='create_new',role_code='student'),f'account:{self.external}')
 def test_z_own_password_reset_preserves_person_through_login(self):
  r=self.post(f'/admin/accounts/{self.owner}/reset-password',password='Owner-fixture-pass-123',password_confirm='Owner-fixture-pass-123')
  self.assertEqual(r.status_code,302);u=urlsplit(r.location);self.assertEqual(u.path,'/login')
  destination=parse_qs(u.query)['next'][0];self.assertEqual(parse_qs(urlsplit(destination).query)['person'],[f'employee:{self.person}'])
  self.assertEqual(urlsplit(destination).path,'/admin/roles')
 def test_nonadmin_cannot_use_navigation_to_gain_access(self):
  with SessionFactory() as db:version=db.get(m.RFOneAccount,self.external).session_version
  with self.client.session_transaction() as s:s['rfone_account_id']=self.external;s['rfone_session_version']=version
  self.assertEqual(self.client.get(f'/admin/accounts/{self.owner}/access').status_code,403)
 @unittest.skipIf(os.environ.get('RFONE_TEST_SKIP_BROWSER')=='1','Headless browser coverage runs locally')
 def test_browser_reopens_person_after_save_and_back_link(self):
  from werkzeug.serving import make_server
  from playwright.sync_api import sync_playwright
  server=make_server('127.0.0.1',0,web.app,threaded=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
  try:
   with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    context=browser.new_context();context.add_cookies([{'name':'session','value':self.client.get_cookie('session').value,'url':base}]);page=context.new_page()
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+f'/admin/accounts/{self.owner}/access?from_person=account:{self.owner}')
    page.get_by_role('button',name='Save',exact=True).click();page.wait_for_url('**/admin/roles?**')
    dialog=page.locator('#person-dialog');dialog.wait_for(state='visible');self.assertEqual(page.locator('#person-dialog input[name="person"]').input_value(),f'employee:{self.person}')
    self.assertEqual(page.locator('#person-dialog input[name="name"]').input_value(),'Owner person')
    page.goto(base+f'/admin/accounts/{self.owner}/edit');page.get_by_role('link',name='Back to person',exact=True).click();dialog.wait_for(state='visible')
    self.assertEqual(page.locator('#person-dialog input[name="person"]').input_value(),f'employee:{self.person}');self.assertEqual(errors,[])
    browser.close()
  finally:server.shutdown();thread.join()

if __name__=='__main__':unittest.main()
