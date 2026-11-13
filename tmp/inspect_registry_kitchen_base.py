from pathlib import Path
import boto3,zipfile,io,json,hashlib,difflib
root=Path.cwd();s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');key='kitchen/home/e65f9b37dabb725aa057c889afe499c7a51e537f/source.zip';payload=s.client('s3').get_object(Bucket='rfone-tips-deploy-418674484214',Key=key)['Body'].read();(root/'tmp/registry-home-release/current-kitchen-source.zip').write_bytes(payload)
with zipfile.ZipFile(io.BytesIO(payload)) as current,zipfile.ZipFile(root/'tmp/anagrafica-release/source.zip') as old:
 changed=[n for n in current.namelist() if n not in old.namelist() or current.read(n)!=old.read(n)]
 print('Changed paths',json.dumps(changed))
 name='RF-One Web/templates/home.html';print(''.join(difflib.unified_diff(old.read(name).decode().splitlines(True),current.read(name).decode().splitlines(True),fromfile='anagrafica',tofile='current-kitchen')))
