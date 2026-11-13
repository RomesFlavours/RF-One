from pathlib import Path
root=Path.cwd();s=(root/'tmp/check_anagrafica_deploy.py').read_text(encoding='utf-8-sig').replace('tmp/anagrafica-release','tmp/registry-home-release');(root/'tmp/check_registry_home_deploy.py').write_text(s,encoding='utf-8')
