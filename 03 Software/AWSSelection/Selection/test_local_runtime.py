"""Local workflow test using a disposable copy; never changes the live database."""
from pathlib import Path
from contextlib import closing, ExitStack
import re
import sqlite3
import tempfile
from unittest.mock import patch
import local_runtime as runtime


def main():
    source = runtime.existing_database()
    with tempfile.TemporaryDirectory(prefix='rfone-selection-check-') as tmp, ExitStack() as cleanup:
        path = Path(tmp) / 'test.db'
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src:
            with closing(sqlite3.connect(path)) as dst:
                src.backup(dst)
        with patch.object(runtime, 'existing_database', return_value=path):
            app = runtime.create_application()
            import sys
            cleanup.callback(sys.modules['selection_app']._engine.dispose)
            app.config['TESTING'] = True
            client = app.test_client()
            base = 'http://127.0.0.1:5096'
            checks = []
            from flask import url_for
            with app.test_request_context('/selection/',base_url=base):
                urls = {name: '/selection' + url_for(name) for name in
                    ('positions.dashboard','positions.configuration','positions.requirements_priorities','positions.position_new','positions.how_it_works')}
            # url_for has no SCRIPT_NAME in this synthetic context.
            for name, url in urls.items():
                response = client.get(url, base_url=base, follow_redirects=True)
                assert response.status_code == 200, (name,response.status_code)
                body = response.get_data(as_text=True)
                assert 'lang="it"' in body, name
                assert 'Come funziona questa pagina' in body, name
                checks.append(name + ': 200, Italian, contextual help')
            assert client.get('/selection/',base_url=base,environ_overrides={'REMOTE_ADDR':'192.0.2.1'}).status_code == 403
            assert client.get('/selection/',base_url='http://invalid.example:5096').status_code in (400,403)
            checks.append('Non-loopback clients and foreign hosts refused')
            response = client.get(urls['positions.position_new'],base_url=base)
            token = re.search(r'name="csrf_token" value="([^"]+)"',response.get_data(as_text=True)).group(1)
            response=client.post(urls['positions.configuration'],base_url=base,
                data={'csrf_token':token,'name':'Synthetic verification role'},follow_redirects=True)
            assert response.status_code==200
            with closing(sqlite3.connect(path)) as db:
                role=db.execute("select code from selection_workspace_job_roles where name='Synthetic verification role'").fetchone()[0]
                before=db.execute('select count(*) from selection_workspace_positions').fetchone()[0]
                accounts=db.execute('select count(*) from rfone_accounts').fetchone()[0]
            form=dict(title='Local verification',role_code=role,location='Local verification',
                headcount='1',manager_account_id='1',timezone='America/New_York',description='Synthetic local trial')
            client.post(urls['positions.position_new'],base_url=base,data=form)
            with closing(sqlite3.connect(path)) as db:
                assert db.execute('select count(*) from selection_workspace_positions').fetchone()[0]==before
            form['csrf_token']=token
            response=client.post(urls['positions.position_new'],base_url=base,data=form,follow_redirects=True)
            assert response.status_code==200
            with closing(sqlite3.connect(path)) as db:
                assert db.execute('select count(*) from selection_workspace_positions').fetchone()[0]==before+1
                assert db.execute('select count(*) from rfone_accounts').fetchone()[0]==accounts
                assert db.execute('select count(*) from selection_candidate_accounts').fetchone()[0]==0
            checks.append('Draft creation persists only with CSRF; no internal/candidate account created')
            with closing(sqlite3.connect(path)) as db:
                db.execute("UPDATE rfone_account_domain_access SET enabled=0 WHERE domain_code='SELECTION' AND account_id=1")
                db.commit()
            assert client.get('/selection/',base_url=base).status_code==403
            checks.append('Revoking the existing Selection grant blocks the next request')
            print('\n'.join(checks),flush=True)
    print('Disposable database removed; live data untouched by the workflow test.',flush=True)


if __name__ == '__main__':
    main()
