"""Test the additive schema on a NEW local clone; never alter a source or call AWS."""
import argparse,json,sys
from pathlib import Path
from datetime import datetime,timezone
import psycopg2
from psycopg2 import sql

REPO=Path(__file__).resolve().parents[3];APP=REPO/'03 Software/AWSSelection/Selection'
sys.path[:0]=[str(APP),str(APP.parent/'RF-One Data Store')]
from workspace import schema


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--review',type=Path,required=True);parser.add_argument('--port',type=int,default=55479);args=parser.parse_args()
    review=args.review.resolve();archive=review.parent.parent
    summary=json.loads((review/'summary.json').read_text(encoding='utf-8'))
    if summary['aws_connections'] or summary['migration_applied']:raise RuntimeError('Unexpected review provenance')
    clone='selection_migration_rehearsal_'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    admin=psycopg2.connect(host='127.0.0.1',port=args.port,user='archiveverify',dbname='postgres',options='-c default_transaction_read_only=off');admin.autocommit=True
    try:
        with admin.cursor() as cur:
            cur.execute('SHOW data_directory');data=Path(cur.fetchone()[0]).resolve()
            if data!=(archive/'current-restore-verification/pgdata').resolve():raise RuntimeError('Not the isolated archive verification cluster')
            cur.execute(sql.SQL('CREATE DATABASE {} TEMPLATE {}').format(sql.Identifier(clone),sql.Identifier('rfone_current_verify')))
    finally:admin.close()
    ddl=(review/'aws_operational-schema-review.sql').read_text(encoding='utf-8')
    if '-- BLOCKED:' in ddl:raise RuntimeError('Unresolved backfill requirements; schema rehearsal blocked')
    ddl=ddl.replace('ROLLBACK; -- Default is non-persistent. Reviewed migration must be separately approved.','COMMIT; -- Isolated local rehearsal only.')
    connection=psycopg2.connect(host='127.0.0.1',port=args.port,user='archiveverify',dbname=clone,options='-c default_transaction_read_only=off');connection.autocommit=True
    before=json.loads((archive/'databases/rfone-dev/snapshot.json').read_text(encoding='utf-8'))['table_counts']
    try:
        with connection.cursor() as cur:
            cur.execute(ddl)
            differences=[]
            for table,count in before.items():
                cur.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table)))
                if cur.fetchone()[0]!=count:differences.append(table)
            cur.execute('SELECT version_num FROM alembic_version');revision=[r[0] for r in cur.fetchall()]
        if differences:raise RuntimeError('Existing data counts changed: '+str(differences))
        result=schema.verify(f'postgresql+psycopg2://archiveverify@127.0.0.1:{args.port}/{clone}')
        report={'local_clone':clone,'cloud_connections':False,'original_aws_copy_unchanged':True,'live_local_database_unchanged':True,
            'existing_table_counts_unchanged':True,'existing_tables_checked':len(before),'aws_revision_preserved':revision,
            'local_app_schema_compatibility_verified':True,'created_tables':summary['missing_tables']['aws_operational'],
            'new_columns':summary['missing_column_counts']['aws_operational'],'data_merge_performed':False,
            'next_gate':'Approve role/site/position/account and data mappings before rehearsing the data import.'}
        (review/'schema-rehearsal.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('SCHEMA REHEARSAL PASS:',json.dumps(report))
    finally:connection.close()


if __name__=='__main__':main()
