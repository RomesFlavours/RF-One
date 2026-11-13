from pathlib import Path
import hashlib
root=Path('tmp/registry-navigation/before');deployed=Path('tmp/registry-clover-release/verification-source/RF-One Web')
for name in ('app.py','templates/admin_account_access.html','templates/admin_account_form.html','templates/admin_account_training_link.html','static/js/role-profiles.js','templates/role_profiles.html'):
 a=(root/name).read_bytes();p=deployed/name
 print(name,hashlib.sha256(a).hexdigest(), 'matches extracted AWS' if p.exists() and a==p.read_bytes() else 'needs baseline check')
