"""Isolated status persistence tests using the actual 5094 Registry service."""
import unittest
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from test_role_company_profiles import ProfilesTest, m, p

class PersonStatusTests(unittest.TestCase):
    setUp=ProfilesTest.setUp
    tearDown=ProfilesTest.tearDown

    def save(self,**extra):
        values=dict(name='Updated person',company_ids=[self.wp.id],assignments=[],email='updated@example.test',phone='12345',actor=None)
        values.update(extra)
        p.save_person_profile(self.db,f'employee:{self.person.id}',**values)

    def test_statuses_and_contacts_persist_without_grant_changes(self):
        before=self.db.scalar(select(func.count()).select_from(m.RFOneAccountDomainAccess))
        version=self.user.session_version
        self.save(company_statuses=['CANDIDATE','EMPLOYEE'],account_status='INACTIVE')
        self.db.expire_all()
        snapshot=p.profile_status_snapshot(self.db,f'employee:{self.person.id}')
        self.assertEqual(set(snapshot['company_statuses']),{'CANDIDATE','EMPLOYEE'})
        self.assertEqual(snapshot['account_status'],'INACTIVE')
        self.assertEqual(self.person.display_name,'Updated person')
        self.assertEqual(self.person.email,'updated@example.test')
        self.assertEqual(self.user.session_version,version+1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.RFOneAccountDomainAccess)),before)
        self.assertEqual(self.member.valid_to,None)
        self.save(company_statuses=['EXTERNAL','EMPLOYEE'],account_status='ACTIVE')
        self.assertEqual(set(p.profile_status_snapshot(self.db,f'employee:{self.person.id}')['company_statuses']),{'EXTERNAL','EMPLOYEE'})
        self.assertEqual(self.user.status,'ACTIVE')

    def test_legacy_call_preserves_status(self):
        self.save(company_statuses=['EXTERNAL'],account_status='INACTIVE')
        self.save(name='Legacy caller')
        self.assertEqual(p.profile_status_snapshot(self.db,f'employee:{self.person.id}')['company_statuses'],['EXTERNAL'])
        self.assertEqual(self.user.status,'INACTIVE')

    def test_invalid_values_and_owner_protection(self):
        for values in [dict(company_statuses=['ADMIN']),dict(account_status='DELETED'),dict(account_status='INACTIVE',actor=self.user.id)]:
            with self.assertRaises(ValueError):self.save(**values)
        self.user.is_admin=True;self.user.is_owner=True
        with self.assertRaises(ValueError):self.save(account_status='INACTIVE')
        self.assertEqual(self.user.status,'ACTIVE')

    def test_inactive_external_account_remains_editable(self):
        account=m.RFOneAccount(username='external',display_name='External',password_hash='!',status='INACTIVE',is_admin=False,is_owner=False)
        self.db.add(account);self.db.flush()
        p.save_person_profile(self.db,f'account:{account.id}',name='External updated',company_ids=[],assignments=[],company_statuses=['EXTERNAL'],account_status='ACTIVE')
        self.assertEqual(account.status,'ACTIVE')
        self.assertEqual(p.profile_status_snapshot(self.db,f'account:{account.id}')['company_statuses'],['EXTERNAL'])

    def test_create_uses_existing_identity_and_account_service(self):
        people=self.db.scalar(select(func.count()).select_from(m.Employee))
        person=p.create_profile_person(self.db,name='New candidate',company_ids=[],assignments=[],company_statuses=['CANDIDATE','EXTERNAL'],account_status='INACTIVE')
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.Employee)),people+1)
        snapshot=p.profile_status_snapshot(self.db,f'employee:{person.id}')
        self.assertEqual(snapshot['account_status'],'INACTIVE')
        self.assertEqual(set(snapshot['company_statuses']),{'CANDIDATE','EXTERNAL'})

    def test_error_rolls_back_all_changes(self):
        self.db.commit()
        try:
            self.save(company_statuses=['EMPLOYEE'],account_status='INACTIVE',assignments=[dict(company_id=999,role_id=1,area_id=1)])
        except ValueError:self.db.rollback()
        else:self.fail('Invalid assignment was accepted')
        self.assertEqual(self.user.status,'ACTIVE')
        self.assertEqual(self.person.display_name,'Test person')
        self.assertEqual(p.profile_status_snapshot(self.db,f'employee:{self.person.id}')['company_statuses'],[])

if __name__=='__main__':unittest.main(verbosity=2)
