"""Local trial on the existing canonical PostgreSQL copy; never creates a DB.

python employee_registry_local.py --initialize
python employee_registry_local.py --serve [--operator rfone]
The optional operator is an explicit loopback-preview session for an existing admin.
"""
from pathlib import Path
import argparse,json,os,secrets,subprocess,sys,tempfile

WEB=Path(__file__).resolve().parent
STORE=WEB.parent/'RF-One Data Store'
ROOT=Path(os.environ['LOCALAPPDATA'])/'RF-One/AWS-Copy/20261025T130037Z'
sys.path.insert(0,str(STORE))

def configure():
    from sqlalchemy.engine import URL
    cfg=json.loads((ROOT/'local-connection.json').read_text())
    if cfg['host']!='127.0.0.1' or cfg['port']!=55434 or cfg['database']!='rfone_aws_copy':
        raise RuntimeError('Unexpected local database; no database was changed.')
    os.environ['RFONE_DATABASE_URL']=URL.create('postgresql+psycopg2',username=cfg['user'],password=cfg['password'],
        host=cfg['host'],port=cfg['port'],database=cfg['database']).render_as_string(hide_password=False)
    with tempfile.TemporaryFile() as out:
        status=subprocess.run([str(ROOT/'runtime/pgsql/bin/pg_ctl.exe'),'-D',str(ROOT/'postgres-data'),'status'],
            stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,creationflags=0x08000000)
        if status.returncode:
            start=subprocess.run([str(ROOT/'runtime/pgsql/bin/pg_ctl.exe'),'-D',str(ROOT/'postgres-data'),
                '-l',str(ROOT/'postgres.log'),'-w','start'],stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,
                creationflags=0x08000000,timeout=90)
            if start.returncode:raise RuntimeError('Cannot start the canonical local PostgreSQL database.')

def initialize():
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import create_engine,select,func
    from sqlalchemy.orm import Session
    from rfone_data_store import models as m,employee_registry as svc
    config=Config(str(STORE/'alembic.ini'));config.set_main_option('script_location',str(STORE/'migrations'))
    # The deployed branch is d5a120261021. Do not run unrelated pending branches.
    os.environ['ALEMBIC_DATABASE_URL_OVERRIDE']=os.environ['RFONE_DATABASE_URL'].replace('%','%%')
    command.upgrade(config,'e6b220261026')
    engine=create_engine(os.environ['RFONE_DATABASE_URL'])
    with Session(engine) as db:
        count=svc.initialize(db);db.commit()
        total=db.scalar(select(func.count()).select_from(m.EmployeeRegistryProfile))
        print(f'Local employee registry initialized: {total} profiles, {count} new. No source roles or names corrected automatically.')
    engine.dispose()

def serve(operator=None):
    private=Path(os.environ['LOCALAPPDATA'])/'RF-One/Web'
    private.mkdir(parents=True,exist_ok=True);key=private/'session.key'
    if not key.exists():key.write_text(secrets.token_hex(32),encoding='ascii')
    os.environ['RFONE_WEB_TEST_SECRET_KEY']=key.read_text(encoding='ascii')
    # Shared shell routes/auth remain the same. Only local cookie transport differs.
    from app import app
    app.config.update(SESSION_COOKIE_SECURE=False,SESSION_COOKIE_NAME='rfone_local',TRUSTED_HOSTS=['127.0.0.1','localhost'])
    if operator:
        from flask import request
        from db import SessionFactory
        from sqlalchemy import select
        from rfone_data_store import models as m
        from auth import log_in,load_current_account
        with SessionFactory() as db:
            account=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username==operator,m.RFOneAccount.is_admin.is_(True),m.RFOneAccount.status=='ACTIVE'))
            if account is None:raise RuntimeError('Preview operator must be an existing active RF-One administrator.')
            account_id=account.id;version=account.session_version
        @app.before_request
        def local_preview_identity():
            if request.remote_addr not in ('127.0.0.1','::1'):return 'Loopback only',403
            with SessionFactory() as db:
                if load_current_account(db) is None:log_in(account_id,version)
    print('Employee registry: http://127.0.0.1:5092/employees',flush=True)
    app.run(host='127.0.0.1',port=5092,debug=False,use_reloader=False)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--initialize',action='store_true');parser.add_argument('--serve',action='store_true');parser.add_argument('--operator')
    args=parser.parse_args()
    if not (args.initialize or args.serve):parser.error('Choose --initialize or --serve')
    configure()
    if args.initialize:initialize()
    if args.serve:serve(args.operator)
