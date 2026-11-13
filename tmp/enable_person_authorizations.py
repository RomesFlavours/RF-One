from pathlib import Path
p=Path('03 Software/RF-One Web/role_profile_routes.py');t=p.read_text(encoding='utf-8');needle="            people_rows.append({'key':key"
idx=t.index(needle);t=t[:idx]+'''            account_ids=([identity] if kind=='account' else [aid for aid in db.scalars(select(m.RFOneAccount.id)) if directory.context_person_id(db,'RFONE_ACCOUNT',aid)==identity])
            access_url=url_for('admin_account_access',account_id=account_ids[0],from_person=key) if len(account_ids)==1 else None
''' +t[idx:];t=t.replace("{'key':key,'name':target.display_name", "{'key':key,'access_url':access_url,'name':target.display_name")
p.write_text(t,encoding='utf-8')
p=Path('03 Software/RF-One Web/templates/role_profiles.html');t=p.read_text(encoding='utf-8').replace('<button type="button" disabled title="Available in a future update">Other system authorizations</button>', '<a id="person-system-authorizations" class="person-authorizations-button" target="_blank" rel="noopener" hidden>Other system authorizations</a><p id="person-authorizations-help" class="muted">Save the person first to manage their system authorizations.</p>').replace('?v=6','?v=7');p.write_text(t,encoding='utf-8')
p=Path('03 Software/RF-One Web/static/js/role-profiles.js');t=p.read_text(encoding='utf-8');idx=t.index('  function companyGroups()');t=t[:idx]+'''  function systemAuthorizations(person){
    var link=document.getElementById('person-system-authorizations'),help=document.getElementById('person-authorizations-help');
    link.hidden=!person||!person.access_url;
    if(person&&person.access_url){link.href=person.access_url;help.textContent='Opens Domain Access for this person in a separate window. Your unsaved changes here are retained.';}
    else {link.removeAttribute('href');help.textContent=person?'Link one RF1 account to this person in Employee Directory to manage authorizations.':'Save the person first to manage their system authorizations.';}
  }
''' +t[idx:];t=t.replace("    companyGroups();p.assignments", "    systemAuthorizations(p);companyGroups();p.assignments");t=t.replace("field(editor,'action','person_create');field", "field(editor,'action','person_create');systemAuthorizations(null);field");t=t.replace("if (id === 'person-dialog') { document", "if (id === 'person-dialog') { systemAuthorizations(people.get(editor.elements.person.value)); document")
p.write_text(t,encoding='utf-8')
p=Path('03 Software/RF-One Web/static/css/role-profiles.css');p.write_text(p.read_text(encoding='utf-8')+'\n.person-authorizations-button{display:inline-block;background:#55652f;color:#fff;text-decoration:none;padding:.75rem 1.1rem;border-radius:8px}.person-authorizations-button[hidden]{display:none}#person-authorizations-help{font-size:.85rem;margin:.65rem 0 0}\n',encoding='utf-8')
# Preserve and validate the originating person in the existing canonical access route.
p=Path('tmp/prepare_role_company_development.py');t=p.read_text(encoding='utf-8');needle='    t=t[:start]+chunk+t[end:]';replacement='''    chunk=chunk.replace('        if request.method == "POST":', '''+repr('''        profile_person=request.values.get('from_person','')
        profile_return=None
        if profile_person:
            from rfone_data_store import employee_directory as profile_directory
            expected=f'account:{account.id}'
            person_id=profile_directory.context_person_id(db,'RFONE_ACCOUNT',account.id)
            if profile_person not in (expected,f'employee:{person_id}' if person_id is not None else expected):abort(400)
            profile_return=url_for('role_profiles_home',tab='people',person=profile_person)
        if request.method == "POST":''')+''',1)
    chunk=chunk.replace('return redirect(url_for("admin_accounts"))','return redirect(url_for("admin_account_access",account_id=account_id,from_person=profile_person,saved="1")) if profile_return else redirect(url_for("admin_accounts"))')
    chunk=chunk.replace('account_id=account_id))','account_id=account_id,from_person=profile_person))')
    chunk=chunk.replace('account=account, domains_view=domains_view)','account=account, domains_view=domains_view,profile_return=profile_return,profile_person=profile_person)')
    t=t[:start]+chunk+t[end:]''';assert needle in t;t=t.replace(needle,replacement,1)
# Extend the already-existing template patch after its baseline is prepared.
idx=t.index("patch('RF-One Web/templates/employee_directory_detail.html'")
t=t[:idx]+'''access_template=DEV/'RF-One Web/templates/admin_account_access.html'
access_text=access_template.read_text(encoding='utf-8')
access_text=access_text.replace('<h1>Domain Access</h1>','<h1>Domain Access</h1>{% if profile_return %}<p><a href="{{ profile_return }}">Back to person</a></p>{% endif %}')
access_text=access_text.replace('<button type="submit">Save</button>','<input type="hidden" name="from_person" value="{{ profile_person or \'\' }}"><button type="submit">Save</button>')
access_template.write_text(access_text,encoding='utf-8')
''' +t[idx:];p.write_text(t,encoding='utf-8')
