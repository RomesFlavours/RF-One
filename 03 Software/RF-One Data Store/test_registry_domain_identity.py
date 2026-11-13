"""Isolated tests of the real 5094 services, with no external providers."""
from pathlib import Path
import sys,unittest
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import Session
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'RF-One Web'));sys.path.insert(0,str(ROOT/'RF-One Data Store'))
from rfone_data_store import models as m,access_profiles as profiles,registry_identity as registry,employee_directory as directory,student_registry
from rfone_data_store.selection import identity_service as selection
from rfone_data_store.training import service as training
import training_integration as integration

class RegistryDomainTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        m.Base.metadata.create_all(self.engine)
        self.db=Session(self.engine)
        self.owner=m.RFOneAccount(username='owner',display_name='Owner',password_hash='!',status='ACTIVE',is_admin=True,is_owner=True)
        self.db.add(self.owner);self.db.flush()
    def tearDown(self):self.db.close();self.engine.dispose()
    def count(self,model):return self.db.scalar(select(func.count()).select_from(model))
    def employee(self):
        return profiles.create_profile_person(self.db,name='Central Employee',email='central@example.test',company_ids=[],assignments=[],company_statuses=['EMPLOYEE'],account_status='ACTIVE',actor=self.owner.id)
    def enroll(self,person,**kwargs):
        return integration.create_student_via_rf_one(self.db,username='',display_name=person.display_name,email=person.email,password='',registry_person_id=person.id,actor_id=self.owner.id,**kwargs)

    def test_registry_employee_can_enroll_without_student_qualification(self):
        person=self.employee();account=profiles.profile_account(self.db,f'employee:{person.id}')
        password=account.password_hash;people=self.count(m.Employee)
        rf,learner=self.enroll(person)
        self.assertEqual(rf.id,account.id);self.assertEqual(rf.password_hash,password)
        self.assertEqual(directory.context_person_id(self.db,'TRAINING',learner.id),person.id)
        self.assertEqual(self.count(m.Employee),people)
        self.assertEqual(self.count(student_registry.PersonQualification),0)
        self.assertIn(learner.acting_identity_id,student_registry.operational_identity_ids(self.db))
        self.assertTrue(registry.training_eligible(self.db,person.id))
        self.assertEqual(integration.check_training_authorization(self.db,rf).training_account.id,learner.id)
        again=self.enroll(person)
        self.assertEqual(again[1].id,learner.id);self.assertEqual(self.count(m.TrainingAccount),1)
        self.assertEqual(self.count(student_registry.PersonQualification),0)
        pill=m.TrainingPill(slug='synthetic',title='Synthetic course',learning_objectives='Synthetic objective');self.db.add(pill);self.db.flush()
        need=training.create_need(self.db,student_account_id=learner.id,text='Synthetic learning',origin=None,created_by_account_id=learner.id)
        assignment=training.assign_pill(self.db,need_id=need.id,pill_id=pill.id,assigned_by_account_id=learner.id)
        self.assertEqual(assignment.need.student_account_id,learner.id)

    def test_selection_and_training_reuse_manual_registry_person(self):
        employee=self.employee();people=self.count(m.Employee)
        candidate,new=selection.resolve_or_create_person(self.db,restaurant_id=None,full_name=employee.display_name,email=employee.email,phone=None)
        self.assertTrue(new)
        self.assertEqual(directory.context_person_id(self.db,'CANDIDATE',candidate.id),employee.id)
        same,new=selection.resolve_or_create_person(self.db,restaurant_id=None,full_name=employee.display_name,email=employee.email,phone=None)
        self.assertFalse(new);self.assertEqual(candidate.id,same.id)
        rf,learner=self.enroll(employee)
        self.assertEqual(directory.context_person_id(self.db,'RFONE_ACCOUNT',rf.id),employee.id)
        self.assertEqual(self.count(m.Employee),people);self.assertEqual(self.count(m.CandidatePerson),1)

    def test_selection_first_then_training_creates_one_central_person(self):
        candidate,new=selection.resolve_or_create_person(self.db,restaurant_id=None,full_name='New Candidate',email='new@example.test',phone=None)
        employee_id=directory.context_person_id(self.db,'CANDIDATE',candidate.id)
        self.assertIsNotNone(employee_id)
        rf,learner=integration.create_student_via_rf_one(self.db,username='newcandidate',display_name='New Candidate',email='new@example.test',password='Example-pass-123',actor_id=self.owner.id)
        self.assertEqual(directory.context_person_id(self.db,'TRAINING',learner.id),employee_id)
        self.assertEqual(self.count(m.Employee),1)

    def test_manual_registry_reuses_legacy_selection_facet(self):
        candidate=m.CandidatePerson(full_name='Legacy Candidate',primary_email='legacy@example.test')
        self.db.add(candidate);self.db.flush()
        employee=profiles.create_profile_person(self.db,name='Legacy Candidate',email='legacy@example.test',company_ids=[],assignments=[],actor=self.owner.id)
        self.assertEqual(self.count(m.CandidatePerson),1)
        self.assertEqual(directory.context_person_id(self.db,'CANDIDATE',candidate.id),employee.id)
        with self.assertRaises(registry.IdentityReviewRequired):
            profiles.create_profile_person(self.db,name='Legacy Candidate',email='legacy@example.test',company_ids=[],assignments=[],actor=self.owner.id)
        self.assertEqual(self.count(m.Employee),1)

    def test_ambiguous_contacts_do_not_merge_or_create_people(self):
        for name in ['First person','Second person']:
            directory.create_person(self.db,display_name=name,email='shared@example.test',account_id=self.owner.id)
        before=self.count(m.Employee)
        with self.assertRaises(registry.IdentityReviewRequired):
            registry.resolve_person(self.db,name='Shared Contact',email='shared@example.test')
        self.assertEqual(self.count(m.Employee),before)
        self.assertEqual(self.count(m.EmployeeContextLink),0)

    def test_another_restaurant_application_reuses_the_same_person_facet(self):
        employee=self.employee()
        first=m.Restaurant(name='First site');second=m.Restaurant(name='Second site')
        self.db.add_all([first,second]);self.db.flush()
        candidate,new=selection.resolve_or_create_person(self.db,restaurant_id=first.id,full_name=employee.display_name,email=employee.email,phone=None)
        again,new=selection.resolve_or_create_person(self.db,restaurant_id=second.id,full_name=employee.display_name,email=employee.email,phone=None)
        self.assertFalse(new);self.assertEqual(again.id,candidate.id)
        self.assertEqual(self.count(m.Employee),1);self.assertEqual(self.count(m.CandidatePerson),1)

    def test_historically_confirmed_registry_bridges_are_read_without_backfill(self):
        from rfone_data_store import people_registry as links
        employee=self.employee()
        candidate=m.CandidatePerson(full_name=employee.display_name,primary_email=employee.email)
        self.db.add(candidate);self.db.flush()
        links.link_source(self.db,self.owner,candidate.id,'employee',employee.id)
        learner=training.create_account(self.db,display_name=employee.display_name,username='legacy-learning',password='unused',role='student')
        self.db.add(student_registry.TrainingPersonLink(training_account_id=learner.id,person_id=candidate.id));self.db.flush()
        before=self.count(m.EmployeeContextLink)
        self.assertEqual(directory.context_person_id(self.db,'TRAINING',learner.id),employee.id)
        self.assertEqual(directory.context_person_id(self.db,'CANDIDATE',candidate.id),employee.id)
        self.assertEqual(self.count(m.EmployeeContextLink),before)
        self.assertEqual(registry.candidate_for_person(self.db,employee.id).id,candidate.id)
        self.assertEqual(self.count(student_registry.PersonQualification),0)

    def test_legacy_training_adapter_reuses_registry_without_student_tag(self):
        employee=self.employee();rf,learner=self.enroll(employee)
        facet,account=student_registry.resolve(self.db,name=employee.display_name,email=employee.email,username=rf.username,confirmation=f'account:{rf.id}')
        student_registry.attach(self.db,facet,account,learner)
        self.assertEqual(directory.context_person_id(self.db,'CANDIDATE',facet.id),employee.id)
        self.assertEqual(self.count(m.Employee),1);self.assertEqual(self.count(m.TrainingAccount),1)
        self.assertEqual(self.count(student_registry.PersonQualification),0)

    def test_account_only_registry_qualifications_survive_central_linking(self):
        account=m.RFOneAccount(username='external-person',display_name='External Person',email='external-person@example.test',password_hash='!',status='ACTIVE',is_admin=False,is_owner=False)
        self.db.add(account);self.db.flush()
        profiles.save_company_statuses(self.db,f'account:{account.id}',['EXTERNAL','EMPLOYEE'],self.owner.id)
        rf,learner=integration.create_student_via_rf_one(self.db,username=account.username,display_name=account.display_name,email=account.email,password='',actor_id=self.owner.id)
        person_id=directory.context_person_id(self.db,'TRAINING',learner.id)
        self.assertIsNotNone(person_id);self.assertEqual(rf.id,account.id)
        self.assertEqual(set(profiles.profile_status_snapshot(self.db,f'employee:{person_id}')['company_statuses']),{'EXTERNAL','EMPLOYEE'})
        self.assertEqual(self.count(m.Employee),1);self.assertEqual(self.count(student_registry.PersonQualification),0)

    def test_name_only_match_requires_explicit_registry_selection(self):
        employee=self.employee()
        with self.assertRaises(registry.IdentityReviewRequired):
            registry.resolve_person(self.db,name=employee.display_name,email='other@example.test')
        confirmed=registry.resolve_person(self.db,name=employee.display_name,employee_id=employee.id)
        self.assertEqual(confirmed.id,employee.id);self.assertEqual(self.count(m.Employee),1)

    def test_inactive_account_and_existing_permissions_are_preserved(self):
        person=self.employee();rf=profiles.profile_account(self.db,f'employee:{person.id}')
        rf.status='INACTIVE';self.db.flush()
        with self.assertRaises(ValueError):self.enroll(person)
        self.assertEqual(self.count(m.TrainingAccount),0)
        rf.status='ACTIVE'
        self.db.add(m.RFOneAccountDomainAccess(account_id=rf.id,domain_code='BANK',enabled=True,role_code='view'));self.db.flush()
        self.enroll(person)
        grant=self.db.scalar(select(m.RFOneAccountDomainAccess).where(m.RFOneAccountDomainAccess.account_id==rf.id,m.RFOneAccountDomainAccess.domain_code=='BANK'))
        self.assertTrue(grant.enabled);self.assertEqual(grant.role_code,'view')
        self.assertFalse(rf.is_admin)

if __name__=='__main__':unittest.main(verbosity=2)
