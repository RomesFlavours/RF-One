from pathlib import Path
import boto3,json,psycopg2
from sqlalchemy.engine import make_url
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');a=s.client('apprunner');arn=json.loads(Path('tmp/anagrafica_deploy_audit.json').read_text())['service_arn'];cfg=a.describe_service(ServiceArn=arn)['Service']['SourceConfiguration']['ImageRepository']['ImageConfiguration'];raw=s.client('secretsmanager').get_secret_value(SecretId=cfg['RuntimeEnvironmentSecrets']['RFONE_DATABASE_URL'])['SecretString']
try:
    v=json.loads(raw);raw=v if isinstance(v,str) else next(v[k] for k in ('RFONE_DATABASE_URL','DATABASE_URL','url') if k in v)
except json.JSONDecodeError:pass
u=make_url(raw)
try:
    c=psycopg2.connect(host=u.host,port=u.port or 5432,dbname=u.database,user=u.username,password=u.password,sslmode='require',connect_timeout=5,options='-c default_transaction_read_only=on')
    with c.cursor() as q:q.execute('select version_num from alembic_version');print(json.dumps({'connection':True,'revision':q.fetchall()}))
    c.close()
except psycopg2.OperationalError:print('Direct database connection unavailable')
