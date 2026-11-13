from pathlib import Path
root=Path.cwd();repo=root/'tmp/git-anagrafica-release'
for base in (root,repo):
 p=base/'03 Software/RF-One Web/templates/role_profiles.html';t=p.read_text(encoding='utf-8');old="[('roles','Roles'),('areas','Areas'),('companies','Companies'),('people','People & assignments')]";new="[('people','People & assignments'),('roles','Roles'),('areas','Areas'),('companies','Companies')]";assert old in t;t=t.replace(old,new);p.write_text(t,encoding='utf-8')
 p=base/'03 Software/RF-One Web/role_profile_routes.py';t=p.read_text(encoding='utf-8').replace("request.values.get('tab','roles')","request.values.get('tab','people')").replace("if tab not in ('roles','areas','companies','people'):tab='roles'","if tab not in ('roles','areas','companies','people'):tab='people'");p.write_text(t,encoding='utf-8')
p=repo/'03 Software/RF-One Web/tests/test_role_company_http.py';t=p.read_text(encoding='utf-8');i=t.index('print(json.dumps(');t=t[:i]+'''default_page=owner.get('/admin/roles').get_data(as_text=True)
nav=default_page.split('<nav class="profile-tabs"',1)[1].split('</nav>',1)[0]
check('People tab is first',nav.index('People &amp; assignments')<nav.index('>Roles<') if 'People &amp; assignments' in nav else nav.index('People & assignments')<nav.index('>Roles<'))
check('People opens by default','tab=people' in nav.split('aria-current="page"',1)[0] and 'id="people-table"' in default_page)
check('Unknown tab falls back to People','id="people-table"' in owner.get('/admin/roles?tab=unknown').get_data(as_text=True))
''' +t[i:];p.write_text(t,encoding='utf-8')
