"""Build a local working source from the immutable copied AWS image; no cloud calls."""
from pathlib import Path
import ast,difflib,json,shutil

ROOT=Path(__file__).resolve().parent.parent
DEV=ROOT/'tmp/role-company-development'
original=Path(r'C:\Users\servi\AppData\Local\RF-One\Employee Directory\AWS-20261110T120743Z\source')
files=['RF-One Data Store/rfone_data_store/access_profiles.py',
 'RF-One Web/role_profile_routes.py','RF-One Web/templates/role_profiles.html',
 'RF-One Web/static/css/role-profiles.css','RF-One Web/static/js/role-profiles.js']
for name in files:
    target=DEV/name;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT/'03 Software'/name,target)

def patch(name,change):
    baseline=(original/name).read_text(encoding='utf-8')
    (DEV/name).write_text(change(baseline),encoding='utf-8')

def models(t):
    for cls,next_cls in [('OperationalArea','PhysicalArea'),('RestaurantRole','OperationalAreaRole')]:
        start=t.index('class '+cls+'(');end=t.index('class '+next_cls+'(',start)
        chunk=t[start:end].replace('restaurant_id: Mapped[int]','restaurant_id: Mapped[int | None]').replace('ForeignKey("restaurants.id"), nullable=False','ForeignKey("restaurants.id"), nullable=True')
        t=t[:start]+chunk+t[end:]
    return t
patch('RF-One Data Store/rfone_data_store/models.py',models)

def account_service(t):
    t=t.replace('def list_domain_access_for_account(', 'def list_direct_domain_access_for_account(',1)
    t=t.replace('def list_domain_item_access_for_account(', 'def list_direct_domain_item_access_for_account(',1)
    t+='''

def list_domain_access_for_account(session, account_id):
    from .access_profiles import effective_access_rows
    return effective_access_rows(session, account_id)


def list_domain_item_access_for_account(session, account_id):
    from .access_profiles import effective_item_rows
    return effective_item_rows(session, account_id)
'''
    return t
patch('RF-One Data Store/rfone_data_store/rfone_account_service.py',account_service)

def web(t):
    start=t.index('def admin_account_access(');end=t.index('# The three access choices',start)
    chunk=t[start:end].replace('account_service.list_domain_access_for_account','account_service.list_direct_domain_access_for_account').replace('account_service.list_domain_item_access_for_account','account_service.list_direct_domain_item_access_for_account')
    chunk=chunk.replace('        if request.method == "POST":', '        profile_person=request.values.get(\'from_person\',\'\')\n        profile_return=None\n        if profile_person:\n            from rfone_data_store import employee_directory as profile_directory\n            expected=f\'account:{account.id}\'\n            person_id=profile_directory.context_person_id(db,\'RFONE_ACCOUNT\',account.id)\n            if profile_person not in (expected,f\'employee:{person_id}\' if person_id is not None else expected):abort(400)\n            profile_return=url_for(\'role_profiles_home\',tab=\'people\',person=profile_person)\n        if request.method == "POST":',1)
    chunk=chunk.replace('return redirect(url_for("admin_accounts"))','return redirect(url_for("admin_account_access",account_id=account_id,from_person=profile_person,saved="1")) if profile_return else redirect(url_for("admin_accounts"))')
    chunk=chunk.replace('account_id=account_id))','account_id=account_id,from_person=profile_person))')
    chunk=chunk.replace('account=account, domains_view=domains_view)','account=account, domains_view=domains_view,profile_return=profile_return,profile_person=profile_person)')
    t=t[:start]+chunk+t[end:]
    t+='''

from role_profile_routes import register_role_profile_routes
register_role_profile_routes(app, SessionFactory=SessionFactory, require_admin=require_admin,
    load_current_account=load_current_account, require_csrf=require_csrf, domains=DOMAINS)
'''
    return t
patch('RF-One Web/app.py',web)
patch('RF-One Data Store/migrations/env.py',lambda t:t.replace('from rfone_data_store.models import Base','from rfone_data_store import access_profiles as profile_models  # register profile tables\nfrom rfone_data_store.models import Base',1))

def directory_routes(t):
    t=t.replace('from rfone_data_store import models as m','from rfone_data_store import models as m\nfrom rfone_data_store import access_profiles as profiles',1)
    needle='            employees = list(db.scalars(directory.canonical_employees().order_by(m.Employee.display_name, m.Employee.id)))'
    t=t.replace(needle,'''            scope_ids=profiles.employee_scope_ids(db,account)
            query_people=directory.canonical_employees().order_by(m.Employee.display_name,m.Employee.id)
            if scope_ids is not None:query_people=query_people.where(m.Employee.id.in_(scope_ids))
            employees=list(db.scalars(query_people))''')
    t=t.replace('            sites = _sites(db)', '            if scope_ids is not None:pending=[]\n            sites = _sites(db)',1)
    marker='            account = load_current_account(db)\n            if request.method == "POST":'
    t=t.replace(marker,'''            account = load_current_account(db)
            scope_ids=profiles.employee_scope_ids(db,account)
            if scope_ids is not None and employee_id not in scope_ids:abort(403)
            if request.method == "POST":''',1)
    needle='phone=request.form.get("phone"), account_id=account.id)\n                db.commit()'
    t=t.replace(needle,'''phone=request.form.get("phone"), account_id=account.id)
                if profiles.employee_scope_ids(db,account) is not None:
                    profiles.membership(db,f'employee:{person.id}',profiles.company_context.get(),account.id)
                db.commit()''',1)
    return t
patch('RF-One Web/employee_directory_routes.py',directory_routes)

