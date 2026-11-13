from pathlib import Path
import requests,json,concurrent.futures
root=Path('tmp/registry-access-release');state=json.loads((root/'release-state.json').read_text());base='https://rfone.romesflavours.com'
checks=[('login',base+'/login',{200}),('Registry requires login',base+'/admin/roles?tab=people',{302,303,401}),('Kitchen requires login',base+'/kitchen',{302,303,401}),('Training requires login',base+'/training/manage/students',{302,303,401}),('Tips requires login',base+'/tips/',{302,303,401}),('Selection requires login',base+'/selection/',{302,303,401}),('Selection bridge preserved',base+'/selection/candidate/bridge/health',{200})]
for name in ('training','kitchen'):checks.append((name+' health','https://'+state['services'][name]['service_url']+'/health',{200}))
def test(item):
 name,url,expected=item;s=requests.Session();s.trust_env=False;r=s.get(url,allow_redirects=False,timeout=40);result={'check':name,'url':url,'status':r.status_code,'passed':r.status_code in expected}
 if name.endswith('health') and r.status_code==200:result['revision']=r.json().get('revision');result['passed']=result['passed'] and result['revision']==state['commit']
 if name=='login':result['passed']=result['passed'] and 'Switch user' not in r.text and '/local/access-user' not in r.text
 if name=='Selection bridge preserved' and r.status_code==200:result['bridge_version']=r.json().get('version');result['passed']=bool(result['bridge_version'] and result['bridge_version'].startswith('rmaed-selection-bridge'))
 return result
results=list(concurrent.futures.ThreadPoolExecutor(max_workers=5).map(test,checks));(root/'http-checks.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2));assert all(v['passed'] for v in results)
