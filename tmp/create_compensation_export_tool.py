from pathlib import Path
root=Path('tmp/compensation-aws-copy');context=root/'export-tool';context.mkdir(exist_ok=True)
(context/'Dockerfile').write_text('''FROM public.ecr.aws/docker/library/postgres:18
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-psycopg2 python3-requests ca-certificates && rm -rf /var/lib/apt/lists/*
COPY export_compensation.py /opt/export_compensation.py
ENTRYPOINT ["python3","/opt/export_compensation.py"]
''',encoding='utf-8')
(context/'export_compensation.py').write_text('''"""Read-only snapshot export of Compensation data and FK dependencies."""
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlsplit,unquote
import hashlib,json,os,re,subprocess,tempfile,zipfile,sys
import psycopg2
from psycopg2 import sql
import requests


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def main():
    raw=os.environ['RFONE_DATABASE_URL']
    try:
        parsed=json.loads(raw)
        raw=parsed if isinstance(parsed,str) else next(parsed[k] for k in ('RFONE_DATABASE_URL','DATABASE_URL','database_url','url') if k in parsed)
    except json.JSONDecodeError:pass
    url=urlsplit(raw)
    env=os.environ.copy()
    for key in tuple(env):
        if key.startswith('PG'):env.pop(key,None)
    env.update(PGHOST=url.hostname,PGPORT=str(url.port or 5432),PGDATABASE=url.path.lstrip('/'),PGUSER=unquote(url.username),PGPASSWORD=unquote(url.password),PGSSLMODE='require',PGCONNECT_TIMEOUT='20',PGOPTIONS='-c default_transaction_read_only=on -c lock_timeout=15000 -c statement_timeout=900000 -c timezone=UTC')
    connection=psycopg2.connect(host=env['PGHOST'],port=env['PGPORT'],dbname=env['PGDATABASE'],user=env['PGUSER'],password=env['PGPASSWORD'],sslmode='require',connect_timeout=20)
    connection.set_session(isolation_level='REPEATABLE READ',readonly=True,autocommit=False)
    folder=Path(tempfile.mkdtemp(prefix='compensation-copy-'))
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL TIME ZONE 'UTC'")
        cursor.execute("SELECT pg_export_snapshot(),transaction_timestamp(),current_setting('server_version_num')")
        snapshot,when,version=cursor.fetchone()
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        tables={row[0] for row in cursor.fetchall()}
        explicit={'alembic_version','shifts','employees','employee_assignments','employee_source_roles','employee_clover_links','employee_context_links','employee_identity_aliases','employee_directory_events','employee_registry_profiles','employee_registry_changes','source_systems','locations','restaurants','restaurant_locations','legal_entities','operational_areas','restaurant_roles','operational_area_roles','rfone_accounts','rfone_account_domain_access','rfone_account_domain_item_access','rfone_training_identity_links','rfone_company_contexts','rfone_person_company_memberships','rfone_role_profile_assignments','rfone_role_permissions','rfone_access_profile_events'}
        prefixes=('payroll_','employee_payroll_','employee_compensation_','approved_compensation_','approved_employee_','approved_incentive_','compensation_','incentive_','tip_','tips_','workweek_')
        roots={name for name in tables if name in explicit or name.startswith(prefixes)}
        selected=set(roots)
        cursor.execute("""SELECT child.relname,parent.relname FROM pg_constraint fk JOIN pg_class child ON child.oid=fk.conrelid JOIN pg_namespace cn ON cn.oid=child.relnamespace JOIN pg_class parent ON parent.oid=fk.confrelid JOIN pg_namespace pn ON pn.oid=parent.relnamespace WHERE fk.contype='f' AND cn.nspname='public' AND pn.nspname='public'""")
        edges=cursor.fetchall()
        while True:
            expanded=selected|{parent for child,parent in edges if child in selected}
            if expanded==selected:break
            selected=expanded
        assert {'employees','shifts','payroll_calculation_runs','employee_compensation_terms','tip_entitlements'}<=selected
        assert not {'bank_transactions','bank_transaction_records','raw_source_records','raw_clover_records'}&selected,'Unexpected unrelated data dependency; inspect scope'
        cursor.execute("""SELECT DISTINCT sequence.relname,parent.relname FROM pg_class sequence JOIN pg_namespace ns ON ns.oid=sequence.relnamespace JOIN pg_depend dependency ON dependency.objid=sequence.oid AND dependency.classid='pg_class'::regclass JOIN pg_class parent ON parent.oid=dependency.refobjid WHERE sequence.relkind='S' AND ns.nspname='public' AND dependency.deptype IN ('a','i')""")
        sequences=sorted({sequence for sequence,parent in cursor.fetchall() if parent in selected})
        manifest={'snapshot_time':when.isoformat(),'server_version_num':version,'pg_dump_version':subprocess.check_output(['pg_dump','--version'],text=True).strip(),'full_public_schema':True,'scoped_data':True,'root_tables':sorted(roots),'dependency_tables':sorted(selected-roots),'tables':{},'database_writes':False}
        critical={'employees','shifts','employee_compensation_terms','workweek_definitions','payroll_calculation_runs','employee_payroll_calculations','approved_compensation_snapshots','tip_entitlements'}
        for name in sorted(selected):
            assert re.fullmatch('[a-z_0-9]+',name)
            cursor.execute(sql.SQL('SELECT count(*) FROM public.{}').format(sql.Identifier(name)))
            item={'rows':cursor.fetchone()[0]}
            if name in critical:
                cursor.execute(sql.SQL('SELECT to_jsonb(t)::text FROM public.{} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(sql.Identifier(name)))
                h=hashlib.sha256()
                for row in cursor:h.update(row[0].encode('utf-8'));h.update(b'\\n')
                item['content_sha256']=h.hexdigest()
            manifest['tables'][name]=item
        common=['pg_dump','--format=custom','--compress=6','--no-owner','--no-privileges','--snapshot='+snapshot,'--schema=public']
        commands=[common+['--schema-only','--file='+str(folder/'schema.dump')],common+['--data-only','--file='+str(folder/'data.dump')]+['--table=public.'+name for name in sorted(selected)+sequences]]
        for command in commands:
            result=subprocess.run(command,env=env,capture_output=True,text=True)
            if result.returncode:raise RuntimeError('Read-only export failed: '+result.stderr.replace(env['PGPASSWORD'],'[REDACTED]')[-1500:])
        cursor.execute("SELECT version_num FROM alembic_version")
        manifest['schema_revision']=[row[0] for row in cursor.fetchall()]
    connection.rollback();connection.close()
    manifest['files']={name:{'sha256':digest(folder/name),'bytes':(folder/name).stat().st_size} for name in ('schema.dump','data.dump')}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    bundle=folder/'compensation-copy.zip'
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_STORED) as archive:
        for name in ('schema.dump','data.dump','manifest.json'):archive.write(folder/name,name)
    with bundle.open('rb') as body:
        response=requests.put(os.environ['RFONE_EXPORT_UPLOAD_URL'],data=body,headers={'Content-Length':str(bundle.stat().st_size),'x-amz-server-side-encryption':'AES256'},timeout=(20,300))
    if response.status_code not in (200,201):raise RuntimeError('Private staging upload failed, HTTP '+str(response.status_code))
    print('COMPENSATION_COPY_READY '+json.dumps({'bundle_sha256':digest(bundle),'bundle_bytes':bundle.stat().st_size,'tables':len(selected),'rows':sum(v['rows'] for v in manifest['tables'].values()),'snapshot_time':manifest['snapshot_time'],'schema_revision':manifest['schema_revision'],'database_writes':False}),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as error:
        # Never print the DSN, password or signed transport URL.
        print('COMPENSATION_COPY_FAILED '+type(error).__name__+': '+str(error)[:1600] if isinstance(error,AssertionError) else 'COMPENSATION_COPY_FAILED '+type(error).__name__,flush=True)
        sys.exit(1)
''',encoding='utf-8',newline='\n')
