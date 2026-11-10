"""Real standalone app grant/revoke checks on a disposable database.
Run separately for each service: python .../test_registry_standalone_access.py tips|selection|kitchen
"""
from pathlib import Path
import importlib.util, json, os, sys, tempfile
ROOT=Path(__file__).resolve().parents[2]
service=sys.argv[1]
temporary=tempfile.TemporaryDirectory(prefix="registry-standalone-",dir=ROOT.parent,ignore_cleanup_errors=True)
os.environ.update(RFONE_DATABASE_URL="sqlite:///"+str(Path(temporary.name)/"test.db").replace("\\","/"),
    RFONE_FLASK_SECRET_KEY="disposable-registry-check",RFONE_SELECTION_REQUIRE_RFONE_LOGIN="1",AWS_EC2_METADATA_DISABLED="true")
sys.path[:0]=[str(ROOT/"RF-One Data Store"),str(ROOT/"RF-One Web")]
from rfone_data_store import models as m,access_profiles as p,rfone_account_service as accounts
from rfone_data_store.database import create_configured_engine,create_session_factory
from rfone_data_store import kitchen, kitchen_configuration
engine=create_configured_engine(os.environ["RFONE_DATABASE_URL"]);m.Base.metadata.create_all(engine);factory=create_session_factory(engine)
with factory() as db:
    user=m.RFOneAccount(username="fixture",display_name="Fixture",password_hash="!",status="ACTIVE",is_admin=False,is_owner=False,session_version=1)
    wp=p.CompanyContext(name="WP",kind="COMPANY");md=p.CompanyContext(name="MD",kind="COMPANY")
    db.add_all([user,wp,md]);db.flush();uid,wpid,mdid=user.id,wp.id,md.id
    area=p.save_area(db,name="Operations");role=p.save_role(db,name="Fixture role",area_ids=[area.id])
    membership=p.membership(db,f"account:{uid}",wpid);p.membership(db,f"account:{uid}",mdid)
    assignment=p.assign_role(db,membership_id=membership.id,role_id=role.id,area_id=area.id);rid=role.id;db.commit()
folder=ROOT/({"tips":"Tips","selection":"Selection","kitchen":"RF-One Web"}[service])
sys.path.insert(0,str(folder))
filename="kitchen_cloud.py" if service=="kitchen" else "app.py"
spec=importlib.util.spec_from_file_location("standalone_"+service,folder/filename)
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
app=module.app;app.config["TESTING"]=True
c=app.test_client()
with c.session_transaction() as browser:browser["rfone_account_id"]=uid;browser["rfone_session_version"]=1;browser["rfone_company_context"]=wpid
paths={"tips":("/","/roles","/tips-configuration"),"selection":("/","/requirements"),"kitchen":("/kitchen/dashboard","/kitchen/recipes","/kitchen/configuration")}[service]
checks=[]
def expect(label,statuses):
    for path in paths:
        actual=c.get(path).status_code
        assert actual in statuses,(service,label,path,actual,statuses)
        checks.append(label+" "+path)
code=service.upper()
expect("No grant",{403})
with factory() as db:db.add(p.RolePermission(role_id=rid,domain_code=code,scope="ALL",role_code=None,items=[]));db.commit()
expect("Role grants access",{200,302})
with c.session_transaction() as browser:browser["rfone_company_context"]=mdid
expect("Other company denied",{403})
with c.session_transaction() as browser:browser["rfone_company_context"]=wpid
with factory() as db:
    grant=db.query(p.RolePermission).filter_by(role_id=rid,domain_code=code).one();db.delete(grant);db.commit()
expect("Role revoked existing session",{403})
with factory() as db:accounts.set_domain_access(db,account_id=uid,domain_code=code,enabled=True,role_code=None);db.commit()
expect("Personal grant",{200,302})
with factory() as db:accounts.set_domain_access(db,account_id=uid,domain_code=code,enabled=False,role_code=None);db.commit()
expect("Personal revoke existing session",{403})
with factory() as db:accounts.set_domain_access(db,account_id=uid,domain_code=code,enabled=True,role_code=None);db.get(m.RFOneAccount,uid).session_version=2;db.commit()
expect("Revoked session denied",{401,302})
with c.session_transaction() as browser:browser["rfone_session_version"]=2
with factory() as db:db.get(m.RFOneAccount,uid).status="INACTIVE";db.commit()
expect("Inactive account denied",{401,302})
if service == "tips":
    with factory() as db:
        db.get(m.RFOneAccount,uid).status="ACTIVE"
        from rfone_data_store.training import service as training
        identity=training.create_account(db,display_name="Fixture",username="training-fixture",password="Unused123!",role="trainer")
        db.add(m.RFOneTrainingIdentityLink(rfone_account_id=uid,training_account_id=identity.id))
        grant=p.RolePermission(role_id=rid,domain_code="TRAINING",scope="ALL",role_code="student",items=[])
        db.add(grant);db.commit();training_id=identity.id
    os.environ["RFONE_WEB_BASE_URL"]="http://localhost:5000"
    response=c.get('/training')
    assert response.status_code==302 and response.location=='http://localhost:5000/training'
    checks.append('Operational Training uses canonical RF1 entry')
    with factory() as db:
        db.delete(db.query(p.RolePermission).filter_by(role_id=rid,domain_code='TRAINING').one());db.commit()
    with c.session_transaction() as browser:browser['training_account_id']=training_id
    assert c.get('/training/trainer').status_code==403
    assert c.post('/training/login',data={'username':'training-fixture','password':'Unused123!'}).status_code==403
    checks.extend(['Revoked Training denies legacy session','Legacy Training password cannot bypass Registry'])
print(json.dumps({"service":service,"checks_passed":len(checks),"checks":checks}))
engine.dispose()

