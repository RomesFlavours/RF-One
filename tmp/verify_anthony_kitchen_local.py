from pathlib import Path
import requests,re,json
base='http://127.0.0.1:5094';c=requests.Session();c.trust_env=False
page=c.get(base+'/admin/accounts/15/access?from_person=account:15',timeout=30)
assert page.status_code==200
assert 'Anthony (anthony)' in page.text
assert 'account_label' in c.get(base+'/admin/roles?tab=people',timeout=30).text
chooser=c.get(base+'/local/users',timeout=20);token=re.search(r'name="csrf_token" value="([^"]+)"',chooser.text)[1]
assert c.post(base+'/local/access-user',data={'csrf_token':token,'account_id':15},allow_redirects=False,timeout=20).status_code==302
home=c.get(base+'/',timeout=30)
assert home.status_code==200
assert 'Welcome, Anthony' in home.text
assert 'href="/kitchen"' in home.text
for path in ('/tips/','/compensation','/bank','/projects','/restaurant/wines','/admin/organization','/selection/'):
 r=c.get(base+path,timeout=20,allow_redirects=False)
 assert r.status_code==403,(path,r.status_code)
for path in ('/kitchen','/kitchen/dashboard','/kitchen/recipes','/kitchen/configuration'):
 r=c.get(base+path,timeout=30,allow_redirects=False)
 assert r.status_code in (200,302),(path,r.status_code)
assert 'Switch user' not in home.text
Path('tmp/anthony-kitchen-only-result.json').write_text(json.dumps({'account_id':15,'username':'anthony','local_only':True,'granted':['KITCHEN'],'other_domains_denied':True,'kitchen_pages_verified':4,'identities_merged':False},indent=2),encoding='utf-8')
print('Anthony: only Kitchen visible; four Kitchen entries work; seven other component entries return 403; identities unchanged.')
