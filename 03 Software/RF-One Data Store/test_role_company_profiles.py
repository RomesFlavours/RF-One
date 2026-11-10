import sys,unittest
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import select,func
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'RF-One Data Store'))
from rfone_data_store import models as m,access_profiles as p,employee_directory as directory,rfone_account_service as accounts,rfone_web_session as auth
from rfone_data_store.database import create_configured_engine,create_session_factory

DOMAINS=[SimpleNamespace(code='BANK',items=[SimpleNamespace(code='import'),SimpleNamespace(code='review')]),
         SimpleNamespace(code='TRAINING',items=[]),SimpleNamespace(code='EMPLOYEES',items=[])]

class ProfilesTest(unittest.TestCase):
    def setUp(self):
        self.engine=create_configured_engine('sqlite:///:memory:');m.Base.metadata.create_all(self.engine)
        self.db=create_session_factory(self.engine)()
        self.person=m.Employee(display_name='Test person',active=True)
        self.user=m.RFOneAccount(username='test',display_name='Test',password_hash='!',status='ACTIVE',is_admin=False,is_owner=False)
        self.wp=p.CompanyContext(name='WP',kind='COMPANY');self.md=p.CompanyContext(name='MD',kind='COMPANY')
        self.db.add_all([self.person,self.user,self.wp,self.md]);self.db.flush()
        self.db.add(m.EmployeeContextLink(employee_id=self.person.id,rfone_account_id=self.user.id));self.db.flush()
        self.area=p.save_area(self.db,name='FOH');self.other_area=p.save_area(self.db,name='BOH')
        self.manager=p.save_role(self.db,name='Manager',area_ids=[self.area.id])
        self.server=p.save_role(self.db,name='Server',area_ids=[self.area.id,self.other_area.id])
        self.member=p.membership(self.db,'employee:'+str(self.person.id),self.wp.id)

    def tearDown(self):self.db.close();self.engine.dispose()
    def grant(self,role,domain='BANK',mode='selected',items=('import',),level=''):
        p.save_permissions(self.db,role.id,{domain:{'mode':mode,'items':list(items),'role':level}},DOMAINS)
    def assign(self,role=None,member=None,area=None):return p.assign_role(self.db,membership_id=(member or self.member).id,role_id=(role or self.manager).id,area_id=(area or self.area).id)
    def effective(self,company=None):return p.effective_permissions(self.db,self.user.id,company_id=(company or self.wp).id)

    def test_roles_unite_selected_items(self):
        self.grant(self.manager);self.grant(self.server,items=('review',));self.assign();self.assign(self.server)
        self.assertEqual(self.effective()['BANK']['items'],{'import','review'})
        self.assertEqual(self.db.scalar(select(func.count()).select_from(m.EmployeeAssignment)),0)

    def test_all_dominates_and_admin_wins(self):
        self.grant(self.manager,mode='all',items=(),level='admin');self.grant(self.server);self.assign();self.assign(self.server)
        value=self.effective()['BANK'];self.assertEqual((value['scope'],value['role_code']),('ALL','admin'))
        self.assertFalse(self.user.is_admin)

    def test_company_grants_do_not_cross(self):
        self.grant(self.manager);self.assign();other=p.membership(self.db,'employee:'+str(self.person.id),self.md.id)
        self.assertIn('BANK',self.effective());self.assertEqual(self.effective(self.md),{})
        self.assertEqual(p.effective_permissions(self.db,self.user.id,company_id=None),{})
        self.grant(self.server,items=('review',));self.assign(self.server,other)
        self.assertEqual(self.effective()['BANK']['items'],{'import'})
        self.assertEqual(self.effective(self.md)['BANK']['items'],{'review'})

    def test_shared_auth_consumes_profile_permissions(self):
        self.grant(self.manager);self.assign();token=p.company_context.set(self.wp.id)
        try:
            self.assertTrue(auth.account_may_use_domain_item(self.db,self.user,'BANK','import'))
            self.assertFalse(auth.account_may_use_domain_item(self.db,self.user,'BANK','review'))
            self.assertFalse(auth.account_is_domain_admin(self.db,self.user,'BANK'))
        finally:p.company_context.reset(token)

    def test_permission_edits_are_immediate_and_do_not_materialize_direct_grants(self):
        self.grant(self.manager);self.assign();self.assertIn('BANK',self.effective())
        p.save_permissions(self.db,self.manager.id,{},DOMAINS);self.assertEqual(self.effective(),{})
        self.assertEqual(list(self.db.scalars(select(m.RFOneAccountDomainAccess))),[])

    def test_archive_area_role_company_and_restore(self):
        self.grant(self.manager);self.assign()
        for kind,obj in [('role',self.manager),('area',self.area),('company',self.wp)]:
            p.set_archived(self.db,kind,obj.id,True);self.assertEqual(self.effective(),{})
            p.set_archived(self.db,kind,obj.id,False);self.assertIn('BANK',self.effective())

    def test_withdraw_membership_closes_roles_and_preserves_history(self):
        self.grant(self.manager);assignment=self.assign();p.withdraw(self.db,'membership',self.member.id)
        self.assertEqual(self.effective(),{});self.assertIsNotNone(assignment.valid_to)
        self.assertIsNotNone(self.db.get(p.CompanyMembership,self.member.id))

    def test_direct_grants_stay_additive_and_remain_unchanged(self):
        accounts.set_domain_access(self.db,account_id=self.user.id,domain_code='BANK',enabled=True,role_code=None,scope='SELECTED',item_codes=['review'])
        self.grant(self.manager);self.assign();self.assertEqual(self.effective()['BANK']['items'],{'import','review'})
        p.set_archived(self.db,'role',self.manager.id,True)
        self.assertEqual(self.effective()['BANK']['items'],{'review'})
        self.assertEqual(accounts.list_direct_domain_item_access_for_account(self.db,self.user.id),{'BANK':{'review'}})

    def test_external_account_and_group_need_no_employee(self):
        external=m.RFOneAccount(username='consultant',display_name='Consultant',password_hash='!',status='ACTIVE')
        group=p.CompanyContext(name='RFGroup',kind='GROUP');self.db.add_all([external,group]);self.db.flush()
        member=p.membership(self.db,'account:'+str(external.id),group.id);self.assertIsNone(member.employee_id)
        self.grant(self.manager);self.assign(member=member)
        self.assertIn('BANK',p.effective_permissions(self.db,external.id,company_id=group.id))
        self.assertEqual(p.effective_permissions(self.db,external.id,company_id=self.wp.id),{})

    def test_dismissed_person_rejected_and_no_longer_contributes(self):
        self.grant(self.manager);self.assign();self.person.active=False;self.db.flush()
        self.assertEqual(self.effective(),{})
        with self.assertRaises(ValueError):p.membership(self.db,'employee:'+str(self.person.id),self.md.id)
        with self.assertRaises(ValueError):self.assign(self.server)

    def test_invalid_permission_and_area_inputs_leave_previous_policy_intact(self):
        self.grant(self.manager)
        for value in [{'mode':'selected','items':[]},{'mode':'all','role':'owner'},{'mode':'selected','items':['hacked']}]:
            with self.assertRaises(ValueError):p.save_permissions(self.db,self.manager.id,{'BANK':value},DOMAINS)
        with self.assertRaises(ValueError):self.assign(area=self.other_area)
        p.set_archived(self.db,'area',self.area.id,True)
        with self.assertRaises(ValueError):self.assign()

    def test_training_precedence(self):
        self.grant(self.manager,'TRAINING','all',(),level='trainer');self.grant(self.server,'TRAINING','all',(),level='student')
        self.assign();self.assign(self.server);self.assertEqual(self.effective()['TRAINING']['role_code'],'trainer')

    def test_memberships_and_assignments_are_idempotent(self):
        same=p.membership(self.db,'account:'+str(self.user.id),self.wp.id);self.assertEqual(same.id,self.member.id)
        first=self.assign();second=self.assign();self.assertEqual(first.id,second.id)
        with self.assertRaises(ValueError):p.save_role(self.db,name='manager',area_ids=[self.area.id])

    def test_employee_directory_company_scope(self):
        token=p.company_context.set(self.wp.id)
        try:self.assertEqual(p.employee_scope_ids(self.db,self.user),{self.person.id})
        finally:p.company_context.reset(token)
        token=p.company_context.set(self.md.id)
        try:self.assertEqual(p.employee_scope_ids(self.db,self.user),set())
        finally:p.company_context.reset(token)

    def test_external_membership_follows_confirmed_person_without_a_duplicate(self):
        account=m.RFOneAccount(username='later-linked',display_name='External',password_hash='!',status='ACTIVE')
        person=m.Employee(display_name='Confirmed person',active=True);self.db.add_all([account,person]);self.db.flush()
        old=p.membership(self.db,'account:'+str(account.id),self.md.id)
        self.db.add(m.EmployeeContextLink(employee_id=person.id,rfone_account_id=account.id));self.db.flush()
        same=p.membership(self.db,'employee:'+str(person.id),self.md.id)
        self.assertEqual(old.id,same.id);self.assertEqual(same.employee_id,person.id);self.assertIsNone(same.account_id)

if __name__=='__main__':unittest.main()
