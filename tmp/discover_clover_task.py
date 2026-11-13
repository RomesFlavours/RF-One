exec(open('tmp/discover_clover_read.py',encoding='utf-8-sig').read().split('try:')[0])
v=next(v for v in a.list_services()['ServiceSummaryList'] if v['ServiceName']=='rfone-web');cfg=a.describe_service(ServiceArn=v['ServiceArn'])['Service']['SourceConfiguration']['ImageRepository']['ImageConfiguration']
t=s.client('ecs').describe_task_definition(taskDefinition=cfg['RuntimeEnvironmentVariables']['RFONE_CLOVER_JOB_ECS_TASK_DEFINITION'])['taskDefinition']
for c in t['containerDefinitions']:print(json.dumps({'container':c['name'],'env_keys':[v['name'] for v in c.get('environment',[])],'secret_keys':[v['name'] for v in c.get('secrets',[])]}))
