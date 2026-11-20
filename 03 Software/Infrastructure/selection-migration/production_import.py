"""Reviewed, targeted Selection import. Default is local/check; never restore a database.

Production writes require an explicit mode, two gates and an approval bound to plan+target.
No upload/delete API is implemented here: original S3 objects must already be verified.
"""
import argparse,copy,hashlib,json,os,sys,re
from datetime import datetime,timezone,date
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import create_engine,MetaData,Table,select,insert,update,delete,text,inspect
from sqlalchemy.engine import make_url
from sqlalchemy.types import JSON,Boolean,DateTime,Date

REPO=Path(__file__).resolve().parents[3];APP=REPO/'03 Software/AWSSelection/Selection'
sys.path[:0]=[str(APP),str(APP.parent/'RF-One Data Store')]
from workspace import schema
from rfone_data_store.models import Base

LEDGER='selection_migration_batches'
TABLES={'selection_workspace_job_roles','selection_workspace_automation_items','selection_workspace_pdl_rules','selection_workspace_observation_templates',
    'requirement_sets','requirements','requirement_set_snapshots','requirement_snapshot_items','selection_workspace_positions','raw_resumes','candidate_persons','candidates',
    'candidate_work_history','candidate_education','candidate_skills','candidate_certifications','candidate_languages','applications','selection_workspace_position_candidates',
    'selection_workspace_decisions','selection_workspace_events','selection_workspace_action_runs'}
CUSTOM={'selection_workspace_events':{'position_candidate_id':'selection_workspace_position_candidates'},
    'requirement_snapshot_items':{'source_requirement_id':'requirements'},
    'selection_workspace_positions':{'role_code':'selection_workspace_job_roles'},
    'applications':{'target_role':'selection_workspace_job_roles'},'candidates':{'target_role':'selection_workspace_job_roles'},
    'requirement_sets':{'target_role':'selection_workspace_job_roles'},'requirement_set_snapshots':{'target_role':'selection_workspace_job_roles'}}
JSON_REFS={'position_candidate_id':'selection_workspace_position_candidates','candidate_id':'candidates','application_id':'applications','raw_resume_id':'raw_resumes',
    'decision_id':'selection_workspace_decisions','event_id':'selection_workspace_events','outbox_id':'selection_workspace_email_outbox'}


class PlanError(RuntimeError):pass


