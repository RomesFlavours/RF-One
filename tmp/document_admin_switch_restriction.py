from pathlib import Path
import shutil
base=Path('tmp/git-anagrafica-release')
shutil.copyfile(base/'03 Software/Infrastructure/Registry Local/launch_local.py',Path('tmp/launch_registry_local.py'))
addition='''

## Switch user administrator restriction — 2026-11-10

At the Product Owner request, the local selector is visible and usable only by a
currently valid RF1 platform administrator/owner. Both chooser GET and switch POST
check the current account server-side. Domain administration alone is insufficient.
After switching to an ordinary user the selector disappears and both endpoints
return 403; inactive/revoked sessions are also denied. No retained administrator
privilege is attached to the impersonated user's session. Verified against the
7 accounts currently in the local database: 31 checks passed. No account grants,
AWS configuration or production source were changed by this restriction.
'''
for p in [base/'07 Tasks/Reports/REGISTRY_AUTHORIZATION_LOCAL_FIX_20261110_REPORT.md',Path('07 Tasks/Reports/REGISTRY_AUTHORIZATION_LOCAL_FIX_20261110_REPORT.md'),base/'10 System/Identity & Access/Role Profiles and Company Access.md']:
 p.write_text(p.read_text(encoding='utf-8')+addition,encoding='utf-8',newline='\n')
