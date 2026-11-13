from pathlib import Path
import zipfile,json,hashlib,py_compile
root=Path.cwd();dev=root/'tmp/role-company-development';out=root/'tmp/anagrafica-release';tag='anagrafica-20261110t'+__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%H%M%Sz')
with zipfile.ZipFile(root/'tmp/aws-current-build-source.zip') as previous:
    docker=previous.read('Dockerfile')
# Production image uses canonical authentication; the private local wrapper is outside this tree.
assert not (dev/'launch_local.py').exists()
with zipfile.ZipFile(out/'source.zip','w',zipfile.ZIP_DEFLATED) as z:
    for folder in ('RF-One Data Store','RF-One Web','Training','Shared UI','Clover Data Explorer'):
        for p in (dev/folder).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.db','.dump') and p.name!='.env':z.write(p,p.relative_to(dev).as_posix())
    z.writestr('Dockerfile',docker)
state=json.loads((out/'state.json').read_text());state.update(tag=tag,source_sha256=hashlib.sha256((out/'source.zip').read_bytes()).hexdigest());(out/'state.json').write_text(json.dumps(state,indent=2));print(json.dumps({'tag':tag,'source_bytes':(out/'source.zip').stat().st_size}))