def canonical(value):
    if isinstance(value,datetime):return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
    if isinstance(value,date):return value.isoformat()
    if isinstance(value,dict):return {str(k):canonical(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [canonical(v) for v in value]
    return value


def digest(value):return hashlib.sha256(json.dumps(canonical(value),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def load_plan(path):
    plan=json.loads(Path(path).read_text(encoding='utf-8'));expected=plan.pop('plan_sha256',None)
    if digest(plan)!=expected:raise PlanError('Plan checksum mismatch.')
    plan['plan_sha256']=expected
    if plan.get('version')!=1:raise PlanError('Unsupported plan version.')
    for name in plan['inserts']:
        if name not in TABLES:raise PlanError('Unapproved target table.')
    if set(plan['updates'])!={'selection_workspace_positions'}:raise PlanError('Only reviewed position updates are permitted.')
    if any(set(row['values'])-{'role_code','organization_context_json'} for row in plan['updates']['selection_workspace_positions']):raise PlanError('Unapproved update columns.')
    return plan


def connect_target(dsn,mode,command,approval,plan,allow_production=False,writes_paused=False):
    url=make_url(dsn)
    if url.get_backend_name()!='postgresql':raise PlanError('PostgreSQL target required.')
    if set(url.query)&{'host','port','dbname','database','user','password','service'}:raise PlanError('Connection-query overrides are not permitted.')
    if url.query.get('hostaddr') not in (None,'127.0.0.1'):raise PlanError('Only an explicit loopback tunnel address is permitted.')
    if mode=='local':
        if url.host not in ('127.0.0.1','localhost') or not (url.database or '').startswith('selection_production_test_'):
            raise PlanError('Local mode only permits a new selection_production_test_* database on loopback.')
    elif mode=='production':
        if (url.host,url.database)!=('rfone-dev.coj0wskcg634.us-east-1.rds.amazonaws.com','rfone'):raise PlanError('Unexpected production target.')
        if command!='check':
            if not allow_production or not writes_paused:raise PlanError('Production writes require explicit release authorization and a Selection-only write window.')
            if not approval or approval.get('approved') is not True or approval.get('plan_sha256')!=plan['plan_sha256'] or (approval.get('target_host'),approval.get('target_database'))!=(url.host,url.database):
                raise PlanError('Approval must match this plan and production target.')
    else:raise PlanError('Unknown execution mode.')
    connection={'options':'-c default_transaction_read_only='+('on' if command=='check' else 'off')+' -c lock_timeout=5000 -c statement_timeout=120000','connect_timeout':15}
    if mode=='local':connection['hostaddr']='127.0.0.1'
    else:connection['sslmode']='require'
    return create_engine(url,hide_parameters=True,connect_args=connection)


def prepare_schema(engine):
    # Explicit operation, never part of application boot or a preflight check.
    names={'selection_workspace_job_roles','selection_workspace_automation_items','selection_workspace_action_runs','selection_workspace_pdl_rules','selection_workspace_observation_templates'}
    with engine.begin() as c:
        while names:
            ready=[n for n in sorted(names) if not {f.column.table.name for f in Base.metadata.tables[n].foreign_keys}&(names-{n})]
            if not ready:raise PlanError('Schema dependency cycle.')
            for n in ready:Base.metadata.tables[n].create(c,checkfirst=True);names.remove(n)
        for table,column in [('primary_screening_criteria','research_id'),('primary_screening_criteria','criterion_group'),('primary_screening_criterion_snapshots','criterion_group'),('primary_screening_runs','evaluation_context')]:
            field=Base.metadata.tables[table].c[column]
            c.execute(text('ALTER TABLE "'+table+'" ADD COLUMN IF NOT EXISTS "'+column+'" '+str(field.type.compile(dialect=c.dialect))+' NULL'))
        c.execute(text('CREATE INDEX IF NOT EXISTS ix_primary_screening_criteria_research_id ON primary_screening_criteria(research_id)'))
        c.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_pdl_active_override ON selection_workspace_pdl_rules(role_code,overrides_rule_id) WHERE is_active AND overrides_rule_id IS NOT NULL'))
        c.execute(text('CREATE TABLE IF NOT EXISTS '+LEDGER+' (batch_id text PRIMARY KEY,plan_hash text NOT NULL,status varchar(16) NOT NULL,payload jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now())'))


def converted(table,row):
    result={}
    for key,value in row.items():
        if key not in table.c:raise PlanError('Unexpected target column: '+table.name+'.'+key)
        typ=table.c[key].type
        if value is not None:
            if isinstance(typ,Boolean):value=bool(value)
            elif isinstance(typ,JSON) and isinstance(value,str):value=json.loads(value)
            elif isinstance(typ,DateTime) and isinstance(value,str):
                value=datetime.fromisoformat(value.replace('Z','+00:00'))
                if typ.timezone and value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
                if not typ.timezone and value.tzinfo:value=value.astimezone(timezone.utc).replace(tzinfo=None)
            elif isinstance(typ,Date) and isinstance(value,str):value=date.fromisoformat(value)
        result[key]=value
    return result


def validate_objects(plan,mode,local_receipt=None):
    for obj in plan['objects']:
        uri=obj['uri'];parts=urlsplit(uri)
        if parts.scheme!='s3' or parts.netloc!='rfone-selection-documents-418674484214' or not parts.path.startswith('/selection/resumes/migrations/'):
            raise PlanError('New originals must use the reviewed private Selection prefix.')
        if mode=='local':
            item=(local_receipt or {}).get(uri)
            if not item:raise PlanError('Missing local original receipt.')
            with Path(item).open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
            size=Path(item).stat().st_size
        else:
            import boto3
            # GET only. No credentials or write operations are in the plan.
            response=boto3.client('s3').get_object(Bucket=parts.netloc,Key=parts.path.lstrip('/'))
            h=hashlib.sha256();size=0
            try:
                for chunk in iter(lambda:response['Body'].read(1048576),b''):h.update(chunk);size+=len(chunk)
            finally:response['Body'].close()
            actual=h.hexdigest()
        if size!=obj['bytes'] or actual!=obj['sha256']:raise PlanError('Original object checksum mismatch.')


def check(c,plan,metadata):
    for anchor in plan['anchors']:
        table=metadata.tables[anchor['table']];pk=list(table.primary_key.columns)[0]
        row=c.execute(select(table).where(pk==anchor['id'])).mappings().one_or_none()
        if row is None or digest({k:row[k] for k in anchor['before']})!=digest(anchor['before']):raise PlanError('Source changed: refresh and review the migration plan ('+anchor['table']+').')
    for spec in plan['baseline_counts']:
        table=metadata.tables[spec['table']];query=select(text('count(*)')).select_from(table)
        if 'restaurant_id' in spec:query=query.where(table.c.restaurant_id==spec['restaurant_id'])
        if c.scalar(query)!=spec['count']:raise PlanError('New Selection data detected; reconcile the latest source before importing.')
    hashes=[r['content_hash'] for r in plan['inserts']['raw_resumes'] if r.get('content_hash')]
    raw=metadata.tables['raw_resumes']
    if c.execute(select(raw.c.id).where(raw.c.restaurant_id==1,raw.c.content_hash.in_(hashes)).limit(1)).first():raise PlanError('A local CV is already on the target; reconcile duplicates before importing.')
    def phone(value):
        digits=re.sub(r'\D','',value or '')
        if len(digits)==11 and digits.startswith('1'):digits=digits[1:]
        return digits if len(digits)>=7 and len(set(digits))>1 else None
    def normalize(value):return ' '.join((value or '').split()).casefold()
    candidate=metadata.tables['candidates']
    current=list(c.execute(select(candidate.c.full_name,candidate.c.email,candidate.c.phone).where(candidate.c.restaurant_id==1)).mappings())
    for row in plan['inserts']['candidates']:
        if any((row.get('email') and normalize(row['email'])==normalize(old['email'])) or (row.get('full_name') and normalize(row['full_name'])==normalize(old['full_name'])) or (phone(row.get('phone')) and phone(row['phone'])==phone(old['phone'])) for old in current):
            raise PlanError('Candidate identity overlap detected; reconcile the latest source before importing.')
    return {'preflight':'passed','objects':len(plan['objects']),'source_drift':False}


def rebase_context(value,maps):
    result=copy.deepcopy(value)
    def mapped(table,v):return maps.get(table,{}).get(str(v),v)
    run=result.get('pdl_filter_run')
    if run:
        if run.get('incremental_version'):raise PlanError('Incremental cache requires an explicit cache migration adapter.')
        run['results']={str(mapped('selection_workspace_position_candidates',k)):v for k,v in run.get('results',{}).items()}
        run['errors']={str(mapped('selection_workspace_position_candidates',k)):v for k,v in run.get('errors',{}).items()}
        run['candidates']=[mapped('selection_workspace_position_candidates',v) for v in run.get('candidates',[])]
        for rule in run.get('rules',[]):
            rule['id']=mapped('selection_workspace_pdl_rules',rule['id'])
            if rule.get('overrides_rule_id') is not None:rule['overrides_rule_id']=mapped('selection_workspace_pdl_rules',rule['overrides_rule_id'])
        for row in run.get('results',{}).values():
            for detail in row.get('details',[]):detail['id']=mapped('selection_workspace_pdl_rules',detail['id'])
        run['signature']=hashlib.sha256(json.dumps(run.get('rules',[]),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return result


def rebase_row(table,row,maps):
    row=copy.deepcopy(row);refs={fk.parent.name:fk.column.table.name for fk in table.foreign_keys};refs.update(CUSTOM.get(table.name,{}))
    for key,parent in refs.items():
        if row.get(key) is not None:row[key]=maps.get(parent,{}).get(str(row[key]),row[key])
    if 'organization_context_json' in row:row['organization_context_json']=json.dumps(rebase_context(json.loads(row['organization_context_json']),maps),ensure_ascii=False)
    if table.name=='selection_workspace_action_runs':
        def walk(value):
            if isinstance(value,list):return [walk(v) for v in value]
            if isinstance(value,dict):return {k:maps.get(JSON_REFS.get(k,''),{}).get(str(v),v) if k in JSON_REFS and isinstance(v,int) else walk(v) for k,v in value.items()}
            return value
        for key in ('action_snapshot','procedure_snapshot','steps','attempts'):row[key]=walk(row[key])
    return row


def apply(engine,plan,mode,local_receipt=None):
    validate_objects(plan,mode,local_receipt)
    metadata=MetaData();metadata.reflect(engine)
    if LEDGER not in metadata.tables:raise PlanError('Explicit schema preparation required.')
    with engine.begin() as c:
        c.execute(text('SELECT pg_advisory_xact_lock(187042,1)'))
        previous=c.execute(text('SELECT * FROM '+LEDGER+' WHERE batch_id=:id FOR UPDATE'),{'id':plan['batch_id']}).mappings().first()
        if previous:
            if previous['plan_hash']!=plan['plan_sha256'] or previous['status']!='APPLIED':raise PlanError('Batch hash/status conflict; prepare a new reviewed batch.')
            return {'status':'ALREADY_APPLIED','new_rows':0}
        # Short, Selection-scoped DML locks prevent duplicate uploads racing the final check.
        for name in sorted(plan['inserts']):c.execute(text('LOCK TABLE "'+name+'" IN SHARE ROW EXCLUSIVE MODE'))
        for anchor in plan['anchors']:
            table=metadata.tables[anchor['table']];pk=list(table.primary_key.columns)[0]
            c.execute(select(pk).where(pk==anchor['id']).with_for_update()).first()
        check(c,plan,metadata)
        maps={};inserted=[];updates=[]
        for name,rows in plan['inserts'].items():
            table=metadata.tables[name];pk=list(table.primary_key.columns)[0]
            for original in rows:
                old_id=original[pk.name];row=rebase_row(table,original,maps)
                if pk.name=='id':row.pop('id')
                actual=dict(c.execute(insert(table).values(**converted(table,row)).returning(*table.c)).mappings().one())
                maps.setdefault(name,{})[str(old_id)]=actual[pk.name]
                inserted.append({'table':name,'pk':pk.name,'id':actual[pk.name],'after':canonical(actual)})
        for entry in plan['updates']['selection_workspace_positions']:
            table=metadata.tables['selection_workspace_positions'];before=dict(c.execute(select(table).where(table.c.id==entry['id'])).mappings().one())
            values=rebase_row(table,entry['values'],maps)
            actual=dict(c.execute(update(table).where(table.c.id==entry['id']).values(**converted(table,values)).returning(*table.c)).mappings().one())
            updates.append({'table':table.name,'id':entry['id'],'before':{k:canonical(before[k]) for k in values},'after':{k:canonical(actual[k]) for k in values}})
        payload={'inserted':inserted,'updates':updates,'id_maps':maps,'object_receipts':plan['objects'],
            'preexisting_role_codes':sorted({a['before']['role_code'] for a in plan['anchors'] if a['table']=='selection_workspace_positions'})}
        c.execute(text('INSERT INTO '+LEDGER+' (batch_id,plan_hash,status,payload) VALUES (:id,:hash,\'APPLIED\',CAST(:payload AS jsonb))'),{'id':plan['batch_id'],'hash':plan['plan_sha256'],'payload':json.dumps(payload,ensure_ascii=False)})
        return {'status':'APPLIED','new_rows':len(inserted),'updated_positions':len(updates),'id_maps':maps}


def rollback(engine,plan):
    metadata=MetaData();metadata.reflect(engine)
    with engine.begin() as c:
        c.execute(text('SELECT pg_advisory_xact_lock(187042,1)'))
        batch=c.execute(text('SELECT * FROM '+LEDGER+' WHERE batch_id=:id FOR UPDATE'),{'id':plan['batch_id']}).mappings().one()
        if batch['plan_hash']!=plan['plan_sha256']:raise PlanError('Rollback hash mismatch.')
        if batch['status']=='ROLLED_BACK':return {'status':'ALREADY_ROLLED_BACK','deleted_rows':0}
        payload=batch['payload'];batch_ids={}
        for entry in payload['inserted']:batch_ids.setdefault(entry['table'],set()).add(entry['id'])
        for name in sorted(batch_ids):c.execute(text('LOCK TABLE "'+name+'" IN SHARE ROW EXCLUSIVE MODE'))
        for entry in payload['inserted']:
            table=metadata.tables[entry['table']];row=c.execute(select(table).where(table.c[entry['pk']]==entry['id']).with_for_update()).mappings().one_or_none()
            if row is None or digest(dict(row))!=digest(entry['after']):raise PlanError('Imported row changed after cutover; selective recovery required.')
        for entry in payload['updates']:
            table=metadata.tables[entry['table']];row=c.execute(select(table).where(table.c.id==entry['id']).with_for_update()).mappings().one()
            if digest({k:row[k] for k in entry['after']})!=digest(entry['after']):raise PlanError('Position changed after cutover; preserve new writes before rollback.')
        # Guard every declared FK and the application's unconstrained legacy references.
        for table in metadata.tables.values():
            refs={fk.parent.name:fk.column.table.name for fk in table.foreign_keys};refs.update(CUSTOM.get(table.name,{}))
            for column,parent in refs.items():
                if parent not in batch_ids or column not in table.c:continue
                ids=batch_ids[parent]
                if parent=='selection_workspace_job_roles' and column in CUSTOM.get(table.name,{}):ids=ids-set(payload['preexisting_role_codes'])
                if not ids:continue
                query=select(table).where(table.c[column].in_(ids));pk=list(table.primary_key.columns)
                dependents=list(c.execute(query).mappings())
                if not dependents:continue
                if len(pk)!=1:raise PlanError('New dependent composite records require explicit recovery review.')
                for row in dependents:
                    if any(u['table']==table.name and u['id']==row[pk[0].name] and column in u['before'] for u in payload['updates']):continue
                    if row[pk[0].name] not in batch_ids.get(table.name,set()):raise PlanError('New dependent records exist; rollback refused without deleting them.')
        for entry in payload['updates']:
            table=metadata.tables[entry['table']];c.execute(update(table).where(table.c.id==entry['id']).values(**converted(table,entry['before'])))
        for entry in reversed(payload['inserted']):
            table=metadata.tables[entry['table']];c.execute(delete(table).where(table.c[entry['pk']]==entry['id']))
        c.execute(text('UPDATE '+LEDGER+' SET status=\'ROLLED_BACK\' WHERE batch_id=:id'),{'id':plan['batch_id']})
        return {'status':'ROLLED_BACK','deleted_rows':len(payload['inserted']),'objects_deleted':0}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('check','schema','apply','rollback'));p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--mode',choices=('local','production'),default='local');p.add_argument('--approval-file',type=Path);p.add_argument('--local-object-receipt',type=Path)
    p.add_argument('--allow-production-write',action='store_true');p.add_argument('--selection-writes-paused',action='store_true');args=p.parse_args()
    plan=load_plan(args.plan);approval=json.loads(args.approval_file.read_text()) if args.approval_file else None
    dsn=os.environ.get('RFONE_MIGRATION_DATABASE_URL')
    if not dsn:raise PlanError('Set RFONE_MIGRATION_DATABASE_URL securely; never put credentials in the plan.')
    engine=connect_target(dsn,args.mode,args.command,approval,plan,args.allow_production_write,args.selection_writes_paused)
    try:
        if args.command=='schema':prepare_schema(engine);result={'status':'SCHEMA_PREPARED'}
        elif args.command=='apply':result=apply(engine,plan,args.mode,json.loads(args.local_object_receipt.read_text()) if args.local_object_receipt else None)
        elif args.command=='rollback':result=rollback(engine,plan)
        else:
            validate_objects(plan,args.mode,json.loads(args.local_object_receipt.read_text()) if args.local_object_receipt else None)
            metadata=MetaData();metadata.reflect(engine)
            with engine.connect() as c:result=check(c,plan,metadata)
        print(json.dumps(result,ensure_ascii=False))
    finally:engine.dispose()


if __name__=='__main__':
    try:main()
    except PlanError as exc:print(str(exc),file=sys.stderr);raise SystemExit(2)
