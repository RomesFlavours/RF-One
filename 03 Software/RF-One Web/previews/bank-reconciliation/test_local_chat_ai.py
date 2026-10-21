"""One real local-AI interpretation; operational database opened read-only."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

HERE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,'C:/Users/servi/OneDrive/AI-RF-ONE/rf-one-bank-simple-who-rules/03 Software/RF-One Data Store')
os.environ['RFONE_BANK_AI_MODE']='SESSION'
os.environ['RFONE_BANK_CLAUDE_CODE_CLI']='auto'
spec=importlib.util.spec_from_file_location('local_chat_ai_test',HERE/'bank_assistant_preview_routes.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
engine=create_engine('sqlite://',creator=lambda:sqlite3.connect('file:C:/Users/servi/AppData/Local/RF-One/Bank/rfone.db?mode=ro',uri=True))
with Session(engine) as db:
    result=module._chat_answer(db,113,[
        {'role':'assistant','text':'Questi acquisti TEMU sono per il ristorante o personali? Che tipo di prodotti sono?'},
        {'role':'user','text':'Gli acquisti TEMU sulla carta aziendale sono forniture per il ristorante. Se sono sulla carta personale sono spese personali.'}
    ],[{'title':'Pasti al ristorante','text':'Carta aziendale: business meal; carta personale: spesa personale.'}])
    print(json.dumps({key:result.get(key) for key in ('ready','reply','rule_text','provider','model')},ensure_ascii=True))
    output=HERE.parents[2]/'RF-One Data Store/data/why_codex_chat_test_20261017/real_ai_result.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
engine.dispose()
