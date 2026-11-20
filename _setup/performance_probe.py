"""Read-only comparative probe; runs only against the isolated performance backup."""
import json
from pathlib import Path
import sys
import time
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / 'backups' / 'performance-20261117'
baseline = '--baseline' in sys.argv
CODE = BACKUP / 'baseline' if baseline else ROOT
sys.path[:0] = [str(CODE), str(CODE / '03 Software/RF-One Web'),
                str(CODE / '03 Software/RF-One Data Store')]
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from flask import Flask
from rfone_data_store.bank_reconciliation import who_search_text
import bank_why_signals

engine = create_engine('sqlite:///' + (BACKUP / 'baseline.db').as_posix())
factory = sessionmaker(engine)
queries = []
event.listen(engine, 'before_cursor_execute', lambda c, cu, s, p, ctx, many: queries.append(s))
result = {}
for repeat in range(2):
    queries.clear()
    start = time.perf_counter()
    with factory() as db:
        rows = who_search_text.movements(db)
    result['who_' + str(repeat)] = dict(seconds=time.perf_counter()-start, queries=len(queries),
        settlement_reads=sum('FROM bank_card_settlement_accounts' in q for q in queries),
        version_reads=sum('FROM bank_ai_rule_versions' in q for q in queries))
    if repeat == 0:
        (BACKUP / ('before-rows.json' if baseline else 'after-rows.json')).write_text(
            json.dumps(rows, ensure_ascii=False), encoding='utf-8')
app = Flask(__name__)
bank_why_signals.register(app, gate=lambda f:f, SessionFactory=factory,
    require_csrf=lambda:None, owner=lambda db:None, endpoint=lambda f:f)
queries.clear()
start = time.perf_counter()
with app.test_client() as client:
    response = client.get('/bank/why-signals/editor-data')
    assert response.status_code == 200, response.data
result['why_editor'] = dict(seconds=time.perf_counter()-start, queries=len(queries))
(BACKUP / ('before-editor.json' if baseline else 'after-editor.json')).write_text(
    json.dumps(response.get_json(), ensure_ascii=False), encoding='utf-8')
(BACKUP / ('before-timing.json' if baseline else 'after-timing.json')).write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
engine.dispose()
