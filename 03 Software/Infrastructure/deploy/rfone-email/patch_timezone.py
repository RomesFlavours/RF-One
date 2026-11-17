"""UI-only overlay: reuse RF-One's existing Location timezone resolver."""
from pathlib import Path

path = Path('/app/RF-One Web/app.py')
source = path.read_text(encoding='utf-8')
anchor = 'load_current_account=load_current_account, require_csrf=require_csrf)'
if source.count(anchor) != 1 or 'def inject_site_timezone(' not in source:
    raise RuntimeError('Unexpected RF-One timezone registration; refusing UI overlay')
source = source.replace(anchor,
    "load_current_account=load_current_account, require_csrf=require_csrf,\n"
    "                      get_timezone=lambda: inject_site_timezone()['tz'])")
path.write_text(source, encoding='utf-8')
print('Email Control uses the existing RF-One Location timezone resolver.')
