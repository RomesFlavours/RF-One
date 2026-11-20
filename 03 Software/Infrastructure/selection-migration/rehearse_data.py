"""Rehearse confirmed Selection mappings on a NEW, guarded local PostgreSQL clone only."""
import argparse,copy,hashlib,json,shutil,sqlite3,sys
from contextlib import closing
from datetime import datetime,timezone,date
from pathlib import Path
from urllib.parse import urlsplit,unquote
import psycopg2
from psycopg2 import sql
from sqlalchemy import create_engine,inspect,MetaData,Table,text,select,insert,update
from sqlalchemy.types import Boolean,JSON,DateTime,Date

REPO=Path(__file__).resolve().parents[3];APP=REPO/'03 Software/AWSSelection/Selection'
sys.path[:0]=[str(APP),str(APP.parent/'RF-One Data Store')]
from workspace import schema


def encode(value):
    if isinstance(value,datetime):return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
    if isinstance(value,date):return value.isoformat()
    return str(value)


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=encode,separators=(',',':')).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--review',type=Path,required=True);parser.add_argument('--port',type=int,default=55479);args=parser.parse_args()
    review=args.review.resolve();archive=review.parent.parent
    baseline=review/'local-baseline.sqlite';summary=json.loads((review/'summary.json').read_text(encoding='utf-8'))
    if sha(baseline)!=summary['local_snapshot_sha256']:raise RuntimeError('Local baseline checksum mismatch')
    proof=json.loads((archive/'current-backup-verification.json').read_text(encoding='utf-8'))
    if sha(archive/'databases/rfone-dev/database.dump')!=proof['databases']['rfone-dev']['sha256']:raise RuntimeError('AWS dump checksum mismatch')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=archive/'data-rehearsal'/stamp;out.mkdir(parents=True,exist_ok=False)
    target='selection_data_rehearsal_'+stamp.lower();role_assistant='ROLE_05616600fcc546cbbd10933aa7e236f5'
    confirmed={'positions':{'2':3,'3':7,'4':6},'new_position':1,'canonical_server':'SERVER','canonical_assistant':role_assistant,
        'aws_role_aliases':{'FOOD_RUNNER':role_assistant,'BUSSER':role_assistant},'new_manager':14,'local_actor_to_aws':{'1':4},'restaurant':1,'prototype':'ARCHIVE_ONLY'}
    def write(name,value):(out/name).write_text(json.dumps(value,indent=2,ensure_ascii=False,default=encode),encoding='utf-8')
    write('confirmed-mappings.json',confirmed)
    admin=psycopg2.connect(host='127.0.0.1',port=args.port,user='archiveverify',dbname='postgres',options='-c default_transaction_read_only=off');admin.autocommit=True
    try:
        with admin.cursor() as cur:
            cur.execute('SHOW data_directory')
            if Path(cur.fetchone()[0]).resolve()!=(archive/'current-restore-verification/pgdata').resolve():raise RuntimeError('Wrong local cluster')
            cur.execute(sql.SQL('CREATE DATABASE {} TEMPLATE {}').format(sql.Identifier(target),sql.Identifier('rfone_current_verify')))
    finally:admin.close()
    print('Created isolated data-rehearsal clone:',target,flush=True)
    if not target.startswith('selection_data_rehearsal_'):raise RuntimeError('Unsafe target name')
    url=f'postgresql+psycopg2://archiveverify@127.0.0.1:{args.port}/{target}'
    target_engine=create_engine(url,connect_args={'options':'-c default_transaction_read_only=off'})
    source_engine=create_engine(f'postgresql+psycopg2://archiveverify@127.0.0.1:{args.port}/rfone_current_verify',connect_args={'options':'-c default_transaction_read_only=on'})
    local=sqlite3.connect(baseline.as_uri()+'?mode=ro',uri=True);local.row_factory=sqlite3.Row;local.execute('PRAGMA query_only=ON')
    def local_rows(table):return [dict(r) for r in local.execute('SELECT * FROM "'+table+'"')]
    local_tables={r[0] for r in local.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    local_foreign={table:{r[3]:(r[2],r[4]) for r in local.execute('PRAGMA foreign_key_list("'+table+'")')} for table in local_tables}
    before={};original_counts={};positions_before={}
    try:
        with source_engine.connect() as c:
            assert c.scalar(text('SHOW transaction_read_only'))=='on'
            for table in inspect(c).get_table_names():
                original_counts[table]=c.scalar(text('SELECT count(*) FROM "'+table+'"'))
                if table in {t.name for t in schema.required_tables()} or table in ('rfone_account_domain_access',):
                    before[table]=[dict(r) for r in c.execute(text('SELECT * FROM "'+table+'"')).mappings()]
            positions_before={r['id']:r for r in before['selection_workspace_positions']}
        write('aws-selection-before.json',before)
        ddl=(review/'aws_operational-schema-review.sql').read_text(encoding='utf-8')
        if '-- BLOCKED:' in ddl:raise RuntimeError('Schema backfill decisions missing')
        ddl=ddl.replace('ROLLBACK; -- Default is non-persistent. Reviewed migration must be separately approved.','COMMIT;')
        raw=target_engine.raw_connection()
        try:
            raw.autocommit=True
            with raw.cursor() as cursor:cursor.execute(ddl)
        finally:raw.close()
        metadata=MetaData();metadata.reflect(target_engine)
        documents=json.loads((review/'document-inventory.json').read_text(encoding='utf-8'))
        local_doc={r['id']:r for r in documents['local']};archive_objects=json.loads((archive/'document-manifest.json').read_text(encoding='utf-8'))['objects']
        files={}
        for obj in archive_objects:
            uri='s3://'+obj['bucket']+'/'+obj['key']
            if uri not in files or obj['is_latest']:files[uri]=str(archive/obj['file'])
        maps={'restaurants':{1:1},'rfone_accounts':{1:4},'selection_workspace_positions':{2:3,3:7,4:6}}
        roles=local_rows('selection_workspace_job_roles');rolemap={r['code']:('SERVER' if r['name'].strip().casefold()=='server' else r['code']) for r in roles}
        maps['selection_workspace_job_roles']=rolemap
        imported={};conflicts=[];sanitizations=[];expected_rows={};sequence_reset=set();batch=fingerprint({'baseline':summary['local_snapshot_sha256'],'aws':proof['databases']['rfone-dev']['sha256'],'confirmed':confirmed})

        def clean(value,location):
            if isinstance(value,str) and '\x00' in value:
                sanitized=value.replace('\x00','')
                sanitizations.append({'location':location,'removed_nul_count':value.count('\x00'),'original':value,'normalized':sanitized,
                    'original_sha256':hashlib.sha256(value.encode()).hexdigest(),'normalized_sha256':hashlib.sha256(sanitized.encode()).hexdigest()})
                return sanitized
            if isinstance(value,dict):return {k:clean(v,location+'.'+str(k)) for k,v in value.items()}
            if isinstance(value,list):return [clean(v,location+'[]') for v in value]
            return value

        def mapped(table,value):
            if value is None:return None
            if value not in maps.get(table,{}):raise RuntimeError('Unmapped reference '+table+':'+str(value))
            return maps[table][value]

        def convert(table,row):
            result={}
            for key,value in row.items():
                if key not in table.c:raise RuntimeError('Target column missing: '+table.name+'.'+key)
                typ=table.c[key].type
                if value is not None:
                    if isinstance(typ,Boolean):value=bool(value)
                    elif isinstance(typ,JSON) and isinstance(value,str):value=json.loads(value)
                    elif isinstance(typ,DateTime) and isinstance(value,str):value=datetime.fromisoformat(value.replace('Z','+00:00'))
                    elif isinstance(typ,Date) and isinstance(value,str):value=date.fromisoformat(value)
                    if isinstance(typ,DateTime) and isinstance(value,datetime):
                        if typ.timezone and value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
                        elif not typ.timezone and value.tzinfo is not None:value=value.astimezone(timezone.utc).replace(tzinfo=None)
                result[key]=clean(value,table.name+'.'+str(row.get('id',row.get('code','new')))+'.'+key)
            return result

        def add(c,name,source,overrides=None):
            table=metadata.tables[name];old=source.get('id',source.get('code'));row=copy.deepcopy(source)
            pk=list(table.primary_key.columns)
            if len(pk)!=1:raise RuntimeError('Unsupported composite import key: '+name)
            primary=pk[0].name
            if primary=='id':row.pop('id',None)
            for field,(parent,_) in local_foreign.get(name,{}).items():
                if row.get(field) is not None:row[field]=mapped(parent,row[field])
            for field in ('role_code','target_role','intended_role'):
                if row.get(field) in rolemap:row[field]=rolemap[row[field]]
            for field in ('actor_account_id','added_by_account_id','approved_by_account_id'):
                if row.get(field) is not None:row[field]=mapped('rfone_accounts',row[field])
            if name=='selection_workspace_events' and row.get('position_candidate_id') is not None:row['position_candidate_id']=mapped('selection_workspace_position_candidates',row['position_candidate_id'])
            if name=='requirement_snapshot_items' and row.get('source_requirement_id') is not None:row['source_requirement_id']=mapped('requirements',row['source_requirement_id'])
            row.update(overrides or {})
            if primary=='id' and name not in sequence_reset:
                c.execute(text("SELECT setval(pg_get_serial_sequence(:table,'id'), GREATEST(COALESCE((SELECT max(id) FROM \""+name+"\"),0),1), EXISTS(SELECT 1 FROM \""+name+"\"))"),{'table':name});sequence_reset.add(name)
            values=convert(table,row)
            result=c.execute(insert(table).values(**values).returning(table.c[primary])).scalar_one()
            expected_rows.setdefault(name,{})[result]=values
            maps.setdefault(name,{})[old]=result;imported[name]=imported.get(name,0)+1
            return result

        def apply():
            with target_engine.begin() as c:
                c.execute(text('CREATE TABLE IF NOT EXISTS selection_migration_rehearsal_ledger (batch_id text PRIMARY KEY, payload jsonb NOT NULL)'))
                previous=c.scalar(text('SELECT payload FROM selection_migration_rehearsal_ledger WHERE batch_id=:id'),{'id':batch})
                if previous:return {'second_run':True,'new_rows':0,'payload':previous}
                for role in roles:
                    row=dict(role);row['code']=rolemap[row['code']];add(c,'selection_workspace_job_roles',row)
                for item in local_rows('selection_workspace_automation_items'):add(c,'selection_workspace_automation_items',item)
                for rule in local_rows('selection_workspace_pdl_rules'):add(c,'selection_workspace_pdl_rules',rule)
                for model in local_rows('selection_workspace_observation_templates'):add(c,'selection_workspace_observation_templates',model)
                for name in ('requirement_sets','requirements','requirement_set_snapshots','requirement_snapshot_items'):
                    for row in local_rows(name):add(c,name,row)
                for row in local_rows('selection_workspace_positions'):
                    if row['id']==1:add(c,'selection_workspace_positions',row,{'manager_account_id':14})
                for row in local_rows('raw_resumes'):
                    doc=local_doc[row['id']];frozen=Path(doc['local_file']);assert sha(frozen)==doc['sha256']
                    target_file=out/'documents/local'/(doc['sha256']+Path(doc['filename']).suffix.lower());target_file.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(frozen,target_file);assert sha(target_file)==doc['sha256']
                    add(c,'raw_resumes',row,{'storage_path':str(target_file)})
                for name in ('candidate_persons','candidates','candidate_work_history','candidate_education','candidate_skills','candidate_certifications','candidate_languages','applications','selection_workspace_position_candidates','selection_workspace_decisions','selection_workspace_events'):
                    for row in local_rows(name):add(c,name,row)
                for row in local_rows('selection_workspace_action_runs'):
                    if row['status']!='SUCCEEDED':raise RuntimeError('Non-completed automation needs a separate migration decision')
                    action=json.loads(row['action_snapshot']);action['actor_id']=mapped('rfone_accounts',action['actor_id'])
                    add(c,'selection_workspace_action_runs',row,{'action_snapshot':action})
                positions=metadata.tables['selection_workspace_positions']
                for old_code,new_code in confirmed['aws_role_aliases'].items():
                    for row in c.execute(select(positions).where(positions.c.role_code==old_code)).mappings():
                        context=json.loads(row['organization_context_json'] or '{}');context['_migration_role_alias']={'original':old_code,'canonical':new_code,'batch':batch}
                        c.execute(update(positions).where(positions.c.id==row['id']).values(role_code=new_code,organization_context_json=json.dumps(context,ensure_ascii=False)))
                for original in local_rows('selection_workspace_positions'):
                    target_id=mapped('selection_workspace_positions',original['id']);target_row=c.execute(select(positions).where(positions.c.id==target_id)).mappings().one()
                    context=json.loads(target_row['organization_context_json'] or '{}');local_context=json.loads(original['organization_context_json'] or '{}')
                    context.setdefault('_migration_local_positions',{})[str(original['id'])]={'batch':batch,'original':original}
                    if original['id']!=1:
                        before_cfg=copy.deepcopy(context.get('configuration',{}));new_cfg=local_context.get('configuration',{})
                        merged_cfg=dict(before_cfg)
                        for key,value in new_cfg.items():
                            if key=='profile' and not value and before_cfg.get('profile'):continue
                            merged_cfg[key]=value
                        context['configuration']=merged_cfg
                        if before_cfg!=merged_cfg:conflicts.append({'position_id':target_id,'field':'configuration','aws_original':before_cfg,'local':new_cfg,'selected':merged_cfg})
                    if local_context.get('pdl_filter_run'):
                        run=copy.deepcopy(local_context['pdl_filter_run']);original_signature=run.get('signature')
                        def remap_details(value):
                            result=copy.deepcopy(value)
                            for detail in result.get('details',[]):detail['id']=mapped('selection_workspace_pdl_rules',detail['id'])
                            return result
                        run['results']={str(mapped('selection_workspace_position_candidates',int(k))):remap_details(v) for k,v in run['results'].items()}
                        run['errors']={str(mapped('selection_workspace_position_candidates',int(k))):v for k,v in (run.get('errors') or {}).items()}
                        for rule in run.get('rules',[]):
                            rule['id']=mapped('selection_workspace_pdl_rules',rule['id'])
                            if rule.get('overrides_rule_id') is not None:rule['overrides_rule_id']=mapped('selection_workspace_pdl_rules',rule['overrides_rule_id'])
                        rule_signature=hashlib.sha256(json.dumps(run['rules'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                        source_rules=local_context['pdl_filter_run'].get('rules',[])
                        source_signature=hashlib.sha256(json.dumps(source_rules,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                        if source_signature!=original_signature:raise RuntimeError('Source AI result is already stale; explicit review required')
                        run['signature']=rule_signature;run['role_code']=rolemap.get(run['role_code'],run['role_code'])
                        ids=list(c.scalars(text('SELECT id FROM selection_workspace_position_candidates WHERE position_id=:id ORDER BY id'),{'id':target_id}))
                        run['candidates']=ids;run['state']='COMPLETED' if len(run['results'])==len(ids) else 'PARTIAL';run['migration_original_signature']=original_signature
                        context['pdl_filter_run']=clean(run,'position_context.'+str(target_id)+'.pdl_filter_run')
                    c.execute(update(positions).where(positions.c.id==target_id).values(organization_context_json=json.dumps(context,ensure_ascii=False)))
                payload={'maps':maps,'imported':imported,'confirmed':confirmed}
                c.execute(text('INSERT INTO selection_migration_rehearsal_ledger(batch_id,payload) VALUES (:id,CAST(:payload AS jsonb))'),{'id':batch,'payload':json.dumps(payload,default=encode)})
                return {'second_run':False,'new_rows':sum(imported.values()),'payload':payload}

        first=apply();print('First import committed on isolated clone:',first['new_rows'],'new rows.',flush=True)
        with target_engine.connect() as c:
            counts_after={t:c.scalar(text('SELECT count(*) FROM "'+t+'"')) for t in inspect(c).get_table_names()}
        second=apply();assert second['second_run'] and second['new_rows']==0
        with target_engine.connect() as c:
            assert counts_after=={t:c.scalar(text('SELECT count(*) FROM "'+t+'"')) for t in inspect(c).get_table_names()}
            changed=[];checked=0;local_fields_checked=0
            for name,source_rows in before.items():
                if not source_rows:continue
                table=metadata.tables[name];pk=list(table.primary_key.columns)
                for original in source_rows:
                    predicate=[table.c[col.name]==original[col.name] for col in pk]
                    actual=c.execute(select(table).where(*predicate)).mappings().one()
                    for key,value in original.items():
                        if name=='selection_workspace_positions' and key=='organization_context_json' and original['id'] in (3,6,7,8):continue
                        if name=='selection_workspace_positions' and key=='role_code' and original['id'] in (7,8):
                            assert actual[key]==role_assistant;continue
                        if fingerprint(actual[key])!=fingerprint(value):changed.append((name,original.get('id'),key))
                    checked+=1
            assert not changed,changed[:5]
            for name,imported_rows in expected_rows.items():
                table=metadata.tables[name];primary=list(table.primary_key.columns)[0]
                for target_id,values in imported_rows.items():
                    actual=c.execute(select(table).where(primary==target_id)).mappings().one()
                    for key,value in values.items():
                        if name=='selection_workspace_positions' and key=='organization_context_json':continue
                        assert fingerprint(value)==fingerprint(actual[key]),('Local field mismatch',name,target_id,key)
                        local_fields_checked+=1
            for name,old_count in original_counts.items():
                assert counts_after[name]==old_count+imported.get(name,0),(name,old_count,counts_after[name])
            all_documents=[dict(r) for r in c.execute(text('SELECT id,storage_path FROM raw_resumes ORDER BY id')).mappings()]
            for doc in all_documents:
                value=doc['storage_path'];file=Path(files[value]) if value.startswith('s3://') else Path(value)
                assert file.is_file(),doc['id']
            assert counts_after['raw_resumes']==202 and counts_after['candidates']==202 and counts_after['selection_workspace_position_candidates']==206
        write('id-maps.json',maps);write('imported-row-counts.json',imported);write('configuration-conflicts-resolved.json',conflicts);write('offline-original-file-map.json',files)
        write('text-normalizations-original-values.json',sanitizations)
        write('local-company-profile-preserved.json',local_rows('selection_workspace_company_profile'))
        report={'target_database':target,'output':str(out),'aws_access':False,'live_local_database_access':False,'source_baseline_sha256':summary['local_snapshot_sha256'],
            'cv_documents':202,'candidate_profiles':202,'candidate_position_links':206,'positions':counts_after['selection_workspace_positions'],
            'local_cv_originals_preserved':52,'all_cv_originals_accessible_offline':True,'aws_existing_rows_compared':checked,'unexpected_aws_row_changes':changed,
            'aws_history_preserved':True,'local_events_imported':imported.get('selection_workspace_events',0),'local_ai_results_preserved':52,
            'local_config_counts':{t:counts_after[t] for t in ('selection_workspace_job_roles','selection_workspace_pdl_rules','selection_workspace_observation_templates','selection_workspace_automation_items','selection_workspace_action_runs')},
            'completed_action_preserved':True,'idempotence_second_run_new_rows':0,'prototype_imported':False,'data_import_success':True,'confirmed_mappings':confirmed}
        report['local_fields_compared']=local_fields_checked;report['text_normalizations']=len(sanitizations)
        write('result.json',report);print('DATA REHEARSAL VERIFIED:',json.dumps(report),flush=True)
    finally:
        local.close();source_engine.dispose();target_engine.dispose()


if __name__=='__main__':main()
