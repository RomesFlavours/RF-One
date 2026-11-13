import urllib.request
p=urllib.request.urlopen('http://127.0.0.1:5094/admin/roles',timeout=45).read().decode()
nav=p.split('<nav class="profile-tabs"',1)[1].split('</nav>',1)[0]
assert nav.index('People')<nav.index('>Roles<')
assert 'id="people-table"' in p and '<h1>Registry</h1>' in p
h=urllib.request.urlopen('http://127.0.0.1:5094/',timeout=45).read().decode()
assert '<strong>Registry' in h
assert '/admin/roles' not in h.split('<div class="domain-name">Settings</div>',1)[1]
print('Local Registry People-first and MyRF verified')
