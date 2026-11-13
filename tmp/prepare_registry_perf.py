from pathlib import Path
import shutil
root=Path('tmp/git-anagrafica-release/03 Software/RF-One Web');out=Path('tmp/registry-performance/before');out.mkdir(parents=True,exist_ok=True)
for name in ('role_profile_routes.py','registry_clover.py'):shutil.copyfile(root/name,out/name)
