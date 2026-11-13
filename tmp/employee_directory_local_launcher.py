"""Isolated local launcher. Kept outside the byte-verified AWS source tree."""
from pathlib import Path
import json, os, secrets, socket, sys

ROOT=Path(__file__).resolve().parent
state=json.loads((ROOT/'verification.json').read_text(encoding='utf-8'))
db=state['local_database']
assert db['host']=='127.0.0.1'
assert db['database']=='rfone_employee_directory'
for key in list(os.environ):
    if key.startswith(('AWS_','CLOVER_','RFONE_','PG')):
        os.environ.pop(key,None)
os.environ.update(
    RFONE_DATABASE_URL=f"postgresql+psycopg2://{db['username']}@127.0.0.1:{db['port']}/{db['database']}",
    RFONE_FLASK_SECRET_KEY=(ROOT/'local-session.key').read_text(encoding='utf-8').strip(),
    AWS_EC2_METADATA_DISABLED='true', AWS_CONFIG_FILE=str(ROOT/'disabled-aws-config'),
    AWS_SHARED_CREDENTIALS_FILE=str(ROOT/'disabled-aws-credentials'),
    RFONE_AI_PROVIDER='DISABLED', RFONE_CLOVER_JOB_LAUNCHER='disabled',
    RFONE_PUBLIC_BASE_URL=f"http://127.0.0.1:{state['web_port']}",
    HTTP_PROXY='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9',
    NO_PROXY='localhost,127.0.0.1,::1',
)

# Outbound protection supplements removing all cloud credentials/configuration.
original_connect=socket.socket.connect
original_connect_ex=socket.socket.connect_ex
def local_address(address):
    return isinstance(address,tuple) and str(address[0]) in ('127.0.0.1','localhost','::1')
def connect(sock,address):
    if not local_address(address):raise RuntimeError('AWS/Clover/external network disabled in this local copy')
    return original_connect(sock,address)
def connect_ex(sock,address):
    if not local_address(address):raise RuntimeError('External network disabled in this local copy')
    return original_connect_ex(sock,address)
socket.socket.connect=connect
socket.socket.connect_ex=connect_ex
import boto3
def no_aws(*args,**kwargs):raise RuntimeError('AWS operations disabled in this local copy')
boto3.session.Session.client=no_aws
boto3.session.Session.resource=no_aws

source=ROOT/'source'
sys.path.insert(0,str(source/'RF-One Web'))
sys.path.insert(0,str(source/'RF-One Data Store'))
os.chdir(source/'RF-One Web')
import app as web
web.clover_job_launcher=no_aws
from flask import request, abort, session as browser_session, redirect
from sqlalchemy import select, text
from db import SessionFactory
from rfone_data_store import models as m
def local_copy_scope():
    permitted_hosts={f'127.0.0.1:{state["web_port"]}',f'localhost:{state["web_port"]}'}
    if request.remote_addr not in ('127.0.0.1','::1') or request.host not in permitted_hosts:
        abort(403)
    allowed=('/', '/login', '/logout', '/profile', '/favicon.ico')
    prefixes=('/administration/employees','/admin/accounts','/static/','/shared-brand/')
    if not (request.path in allowed or request.path.startswith(prefixes)):
        abort(403,description='This isolated copy serves Employee Directory and RF1 accounts only.')
    if request.method!='GET' and any(word in request.path.lower() for word in ('sync','clover','acquisition')):
        abort(403,description='Cloud and POS synchronization is disabled in this local copy.')
    with SessionFactory() as database:
        account=database.scalar(select(m.RFOneAccount).where(
            m.RFOneAccount.status=='ACTIVE',m.RFOneAccount.is_owner.is_(True)))
        if account is None:
            account=database.scalar(select(m.RFOneAccount).join(m.RFOneAccountDomainAccess,
                m.RFOneAccountDomainAccess.account_id==m.RFOneAccount.id).where(
                    m.RFOneAccount.status=='ACTIVE',m.RFOneAccount.is_admin.is_(True),
                    m.RFOneAccountDomainAccess.domain_code=='EMPLOYEES',
                    m.RFOneAccountDomainAccess.enabled.is_(True)))
        assert account is not None,'An active local administrator is required'
        if not browser_session.get('local_direct_access'):
            browser_session.pop('_flashes',None)
        browser_session['local_direct_access']=True
        browser_session['rfone_account_id']=account.id
        browser_session['rfone_session_version']=account.session_version
    if request.path in ('/login','/logout'):
        return redirect('/administration/employees')
web.app.before_request_funcs.setdefault(None,[]).insert(0,local_copy_scope)

if '--check' in sys.argv:
    with SessionFactory() as session:
        revision=session.scalar(text('select version_num from alembic_version'))
        account=session.scalar(select(m.RFOneAccount).join(m.RFOneAccountDomainAccess,
            m.RFOneAccountDomainAccess.account_id==m.RFOneAccount.id).where(
                m.RFOneAccount.status=='ACTIVE',m.RFOneAccountDomainAccess.domain_code=='EMPLOYEES',
                m.RFOneAccountDomainAccess.enabled.is_(True)).order_by(m.RFOneAccount.is_admin.desc()))
        assert account is not None,'No active copied account has Employee Directory access'
        account_id,version=account.id,account.session_version
        employee_id=session.scalar(select(m.Employee.id).order_by(m.Employee.id))
    web.app.config['TESTING']=True
    client=web.app.test_client()
    base=f'http://127.0.0.1:{state["web_port"]}'
    anonymous=client.get('/administration/employees',base_url=base)
    assert anonymous.status_code==200
    assert 'class="local-env' not in anonymous.get_data(as_text=True)
    paths=['/','/administration/employees']
    if employee_id is not None:paths.append(f'/administration/employees/{employee_id}')
    results={path:client.get(path,base_url=base).status_code for path in paths}
    assert all(code==200 for code in results.values()),results
    try:
        no_aws()
    except RuntimeError:blocked=True
    else:blocked=False
    assert blocked
    assert client.get('/administration/employees',base_url='http://invalid.example').status_code==403
    print(json.dumps({'schema_revision':revision,'direct_directory':200,'login_required':False,'pages':results,
                      'environment_banner':False,'external_integrations_disabled':True,'local_database_only':True}))
else:
    web.app.run(host='127.0.0.1',port=state['web_port'],debug=False,use_reloader=False)
