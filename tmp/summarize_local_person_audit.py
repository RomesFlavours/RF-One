from pathlib import Path
import json
r=json.loads(Path('tmp/person-reconciliation/local-audit.json').read_text());p=json.loads(Path('tmp/person-reconciliation/protected-data-check.json').read_text());print('Protected counts:',json.dumps({k:v['count'] for k,v in p['before'].items()}));print('Groups with suggestions:',sum(bool(g['suggestions']) for g in r['groups']))
