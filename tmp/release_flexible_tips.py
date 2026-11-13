"""Release only committed/pushed Tips source; additive schema migration is explicit."""
from pathlib import Path
from datetime import datetime,timezone
import boto3,subprocess,zipfile,io,json,hashlib,sys
ROOT=Path(__file__).resolve().parents[1];STATE=ROOT/'tmp/flexible_release.json'
S=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1')
APP=S.client('apprunner');CB=S.client('codebuild');S3=S.client('s3');ECS=S.client('ecs')
ARN='arn:aws:apprunner:us-east-1:418674484214:service/rfone-tips/f12550d3be8047d0a72e17a91e218d27'
BUCKET='rfone-tips-deploy-418674484214'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def save(d):STATE.write_text(json.dumps(d,indent=2,default=str))
def load():return json.loads(STATE.read_text())
def prepare():
 assert not STATE.exists()
 commit=git('rev-parse','HEAD').decode().strip();assert git('rev-parse','origin/codex/tips-flexible-rules').decode().strip()==commit
 current=APP.describe_service(ServiceArn=ARN)['Service'];assert current['Status']=='RUNNING'
 previous=current['SourceConfiguration']['ImageRepository']['ImageIdentifier'];assert previous.endswith(':tips-openai-bedrock-20261109t140457z')
 tag='tips-flexible-'+datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%Sz').lower()
 content=io.BytesIO();prefixes=['RF-One Data Store','Tips','Clover Data Explorer','Shared UI','Training']
 snapshot=zipfile.ZipFile(io.BytesIO(git('archive','--format=zip',commit,*[f'03 Software/{p}' for p in prefixes])))
 with zipfile.ZipFile(content,'w',zipfile.ZIP_DEFLATED) as out:
  for name in snapshot.namelist():
   if name.endswith('/'):continue
   assert '/data/' not in name or name.endswith('.gitkeep'),name
   assert not any(x in name for x in ['/.env','__pycache__','.dump','local-connection']),name
   out.writestr(name[len('03 Software/'):],snapshot.read(name))
  for name in ['Dockerfile','buildspec.yml']:
   data=git('show',commit+':03 Software/Infrastructure/deploy/rfone-tips/'+name)
   if name=='buildspec.yml':data=data.replace(b'tips-openai-bedrock-20261109t140457z',tag.encode())
   out.writestr(name,data)
 data=content.getvalue();key='releases/'+tag+'/source.zip'
 S3.put_object(Bucket=BUCKET,Key=key,Body=data,ServerSideEncryption='AES256',Metadata={'rfone-commit':commit,'sha256':hashlib.sha256(data).hexdigest()})
 (ROOT/'tmp/flexible_previous_service.json').write_text(json.dumps(current,default=str))
 build=CB.start_build(projectName='rfone-tips-build',sourceTypeOverride='S3',sourceLocationOverride=BUCKET+'/'+key)['build']
 d=dict(commit=commit,tag=tag,previous_image=previous,image=previous.rsplit(':',1)[0]+':'+tag,
  source_key=key,source_sha256=hashlib.sha256(data).hexdigest(),build_id=build['id'],schema_revision='e2c320261109')
 save(d);print(json.dumps(d),flush=True)
def status():
 d=load();b=CB.batch_get_builds(ids=[d['build_id']])['builds'][0];d['build_status']=b['buildStatus'];save(d)
 print('BUILD',b['buildStatus'],b.get('currentPhase'),flush=True)
 if b['buildStatus']=='FAILED':
  print(json.dumps([p for p in b['phases'] if p.get('phaseStatus')=='FAILED'],default=str))
 if d.get('migration_task'):
  t=ECS.describe_tasks(cluster='rfone-jobs',tasks=[d['migration_task']])['tasks'][0]
  print('MIGRATION',t['lastStatus'],[(c.get('exitCode'),c.get('reason')) for c in t['containers']],flush=True)
 if d.get('operation_id'):
  op=next(x for x in APP.list_operations(ServiceArn=ARN)['OperationSummaryList'] if x['Id']==d['operation_id'])
  d['deployment_status']=op['Status'];save(d);print('DEPLOYMENT',op['Status'],flush=True)
