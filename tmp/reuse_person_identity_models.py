from pathlib import Path
import shutil
base=Path('tmp/git-anagrafica-release/03 Software');source=Path('C:/Users/servi/OneDrive/AI-RF-ONE/RF One/03 Software/RF-One Data Store/rfone_data_store')
for name in ('people_registry.py','student_registry.py'):shutil.copyfile(source/name,base/'RF-One Data Store/rfone_data_store'/name)
