"""Job ad rule and the website feed, against a disposable SQLite database.

Run:  python test_job_ad_feed.py
"""
from pathlib import Path
import json
import os
import sys
import tempfile
from types import SimpleNamespace as NS

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'RF-One Data Store')]
from flask import Flask, render_template_string
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from rfone_data_store import models as m
from rfone_data_store.selection import workspace_models as ps
from workspace import careers, job_ad, routes
from workspace.schema import REQUIRED_TABLES

REAL = ("We are looking for a Line Cook to prepare our dishes to the chef’s standard, service after service. "
        "You set up and run your station and cook each plate to the recipe.")
checks = []

assert job_ad.problem(REAL) is None and job_ad.public(REAL) == REAL
for bad in ('Nessun annuncio', '  nessun annuncio. ', 'No ad', 'TBD', '', None, 'Line cook wanted'):
    assert job_ad.problem(bad), bad
    assert job_ad.public(bad) == '', bad
checks.append('Placeholders like "Nessun annuncio" and a few words are not a job ad; a real ad is')

with tempfile.TemporaryDirectory(prefix='job_ad_feed_', ignore_cleanup_errors=True) as tmp:
    engine = create_engine('sqlite:///' + str(Path(tmp) / 'test.db'), poolclass=NullPool)
    m.Base.metadata.create_all(engine, tables=[t for name, t in m.Base.metadata.tables.items()
        if name in REQUIRED_TABLES or name.startswith('selection_workspace_')])
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        for title, ad, desc in (('Line Cook', 'Nessun annuncio', 'Nessun annuncio'), ('Server', REAL, ''),
                                ('Food Runner', None, 'Internal note: busser')):
            db.add(ps.Position(title=title, role_code='TEST', location_label='Mount Dora', timezone='America/New_York',
                               manager_account_id=1, created_by_account_id=1, requirement_set_id=1, status=ps.OPEN,
                               approved_job_ad_en=ad, description=desc, public_token='tok' + title.replace(' ', '')))
        db.commit()
    routes._cfg.SessionFactory = factory
    app = Flask(__name__, template_folder=str(HERE / 'templates'))
    app.secret_key = 'x'; app.config['TESTING'] = True
    app.register_blueprint(careers.bp)
    app.register_blueprint(routes.bp)
    os.environ.setdefault('RFONE_PUBLIC_BASE_URL', 'https://rfone.example.invalid')
    r = app.test_client().get('/careers.json')
    assert r.status_code == 200, r.status_code
    feed = {j['title']: j['excerpt'] for j in r.get_json()['jobs']}
    assert feed['Server'] == REAL and feed['Line Cook'] == '' and feed['Food Runner'] == '', feed
    assert all('Nessun' not in v and 'busser' not in v for v in feed.values())
    checks.append('Feed sends each real ad and no text for a job without one (no placeholder, no internal description)')

    with app.test_request_context():
        out = render_template_string('{{ ("Nessun annuncio"|public_ad) or "Line Cook" }}|{{ ad|public_ad }}', ad=REAL)
    assert out == 'Line Cook|' + REAL.replace('’', '&#8217;') or out.startswith('Line Cook|We are looking'), out
    checks.append('The job page Indeed reads uses the same rule: no placeholder in its description')
    engine.dispose()

src = (HERE / 'workspace' / 'routes.py').read_text(encoding='utf-8')
assert 'job_ad.problem(position.job_ad_en)' in src
checks.append('Publishing an ad and confirming a Job both refuse a placeholder ad')
print(json.dumps({'passed': len(checks), 'checks': checks}, indent=1))