def migrate():
 d=load();assert d.get('build_status')=='SUCCEEDED';assert not d.get('migration_task')
 # Use the already verified full AWS export as the recovery backup. Only this
 # additive configuration column changes; no local data is uploaded.
 copy=json.loads((ROOT.parent/'tmp/tips_full_copy_state.json').read_text());assert copy['copy_verified']
 verify=json.loads(Path(copy['verification']).read_text());assert verify['verified']
 script="""import os,sys,urllib.request,zipfile,io,json
from pathlib import Path
from sqlalchemy import create_engine,text
from alembic import command
from alembic.config import Config
root=Path('/tmp/tips-flexible');root.mkdir(exist_ok=True)
archive=zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(os.environ['SOURCE_URL']).read()))
for item in archive.infolist():
 if item.filename.startswith('RF-One Data Store/'):
  dest=root/item.filename;assert dest.resolve().is_relative_to(root.resolve());dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(archive.read(item))
store=root/'RF-One Data Store';sys.path.insert(0,str(store))
url=os.environ['RFONE_DATABASE_URL'];e=create_engine(url)
with e.connect() as c:
 assert c.scalar(text('select version_num from alembic_version'))=='e1b220261102','AWS schema changed: stop'
 before={n:c.scalar(text('select count(*) from '+n)) for n in ['orders','shifts','employee_assignments','tip_distribution_rules','tip_distribution_rule_versions']}
os.environ['ALEMBIC_DATABASE_URL_OVERRIDE']=url
command.upgrade(Config(str(store/'alembic.ini')),'e2c320261109')
with e.connect() as c:
 assert c.scalar(text('select version_num from alembic_version'))=='e2c320261109'
 after={n:c.scalar(text('select count(*) from '+n)) for n in before}
 assert before==after
 assert c.scalar(text("select count(*) from tip_distribution_rule_versions where aggregation_scope<>'ORDER'"))==0
print('TIPS_MIGRATION_OK '+json.dumps(dict(revision='e2c320261109',row_counts_unchanged=before==after,existing_rules_preserved=True)),flush=True)
"""
 key='releases/'+d['tag']+'/migrate.py';S3.put_object(Bucket=BUCKET,Key=key,Body=script.encode(),ServerSideEncryption='AES256')
 source_url=S3.generate_presigned_url('get_object',Params={'Bucket':BUCKET,'Key':d['source_key']},ExpiresIn=3600)
 script_url=S3.generate_presigned_url('get_object',Params={'Bucket':BUCKET,'Key':key},ExpiresIn=3600)
 bootstrap="import os,urllib.request;exec(compile(urllib.request.urlopen(os.environ['MIGRATION_URL']).read(),'<tips-explicit-migration>','exec'))"
 network=ECS.describe_services(cluster='rfone-jobs',services=['rfone-clover-correction-sync'])['services'][0]['networkConfiguration']
 tasks=ECS.run_task(cluster='rfone-jobs',taskDefinition='rfone-interviews-migration:3',launchType='FARGATE',networkConfiguration=network,
  overrides={'containerOverrides':[{'name':'interviews-migration','command':['-c',bootstrap],
  'environment':[{'name':'MIGRATION_URL','value':script_url},{'name':'SOURCE_URL','value':source_url}]}]})
 assert not tasks.get('failures'),tasks.get('failures');d['migration_task']=tasks['tasks'][0]['taskArn'];d['backup_verification']=copy['verification'];save(d);print('MIGRATION_TASK_STARTED',d['migration_task'])
def deploy():
 d=load();assert d.get('build_status')=='SUCCEEDED'
 task=ECS.describe_tasks(cluster='rfone-jobs',tasks=[d['migration_task']])['tasks'][0]
 assert task['lastStatus']=='STOPPED' and all(c.get('exitCode')==0 for c in task['containers']),'Migration not successful'
 current=APP.describe_service(ServiceArn=ARN)['Service'];assert current['Status']=='RUNNING'
 source=current['SourceConfiguration'];assert source['ImageRepository']['ImageIdentifier']==d['previous_image']
 source['ImageRepository']['ImageIdentifier']=d['image']
 result=APP.update_service(ServiceArn=ARN,SourceConfiguration=source);d['operation_id']=result['OperationId'];save(d)
 print('DEPLOYMENT_STARTED',d['operation_id'])
if __name__=='__main__':{'prepare':prepare,'status':status,'migrate':migrate,'deploy':deploy}[sys.argv[1]]()
