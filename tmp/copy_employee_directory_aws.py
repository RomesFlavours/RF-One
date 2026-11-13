"""Copy actual AWS RF1 runtime and shared PostgreSQL database into an isolated local instance."""
from pathlib import Path
from datetime import datetime, timezone
from io import BytesIO
import hashlib, ipaddress, json, os, shutil, socket, subprocess, sys, tarfile, time, urllib.request, zipfile
import boto3, psycopg2, requests
from psycopg2 import sql
from sqlalchemy.engine import make_url
from botocore.config import Config

BASE = Path(r"C:\Users\servi\AppData\Local\RF-One\Employee Directory")
STATE = Path(__file__).with_suffix('.json')
PG = Path(r"C:\Users\servi\AppData\Local\RF-One\AWS-Copy\20261025T130037Z\runtime\pgsql")
CFG = Config(connect_timeout=10, read_timeout=60, retries={'max_attempts': 2})
aws = boto3.Session(profile_name='rfone-dev-login', region_name='us-east-1')
def client(name): return aws.client(name, config=CFG)
def save(d):
    STATE.write_text(json.dumps(d, indent=2, default=str), encoding='utf-8')
    (Path(d['folder'])/'verification.json').write_text(json.dumps(d, indent=2, default=str), encoding='utf-8')
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1024*1024), b''): h.update(part)
    return h.hexdigest()
