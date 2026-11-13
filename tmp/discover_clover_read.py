import boto3,json,os
from botocore.config import Config
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');a=s.client('apprunner',config=Config(connect_timeout=10,read_timeout=20,retries={'max_attempts':1}))
try:
    services=a.list_services()['ServiceSummaryList']
    for v in services:
        if any(x in v['ServiceName'].lower() for x in ('sync','acquisition','web')):
            d=a.describe_service(ServiceArn=v['ServiceArn'])['Service']['SourceConfiguration'].get('ImageRepository',{}).get('ImageConfiguration',{})
            print(json.dumps({'service':v['ServiceName'],'variables':list(d.get('RuntimeEnvironmentVariables',{})),'secret_keys':list(d.get('RuntimeEnvironmentSecrets',{}))}))
except Exception as e:print(type(e).__name__);raise SystemExit(1)
