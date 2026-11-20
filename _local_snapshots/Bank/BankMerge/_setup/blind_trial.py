from pathlib import Path
import sqlite3, os, json, sys, runpy
b=Path(__file__).resolve().parents[1]
d=Path(os.environ["LOCALAPPDATA"])/"RF-One"
s=b/"03 Software"
launch=runpy.run_path(str(b/'_setup/launch.py'))
os.environ.update(launch['environment']())
sys.path[:0]=[str(s/n) for n in ('RF-One Web','RF-One Data Store','C-Bank Prototype')]
from cbank import legacy, merge_engine
from collections import Counter
eng=merge_engine.engine_class()(legacy.session(),None,merge_engine.Options(blind=True))
rows={}
for t in eng.txns:
 r=eng.evaluate(t)
 assert not r['protected']
 rows[t.id]={k:r.get(k) for k in ('status','who_name','why','category','beneficiary','exceptions','method_conflicts','claude_proposal','why_method','split')}
 rows[t.id]['why_code']=eng.c.whys[r['why_id']].code if r['why_id'] else None
 rows[t.id]['what_code']=eng.c.classes[r['category_id']].code if r['category_id'] else None
print(len(rows),Counter(r['status'] for r in rows.values()))
(d/'BankMerge/blind-results.json').write_text(json.dumps(rows,ensure_ascii=False,default=str),encoding='utf-8')
import psycopg2, unicodedata
from collections import Counter,defaultdict
from html import escape
pred=json.loads((d/'BankMerge/blind-results.json').read_text(encoding='utf-8'))
pg=psycopg2.connect(**json.loads((d/'Bank1/local-connection.json').read_text(encoding='utf-8-sig')))
pg.set_session(readonly=True,isolation_level='REPEATABLE READ')
p=pg.cursor()
l=sqlite3.connect((d/'BankMerge/rfone.db').as_uri()+'?mode=ro',uri=True).cursor()
def query(cursor,q):
 cursor.execute(q)
 return cursor.fetchall()
def norm(v):
 return ' '.join(str(v or '').upper().split())
q="""select t.id,t.posting_date,t.amount_minor,i.display_name,t.description_original,t.fingerprint,t.occurrence_index_in_batch,
 e.decision_status,coalesce(o.canonical_name,e.occurrence_name_snapshot),r.code,r.name,
 coalesce(e.accounting_classification_code_snapshot,a.code), batch.sha256,t.source_row_number
 from financial_transactions t join payment_instruments i on i.id=t.payment_instrument_id
 left join bank_import_batches batch on batch.id=t.import_batch_id
 left join bank_transaction_explanations e on e.id=t.explanation_id
 left join bank_occurrences o on o.id=e.occurrence_id
 left join bank_transaction_reasons r on r.id=e.transaction_reason_id
 left join bank_accounting_classifications a on a.id=coalesce(e.accounting_classification_id,r.accounting_classification_id)
 order by t.posting_date desc,t.id"""
one=query(p,q); local=query(l,q)
assert len(local)==len(pred)==3299
def ident(x):
 return (str(x[1]),x[2],norm(x[3]),norm(x[4]))
def index(rows,f):
 m=defaultdict(list)
 for x in rows:m[f(x)].append(x)
 return m
def fp(x):return (x[5],x[6],ident(x))
ia=index(one,fp); il=index(local,fp)
links={x[0]:ia[fp(x)][0] for x in local if x[5] and len(ia[fp(x)])==len(il[fp(x)])==1}
def provenance(x):return fp(x)+(x[12],x[13])
ap=index(one,provenance); al=index(local,provenance)
for x in local:
 if x[0] not in links and x[12] and x[13] and len(ap[provenance(x)])==len(al[provenance(x)])==1:
  links[x[0]]=ap[provenance(x)][0]
used={x[0] for x in links.values()}
remaining=[x for x in local if x[0] not in links]
ia=index((x for x in one if x[0] not in used),ident); il=index(remaining,ident)
for x in remaining:
 if len(ia[ident(x)])==len(il[ident(x)])==1:links[x[0]]=ia[ident(x)][0]
assert len({x[0] for x in links.values()})==len(links)
snapshot={i:json.loads(r) for i,r in query(l,'select financial_transaction_id,payload_json from bank_engine_results where run_id=(select max(run_id) from bank_engine_results)')}
def disp(*xs):return ' · '.join(str(x or '—') for x in xs)
def printid(t):return f"{t[1]} | {t[3]} | {t[2]/100:,.2f} | {t[4]}"
labels=Counter(); conflicts=Counter(); changes=0; groups=defaultdict(list)
for t in local:
 tid=t[0]; r=pred[str(tid)]; old=snapshot[tid]; a=links.get(tid)
 o=(a[8],a[9],a[11]) if a else ('','','')
 m=(r['who_name'],r['why_code'],r['what_code'])
 dif=[k for k,x,y in zip(('WHO','WHY','WHAT'),o,m) if norm(x)!=norm(y)]
 ref=a[7] if a else ''
 res='Riconciliato' if r['status']=='RECONCILED' else 'Aperto'
 if ref=='HUMAN_CONFIRMED':
  cl='Coincide' if not dif and res=='Riconciliato' else 'Diverso' if res=='Riconciliato' else 'Aperto'
  labels[cl]+=1
 codes=', '.join(x['code'] for x in r['exceptions'])
 for cf in set(x['kind'] for x in r['method_conflicts'] or []):conflicts[cf]+=1
 src=disp(a[8],a[10],a[11]) if a else '—'
 new=disp(r['who_name'],r['why'],r['category'])
 prev=disp(old.get('who_name'),old.get('why'),old.get('category'))
 changed=(prev!=new or old['status']!=r['status'] or norm(old.get('beneficiary'))!=norm(r['beneficiary']))
 changes+=changed
 row=(tid,printid(t),ref or ('Senza classificazione' if a else 'Senza corrispondenza'),src,prev+' | '+old['status'],new+' | '+res,', '.join(dif) if a else '—',codes, str(r['method_conflicts'] or ''))
 groups['Tutti i movimenti'].append(row)
 if ref=='HUMAN_CONFIRMED': groups['Prova alla cieca · '+cl].append(row)
 if changed:groups['Variazioni rispetto all’ultima elaborazione locale'].append(row)
 if r['method_conflicts']:groups['Conflitti fra metodi'].append(row)
 if not a:groups['Movimenti locali senza corrispondenza in Bank1'].append(row)
 if a and dif:groups['Classificazioni diverse da Bank1 (incluse le proposte)'].append(row)
