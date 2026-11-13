"""Isolated SQLite HTTP, compatibility and additive migration regression checks."""
import test_interviews as fixture
from test_interviews import m, people, SessionFactory, _engine, web
from sqlalchemy import select, func, inspect, text
from sqlalchemy.exc import IntegrityError
from rfone_data_store import student_registry as students
from rfone_data_store.training import workspace
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
import importlib.util
import unittest


class RegistryStatusTests(unittest.TestCase):
    setUpClass = classmethod(fixture.InterviewTests.setUpClass.__func__)
    setUp = fixture.InterviewTests.setUp
    tearDown = fixture.InterviewTests.tearDown
    login = fixture.InterviewTests.login

    @classmethod
    def tearDownClass(cls):
        _engine.dispose()
        fixture.TEMP.cleanup()

    def test_multiple_relationships_do_not_grant_access(self):
        p = people.create_person(self.db, self.admin, 'Employee external',
            company_codes=['EMPLOYEE', 'EXTERNAL'])
        self.assertEqual(people.company_statuses(self.db, p.id), {'EMPLOYEE', 'EXTERNAL'})
        self.assertTrue(students.eligible_for_training(self.db, p.id))
        self.assertIsNone(self.db.get(students.PersonQualification, (p.id, 'STUDENT')))
        self.assertIsNone(people.delivery_account(self.db, p.id))
        self.assertFalse(students.eligible_for_training(self.db, 999999))
        people.set_company_statuses(self.db, self.admin, p.id, ['CANDIDATE', 'EMPLOYEE'])
        self.assertEqual(people.company_statuses(self.db, p.id), {'CANDIDATE', 'EMPLOYEE'})

    def test_selection_reuses_registry_identity_and_keeps_qualifications(self):
        from rfone_data_store.selection.identity_service import resolve_or_create_person
        p=people.create_person(self.db,self.admin,'Candidate employee','selection-status@example.test',company_codes=['EMPLOYEE'])
        restaurant=m.Restaurant(name='Scoped selection');self.db.add(restaurant);self.db.flush()
        resolved,is_new=resolve_or_create_person(self.db,restaurant_id=restaurant.id,full_name=p.full_name,email=p.primary_email,phone=None)
        self.assertFalse(is_new)
        self.assertEqual(resolved.id,p.id)
        self.assertEqual(people.company_statuses(self.db,p.id),{'EMPLOYEE'})
        created,is_new=resolve_or_create_person(self.db,restaurant_id=None,full_name='New candidate',email='new-candidate@example.test',phone=None)
        self.assertTrue(is_new)
        self.assertEqual(created.primary_email,'new-candidate@example.test')

    def test_local_italian_and_shared_english_help(self):
        self.login(self.admin)
        web.app.config['RFONE_LOCAL_OPERATOR']='rfone'
        try:
            response=self.client.get('/people',base_url='https://localhost')
            self.assertEqual(response.status_code,200)
            self.assertIn(b'Come funziona questa pagina',response.data)
            self.assertIn(b'Status Aziendale',response.data)
            self.assertIn(b'name="company_status"',response.data)
        finally:
            web.app.config.pop('RFONE_LOCAL_OPERATOR',None)
        response=self.client.get('/people',base_url='https://localhost')
        self.assertIn(b'How this page works',response.data)
        self.assertIn(b'Company status',response.data)

    def test_edge_desktop_mobile_form_and_help(self):
        from playwright.sync_api import sync_playwright
        from werkzeug.serving import make_server
        from threading import Thread
        self.login(self.admin)
        web.app.config['RFONE_LOCAL_OPERATOR']='rfone'
        server=make_server('127.0.0.1',0,web.app)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        cookie=self.client.get_cookie(web.app.config['SESSION_COOKIE_NAME'])
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                context=browser.new_context(viewport={'width':1440,'height':1000})
                context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base) else route.abort())
                context.add_cookies([{'name':cookie.key,'value':cookie.value,'url':base}])
                page=context.new_page()
                for width in [1440,390]:
                    page.set_viewport_size({'width':width,'height':900})
                    page.goto(base+'/people')
                    page.get_by_text('Aggiungi una persona',exact=True).click()
                    page.get_by_label('Nome e cognome',exact=True).fill('Browser employee')
                    page.get_by_role('checkbox',name='Dipendente',exact=True).check()
                    page.get_by_role('checkbox',name='Esterno',exact=True).check()
                    page.get_by_role('button',name='Come funziona questa pagina').click()
                    self.assertTrue(page.locator('#rf-help').evaluate('(el)=>el.open'))
                    page.get_by_role('button',name='Chiudi',exact=True).click()
                    self.assertEqual(page.get_by_label('Nome e cognome',exact=True).input_value(),'Browser employee')
                    self.assertTrue(page.get_by_role('checkbox',name='Dipendente',exact=True).is_checked())
                page.get_by_role('button',name='Aggiungi persona',exact=True).click()
                page.wait_for_url('**/people/*')
                self.assertTrue(page.get_by_role('checkbox',name='Dipendente',exact=True).is_checked())
                self.assertTrue(page.get_by_role('checkbox',name='Esterno',exact=True).is_checked())
                self.assertIn('Nessun account RF-One collegato',page.locator('body').inner_text())
                context.close();browser.close()
        finally:
            server.shutdown();thread.join();server.server_close()
            web.app.config.pop('RFONE_LOCAL_OPERATOR',None)

    def test_existing_employee_link_preserves_eligibility_and_other_qualifications(self):
        source=m.SourceSystem(code='STATUS_TEST',name='Status test');self.db.add(source);self.db.flush()
        merchant=m.Merchant(source_system_id=source.id,source_merchant_id='status-test',name='Status merchant')
        self.db.add(merchant);self.db.flush()
        location=m.Location(merchant_id=merchant.id,name='Status location',source_system_id=source.id,source_location_id='status-test',timezone='America/New_York')
        self.db.add(location);self.db.flush()
        employee=m.Employee(location_id=location.id,source_system_id=source.id,source_employee_id='status-employee',display_name='Linked employee')
        self.db.add(employee);self.db.flush()
        p=people.create_person(self.db,self.admin,'Linked employee',company_codes=['CANDIDATE'])
        people.link_source(self.db,self.admin,p.id,'employee',employee.id)
        self.db.add(students.PersonQualification(person_id=p.id,code='STUDENT'));self.db.flush()
        people.set_company_statuses(self.db,self.admin,p.id,['EXTERNAL'])
        self.assertEqual(people.company_statuses(self.db,p.id),{'EXTERNAL','EMPLOYEE'})
        self.assertTrue(students.eligible_for_training(self.db,p.id))
        self.assertIsNotNone(self.db.get(students.PersonQualification,(p.id,'STUDENT')))
        self.assertEqual(self.db.get(people.PersonEmployeeLink,employee.id).person_id,p.id)

    def test_validation_and_duplicate_contacts(self):
        p = people.create_person(self.db, self.admin, 'Unique contact', 'unique-status@example.test')
        with self.assertRaises(ValueError):
            people.create_person(self.db, self.admin, 'Different name', 'UNIQUE-STATUS@example.test')
        with self.assertRaises(ValueError):
            people.set_company_statuses(self.db, self.admin, p.id, ['ADMIN'])
        with self.assertRaises(PermissionError):
            people.set_company_statuses(self.db, self.person, p.id, ['EMPLOYEE'])
        self.assertFalse(students.eligible_for_training(self.db, p.id))

    def test_manual_http_and_account_independence(self):
        self.login(self.admin)
        data=dict(action='create', full_name='Manual multi status', email='manual-status@example.test',
                  company_status=['EMPLOYEE','CANDIDATE'], csrf_token='test-csrf')
        response=self.client.post('/people', data=data, base_url='https://localhost')
        self.assertEqual(response.status_code, 302)
        p=self.db.scalar(select(m.CandidatePerson).where(m.CandidatePerson.primary_email==data['email']))
        self.assertEqual(people.company_statuses(self.db,p.id), {'EMPLOYEE','CANDIDATE'})
        self.assertEqual(self.client.get(response.location, base_url='https://localhost').status_code,200)
        self.db.rollback()
        response=self.client.post('/people', data=data, base_url='https://localhost')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'manual-status@example.test',response.data)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.CandidatePerson).where(m.CandidatePerson.primary_email==data['email'])),1)
        pid=p.id
        self.db.rollback()
        response=self.client.post(f'/people/{pid}',data={'company_status':['EXTERNAL'],'csrf_token':'test-csrf'},base_url='https://localhost')
        self.assertEqual(response.status_code,302)
        self.assertEqual(people.company_statuses(self.db,pid),{'EXTERNAL'})
        self.assertEqual(self.person.status,'ACTIVE')
        self.db.rollback()
        self.assertEqual(self.client.post(f'/people/{pid}',data={'company_status':'EMPLOYEE'},base_url='https://localhost').status_code,400)

    def test_training_resolves_existing_employee_without_student_qualification(self):
        p=people.create_person(self.db,self.admin,'Employee training', 'employee-training@example.test',company_codes=['EMPLOYEE'])
        resolved, account=students.resolve(self.db,name=p.full_name,email=p.primary_email,username='employee-training',confirmation=f'person:{p.id}')
        self.assertEqual(resolved.id,p.id)
        self.assertTrue(students.eligible_for_training(self.db,p.id))
        self.assertIsNone(self.db.get(students.PersonQualification,(p.id,'STUDENT')))
        import training_integration as integration
        rf, training=integration.create_student_via_rf_one(self.db,username='employee-training',
            display_name=p.full_name,email=p.primary_email,password='Long-pass-123!',confirmation=f'person:{p.id}')
        self.assertEqual(self.db.get(students.TrainingPersonLink,training.id).person_id,p.id)
        self.assertIsNone(self.db.get(students.PersonQualification,(p.id,'STUDENT')))
        rf.status='INACTIVE'
        self.assertTrue(students.eligible_for_training(self.db,p.id))
        self.assertIsNone(people.delivery_account(self.db,p.id))
        # Repeating onboarding never creates another person.
        count=self.db.scalar(select(func.count()).select_from(m.CandidatePerson))
        with self.assertRaises(ValueError):
            integration.create_student_via_rf_one(self.db,username='employee-training',
                display_name=p.full_name,email=p.primary_email,password='Long-pass-123!',confirmation=f'person:{p.id}')
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.CandidatePerson)),count)

    def test_additive_migration_and_pre_migration_read_compatibility(self):
        # A separate disposable database tests the exact migration, preserving old rows.
        from sqlalchemy import create_engine
        engine=create_engine('sqlite://')
        path=Path(__file__).resolve().parents[2]/'RF-One Data Store/migrations/versions/t9c120261112_person_company_status.py'
        spec=importlib.util.spec_from_file_location('status_migration',path)
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        with engine.begin() as c:
            c.execute(text('CREATE TABLE candidate_persons (id INTEGER PRIMARY KEY, full_name TEXT)'))
            c.execute(text("INSERT INTO candidate_persons VALUES (1, 'Preserved')"))
            from sqlalchemy.orm import Session
            with Session(c) as old:
                self.assertEqual(people.company_statuses(old,1),set())
            with Operations.context(MigrationContext.configure(c)):
                migration.upgrade()
                migration.upgrade()
            self.assertEqual(c.scalar(text('SELECT full_name FROM candidate_persons WHERE id=1')),'Preserved')
            self.assertEqual(c.scalar(text('SELECT count(*) FROM person_company_statuses')),0)
            with self.assertRaises(IntegrityError):
                c.execute(text("INSERT INTO person_company_statuses VALUES (1,'ADMIN',CURRENT_TIMESTAMP)"))
        engine.dispose()
        with self.assertRaises(RuntimeError):migration.downgrade()


if __name__ == '__main__':
    unittest.main()