def pg_env(url=None):
    env=os.environ.copy()
    for key in ('PGHOST','PGPORT','PGDATABASE','PGUSER','PGPASSWORD','PGSERVICE','PGSERVICEFILE','PGOPTIONS'):
        env.pop(key,None)
    env['PGCONNECT_TIMEOUT']='15'
    if url:
        env.update(PGHOST=url.host,PGPORT=str(url.port or 5432),PGDATABASE=url.database,
                   PGUSER=url.username,PGPASSWORD=url.password,PGSSLMODE='require',
                   PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=600000 -c lock_timeout=15000')
    return env
def secret_url(service):
    secret_id=service['SourceConfiguration']['ImageRepository']['ImageConfiguration']['RuntimeEnvironmentSecrets']['RFONE_DATABASE_URL']
    value=client('secretsmanager').get_secret_value(SecretId=secret_id)['SecretString']
    try:
        data=json.loads(value)
        value=data if isinstance(data,str) else next(data[k] for k in ('RFONE_DATABASE_URL','DATABASE_URL','database_url','url') if k in data)
    except json.JSONDecodeError: pass
    return make_url(value)
def live_service():
    a=client('apprunner')
    service=next(v for v in a.list_services()['ServiceSummaryList'] if v['ServiceName']=='rfone-web')
    return a.describe_service(ServiceArn=service['ServiceArn'])['Service']

phase=sys.argv[1]
if phase=='source':
    assert client('sts').get_caller_identity()['Account']=='418674484214'
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    root=BASE/('AWS-'+stamp); root.mkdir(parents=True,exist_ok=False)
    d={'folder':str(root),'started_at':datetime.now(timezone.utc).isoformat(),'status':'IN_PROGRESS',
       'production_database_writes':False,'production_service_changes':False,'source_files':{},'phases':{}}
    save(d)
    live=live_service(); identifier=live['SourceConfiguration']['ImageRepository']['ImageIdentifier']
    d['service_arn']=live['ServiceArn'];d['service_image']=identifier
    repository,tag=identifier.split('/')[-1].rsplit(':',1)
    ecr=client('ecr'); item=ecr.batch_get_image(repositoryName=repository,imageIds=[{'imageTag':tag}])['images'][0]
    manifest=json.loads(item['imageManifest']);d['image_digest']=item['imageId']['imageDigest']
    if 'manifests' in manifest:
        chosen=next(x for x in manifest['manifests'] if x.get('platform',{}).get('architecture')=='amd64')
        item=ecr.batch_get_image(repositoryName=repository,imageIds=[{'imageDigest':chosen['digest']}])['images'][0]
        manifest=json.loads(item['imageManifest']);d['platform_image_digest']=item['imageId']['imageDigest']
    (root/'image-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    source=root/'source';source.mkdir()
    for index,layer in enumerate(manifest['layers']):
        # Inspect all layers: extraction allowlist is /app only, never the OS.
        url=ecr.get_download_url_for_layer(repositoryName=repository,layerDigest=layer['digest'])['downloadUrl']
        path=root/f'.layer-{index}.tar'
        with requests.get(url,timeout=(15,180),stream=True) as response:
            response.raise_for_status()
            with path.open('wb') as f:
                for chunk in response.iter_content(1024*1024):f.write(chunk)
        assert 'sha256:'+digest(path)==layer['digest']
        count=0
        with tarfile.open(path,'r:*') as archive:
            for member in archive:
                name=member.name.removeprefix('./');parts=Path(name).parts
                if not parts or parts[0]!='app' or '..' in parts:continue
                rel=Path(*parts[1:])
                if not rel.parts:continue
                if rel.name.startswith('.wh.'):
                    target=source/rel.parent/rel.name.removeprefix('.wh.')
                    if target.is_file():target.unlink()
                    continue
                if not member.isfile() or member.issym() or member.islnk():continue
                if '__pycache__' in rel.parts or rel.suffix in ('.pyc','.db','.sqlite') or rel.name=='.env':continue
                target=source/rel;target.parent.mkdir(parents=True,exist_ok=True)
                payload=archive.extractfile(member).read();target.write_bytes(payload);count+=1
        path.unlink()
        print('Image layer',index+1,'/',len(manifest['layers']),'application files',count,flush=True)
    assert (source/'RF-One Web/employee_directory_routes.py').exists()
    assert (source/'RF-One Data Store/rfone_data_store/models.py').exists()
    for file in source.rglob('*'):
        if file.is_file():d['source_files'][file.relative_to(source).as_posix()]=digest(file)
    # Keep the current build source separately; do not claim it is the running image.
    obj=client('s3').get_object(Bucket='rfone-tips-deploy-418674484214',Key='rfone-web-source.zip')
    payload=obj['Body'].read();(root/'aws-build-source.zip').write_bytes(payload)
    d['build_source']={'sha256':hashlib.sha256(payload).hexdigest(),'last_modified':str(obj['LastModified'])}
    with zipfile.ZipFile(BytesIO(payload)) as z:
        d['build_source']['runtime_differences']=[name for name in d['source_files'] if name in z.namelist()
            and hashlib.sha256(z.read(name)).hexdigest()!=d['source_files'][name]]
    assert live_service()['SourceConfiguration']['ImageRepository']['ImageIdentifier']==identifier,'Service changed while copying'
    d['phases']['source']='VERIFIED_ACTUAL_IMAGE';save(d)
    print(json.dumps({'folder':str(root),'image_digest':d['image_digest'],'files':len(d['source_files'])}),flush=True)
elif phase=='database':
    d=json.loads(STATE.read_text());root=Path(d['folder']);assert d['phases']['source']=='VERIFIED_ACTUAL_IMAGE'
    live=live_service();assert live['SourceConfiguration']['ImageRepository']['ImageIdentifier']==d['service_image']
    url=secret_url(live)
    r=client('rds').describe_db_instances(DBInstanceIdentifier='rfone-dev')['DBInstances'][0]
    assert url.host==r['Endpoint']['Address']
    ip=urllib.request.urlopen('https://checkip.amazonaws.com',timeout=15).read().decode().strip()
    assert ipaddress.ip_address(ip).version==4
    cidr=ip+'/32';group='sg-0f0e0d7421ec0d759'
    assert group in [x['VpcSecurityGroupId'] for x in r['VpcSecurityGroups']]
    ec2=client('ec2');rule_id=None;connection=None
    try:
        permissions=ec2.describe_security_groups(GroupIds=[group])['SecurityGroups'][0]['IpPermissions']
        exists=any(p.get('FromPort')==5432 and p.get('ToPort')==5432 and
                   any(x.get('CidrIp')==cidr for x in p.get('IpRanges',[])) for p in permissions)
        if not exists:
            result=ec2.authorize_security_group_ingress(GroupId=group,IpPermissions=[{
                'IpProtocol':'tcp','FromPort':5432,'ToPort':5432,
                'IpRanges':[{'CidrIp':cidr,'Description':'RF1 temporary read-only local Employee Directory copy '+root.name}]}])
            rule_id=result['SecurityGroupRules'][0]['SecurityGroupRuleId']
            d['temporary_network_rule']={'id':rule_id,'group':group,'cidr':cidr,'removed':False};save(d)
        for attempt in range(10):
            try:
                connection=psycopg2.connect(host=url.host,port=url.port or 5432,dbname=url.database,user=url.username,
                    password=url.password,sslmode='require',connect_timeout=8,
                    options='-c default_transaction_read_only=on -c statement_timeout=600000 -c lock_timeout=15000')
                break
            except psycopg2.OperationalError:
                if attempt==9:raise RuntimeError('PostgreSQL connection unavailable after temporary IP access') from None
                time.sleep(2)
        connection.set_session(isolation_level='REPEATABLE READ',readonly=True)
        with connection.cursor() as cur:
            cur.execute('SHOW transaction_read_only');assert cur.fetchone()[0]=='on'
            cur.execute('SELECT pg_export_snapshot(), transaction_timestamp(), version()');snapshot,when,version=cur.fetchone()
            d['database']={'snapshot_time':str(when),'server_version':version,'tables':{},'read_only':True}
            cur.execute('SELECT version_num FROM alembic_version');d['database']['schema_revision']=[x[0] for x in cur.fetchall()]
            cmd=[str(PG/'bin/pg_dump.exe'),'--format=custom','--compress=6','--no-owner','--no-privileges',
                 '--snapshot='+snapshot,'--file='+str(root/'rfone-aws.dump')]
            result=subprocess.run(cmd,env=pg_env(url),capture_output=True,text=True)
            if result.returncode:raise RuntimeError('pg_dump failed: '+result.stderr.replace(url.password or '<none>','[REDACTED]'))
            cur.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1,2")
            tables=cur.fetchall()
            for schema,table in tables:
                cur.execute(sql.SQL('SELECT count(*) FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(table)))
                d['database']['tables'][schema+'.'+table]={'rows':cur.fetchone()[0]}
            for table in ('employees','employee_clover_links','employee_context_links','employee_identity_aliases','rfone_accounts','shifts'):
                if 'public.'+table not in d['database']['tables']:continue
                cur.execute(sql.SQL('SELECT to_jsonb(t)::text FROM {} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(sql.Identifier(table)))
                h=hashlib.sha256()
                for row in cur:
                    h.update(row[0].encode('utf-8'));h.update(b'\n')
                d['database']['tables']['public.'+table]['content_sha256']=h.hexdigest()
        d['database']['dump_sha256']=digest(root/'rfone-aws.dump');d['database']['dump_bytes']=(root/'rfone-aws.dump').stat().st_size
        d['phases']['database']='CONSISTENT_SNAPSHOT_EXPORTED';save(d)
        print('Full consistent database exported:',len(tables),'tables;',sum(x['rows'] for x in d['database']['tables'].values()),'rows',flush=True)
    finally:
        if connection is not None:connection.rollback();connection.close()
        if rule_id:
            ec2.revoke_security_group_ingress(GroupId=group,SecurityGroupRuleIds=[rule_id])
            d['temporary_network_rule']['removed']=True;save(d);print('Temporary network rule removed',flush=True)
elif phase=='restore':
    d=json.loads(STATE.read_text());root=Path(d['folder']);assert d['phases']['database']=='CONSISTENT_SNAPSHOT_EXPORTED'
    runtime=root/'runtime/pgsql'
    if not runtime.exists():shutil.copytree(PG,runtime)
    port=55571
    if not (root/'postgres-data/PG_VERSION').exists():
        while True:
            probe=socket.socket()
            try:probe.bind(('127.0.0.1',port));probe.close();break
            except OSError:probe.close();port+=1
    elif (root/'postgres-data/postgresql.conf').exists():
        import re
        port=int(re.findall(r'^port = (\d+)',(root/'postgres-data/postgresql.conf').read_text(),re.M)[-1])
    pgdata=root/'postgres-data';env=pg_env()
    def run(args):
        with (root/'restore-commands.log').open('a',encoding='utf-8') as log:
            result=subprocess.run([str(runtime/'bin'/args[0]),*args[1:]],env=env,stdout=log,stderr=subprocess.STDOUT,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:raise RuntimeError(args[0]+' failed; inspect restore-commands.log')
    if not (pgdata/'PG_VERSION').exists():
        run(['initdb.exe','-D',str(pgdata),'-U','rfone_local','--auth=trust','--encoding=UTF8','--locale=C'])
        with (pgdata/'postgresql.conf').open('a',encoding='utf-8') as f:
            f.write("\nlisten_addresses = '127.0.0.1'\nport = "+str(port)+"\ntimezone = 'UTC'\n")
    try:
        probe=socket.create_connection(('127.0.0.1',port),timeout=2);probe.close()
        check=psycopg2.connect(host='127.0.0.1',port=port,dbname='postgres',user='rfone_local')
        with check.cursor() as cur:
            cur.execute('SHOW data_directory');assert Path(cur.fetchone()[0]).resolve()==pgdata.resolve()
        check.close()
    except (OSError,psycopg2.OperationalError):
        run(['pg_ctl.exe','-D',str(pgdata),'-l',str(root/'postgres.log'),'-w','start'])
    d['local_database']={'host':'127.0.0.1','port':port,'database':'rfone_employee_directory','username':'rfone_local'};save(d)
    check=psycopg2.connect(host='127.0.0.1',port=port,dbname='postgres',user='rfone_local')
    check.autocommit=True
    with check.cursor() as cur:
        cur.execute('SHOW data_directory');assert Path(cur.fetchone()[0]).resolve()==pgdata.resolve()
        cur.execute("SELECT count(*) FROM pg_database WHERE datname='rfone_employee_directory'")
        assert cur.fetchone()[0]==0,'Local target database already exists; inspect before restoring again'
        cur.execute('CREATE DATABASE rfone_employee_directory')
    check.close()
    run(['pg_restore.exe','--exit-on-error','--no-owner','--no-privileges','-h','127.0.0.1','-p',str(port),'-U','rfone_local',
         '-d','rfone_employee_directory',str(root/'rfone-aws.dump')])
    connection=psycopg2.connect(host='127.0.0.1',port=port,dbname='rfone_employee_directory',user='rfone_local')
    with connection.cursor() as cur:
        for full,expected in d['database']['tables'].items():
            schema,table=full.split('.',1)
            cur.execute(sql.SQL('SELECT count(*) FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(table)))
            assert cur.fetchone()[0]==expected['rows'],'Restored count differs for '+full
            if 'content_sha256' in expected:
                cur.execute(sql.SQL('SELECT to_jsonb(t)::text FROM {}.{} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(sql.Identifier(schema),sql.Identifier(table)))
                h=hashlib.sha256()
                for row in cur:h.update(row[0].encode('utf-8'));h.update(b'\n')
                assert h.hexdigest()==expected['content_sha256'],'Restored contents differ for '+full
        cur.execute('SELECT version_num FROM alembic_version');assert [x[0] for x in cur.fetchall()]==d['database']['schema_revision']
    connection.close();d['phases']['restore']='ALL_TABLE_COUNTS_AND_DIRECTORY_HASHES_VERIFIED';save(d)
    print('Local PostgreSQL restored and verified on loopback port',port,flush=True)
else:raise SystemExit('Unknown phase')
