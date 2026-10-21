"""Install the chat-first revision into the existing local Bank worktree."""
import ast
from pathlib import Path
import shutil
import sys

SOURCE=Path(__file__).resolve().parent
TARGET=Path('C:/Users/servi/OneDrive/AI-RF-ONE/rf-one-bank-simple-who-rules/03 Software/RF-One Web')
route_path=TARGET/'bank_ai_rule_routes.py'
route=route_path.read_text(encoding='utf-8')
before='register_bank_assistant_preview_routes(app, gate=gate, SessionFactory=SessionFactory)'
after='register_bank_assistant_preview_routes(app, gate=gate, SessionFactory=SessionFactory, require_csrf=require_csrf, load_current_account=load_current_account)'
assert route.count(before)==1,'Unexpected registration; nothing changed'
route=route.replace(before,after);ast.parse(route)
helper=(SOURCE/'bank_assistant_preview_routes.py').read_text(encoding='utf-8');ast.parse(helper)
html=(SOURCE/'index.html').read_text(encoding='utf-8')
for old,new in [
 ('href="rf-one.png"','href="/static/bank-assistant/rf-one.png"'),
 ('src="rf-one.png"','src="/static/bank-assistant/rf-one.png"'),
 ('href="rf-one.css"','href="/static/css/rf-one.css"'),
 ('href="preview.css"','href="/static/bank-assistant/preview.css?v=chat1"'),
 ('src="app.js?v=3"','src="/static/bank-assistant/app.js?v=chat1"')]:html=html.replace(old,new)
javascript=(SOURCE/'app.js').read_text(encoding='utf-8').replace("fetch('snapshot.json')","fetch('/bank/ai-rules/snapshot')")
javascript=javascript.replace('rfone-bank-assistant-chat-v1','rfone-bank-assistant-local-chat-v1')
assert '/bank/ai-rules/chat/preview' in javascript
assert 'answer-form' not in javascript and 'answer-why' not in html
assert 'bank-csrf' in html and 'chat-form' in html
if sys.argv[1]=='check':
    print('Chat routes, CSRF integration and preview UI staging checks passed.')
elif sys.argv[1]=='install':
    backup=SOURCE/'integration_chat_backup';assert not backup.exists();backup.mkdir()
    files=[route_path,TARGET/'bank_assistant_preview_routes.py',TARGET/'templates/bank_assistant_preview.html',TARGET/'static/bank-assistant/app.js',TARGET/'static/bank-assistant/preview.css']
    for i,path in enumerate(files):shutil.copy2(path,backup/(str(i)+'_'+path.name))
    route_path.write_text(route,encoding='utf-8')
    (TARGET/'bank_assistant_preview_routes.py').write_text(helper,encoding='utf-8')
    (TARGET/'templates/bank_assistant_preview.html').write_text(html,encoding='utf-8')
    (TARGET/'static/bank-assistant/app.js').write_text(javascript,encoding='utf-8')
    shutil.copy2(SOURCE/'preview.css',TARGET/'static/bank-assistant/preview.css')
    print('Chat-first page installed. Restart through the supported Bank launcher.')
else:raise ValueError('check or install')
