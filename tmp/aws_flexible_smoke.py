"""Authenticated interpretation-only AWS smoke check; never confirms a rule."""
from pathlib import Path
import boto3,json,secrets,requests,psycopg2
from sqlalchemy.engine import make_url
from flask import Flask
from flask.sessions import SecureCookieSessionInterface
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parent / 'flexible_smoke'
ROOT.mkdir(exist_ok=True)
existing=Path('C:/Users/servi/OneDrive/AI-RF-ONE/RF One/tmp/tips_openai_20261109/account_identity.json')
(ROOT/'account_identity.json').write_bytes(existing.read_bytes())
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1')
def secret(name):
    value=s.client('secretsmanager').get_secret_value(SecretId=name)['SecretString']
    try:
        v=json.loads(value)
        return v if isinstance(v,str) else next(v[k] for k in ('RFONE_DATABASE_URL','DATABASE_URL','database_url','url','RFONE_FLASK_SECRET_KEY','secret_key') if k in v)
    except json.JSONDecodeError:return value

identity=ROOT/'account_identity.json'
if identity.exists():
    verified=json.loads(identity.read_text());row=(verified['id'],verified['session_version'])
else:
    u=make_url(secret('rfone-tips/database-url'))
    c=psycopg2.connect(host=u.host,port=u.port or 5432,dbname=u.database,user=u.username,password=u.password,
        sslmode='require',connect_timeout=12,options='-c default_transaction_read_only=on -c statement_timeout=10000')
    with c.cursor() as q:
        q.execute('SHOW transaction_read_only');assert q.fetchone()[0]=='on'
        q.execute("SELECT id,session_version FROM rfone_accounts WHERE username='rfone' AND status='ACTIVE' AND is_admin=true")
        row=q.fetchone();assert row,'Existing RF-One administrator not found'
    c.rollback();c.close()
app=Flask('tips_smoke');app.secret_key=secret('rfone-web/flask-secret-key')
csrf=secrets.token_urlsafe(32)
cookie=SecureCookieSessionInterface().get_signing_serializer(app).dumps({
    'rfone_account_id':row[0],'rfone_session_version':row[1],'rfone_csrf_token':csrf})
http=requests.Session();http.cookies.set('session',cookie,domain='rfone.romesflavours.com',secure=True,path='/')
base='https://rfone.romesflavours.com'
before=http.get(base+'/tips/configuration',timeout=30,allow_redirects=False)
assert before.status_code==200,'Tips auth GET returned '+str(before.status_code)
statement='Starting January 1, 2026, pool 10% of each Server daily total voluntary tips plus gratuity and distribute that contribution to Hosts who worked that business day, proportionally to each Host hours divided by total Host hours. If no Host worked that day, take nothing and the Server keeps 100%.'
response=http.post(base+'/tips/distribution-rules/ai/interpret',data={'statement':statement,'csrf_token':csrf},timeout=55,allow_redirects=False)
class Proposal(HTMLParser):
    value=None
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=='input' and d.get('name')=='proposal_json':self.value=d.get('value')
p=Proposal();p.feed(response.text)
result={'get_status':before.status_code,'interpret_status':response.status_code,
    'proposal_shown':p.value is not None,'confirmation_submitted':False,'database_write_requests':False,'identity_from_previous_verified_read':True}
if p.value:
    proposal=json.loads(p.value);result.update(rate=proposal['rate'],base=proposal['calculation_base'],aggregation_scope=proposal['aggregation_scope'],eligibility_mode=proposal['eligibility_mode'],distribution_method=proposal['distribution_method'])
else:
    result['provider_error']='AI rule interpretation is currently unavailable' in response.text
    result['access_denied']='Access denied' in response.text
    result['body_excerpt']=None
    import re
    error=re.search(r'AI rule interpretation is currently unavailable[^<]+',response.text)
    if error:result['provider_error_detail']=error.group(0)[:400]
print(json.dumps(result))
(ROOT/'smoke.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
assert result['proposal_shown'] and float(result['rate'])==10,'AWS did not produce a usable proposal'

assert result['aggregation_scope']=='SOURCE_BUSINESS_DAY' and result['eligibility_mode']=='WORKED_DURING_BUSINESS_DAY' and result['distribution_method']=='HOURS_PROPORTIONAL'
assert 'How this page works' in before.text and 'data-how-works' in before.text