def base(t):
    return t.replace('  </header>', '''  </header>
  {% if profile_companies and request.endpoint != 'role_profiles_home' %}<form method="post" action="{{ url_for('switch_access_company') }}" style="display:flex;align-items:center;gap:.6rem;justify-content:flex-end;margin:.75rem 0">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><label style="margin:0">Company <select name="company_id" style="display:inline;width:auto;margin:0">{% for company in profile_companies %}<option value="{{ company.id }}" {% if company.id==profile_company_id %}selected{% endif %}>{{ company.name }}</option>{% endfor %}</select></label><button style="padding:.3rem .7rem">Switch</button></form>{% endif %}''',1)
patch('RF-One Web/templates/base.html',base)
patch('RF-One Web/templates/home.html',lambda t:t.replace('<strong>Accounts</strong>', '<strong>Accounts</strong>').replace('      <a class="home-row" href="{{ url_for(\'admin_accounts\') }}">', '      <a class="home-row" href="{{ url_for(\'role_profiles_home\') }}"><strong>Anagrafica</strong> &mdash; Areas, permissions and company assignments.</a>\n      <a class="home-row" href="{{ url_for(\'admin_accounts\') }}">',1))
patch('RF-One Web/templates/admin_accounts.html',lambda t:t.replace('<h1>Accounts</h1>','<h1>Accounts</h1>\n<p><a href="{{ url_for(\'role_profiles_home\') }}">Anagrafica</a></p>').replace('>Training Identity</a>','>Training Identity</a> · <a href="{{ url_for(\'role_profiles_home\',tab=\'people\',person=\'account:\'~account.id) }}">Anagrafica</a>'))
patch('RF-One Web/templates/admin_account_access.html',lambda t:t.replace('<h1>Domain Access</h1>','<h1>Domain Access</h1>\n<p>These are direct account permissions. <a href="{{ url_for(\'role_profiles_home\',tab=\'people\',person=\'account:\'~account.id) }}">Role permissions</a> add to them in each company.</p>'))
access_template=DEV/'RF-One Web/templates/admin_account_access.html'
access_text=access_template.read_text(encoding='utf-8')
access_text=access_text.replace('<h1>Domain Access</h1>','<h1>Domain Access</h1>{% if profile_return %}<p><a href="{{ profile_return }}">Back to person</a></p>{% endif %}')
access_text=access_text.replace('<button type="submit">Save</button>','<input type="hidden" name="from_person" value="{{ profile_person|default("", true) }}"><button type="submit">Save</button>')
access_template.write_text(access_text,encoding='utf-8')
patch('RF-One Web/templates/employee_directory_detail.html',lambda t:t.replace('<p>Identità interna RF1:', '''{% set profile_summary=person_profile_summary('employee',employee.id) %}
<p><strong>Companies:</strong> {{ profile_summary.companies|sort|join(', ') or 'Not assigned' }}</p>
<p><strong>Roles:</strong> {{ profile_summary.roles|sort|join('; ') or 'Not assigned' }}</p>
{% if can_manage_profiles %}<p><a href="{{ url_for('role_profiles_home',tab='people',person='employee:'~employee.id) }}">Anagrafica</a></p>{% endif %}
<p>Identità interna RF1:''',1))
patch('RF-One Web/templates/employee_directory.html',lambda t:t.replace("{{ row.employee.display_name or 'Nome da completare' }}</a></td>","{{ row.employee.display_name or 'Nome da completare' }}</a>{% set summary=person_profile_summary('employee',row.employee.id) %}{% if summary.companies %}<div class=\"muted\">{{ summary.companies|sort|join(', ') }}</div>{% endif %}</td>"))

shutil.copyfile(ROOT/'07 Tasks/Reports/ROLE_PROFILES_LOCAL_20261110/f2a120261110_role_profiles_companies.py',DEV/'RF-One Data Store/migrations/versions/f2a120261110_role_profiles_companies.py')

# Recover only the already-applied missing migration, not unrelated future work.
parent=Path(r'C:\Users\servi\OneDrive\AI-RF-ONE\RF One\tmp\visual-menu-migration\migrations\versions\e2c320261109_tips_aggregation_scope.py')
shutil.copyfile(parent,DEV/'RF-One Data Store/migrations/versions'/parent.name)
# Keep the development artifact byte-verifiable (Windows text I/O can add CRLF).
import hashlib
for file in DEV.rglob('*'):
    if file.is_file() and file.suffix in ('.py','.html','.js','.css','.json','.md','.txt','.ini','.yml'):
        file.write_bytes(file.read_bytes().replace(b'\r\n',b'\n'))
manifest_path=DEV/'RF-One Data Store/clover_connector_release.json'
manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
manifest['release']='rfone-role-company-local-20261110'
manifest['scope']='Local additive role profiles and company membership; no cloud deployment'
for name in ['RF-One Data Store/rfone_data_store/access_profiles.py','RF-One Data Store/rfone_data_store/rfone_account_service.py','RF-One Data Store/migrations/versions/f2a120261110_role_profiles_companies.py']:
    manifest['files'][name]=''
for name in manifest['files']:manifest['files'][name]=hashlib.sha256((DEV/name).read_bytes()).hexdigest()
manifest_path.write_bytes((json.dumps(manifest,indent=2)+'\n').encode('utf-8'))
patches=[]
for file in DEV.rglob('*'):
    if file.is_file() and file.suffix in ('.py','.html','.js','.css'):
        rel=file.relative_to(DEV);old=original/rel
        if old.exists() and file.read_bytes()!=old.read_bytes():
            patches.extend(difflib.unified_diff(old.read_text(encoding='utf-8').splitlines(True),file.read_text(encoding='utf-8').splitlines(True),fromfile='a/'+str(rel),tofile='b/'+str(rel)))
(ROOT/'tmp/role-company-existing-files.patch').write_text(''.join(patches),encoding='utf-8')
print('Development source prepared:',DEV)
