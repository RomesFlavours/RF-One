"""Add email routes to the pinned running image without replacing its apps."""
from pathlib import Path


def insert_once(path, anchor, addition):
    source = path.read_text(encoding='utf-8')
    if source.count(anchor) != 1:
        raise RuntimeError(f'Email overlay anchor mismatch: {path.name}')
    path.write_text(source.replace(anchor, anchor + addition), encoding='utf-8')


root = Path('/app')
insert_once(root / 'RF-One Web/app.py', 'from db import SessionFactory  # noqa: E402',
            '\nfrom email_routes import register_email_routes  # noqa: E402')
insert_once(root / 'RF-One Web/app.py', 'app.secret_key = _secret_key',
            '\nregister_email_routes(app, SessionFactory=SessionFactory,\n'
            '                      load_current_account=load_current_account, require_csrf=require_csrf)')
insert_once(root / 'RF-One Data Store/migrations/env.py',
            'from rfone_data_store.models import Base  # noqa: E402',
            '\nfrom rfone_data_store import email_service  # noqa: E402,F401')
home = root / 'RF-One Web/templates/home.html'
source = home.read_text(encoding='utf-8')
condition = 'or can_manage_profiles or employees_available %}'
if source.count(condition) != 1:
    raise RuntimeError('Email navigation anchor mismatch')
home.write_text(source.replace(condition, 'or can_manage_profiles or employees_available or account.is_admin %}'), encoding='utf-8')
insert_once(home, '<div class="domain-name">Administration</div>',
            '\n      {% if account.is_admin %}\n'
            '      <a class="home-row" href="{{ url_for(\'email_control\') }}"><strong>Email Control</strong> &mdash; Monitor the shared email service.</a>\n'
            '      {% endif %}')
print('Email overlay applied; existing app files preserved.')
