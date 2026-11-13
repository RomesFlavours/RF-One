from pathlib import Path
s=Path('tmp/fix_anthony_kitchen_local.py').read_text(encoding='utf-8')
a=s.index('csrf=re.search');b=s.index('chooser=c.get',a)
s=s[:a]+"assert 'account_label' in c.get(base+'/admin/roles?tab=people',timeout=30).text\n"+s[b:]
Path('tmp/verify_anthony_kitchen_local.py').write_text(s,encoding='utf-8')
