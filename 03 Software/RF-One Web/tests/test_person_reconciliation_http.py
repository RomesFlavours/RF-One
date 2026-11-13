"""Administrator UI, CSRF and real browser confirmation on disposable data."""
from pathlib import Path
import json,threading,unittest
from sqlalchemy import select,func
from test_registry_navigation import NavigationTest as Fixture,SessionFactory,web,m
from rfone_data_store import people_registry as people,person_reconciliation as rec

class PersonReconciliationHTTP(Fixture):
 def test_identity_audit_get_is_readonly_and_admin_only(self):
  with SessionFactory() as db:before=db.scalar(select(func.count()).select_from(m.CandidatePerson))
  r=self.client.get('/admin/registry/identity-reconciliation');self.assertEqual(r.status_code,200);self.assertIn(b'Identity reconciliation',r.data)
  with SessionFactory() as db:self.assertEqual(db.scalar(select(func.count()).select_from(m.CandidatePerson)),before)
  self.assertEqual(web.app.test_client().get('/admin/registry/identity-reconciliation').status_code,302)
  self.assertEqual(self.client.post('/admin/registry/identity-reconciliation',data={}).status_code,400)
 def test_identity_browser_explicitly_confirms_a_person_without_credentials_changes(self):
  from werkzeug.serving import make_server
  from playwright.sync_api import sync_playwright
  with SessionFactory() as db:
   record=m.Employee(display_name='Browser identity source',active=True);db.add(record);db.commit();eid=record.id
   accounts_before=db.scalar(select(func.count()).select_from(m.RFOneAccount))
  server=make_server('127.0.0.1',0,web.app,threaded=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
  try:
   with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True);context=browser.new_context();context.add_cookies([{'name':'session','value':self.client.get_cookie('session').value,'url':base}]);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/admin/roles?tab=people');page.get_by_role('link',name='Identity reconciliation',exact=True).click();group=page.locator('details').filter(has=page.get_by_text('Browser identity source',exact=True)).first
    group.locator('summary').click();group.locator('input[name="new_name"]').fill('Browser confirmed central person');group.get_by_role('button',name='Create person and confirm links',exact=True).click();page.wait_for_url('**/identity-reconciliation?person_id=*')
    self.assertIn('Identity links confirmed.',page.locator('body').inner_text());self.assertEqual(errors,[]);browser.close()
  finally:server.shutdown();thread.join()
  with SessionFactory() as db:
   linked=db.get(people.PersonEmployeeLink,eid);self.assertIsNotNone(linked);self.assertEqual(db.get(m.CandidatePerson,linked.person_id).full_name,'Browser confirmed central person');self.assertEqual(db.scalar(select(func.count()).select_from(m.RFOneAccount)),accounts_before)

# Run only this fixture class; importing the reusable fixture must not duplicate it.
def load_tests(loader,tests,pattern):return loader.loadTestsFromTestCase(PersonReconciliationHTTP)
if __name__=='__main__':unittest.main()
