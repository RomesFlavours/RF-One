from pathlib import Path
import shutil
base=Path('tmp/registry-access-release/kitchen-source/03 Software/RF-One Data Store/rfone_data_store');canonical=Path('tmp/git-anagrafica-release/03 Software/RF-One Data Store/rfone_data_store')
shutil.copytree(canonical/'training',base/'training',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copyfile(canonical/'acting_identity_service.py',base/'acting_identity_service.py')
