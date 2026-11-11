"""Registry HTTP + real held-shift attribution; disposable SQLite only."""
from pathlib import Path
import sys, tempfile, unittest
from functools import wraps
from datetime import datetime, timezone, date, timedelta
from flask import Flask, abort, request
from jinja2 import ChoiceLoader, DictLoader
from sqlalchemy import select
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'RF-One Data Store'), str(ROOT / 'RF-One Web')]
from rfone_data_store import models as m, access_profiles as profiles
from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store.technical.connectors.clover.identity_holds import unattributed_work
from role_profile_routes import register_role_profile_routes

class RegistryCloverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='registry-clover-')
        self.engine = create_configured_engine('sqlite:///' + str(Path(self.tmp.name) / 'test.db'))
        m.Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.engine.dispose)
        with self.factory() as db:
            source = m.SourceSystem(code='CLOVER', name='Clover'); db.add(source); db.flush()
            merchant = m.Merchant(name='WP', source_system_id=source.id, source_merchant_id='WP'); db.add(merchant); db.flush()
            loc = m.Location(name='Winter Park', merchant_id=merchant.id, source_system_id=source.id, source_location_id='WP', timezone='America/New_York'); db.add(loc); db.flush()
            person = m.Employee(display_name='Existing person', location_id=loc.id, source_system_id=source.id, source_employee_id='existing')
            admin = m.RFOneAccount(username='admin', display_name='Admin', password_hash='!', status='ACTIVE', is_owner=True, is_admin=True, session_version=1)
            db.add_all([person,admin]); db.flush()
            link = m.EmployeeCloverLink(location_id=loc.id, merchant_id='WP', external_employee_id='pending', state='PRESENT', snapshot={'name':'Clover person'})
            run = m.IngestionRun(source_system_id=source.id, location_id=loc.id, status='COMPLETE', started_at=datetime.now(timezone.utc))
            db.add_all([link,run]); db.flush()
            self.loc, self.link, self.person, self.admin = loc.id,link.id,person.id,admin.id
            for i in range(7):
                raw={'id':f'held-{i}', 'employee':{'id':'pending'}, 'inTime':int((datetime(2026,10,26,16,tzinfo=timezone.utc)+timedelta(days=i)).timestamp()*1000)}
                db.add(m.SourceRecord(source_system_id=source.id, retrieved_at=datetime.now(timezone.utc), payload_hash='fixture', ingestion_run_id=run.id, entity_type='shift', source_id=raw['id'], raw_json=raw))
            db.commit()
        self.actor = self.admin
        app = Flask(__name__, template_folder=str(ROOT / 'RF-One Web/templates')); app.secret_key='test'; app.testing=True
        app.jinja_loader = ChoiceLoader([DictLoader({'base.html':'{% block content %}{% endblock %}', '_nav_macros.html':'{% macro breadcrumb(items) %}{% endmacro %}'}),app.jinja_loader])
        app.jinja_env.globals['csrf_token'] = lambda:'token'
        def load(db): return db.get(m.RFOneAccount,self.actor) if self.actor else None
        def admin_required(fn):
            @wraps(fn)
            def wrapper(*a,**kw):
                with self.factory() as db:
                    actor=load(db)
                    if not actor or not actor.is_admin: abort(403)
                return fn(*a,**kw)
            return wrapper
        def csrf():
            if request.form.get('csrf_token') != 'token': abort(400)
        app.add_url_rule('/', 'home',lambda:'home')
        app.add_url_rule('/account/<int:account_id>', 'admin_account_access',lambda account_id:'access')
        app.add_url_rule('/account/<int:account_id>/edit', 'admin_account_edit',lambda account_id:'edit')
        register_role_profile_routes(app,SessionFactory=self.factory,require_admin=admin_required,load_current_account=load,require_csrf=csrf,domains=[])
        self.client=app.test_client()
    def tearDown(self):
        self.engine.dispose(); self.tmp.cleanup()
    def post(self,**extra):
        return self.client.post('/admin/roles',data={'action':'clover_confirm','tab':'people','link_id':str(self.link),'employee_id':str(self.person),'csrf_token':'token',**extra})
    def held(self,db):
        return unattributed_work(db,location_ids=[self.loc],first_business_date=date(2026,10,26),last_business_date=date(2026,11,1),window_start=datetime(2026,10,26,tzinfo=timezone.utc),window_end=datetime(2026,11,2,tzinfo=timezone.utc))['shifts']
    def test_existing_person_and_seven_shifts(self):
        response=self.client.get('/admin/roles')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'Clover person',response.data); self.assertIn(b'held-6',response.data)
        self.assertIn(b'2026-10-26 12:00 EDT',response.data)
        with self.factory() as db:self.assertEqual(self.held(db),7)
        self.assertEqual(self.post().status_code,302)
        with self.factory() as db:
            self.assertEqual(self.held(db),0)
            self.assertEqual(len(list(db.scalars(select(m.Shift).where(m.Shift.employee_id==self.person)))),7)
            self.assertEqual(db.get(m.EmployeeCloverLink,self.link).employee_id,self.person)
        self.assertEqual(self.post().status_code,422)
        with self.factory() as db:self.assertEqual(len(list(db.scalars(select(m.Shift)))),7)
    def test_invalid_target_rolls_back(self):
        self.assertEqual(self.post(employee_id='999999').status_code,422)
        with self.factory() as db:
            self.assertIsNone(db.get(m.EmployeeCloverLink,self.link).employee_id); self.assertEqual(self.held(db),7)
    def test_explicit_new_person(self):
        self.assertEqual(self.post(create_new='yes',employee_id='').status_code,302)
        with self.factory() as db:
            linked=db.get(m.EmployeeCloverLink,self.link).employee_id
            self.assertNotEqual(linked,self.person); self.assertEqual(self.held(db),0)
    def test_csrf_and_access(self):
        self.assertEqual(self.post(csrf_token='bad').status_code,400)
        self.actor=None
        self.assertEqual(self.post().status_code,403)
        with self.factory() as db:self.assertEqual(self.held(db),7)

if __name__=='__main__':unittest.main()
