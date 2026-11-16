"""Observation templates per Role and location, applied to Interviews; disposable SQLite, synthetic data only.

Updated 2026-11-15 (A7): the former version imported `local_runtime` (local launcher, not shipped in the
release) and copied the real local database.  The same checks now run through the release application:
AI proposal without saving, explicit save, stale-edit protection (409), validation, location isolation,
only active observations shown in Interviews, immutable interview snapshot, evidence preservation and
cross-candidate token rejection.  The AI is a fake (no network).

    python test_observation_templates.py
"""
import json
import os
import re
import shutil
import tempfile
from io import BytesIO
from unittest.mock import patch

TMP = tempfile.mkdtemp(prefix='selection_observations_')
os.environ['RFONE_DATABASE_URL'] = f"sqlite:///{os.path.join(TMP, 'rfone.db').replace(os.sep, '/')}"
os.environ['RFONE_SELECTION_UPLOAD_DIR'] = os.path.join(TMP, 'uploads')
os.environ['RFONE_SELECTION_REQUIRE_RFONE_LOGIN'] = '1'
os.environ['RFONE_WEB_BASE_URL'] = 'https://rfone.example.test'
os.environ['RFONE_FLASK_SECRET_KEY'] = 'selection-observations-secret'
os.environ['RFONE_UI_LANGUAGE'] = 'it'
for name in ('RFONE_PUBLIC_BASE_URL', 'RFONE_SELECTION_DOCUMENT_BUCKET', 'RFONE_EMAIL_FROM_ADDRESS', 'RFONE_SMTP_HOST',
             'RFONE_SMTP_USERNAME', 'RFONE_SMTP_PASSWORD', 'RFONE_SELECTION_AI', 'RFONE_SELECTION_AI_CV'):
    os.environ.pop(name, None)

import app as selection_app  # noqa: E402
from sqlalchemy import select  # noqa: E402
from workspace.schema import provision  # noqa: E402
provision(selection_app._engine)
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.selection import requirements_service as req  # noqa: E402
from rfone_data_store.selection import workspace_models as ws  # noqa: E402
from workspace import routes  # noqa: E402
from workspace.role_catalog import JobRole  # noqa: E402


def main():
    app = selection_app.app
    app.config['TESTING'] = True
    with selection_app.SessionFactory() as db:
        acc = account_svc.create_account(db, username='observations-owner', display_name='Synthetic Owner',
                                         password='synthetic-password-1', is_admin=True)
        account_svc.set_domain_access(db, account_id=acc.id, domain_code='SELECTION', enabled=True, role_code=None)
        account = (acc.id, acc.session_version)
        db.add(JobRole(code='TEST_SERVER', name='Synthetic Server', name_key='synthetic-server', active=True, version=1))
        rs = req.create_requirement_set(db, restaurant_id=routes._restaurant_id(db), name='Synthetic', target_role='TEST_SERVER')
        job = ws.Position(title='Synthetic Server', role_code='TEST_SERVER', location_label='Mount Dora',
                          timezone='America/New_York', status='OPEN', manager_account_id=acc.id,
                          created_by_account_id=acc.id, requirement_set_id=rs.id)
        db.add(job)
        # A second site of the same Role: its observation template must stay separate.
        db.add(ws.Position(title='Synthetic Server WP', role_code='TEST_SERVER', location_label='Winter Park',
                           timezone='America/New_York', status='OPEN', manager_account_id=acc.id,
                           created_by_account_id=acc.id, requirement_set_id=rs.id))
        db.commit()
        position, role, location = job.id, job.role_code, job.location_label
    client = app.test_client()
    with client.session_transaction() as sess:
        sess[shared_session.SESSION_ACCOUNT_KEY], sess[shared_session.SESSION_VERSION_KEY] = account
    page = client.get('/selection/configurazioni')
    assert page.status_code == 200
    csrf = re.search(rb'name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
    for name in ('Alex Example', 'Blake Example'):
        cv = f'{name}\n{name.split()[0].lower()}@example.test\n\nEXPERIENCE\nServer, Trattoria Prova, Mount Dora, FL\n'
        response = client.post(f'/selection/posizioni/{position}/sp/upload', data={
            'csrf_token': csrf, 'modal': '1', 'cv': (BytesIO(cv.encode()), name.split()[0] + '.txt')},
            content_type='multipart/form-data')
        assert response.status_code == 200, response.data
    with selection_app.SessionFactory() as db:
        ids = list(db.scalars(select(ws.PositionCandidate.id).where(ws.PositionCandidate.position_id == position)
                              .order_by(ws.PositionCandidate.id)))
    assert len(ids) == 2
    endpoint = '/selection/configurazioni/osservazioni'
    scope = {'role_code': role, 'location': location}
    items = [dict(id='observe', title='Priorità operative', description='Spiega come gestisce richieste simultanee.',
                  question='Due tavoli chiedono aiuto: come procedi?', active=True),
             dict(id='disabled', title='Voce disattivata', description='Descrizione', question='Domanda da non mostrare?',
                  active=False)]

    def post(operation, **values):
        return client.post(endpoint, data={'csrf_token': csrf, 'payload': json.dumps(dict(scope, operation=operation, **values))})
    with patch('workspace.rule_ai.generate', return_value={'items': items}) as ai:
        response = post('propose', items=[])
        assert response.status_code == 200, response.data
        assert ai.call_count == 1
    assert client.get(endpoint, query_string=scope).json['items'] == []  # AI never saves
    assert post('save', items=items, version=0).status_code == 200
    assert post('save', items=items, version=0).status_code == 409
    assert post('save', items=[dict(items[0], question='')], version=1).status_code == 422
    assert client.get(endpoint, query_string=dict(scope, location='Winter Park')).json['items'] == []
    interview = f'/selection/posizioni/{position}/interviews?pc={ids[0]}'
    response = client.get(interview)
    assert response.status_code == 200, response.data
    assert items[0]['question'].encode() in response.data
    assert b'Voce disattivata' not in response.data
    assert b'InterviewConfig' not in response.data
    token = re.search(rb'name="observation_snapshot" value="([^"]+)"', response.data).group(1).decode()
    changed = [dict(items[0], title='Modello aggiornato', question='Domanda aggiornata?')]
    assert post('save', items=changed, version=1).status_code == 200
    # A form opened before the model changed saves the observations it actually displayed.
    response = client.post(f'/selection/posizioni/{position}/interviews/{ids[0]}/save', data={
        'csrf_token': csrf, 'autosave': '1', 'observation_snapshot': token,
        'dim_observe_evidence': 'Evidenza conservata', 'dim_observe_rating': 'DEMONSTRATED'})
    assert response.status_code == 200, response.data
    response = client.get(interview)
    assert items[0]['question'].encode() in response.data
    assert b'Evidenza conservata' in response.data
    assert b'Domanda aggiornata?' not in response.data
    response = client.get(f'/selection/posizioni/{position}/interviews?pc={ids[1]}')
    assert b'Domanda aggiornata?' in response.data
    response = client.post(f'/selection/posizioni/{position}/interviews/{ids[1]}/save', data={
        'csrf_token': csrf, 'autosave': '1', 'observation_snapshot': token})
    assert response.status_code == 400
    print('PASS: AI proposal without save, explicit save, stale edit protection, validation, site isolation, selected observations/questions, immutable interview snapshot, evidence preservation, cross-candidate token rejection.')


if __name__ == '__main__':
    try:
        main()
    finally:
        selection_app._engine.dispose()
        shutil.rmtree(TMP, ignore_errors=True)
