from pathlib import Path
import json,boto3
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');root=Path('tmp/anagrafica-release');p=root/'state.json';d=json.loads(p.read_text());r=s.client('ecr').describe_images(repositoryName='rfone-web',imageIds=[{'imageTag':d['tag']}])['imageDetails'][0];d['image_digest']=r['imageDigest'];p.write_text(json.dumps(d,indent=2));print(json.dumps({'digest':d['image_digest']}))
