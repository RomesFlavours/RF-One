import urllib.request,http.cookiejar,re,json,time,pathlib
jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar));base='http://127.0.0.1:5111/recognition'
html=client.open(base).read().decode();token=re.search('name="csrf" content="([^"]+)',html)[1]
def req(path,data=None):
 return json.loads(client.open(urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':token})).read())
r=req('/api/chat',{'text':'Voglio riconoscere solo il WHO nelle descrizioni ACH: quando la descrizione contiene ORIG CO NAME: e ORIG ID:, estrai il WHO tra questi due delimitatori. Escludi tutte le descrizioni contenenti PAYPAL. Conserva cifre e spazi interni. Non assegnare né dedurre WHY. Questo è il procedimento completo che voglio simulare; riepilogalo e preparalo.','research':False});print('Real ChatGPT request accepted',flush=True)
for i in range(170):
 time.sleep(2);r=req('/api/chat')
 if not r['busy']:break
print(json.dumps({'busy':r['busy'],'error':r['error'],'reply':r['messages'][-1]['text'][:2000],'plan':r['plan']},ensure_ascii=False),flush=True)
if r['plan']:
 sim=req('/api/simulate',{'revision':r['revision']});print(json.dumps({k:v for k,v in sim.items() if k!='rows'}),flush=True)
 out={'chat':r,'simulation_summary':{k:v for k,v in sim.items() if k!='rows'},'first_results':sim['rows'][:3]}
else:out={'chat':r}
pathlib.Path(r'C:\Users\servi\OneDrive\AI-RF-ONE\RFBank\live-ai-verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
