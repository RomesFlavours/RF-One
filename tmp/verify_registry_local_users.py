from pathlib import Path
import requests,re,json,sys,os
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'tmp/git-anagrafica-release/03 Software'
sys.path[:0]=[str(source/'RF-One Data Store')]
from rfone_data_store.database import create_configured_engine,create_session_factory
from rfone_data_store import models as m,access_profiles as p
from rfone_data_store.web_access import training_account_for_rf1
from sqlalchemy import select,func
sys.path.insert(0,str(source/'RF-One Web'))
from domain_registry import DOMAINS_BY_CODE
copy=json.loads((ROOT/'tmp/copy_employee_directory_aws.json').read_text(encoding='utf-8'))
private=Path(copy['folder']);state=json.loads((private/'verification.json').read_text(encoding='utf-8'));db=state['local_database']
assert db['host']=='127.0.0.1'
engine=create_configured_engine(f"postgresql+psycopg2://{db['username']}@127.0.0.1:{db['port']}/{db['database']}");factory=create_session_factory(engine)
base='http://127.0.0.1:5094';checks=[];failures=[]
routes={'EMPLOYEES':'/administration/employees','TRAINING':'/training','TIPS':'/tips/','COMPENSATION':'/compensation','BANK':'/bank','WINES':'/restaurant/wines','PROJECTS':'/projects','ORGANIZATION':'/admin/organization','DEV_JOURNAL':'/services/development-journal','KITCHEN':'/kitchen/dashboard','SELECTION':'/selection/'}
# Resolve actual Journal URL from registered shared route source rather than guess.
text=(source/'RF-One Web/dev_journal_routes.py').read_text(encoding='utf-8')
match=re.search(r"@app\.route\([\"']([^\"']+)[\"']\).*?def dev_journal_list",text,re.S)
if '/development-journal' in text:routes['DEV_JOURNAL']='/services/development-journal'
with factory() as database:
 accounts=list(database.scalars(select(m.RFOneAccount).order_by(m.RFOneAccount.id)))
 identities=[(a.id,a.session_version,a.status,a.is_admin) for a in accounts]
 counts={'people':database.scalar(select(func.count()).select_from(m.Employee)),'dismissed':database.scalar(select(func.count()).select_from(m.Employee).where(m.Employee.active.is_(False)))}
for identity,version,status,admin in identities:
 c=requests.Session();c.trust_env=False
 first=c.get(base+'/local/users',timeout=20);token=re.search(r'name="csrf_token" value="([^"]+)"',first.text)[1]
 assert c.post(base+'/local/access-user',data={'account_id':identity,'csrf_token':token},allow_redirects=False,timeout=20).status_code==302
 with factory() as database:
  companies=p.company_ids_for_account(database,identity);company=min(companies) if companies else None
  grants=p.effective_permissions(database,identity,company_id=company)
  for domain,path in routes.items():
   if domain=='DEV_JOURNAL':continue # tested by full Registry synthetic gate matrix
   expected=domain in grants
   if domain=='TRAINING':
    token=p.company_context.set(company)
    try:expected=bool(training_account_for_rf1(database,database.get(m.RFOneAccount,identity)))
    finally:p.company_context.reset(token)
   item_grant=grants.get(domain)
   if item_grant and item_grant['scope']=='SELECTED':
    items=DOMAINS_BY_CODE[domain].items
    first=next((item for item in items if item.code in item_grant['items']),None)
    if first:path=(first.exact_paths or first.paths)[0]
   response=c.get(base+path,allow_redirects=False,timeout=30)
   actual=response.status_code
   passed=actual in ({200,302} if expected else {401,403,302}) and actual!=500
   if not expected and actual==302:
    from urllib.parse import urlsplit
    passed=urlsplit(response.headers.get('Location','')).path in ('/','/login','/local/users','/training/login','/kitchen/sign-in')
   row={'account_id':identity,'domain':domain,'expected_allowed':expected,'status':actual,'passed':passed}
   checks.append(row)
   if not passed:failures.append(row)
 # No login/signature page even after inactive selection; switching remains possible.
 response=c.get(base+'/local/users',timeout=20)
 assert response.status_code==200 and 'Switch user' in response.text
 assert 'class="local-env' not in response.text
result={'accounts_checked':len(identities),'checks':len(checks),'failures':failures,'counts':counts,'test_data_written':False}
(ROOT/'tmp/registry-local-real-user-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
assert not failures
