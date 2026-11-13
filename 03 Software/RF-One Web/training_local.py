"""Canonical database, loopback-only Training workspace. Never installed on AWS."""
from pathlib import Path
import argparse, importlib.util, json, os, sys

WEB=Path(__file__).resolve().parent
STORE=WEB.parent/'RF-One Data Store'
PRIVATE=Path('C:/Users/servi/AppData/Local/RF-One')
sys.path.insert(0,str(STORE))


def configure():
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL
    cfg=json.loads((PRIVATE/'AWS-Copy/20261025T130037Z/local-connection.json').read_text())
    if (cfg['host'],cfg['port'],cfg['database'])!=('127.0.0.1',55436,'rfone_aws_copy'):
        raise RuntimeError('Only the existing canonical local database is allowed.')
    url=URL.create('postgresql+psycopg2',username=cfg['user'],password=cfg['password'],host=cfg['host'],port=cfg['port'],database=cfg['database'])
    os.environ['RFONE_DATABASE_URL']=url.render_as_string(hide_password=False)
    os.environ['RFONE_WEB_TEST_SECRET_KEY']=(PRIVATE/'Web/session.key').read_text(encoding='ascii')
    # Reuse the existing Windows-user-protected SMTP settings; never copy secrets.
    smtp_path=WEB.parent/'Selection/smtp_local_config.py'
    spec=importlib.util.spec_from_file_location('rfone_local_smtp',smtp_path)
    smtp=importlib.util.module_from_spec(spec);spec.loader.exec_module(smtp)
    if not os.environ.get('RFONE_SMTP_HOST'):smtp.apply_to_environment()
    os.environ.setdefault('RFONE_EMAIL_FROM_ADDRESS','RFOne@romesflavours.com')
    return create_engine(url)


