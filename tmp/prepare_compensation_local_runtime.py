from pathlib import Path
import json,shutil,secrets,psycopg2
from psycopg2 import sql
root=Path('tmp/compensation-aws-copy');p=root/'state.json';state=json.loads(p.read_text());folder=Path(state['folder']);source=Path(state['source']);development=folder/'development-source'
shutil.copytree(source,development,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
existing=json.loads(Path(r'C:/Users/servi/AppData/Local/RF-One/Employee Directory/AWS-20261110T120743Z/verification.json').read_text(encoding='utf-8'));database=existing['local_database'];assert database['host']=='127.0.0.1';name='rfone_compensation_'+folder.name.removeprefix('AWS-').lower();connection=psycopg2.connect(host='127.0.0.1',port=database['port'],dbname='postgres',user=database['username']);connection.autocommit=True
with connection.cursor() as cursor:
 cursor.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,));exists=cursor.fetchone()
 if not exists:cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
 elif not state.get('local_database'):raise RuntimeError('Unexpected existing local target; preserve it')
connection.close();state['local_database']={'host':'127.0.0.1','port':database['port'],'database':name,'username':database['username']};state['development_source']=str(development);state['postgres_bin']=str(Path(existing['folder'])/'runtime/pgsql/bin');state['database_restored']=False
key=folder/'local-session.key'
if not key.exists():key.write_text(secrets.token_hex(32),encoding='utf-8')
p.write_text(json.dumps(state,indent=2));(folder/'verification.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
print('Local isolated Compensation database and source prepared; data restore pending.')
