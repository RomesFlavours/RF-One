from pathlib import Path
import boto3,json
root=Path('tmp/registry-access-release');p=root/'release-state.json';state=json.loads(p.read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');cloud=s.client('cloudfront');matches=[]
for page in cloud.get_paginator('list_distributions').paginate():
 for d in page.get('DistributionList',{}).get('Items',[]):
  if 'rfone.romesflavours.com' in d.get('Aliases',{}).get('Items',[]):matches.append(d['Id'])
assert len(matches)==1,matches;state['cloudfront_distribution']=matches[0];p.write_text(json.dumps(state,indent=2));print('RF1 distribution identified; invalidation will follow completed deployments.')
