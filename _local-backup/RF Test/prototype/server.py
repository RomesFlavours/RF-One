import json, sqlite3, uuid
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'demo.sqlite3'
ROLES = {'staff': 'Dipendente', 'foh': 'Responsabile FOH Winter Park', 'md': 'Responsabile scorte Mount Dora', 'control': 'Controllo di gestione'}
PROCEDURE = {'id':'001','version':'0.3','status':'Bozza per revisione', 'owner':'Responsabile FOH', 'keeper':'Anthony', 'approver':'Pino', 'steps':['Registrare la rottura nello stesso turno.', 'Al minimo o sotto: verificare disponibilità, ordini e scorta cedibile.', 'FOH conferma la richiesta; Mount Dora accetta entro 24 ore.', 'All’accettazione riservare la quantità; alla spedizione passarla in transito.', 'Alla ricezione confermata rendere disponibile la quantità e registrare l’intercompany.', 'Chiudere solo con spedizione, ricezione, intercompany, scorte nei limiti e controllo di gestione.']}
def now(): return datetime.now(timezone.utc).isoformat()
def initial():
    t=now()
    return {'stock':{'wp':{'available':80,'reserved':0,'min':60,'max':120},'md':{'available':400,'reserved':0,'min':0,'max':None}},'transit':0,'onOrder':0,'cases':[], 'intercompany':[], 'movements':[{'date':t,'role':'Dati dimostrativi','type':'Conteggio iniziale','wp':80,'md':400,'reserved':0,'transit':0}], 'audit':[{'date':t,'role':'Dati dimostrativi','result':'Conteggi iniziali: Winter Park 80; Mount Dora 400.'}], 'requests':{}}
@contextmanager
def connect():
    c=sqlite3.connect(DB, timeout=10)
    c.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, data TEXT NOT NULL)')
    c.execute('INSERT OR IGNORE INTO state VALUES (1,?)',(json.dumps(initial()),)); c.commit()
    try:
        with c: yield c
    finally: c.close()
def proposal(s):
    wp,md=s['stock']['wp'],s['stock']['md']
    pending=sum(c['qty'] for c in s['cases'] if c['status'] not in ['closed','received'])
    need=max(0,wp['max']-wp['available']-s['onOrder']-pending)
    return min(need,max(0,md['available']-md['min'])) if wp['available']<=wp['min'] else 0
