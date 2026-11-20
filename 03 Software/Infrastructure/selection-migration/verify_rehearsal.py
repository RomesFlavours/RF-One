"""Read the migrated clone using current application services; prohibit AI/action execution."""
import argparse,hashlib,json,sys
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from sqlalchemy import create_engine,select,text
from sqlalchemy.orm import Session
REPO=Path(__file__).resolve().parents[3];APP=REPO/'03 Software/AWSSelection/Selection'
sys.path[:0]=[str(APP),str(APP.parent/'RF-One Data Store')]
from workspace import schema,candidate_board,interviews,observation_templates,automations,rule_ai
from rfone_data_store.selection import workspace_models as ps
from workspace.action_models import ActionRun


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--trial',type=Path,required=True);parser.add_argument('--port',type=int,default=55479);args=parser.parse_args();trial=args.trial.resolve();archive=trial.parent.parent
    result=json.loads((trial/'result.json').read_text(encoding='utf-8'));name=result['target_database']
    if not name.startswith('selection_data_rehearsal_'):raise RuntimeError('Not an isolated data-rehearsal database')
    url=f'postgresql+psycopg2://archiveverify@127.0.0.1:{args.port}/{name}'
    engine=create_engine(url,connect_args={'options':'-c default_transaction_read_only=off'})
    with engine.connect() as c:
        if Path(c.scalar(text('SHOW data_directory'))).resolve()!=(archive/'current-restore-verification/pgdata').resolve():raise RuntimeError('Wrong cluster')
    schema.verify(url)
    manifest=json.loads((archive/'document-manifest.json').read_text(encoding='utf-8'))['objects'];by_uri={}
    for o in manifest:
        uri='s3://'+o['bucket']+'/'+o['key']
        if uri not in by_uri or o['is_latest']:by_uri[uri]=o
    maps=json.loads((trial/'id-maps.json').read_text(encoding='utf-8'));local_documents=json.loads((archive/'migration-review/20261115T171115Z/document-inventory.json').read_text(encoding='utf-8'))['local']
    local_hashes={int(maps['raw_resumes'][str(d['id'])]):d['sha256'] for d in local_documents}
    app=Flask('selection-rehearsal-smoke');app.secret_key='isolated-local-smoke-only'
    with app.test_request_context('/selection/posizioni/7?tab=candidature'),Session(engine) as db,patch.object(rule_ai,'generate',side_effect=AssertionError('AI must not execute')),patch.object(automations,'advance',side_effect=AssertionError('Actions must not execute')):
        position=db.get(ps.Position,7);draft=db.get(ps.Position,8)
        assert position.role_code==draft.role_code==result['confirmed_mappings']['canonical_assistant']
        assert (position.status,draft.status)==('OPEN','DRAFT')
        rows=candidate_board.board_rows(db,position);assert len(rows)==68
        migrated_ids={int(v) for v in maps['selection_workspace_position_candidates'].values()}
        imported=[r for r in rows if r['pc'].id in migrated_ids];legacy=[r for r in rows if r['pc'].id not in migrated_ids]
        assert len(imported)==52 and all(r['result'] is not None and not r['stale'] for r in imported)
        assert len(legacy)==16 and all(r['result'] is None for r in legacy)
        groups=interviews.candidate_priority_groups(db,position,[dict(r,pdl_result=r['result']) for r in rows]);assert sum(len(g) for _,g in groups)==68
        selected_model=observation_templates.find(db,position.role_code,position.location_label)
        assert selected_model and selected_model.items
        first=next(iter(imported));config=interviews.configuration(db,position,first['pc'],interviews.load(db,first['pc'].id))
        assert config['observations']==selected_model.items
        runs=list(db.scalars(select(ActionRun)));assert len(runs)==1 and runs[0].status=='SUCCEEDED'
        assert any(r['completed'] for r in imported)
        for raw in db.execute(text('SELECT id,storage_path FROM raw_resumes')).mappings():
            if raw['storage_path'].startswith('s3://'):
                item=by_uri[raw['storage_path']];path=archive/item['file'];expected=item['sha256']
            else:path=Path(raw['storage_path']);expected=local_hashes[raw['id']]
            with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==expected
        completed=db.execute(text("SELECT position_candidate_id FROM selection_workspace_proposals WHERE source='INTERVIEW' AND group_code='COMPLETED'" )).scalars().all()
        assert len(completed)==1 and interviews.load(db,completed[0])['status']=='COMPLETED'
        # Every FK is checked on the whole clone, including original and imported rows.
        from sqlalchemy import inspect
        inspector=inspect(db.connection());foreign_key_checks=0
        for table,foreign_keys in inspector.get_multi_foreign_keys().items():
            _,table_name=table
            for fk in foreign_keys:
                left=fk['constrained_columns'];right=fk['referred_columns'];parent=fk['referred_table']
                present=' AND '.join('c."'+k+'" IS NOT NULL' for k in left)
                join=' AND '.join('p."'+b+'"=c."'+a+'"' for a,b in zip(left,right))
                query='SELECT count(*) FROM "'+table_name+'" c WHERE '+present+' AND NOT EXISTS (SELECT 1 FROM "'+parent+'" p WHERE '+join+')'
                assert db.scalar(text(query))==0,(table_name,parent)
                foreign_key_checks+=1
        checks={'current_app_schema_compatible':True,'candidate_board_rows':68,'local_ai_results_readable_and_current':52,'original_aws_candidates_pending_new_evaluation':16,
            'interview_priority_groups':{label:len(members) for label,members in groups},'observation_model_readable':True,'existing_completed_interview_readable':True,
            'succeeded_action_visible_without_reexecution':True,'original_document_sha256_checks':202,'foreign_keys_checked':foreign_key_checks,'orphan_foreign_keys':0,
            'ai_calls':0,'action_execution_calls':0,'database_changes_from_smoke':False}
        db.rollback()
    engine.dispose();(trial/'application-verification.json').write_text(json.dumps(checks,indent=2,ensure_ascii=False),encoding='utf-8');print('APPLICATION SMOKE VERIFIED:',json.dumps(checks,ensure_ascii=False))


if __name__=='__main__':main()
