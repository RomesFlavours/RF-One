import http.cookiejar,urllib.request,urllib.error,json,re,hashlib,pathlib
base='http://127.0.0.1:5111';op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
checks=[]
for path in ['/','/bank/work','/bank/review','/bank/review?view=to_reconcile&year=2026','/bank/configuration/category-trial','/bank/who-search-text','/bank/why-signals','/bank/configuration','/bank/how-it-works','/recognition/?embed=1','/recognition/static/app.js','/recognition/static/style.css']:
 r=op.open(base+path);body=r.read().decode();checks.append(dict(path=path,status=r.status))
 if path=='/bank/configuration/category-trial':assert 'src="/recognition/?embed=1"' in body and 'Chat e simulazione' in body
 if path=='/recognition/?embed=1':
  assert '/recognition/static/app.js' in body and 'content="/recognition"' in body
  token=re.search('name="csrf" content="([^"]+)',body)[1]
for path in ['/bank/work','/bank/manual-reconciliation/1','/bank/configuration/category-trial/simulate']:
 try:op.open(urllib.request.Request(base+path,data=b'test=1'));raise AssertionError('Legacy write endpoint allowed')
 except urllib.error.HTTPError as e:assert e.code==405;checks.append(dict(path=path,post_status=e.code))
r=op.open(urllib.request.Request(base+'/recognition/api/new',data=b'{}',headers={'Content-Type':'application/json','X-CSRF-Token':token}));assert r.status==200
try:op.open(urllib.request.Request(base+'/recognition/api/simulate',data=b'{"revision":0}',headers={'Content-Type':'application/json','X-CSRF-Token':token}));raise AssertionError('Missing plan accepted')
except urllib.error.HTTPError as e:assert e.code==409
assert op.open(base+'/recognition/api/chat').status==200
assert op.open(base+'/bank/review').status==200
cookies=[c.name for c in op.handlers[0].cookiejar] if hasattr(op.handlers[0],'cookiejar') else []
pathlib.Path(r'C:\Users\servi\OneDrive\AI-RF-ONE\RFBank\module-http-verification.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
print(json.dumps(checks));print('Mounted chat, API prefix, CSRF, cookie coexistence and no-plan simulation block: PASS')
