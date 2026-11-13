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
    RFONE_UI_LANGUAGE='it', RFONE_AI_PROVIDER='DISABLED', RFONE_CLOVER_JOB_LAUNCHER='disabled',
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

source=Path(state.get('development_source',str(ROOT/'source')))
sys.path.insert(0,str(source/'RF-One Web'))
sys.path.insert(0,str(source/'RF-One Data Store'))
os.chdir(source/'RF-One Web')
import app as web
web.clover_job_launcher=no_aws
web.app.config['RFONE_LOCAL_OFFLINE']=True

from flask import request, abort, session as browser_session, redirect, render_template_string
from sqlalchemy import select
from db import SessionFactory
from rfone_data_store import models as m, rfone_web_session as shared
from html import escape
from flask import g
from itsdangerous import URLSafeSerializer, BadSignature
local_signer=URLSafeSerializer(web.app.secret_key,salt='loopback-user-selection')
LOCAL_CHOICE_COOKIE='rfone_local_user_choice'
import importlib.util
os.environ['RFONE_SELECTION_REQUIRE_RFONE_LOGIN']='1'
os.environ['RFONE_WEB_BASE_URL']=os.environ['RFONE_PUBLIC_BASE_URL']

def load_app(name, folder, filename='app.py', isolate=False):
    names=('auth','db','routes','dish_data')
    saved={key:sys.modules.get(key) for key in names}
    old_path=sys.path[:]
    if isolate:
        for key in names:sys.modules.pop(key,None)
    sys.path.insert(0,str(folder))
    try:
        spec=importlib.util.spec_from_file_location(name,folder/filename)
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
        return module.app
    finally:
        sys.path[:]=old_path
        if isolate:
            for key,value in saved.items():
                if value is None:sys.modules.pop(key,None)
                else:sys.modules[key]=value

tips=load_app('rfone_local_tips',source/'Tips',isolate=True)
selection=load_app('rfone_local_selection',source/'Selection',isolate=True)
kitchen=load_app('rfone_local_kitchen',source/'RF-One Web','kitchen_cloud.py')
apps=[web.app,tips,selection,kitchen]


def local_copy_scope():
    permitted_hosts={f'127.0.0.1:{state["web_port"]}',f'localhost:{state["web_port"]}'}
    if request.remote_addr not in ('127.0.0.1','::1') or request.host not in permitted_hosts:
        abort(403)
    if request.method not in ('GET','HEAD','OPTIONS') and any(word in request.path.lower() for word in ('sync','clover','acquisition')):
        abort(403)
    # Keep the explicit choice outside the RF1 session: a denied/inactive
    # account must never fall back to owner after auth clears that session.
    choice=None
    try:
        choice=local_signer.loads(request.cookies.get(LOCAL_CHOICE_COOKIE,''))
    except BadSignature:
        pass
    if not browser_session.get('local_user_selected'):
        if choice is None:
            with SessionFactory() as db:
                owner=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.status=='ACTIVE',m.RFOneAccount.is_owner.is_(True)))
                assert owner is not None
                choice={'id':owner.id,'version':owner.session_version}
        browser_session.clear()
        browser_session['local_user_selected']=True
        browser_session[shared.SESSION_ACCOUNT_KEY]=choice['id']
        browser_session[shared.SESSION_VERSION_KEY]=choice['version']
    g.local_user_choice=choice or {'id':browser_session.get(shared.SESSION_ACCOUNT_KEY),'version':browser_session.get(shared.SESSION_VERSION_KEY)}
    if request.path in ('/login','/logout'):
        return redirect('/local/users')


def local_administrator(db):
    account=shared.account_for_session(db,
        account_id=browser_session.get(shared.SESSION_ACCOUNT_KEY),
        session_version=browser_session.get(shared.SESSION_VERSION_KEY))
    return bool(account and (account.is_admin or account.is_owner))


def require_local_administrator():
    with SessionFactory() as db:
        if not local_administrator(db):abort(403)


