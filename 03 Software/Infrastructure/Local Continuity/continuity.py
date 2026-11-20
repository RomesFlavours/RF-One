"""Local recovery tooling. No production writes, schema migration or account setup."""
from pathlib import Path
import argparse, hashlib, importlib.metadata, json, os, secrets, shutil, socket
import subprocess, sys, tempfile, time, zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
AREA = ROOT / 'output/local-continuity'
PACKAGE = AREA / 'current'
STATE = AREA / 'runtime'
LEGACY = Path(os.environ.get('LOCALAPPDATA', '')) / 'RF-One/AWS-Copy/20261025T130037Z'
PORT = 55436

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def run(args, **kwargs):
    # Windows PostgreSQL children can inherit pipe handles after pg_ctl exits.
    # A regular temporary file prevents communicate() waiting for the daemon.
    with tempfile.TemporaryFile() as output:
        result = subprocess.run([str(x) for x in args], stdin=subprocess.DEVNULL,
                                stdout=output, stderr=subprocess.STDOUT, **kwargs)
        output.seek(0); text=output.read().decode('utf-8',errors='replace')
    if result.returncode:
        raise RuntimeError(f'{Path(args[0]).name} failed: ' + text[-1500:])
    return text

def connection_url(config):
    from sqlalchemy import URL
    if config['host'] != '127.0.0.1' or config['database'] != 'rfone_aws_copy':
        raise RuntimeError('Only the existing loopback RF-One database is supported.')
    return URL.create('postgresql+psycopg2', username=config['user'], password=config['password'],
                      host=config['host'], port=config['port'], database=config['database'])

