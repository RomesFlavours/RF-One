from pathlib import Path
p=Path('tmp/verify_registry_local_users.py');s=p.read_text(encoding='utf-8').replace("if not expected and actual==302:passed='/training' not in response.headers.get('Location','')","if not expected and actual==302:\n    from urllib.parse import urlsplit\n    passed=urlsplit(response.headers.get('Location','')).path in ('/','/login','/local/users','/training/login')")
p.write_text(s,encoding='utf-8',newline='\n')
