from pathlib import Path
import os,sys,tempfile,importlib.util,json
root=Path.cwd();service=sys.argv[1];folder=Path(sys.argv[2]).resolve();base=folder/'03 Software' if (folder/'03 Software').exists() else folder
temp=tempfile.TemporaryDirectory(dir=root/'tmp',prefix='release-policy-',ignore_cleanup_errors=True);os.environ.update(RFONE_DATABASE_URL='sqlite:///'+str(Path(temp.name)/'db.sqlite').replace('\\','/'),RFONE_FLASK_SECRET_KEY='disposable-release-test',RFONE_SELECTION_REQUIRE_RFONE_LOGIN='1',RFONE_WEB_BASE_URL='http://localhost:5000',RFONE_PUBLIC_BASE_URL='http://localhost:5000',AWS_EC2_METADATA_DISABLED='true');sys.path[:0]=[str(base/'RF-One Data Store'),str(base/('Tips' if service=='tips' else 'Selection' if service=='selection' else 'RF-One Web'))]
from rfone_data_store import models as m,access_profiles as p,rfone_account_service as accounts
from rfone_data_store.database import create_configured_engine,create_session_factory
engine=create_configured_engine(os.environ['RFONE_DATABASE_URL'])
if service=='selection':
 from workspace import schema
m.Base.metadata.create_all(engine)
from sqlalchemy import text
with engine.begin() as conn:
 conn.execute(text('CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
 conn.execute(text("INSERT INTO alembic_version VALUES ('t9a120261110')"))
factory=create_session_factory(engine)
appfile=base/('Tips/app.py' if service=='tips' else 'Selection/app.py' if service=='selection' else 'RF-One Web/training_cloud.py' if service=='training' else 'RF-One Web/kitchen_cloud.py' if service=='kitchen' else 'RF-One Web/app.py')
spec=importlib.util.spec_from_file_location('release_'+service,appfile);module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);module.app.config['TESTING']=True;m.Base.metadata.create_all(engine)
with factory() as db:
 user=m.RFOneAccount(username='release-test',display_name='Release policy test',password_hash='!',status='ACTIVE',is_admin=False,is_owner=False,session_version=1);wp=p.CompanyContext(name='WP',kind='COMPANY');md=p.CompanyContext(name='MD',kind='COMPANY');db.add_all([user,wp,md]);db.flush();uid,wpid,mdid=user.id,wp.id,md.id
 area=p.save_area(db,name='Operations');role=p.save_role(db,name='Test role',area_ids=[area.id]);member=p.membership(db,f'account:{uid}',wpid);p.membership(db,f'account:{uid}',mdid);p.assign_role(db,membership_id=member.id,role_id=role.id,area_id=area.id);rid=role.id
 if service=='training':
  from rfone_data_store.training import service as training
  identity=training.create_account(db,display_name='Release policy test',username='release-test-training',password='Unused123!',role='student');db.add(m.RFOneTrainingIdentityLink(rfone_account_id=uid,training_account_id=identity.id));trainingid=identity.id
 db.commit()
c=module.app.test_client()
with c.session_transaction() as browser:browser['rfone_account_id']=uid;browser['rfone_session_version']=1;browser['rfone_company_context']=wpid
paths={'web':('/bank','/projects'), 'tips':('/','/roles'), 'selection':('/','/requirements'), 'kitchen':('/kitchen/dashboard',), 'training':('/training/manage/students','/training/manage/content')}[service];code={'web':'BANK'}.get(service,service.upper());checks=[]
def verify(label,expected):
 for path in paths:
  if service=='web' and path=='/projects':continue
  response=c.get(path,follow_redirects=False);assert response.status_code in expected,(service,label,path,response.status_code);checks.append(label+' '+path)
verify('No grant denied',{403,302})
with factory() as db:db.add(p.RolePermission(role_id=rid,domain_code=code,scope='ALL',role_code='trainer' if service=='training' else None,items=[]));db.commit()
verify('Company role opens',{200,302})
with c.session_transaction() as browser:browser['rfone_company_context']=mdid
verify('Other company denied',{403,302})
with c.session_transaction() as browser:browser['rfone_company_context']=wpid
with factory() as db:db.delete(db.query(p.RolePermission).filter_by(role_id=rid,domain_code=code).one());db.commit()
verify('Role revoked in open session',{403,302})
if service=='training':
 with factory() as db:
  assert db.get(m.TrainingAccount,trainingid).role=='student'
  db.add(p.RolePermission(role_id=rid,domain_code=code,scope='ALL',role_code='student',items=[]));db.commit()
 verify('Trainer downgrade denied',{403})
 assert c.get('/training').status_code==200
 checks.extend(['Stored Training identity role unchanged','Student page opens'])
if service=='selection':
 assert any(rule.endpoint.startswith('positions.') for rule in module.app.url_map.iter_rules())
 checks.append('Current Selection workspace preserved')
if service=='tips':
 assert c.get('/training/trainer').status_code==403
 checks.append('Legacy Training login cannot bypass Registry')
print(json.dumps({'service':service,'passed':len(checks),'checks':checks}));engine.dispose()
