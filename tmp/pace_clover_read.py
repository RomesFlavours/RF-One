from pathlib import Path
p=Path('tmp/clover_15day_local.py');t=p.read_text(encoding='utf-8').replace('import json,sys,boto3,requests','import json,sys,boto3,requests,time');t=t.replace("        r=http.get('https://api.clover.com/v3/merchants/'+merchant+'/'+path,params={'limit':1000,'offset':offset},timeout=45)","""        for attempt in range(8):
            r=http.get('https://api.clover.com/v3/merchants/'+merchant+'/'+path,params={'limit':1000,'offset':offset},timeout=45)
            if r.status_code!=429:break
            delay=min(30,max(5,float(r.headers.get('Retry-After','5')))*(attempt+1))
            print(f'Rate limit; retry in {delay}s',flush=True);time.sleep(delay)
        time.sleep(1.5)""");p.write_text(t,encoding='utf-8')
