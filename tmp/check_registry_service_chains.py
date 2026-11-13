from pathlib import Path
import subprocess,sys
root=Path('tmp/registry-access-release')
for service in ('web','tips','selection','training','kitchen'):
 folder=root/(service+'-source');base=folder/'03 Software' if (folder/'03 Software').exists() else folder
 result=subprocess.run([sys.executable,str(base/'RF-One Data Store/check_migration_chain.py'),'--aws-revision','t9a120261110'],capture_output=True,text=True)
 print(service,result.returncode,result.stdout.strip(),result.stderr[-500:])
