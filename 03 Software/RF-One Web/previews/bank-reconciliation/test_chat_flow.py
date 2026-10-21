"""Confirmation and no-classification-write regression checks on a disposable DB."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

from flask import Flask, abort, request
from jinja2 import DictLoader
from sqlalchemy.orm import sessionmaker

ROOT=Path(__file__).resolve().parents[4]
CODE=Path('C:/Users/servi/OneDrive/AI-RF-ONE/rf-one-bank-simple-who-rules/03 Software/RF-One Data Store')
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(CODE));sys.dont_write_bytecode=True
from rfone_data_store.database import create_configured_engine
from rfone_data_store.bank_reconciliation import ai_rules

scratch=ROOT/'03 Software/RF-One Data Store/data/why_codex_chat_test_20261017'
scratch.mkdir(exist_ok=True)
dbpath=scratch/'chat_rule_lifecycle_final.db'
assert not dbpath.exists(), 'Use a fresh disposable database'
with sqlite3.connect('file:C:/Users/servi/AppData/Local/RF-One/Bank/rfone.db?mode=ro',uri=True) as source,sqlite3.connect(dbpath) as target:source.backup(target)
engine=create_configured_engine('sqlite:///'+dbpath.as_posix())
spec=importlib.util.spec_from_file_location('chat_test_routes',HERE/'bank_assistant_preview_routes.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
app=Flask(__name__);app.secret_key='disposable-test-only'
app.jinja_loader=DictLoader({'bank_assistant_preview.html':(HERE/'index.html').read_text(encoding='utf-8')})
app.jinja_env.globals['csrf_token']=lambda:'test-csrf'
account=[1]
def csrf():
    if request.form.get('csrf_token')!='test-csrf':abort(400)
module.register_bank_assistant_preview_routes(app,gate=lambda fn:fn,SessionFactory=sessionmaker(bind=engine),
    require_csrf=csrf,load_current_account=lambda db:SimpleNamespace(id=account[0]))
client=app.test_client()
rule='Se la descrizione contiene "TEMU", assegna WHY "RESTAURANT_OPERATING_SUPPLIES". Lascia invariati WHO e For Whom. Mantieni protette le decisioni manuali.'
raw={'kind':'STRUCTURED','conditions':[{'field':'description','op':'contains','value':'TEMU'}],
    'who':None,'why':{'mode':'fixed','name':'RESTAURANT_OPERATING_SUPPLIES'},'for_whom':None,'status':None,
    'only_if_who_differs':False,'replace_existing':False,'branches':[],
    'coverage':[{'instruction':'Se la descrizione contiene TEMU','represented_by':'conditions description contains'},
                {'instruction':'Assegna WHY RESTAURANT_OPERATING_SUPPLIES','represented_by':'why fixed'},
                {'instruction':'Lascia invariati WHO e For Whom','represented_by':'who null and for_whom null'},
                {'instruction':'Mantieni protette le decisioni manuali','represented_by':'built-in protection'}],
    'unsupported':[]}
answer={'ready':True,'reply':'Ho capito: i movimenti con TEMU sono forniture operative per il ristorante.',
        'rule_text':rule,'interpretation':raw}
mode=['ready'];calls=[0]
def generate(prompt):
    calls[0]+=1
    if mode[0]=='clarify':return {'ready':False,'reply':'Vale per tutte le carte o solo per quelle aziendali?'}
    if mode[0]=='invalid':
        result=deepcopy(answer);result['interpretation']['unsupported']=['unsupported operation'];return result
    return deepcopy(answer)
module.bank_chatgpt.generate_json=generate
os.environ['RFONE_BANK_AI_MODE']='SESSION'

def snapshot():
    with sqlite3.connect(dbpath) as conn:
        return {table:conn.execute('SELECT * FROM '+table+' ORDER BY id').fetchall()
                for table in ('financial_transactions','bank_transaction_explanations','bank_transaction_allocations','bank_occurrences')}

before=snapshot()
assert client.get('/bank/ai-rules').status_code==200
assert client.post('/bank/ai-rules/chat').status_code==400
params={'csrf_token':'test-csrf','who_id':'113','messages':json.dumps([{'role':'assistant','text':'Cosa sono questi acquisti TEMU?'},{'role':'user','text':'Forniture per il ristorante.'}]),'general_rules':'[]'}
assert client.post('/bank/ai-rules/chat',data=params).status_code==403
assert calls[0]==0,'Missing authorization still called the provider'
app.config['BANK_CHAT_PROVIDER_CONTEXT_APPROVED']=True # Mocked provider only; no external calls in this test.
mode[0]='clarify';response=client.post('/bank/ai-rules/chat',data=params).get_json();assert not response['ready'] and 'confirmation_token' not in response
mode[0]='invalid';response=client.post('/bank/ai-rules/chat',data=params).get_json();assert not response['ready'] and 'confirmation_token' not in response
mode[0]='ready';response=client.post('/bank/ai-rules/chat',data=params);assert response.status_code==200,response.get_data(as_text=True)
draft=response.get_json();assert draft['ready'] and draft['rule_text']==rule
assert snapshot()==before,'Chat changed operational data'
assert client.post('/bank/ai-rules/chat/preview',data={'csrf_token':'test-csrf','confirmation_token':draft['confirmation_token']}).status_code==400
assert client.post('/bank/ai-rules/chat/preview',data={'csrf_token':'test-csrf','confirmed':'yes','confirmation_token':'tampered'}).status_code==400
payload={'csrf_token':'test-csrf','confirmed':'yes','confirmation_token':draft['confirmation_token']}
account[0]=2;assert client.post('/bank/ai-rules/chat/preview',data=payload).status_code==403
account[0]=1;call_count=calls[0]
response=client.post('/bank/ai-rules/chat/preview',data=payload)
assert response.status_code==200,response.get_data(as_text=True)
preview=response.get_json()
assert preview['ok'] and preview['scope']==ai_rules.SCOPE_ALL
assert preview['confirmed_rule']==rule
assert preview['examined']+preview['excluded_from_scope']==preview['database_total']
assert preview['database_total']==len(before['financial_transactions'])
assert len(preview['match_items'])+len(preview['doubt_items'])==preview['matches']+preview['doubts']
assert calls[0]==call_count,'Confirmed rule was reinterpreted by AI'
assert snapshot()==before,'Preview applied classifications or changed WHO/allocation data'
# Persisted rule survives a fresh request and is refined in place, not duplicated.
rule_id=preview['saved_rule_id']
queue=client.get('/bank/ai-rules/snapshot').get_json()
assert any(r['id']==rule_id for r in queue['learned_rules'])
covered_ids={row['id'] for case in queue['cases'] for row in case['rows'] if row['covered']}
update_ids={item['id'] for item in preview['match_items'] if item['plan']=='UPDATED'}
assert update_ids <= covered_ids
problem_ids={item['id'] for item in preview['match_items'] if item['plan']=='CONFLICT'}
queue_ids={row['id'] for case in queue['cases'] for row in case['rows'] if not row['covered']}
assert problem_ids <= queue_ids
params['rule_id']=str(rule_id)
refinement=client.post('/bank/ai-rules/chat',data=params).get_json()
assert refinement['ready']
again=client.post('/bank/ai-rules/chat/preview',data={'csrf_token':'test-csrf','confirmed':'yes','confirmation_token':refinement['confirmation_token']}).get_json()
assert again['saved_rule_id']==rule_id
assert len([r for r in client.get('/bank/ai-rules/snapshot').get_json()['learned_rules'] if r['id']==rule_id])==1
assert snapshot()==before
result=dict(checks_passed=True, durable_rule=True, exceptions_requeued=True, refinement_same_rule=True,database_total=preview['database_total'],examined=preview['examined'],
            matches=preview['matches'],updates=preview['planned_updates'],protected=preview['protected'],
            conflicts=preview['conflicts'],no_second_ai_call=True,no_operational_writes=True)
(scratch/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result));engine.dispose()
