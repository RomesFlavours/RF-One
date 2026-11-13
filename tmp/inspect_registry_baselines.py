from pathlib import Path
import hashlib
r=Path('tmp/registry-access-release')
for n in ('web','tips','selection','training','kitchen'):
 root=r/(n+'-source');base=root/'03 Software' if (root/'03 Software').exists() else root
 print(n)
 for file in ('RF-One Data Store/rfone_data_store/models.py','RF-One Data Store/rfone_data_store/employee_directory.py','RF-One Data Store/rfone_data_store/rfone_account_service.py','RF-One Data Store/rfone_data_store/rfone_web_session.py','RF-One Web/training_integration.py'):
  p=base/file
  if p.exists():
   s=p.read_text(encoding='utf-8');print(file.split('/')[-1],len(s),'foundation', 'context_person_id' in s,'passwordchange','must_change_password' in s)
