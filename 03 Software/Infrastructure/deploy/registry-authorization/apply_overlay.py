"""Reproduce a Registry authorization release from a hash-pinned service source.

No credentials, AWS calls, migrations or deployment. Usage:
python apply_overlay.py SERVICE BASELINE_ZIP OUTPUT_DIRECTORY
"""
from pathlib import Path
import hashlib,json,re,sys,zipfile
HERE=Path(__file__).resolve().parent

def apply(service, baseline_zip, output):
    spec=json.loads((HERE/'manifest.json').read_text(encoding='utf-8'))['services'][service]
    assert hashlib.sha256(baseline_zip.read_bytes()).hexdigest()==spec['baseline']['sha256'],'Baseline source changed'
    patch=HERE/'patches'/(service+'.patch')
    assert hashlib.sha256(patch.read_bytes()).hexdigest()==spec['patch_sha256'],'Patch changed'
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(baseline_zip) as archive:
        for name in archive.namelist():assert (output/name).resolve().is_relative_to(output)
        archive.extractall(output)
    blocks={};name=None
    for line in patch.read_text(encoding='utf-8').splitlines():
        if line.startswith('--- a/'):
            name=line[len('--- a/'):];blocks[name]=[]
        elif name is not None and not line.startswith('+++ b/'):
            blocks[name].append(line)
    for name,change in spec['changes'].items():
        path=output/name
        assert path.resolve().is_relative_to(output)
        before=path.read_bytes() if path.exists() else None
        assert (hashlib.sha256(before).hexdigest() if before is not None else None)==change['before'],name
        if change['after'] is None:
            path.unlink();continue
        lines=before.decode('utf-8').splitlines() if before is not None else []
        result=[];position=0
        for line in blocks.get(name,[]):
            if line.startswith('@@'):
                header=re.match(r'@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@',line)
                assert header,line
                start=max(0,int(header[1])-1);assert start>=position
                result.extend(lines[position:start]);position=start
            elif line.startswith(' '):
                assert lines[position]==line[1:],name
                result.append(line[1:]);position+=1
            elif line.startswith('-'):
                assert lines[position]==line[1:],name
                position+=1
            elif line.startswith('+'):
                result.append(line[1:])
        result.extend(lines[position:])
        data=('\n'.join(result)+('\n' if change['newline'] else '')).encode('utf-8')
        assert hashlib.sha256(data).hexdigest()==change['after'],name
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    return output

if __name__=='__main__':
    apply(sys.argv[1],Path(sys.argv[2]),Path(sys.argv[3]))
    print('Verified authorization overlay applied:',sys.argv[1])
