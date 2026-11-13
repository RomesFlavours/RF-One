from pathlib import Path
import shutil
repo=Path('tmp/git-anagrafica-release');local=Path(r'C:/Users/servi/AppData/Local/RF-One/Compensation/AWS-20261110T214612Z/development-source/RF-One Web')
for name in ('templates/compensation_run_detail.html','static/js/compensation-checks.js'):
 shutil.copyfile(local/name,repo/'03 Software/RF-One Web'/name)
