from pathlib import Path
root=Path('/app/RF-One Web')
(root/'registry_navigation.py').write_text('''"""Validated Registry return targets; never accept an arbitrary redirect URL."""
from flask import abort, request, url_for
from rfone_data_store import employee_directory as directory


def account_return(db, account):
    person_id = directory.context_person_id(db, 'RFONE_ACCOUNT', account.id)
    target = f'employee:{person_id}' if person_id is not None else f'account:{account.id}'
    supplied = request.values.get('from_person', '')
    if supplied:
        try:
            kind, raw = supplied.split(':')
            identity = int(raw)
        except (ValueError, AttributeError):
            abort(400)
        if kind == 'account':
            if identity != account.id: abort(400)
        elif kind == 'employee':
            if person_id is None or directory.resolve_employee_id(db, identity) != person_id: abort(400)
        else:
            abort(400)
    return target, url_for('role_profiles_home', tab='people', person=target, _anchor='people-table')
''',encoding='utf-8',newline='\n')
p=root/'app.py';s=p.read_text(encoding='utf-8');s=s.replace('def admin_accounts():\n    with SessionFactory() as db:\n        accounts = account_service.list_accounts(db)\n        return render_template("admin_accounts.html", accounts=accounts)',"def admin_accounts():\n    return redirect(url_for('role_profiles_home', tab='people'))")
# Shared return calculation only changes navigation, not access control or writes.
for name,next_marker in [('admin_account_edit','@app.route("/admin/accounts/<int:account_id>/reset-password"'),('admin_account_access','# The three access choices'),('admin_account_training_link','# ---------------------------------------------------------------------------\n# Trainer-facing')]:
 start=s.index('def '+name+'(')
 if name=='admin_account_training_link':end=s.index('\n\n# ---------------------------------------------------------------------------',start)
 else:end=s.index(next_marker,start)
 part=s[start:end]
 if name=='admin_account_access':
  old=part[part.index("        profile_person=request.values"):part.index('        if request.method == "POST":')]
  part=part.replace(old,"        from registry_navigation import account_return\n        profile_person, profile_return = account_return(db, account)\n        status = 200\n        submitted = None\n")
  part=part.replace('                return redirect(url_for("admin_account_access", account_id=account_id,from_person=profile_person))\n            db.commit()\n            flash("Domain access updated.", "info")\n            return redirect(url_for("admin_account_access",account_id=account_id,from_person=profile_person,saved="1")) if profile_return else redirect(url_for("admin_accounts"))','                status = 400\n                submitted = request.form\n            else:\n                db.commit()\n                flash("Domain access updated.", "info")\n                return redirect(profile_return)')
  part=part.replace('            domains_view.append({','''            if submitted is not None:
                legacy = _ACCESS_ALL if submitted.get(f'enabled_{d.code}') == 'on' else _ACCESS_NONE
                mode = submitted.get(f'access_{d.code}', legacy)
                access = {'role_code': submitted.get(f'role_{d.code}', '')}
                items_by_code[d.code] = set(submitted.getlist(f'items_{d.code}'))
            domains_view.append({''')
  part=part.replace('profile_person=profile_person)','profile_person=profile_person), status')
 else:
  needle='        if account is None:\n            abort(404)\n'
  part=part.replace(needle,needle+'        from registry_navigation import account_return\n        profile_person, profile_return = account_return(db, account)\n',1)
  part=part.replace('return redirect(url_for("admin_accounts"))','return redirect(profile_return)')
  if name=='admin_account_edit':
   part=part.replace('actor_id=current_account_id())','actor_id=current_account_id(), profile_person=profile_person, profile_return=profile_return)')
  else:
   part=part.replace('return redirect(url_for("admin_account_training_link", account_id=account_id))','return render_template("admin_account_training_link.html", account=account, existing_link=existing_link, linked_training_account=None, unlinked_accounts=training_integration.list_unlinked_training_accounts(db), profile_person=profile_person, profile_return=profile_return), 400')
   part=part.replace('linked_training_account=linked_training_account, unlinked_accounts=unlinked_accounts,','linked_training_account=linked_training_account, unlinked_accounts=unlinked_accounts,\n            profile_person=profile_person, profile_return=profile_return,')
 s=s[:start]+part+s[end:]