def snapshot(config=None, pg=None):
    import sqlalchemy as sa
    from packaging.requirements import Requirement
    config = config or json.loads((LEGACY / 'local-connection.json').read_text())
    pg = pg or LEGACY / 'runtime/pgsql'
    AREA.mkdir(parents=True, exist_ok=True)
    target = AREA / ('preparing-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    target.mkdir()
    env = os.environ.copy(); env['PGPASSWORD'] = config['password']
    engine = sa.create_engine(connection_url(config))
    manifest = {'created_at': datetime.now(timezone.utc).isoformat(), 'source_host': socket.gethostname(),
                'source_root': str(ROOT), 'database': config['database'], 'table_counts': {},
                'local_assets': [], 'remote_asset_count': 0, 'files': {}}
    # Counts and dump use the same exported MVCC snapshot; active source is never changed.
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
        c.execute(sa.text('SET TRANSACTION READ ONLY'))
        snap = c.scalar(sa.text('SELECT pg_export_snapshot()'))
        manifest['revisions'] = list(c.scalars(sa.text('SELECT version_num FROM alembic_version ORDER BY version_num')))
        for name in sa.inspect(c).get_table_names():
            quoted = c.dialect.identifier_preparer.quote(name)
            manifest['table_counts'][name] = c.scalar(sa.text('SELECT count(*) FROM ' + quoted))
        for table, column in [('kitchen_recipe_photos','asset_uri'), ('raw_resumes','storage_path'),
                              ('dev_journal_documents','storage_path')]:
            if not sa.inspect(c).has_table(table): continue
            for value in c.scalars(sa.text(f'SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL')):
                if value.startswith(('s3://','http://','https://')):
                    manifest['remote_asset_count'] += 1; continue
                p = Path(value)
                if not p.is_file(): continue
                relative = 'assets/' + digest(p) + p.suffix.lower()
                dest = target / relative; dest.parent.mkdir(exist_ok=True)
                if not dest.exists(): shutil.copyfile(p, dest)
                manifest['local_assets'].append({'table':table,'column':column,'old':value,'file':relative})
        run([pg/'bin/pg_dump.exe', '-h',config['host'],'-p',str(config['port']),'-U',config['user'],
             '-Fc','--no-owner','--no-acl','--snapshot',snap,'-f',target/'database.dump',config['database']], env=env)
    engine.dispose()
    with zipfile.ZipFile(target/'postgres-runtime.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in pg.rglob('*'):
            if p.is_file(): z.write(p,p.relative_to(pg).as_posix())
    # Code checkpoint is independent of absolute .git worktree links.
    allowed={'.py','.html','.css','.js','.md','.txt','.toml','.ini','.yaml','.yml','.ps1','.cmd',
             '.svg','.png','.jpg','.jpeg','.webp','.woff','.woff2','.ttf'}
    with zipfile.ZipFile(target/'source.zip','w',zipfile.ZIP_DEFLATED) as z:
        for folder in ['03 Software','RFBank']:
            for directory,dirs,files in os.walk(ROOT/folder):
                dirs[:]=[x for x in dirs if x.lower() not in {'__pycache__','.venv','venv','data','uploads','recovery','node_modules','parking','.git'}]
                for name in files:
                    p=Path(directory)/name
                    if p.suffix.lower() not in allowed and p.name!='how_works_registry.json': continue
                    rel=p.relative_to(ROOT)
                    if any(x in p.name.lower() for x in ['session.key','credentials','connection.json']): continue
                    z.write(p,rel.as_posix())
        for name in ['CLAUDE.md','AGENTS.md','PROJECT_STATE.md','.gitignore','Riprendi lavoro locale.cmd','Prepara cambio PC.cmd','07 Tasks/Reports/SESSION_HANDOFF_20261114.md']:
            if (ROOT/name).exists(): z.write(ROOT/name,name)
    seeds=['Flask','SQLAlchemy','alembic','requests','openpyxl','paramiko','boto3','botocore',
           'psycopg2-binary','PyJWT','tzdata','pdfplumber','python-docx','Pillow','cryptography','awscrt','reportlab','packaging']
    versions={}; queue=list(seeds)
    while queue:
        name=queue.pop()
        try: d=importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError: continue
        canonical=d.metadata['Name']
        if canonical in versions: continue
        versions[canonical]=d.version
        for raw in d.requires or []:
            req=Requirement(raw)
            if req.marker is None or req.marker.evaluate({'extra':''}): queue.append(req.name)
    (target/'requirements.lock.txt').write_text(''.join(f'{k}=={v}\n' for k,v in sorted(versions.items())),encoding='utf-8')
    run([sys.executable,'-m','pip','download','--only-binary=:all:','-r',target/'requirements.lock.txt','-d',target/'wheels'])
    manifest['git_head']=run(['git','rev-parse','HEAD'],cwd=ROOT).strip()
    manifest['git_status']=run(['git','status','--short'],cwd=ROOT)
    for p in target.rglob('*'):
        if p.is_file(): manifest['files'][p.relative_to(target).as_posix()]={'sha256':digest(p),'bytes':p.stat().st_size}
    write_json(target/'manifest.json',manifest)
    if PACKAGE.exists():
        PACKAGE.rename(AREA/('previous-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')))
    target.rename(PACKAGE)
    print(f'Recovery ready: {len(manifest["table_counts"])} tables, {len(manifest["local_assets"])} local assets.')
    return manifest

def check(require_sources=False):
    m=json.loads((PACKAGE/'manifest.json').read_text(encoding='utf-8'))
    for name,info in m['files'].items():
        p=PACKAGE/name
        if not p.is_file() or digest(p)!=info['sha256']: raise RuntimeError('Incomplete or changed transfer: '+name)
    if require_sources:
        with zipfile.ZipFile(PACKAGE/'source.zip') as z:
            for name in z.namelist():
                p=ROOT/name
                if not p.is_file() or hashlib.sha256(p.read_bytes()).digest()!=hashlib.sha256(z.read(name)).digest():
                    raise RuntimeError('Source differs from the checkpoint or is not fully synchronized: '+name)
    print('PASS: recovery files and SHA-256 hashes verified. Snapshot:',m['created_at'])
    return m

def unpack_runtime(where):
    pg=where/'pgsql'
    if not (pg/'bin/pg_ctl.exe').exists():
        pg.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(PACKAGE/'postgres-runtime.zip') as z: z.extractall(pg)
    return pg

def occupied(port):
    with socket.socket() as s: return s.connect_ex(('127.0.0.1',port))==0

def initialize(where, port):
    if occupied(port): raise RuntimeError(f'Port {port} is already in use. Existing database was not changed.')
    pg=unpack_runtime(where);data=where/'postgres-data'
    if data.exists(): raise RuntimeError('An existing database must never be overwritten.')
    password=secrets.token_urlsafe(32);pw=where/'init-password.tmp';pw.write_text(password,encoding='utf-8')
    try: run([pg/'bin/initdb.exe','-D',data,'-U','rfone_local','--pwfile',pw,'--auth-host=scram-sha-256','--auth-local=scram-sha-256','--encoding=UTF8','--locale=C'])
    finally: pw.unlink(missing_ok=True)
    config={'host':'127.0.0.1','port':port,'user':'rfone_local','password':password,'database':'rfone_aws_copy'}
    write_json(where/'connection.json',config)
    start_database(where,config)
    env=os.environ.copy();env['PGPASSWORD']=password
    run([pg/'bin/psql.exe','-h','127.0.0.1','-p',str(port),'-U','rfone_local','-d','postgres','-c','CREATE DATABASE rfone_aws_copy'],env=env)
    run([pg/'bin/pg_restore.exe','-h','127.0.0.1','-p',str(port),'-U','rfone_local','-d','rfone_aws_copy',
         '--no-owner','--no-acl','--exit-on-error',PACKAGE/'database.dump'],env=env)
    return config

def start_database(where, config):
    pg=unpack_runtime(where)
    status=subprocess.run([str(pg/'bin/pg_ctl.exe'),'-D',str(where/'postgres-data'),'status'],capture_output=True)
    if status.returncode:
        if occupied(config['port']): raise RuntimeError('Port occupied by a different database.')
        run([pg/'bin/pg_ctl.exe','-D',where/'postgres-data','-l',where/'postgres.log','-o',f'-h 127.0.0.1 -p {config["port"]}','-w','start'])

def stop_database(where):
    # No computed target outside this task's state may ever be stopped.
    if not where.resolve().is_relative_to(AREA.resolve()): raise RuntimeError('Unsafe database directory.')
    run([where/'pgsql/bin/pg_ctl.exe','-D',where/'postgres-data','-m','fast','-w','stop'])

def verify_restore():
    import sqlalchemy as sa
    m=check();AREA.mkdir(exist_ok=True,parents=True)
    with tempfile.TemporaryDirectory(prefix='restore-test-',dir=AREA) as tmp:
        where=Path(tmp)
        if not where.resolve().is_relative_to(AREA.resolve()): raise RuntimeError('Unsafe temporary restore directory.')
        try:
            config=initialize(where,55437);engine=sa.create_engine(connection_url(config))
            with engine.connect() as c:
                for table,count in m['table_counts'].items():
                    actual=c.scalar(sa.text('SELECT count(*) FROM '+c.dialect.identifier_preparer.quote(table)))
                    if actual!=count: raise RuntimeError('Restored table count mismatch: '+table)
                assert list(c.scalars(sa.text('SELECT version_num FROM alembic_version ORDER BY version_num')))==m['revisions']
            engine.dispose();print('PASS: complete PostgreSQL restore, all table counts and schema revisions match.')
        finally:
            if (where/'postgres-data/postmaster.pid').exists(): stop_database(where)

def launch():
    import sqlalchemy as sa
    m=check(require_sources=True);owner=STATE/'owner.json'
    if owner.exists():
        lease=json.loads(owner.read_text())
        if lease['host']!=socket.gethostname() and not lease.get('released'):
            raise RuntimeError('The prior PC has not released this environment. Close it there and synchronize OneDrive.')
    if not (STATE/'connection.json').exists():
        if not (PACKAGE/'source-closed.json').exists():
            raise RuntimeError('Run Prepara cambio PC on the source computer and finish synchronizing before first local startup.')
        if socket.gethostname()==m['source_host'] and (LEGACY/'local-connection.json').exists():
            raise RuntimeError('This source PC already has the working database. Do not create a second permanent copy.')
        STATE.mkdir(parents=True,exist_ok=True);config=initialize(STATE,PORT)
    else:
        config=json.loads((STATE/'connection.json').read_text());start_database(STATE,config)
    # Relocate only known file references after a closed environment changes PCs.
    engine=sa.create_engine(connection_url(config))
    with engine.begin() as c:
        for asset in m['local_assets']:
            c.execute(sa.text(f'UPDATE {asset["table"]} SET {asset["column"]}=:new WHERE {asset["column"]}=:old'),
                      {'old':asset['old'],'new':str((PACKAGE/asset['file']).resolve())})
    engine.dispose()
    write_json(owner,{'host':socket.gethostname(),'released':False,'opened_at':datetime.now(timezone.utc).isoformat()})
    appdata=STATE/'appdata';compat=appdata/'RF-One/AWS-Copy/20261025T130037Z'
    write_json(compat/'local-connection.json',config)
    key=appdata/'RF-One/Web/session.key';key.parent.mkdir(parents=True,exist_ok=True)
    if not key.exists(): key.write_text(secrets.token_hex(32),encoding='ascii')
    # Load this PC's own protected SMTP settings before the compatibility layout
    # changes LOCALAPPDATA. Cloud/mail credentials are never synchronized here.
    import importlib.util
    smtp_path=ROOT/'03 Software/Selection/smtp_local_config.py'
    if smtp_path.exists() and not os.environ.get('RFONE_SMTP_HOST'):
        spec=importlib.util.spec_from_file_location('smtp_local_config',smtp_path)
        smtp=importlib.util.module_from_spec(spec);sys.modules[spec.name]=smtp
        spec.loader.exec_module(smtp);smtp.apply_to_environment()
    os.environ.update(LOCALAPPDATA=str(appdata),AWS_EC2_METADATA_DISABLED='true',PYTHONDONTWRITEBYTECODE='1')
    sys.path[:0]=[str(ROOT/'03 Software/RF-One Web'),str(ROOT/'03 Software/RF-One Data Store')]
    os.chdir(ROOT/'03 Software/RF-One Web')
    import visual_menu_local
    print('Open in Edge: http://127.0.0.1:5097/ — automatic existing local operator; no migrations.')
    # Open the requested system browser only once the local app answers.
    from threading import Thread
    import urllib.request
    def open_edge_when_ready():
        for attempt in range(60):
            try:
                with urllib.request.urlopen('http://127.0.0.1:5097/',timeout=2) as response:
                    if response.status==200:
                        edge=shutil.which('msedge.exe')
                        for base in [os.environ.get('PROGRAMFILES(X86)',''),os.environ.get('PROGRAMFILES','')]:
                            candidate=Path(base)/'Microsoft/Edge/Application/msedge.exe'
                            if candidate.is_file(): edge=str(candidate)
                        if edge: subprocess.Popen([edge,'http://127.0.0.1:5097/'])
                        return
            except OSError: pass
            time.sleep(1)
    Thread(target=open_edge_when_ready,daemon=True).start()
    visual_menu_local.main()

def release():
    if occupied(5097): raise RuntimeError('Close the local web-server console before releasing the database.')
    config=json.loads((STATE/'connection.json').read_text());snapshot(config,STATE/'pgsql')
    stop_database(STATE)
    write_json(STATE/'owner.json',{'host':socket.gethostname(),'released':True,'closed_at':datetime.now(timezone.utc).isoformat()})
    print('Closed. Wait for OneDrive synchronization before opening the other PC.')

def prepare_switch():
    if any(occupied(p) for p in [5094,5097,5098,5111]):
        raise RuntimeError('Close the RF-One local applications before preparing the PC switch.')
    if (STATE/'connection.json').exists(): return release()
    # Explicit source-PC handoff only; the normal snapshot never stops this instance.
    config=json.loads((LEGACY/'local-connection.json').read_text())
    if config['host']!='127.0.0.1' or config['port']!=55436 or config['database']!='rfone_aws_copy':
        raise RuntimeError('Unexpected source database; nothing stopped.')
    snapshot(config,LEGACY/'runtime/pgsql')
    run([LEGACY/'runtime/pgsql/bin/pg_ctl.exe','-D',LEGACY/'postgres-data','-m','fast','-w','stop'])
    if occupied(55436): raise RuntimeError('Source database did not close; do not switch computers.')
    write_json(PACKAGE/'source-closed.json',{'host':socket.gethostname(),'closed_at':datetime.now(timezone.utc).isoformat()})
    print('Source database closed and recovery updated. Wait for OneDrive synchronization.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['snapshot','check','verify-restore','launch','release','prepare-switch'])
    action=p.parse_args().action
    {'snapshot':snapshot,'check':check,'verify-restore':verify_restore,'launch':launch,'release':release,'prepare-switch':prepare_switch}[action]()
