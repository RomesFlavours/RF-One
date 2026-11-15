"""Role catalogue and its actual HTTP forms, using only disposable memory data."""
from pathlib import Path
import os
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'RF-One Data Store')]
os.environ['RFONE_UI_LANGUAGE'] = 'it'

from flask import Flask, request
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from workspace import role_catalog as roles, routes, sp_queue
sp_queue.kick = lambda *args, **kwargs: None
from rfone_data_store.selection import workspace_models as ps
from local_i18n import install

engine = create_engine('sqlite://')
roles.initialize(engine)
from rfone_data_store.models import Base
Base.metadata.create_all(engine)
factory = sessionmaker(engine)
routes._cfg.SessionFactory = factory
routes._cfg.rfone_web_base_url = lambda: 'http://localhost'
routes.current_account = lambda db: None if request.headers.get('X-Test-Actor') == 'anonymous' else SimpleNamespace()
routes.actor_for = lambda db, account: SimpleNamespace(is_owner=request.headers.get('X-Test-Actor', 'owner') == 'owner')
app = Flask(__name__, template_folder=str(HERE / 'templates'))
app.secret_key = 'in-memory-test-only'
app.config['TESTING'] = True
app.register_blueprint(routes.bp)
install(app)
client = app.test_client()
with client.session_transaction() as session:
    from rfone_data_store import rfone_web_session as shared
    session[shared.SESSION_CSRF_KEY] = 'csrf-test'

with factory() as db:
    assert db.scalar(select(func.count()).select_from(roles.JobRole)) == 0
    historical = ps.Position(title='Original title', role_code='SERVER', location_label='Original location', timezone='America/New_York', manager_account_id=1, created_by_account_id=1, requirement_set_id=1)
    db.add(historical)
    db.commit()
    historical_id = historical.id
    db.add(roles.JobRole(code='SERVER', name='Cameriere', name_key='archived:SERVER', active=False, version=1))
    db.commit()
    assert db.get(ps.Position, historical_id).role_code == 'SERVER'
    assert db.get(ps.Position, historical_id).title == 'Original title'
    assert 'SERVER' not in dict(roles.choices(db))
    assert 'SERVER' in dict(roles.choices(db, current='SERVER'))

response = client.get('/configurazioni')
assert response.status_code == 200
assert 'Configurazioni' in response.get_data(as_text=True)
assert 'lang="it"' in response.get_data(as_text=True)
payload = {'csrf_token': 'csrf-test', 'name': 'Responsabile eventi'}
assert client.post('/configurazioni', data=payload, headers={'X-Test-Actor': 'manager'}).status_code == 403
assert client.get('/configurazioni', headers={'X-Test-Actor': 'anonymous'}).status_code == 302
assert client.post('/configurazioni', data={**payload, 'csrf_token': 'bad'}).status_code == 302
with factory() as db:
    assert db.scalar(select(func.count()).select_from(roles.JobRole).where(roles.JobRole.active.is_(True))) == 0
assert client.post('/configurazioni', data=payload).status_code == 302
assert client.post('/configurazioni', data={**payload, 'name': '  responsabile EVENTI '}).status_code == 422
assert client.post('/configurazioni', data={**payload, 'name': ' '}).status_code == 422
with factory() as db:
    role = db.scalar(select(roles.JobRole).where(roles.JobRole.name == payload['name']))
    code, version = role.code, role.version
    roles.save(db, code=code, name='Coordinatore eventi', version=version)
    db.commit()
    assert roles.enabled(db, code) is True
    assert dict(roles.choices(db, current=code))[code] == 'Coordinatore eventi'
assert client.post('/configurazioni', data={**payload, 'code': code, 'version': version}).status_code == 422
with factory() as db:
    assert db.get(roles.JobRole, code).name == 'Coordinatore eventi'

# Translation must never rewrite endpoint names, form keys, enums or facts.
template = app.jinja_env.from_string("{{ url_for('positions.configuration') }}|{{ data['name'] }}|{{ state == 'DRAFT' }}|<span>New Job</span>")
with app.test_request_context('/'):
    rendered = template.render(data={'name': 'Server'}, state='DRAFT')
    assert rendered == '/configurazioni|Server|True|<span>Nuova posizione</span>', rendered
if '--serve' not in sys.argv:
    engine.dispose()
print('PASS: empty initialization, name-only creation/edit, persistence, historical preservation, duplicate/blank validation, CSRF, owner-only writes, stale edit protection and literal translation boundaries')

if '--serve' in sys.argv:
    app.run(host='127.0.0.1', port=5113, threaded=False, use_reloader=False)
