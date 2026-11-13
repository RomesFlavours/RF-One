"""Read Clover shifts completely; plan local-only 15-day inactivity dismissals."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import json,sys,boto3,requests,time
from sqlalchemy import create_engine,select
root=Path.cwd();state=json.loads((root/'tmp/copy_employee_directory_aws.json').read_text());sys.path.insert(0,str(root/'tmp/role-company-development/RF-One Data Store'))
from rfone_data_store import models as m,employee_directory as directory,access_profiles as profiles
from sqlalchemy.orm import Session
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');a=s.client('apprunner');v=next(v for v in a.list_services()['ServiceSummaryList'] if v['ServiceName']=='rfone-web');cfg=a.describe_service(ServiceArn=v['ServiceArn'])['Service']['SourceConfiguration']['ImageRepository']['ImageConfiguration'];task=s.client('ecs').describe_task_definition(taskDefinition=cfg['RuntimeEnvironmentVariables']['RFONE_CLOVER_JOB_ECS_TASK_DEFINITION'])['taskDefinition'];secrets={x['name']:x['valueFrom'] for c in task['containerDefinitions'] for x in c.get('secrets',[])}
sm=s.client('secretsmanager')
def secret(name):
    arn=secrets[name];parts=arn.split(':');key=parts[7] if len(parts)>7 else None;arn=':'.join(parts[:7]);value=sm.get_secret_value(SecretId=arn)['SecretString']
    if key:value=json.loads(value)[key]
    else:
        try:
            parsed=json.loads(value)
            if isinstance(parsed,dict):value=parsed.get(name,parsed.get('value',''))
            elif isinstance(parsed,str):value=parsed
        except json.JSONDecodeError:pass
    return value
merchant=secret('CLOVER_MERCHANT_ID');token=secret('CLOVER_API_TOKEN')
now=datetime.now(timezone.utc);cutoff=now-timedelta(days=15)
http=requests.Session();http.headers.update({'Authorization':'Bearer '+token})
def collection(path):
    all_rows=[];offset=0;seen=set()
    while True:
        for attempt in range(8):
            r=http.get('https://api.clover.com/v3/merchants/'+merchant+'/'+path,params={'limit':1000,'offset':offset},timeout=45)
            if r.status_code!=429:break
            delay=min(30,max(5,float(r.headers.get('Retry-After','5')))*(attempt+1))
            print(f'Rate limit; retry in {delay}s',flush=True);time.sleep(delay)
        time.sleep(1.5)
        if r.status_code!=200:raise RuntimeError(f'Clover {path}: HTTP {r.status_code}; no local changes')
        data=r.json()
        if not isinstance(data,dict) or not isinstance(data.get('elements'),list):raise RuntimeError('Incomplete Clover response')
        rows=data['elements']
        if not rows:break
        for row in rows:
            if not row.get('id') or row['id'] in seen:raise RuntimeError('Pagination incomplete/repeated')
            seen.add(row['id'])
        all_rows.extend(rows);offset+=len(rows)
        print(f'{path}: {len(all_rows)} read',flush=True)
    return all_rows
employees=collection('employees');shifts=collection('shifts')
last={};last_in={}
for row in shifts:
    identity=(row.get('employee') or {}).get('id')
    if not identity:raise RuntimeError('Shift without employee; no dismissal')
    ins=[row.get(k) for k in ('inTime','overrideInTime') if row.get(k)]
    instants=ins+[row.get(k) for k in ('outTime','overrideOutTime') if row.get(k)]
    if instants:last[identity]=max(last.get(identity,0),*instants)
    for field,timefield in (('overrideInEmployee','overrideInTime'),('overrideOutEmployee','overrideOutTime')):
        other=(row.get(field) or {}).get('id')
        instant=row.get(timefield)
        if other and instant:last[other]=max(last.get(other,0),instant)
    if ins:last_in[identity]=max(last_in.get(identity,0),*ins)
local=state['local_database'];assert local['host']=='127.0.0.1'
engine=create_engine(f"postgresql+psycopg2://{local['username']}@127.0.0.1:{local['port']}/{local['database']}")
plan={'at':now.isoformat(),'cutoff':cutoff.isoformat(),'scope':'LOCAL_ONLY','clover_shifts_read':len(shifts),'clover_employees_read':len(employees),'dismiss':[],'retain':[],'skip':[]}
with Session(engine) as db:
    for person in db.scalars(directory.canonical_employees().order_by(m.Employee.id)):
        if not directory.employee_is_active(person,[]):continue
        links=list(db.scalars(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.employee_id==person.id)))
        entry={'id':person.id,'name':person.display_name}
        if not links:entry['reason']='No Clover identity';plan['skip'].append(entry);continue
        if any(l.merchant_id!=merchant for l in links):entry['reason']='Other location not configured; no complete verification';plan['skip'].append(entry);continue
        ids=[l.external_employee_id for l in links]
        recent=max([last.get(i,0) for i in ids],default=0)
        if recent>=cutoff.timestamp()*1000:plan['retain'].append(entry);continue
        clockin=max([last_in.get(i,0) for i in ids],default=0)
        entry.update(last_punch=datetime.fromtimestamp(recent/1000,timezone.utc).isoformat() if recent else None,dismissal_date=(datetime.fromtimestamp(clockin/1000,timezone.utc) if clockin else now).date().isoformat(),reason='No Clover clock-in/out in previous 15 days',date_basis='last_clock_in' if clockin else 'execution_date_no_clock_history')
        plan['dismiss'].append(entry)
    known={l.external_employee_id for l in db.scalars(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.merchant_id==merchant,m.EmployeeCloverLink.employee_id.is_not(None)))}
    plan['unmapped_recent_identities']=sorted(i for i,v in last.items() if i not in known and v>=cutoff.timestamp()*1000)
    names={e['id']:e.get('name') or ' '.join(str(e.get(k) or '') for k in ('firstName','lastName')).strip() for e in employees}
    plan['unmapped_recent']=[{'external_id':i,'name':names.get(i)} for i in plan['unmapped_recent_identities']]
    normalized=lambda name:' '.join(sorted((name or '').casefold().split()))
    ambiguous={normalized(names.get(i)) for i in plan['unmapped_recent_identities'] if names.get(i)}
    held=[v for v in plan['dismiss'] if normalized(v['name']) in ambiguous]
    for v in held:v['reason']='Recent unlinked Clover identity with matching name; reconciliation required';plan['skip'].append(v)
    plan['dismiss']=[v for v in plan['dismiss'] if v not in held]
path=root/'tmp/clover_15day_local_plan.json';path.write_text(json.dumps(plan,indent=2),encoding='utf-8')
print(json.dumps({'shifts_read':len(shifts),'dismiss_count':len(plan['dismiss']),'retain_count':len(plan['retain']),'skip_count':len(plan['skip']),'unmapped_recent':len(plan['unmapped_recent_identities'])}))
