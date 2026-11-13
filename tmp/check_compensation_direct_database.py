from pathlib import Path
import boto3,json,psycopg2
from sqlalchemy.engine import make_url
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');state=json.loads(Path('tmp/registry-access-release/release-state.json').read_text());svc=s.client('apprunner').describe_service(ServiceArn=state['services']['web']['service_arn'])['Service'];reference=svc['SourceConfiguration']['ImageRepository']['ImageConfiguration']['RuntimeEnvironmentSecrets']['RFONE_DATABASE_URL'];raw=s.client('secretsmanager').get_secret_value(SecretId=reference)['SecretString']
try:
 obj=json.loads(raw);raw=obj if isinstance(obj,str) else next(obj[k] for k in ('RFONE_DATABASE_URL','DATABASE_URL','database_url','url') if k in obj)
except json.JSONDecodeError:pass
url=make_url(raw)
try:
 c=psycopg2.connect(host=url.host,port=url.port or 5432,dbname=url.database,user=url.username,password=url.password,sslmode='require',connect_timeout=6,options='-c default_transaction_read_only=on')
 with c.cursor() as cursor:cursor.execute('SHOW server_version');version=cursor.fetchone()[0]
 c.close();print(json.dumps({'direct_readonly_connection':True,'server_version':version,'network_changes':False}))
except psycopg2.OperationalError:
 print(json.dumps({'direct_readonly_connection':False,'network_changes':False}))
