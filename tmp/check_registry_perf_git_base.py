import subprocess,hashlib,json
base='tmp/git-anagrafica-release';ref='consolidate/training-registry-20261112'
for name in ('role_profile_routes.py','registry_clover.py','tests/test_registry_clover_confirmation.py'):
 try:
  data=subprocess.check_output(['git','-C',base,'show',ref+':03 Software/RF-One Web/'+name]);print(name,hashlib.sha256(data).hexdigest())
 except subprocess.CalledProcessError:pass
print(subprocess.check_output(['git','-C',base,'log','-1','--oneline',ref],text=True))
