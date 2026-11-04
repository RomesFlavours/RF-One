"""Registry invariants and HTTP authorization; disposable in-memory DB only."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import os,sys,unittest
os.environ['RFONE_DATABASE_URL']='sqlite:///:memory:'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'RF-One Web'))
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker
from flask import Flask
from rfone_data_store import models as m,employee_registry as svc,display_format
from rfone_data_store.technical.connectors.clover.ingest import upsert
from rfone_data_store.technical.connectors.clover.acquisition import _get_or_create

class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite:///:memory:')
        m.Base.metadata.create_all(self.engine)
        self.Factory=sessionmaker(self.engine,expire_on_commit=False)
        self.db=self.Factory();d=self.db
        source=m.SourceSystem(code='CLOVER',name='Clover');d.add(source);d.flush()
        merchant=m.Merchant(source_system_id=source.id,source_merchant_id='synthetic-merchant',name='Test merchant');d.add(merchant);d.flush()
        location=m.Location(merchant_id=merchant.id,name='Test location',source_system_id=source.id,source_location_id='synthetic',timezone='America/New_York');d.add(location);d.flush()
        restaurant=m.Restaurant(name='Test restaurant');d.add(restaurant);d.flush()
        d.add(m.RestaurantLocation(restaurant_id=restaurant.id,location_id=location.id))
        area=m.OperationalArea(name='FOH',restaurant_id=restaurant.id,active=True)
        host=m.RestaurantRole(name='Host',restaurant_id=restaurant.id,active=True)
        server=m.RestaurantRole(name='Server',restaurant_id=restaurant.id,active=True)
        account=m.RFOneAccount(username='synthetic-admin',display_name='Test admin',password_hash='unused',status='ACTIVE',is_admin=True,session_version=1)
        d.add_all([area,host,server,account]);d.flush()
        self.location=location;self.restaurant=restaurant;self.area=area;self.host=host;self.server=server;self.account=account
        self.employee=upsert(d,m.Employee,{'source_system_id':source.id,'source_employee_id':'synthetic-employee'},
            {'display_name':'Source Name','custom_id':'A','location_id':location.id})
        d.flush();self.profile=d.get(m.EmployeeRegistryProfile,self.employee.id)

    def tearDown(self):
        self.db.close();self.engine.dispose()

    def save(self,**kwargs):
        values=dict(employee_id=self.employee.id,account_id=self.account.id,version=self.profile.version,name='RF1 Corrected',code='RF1',status='active')
        values.update(kwargs);return svc.save(self.db,**values)

    def test_initialization_is_idempotent_and_discovers_stubs(self):
        svc.initialize(self.db);svc.initialize(self.db)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.EmployeeRegistryProfile)),1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.EmployeeRegistryChange)),1)
        obj,new=_get_or_create(self.db,m.Employee,{'source_system_id':self.employee.source_system_id,'source_employee_id':'new-stub'},
            {'display_name':None,'location_id':self.location.id})
        self.assertTrue(new);self.assertTrue(self.db.get(m.EmployeeRegistryProfile,obj.id).needs_review)

    def test_corrections_survive_both_import_paths_and_sparse_references(self):
        self.save();self.assertFalse(self.profile.needs_review)
        for method in (upsert,lambda *a:_get_or_create(*a)[0]):
            method(self.db,m.Employee,{'source_system_id':self.employee.source_system_id,'source_employee_id':'synthetic-employee'},
                {'display_name':'New Clover Name','custom_id':'B','active':None})
            self.assertEqual(self.employee.display_name,'RF1 Corrected');self.assertEqual(self.employee.custom_id,'RF1');self.assertTrue(self.employee.active)
        self.assertEqual(self.profile.source_name,'New Clover Name');self.assertTrue(self.profile.needs_review)
        upsert(self.db,m.Employee,{'source_system_id':self.employee.source_system_id,'source_employee_id':'synthetic-employee'},{'display_name':None})
        self.assertEqual(self.profile.source_name,'New Clover Name')

    def test_temporal_roles_preserve_history_and_stale_edits_fail(self):
        start=datetime(2026,10,1,tzinfo=timezone.utc);change=start+timedelta(days=10)
        old=m.EmployeeAssignment(employee_id=self.employee.id,restaurant_id=self.restaurant.id,operational_area_id=self.area.id,
            restaurant_role_id=self.host.id,location_id=self.location.id,valid_from=start,assignment_source='IMPORT')
        self.db.add(old);self.db.flush();version=self.profile.version
        self.save(role_id=self.server.id,area_id=self.area.id,restaurant_id=self.restaurant.id,effective_at=change)
        self.assertEqual(svc.aware(old.valid_to),change);self.assertTrue(self.profile.protect_roles)
        self.assertEqual(len(svc.assignments(self.db,self.employee.id)),2)
        with self.assertRaises(svc.RegistryError):self.save(version=version)
        with self.assertRaises(svc.RegistryError):self.save(role_id=self.host.id,area_id=self.area.id,restaurant_id=self.restaurant.id,effective_at=start)

    def test_role_observations_flag_drift_without_changing_assignments(self):
        svc.observe_roles(self.db,self.employee.id,['Host']);self.save()
        svc.observe_roles(self.db,self.employee.id,['Server'])
        self.assertTrue(self.profile.needs_review);self.assertEqual(self.profile.source_roles_signature,'Server')
        svc.observe_roles(self.db,self.employee.id,[])
        self.assertEqual(self.profile.source_roles_signature,'')

    def test_http_authorization_csrf_render_and_save(self):
        import auth
        from employee_registry_routes import register_employee_registry_routes
        auth.SessionFactory=self.Factory
        self.db.commit()
        app=Flask(__name__,template_folder=str(Path(__file__).resolve().parents[1]/'RF-One Web/templates'),static_folder=str(Path(__file__).resolve().parents[1]/'RF-One Web/static'))
        app.secret_key='synthetic-test-only';app.config['TESTING']=True
        app.jinja_env.globals.update(csrf_token=auth.get_csrf_token,brand_logo_filename=None)
        app.jinja_env.filters['local_dt']=display_format.local_datetime
        app.add_url_rule('/',endpoint='home',view_func=lambda:'home')
        app.add_url_rule('/login',endpoint='login',view_func=lambda:'login')
        register_employee_registry_routes(app,SessionFactory=self.Factory,require_admin=auth.require_admin,require_csrf=auth.require_csrf,current_account_id=auth.current_account_id)
        c=app.test_client();self.assertEqual(c.get('/employees').status_code,302)
        with c.session_transaction() as s:
            s[auth.SESSION_ACCOUNT_KEY]=self.account.id;s[auth.SESSION_VERSION_KEY]=1;s[auth.SESSION_CSRF_KEY]='test-token'
        self.assertEqual(c.get('/employees').status_code,200)
        self.assertEqual(c.get(f'/employees/{self.employee.id}').status_code,200)
        self.assertEqual(c.post('/employees/initialize').status_code,400)
        self.assertEqual(c.post('/employees/initialize',data={'csrf_token':'test-token'}).status_code,302)
        result=c.post(f'/employees/{self.employee.id}',data={'csrf_token':'test-token','version':self.profile.version,'name':'Reviewed Person','code':'T','status':'active'})
        self.assertEqual(result.status_code,302)
        with self.Factory() as d:self.assertEqual(d.get(m.Employee,self.employee.id).display_name,'Reviewed Person')
        with self.Factory() as d:d.get(m.RFOneAccount,self.account.id).is_admin=False;d.commit()
        self.assertEqual(c.get('/employees').status_code,403)

    def test_dst_invalid_and_ambiguous_times_are_rejected(self):
        from employee_registry_routes import parse_local
        for raw in ('2026-11-01T01:30','2026-03-08T02:30'):
            with self.assertRaises(svc.RegistryError):parse_local(raw,'America/New_York')
        self.assertEqual(parse_local('2026-10-21T12:00','America/New_York').hour,12)

    def test_incomplete_source_role_catalog_does_not_erase_last_observation(self):
        from types import SimpleNamespace
        from rfone_data_store.technical.connectors.clover import ingest
        svc.observe_roles(self.db,self.employee.id,['Host'])
        bundle=SimpleNamespace(employees_expand_role=[{'id':'synthetic-employee','roles':{'elements':[{'id':'unknown-role'}]}}])
        ingest.ingest_employee_source_roles(self.db,bundle,self.employee.source_system_id,
            {'synthetic-employee':self.employee.id},{},svc.now(),ingest.IngestionStats())
        self.assertEqual(self.profile.source_roles_signature,'Host')

    def test_profile_bootstrap_keeps_reviewed_role(self):
        from rfone_data_store.profile.bootstrap import bootstrap_restaurant_profile,MODE_PERSIST
        start=datetime(2026,10,1,tzinfo=timezone.utc)
        self.save(role_id=self.host.id,area_id=self.area.id,restaurant_id=self.restaurant.id,effective_at=start)
        source_role=m.SourceRole(source_system_id=self.employee.source_system_id,source_role_id='source-server',location_id=self.location.id,name='Server')
        self.db.add(source_role);self.db.flush()
        self.db.add(m.EmployeeSourceRole(employee_id=self.employee.id,source_role_id=source_role.id,source_system_id=self.employee.source_system_id,observed_at=start))
        self.db.flush()
        bootstrap_restaurant_profile(self.db,restaurant_id=self.restaurant.id,source_system_id=self.employee.source_system_id,
            mode=MODE_PERSIST,sync_time=start+timedelta(days=10))
        current=[a for a in svc.assignments(self.db,self.employee.id) if a.valid_to is None]
        self.assertEqual(len(current),1);self.assertEqual(current[0].restaurant_role_id,self.host.id)

if __name__=='__main__':unittest.main(verbosity=2)
