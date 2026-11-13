from pathlib import Path
import json,shutil,hashlib
root=Path.cwd();target=root/'tmp/git-anagrafica-release';state=json.loads((root/'tmp/copy_employee_directory_aws.json').read_text());source=Path(state['folder'])/'source'
for rel,digest in state['source_files'].items():
    if not rel.startswith(('RF-One Web/','RF-One Data Store/','Training/','Shared UI/','Clover Data Explorer/')):continue
    file=source/rel;assert hashlib.sha256(file.read_bytes()).hexdigest()==digest
    destination=target/'03 Software'/rel;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(file,destination)
print('Recovered immutable pre-release AWS runtime in isolated Git worktree')
