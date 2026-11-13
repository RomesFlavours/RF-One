from pathlib import Path
import boto3,json,copy
root=Path('tmp/registry-access-release');p=root/'release-state.json';state=json.loads(p.read_text());assert state['audit_verified'];assert all(i['build_status']=='SUCCEEDED' for i in state['services'].values());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');ap=s.client('apprunner');ecr=s.client('ecr')
for name,item in state['services'].items():
 current=ap.describe_service(ServiceArn=item['service_arn'])['Service'];assert current['Status']=='RUNNING',name;assert current['SourceConfiguration']['ImageRepository']['ImageIdentifier']==item['previous_image'],name+' changed concurrently'
 image=item['image'];repository=image.split('/',1)[1].split(':',1)[0];digest=ecr.describe_images(repositoryName=repository,imageIds=[{'imageTag':item['tag']}])['imageDetails'][0]['imageDigest'];item['image_digest']=digest;(root/(name+'-baseline-service.json')).write_text(json.dumps(current,default=str,indent=2))
for name,item in state['services'].items():
 current=json.loads((root/(name+'-baseline-service.json')).read_text());config=copy.deepcopy(current['SourceConfiguration']);config['ImageRepository']['ImageIdentifier']=item['image'];config['ImageRepository'].setdefault('ImageConfiguration',{}).setdefault('RuntimeEnvironmentVariables',{})['RFONE_RELEASE_REVISION']=state['commit'];r=ap.update_service(ServiceArn=item['service_arn'],SourceConfiguration=config);item['deploy_operation']=r['OperationId'];p.write_text(json.dumps(state,indent=2));print(name,item['deploy_operation'],flush=True)
