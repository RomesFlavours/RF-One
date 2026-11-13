import boto3,json
from datetime import datetime,timezone,timedelta
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');a=s.client('apprunner');arn='arn:aws:apprunner:us-east-1:418674484214:service/rfone-web/07524815436944e3a05c600c5486f951'
v=a.describe_service(ServiceArn=arn)['Service'];print(json.dumps({'status':v['Status'],'image':v['SourceConfiguration']['ImageRepository']['ImageIdentifier'],'instance':v['InstanceConfiguration']['Cpu']+' CPU / '+v['InstanceConfiguration']['Memory'],'updated':str(v['UpdatedAt'])}));l=s.client('logs');groups=l.describe_log_groups(logGroupNamePrefix='/aws/apprunner/rfone-web/')['logGroups'];print('GROUPS',[(g['logGroupName']) for g in groups]);
for g in groups:
 if g['logGroupName'].endswith('/application'):
  r=l.filter_log_events(logGroupName=g['logGroupName'],startTime=int((datetime.now(timezone.utc)-timedelta(minutes=45)).timestamp()*1000),limit=150)
  for e in r['events']:print(e['message'][:1200])
