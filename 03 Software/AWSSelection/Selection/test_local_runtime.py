"""Italian local workflow on the release app; disposable SQLite and synthetic data only.

Updated 2026-11-15 (A7): the former version imported `local_runtime` (the Product Owner's local launcher,
not shipped in the release) and copied the real local database.  The same workflow now runs through the
release application with RFONE_UI_LANGUAGE=it: main pages in Italian with contextual help, a Role created in
Configurations, a Draft Job saved only with CSRF and without creating accounts, and a revoked Selection
grant blocking the next request.  The launcher's loopback/host guard is not part of the release.

    python test_local_runtime.py
"""
import os
import re
import shutil
import tempfile

TMP = tempfile.mkdtemp(prefix='selection_local_workflow_')
os.environ['RFONE_DATABASE_URL'] = f"sqlite:///{os.path.join(TMP, 'rfone.db').replace(os.sep, '/')}"
os.environ['RFONE_SELECTION_UPLOAD_DIR'] = os.path.join(TMP, 'uploads')
os.environ['RFONE_SELECTION_REQUIRE_RFONE_LOGIN'] = '1'
os.environ['RFONE_WEB_BASE_URL'] = 'https://rfone.example.test'
os.environ['RFONE_FLASK_SECRET_KEY'] = 'selection-local-workflow-secret'
os.environ['RFONE_UI_LANGUAGE'] = 'it'
for name in ('RFONE_PUBLIC_BASE_URL', 'RFONE_SELECTION_DOCUMENT_BUCKET', 'RFONE_EMAIL_FROM_ADDRESS', 'RFONE_SMTP_HOST',
             'RFONE_SMTP_USERNAME', 'RFONE_SMTP_PASSWORD', 'RFONE_SELECTION_AI', 'RFONE_SELECTION_AI_CV'):
    os.environ.pop(name, None)

import app as selection_app  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from workspace.schema import provision  # noqa: E402
provision(selection_app._engine)
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.selection import workspace_models as ws  # noqa: E402
from workspace.role_catalog import JobRole  # noqa: E402


def count(table):
    with selection_app.SessionFactory() as db:
        return db.scalar(select(func.count()).select_from(table))


def main():
    checks = []
    app = selection_app.app
    app.config['TESTING'] = True
    with selection_app.SessionFactory() as db:
        acc = account_svc.create_account(db, username='local-owner', display_name='Synthetic Owner',
                                         password='synthetic-password-1', is_admin=True)
        account_svc.set_domain_access(db, account_id=acc.id, domain_code='SELECTION', enabled=True, role_code=None)
        db.commit()
        account = (acc.id, acc.session_version)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess[shared_session.SESSION_ACCOUNT_KEY], sess[shared_session.SESSION_VERSION_KEY] = account
    from flask import url_for
    with app.test_request_context('/selection/'):
        urls = {name: '/selection' + url_for(name) for name in
                ('positions.dashboard', 'positions.configuration', 'positions.requirements_priorities',
                 'positions.position_new', 'positions.how_it_works')}
    for name, url in urls.items():
        response = client.get(url, follow_redirects=True)
        assert response.status_code == 200, (name, response.status_code)
        body = response.get_data(as_text=True)
        assert 'lang="it"' in body, name
        assert 'Come funziona questa pagina' in body, name
        checks.append(name + ': 200, Italian, contextual help')
    page = client.get(urls['positions.position_new']).get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    response = client.post(urls['positions.configuration'], data={'csrf_token': token, 'name': 'Synthetic verification role'},
                           follow_redirects=True)
    assert response.status_code == 200
    with selection_app.SessionFactory() as db:
        role = db.scalar(select(JobRole.code).where(JobRole.name == 'Synthetic verification role'))
    assert role
    checks.append('Role created in Configurations')
    candidate_accounts = m.Base.metadata.tables['selection_candidate_accounts']
    before, accounts = count(ws.Position), count(m.RFOneAccount)
    form = dict(title='Local verification', role_code=role, location='Local verification', headcount='1',
                manager_account_id=str(account[0]), timezone='America/New_York', description='Synthetic local trial')
    client.post(urls['positions.position_new'], data=form)
    assert count(ws.Position) == before
    form['csrf_token'] = token
    response = client.post(urls['positions.position_new'], data=form, follow_redirects=True)
    assert response.status_code == 200
    assert count(ws.Position) == before + 1
    assert count(m.RFOneAccount) == accounts
    assert count(candidate_accounts) == 0
    checks.append('Draft creation persists only with CSRF; no internal/candidate account created')
    with selection_app.SessionFactory() as db:
        account_svc.set_domain_access(db, account_id=account[0], domain_code='SELECTION', enabled=False, role_code=None)
        db.commit()
    assert client.get('/selection/').status_code == 403
    checks.append('Revoking the existing Selection grant blocks the next request')
    print('\n'.join(checks), flush=True)


if __name__ == '__main__':
    try:
        main()
    finally:
        selection_app._engine.dispose()
        shutil.rmtree(TMP, ignore_errors=True)
    print('Disposable database removed; no real database used.', flush=True)
