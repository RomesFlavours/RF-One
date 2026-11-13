from pathlib import Path
p=Path('tmp/git-anagrafica-release/03 Software/Infrastructure/deploy/registry-authorization/test_service.py');s=p.read_text(encoding='utf-8').replace("dir=root/'tmp',prefix='release-policy-'","dir=Path(tempfile.gettempdir()),prefix='release-policy-'");p.write_text(s,encoding='utf-8',newline='\n')
