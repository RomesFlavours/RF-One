import boto3,json,requests,time,concurrent.futures
from datetime import datetime,timezone,timedelta
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');c=s.client('cloudwatch');l=s.client('logs');now=datetime.now(timezone.utc)
metrics=c.list_metrics(Namespace='AWS/AppRunner',Dimensions=[{'Name':'ServiceName','Value':'rfone-web'}])['Metrics']
for m in metrics:
 if m['MetricName'] in ['RequestLatency','CPUUtilization','MemoryUtilization','5xxStatusResponses','Requests','ActiveInstances']:
  data=c.get_metric_statistics(Namespace=m['Namespace'],MetricName=m['MetricName'],Dimensions=m['Dimensions'],StartTime=now-timedelta(hours=3),EndTime=now,Period=300,Statistics=['Average','Maximum','Sum'])['Datapoints']; data=sorted(data,key=lambda x:x['Timestamp'])
  print('METRIC',m['MetricName'],json.dumps([{k:str(v) if k=='Timestamp' else v for k,v in p.items()} for p in data[-8:]]))
group='/aws/apprunner/rfone-web/07524815436944e3a05c600c5486f951/application'
streams=l.describe_log_streams(logGroupName=group,orderBy='LastEventTime',descending=True,limit=3)['logStreams']
for stream in streams:
 print('STREAM',stream['logStreamName'],'LAST',stream.get('lastEventTimestamp'))
 r=l.get_log_events(logGroupName=group,logStreamName=stream['logStreamName'],limit=35,startFromHead=False)
 for e in r['events']:print(e['message'][:700])
def probe(path):
 r=requests.Session();r.trust_env=False;start=time.perf_counter();x=r.get('https://rfone.romesflavours.com'+path,allow_redirects=False,timeout=45);return {'path':path,'status':x.status_code,'seconds':round(time.perf_counter()-start,3),'server':x.headers.get('server'),'cache':x.headers.get('x-cache')}
print('HTTP',json.dumps(list(concurrent.futures.ThreadPoolExecutor(max_workers=3).map(probe,['/login','/admin/roles?tab=people','/admin/roles?tab=roles']))))
