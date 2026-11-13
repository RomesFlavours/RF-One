from pathlib import Path
import boto3,json,zipfile,io,hashlib,concurrent.futures
root=Path('tmp/registry-access-release');builds=json.loads((root/'builds.json').read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');s3=s.client('s3')
refs={'web':next(v['source'] for v in builds['rfone-web-build'] if 'registry-contacts-20261110t161756z/' in v['source']), 'training':builds['rfone-web-build'][0]['source'],'kitchen':next(v['source'] for v in builds['rfone-web-build'] if 'kitchen/releases/452568864b54' in v['source']),'tips':builds['rfone-tips-build'][0]['source'],'selection':builds['rfone-selection-build'][0]['source']}
def fetch(item):
 name,ref=item;bucket,key=ref.split('/',1);payload=s3.get_object(Bucket=bucket,Key=key)['Body'].read();(root/(name+'-baseline.zip')).write_bytes(payload);folder=(root/(name+'-source')).resolve();folder.mkdir(exist_ok=True)
 with zipfile.ZipFile(io.BytesIO(payload)) as z:
  for member in z.infolist():assert (folder/member.filename).resolve().is_relative_to(folder)
  z.extractall(folder)
 return name,{'source':ref,'sha256':hashlib.sha256(payload).hexdigest(),'files':len(list(folder.rglob('*')))}
result=dict(concurrent.futures.ThreadPoolExecutor(max_workers=5).map(fetch,refs.items()));(root/'sources.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
