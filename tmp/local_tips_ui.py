from pathlib import Path
import os,json,sys,secrets
from sqlalchemy.engine import URL
ROOT=Path(__file__).resolve().parents[1]
d=json.loads((Path(os.environ['LOCALAPPDATA'])/'RF-One/AWS-Copy/20261025T130037Z/local-connection.json').read_text());assert d['host']=='127.0.0.1' and d['port']==55436
os.environ['RFONE_DATABASE_URL']=URL.create('postgresql+psycopg2',username=d['user'],password=d['password'],host=d['host'],port=d['port'],database=d['database']).render_as_string(hide_password=False)
os.environ['RFONE_UI_LANGUAGE']='it';os.environ['RFONE_TIPS_AWS_PROFILE']='rfone-dev-login'
sys.path.insert(0,str(ROOT/'03 Software/Tips'));sys.path.insert(0,str(ROOT/'03 Software/Clover Data Explorer'))
import app as module
from rfone_data_store import models as m
from flask import redirect,request
from werkzeug.serving import run_simple
with module.SessionFactory() as s:
 account=s.get(m.RFOneAccount,4);assert account is not None
 version=account.session_version
cookie=module.app.session_interface.get_signing_serializer(module.app).dumps(dict(rfone_account_id=4,rfone_session_version=version))
nonce=secrets.token_urlsafe(24)
@module.app.route('/__local_preview/'+nonce)
def preview():
 response=redirect('/configuration');response.set_cookie('session',cookie,httponly=True,samesite='Lax');return response
module._PUBLIC_ENDPOINTS = module._PUBLIC_ENDPOINTS | {'preview'}
# Keep production authentication and routes unchanged; only loopback launcher
# issues this temporary preview session for the already existing account.
module.app.config['SESSION_COOKIE_SECURE']=False
with module.app.test_client() as client:
 client.set_cookie('session',cookie)
 for language in ('en','it'):
  os.environ['RFONE_UI_LANGUAGE']=language
  for path in ['/configuration','/distribution-rules/2','/calculate-tips']:
   response=client.get(path);assert response.status_code==200,(path,response.status_code)
   body=response.get_data(as_text=True);assert 'data-how-works' in body
  response=client.get('/configuration');assert ('Come funziona questa pagina' if language=='it' else 'How this page works') in response.get_data(as_text=True)
 print('English and Italian authenticated page checks passed.',flush=True)
os.environ['RFONE_UI_LANGUAGE']='it'
if '--check' in sys.argv: sys.exit(0)
(ROOT/'tmp/local_ui_entry.json').write_text(json.dumps(dict(url='http://127.0.0.1:5097/__local_preview/'+nonce)))
print('Local Tips running on loopback port 5097 (Italian).',flush=True)
run_simple('127.0.0.1',5097,module.app,use_reloader=False,threaded=True)
