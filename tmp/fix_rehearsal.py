from pathlib import Path
p=Path('tmp/rehearse_anagrafica_release.py');t=p.read_text(encoding='utf-8');a=t.index('c=psycopg2.connect');b=t.index('url=f',a);t=t[:a]+t[b:];t=t.replace(",'bank_transactions'",'');p.write_text(t,encoding='utf-8')