def apply(s,role,action,p):
    expected={'break':'staff','request':'foh','accept':'md','ship':'md','receive':'foh','review':'control'}
    if action not in expected or role!=expected[action]: raise ValueError('Azione non consentita per questo ruolo.')
    if action=='break':
        q=p.get('qty')
        if type(q)!=int or q<=0 or q>s['stock']['wp']['available']: raise ValueError('Inserire una quantità intera positiva entro la disponibilità.')
        note=str(p.get('note','')).strip()[:500]
        s['stock']['wp']['available']-=q
        result=f'Rottura registrata: {q} bicchieri a Winter Park.' + (' Nota: '+note if note else '')
    elif action=='request':
        if any(c['status']!='closed' for c in s['cases']): raise ValueError('Esiste già una pratica aperta: completarla prima di una nuova richiesta.')
        q=proposal(s)
        if not q: raise ValueError('Nessun trasferimento necessario o disponibile.')
        c={'id':f'PR-{len(s["cases"])+1:03}', 'procedure':'001','version':'0.3','qty':q,'status':'requested','requestedAt':now(),'evidence':{'request':now()},'review':False}
        s['cases'].append(c); result=f'{c["id"]}: richiesta confermata per {q} bicchieri.'
    else:
        c=next((x for x in s['cases'] if x['id']==p.get('caseId')),None)
        if not c: raise ValueError('Pratica non trovata.')
        transitions={'accept':('requested','reserved'),'ship':('reserved','transit'),'receive':('transit','received'),'review':('received','received')}
        before,after=transitions[action]
        if action in c['evidence']: return 'Conferma già registrata: nessuna duplicazione.'
        if c['status']!=before: raise ValueError('Passaggio non disponibile nello stato attuale.')
        q=c['qty']; md=s['stock']['md']
        if action=='accept':
            if datetime.now(timezone.utc)>datetime.fromisoformat(c['requestedAt'])+timedelta(hours=24): raise ValueError('Richiesta scaduta: serve il ricalcolo FOH. Gestione eccezione fuori da questo prototipo.')
            if md['available']-md['min']<q: raise ValueError('Scorta cedibile insufficiente.')
            md['available']-=q; md['reserved']+=q
        if action=='ship': md['reserved']-=q; s['transit']+=q
        if action=='receive':
            s['transit']-=q; s['stock']['wp']['available']+=q
            s['intercompany'].append({'id':'IC-'+c['id'],'caseId':c['id'],'date':now(),'role':ROLES[role],'from':'RF-Mount Dora','to':'RF-Winter Park','qty':q,'unitValue':4,'value':q*4})
        if action=='review': c['review']=True
        c['evidence'][action]=now(); c['status']=after
        wp=s['stock']['wp']
        if c['review'] and all(k in c['evidence'] for k in ['ship','receive']) and any(i['caseId']==c['id'] for i in s['intercompany']) and wp['min']<=wp['available']<=wp['max']: c['status']='closed'; c['closedAt']=now()
        labels={'accept':'Accettazione e riserva registrate','ship':'Spedizione confermata','receive':'Ricezione confermata e intercompany registrato','review':'Controllo di gestione registrato'}
        result=f'{c["id"]}: {labels[action]} ({q} bicchieri).' + (' Pratica chiusa.' if c['status']=='closed' else '')
    if action in ['break','accept','ship','receive']:
        s['movements'].append({'date':now(),'role':ROLES[role],'type':result,'wp':s['stock']['wp']['available'],'md':s['stock']['md']['available'],'reserved':s['stock']['md']['reserved'],'transit':s['transit']})
    return result
class Handler(BaseHTTPRequestHandler):
    def respond(self,code,data):
        raw=json.dumps(data,ensure_ascii=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if self.path=='/api/state':
            with connect() as db: s=json.loads(db.execute('SELECT data FROM state WHERE id=1').fetchone()[0])
            self.respond(200,{'state':s,'proposal':proposal(s),'procedure':PROCEDURE}); return
        if self.path not in ['/','/index.html']: self.respond(404,{'error':'Pagina non trovata'}); return
        raw=(ROOT/'index.html').read_bytes(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.end_headers(); self.wfile.write(raw)
    def do_POST(self):
        if self.headers.get('Origin') not in [None,'http://127.0.0.1:8765','http://localhost:8765']: self.respond(403,{'error':'Origine non consentita'}); return
        try:
            p=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
            with connect() as db:
                db.execute('BEGIN IMMEDIATE'); s=json.loads(db.execute('SELECT data FROM state WHERE id=1').fetchone()[0])
                if self.path=='/api/reset': s=initial(); result='Dati dimostrativi ripristinati.'
                elif self.path=='/api/action':
                    role=p.get('role'); key=p.get('requestId')
                    if role not in ROLES or not isinstance(key,str) or not key: raise ValueError('Ruolo o identificativo azione mancante.')
                    if key in s['requests']: self.respond(200,{'result':s['requests'][key]}); return
                    try: result=apply(s,role,p.get('action'),p)
                    except ValueError as e:
                        s['audit'].append({'date':now(),'role':ROLES[role],'result':'Azione respinta: '+str(e)})
                        db.execute('UPDATE state SET data=? WHERE id=1',(json.dumps(s),)); db.commit(); self.respond(400,{'error':str(e)}); return
                    s['requests'][key]=result; s['audit'].append({'date':now(),'role':ROLES[role],'result':result})
                else: self.respond(404,{'error':'Operazione non trovata'}); return
                db.execute('UPDATE state SET data=? WHERE id=1',(json.dumps(s),))
            self.respond(200,{'result':result})
        except (ValueError,TypeError,json.JSONDecodeError) as e: self.respond(400,{'error':str(e)})
if __name__=='__main__':
    with connect(): pass
    print('Cross-Domain Procedures e MyRF: http://127.0.0.1:8765',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
