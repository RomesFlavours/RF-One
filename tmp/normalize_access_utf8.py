from pathlib import Path
base=Path(r'C:\Users\servi\.codex\worktrees\edee\RF One\tmp\git-anagrafica-release\03 Software')
for file in ('RF-One Web/role_profile_routes.py','RF-One Web/training_integration.py','RF-One Web/kitchen_cloud.py','RF-One Web/kitchen_routes.py'):
 p=base/file;s=p.read_text(encoding='utf-8')
 try:fixed=s.encode('cp1252').decode('utf-8')
 except (UnicodeEncodeError,UnicodeDecodeError):continue
 if fixed!=s:p.write_text(fixed,encoding='utf-8',newline='\n');print('Encoding normalized',file)
