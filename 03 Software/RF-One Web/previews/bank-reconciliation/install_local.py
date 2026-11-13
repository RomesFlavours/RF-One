"""Stage/install the approved preview inside the existing local Bank server."""
import ast
from pathlib import Path
import shutil
import sys

SOURCE = Path(__file__).resolve().parent
TARGET = Path('C:/Users/servi/OneDrive/AI-RF-ONE/rf-one-bank-simple-who-rules/03 Software/RF-One Web')
BACKUP = SOURCE / 'integration_backup'
route_path = TARGET / 'bank_ai_rule_routes.py'
registry_path = TARGET / 'domain_registry.py'
original = route_path.read_text(encoding='utf-8')
old = '    @app.route("/bank/ai-rules")\n    @gate\n    def bank_ai_rules():'
new = '''    from bank_assistant_preview_routes import register_bank_assistant_preview_routes
    register_bank_assistant_preview_routes(app, gate=gate, SessionFactory=SessionFactory)

    @app.route("/bank/ai-rules/advanced")
    @gate
    def bank_ai_rules_advanced():'''
assert original.count(old) == 1, 'Unexpected route version; nothing changed'
routes = original.replace(old, new)
ast.parse(routes)
helper = (SOURCE / 'bank_assistant_preview_routes.py').read_text(encoding='utf-8')
ast.parse(helper)
registry = registry_path.read_text(encoding='utf-8')
assert 'DomainItem("ai_rules", "AI Rules",' in registry
registry = registry.replace('DomainItem("ai_rules", "AI Rules",', 'DomainItem("ai_rules", "Regole e chiarimenti",')
ast.parse(registry)
html = (SOURCE / 'index.html').read_text(encoding='utf-8')
html = html.replace('href="rf-one.png"', 'href="/static/bank-assistant/rf-one.png"')
html = html.replace('src="rf-one.png"', 'src="/static/bank-assistant/rf-one.png"')
html = html.replace('href="rf-one.css"', 'href="/static/css/rf-one.css"')
html = html.replace('href="preview.css"', 'href="/static/bank-assistant/preview.css?v=1"')
html = html.replace('src="app.js?v=2"', 'src="/static/bank-assistant/app.js?v=1"')
html = html.replace('Dati Bank letti', 'Dati Bank letti')
javascript = (SOURCE / 'app.js').read_text(encoding='utf-8')
javascript = javascript.replace("fetch('snapshot.json')", "fetch('/bank/ai-rules/snapshot')")
javascript = javascript.replace('rfone-bank-assistant-preview-v2', 'rfone-bank-assistant-local-preview-v1')
assert "fetch('/bank/ai-rules/snapshot')" in javascript
if sys.argv[1] == 'check':
    print('Route, template and asset staging checks passed. Legacy rules remain at /bank/ai-rules/advanced.')
elif sys.argv[1] == 'install':
    assert not BACKUP.exists(), 'Integration backup already exists; do not overwrite'
    BACKUP.mkdir()
    shutil.copy2(route_path, BACKUP / route_path.name)
    shutil.copy2(registry_path, BACKUP / registry_path.name)
    route_path.write_text(routes, encoding='utf-8')
    registry_path.write_text(registry, encoding='utf-8')
    (TARGET / 'bank_assistant_preview_routes.py').write_text(helper, encoding='utf-8')
    (TARGET / 'templates/bank_assistant_preview.html').write_text(html, encoding='utf-8')
    assets = TARGET / 'static/bank-assistant'
    assets.mkdir(exist_ok=True)
    (assets / 'app.js').write_text(javascript, encoding='utf-8')
    shutil.copy2(SOURCE / 'preview.css', assets / 'preview.css')
    shutil.copy2(SOURCE / 'rf-one.png', assets / 'rf-one.png')
    print('Installed preview on /bank/ai-rules. Existing server requires its supported close/start procedure.')
else:
    raise ValueError('Use check or install')