assert sum(labels.values())==sum(x[7]=='HUMAN_CONFIRMED' for x in links.values())
sections=[]
def table(title,head,rows):
 def cells(rr,tag):return ''.join('<'+tag+'>'+escape(str(x if x is not None else '—'))+'</'+tag+'>' for x in rr)
 if rows:sections.append('<details><summary>'+escape(title)+f' ({len(rows)})</summary><table><thead><tr>'+cells(head,'th')+'</tr></thead><tbody>'+''.join('<tr>'+cells(x,'td')+'</tr>' for x in rows)+'</tbody></table></details>')
for title in sorted(groups,key=lambda name:(name=='Tutti i movimenti',not name.startswith('Prova'),name)):
 table(title,['# locale','Movimento · data, conto, importo, descrizione','Stato Bank1','Bank1 · WHO / WHY / WHAT','Ultima locale','BankMerge alla cieca','Campi diversi da Bank1','Da risolvere','Conflitto fra metodi'],groups[title])
used={x[0] for x in links.values()}; extra=[x for x in one if x[0] not in used]
table('Bank1 senza corrispondenza univoca nei 3.299',['# Bank1','Movimento','Stato'],[(x[0],printid(x),x[7]) for x in extra])
catalog={}
for name,sql in [
 ('WHO e WHY predefinito','select o.canonical_name,o.status,r.code from bank_occurrences o left join bank_transaction_reasons r on r.id=o.default_transaction_reason_id'),
 ('WHY e WHAT','select r.code,r.name,r.status,a.code from bank_transaction_reasons r left join bank_accounting_classifications a on a.id=r.accounting_classification_id'),
 ('WHAT','select code,name,statement_type,active from bank_accounting_classifications'),
 ('Associazioni attive WHO / WHY',"select distinct o.canonical_name,r.code from bank_occurrence_reason_associations a join bank_occurrences o on o.id=a.occurrence_id join bank_transaction_reasons r on r.id=a.transaction_reason_id where a.active"),
 ('Regole attive e definizione eseguibile',"""select r.id,v.method,v.spec from bank_ai_rules r join bank_ai_rule_versions v on r.id=v.rule_id where r.status='ACTIVE' and r.deleted_at is null and v.version_no=(select max(x.version_no) from bank_ai_rule_versions x where x.rule_id=r.id)""")]:
 def mapping(cursor):
  out={}
  for k,*v in query(cursor,sql):
   if name.startswith('Regole') and v[-1] is not None:
    spec=json.loads(v[-1]) if isinstance(v[-1],str) else v[-1]
    v[-1]=json.dumps(spec,sort_keys=True,ensure_ascii=False)
   if name=='WHAT':v[-1]=bool(v[-1])
   if name.startswith('Associazioni'):k=disp(k,*v);v=['Attiva']
   out[norm(k)]=disp(*v)
  return out
 left,right=mapping(p),mapping(l)
 diff=[(k,left.get(k,'—'),right.get(k,'—')) for k in sorted(left.keys()|right.keys()) if left.get(k)!=right.get(k)]
 table(name,['Chiave','Bank1','Locale usata da BankMerge'],diff);catalog[name]=(len(left),len(right),len(diff))
stats=f"Movimenti locali 3.299 · Bank1 {len(one)} · abbinati {len(links)} · solo locali o non abbinabili {3299-len(links)} · solo Bank1 o non abbinabili {len(extra)}. Decisioni umane confrontate {sum(labels.values())} su {sum(x[7]=='HUMAN_CONFIRMED' for x in one)}. Coincidono {labels['Coincide']}, diverse {labels['Diverso']}, aperte {labels['Aperto']}. Variazioni rispetto all’ultima elaborazione locale {changes}."
print(stats,conflicts,catalog,len(groups['Conflitti fra metodi']))
html='<!doctype html><html lang="it"><meta charset="utf-8"><title>BankMerge · confronto locale</title><style>body{font:16px system-ui;margin:2rem;color:#26301b}summary{cursor:pointer;padding:.6em;font-weight:600}table{border-collapse:collapse;font-size:14px}td,th{padding:.45em;border:1px solid #ccd3c5;vertical-align:top;overflow-wrap:anywhere}th{background:#edf1e6}</style><h1>BankMerge · confronto locale</h1><p>'+stats+'</p><p>Il motore ha valutato i movimenti prima di leggere le decisioni di Bank1. La prova usa le regole e le configurazioni disponibili. Per coincidere occorrono stato riconciliato e identità di WHO, codice WHY e codice WHAT. Le proposte storiche di Bank1 sono indicate separatamente dalle conferme umane. Le sezioni sono viste sugli stessi movimenti.</p>'+''.join(sections)+'</html>'
(b/'Confronto BankMerge.html').write_text(html,encoding='utf-8')
pg.close()
