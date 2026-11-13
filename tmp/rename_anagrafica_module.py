from pathlib import Path
p=Path('03 Software/RF-One Web/templates/role_profiles.html');t=p.read_text(encoding='utf-8').replace('Roles & companies','Anagrafica');p.write_text(t,encoding='utf-8')
p=Path('tmp/prepare_role_company_development.py');t=p.read_text(encoding='utf-8').replace('Roles &amp; companies','Anagrafica').replace('Roles, areas &amp; companies','Anagrafica').replace('Manage roles &amp; companies','Anagrafica');p.write_text(t,encoding='utf-8')
