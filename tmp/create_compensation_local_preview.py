from pathlib import Path
import json
folder=Path(r'C:/Users/servi/AppData/Local/RF-One/Compensation/AWS-20261110T214612Z')
script='''"""Local Compensation preview using previously copied local RF1 data, read-only."""
from pathlib import Path
import json,os,socket,sys
ROOT=Path(__file__).resolve().parent
state=json.loads((ROOT/'verification.json').read_text(encoding='utf-8'))
existing=json.loads(Path(r'C:/Users/servi/AppData/Local/RF-One/Employee Directory/AWS-20261110T120743Z/verification.json').read_text(encoding='utf-8'))
db=existing['local_database'];assert db['host']=='127.0.0.1'
for key in tuple(os.environ):
    if key.startswith(('RFONE_','AWS_','CLOVER_','PG')):os.environ.pop(key,None)
from sqlalchemy.engine import URL
url=URL.create('postgresql+psycopg2',username=db['username'],host='127.0.0.1',port=db['port'],database=db['database'],query={'options':'-c default_transaction_read_only=on'})
os.environ.update(RFONE_DATABASE_URL=url.render_as_string(hide_password=False),RFONE_FLASK_SECRET_KEY=(ROOT/'local-session.key').read_text().strip(),RFONE_CLOVER_JOB_LAUNCHER='disabled',RFONE_AI_PROVIDER='DISABLED',AWS_EC2_METADATA_DISABLED='true',AWS_CONFIG_FILE=str(ROOT/'disabled-aws-config'),AWS_SHARED_CREDENTIALS_FILE=str(ROOT/'disabled-aws-credentials'),RFONE_PUBLIC_BASE_URL='http://127.0.0.1:5095',HTTP_PROXY='http://127.0.0.1:9',HTTPS_PROXY='http://127.0.0.1:9',NO_PROXY='127.0.0.1,localhost,::1')
original_connect=socket.socket.connect
original_connect_ex=socket.socket.connect_ex

def connect(sock,address):
    if not isinstance(address,tuple) or address[0] not in ('127.0.0.1','localhost','::1'):raise RuntimeError('External connections disabled in local preview')
    return original_connect(sock,address)

def connect_ex(sock,address):
    if not isinstance(address,tuple) or address[0] not in ('127.0.0.1','localhost','::1'):raise RuntimeError('External connections disabled in local preview')
    return original_connect_ex(sock,address)
socket.socket.connect=connect;socket.socket.connect_ex=connect_ex
import boto3

def no_cloud(*args,**kwargs):raise RuntimeError('Cloud operations disabled in local preview')
boto3.session.Session.client=no_cloud;boto3.session.Session.resource=no_cloud
source=Path(state['development_source']);sys.path[:0]=[str(source/'RF-One Web'),str(source/'RF-One Data Store')]
os.chdir(source/'RF-One Web')
import app as web
from db import SessionFactory
from sqlalchemy import select
from rfone_data_store import models as m
from flask import request,session,abort,redirect
web.app.config.update(SESSION_COOKIE_NAME='rfone_compensation_preview',SESSION_COOKIE_SECURE=False)

def local_preview():
    if request.remote_addr not in ('127.0.0.1','::1') or request.host not in ('127.0.0.1:5095','localhost:5095'):abort(403)
    if request.method not in ('GET','HEAD','OPTIONS'):abort(405)
    if request.path in ('/','/login','/logout'):return redirect('/compensation/runs/6#period-hours')
    if not request.path.startswith(('/compensation','/static/','/shared-brand/')):abort(404)
    with SessionFactory() as database:
        owner=database.scalar(select(m.RFOneAccount).where(m.RFOneAccount.is_owner.is_(True),m.RFOneAccount.status=='ACTIVE'))
        assert owner is not None
        session['rfone_account_id']=owner.id
        session['rfone_session_version']=owner.session_version
web.app.before_request_funcs.setdefault(None,[]).insert(0,local_preview)

if __name__=='__main__':web.app.run(host='127.0.0.1',port=5095,debug=False,use_reloader=False)
'''
(folder/'launch_preview.py').write_text(script,encoding='utf-8',newline='\n')
state=json.loads((folder/'verification.json').read_text(encoding='utf-8'));state['preview']={'url':'http://127.0.0.1:5095/compensation/runs/6#period-hours','database_source':'Previously copied local RF1 database','read_only':True,'fresh_aws_database_restored':False};(folder/'verification.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
print('Read-only local preview configured.')
