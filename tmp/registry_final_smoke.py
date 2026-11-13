import requests
s=requests.Session();s.trust_env=False
r=s.get('http://127.0.0.1:5094/admin/roles?tab=people',timeout=30)
assert r.status_code==200,r.status_code
assert 'Switch user' in r.text and 'Dismissis (47)' in r.text and 'class="local-env' not in r.text
print('Local Registry ready: HTTP 200, User selector present, 47 dismissals preserved.')
r=s.get('http://127.0.0.1:5094/tips/training/trainer',allow_redirects=False,timeout=30)
assert r.status_code==302 and r.headers.get('Location')=='http://127.0.0.1:5094/training/trainer',(r.status_code,r.headers.get('Location'))
print('Tips Training delegates to the canonical RF1 route after shared authorization.')
assert s.post('http://127.0.0.1:5094/local/access-user',data={'account_id':1},timeout=20).status_code==400
print('Local user switch requires CSRF.')