def user_controls():
    with SessionFactory() as db:
        if not local_administrator(db):return ''
        rows=list(db.scalars(select(m.RFOneAccount).order_by(m.RFOneAccount.display_name)))
        choices=''.join('<option value="'+str(a.id)+'" '+('selected' if a.id==browser_session.get(shared.SESSION_ACCOUNT_KEY) else '')+'>'+escape(a.display_name)+' ('+escape(a.username)+')'+(' — inactive' if a.status!='ACTIVE' else '')+'</option>' for a in rows)
    return '<form method="post" action="/local/access-user" style="display:flex;align-items:center;justify-content:flex-end;gap:.6rem;padding:.5rem 2rem;color:#53632f;font:16px system-ui"><input type="hidden" name="csrf_token" value="'+escape(shared.csrf_token(browser_session))+'"><label>User <select name="account_id" style="padding:.45rem;border:1px solid #cbd5ad;border-radius:6px">'+choices+'</select></label><button style="background:#55682f;color:white;border:0;border-radius:6px;padding:.6rem 1rem">Switch user</button><a href="/" style="color:#53632f">MyRF</a></form>'

@web.app.get('/local/users')
def local_users():
    require_local_administrator()
    return '<!doctype html><html><body>'+user_controls()+'</body></html>'

@web.app.post('/local/access-user')
def select_local_user():
    require_local_administrator()
    if request.headers.get('Origin') and request.headers['Origin'] not in (f'http://127.0.0.1:{state["web_port"]}',f'http://localhost:{state["web_port"]}'):
        abort(403)
    import secrets
    if not secrets.compare_digest(request.form.get('csrf_token',''),shared.csrf_token(browser_session)):abort(400)
    try:identity=int(request.form.get('account_id',''))
    except ValueError:abort(400)
    with SessionFactory() as db:
        account=db.get(m.RFOneAccount,identity)
        if account is None:abort(400)
        browser_session.clear()
        browser_session['local_user_selected']=True
        browser_session[shared.SESSION_ACCOUNT_KEY]=account.id
        browser_session[shared.SESSION_VERSION_KEY]=account.session_version
        choice={'id':account.id,'version':account.session_version}
    response=redirect('/')
    response.set_cookie(LOCAL_CHOICE_COOKIE,local_signer.dumps(choice),httponly=True,samesite='Lax',path='/')
    return response


def install_local(application):
    application.config.update(SESSION_COOKIE_SECURE=False,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax')
    application.before_request_funcs.setdefault(None,[]).insert(0,local_copy_scope)
    @application.after_request
    def show_user(response):
        response.headers['Cache-Control']='no-store'
        if not request.cookies.get(LOCAL_CHOICE_COOKIE) and getattr(g,'local_user_choice',None):
            response.set_cookie(LOCAL_CHOICE_COOKIE,local_signer.dumps(g.local_user_choice),httponly=True,samesite='Lax',path='/')
        if response.mimetype=='text/html' and not response.is_streamed:
            body=response.get_data(as_text=True)
            if '<body' in body:
                end=body.index('>',body.index('<body'))+1
                body=body[:end]+user_controls()+body[end:]
                response.set_data(body)
        return response
for application in apps:install_local(application)
kitchen.config['KITCHEN_REQUIRE_S3']=False

def local_application(environ,start_response):
    path=environ.get('PATH_INFO','/')
    if path=='/kitchen' or path.startswith('/kitchen/'):target=kitchen
    elif path=='/selection' or path.startswith('/selection/'):target=selection
    elif (path=='/tips' or path.startswith('/tips/')) and not (path=='/tips/runs' or path.startswith('/tips/runs/')):target=tips
    else:target=web.app
    return target(environ,start_response)

if '--check' in sys.argv:
    from werkzeug.test import Client
    from werkzeug.wrappers import Response
    client=Client(local_application,Response)
    base=f'http://127.0.0.1:{state["web_port"]}'
    paths=['/','/admin/roles','/bank','/compensation','/projects','/admin/organization','/restaurant/wines','/tips/','/selection/','/kitchen/dashboard']
    results={path:client.get(path,base_url=base,environ_overrides={'REMOTE_ADDR':'127.0.0.1'}).status_code for path in paths}
    print(json.dumps({'pages':results,'login_required':False,'user_selector':True,'external_integrations_disabled':True}))
else:
    from werkzeug.serving import run_simple
    run_simple('127.0.0.1',state['web_port'],local_application,use_debugger=False,use_reloader=False)
