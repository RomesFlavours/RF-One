from pathlib import Path
import ast,shutil
root=Path('tmp/registry-access-release');canonical=Path('tmp/git-anagrafica-release/03 Software')
def revision(path):
 for n in ast.parse(path.read_text(encoding='utf-8')).body:
  targets=n.targets if isinstance(n,ast.Assign) else [n.target] if isinstance(n,ast.AnnAssign) else []
  if any(isinstance(t,ast.Name) and t.id=='revision' for t in targets):return ast.literal_eval(n.value)
versions=canonical/'RF-One Data Store/migrations/versions';known={revision(p):p for p in versions.glob('*.py') if revision(p)}
for service in ('web','tips','selection','training','kitchen'):
 folder=root/(service+'-source');base=folder/'03 Software' if (folder/'03 Software').exists() else folder
 target=(base/'RF-One Data Store/migrations/versions').resolve()
 for p in list(target.glob('*.py')):
  rev=revision(p)
  if rev and (rev not in known or p.name!=known[rev].name):
   assert p.resolve().parent==target;p.unlink()
 for p in known.values():shutil.copyfile(p,target/p.name)
 for name in ('kitchen.py','kitchen_configuration.py'):
  targetfile=base/'RF-One Data Store/rfone_data_store'/name
  if not targetfile.exists():shutil.copyfile(canonical/'RF-One Data Store/rfone_data_store'/name,targetfile)
print('Aligned package migration source trees to the already-applied shared chain.')
