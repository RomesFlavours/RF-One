from pathlib import Path
p=Path('tmp/git-anagrafica-release/03 Software/Infrastructure/deploy/registry-authorization/package_context.py')
p.write_text('''"""Package a reproduced source with immutable commit provenance and image guards."""
from pathlib import Path
import hashlib,shutil,sys,zipfile
HERE=Path(__file__).resolve().parent

def package(service, context, commit, archive):
    assert len(commit)==40 and all(c in '0123456789abcdef' for c in commit)
    (context/'RELEASE_COMMIT').write_text(commit+'\\n',encoding='utf-8',newline='\\n')
    shutil.copyfile(HERE/'test_service.py',context/'release_policy_test.py')
    docker=context/'Dockerfile'
    text=docker.read_text(encoding='utf-8')
    marker='COPY release_policy_test.py /app/release_policy_test.py'
    if marker not in text:
        text+='\\n'+marker+'\\nRUN python "/app/RF-One Data Store/check_migration_chain.py" --aws-revision t9a120261110\\nRUN python /app/release_policy_test.py '+service+' /app\\n'
        docker.write_text(text,encoding='utf-8',newline='\\n')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for file in context.rglob('*'):
            if not file.is_file() or '__pycache__' in file.parts or file.suffix in ('.pyc','.db','.sqlite','.dump') or file.name=='.env':continue
            assert file.name!='launch_local.py'
            if file.suffix in ('.py','.js','.html'):
                data=file.read_bytes()
                assert b'rfone_local_user_choice' not in data and b'/local/access-user' not in data,file
            bundle.write(file,file.relative_to(context).as_posix())
    return hashlib.sha256(archive.read_bytes()).hexdigest()

if __name__=='__main__':
    print(package(sys.argv[1],Path(sys.argv[2]),sys.argv[3],Path(sys.argv[4])))
''',encoding='utf-8',newline='\n')
