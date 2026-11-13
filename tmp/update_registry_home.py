from pathlib import Path
root=Path.cwd();repo=root/'tmp/git-anagrafica-release';web=repo/'03 Software/RF-One Web/templates'
p=web/'home.html';t=p.read_text(encoding='utf-8');t=t.replace('bank_available or clover_acquisition_available or employees_available','bank_available or clover_acquisition_available or can_manage_profiles');t=t.replace('{% if employees_available %}','{% if can_manage_profiles %}');old="url_for('employee_directory_home')";t=t.replace(old,"url_for('role_profiles_home',tab='people')");t=t.replace('Anagrafica dipendenti <span','Registry <span').replace('Identità RF-One, sedi e collegamenti Clover.','People, roles, companies and system authorizations.');t='\n'.join(line for line in t.split('\n') if not ('home-row' in line and '<strong>Anagrafica</strong>' in line));p.write_text(t,encoding='utf-8')
for name in ('role_profiles.html','admin_accounts.html'):
 p=web/name;t=p.read_text(encoding='utf-8').replace('Anagrafica','Registry');p.write_text(t,encoding='utf-8')
p=web/'employee_directory_detail.html';t=p.read_text(encoding='utf-8').replace('>Anagrafica</a>','>Registry</a>');p.write_text(t,encoding='utf-8')
# Keep the authored local Registry template aligned without touching unrelated lifecycle work.
p=root/'03 Software/RF-One Web/templates/role_profiles.html';p.write_text(p.read_text(encoding='utf-8').replace('Anagrafica','Registry'),encoding='utf-8')
p=repo/'03 Software/RF-One Web/tests/test_role_company_http.py';t=p.read_text(encoding='utf-8');i=t.index('print(json.dumps(');t=t[:i]+'''home=owner.get('/').get_data(as_text=True)
administration=home.split('<div class="domain-name">Administration</div>',1)[1].split('<div class="domain-name">Settings</div>',1)[0]
settings=home.split('<div class="domain-name">Settings</div>',1)[1]
check('Registry in Administration points to new page','href="/admin/roles?tab=people"' in administration and '<strong>Registry' in administration)
check('No Registry duplicate in Settings','/admin/roles' not in settings and 'Anagrafica' not in settings)
check('Legacy directory entry removed from home','href="/administration/employees"' not in home)
check('Registry module title', '<h1>Registry</h1>' in owner.get('/admin/roles?tab=people').get_data(as_text=True))
check('Registry respects administration permissions','href="/admin/roles?tab=people"' not in staff.get('/').get_data(as_text=True))
''' +t[i:];p.write_text(t,encoding='utf-8')
print('Registry home and title updated; added five HTTP checks')
