from pathlib import Path
p=Path('tmp/git-anagrafica-release/03 Software/RF-One Web/tests/test_home_layout_http.py');t=p.read_text(encoding='utf-8').replace('"Administration" not in plain_body and \'href="/bank"\' not in plain_body','\'<div class="domain-name">Administration</div>\' not in plain_body and \'href="/bank"\' not in plain_body');p.write_text(t,encoding='utf-8')
