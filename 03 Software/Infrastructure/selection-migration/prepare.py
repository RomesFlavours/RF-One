"""Build a migration review package from LOCAL restored copies. Never connect to AWS or apply writes."""
import argparse,csv,hashlib,json,sqlite3,sys,re,shutil
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit,unquote
from sqlalchemy import create_engine,inspect,text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable,CreateIndex

REPO=Path(__file__).resolve().parents[3]
APP=REPO/'03 Software/AWSSelection/Selection'
sys.path.insert(0,str(APP));sys.path.insert(0,str(APP.parent/'RF-One Data Store'))
from workspace import schema
from rfone_data_store.models import Base


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def normalize(value):return ' '.join(str(value or '').split()).casefold()


def logical_type(value):
    value=str(value).upper()
    if value in ('JSON','JSONB'):return 'JSON'
    if value.startswith(('TIMESTAMP','DATETIME')):return 'DATETIME'
    if value.startswith('CHARACTER VARYING'):return value.replace('CHARACTER VARYING','VARCHAR')
    if value=='DOUBLE PRECISION':return 'FLOAT'
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--local-database',type=Path,required=True)
    parser.add_argument('--port',type=int,default=55479)
    args=parser.parse_args();archive=args.archive.resolve()
    verified=json.loads((archive/'current-backup-verification.json').read_text(encoding='utf-8'))
    if not verified['complete_current_database_backup']:raise RuntimeError('Verified AWS copies required.')
    for name,entry in verified['databases'].items():
        if digest(archive/'databases'/name/'database.dump')!=entry['sha256']:raise RuntimeError('Dump checksum changed: '+name)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=archive/'migration-review'/stamp;out.mkdir(parents=True,exist_ok=False)
    def write(name,value):(out/name).write_text(json.dumps(value,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    def csvfile(name,records,fields):
        with (out/name).open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(records)
    snapshot=out/'local-baseline.sqlite'
    with closing(sqlite3.connect(args.local_database.resolve().as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(snapshot)) as dest:
        src.execute('PRAGMA query_only=ON');src.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Local snapshot integrity failure')
    engines={'local':create_engine('sqlite:///'+snapshot.as_posix())}
    for name,db in [('aws_operational','rfone_current_verify'),('aws_test','selection_test_verify')]:
        engines[name]=create_engine(f'postgresql+psycopg2://archiveverify@127.0.0.1:{args.port}/{db}',connect_args={'options':'-c default_transaction_read_only=on -c statement_timeout=60000'})
    connections={k:e.connect() for k,e in engines.items()}
    try:
        for name,c in connections.items():
            if name!='local' and c.scalar(text('SHOW transaction_read_only'))!='on':raise RuntimeError('Source connection is not read only')
        def rows(source,table,columns='*'):
            c=connections[source];quote=c.dialect.identifier_preparer.quote
            return [dict(r) for r in c.execute(text('SELECT '+columns+' FROM '+quote(table))).mappings()]
        schemas={};counts={};required={t.name for t in schema.required_tables()}
        for name,c in connections.items():
            inspector=inspect(c);tables=inspector.get_table_names();schemas[name]={};counts[name]={}
            all_columns=inspector.get_multi_columns()
            for table in tables:
                columns=all_columns[(None,table)]
                schemas[name][table]={'columns':[{k:(str(v) if k=='type' else v) for k,v in col.items() if k in ('name','type','nullable','default','autoincrement','primary_key','identity','computed')} for col in columns],
                    'primary_key':inspector.get_pk_constraint(table),'foreign_keys':inspector.get_foreign_keys(table),
                    'unique':inspector.get_unique_constraints(table),'indexes':inspector.get_indexes(table)}
                if table in required or table.startswith('selproto_') or table in ('rfone_account_domain_access','selection_workspace_job_roles'):
                    counts[name][table]=c.scalar(text('SELECT count(*) FROM '+c.dialect.identifier_preparer.quote(table)))
        write('schemas.json',schemas);write('row-counts.json',counts)
        differences={};sql_candidates={};column_review=[]
        for source in ('aws_operational','aws_test'):
            missing=sorted(t for t in required if t in schemas['local'] and t not in schemas[source]);missing_cols=[];types=[];nullable=[]
            for table in sorted(required & schemas['local'].keys() & schemas[source].keys()):
                left={c['name']:c for c in schemas['local'][table]['columns']};right={c['name']:c for c in schemas[source][table]['columns']}
                for col,definition in left.items():
                    if col not in right:missing_cols.append({'table':table,'column':col,'local':definition})
                    else:
                        if logical_type(definition['type'])!=logical_type(right[col]['type']):types.append({'table':table,'column':col,'local':definition['type'],'aws':right[col]['type']})
                        if definition['nullable']!=right[col]['nullable']:nullable.append({'table':table,'column':col,'local_nullable':definition['nullable'],'aws_nullable':right[col]['nullable']})
            differences[source]={'missing_local_tables':missing,'missing_local_columns':missing_cols,'logical_type_differences':types,'nullability_differences':nullable,
                'aws_only_tables_preserved':sorted(set(schemas[source])-set(schemas['local']))}
            statements=['-- REVIEW ONLY. No connection or execution is performed by this file.', '-- Derived from local ORM models; retain the AWS Alembic revision. Do not downgrade.', 'BEGIN;']
            pending=set(missing)
            while pending:
                ready=[t for t in sorted(pending) if not {fk.column.table.name for fk in Base.metadata.tables[t].foreign_keys} & (pending-{t})]
                if not ready:raise RuntimeError('Unresolved schema dependency cycle')
                for table in ready:
                    obj=Base.metadata.tables[table];statements.append(str(CreateTable(obj,if_not_exists=True).compile(dialect=postgresql.dialect()))+';')
                    statements.extend(str(CreateIndex(index,if_not_exists=True).compile(dialect=postgresql.dialect()))+';' for index in sorted(obj.indexes,key=lambda i:i.name or ''))
                    pending.remove(table)
            for entry in missing_cols:
                table=entry['table'];col=Base.metadata.tables[table].columns[entry['column']];q=postgresql.dialect().identifier_preparer.quote
                if col.nullable:
                    statements.append('ALTER TABLE '+q(table)+' ADD COLUMN IF NOT EXISTS '+q(col.name)+' '+str(col.type.compile(dialect=postgresql.dialect()))+' NULL;')
                    for index in sorted(col.table.indexes,key=lambda i:i.name or ''):
                        if col.name in [c.name for c in index.columns]:
                            statements.append(str(CreateIndex(index,if_not_exists=True).compile(dialect=postgresql.dialect()))+';')
                else:statements.append('-- BLOCKED: '+table+'.'+col.name+' requires an explicit backfill/default and validation before NOT NULL.')
                column_review.append({'source':source,'table':table,'column':col.name,'type':str(col.type),'nullable':col.nullable,'decision':'REVIEW','approved_default':''})
            if 'selection_workspace_pdl_rules' in missing:
                statements.append('CREATE UNIQUE INDEX IF NOT EXISTS uq_pdl_active_override ON selection_workspace_pdl_rules (role_code, overrides_rule_id) WHERE is_active AND overrides_rule_id IS NOT NULL;')
            statements.append('ROLLBACK; -- Default is non-persistent. Reviewed migration must be separately approved.')
            (out/(source+'-schema-review.sql')).write_text('\n\n'.join(statements)+'\n',encoding='utf-8')
        write('schema-differences.json',differences);csvfile('column-decisions.csv',column_review,['source','table','column','type','nullable','decision','approved_default'])
        roles=rows('local','selection_workspace_job_roles');roles_by_name={normalize(r['name']):r['code'] for r in roles}
        positions={name:rows(name,'selproto_positions' if name=='aws_test' else 'selection_workspace_positions') for name in connections}
        position_review=[]
        role_names={'SERVER':'Server','FOOD_RUNNER':'Food Runner','BUSSER':'Busser','LINE_COOK':'Line Cook','PREP_COOK':'Prep Cook','HOST':'Host'}
        for source in ('aws_operational','aws_test'):
            for position in positions[source]:
                matches=[p for p in positions['local'] if normalize(p['location_label'])==normalize(position['location_label']) and roles_by_name.get(normalize(role_names.get(position['role_code'],position['role_code'])))==p['role_code']]
                position_review.append({'source':source,'source_position_id':position['id'],'source_title':position['title'],'source_role':position['role_code'],'source_site':position['location_label'],'source_status':position['status'],
                    'local_position_suggestions':';'.join(str(p['id']) for p in matches),'source_manager_id':position['manager_account_id'],
                    'decision':'KEEP_HISTORY' if source=='aws_operational' and position['status']=='CLOSED' else 'EXCLUDE_TEST_PENDING_REVIEW' if source=='aws_test' else 'REVIEW',
                    'approved_target_position':'','notes':'Role/site matches are suggestions only; distinct recruitment campaigns must not be merged automatically.'})
        csvfile('position-decisions.csv',position_review,list(position_review[0]))
        local_position_review=[]
        for position in positions['local']:
            label=next(r['name'] for r in roles if r['code']==position['role_code'])
            suggestions=[p for p in positions['aws_operational'] if normalize(p['location_label'])==normalize(position['location_label']) and normalize(role_names.get(p['role_code'],p['role_code']))==normalize(label)]
            local_position_review.append({'local_position_id':position['id'],'local_title':position['title'],'local_role':label,'site':position['location_label'],
                'suggested_aws_position_ids':';'.join(str(p['id']) for p in suggestions),'decision':'REVIEW_CAMPAIGN_MATCH' if suggestions else 'REVIEW_NEW_POSITION',
                'approved_target_position':'','approved_manager_account_id':'','notes':'Food Runner / Busser and Server Assistant are not automatically equivalent.'})
        csvfile('local-position-decisions.csv',local_position_review,list(local_position_review[0]))
        role_decisions=[]
        for role in roles:
            matches=[code for code,label in role_names.items() if normalize(label)==normalize(role['name']) and any(p['role_code']==code for p in positions['aws_operational'])]
            role_decisions.append({'local_role_code':role['code'],'local_role_name':role['name'],'suggested_existing_aws_code':';'.join(matches),
                'decision':'REVIEW_CODE_ALIAS' if matches else 'REVIEW_NEW_ROLE','approved_target_code':'','approved_name':''})
        csvfile('role-decisions.csv',role_decisions,list(role_decisions[0]))
        legacy_roles=[]
        for code in sorted({p['role_code'] for p in positions['aws_operational']}):
            label=role_names.get(code,code)
            match=next((r['code'] for r in roles if normalize(r['name'])==normalize(label)),'')
            legacy_roles.append({'aws_legacy_code':code,'suggested_catalog_name':label,'aws_position_ids':';'.join(str(p['id']) for p in positions['aws_operational'] if p['role_code']==code),
                'local_role_match':match,'policy':'PRESERVE_LEGACY_CODE','note':'Do not merge professional figures solely by similar names.'})
        csvfile('legacy-role-catalog.csv',legacy_roles,list(legacy_roles[0]))
        write('positions.json',positions);write('local-roles.json',roles)
        objects=json.loads((archive/'document-manifest.json').read_text(encoding='utf-8'))['objects'];by_uri={}
        for item in objects:
            uri='s3://'+item['bucket']+'/'+item['key']
            if uri not in by_uri or item['is_latest']:by_uri[uri]=item
        documents={};file_problems=[]
        for name in connections:
            documents[name]=[]
            for record in rows(name,'raw_resumes'):
                path=record.get('storage_path') or '';file=None
                if path.startswith('s3://'):
                    parts=urlsplit(path);item=by_uri.get('s3://'+parts.netloc+'/'+unquote(parts.path.lstrip('/')))
                    if item:file=archive/item['file']
                else:
                    candidates=[Path(path),REPO/path,APP/path]
                    file=next((p for p in candidates if p.is_file()),None)
                sha=digest(file) if file and file.is_file() else None
                if not sha:file_problems.append({'source':name,'raw_resume_id':record['id'],'path':path})
                if name=='local' and sha:
                    original=file;frozen=out/'local-originals'/(sha+Path(record['original_filename'] or file.name).suffix.lower());frozen.parent.mkdir(exist_ok=True)
                    if not frozen.exists():shutil.copyfile(original,frozen)
                    if digest(frozen)!=sha:raise RuntimeError('Local original changed during snapshot: '+str(record['id']))
                    file=frozen
                documents[name].append({'id':record['id'],'filename':record['original_filename'],'sha256':sha,'content_hash':record['content_hash'],
                    'text_sha256':hashlib.sha256((record.get('raw_text') or '').encode()).hexdigest(),'storage_path':path,'local_file':str(file) if file else None})
        write('document-inventory.json',documents);write('missing-documents.json',file_problems)
        exact=[];text_only=[]
        for doc in documents['local']:
            found=[r for r in documents['aws_operational'] if r['sha256'] and r['sha256']==doc['sha256']]
            text_matches=[r for r in documents['aws_operational'] if r['text_sha256']==doc['text_sha256']] if not found else []
            decision='REUSE_DOCUMENT' if len(found)==1 else 'REVIEW_DUPLICATE' if found else 'REVIEW_TEXT_MATCH' if text_matches else 'IMPORT_NEW_DOCUMENT'
            exact.append({'local_raw_resume_id':doc['id'],'filename':doc['filename'],'sha256':doc['sha256'],
                'aws_raw_resume_ids':';'.join(str(r['id']) for r in found),'same_text_aws_ids':';'.join(str(r['id']) for r in text_matches),'proposed_action':decision,'approved_action':'','approved_target_id':''})
        csvfile('document-decisions.csv',exact,list(exact[0]) if exact else ['local_raw_resume_id'])
        candidates={name:rows(name,'candidates','id,raw_resume_id,full_name,email,phone,restaurant_id,target_role') for name in connections}
        write('candidates.json',candidates)
        candidate_review=[]
        def phone(value):
            value=re.sub(r'\D','',value or '')
            if len(value)==11 and value.startswith('1'):value=value[1:]
            return value if len(value)>=7 and len(set(value))>1 else None
        for cand in candidates['local']:
            doc=next(r for r in exact if r['local_raw_resume_id']==cand['raw_resume_id'])
            exact_ids={int(v) for v in doc['aws_raw_resume_ids'].split(';') if v}
            matches=[r for r in candidates['aws_operational'] if r['raw_resume_id'] in exact_ids]
            email_matches=[r for r in candidates['aws_operational'] if cand.get('email') and normalize(cand['email'])==normalize(r.get('email'))]
            phone_matches=[r for r in candidates['aws_operational'] if phone(cand.get('phone')) and phone(cand['phone'])==phone(r.get('phone'))]
            name_matches=[r for r in candidates['aws_operational'] if cand.get('full_name') and normalize(cand['full_name'])==normalize(r.get('full_name'))]
            candidate_review.append({'local_candidate_id':cand['id'],'local_name':cand['full_name'],'local_raw_resume_id':cand['raw_resume_id'],
                'same_document_candidate_ids':';'.join(str(r['id']) for r in matches),'same_email_candidate_ids':';'.join(str(r['id']) for r in email_matches),
                'same_phone_candidate_ids':';'.join(str(r['id']) for r in phone_matches),'same_name_candidate_ids':';'.join(str(r['id']) for r in name_matches),
                'decision':'REVIEW_PROFILE_MERGE' if matches else 'REVIEW_IDENTITY' if email_matches or phone_matches or name_matches else 'IMPORT_NEW_CANDIDATE','approved_action':'','approved_target_id':''})
        csvfile('candidate-decisions.csv',candidate_review,list(candidate_review[0]) if candidate_review else ['local_candidate_id'])
        config_tables=['selection_workspace_job_roles','selection_workspace_pdl_rules','selection_workspace_observation_templates','selection_workspace_automation_items']
        configs={t:rows('local',t) for t in config_tables if t in schemas['local']};write('local-configurations.json',configs)
        accounts={name:rows(name,'rfone_accounts','id,username,status') for name in connections};write('account-identifiers.json',accounts)
        restaurants={name:rows(name,'restaurants','id,name') for name in connections};write('restaurant-identifiers.json',restaurants)
        position_organizations={}
        for source in connections:
            prefix='selproto_' if source=='aws_test' else 'selection_workspace_'
            result=connections[source].execute(text('SELECT p.id,r.restaurant_id FROM '+prefix+'positions p JOIN requirement_sets r ON r.id=p.requirement_set_id'))
            position_organizations[source]={str(r[0]):r[1] for r in result}
        write('position-organization-evidence.json',position_organizations)
        organization_by_position=[]
        for p in positions['local']:
            related=[a for a in positions['aws_operational'] if normalize(a['location_label'])==normalize(p['location_label'])]
            suggested=sorted({position_organizations['aws_operational'][str(a['id'])] for a in related})
            organization_by_position.append({'local_position_id':p['id'],'site':p['location_label'],'local_restaurant_id':position_organizations['local'][str(p['id'])],
                'suggested_aws_restaurant_ids':';'.join(str(v) for v in suggested),'approved_aws_restaurant_id':'',
                'notes':'Use observed Selection ownership, not the restaurant name or location label alone.'})
        csvfile('position-organization-decisions.csv',organization_by_position,list(organization_by_position[0]))
        write('prototype-decision.json',{'decision':'ARCHIVE_ONLY','reviewed':False,'reason':'The copied prototype contains a closed position explicitly labelled TEST; preserve its archive without promoting it to production.'})
        restaurant_decisions=[{'local_restaurant_id':r['id'],'local_name':r['name'],
            'suggested_aws_restaurant_ids':';'.join(str(a['id']) for a in restaurants['aws_operational'] if normalize(a['name'])==normalize(r['name'])),
            'decision':'REVIEW_ORGANIZATION_IDENTITY','approved_aws_restaurant_id':''} for r in restaurants['local']]
        csvfile('organization-decisions.csv',restaurant_decisions,list(restaurant_decisions[0]))
        sites=sorted({p['location_label'] for group in positions.values() for p in group})
        site_decisions=[{'source_label':site,'suggested_canonical_label':next((p['location_label'] for p in positions['local'] if normalize(p['location_label'])==normalize(site)),''),
            'decision':'REVIEW_SITE_ALIAS','approved_label':''} for site in sites]
        csvfile('site-decisions.csv',site_decisions,list(site_decisions[0]))
        collisions={}
        for table in ('raw_resumes','candidates','applications','candidate_persons','selection_workspace_positions','selection_workspace_position_candidates','rfone_accounts','restaurants'):
            if table in schemas['local'] and table in schemas['aws_operational']:
                local_ids={r['id'] for r in rows('local',table,'id')};cloud_ids={r['id'] for r in rows('aws_operational',table,'id')}
                collisions[table]=len(local_ids & cloud_ids)
        write('numeric-id-collisions.json',collisions)
        account_decisions=[{'source':'local','source_account_id':a['id'],'username':a['username'],'status':a['status'],
            'suggested_aws_account_ids':';'.join(str(b['id']) for b in accounts['aws_operational'] if normalize(b['username'])==normalize(a['username'])),
            'decision':'REVIEW_IDENTITY_AND_PERMISSIONS','approved_aws_account_id':''} for a in accounts['local']]
        csvfile('account-decisions.csv',account_decisions,list(account_decisions[0]))
        history={}
        for source in connections:
            prefix='selproto_' if source=='aws_test' else 'selection_workspace_';history[source]={}
            for table,col in [(prefix+'proposals','source'),(prefix+'messages','status'),(prefix+'email_outbox','status')]:
                if table in schemas[source] and col in [r['name'] for r in schemas[source][table]['columns']]:
                    history[source][table]=[dict(r) for r in connections[source].execute(text('SELECT '+col+',count(*) AS count FROM '+table+' GROUP BY '+col)).mappings()]
            if source=='local':
                for table in ('selection_workspace_action_runs',):
                    history[source][table]=[dict(r) for r in connections[source].execute(text('SELECT status,count(*) AS count FROM '+table+' GROUP BY status')).mappings()]
            history[source]['position_context_keys']={str(p['id']):list(json.loads(p.get('organization_context_json') or '{}')) for p in positions[source]}
        write('history-and-contexts.json',history)
        correspondence=[]
        for table in sorted(required | {t for t in schemas['aws_test'] if t.startswith('selproto_')}):
            correspondence.append({'table':table,'aws_operational_rows':counts['aws_operational'].get(table,0),'aws_test_rows':counts['aws_test'].get(table,0),'local_rows':counts['local'].get(table,0),
                'handling':'ARCHIVE_TEST_BY_DEFAULT' if table.startswith('selproto_') else 'PRESERVE_AWS_AND_REVIEW_LOCAL_IMPORT' if table.startswith(('selection_workspace_','selection_candidate_')) else 'PRESERVE_SHARED_TABLE_NO_REPLACE'})
        csvfile('table-correspondence.csv',correspondence,list(correspondence[0]))
        summary={'created_at_utc':datetime.now(timezone.utc).isoformat(),'aws_connections':False,'live_local_writes':False,'migration_applied':False,
            'local_snapshot_sha256':digest(snapshot),'revisions':{k:[r['version_num'] for r in rows(k,'alembic_version')] for k in connections},
            'position_counts':{k:len(v) for k,v in positions.items()},'raw_resume_counts':{k:len(v) for k,v in documents.items()},
            'exact_duplicate_local_documents':sum(r['proposed_action']=='REUSE_DOCUMENT' for r in exact),'text_only_local_documents':sum(r['proposed_action']=='REVIEW_TEXT_MATCH' for r in exact),
            'new_local_documents':sum(r['proposed_action']=='IMPORT_NEW_DOCUMENT' for r in exact),'file_problems':len(file_problems),
            'config_counts':{k:len(v) for k,v in configs.items()},'missing_tables':{k:v['missing_local_tables'] for k,v in differences.items()},
            'missing_column_counts':{k:len(v['missing_local_columns']) for k,v in differences.items()},'type_difference_counts':{k:len(v['logical_type_differences']) for k,v in differences.items()},
            'apply_allowed':False,'blocking_reviews':['Position/campaign and role mapping','Account ownership and authorization mapping','Candidate/profile conflict decisions','Preserve new local configuration and interview snapshots','Prototype test-data inclusion decision']}
        write('summary.json',summary)
        print('REVIEW PACKAGE:',out);print(json.dumps(summary,ensure_ascii=False))
    finally:
        for c in connections.values():c.close()
        for e in engines.values():e.dispose()


if __name__=='__main__':main()
