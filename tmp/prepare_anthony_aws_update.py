from pathlib import Path
script='''import os,sys,json
sys.path.insert(0,'/app/RF-One Data Store')
from sqlalchemy import select,func
from rfone_data_store.database import create_configured_engine,create_session_factory
from rfone_data_store import models as m,rfone_account_service as accounts,access_profiles as profiles,employee_directory as directory
engine=create_configured_engine(os.environ['RFONE_DATABASE_URL']);factory=create_session_factory(engine)
with factory() as db:
 account=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username=='anthony').with_for_update())
 assert account and account.status=='ACTIVE' and not account.is_owner and not account.is_admin
 assert directory.context_person_id(db,'RFONE_ACCOUNT',account.id) is None,'Identity association changed; no automatic reassociation'
 assert not profiles.company_ids_for_account(db,account.id),'Company memberships changed; preserve newer assignments'
 rows=accounts.list_direct_domain_access_for_account(db,account.id)
 before=[{'domain':r.domain_code,'enabled':r.enabled,'scope':r.scope,'role':r.role_code,'items':list(db.scalars(select(m.RFOneAccountDomainItemAccess.item_code).where(m.RFOneAccountDomainItemAccess.account_id==account.id,m.RFOneAccountDomainItemAccess.domain_code==r.domain_code)))} for r in rows]
 enabled={r.domain_code for r in rows if r.enabled}
 expected={'BANK','CLOVER_ACQUISITION','COMPENSATION','ORGANIZATION','PROJECTS','SELECTION','TIPS','TRAINING','WINES'}
 if enabled=={'KITCHEN'}:
  changed=False
 else:
  assert enabled==expected,'Permissions changed concurrently; refusing to overwrite'
  for r in rows:
   if r.domain_code!='KITCHEN':r.enabled=False
  accounts.set_domain_access(db,account_id=account.id,domain_code='KITCHEN',enabled=True,role_code=None,scope='ALL')
  owner=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.is_owner.is_(True),m.RFOneAccount.status=='ACTIVE'))
  assert owner
  profiles.event(db,'PERSONAL_PERMISSIONS_UPDATED',owner.id,account_id=account.id,username='anthony',reason='Product Owner: only Kitchen; deploy of locally verified correction',before=before,after=['KITCHEN'])
  db.flush();assert set(profiles.effective_permissions(db,account.id,company_id=None))=={'KITCHEN'}
  db.commit();changed=True
 print('REGISTRY_ANTHONY_UPDATE '+json.dumps({'account_id':account.id,'username':account.username,'changed':changed,'before':before,'effective_after':['KITCHEN'],'identities_merged':False}),flush=True)
'''
Path('tmp/registry-access-release/anthony_aws_update.py').write_text(script,encoding='utf-8',newline='\n')