def initialize_student_registry(engine):
    """Explicit additive local migration; no account/grant or historical data writes."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    path=STORE/'migrations/versions/t9b120261112_student_registry.py'
    spec=importlib.util.spec_from_file_location('student_registry_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    if engine.url.host!='127.0.0.1' or engine.url.port!=55436 or engine.url.database!='rfone_aws_copy':
        raise RuntimeError('Only the canonical loopback database is allowed.')
    with engine.begin() as c:
        c.execute(text('LOCK TABLE alembic_version IN EXCLUSIVE MODE'))
        versions=c.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
        if versions==[migration.revision]:return
        if versions!=[migration.down_revision]:raise RuntimeError('Unexpected local revision; no changes applied.')
        with Operations.context(MigrationContext.configure(c)):migration.upgrade()
        c.execute(text('UPDATE alembic_version SET version_num=:new WHERE version_num=:old'),dict(new=migration.revision,old=migration.down_revision))
    print('PASS: additive student Registry schema; existing records and permissions unchanged.')


def initialize(engine):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    path=STORE/'migrations/versions/e6f120261109_training_student_profiles.py'
    spec=importlib.util.spec_from_file_location('training_workspace_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with engine.begin() as c:
        c.execute(text('LOCK TABLE alembic_version IN EXCLUSIVE MODE'))
        current=c.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
        if current in ([migration.revision],['e7f120261110'],['e9f120261110']):
            print('Training local schema already initialized.');return
        if current!=[migration.down_revision]:
            raise RuntimeError('Unexpected schema version; unrelated migrations will not be applied.')
        with Operations.context(MigrationContext.configure(c)):migration.upgrade()
        c.execute(text('UPDATE alembic_version SET version_num=:new WHERE version_num=:old'),dict(new=migration.revision,old=migration.down_revision))
    print('Training local schema initialized; existing records preserved.')


def retire_dish_catalog(engine):
    """Explicit local-only PO instruction: retain Visual Menu as the sole course."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    path=STORE/'migrations/versions/e7f120261110_training_retired_catalog.py'
    spec=importlib.util.spec_from_file_location('training_catalog_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with engine.begin() as c:
        c.execute(text('LOCK TABLE alembic_version IN EXCLUSIVE MODE'))
        versions=c.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
        if versions==[migration.down_revision]:
            with Operations.context(MigrationContext.configure(c)):migration.upgrade()
            c.execute(text('UPDATE alembic_version SET version_num=:new WHERE version_num=:old'),dict(new=migration.revision,old=migration.down_revision))
        elif versions!=[migration.revision]:
            raise RuntimeError('Unexpected local schema '+repr(versions)+'; no catalog changes applied.')
        c.execute(text('LOCK TABLE training_pills IN SHARE ROW EXCLUSIVE MODE'))
        visual=c.execute(text("SELECT id FROM training_pills WHERE slug='visual-menu'")).scalars().all()
        if len(visual)!=1:raise RuntimeError('The existing Visual Menu course must be present before retiring anything.')
        before=dict(c.execute(text('SELECT \'assignments\',count(*) FROM training_assignments UNION ALL SELECT \'questions\',count(*) FROM training_questions')).all())
        c.execute(text('INSERT INTO training_retired_pills(pill_id) SELECT id FROM training_pills WHERE id<>:keep ON CONFLICT(pill_id) DO NOTHING'),dict(keep=visual[0]))
        c.execute(text('DELETE FROM training_retired_pills WHERE pill_id=:keep'),dict(keep=visual[0]))
        active=c.execute(text('SELECT title FROM training_pills p WHERE NOT EXISTS (SELECT 1 FROM training_retired_pills r WHERE r.pill_id=p.id)')).scalars().all()
        assert active==['Visual Menu'],active
        after=dict(c.execute(text('SELECT \'assignments\',count(*) FROM training_assignments UNION ALL SELECT \'questions\',count(*) FROM training_questions')).all())
        assert before==after
        count=c.scalar(text('SELECT count(*) FROM training_retired_pills'))
    print(f'PASS: {count} entries withdrawn from the local catalog; only Visual Menu is available. Assignment and question history preserved.')


def initialize_courses(engine):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from rfone_data_store.training import courses
    path=STORE/'migrations/versions/e9f120261110_training_course_repository.py'
    spec=importlib.util.spec_from_file_location('training_courses_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.execute(text('LOCK TABLE alembic_version IN EXCLUSIVE MODE'))
        versions=connection.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
        if versions==[migration.down_revision]:
            with Operations.context(MigrationContext.configure(connection)):migration.upgrade()
            connection.execute(text('UPDATE alembic_version SET version_num=:new WHERE version_num=:old'),dict(new=migration.revision,old=migration.down_revision))
        elif versions!=[migration.revision]:
            raise RuntimeError('Unexpected local schema '+repr(versions)+'; no course changes applied.')
        with Session(bind=connection,join_transaction_mode='create_savepoint') as db:
            courses.initialize_visual_menu(db);db.commit()
    print('PASS: canonical local course repository initialized; existing Visual Menu retained.')


def create_app(*,factory=None,automatic_operator=True):
    import app as shell
    import auth
    from db import SessionFactory
    from flask import request,abort,session
    from sqlalchemy import select
    from rfone_data_store import models as m
    from training_workspace_routes import install
    factory=factory or SessionFactory
    app=shell.app
    app.config['TRAINING_ENROLLMENT_LOCAL']=True
    app.config.update(SESSION_COOKIE_SECURE=False,SESSION_COOKIE_NAME='rfone_training_local',TRUSTED_HOSTS=['127.0.0.1','localhost'],MAX_CONTENT_LENGTH=30*1024*1024,MAX_FORM_MEMORY_SIZE=2*1024*1024)
    @app.errorhandler(413)
    def training_upload_too_large(error):
        from flask import jsonify
        return jsonify(error='Il salvataggio supera 30 MB. Carica i materiali in più passaggi.'),413
    if automatic_operator:
        app.config['RFONE_LOCAL_OPERATOR']='rfone'
    # The only English strings introduced by the identical shared help component.
    app.jinja_env.globals['ui']=lambda value:{'How this page works':'Come funziona','Close':'Chiudi'}.get(value,value)
    install(app,SessionFactory=factory,auth=auth)
    @app.before_request
    def local_operator():
        if request.remote_addr not in ('127.0.0.1','::1'):abort(403)
        if not automatic_operator or not request.path.startswith(('/training/manage','/visual-menu','/training/visual-menu','/myrf/visual-menu','/people','/employees')):return None
        if session.get('tw_student_session'):return None
        with factory() as db:
            if auth.load_current_account(db) is not None:return None
            operator=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username=='rfone',m.RFOneAccount.status=='ACTIVE'))
            if not operator:abort(403)
            auth.log_in(operator.id,operator.session_version)
    # Operator sign-in must precede all shared SSO/access gates.
    hooks=app.before_request_funcs[None]
    hooks.insert(0,hooks.pop())
    # Enforce first-access replacement before any shared page can run.
    gate=next(h for h in hooks if h.__name__=='first_access_gate')
    hooks.remove(gate);hooks.insert(1,gate)
    return app


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--initialize',action='store_true');parser.add_argument('--serve',action='store_true');parser.add_argument('--test',action='store_true');parser.add_argument('--verify',action='store_true');parser.add_argument('--retire-dish-catalog',action='store_true');parser.add_argument('--restart',action='store_true');parser.add_argument('--initialize-courses',action='store_true');parser.add_argument('--test-courses',action='store_true')
    parser.add_argument('--initialize-student-registry',action='store_true')
    parser.add_argument('--initialize-enrollment',action='store_true')
    args=parser.parse_args()
    engine=configure()
    if args.initialize_enrollment:
        from initialize_training_enrollment import initialize
        initialize(engine)
    if args.initialize_student_registry:initialize_student_registry(engine)
    if args.initialize:initialize(engine)
    if args.retire_dish_catalog:retire_dish_catalog(engine)
    if args.initialize_courses:initialize_courses(engine)
    if args.test_courses:
        from tests_training_courses import run
        run(engine)
    if args.test:
        from tests_training_workspace import run
        run(engine)
    if args.verify:
        from http.client import HTTPConnection
        connection=HTTPConnection('127.0.0.1',5098,timeout=10)
        cookie=None
        for path in ('/training/manage/content','/training/manage/students','/visual-menu?from=training','/static/js/rf-one-row-return.js','/static/js/training-workspace.js','/static/js/training-courses.js','/static/css/training-workspace.css'):
            connection.request('GET',path,headers={'Cookie':cookie} if cookie else {})
            response=connection.getresponse();body=response.read().decode('utf-8')
            assert response.status==200,(path,response.status)
            if response.getheader('Set-Cookie'):cookie=response.getheader('Set-Cookie').split(';')[0]
            if path.startswith('/training/manage'):
                assert '>Assegnazioni<' not in body
                assert 'Come funziona' in body and 'lang="it"' in body
            if path=='/training/manage/students':
                assert 'student-assignment-editor' in body and 'Contenuti disponibili' in body
            if path=='/training/manage/content':
                assert 'Visual Menu' in body and 'Descrizione' in body and 'Contenuti' in body and '/visual-menu/manage' in body
                assert 'id="new-course"' in body and 'Salva bozza' in body and 'Rendi disponibile' in body
            if path.startswith('/visual-menu'):
                assert '<h1>Visual Menu</h1>' in body and 'href="/kitchen' not in body
        connection.close()
        print('PASS: live local management pages open as the existing operator without credentials; help and all Training assets respond.')
    engine.dispose()
    if args.serve:
        if args.restart:
            import subprocess
            script="""$trainingProcesses=Get-CimInstance Win32_Process -Filter \"name='python.exe' AND CommandLine LIKE '%training_local.py%'\";
foreach($trainingProcess in $trainingProcesses){
if($trainingProcess.ProcessId -ne CURRENT_PID -and $trainingProcess.CommandLine -match '[\\/]RF-One Web[\\/]training_local\\.py' -and $trainingProcess.CommandLine -match '--serve'){
Stop-Process -Id $trainingProcess.ProcessId -ErrorAction Stop
}}
""".replace('CURRENT_PID',str(os.getpid()))
            result=subprocess.run(['powershell.exe','-NoProfile','-Command',script],capture_output=True,text=True,creationflags=0x08000000,timeout=30)
            if result.returncode:raise RuntimeError('Could not stop the previous local Training server.')
        app=create_app()
        print('Training: http://127.0.0.1:5098/training/manage',flush=True)
        app.run(host='127.0.0.1',port=5098,debug=False,use_reloader=False)