# Password errors stay on the password section; success returns to the person.
start=s.index('def admin_account_reset_password(');end=s.index('@app.route("/admin/accounts/<int:account_id>/access"',start);part=s[start:end]
part=part.replace('        if password != password_confirm:','        from registry_navigation import account_return\n        profile_person, profile_return = account_return(db, account)\n        saved = False\n        if password != password_confirm:')
part=part.replace('                flash("Password updated.", "info")','                saved = True\n                flash("Password updated.", "info")')
part=part.replace('return redirect(url_for("admin_account_edit", account_id=account_id))','return redirect(profile_return) if saved else redirect(url_for("admin_account_edit", account_id=account_id, from_person=profile_person, _anchor="reset-password"))')
s=s[:start]+part+s[end:]
p.write_text(s,encoding='utf-8',newline='\n')
# Propagate the validated person context through the account pages and forms.
for name in ('admin_account_access','admin_account_form','admin_account_training_link'):
 p=root/'templates'/(name+'.html');s=p.read_text(encoding='utf-8')
 s=s.replace("('Accounts', url_for('admin_accounts'))","('Registry', profile_return|default(url_for('role_profiles_home', tab='people'), true))")
 if name!='admin_account_access':
  heading_end=s.index('</h1>')+len('</h1>');s=s[:heading_end]+'''\n<p><a href="{{ profile_return|default(url_for('role_profiles_home', tab='people'), true) }}">Back to person</a></p>'''+s[heading_end:]
 # Every account POST retains context, including password and Training forms.
 if name!='admin_account_access':
  s=s.replace('<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">','<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">\n    <input type="hidden" name="from_person" value="{{ profile_person|default(\'\', true) }}">')
 if name=='admin_account_access':
  s=s.replace("url_for('admin_account_training_link',account_id=account.id)","url_for('admin_account_training_link',account_id=account.id,from_person=profile_person)")
  s=s.replace('<button type="submit">Save</button>','<button type="submit">Save</button><a class="link-button" href="{{ profile_return }}">Cancel</a>')
 p.write_text(s,encoding='utf-8',newline='\n')
# Pass context for password navigation from the person editor as for permissions.
p=root/'role_profile_routes.py';s=p.read_text(encoding='utf-8').replace("url_for('admin_account_edit',account_id=linked.id,_anchor='reset-password')","url_for('admin_account_edit',account_id=linked.id,from_person=person,_anchor='reset-password')");p.write_text(s,encoding='utf-8',newline='\n')
# Reopen the canonical person after returning; do not force a new tab.
p=root/'templates/role_profiles.html';s=p.read_text(encoding='utf-8').replace(' method="post" target="_blank" rel="noopener"',' method="post"').replace("'reopen':dialog,'error':error","'reopen':dialog,'error':error,'returnPerson':person").replace('?v=level2','?v=navigation1');p.write_text(s,encoding='utf-8',newline='\n')
p=root/'static/js/role-profiles.js';s=p.read_text(encoding='utf-8')
s=s.replace(". Opens Domain Access for this account in a separate window. Your unsaved changes here are retained.",". Opens Domain Access for this account. Save changes to the person before leaving this editor.")
needle="  document.addEventListener('click',function(e){var b=e.target.closest('[data-edit-person]');if(!b)return;var p=people.get(b.dataset.editPerson);if(!p)return;"
s=s.replace(needle,"  function editPerson(p,b){\n    if(!p)return;")
s=s.replace("systemAuthorizations(p);companyGroups();p.assignments.forEach(roleRow);dialogs['person-dialog'].open(b);\n  });","systemAuthorizations(p);companyGroups();p.assignments.forEach(roleRow);dialogs['person-dialog'].open(b);\n  }\n  document.addEventListener('click',function(e){var b=e.target.closest('[data-edit-person]');if(b)editPerson(people.get(b.dataset.editPerson),b);});")
s=s.replace("  if (data.reopen)","  if (data.reopen)") # preserve existing validation-error reopen precedence
pos=s.rindex('}());');s=s[:pos]+'''  if (!data.reopen && data.returnPerson) {
    var returnPerson=people.get(data.returnPerson);
    if(returnPerson){
      var table=document.getElementById('people-table');if(table)table.open=true;
      var button=Array.from(document.querySelectorAll('[data-edit-person]')).find(function(b){return b.dataset.editPerson===data.returnPerson;});
      editPerson(returnPerson,button);
    }
  }
'''+s[pos:];p.write_text(s,encoding='utf-8',newline='\n')


p=root/'templates/role_profiles.html';s=p.read_text(encoding='utf-8').replace('<form id="person-password-form" method="post">','<form id="person-password-form" method="post" target="_blank" rel="noopener">').replace('<form id="person-access-form" method="post">','<form id="person-access-form" method="post" target="_blank" rel="noopener">');p.write_text(s,encoding='utf-8',newline='\n')
p=root/'static/js/role-profiles.js';s=p.read_text(encoding='utf-8').replace('. Opens Domain Access for this account. Save changes to the person before leaving this editor.','. Opens Domain Access for this account in a separate window. Your unsaved changes here are retained.');p.write_text(s,encoding='utf-8',newline='\n')

import compileall
assert compileall.compile_file(str(root/'app.py'),quiet=1)
assert compileall.compile_file(str(root/'registry_navigation.py'),quiet=1)
assert compileall.compile_file(str(root/'role_profile_routes.py'),quiet=1)
from jinja2 import Environment
for name in ('admin_account_access','admin_account_form','admin_account_training_link','role_profiles'):
    text=(root/'templates'/(name+'.html')).read_text(encoding='utf-8')
    Environment().parse(text)
    if name.startswith('admin_account_'):assert "url_for('admin_accounts')" not in text
print('Registry navigation transformations and templates verified')
