"""Export the verified local rehearsal as a data-only, checksummed release plan."""
import argparse,copy,json,sys
from pathlib import Path
from sqlalchemy import create_engine,MetaData,select,text
from production_import import canonical,digest,TABLES,PlanError


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trial',type=Path,required=True);p.add_argument('--upload-plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--port',type=int,default=55479);args=p.parse_args()
    trial=args.trial.resolve();archive=trial.parent.parent;result=json.loads((trial/'result.json').read_text(encoding='utf-8'));name=result['target_database']
    if not name.startswith('selection_data_rehearsal_') or not result['data_import_success']:raise PlanError('Verified isolated trial required.')
    maps=json.loads((trial/'id-maps.json').read_text(encoding='utf-8'));order=json.loads((trial/'imported-row-counts.json').read_text(encoding='utf-8'))
    source=json.loads((trial/'aws-selection-before.json').read_text(encoding='utf-8'));uploads=json.loads(args.upload_plan.read_text(encoding='utf-8'))['objects']
    local_uploads={str(o['source_local_raw_resume_id']):o for o in uploads};raw_to_uri={str(maps['raw_resumes'][k]):v['future_storage_uri'] for k,v in local_uploads.items()}
    engine=create_engine(f'postgresql+psycopg2://archiveverify@127.0.0.1:{args.port}/{name}',connect_args={'options':'-c default_transaction_read_only=on'})
    metadata=MetaData();metadata.reflect(engine)
    try:
        inserts={};updates=[]
        with engine.connect() as c:
            if Path(c.scalar(text('SHOW data_directory'))).resolve()!=(archive/'current-restore-verification/pgdata').resolve():raise PlanError('Unexpected source cluster.')
            for table in order:
                if table not in TABLES:raise PlanError('Unapproved import table.')
                obj=metadata.tables[table];pk=list(obj.primary_key.columns)[0];rows=[]
                # local-key order is the proven dependency order, including rule overrides.
                original_ids={r[pk.name] for r in source.get(table,[])}
                for target_id in dict.fromkeys(maps[table].values()):
                    if target_id in original_ids:continue
                    row=dict(c.execute(select(obj).where(pk==target_id)).mappings().one())
                    if table=='raw_resumes':row['storage_path']=raw_to_uri[str(target_id)]
                    rows.append(canonical(row))
                if len(rows)!=order[table]:raise PlanError('Imported count mismatch.')
                inserts[table]=rows
            positions=metadata.tables['selection_workspace_positions'];anchors=[]
            for row in source['selection_workspace_positions']:
                if row['id'] not in (3,6,7,8):continue
                current=c.execute(select(positions).where(positions.c.id==row['id'])).mappings().one()
                updates.append({'id':row['id'],'values':canonical({k:current[k] for k in ('role_code','organization_context_json')})})
                anchors.append({'table':positions.name,'id':row['id'],'before':row})
            for row in source['rfone_accounts']:
                if row['id'] in (4,14):anchors.append({'table':'rfone_accounts','id':row['id'],'before':{k:row[k] for k in ('id','username','status','is_owner')}})
            for row in source['restaurants']:
                if row['id']==1:anchors.append({'table':'restaurants','id':1,'before':row})
        plan={'version':1,'batch_id':'selection-'+result['source_baseline_sha256'][:24],
            'source_baseline_sha256':result['source_baseline_sha256'],'confirmed':result['confirmed_mappings'],
            'baseline_counts':[{'table':'raw_resumes','restaurant_id':1,'count':150},{'table':'candidates','restaurant_id':1,'count':150},
                {'table':'selection_workspace_positions','count':7},{'table':'selection_workspace_position_candidates','count':154}],
            'anchors':anchors,'inserts':inserts,'updates':{'selection_workspace_positions':updates},
            'objects':[{'uri':o['future_storage_uri'],'sha256':o['sha256'],'bytes':o['bytes']} for o in uploads]}
        plan['plan_sha256']=digest(plan);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(plan,indent=2,ensure_ascii=False),encoding='utf-8')
        receipt={o['future_storage_uri']:o['file'] for o in uploads};args.output.with_suffix('.local-objects.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        args.output.with_suffix('.approval.example.json').write_text(json.dumps({'approved':False,'plan_sha256':plan['plan_sha256'],'target_host':'rfone-dev.coj0wskcg634.us-east-1.rds.amazonaws.com','target_database':'rfone'},indent=2),encoding='utf-8')
        print('PRODUCTION PLAN PREPARED:',args.output,'rows:',sum(len(v) for v in inserts.values()),'objects:',len(uploads),'production approved: false')
    finally:engine.dispose()


if __name__=='__main__':main()
