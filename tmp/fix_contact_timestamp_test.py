from pathlib import Path
p=Path('tmp/git-anagrafica-release/03 Software/RF-One Web/tests/test_role_company_http.py');t=p.read_text(encoding='utf-8').replace('account.email_verified_at==verified','account.email_verified_at.replace(tzinfo=None)==verified.replace(tzinfo=None)');p.write_text(t,encoding='utf-8')
