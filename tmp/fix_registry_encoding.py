from pathlib import Path
p=Path('tmp/git-anagrafica-release/03 Software/RF-One Web/role_profile_routes.py');s=p.read_text(encoding='utf-8');start=s.index('                for member,company');end=s.index('                g._registry_summaries_loaded',start);s=s[:start]+''.join('    '+line+'\n' for line in s[start:end].splitlines())+s[end:]
original=Path('tmp/registry-performance/before/role_profile_routes.py').read_text(encoding='utf-8')
for char in set(original):
 if ord(char)>127:
  try:bad=char.encode('utf-8').decode('cp1252')
  except UnicodeDecodeError:continue
  s=s.replace(bad,char)
p.write_text(s,encoding='utf-8',newline='\n')
