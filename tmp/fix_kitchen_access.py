from pathlib import Path
import shutil
base=Path(r'C:\Users\servi\.codex\worktrees\edee\RF One\tmp\git-anagrafica-release\03 Software')
frozen=Path(r'C:\Users\servi\OneDrive\AI-RF-ONE\RF One\output\kitchen-release\source\03 Software')
for name in ('RF-One Web','RF-One Data Store/rfone_data_store'):
 for src in (frozen/name).glob('kitchen*.py'):
  dst=base/name/src.name
  if not dst.exists():shutil.copy2(src,dst)
for name in ('templates','static/css','static/js'):
 for src in (frozen/'RF-One Web'/name).glob('kitchen*'):
  dst=base/'RF-One Web'/name/src.name
  if src.is_dir():shutil.copytree(src,dst,dirs_exist_ok=True)
  elif not dst.exists():shutil.copy2(src,dst)
p=base/'RF-One Web/kitchen_cloud.py';s=p.read_text();s=s.replace("app=Flask(__name__,static_url_path='/kitchen/static')","app=Flask(__name__,static_url_path='/kitchen/static')\nfrom rfone_data_store.web_access import install_access_context\ninstall_access_context(app, SessionFactory, load_current_account)");p.write_text(s,encoding='utf-8',newline='\n')
p=base/'RF-One Web/kitchen_routes.py';s=p.read_text();start=s.index('    from flask import current_app');end=s.index('\n\n\ndef register_kitchen_routes',start);s=s[:start]+'''    from rfone_data_store import rfone_web_session as shared
    items = shared.allowed_domain_items(db, account, 'KITCHEN')
    if items is None:
        return list(TABS)
    return [tab for tab in TABS if tab[0] in items]
'''+s[end:];p.write_text(s,encoding='utf-8',newline='\n')
print('Kitchen copied from frozen released source; raw SQL permissions replaced with shared policy.')
