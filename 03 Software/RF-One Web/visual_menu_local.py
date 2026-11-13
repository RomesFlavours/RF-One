"""Loopback-only RF-One shell with the explicitly approved local operator session."""
from pathlib import Path
import os
import sys


def main():
    if '--stop-instances' in sys.argv:
        import subprocess, json, signal
        port=5098 if '--training' in sys.argv else 5097
        script='training_local.py' if '--training' in sys.argv else 'visual_menu_local.py'
        lines=subprocess.check_output(['netstat','-ano','-p','tcp'],text=True)
        pids=set()
        for line in lines.splitlines():
            fields=line.split()
            if len(fields)==5 and fields[1].endswith(':'+str(port)) and fields[3]=='LISTENING':
                pids.add(int(fields[4]))
        for pid in pids:
            command=f'(Get-CimInstance Win32_Process -Filter "ProcessId = {pid}").CommandLine'
            args=subprocess.check_output(['powershell','-NoProfile','-Command',command],text=True).strip()
            if script not in args:
                raise RuntimeError(f'Port {port} belongs to another application; it was not stopped.')
            os.kill(pid,signal.SIGTERM)
            print('Stopped local server',script,pid)
        return
    if '--accounts' in sys.argv:
        sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'RF-One Data Store'))
        from import_kitchen_excel import local_engine
        from sqlalchemy import text
        engine=local_engine()
        with engine.connect() as db:
            print(db.execute(text("SELECT id,username FROM rfone_accounts WHERE status='ACTIVE' AND is_admin=true ORDER BY id")).all())
            print(db.execute(text("SELECT account_id,enabled,scope FROM rfone_account_domain_access WHERE domain_code='KITCHEN'")).all())
        engine.dispose()
        return
    if '--verify' in sys.argv:
        from http.client import HTTPConnection
        connection = HTTPConnection('127.0.0.1',5097,timeout=5)
        sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'RF-One Data Store'))
        from import_kitchen_excel import local_engine
        from rfone_data_store.visual_menu_active import read_home
        with local_engine().connect() as db:locations=read_home(db)
        checked=0
        for location in locations:
            for area in location['areas']:
                for dish in area['entries']:
                    if not dish['recipe_id']:continue
                    path=f"/visual-menu/locations/{location['location_id']}/entries/{dish['id']}"
                    connection.request('GET',path);response=connection.getresponse();body=response.read().decode('utf-8')
                    assert response.status==200 and 'Components' in body and '<h1>Visual Menu</h1>' in body
                    assert 'href="/kitchen' not in body
                    if dish['photo_uri'] and not dish['photo_uri'].startswith(('http:','https:')):
                        connection.request('GET',path+'/photo');photo=connection.getresponse()
                        assert photo.status==200 and photo.getheader('Content-Type').startswith('image/')
                        assert photo.read()
                    checked+=1
        for path in ('/visual-menu','/training/manage/content','/visual-menu?from=myrf'):
            connection.request('GET',path)
            page=connection.getresponse();body=page.read().decode('utf-8')
            assert page.status==200,(path,page.status)
            assert 'Visual Menu' in body
            if path.endswith('from=myrf'):
                assert 'Save phrases' not in body
        connection.close()
        print(f'PASS: Visual Menu opens without login; {checked} active dish cards verified with current Kitchen photos.')
        return
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'RF-One Data Store'))
    from import_kitchen_excel import local_engine
    engine = local_engine()
    os.environ['RFONE_DATABASE_URL'] = engine.url.render_as_string(hide_password=False)
    engine.dispose()
    key = Path(os.environ['LOCALAPPDATA'])/'RF-One/Web/session.key'
    if not key.is_file():
        raise RuntimeError('Configure the existing local RF-One Web session key first.')
    os.environ['RFONE_WEB_TEST_SECRET_KEY'] = key.read_text(encoding='ascii')
    from app import app
    app.jinja_env.globals['ui']=lambda value:{'How this page works':'Come funziona','Close':'Chiudi'}.get(value,value)
    # Same local HTTP cookie convention as employee_registry_local.py; never deployed.
    app.config.update(SESSION_COOKIE_SECURE=False, SESSION_COOKIE_NAME='rfone_local',
                      TRUSTED_HOSTS=['127.0.0.1','localhost'])
    from db import SessionFactory
    from auth import load_current_account, log_in
    from local_operator_session import install_local_operator_session
    install_local_operator_session(app,SessionFactory=SessionFactory,
        load_current_account=load_current_account,log_in=log_in)
    import auth
    from training_workspace_routes import install
    if 'tw_content' not in app.view_functions:
        install(app,SessionFactory=SessionFactory,auth=auth)
    app.run(host='127.0.0.1',port=5097,debug=False,use_reloader=False)


if __name__ == '__main__':
    main()
