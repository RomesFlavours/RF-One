"""Real PostgreSQL import/no-op/rollback tests on a newly cloned LOCAL database only."""
import argparse,json,sys
from pathlib import Path
from datetime import datetime,timezone
import psycopg2
from psycopg2 import sql
from sqlalchemy import text,inspect,MetaData,select
from sqlalchemy.orm import Session
from flask import Flask
from unittest.mock import patch
import production_import as runner


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--port',type=int,default=55479);args=p.parse_args()
    plan=runner.load_plan(args.plan);receipts=json.loads(args.plan.with_suffix('.local-objects.json').read_text());archive=args.archive.resolve()
    target='selection_production_test_'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S');admin=psycopg2.connect(host='127.0.0.1',port=args.port,user='archiveverify',dbname='postgres',options='-c default_transaction_read_only=off');admin.autocommit=True
    with admin.cursor() as c:
        c.execute('show data_directory');assert Path(c.fetchone()[0]).resolve()==(archive/'current-restore-verification/pgdata').resolve()
        c.execute(sql.SQL('CREATE DATABASE {} TEMPLATE {}').format(sql.Identifier(target),sql.Identifier('rfone_current_verify')))
    admin.close();engine=runner.connect_target(f'postgresql+psycopg2://archiveverify@127.0.0.1:{args.port}/{target}','local','apply',None,plan)
    def refuse(fn):
        try:fn()
        except runner.PlanError:return
        raise AssertionError('Expected a safe refusal')
    try:
        refuse(lambda:runner.connect_target('postgresql://x@rfone-dev.coj0wskcg634.us-east-1.rds.amazonaws.com/rfone','local','apply',None,plan))
        refuse(lambda:runner.connect_target('postgresql://x@rfone-dev.coj0wskcg634.us-east-1.rds.amazonaws.com/rfone','production','apply',None,plan))
        refuse(lambda:runner.connect_target(f'postgresql://x@127.0.0.1/{target}?host=elsewhere','local','apply',None,plan))
        before={}
        with engine.connect() as c:
            for table in inspect(c).get_table_names():before[table]=c.scalar(text('SELECT count(*) FROM "'+table+'"'))
        runner.prepare_schema(engine);metadata=MetaData();metadata.reflect(engine)
        with engine.begin() as c:
            for name in plan['inserts']:
                table=metadata.tables[name]
                if 'id' in table.c:c.execute(text("SELECT setval(pg_get_serial_sequence(:table,'id'),10000,true)"),{'table':name})
        refuse(lambda:runner.apply(engine,plan,'local',{}))
        with engine.begin() as c:
            title=c.scalar(text('SELECT title FROM selection_workspace_positions WHERE id=3'));c.execute(text("UPDATE selection_workspace_positions SET title='Later user change' WHERE id=3"))
        refuse(lambda:runner.apply(engine,plan,'local',receipts))
        with engine.begin() as c:c.execute(text('UPDATE selection_workspace_positions SET title=:title WHERE id=3'),{'title':title})
        first=runner.apply(engine,plan,'local',receipts);assert first['status']=='APPLIED' and first['new_rows']==1030
        second=runner.apply(engine,plan,'local',receipts);assert second['status']=='ALREADY_APPLIED' and second['new_rows']==0
        with engine.connect() as c:
            assert c.scalar(text('SELECT count(*) FROM raw_resumes'))==202
            assert c.scalar(text('SELECT count(*) FROM selection_workspace_position_candidates'))==206
            # Deliberately shifted sequences prove no rehearsal identifier was blindly copied.
            assert min(first['id_maps']['selection_workspace_pdl_rules'].values())>10000
            context=json.loads(c.scalar(text('SELECT organization_context_json FROM selection_workspace_positions WHERE id=7')))
            assert set(context['pdl_filter_run']['results'])==set(str(v) for v in first['id_maps']['selection_workspace_position_candidates'].values())
            assert {r['id'] for r in context['pdl_filter_run']['rules']}==set(first['id_maps']['selection_workspace_pdl_rules'].values())
        from workspace import candidate_board,automations,rule_ai
        from rfone_data_store.selection import workspace_models as ps
        app=Flask('migration-production-test')
        with app.test_request_context('/selection/posizioni/7'),Session(engine) as db,patch.object(rule_ai,'generate',side_effect=AssertionError('No AI')),patch.object(automations,'advance',side_effect=AssertionError('No actions')):
            rows=candidate_board.board_rows(db,db.get(ps.Position,7));assert len(rows)==68 and sum(bool(r['result']) for r in rows)==52
            assert all(not r['stale'] for r in rows if r['result']);assert any(r['completed'] for r in rows);db.rollback()
        pc=next(iter(first['id_maps']['selection_workspace_position_candidates'].values()))
        with engine.begin() as c:
            event=c.scalar(text("INSERT INTO selection_workspace_events(position_id,position_candidate_id,kind,detail,actor_account_id,actor_name,created_at) VALUES (7,:pc,'NOTE','New user record',4,'local test',now()) RETURNING id"),{'pc':pc})
        refuse(lambda:runner.rollback(engine,plan))
        with engine.begin() as c:
            assert c.scalar(text('SELECT count(*) FROM selection_workspace_events WHERE id=:id'),{'id':event})==1
            c.execute(text('DELETE FROM selection_workspace_events WHERE id=:id'),{'id':event})
        result=runner.rollback(engine,plan);assert result['status']=='ROLLED_BACK' and result['deleted_rows']==1030
        with engine.connect() as c:
            for table,count in before.items():assert c.scalar(text('SELECT count(*) FROM "'+table+'"'))==count,table
            assert c.scalar(text('SELECT role_code FROM selection_workspace_positions WHERE id=7'))=='FOOD_RUNNER'
            assert c.scalar(text('SELECT role_code FROM selection_workspace_positions WHERE id=8'))=='BUSSER'
        report={'database':target,'aws_access':False,'production_guard_verified':True,'connection_override_rejected':True,'stale_source_rejected':True,'missing_objects_rejected':True,
            'rows_imported':1030,'cv_after_import':202,'links_after_import':206,'generated_ids_rebased':True,'json_refs_and_rule_signature_rebased':True,'current_application_reads_migrated_rows':True,
            'idempotent_repeat_new_rows':0,'rollback_refuses_new_dependent_user_data':True,'rollback_restores_all_original_table_counts':True,'rollback_objects_deleted':0}
        path=args.plan.parent/'production-runner-local-verification.json';path.write_text(json.dumps(report,indent=2),encoding='utf-8');print('PRODUCTION RUNNER LOCAL VERIFIED:',json.dumps(report),flush=True)
    finally:engine.dispose()


if __name__=='__main__':main()
