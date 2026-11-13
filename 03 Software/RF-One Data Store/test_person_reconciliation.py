"""Canonical person reconciliation on populated disposable databases only."""
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sqlalchemy import select,func
from rfone_data_store import models as m,people_registry as people,student_registry as students,person_reconciliation as rec
from rfone_data_store.database import create_configured_engine,create_session_factory
from rfone_data_store.training import service as training,workspace

class ReconciliationTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.engine=create_configured_engine('sqlite:///'+str(Path(self.tmp.name)/'fixture.db'));m.Base.metadata.create_all(self.engine);self.factory=create_session_factory(self.engine)
  with self.factory() as db:
   admin=m.RFOneAccount(username='owner',display_name='Owner',status='ACTIVE',password_hash='!',is_admin=True,is_owner=True,session_version=1)
   employee=m.Employee(display_name='Alice Martini',email='alice@example.invalid',active=True)
   account=m.RFOneAccount(username='alice',display_name='Alice Martini',email='alice@example.invalid',status='ACTIVE',password_hash='unchanged',is_admin=False,is_owner=False,session_version=3)
   actor=m.ActingIdentity(display_name='Alice Martini',kind='HUMAN_USER');db.add_all([admin,employee,account,actor]);db.flush()
   ta=m.TrainingAccount(username='old-alice',role='student',acting_identity_id=actor.id,password_hash='old-hash');db.add(ta);db.flush()
   db.add_all([m.RFOneTrainingIdentityLink(rfone_account_id=account.id,training_account_id=ta.id),m.EmployeeContextLink(employee_id=employee.id,rfone_account_id=account.id),workspace.TrainingStudentProfile(training_account_id=ta.id,employee_id=employee.id,phone='legacy-phone',must_change_password=False),m.RFOneAccountDomainAccess(account_id=account.id,domain_code='TRAINING',enabled=True,role_code='student',scope='ALL')]);db.commit()
   self.admin,self.employee,self.account,self.training=admin.id,employee.id,account.id,ta.id
 def tearDown(self):self.engine.dispose();self.tmp.cleanup()
 def group(self,db):return rec.IdentityGraph(db).by_node[('employee',self.employee)]
 def person(self,db,name='Alice Martini'):
  p=people.create_person(db,db.get(m.RFOneAccount,self.admin),name,'alice@example.invalid');db.flush();return p
 def confirm(self,db,**kwargs):
  g=self.group(db);return rec.reconcile(db,db.get(m.RFOneAccount,self.admin),key=g['key'],fingerprint=g['fingerprint'],**kwargs)
 def test_audit_is_readonly_and_name_email_are_never_identity_decisions(self):
  with self.factory() as db:
   p=self.person(db);db.commit();report=rec.audit(db)
   self.assertEqual(self.group(db)['state'],'unlinked');self.assertTrue(any(s['id']==p.id for r in report['groups'] if r['key']==self.group(db)['key'] for s in r['suggestions']))
   self.assertEqual(db.scalar(select(func.count()).select_from(people.PersonAccountLink)),0);self.assertFalse(db.new)
 def test_confirmation_unifies_all_existing_links_without_credentials_grants_or_history_changes(self):
  with self.factory() as db:
   p=self.person(db);pid=p.id;self.confirm(db,person_id=pid);db.commit()
   graph=rec.IdentityGraph(db)
   for kind,key in [('employee',self.employee),('account',self.account),('training',self.training)]:self.assertEqual(graph.person_id(kind,key),pid)
   self.assertEqual(db.get(m.RFOneAccount,self.account).password_hash,'unchanged');self.assertEqual(db.get(m.RFOneAccount,self.account).session_version,3)
   self.assertEqual(db.get(m.TrainingAccount,self.training).password_hash,'old-hash');self.assertEqual(db.get(workspace.TrainingStudentProfile,self.training).phone,'legacy-phone')
   grant=db.scalar(select(m.RFOneAccountDomainAccess).where(m.RFOneAccountDomainAccess.account_id==self.account));self.assertTrue(grant.enabled);self.assertEqual(grant.role_code,'student')
   self.assertEqual(workspace.roster(db)[0]['central_person_id'],pid)
   self.assertEqual(workspace.roster(db)[0]['central_person_name'],'Alice Martini')
   self.assertEqual(workspace.roster(db)[0]['name'],'Alice Martini')
   self.confirm(db,person_id=pid);db.commit();self.assertEqual(db.scalar(select(func.count()).select_from(students.TrainingPersonLink)),1)
 def test_explicit_new_person_never_creates_employee_or_account(self):
  with self.factory() as db:
   counts=[db.scalar(select(func.count()).select_from(model)) for model in (m.Employee,m.RFOneAccount,m.TrainingAccount)]
   p=self.confirm(db,new_name='Alice confirmed');db.commit();self.assertEqual(p.full_name,'Alice confirmed')
   self.assertEqual(counts,[db.scalar(select(func.count()).select_from(model)) for model in (m.Employee,m.RFOneAccount,m.TrainingAccount)])
 def test_two_employee_records_can_link_to_one_person(self):
  with self.factory() as db:
   p=self.person(db);self.confirm(db,person_id=p.id);other=m.Employee(display_name='Martini Alice',active=True);db.add(other);db.flush();g=rec.IdentityGraph(db).by_node[('employee',other.id)]
   rec.reconcile(db,db.get(m.RFOneAccount,self.admin),key=g['key'],fingerprint=g['fingerprint'],person_id=p.id);db.commit()
   self.assertEqual(db.scalar(select(func.count()).select_from(people.PersonEmployeeLink)),2)
 def test_two_confirmed_people_in_legacy_chain_are_blocked(self):
  with self.factory() as db:
   p=self.person(db);q=self.person(db,'Other person');people.link_source(db,db.get(m.RFOneAccount,self.admin),p.id,'account',self.account);db.add(students.TrainingPersonLink(training_account_id=self.training,person_id=q.id));db.commit()
   self.assertTrue(self.group(db)['conflicts'])
   with self.assertRaises(ValueError):self.confirm(db,person_id=p.id)
   self.assertEqual(db.scalar(select(func.count()).select_from(rec.PersonReconciliationEvent)),0)
 def test_destination_other_account_is_blocked_atomically(self):
  with self.factory() as db:
   p=self.person(db);people.link_source(db,db.get(m.RFOneAccount,self.admin),p.id,'account',self.admin);db.commit()
   with self.assertRaises(ValueError):self.confirm(db,person_id=p.id)
   self.assertIsNone(db.get(people.PersonEmployeeLink,self.employee));self.assertIsNone(db.get(students.TrainingPersonLink,self.training))
 def test_stale_review_is_rejected(self):
  with self.factory() as db:
   g=self.group(db);db.get(m.Employee,self.employee).display_name='Changed';db.commit()
   with self.assertRaises(ValueError):rec.reconcile(db,db.get(m.RFOneAccount,self.admin),key=g['key'],fingerprint=g['fingerprint'],new_name='Alice')
   self.assertEqual(db.scalar(select(func.count()).select_from(m.CandidatePerson)),0)
 def test_nonadmin_is_rejected(self):
  with self.factory() as db:
   g=self.group(db)
   with self.assertRaises(PermissionError):rec.reconcile(db,db.get(m.RFOneAccount,self.account),key=g['key'],fingerprint=g['fingerprint'],new_name='Alice')
 def test_student_without_employment_remains_external(self):
  with self.factory() as db:
   actor=m.ActingIdentity(display_name='External learner',kind='HUMAN_USER');db.add(actor);db.flush();ta=m.TrainingAccount(username='learner',role='student',acting_identity_id=actor.id,password_hash='!');db.add(ta);db.flush();g=rec.IdentityGraph(db).by_node[('training',ta.id)]
   p=rec.reconcile(db,db.get(m.RFOneAccount,self.admin),key=g['key'],fingerprint=g['fingerprint'],new_name='External learner');db.commit();self.assertEqual(db.scalar(select(func.count()).select_from(people.PersonEmployeeLink)),0);self.assertIsNone(db.scalar(select(people.PersonAccountLink).where(people.PersonAccountLink.person_id==p.id)))

 def test_shared_writers_reject_conflicting_confirmed_bridges(self):
  with self.factory() as db:
   p=self.person(db);self.confirm(db,person_id=p.id);q=self.person(db,'Different person')
   with self.assertRaises(ValueError):people.link_source(db,db.get(m.RFOneAccount,self.admin),q.id,'employee',self.employee)
   with self.assertRaises(ValueError):students.attach(db,q,db.get(m.RFOneAccount,self.account),db.get(m.TrainingAccount,self.training))
   self.assertEqual(db.get(people.PersonAccountLink,self.account).person_id,p.id)
 def test_frozen_migration_preserves_populated_core_and_is_repeatable(self):
  import importlib.util
  from alembic.migration import MigrationContext
  from alembic.operations import Operations
  path=Path(__file__).resolve().parent/'migrations/versions/r1a120261112_person_reconciliation.py'
  spec=importlib.util.spec_from_file_location('identity_migration',path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
  with self.engine.begin() as connection:
   # Only newly added tables in this disposable fixture are recreated.
   for model in reversed(rec.TABLES):model.__table__.drop(connection)
   before=connection.execute(select(func.count()).select_from(m.RFOneAccount)).scalar()
   operations=Operations(MigrationContext.configure(connection))
   from unittest.mock import patch
   with patch.object(migration,'op',operations):migration.upgrade();migration.upgrade()
   self.assertEqual(connection.execute(select(func.count()).select_from(m.RFOneAccount)).scalar(),before)
   self.assertEqual(connection.execute(select(func.count()).select_from(rec.PersonReconciliationEvent)).scalar(),0)
   with self.assertRaises(RuntimeError):migration.downgrade()

if __name__=='__main__':unittest.main()
