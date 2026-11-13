from pathlib import Path
p=Path('tmp/git-anagrafica-release/03 Software/RF-One Web/tests/test_role_company_http.py');s=p.read_text(encoding='utf-8').replace("f'/admin/accounts/{aid}/edit#reset-password' in reset_open.location","f'/admin/accounts/{aid}/edit?from_person=' in reset_open.location and reset_open.location.endswith('#reset-password')");p.write_text(s,encoding='utf-8',newline='\n')
